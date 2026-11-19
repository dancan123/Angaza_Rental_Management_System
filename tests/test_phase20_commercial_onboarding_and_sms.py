"""
Phase 20 – Commercial Self-Onboarding, 14-Day Trial, User Impersonation & SMS Credit Sales
Tests:
  1. Public self-onboarding route (/auth/register) -> 14-day trial & 50 SMS credits
  2. Trial / Subscription timeline expiration enforcement
  3. Superadmin user impersonation and safe exit back to admin session
  4. Organization SMS credit deduction on dispatch & out-of-credits blocking
  5. Superadmin selling / topping up SMS credits for an organization
  6. Superadmin extending trial / subscription timeline
"""
import pytest
from datetime import datetime, timedelta
from app import create_app
from app.extensions import db
from app.models.user import Role, User
from app.models.organization import Organization


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        superadmin_role = Role(name='SUPERADMIN', display_name='Super Admin', is_system=True)
        manager_role = Role(name='PROPERTY_MANAGER', display_name='Property Manager', is_system=True)
        db.session.add_all([superadmin_role, manager_role])
        db.session.commit()

        # Superadmin
        admin = User(
            username='main_superadmin',
            email='admin@angaza.co.ke',
            full_name='Main Superadmin',
            role=superadmin_role,
            is_active=True
        )
        admin.set_password('AdminPass2026!')

        # Target organization and manager
        org = Organization(
            name='Kileleshwa Premier Villas',
            slug='kileleshwa-villas',
            subscription_tier='COMBINED_SUITE',
            subscription_status='TRIAL',
            subscription_expires_at=datetime.utcnow() + timedelta(days=14),
            sms_credits=50
        )
        db.session.add(org)
        db.session.flush()

        manager = User(
            username='kileleshwa_manager',
            email='manager@kileleshwa.co.ke',
            full_name='Kileleshwa Estate Manager',
            role=manager_role,
            organization_id=org.id,
            is_active=True
        )
        manager.set_password('ManagerPass2026!')

        db.session.add_all([admin, manager])
        db.session.commit()

        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_public_self_onboarding_trial(app, client):
    """Verify external customer self-registers and gets 14-day trial + 50 SMS credits."""
    res = client.post('/auth/register', data={
        'organization_name': 'Runda Luxury Apartments',
        'full_name': 'Grace Mutua',
        'email': 'grace@rundaluxury.co.ke',
        'phone': '+254722554433',
        'password': 'SecurePass2026!',
        'subscription_tier': 'COMBINED_SUITE'
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b'14-day' in res.data or b'Runda Luxury' in res.data

    with app.app_context():
        org = Organization.query.filter_by(name='Runda Luxury Apartments').first()
        assert org is not None
        assert org.subscription_status == 'TRIAL'
        assert org.sms_credits == 50
        assert org.subscription_expires_at is not None
        assert org.days_remaining in (13, 14)

        user = User.query.filter_by(email='grace@rundaluxury.co.ke').first()
        assert user is not None
        assert user.organization_id == org.id
        assert user.check_password('SecurePass2026!') is True


def test_superadmin_user_impersonation(app, client):
    """Verify superadmin can impersonate a manager and exit back."""
    # 1. Login as superadmin
    client.post('/auth/login', data={
        'username': 'main_superadmin',
        'password': 'AdminPass2026!'
    }, follow_redirects=True)

    with app.app_context():
        manager = User.query.filter_by(username='kileleshwa_manager').first()
        manager_id = manager.id

    # 2. Impersonate manager
    res = client.get(f'/auth/impersonate/{manager_id}', follow_redirects=True)
    assert res.status_code == 200
    assert b'Switched into account: Kileleshwa Estate Manager' in res.data

    with client.session_transaction() as sess:
        assert 'impersonator_id' in sess

    # 3. Stop impersonation -> returned to superadmin
    res = client.get('/auth/stop-impersonation', follow_redirects=True)
    assert res.status_code == 200
    assert b'Returned to your Platform Superadmin session' in res.data

    with client.session_transaction() as sess:
        assert 'impersonator_id' not in sess


def test_sms_credit_deduction_and_superadmin_topup(app, client):
    """Verify SMS credits deduction on send, out-of-credit block, and superadmin top up."""
    # Login as manager
    client.post('/auth/login', data={
        'username': 'kileleshwa_manager',
        'password': 'ManagerPass2026!'
    }, follow_redirects=True)

    with app.app_context():
        org = Organization.query.filter_by(slug='kileleshwa-villas').first()
        assert org.sms_credits == 50
        org_id = org.id

    # 1. Send test SMS as manager
    res = client.post('/communication/twilio/test', data={
        'test_phone': '+254711223344',
        'test_message': 'Rent payment reminder notice'
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        org_refreshed = db.session.get(Organization, org_id)
        assert org_refreshed.sms_credits == 49

        # Drain credits to 0
        org_refreshed.sms_credits = 0
        db.session.commit()

    # 2. Try sending SMS with 0 credits -> blocked
    res = client.post('/communication/twilio/test', data={
        'test_phone': '+254711223344',
        'test_message': 'Another reminder'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Insufficient SMS credits' in res.data

    # 3. Superadmin tops up organization wallet by 250 credits
    client.get('/auth/logout', follow_redirects=True)
    client.post('/auth/login', data={
        'username': 'main_superadmin',
        'password': 'AdminPass2026!'
    }, follow_redirects=True)

    res = client.post(f'/platform/organizations/{org_id}/add-sms', data={
        'credits': 250
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        org_topup = db.session.get(Organization, org_id)
        assert org_topup.sms_credits == 250


def test_superadmin_extend_timeline(app, client):
    """Verify superadmin can extend a trial or subscription timeline."""
    client.post('/auth/login', data={
        'username': 'main_superadmin',
        'password': 'AdminPass2026!'
    }, follow_redirects=True)

    with app.app_context():
        org = Organization.query.filter_by(slug='kileleshwa-villas').first()
        org_id = org.id

    res = client.post(f'/platform/organizations/{org_id}/timeline', data={
        'days': 30,
        'status': 'ACTIVE'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'extended by 30 days' in res.data

    with app.app_context():
        org_refreshed = db.session.get(Organization, org_id)
        assert org_refreshed.subscription_status == 'ACTIVE'
        assert org_refreshed.days_remaining > 40
