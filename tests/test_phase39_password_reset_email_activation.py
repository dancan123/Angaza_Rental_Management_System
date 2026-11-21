"""
Phase 39 — Tests for Password Reset, Email Receipt, and Business Account Email Activation
Tests:
  1. Login page shows "Forgot password?" link
  2. Request password reset with registered email generates token and logs email notification
  3. Reset password using valid token successfully updates password and redirects to login
  4. Reset password with invalid/tampered/expired token fails gracefully
  5. Self-onboarding /register automatically dispatches activation email and provides activation link
  6. Account activation via token confirms user and organization email_verified = True and is_active = True
  7. Activation with invalid/expired token returns friendly failure page
"""
import pytest
from app import create_app, db
from app.models.organization import Organization
from app.models.user import User
from app.models.communication import Notification
from app.services.email_auth_service import EmailAuthService


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


def test_login_page_renders_forgot_password_link(client):
    resp = client.get('/auth/login')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Forgot password?' in html
    assert '/auth/forgot-password' in html


def test_forgot_password_page_renders(client):
    resp = client.get('/auth/forgot-password')
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Reset Your Password' in html
    assert 'Registered Email Address' in html


def test_forgot_password_submission_dispatches_email(client, app_instance):
    with app_instance.app_context():
        # Find or create a test user
        user = User.query.filter(User.email.isnot(None)).first()
        assert user is not None
        test_email = user.email

        resp = client.post('/auth/forgot-password', data={'email': test_email}, follow_redirects=True)
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'password reset link has been sent' in html

        # Verify notification record was logged
        notif = Notification.query.filter_by(recipient_user_id=user.id, channel='EMAIL').order_by(Notification.id.desc()).first()
        assert notif is not None
        assert 'Password Reset' in notif.title
        assert '/auth/reset-password/' in notif.message


def test_reset_password_with_valid_token(client, app_instance):
    with app_instance.app_context():
        user = User.query.filter(User.email.isnot(None)).first()
        token = EmailAuthService.generate_password_reset_token(user.id)
        user_id = user.id
        old_hash = user.password_hash

    # GET reset form
    get_resp = client.get(f'/auth/reset-password/{token}')
    assert get_resp.status_code == 200
    assert 'Set New Password' in get_resp.data.decode('utf-8')

    # POST new password
    post_resp = client.post(f'/auth/reset-password/{token}', data={
        'password': 'BrandNewPassword123!',
        'confirm_password': 'BrandNewPassword123!'
    }, follow_redirects=True)

    assert post_resp.status_code == 200
    html = post_resp.data.decode('utf-8')
    assert 'successfully reset' in html.lower()

    # Verify password was updated in DB
    with app_instance.app_context():
        u = db.session.get(User, user_id)
        assert u.check_password('BrandNewPassword123!')
        assert u.password_hash != old_hash


def test_reset_password_with_invalid_token(client):
    resp = client.get('/auth/reset-password/invalid-token-tampered', follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'invalid or has expired' in html.lower()


def test_self_registration_dispatches_email_activation(client, app_instance):
    import uuid
    uid = uuid.uuid4().hex[:6]
    reg_data = {
        'organization_name': f'Greenfield Properties {uid}',
        'full_name': 'George Washington',
        'email': f'george_{uid}@greenfield.co.ke',
        'phone': '+254711889900',
        'password': 'Password123!',
        'subscription_tier': 'COMBINED_SUITE',
        'region': 'Nairobi',
        'county': 'Nairobi City',
        'town': 'Westlands'
    }

    resp = client.post('/auth/register', data=reg_data, follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Account Ready!' in html
    assert 'Confirm Your Business Email' in html
    assert '/auth/activate/' in html

    # Verify notification log
    with app_instance.app_context():
        new_org = Organization.query.filter_by(name=f'Greenfield Properties {uid}').first()
        assert new_org is not None

        new_user = User.query.filter_by(email=f'george_{uid}@greenfield.co.ke').first()
        assert new_user is not None

        notif = Notification.query.filter_by(recipient_user_id=new_user.id, notification_type='ACCOUNT_ACTIVATION').first()
        assert notif is not None
        assert 'Confirm Your Email' in notif.title


def test_activate_account_via_token(client, app_instance):
    with app_instance.app_context():
        org = Organization.query.first()
        user = User.query.filter_by(organization_id=org.id).first()
        assert org is not None and user is not None

        token = EmailAuthService.generate_activation_token(org.id, user.id)

    resp = client.get(f'/auth/activate/{token}', follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Account Confirmed &amp; Activated!' in html or 'Account Confirmed & Activated!' in html

    # Verify database state
    with app_instance.app_context():
        u = db.session.get(User, user.id)
        o = db.session.get(Organization, org.id)
        assert u.email_verified is True
        assert u.email_verified_at is not None
        assert o.email_verified is True
        assert o.is_active is True


def test_activate_account_with_invalid_token(client):
    resp = client.get('/auth/activate/bad-invalid-token-123', follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert 'Activation Link Expired' in html or 'invalid' in html.lower()
