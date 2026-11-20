"""
Phase 33 — Subscription Expiry, Clock-out & Lockout Notification Tests
======================================================================
Tests Superadmin's ability to set subscription expiration dates, clock out
organizations, and provide custom notification messages displayed to
users upon lockout.
"""
import pytest
import random
from datetime import datetime, timedelta
from app import create_app, db
from app.models.organization import Organization
from app.models.user import User, Role


@pytest.fixture(scope='module')
def app():
    application = create_app()
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    return application


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


@pytest.fixture(scope='module')
def setup_org(app):
    """Creates a test organization with a manager and superadmin."""
    r = random.randint(100000, 999999)
    with app.app_context():
        # Ensure superadmin exists
        superadmin = User.query.filter_by(username='admin').first()
        if not superadmin:
            superadmin_role = Role.query.filter_by(name='SUPER_ADMIN').first()
            superadmin = User(
                username=f'superadmin_{r}',
                email=f'sa_{r}@platform.co.ke',
                full_name='Master Super Admin',
                role=superadmin_role,
                is_active=True
            )
            superadmin.set_password('AdminPass123!')
            db.session.add(superadmin)

        manager_role = Role.query.filter_by(name='PROPERTY_MANAGER').first()

        org = Organization(
            name=f'Skyline Property Test {r}',
            slug=f'skyline-test-{r}',
            org_code=f'ANG{r % 10000:04d}',
            is_active=True,
            subscription_status='ACTIVE',
            subscription_tier='RENTAL_STANDARD',
            subscription_expires_at=datetime.utcnow() + timedelta(days=30),
            contact_email=f'manager_{r}@skyline.co.ke'
        )
        db.session.add(org)
        db.session.flush()

        manager = User(
            username=f'skymanager_{r}',
            email=f'skymanager_{r}@skyline.co.ke',
            full_name=f'Skyline Manager {r}',
            role=manager_role,
            organization_id=org.id,
            is_active=True
        )
        manager.set_password('ManagerPass123!')
        db.session.add(manager)
        db.session.commit()

        return {
            'org_id': org.id,
            'org_code': org.org_code,
            'manager_username': manager.username,
            'manager_password': 'ManagerPass123!',
            'superadmin_username': superadmin.username,
            'superadmin_password': 'AdminPass123!' if superadmin.username == f'superadmin_{r}' else 'admin123'
        }


def test_active_organization_can_login(client, app, setup_org):
    """An active organization with valid subscription can log in."""
    with app.app_context():
        org = db.session.get(Organization, setup_org['org_id'])
        org.is_active = True
        org.subscription_status = 'ACTIVE'
        org.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
        org.suspension_reason = None
        db.session.commit()

    res = client.post('/auth/login', data={
        'username': setup_org['manager_username'],
        'password': setup_org['manager_password'],
        'org_code': setup_org['org_code']
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b'Welcome back' in res.data or b'Dashboard' in res.data
    # Clean up session
    client.get('/auth/logout', follow_redirects=True)


def test_expired_subscription_locks_out_manager_with_clockout_message(client, app, setup_org):
    """When subscription_expires_at is in the past, manager login is rejected with expiry notice."""
    past_date = datetime.utcnow() - timedelta(days=2)
    with app.app_context():
        org = db.session.get(Organization, setup_org['org_id'])
        org.subscription_expires_at = past_date
        org.suspension_reason = None
        db.session.commit()

        assert org.is_expired is True
        assert org.is_suspended is True

    res = client.post('/auth/login', data={
        'username': setup_org['manager_username'],
        'password': setup_org['manager_password'],
        'org_code': setup_org['org_code']
    }, follow_redirects=True)

    assert res.status_code == 200
    # Must show Access Suspended banner
    assert b'Access Suspended' in res.data
    assert b'deactivated' in res.data


def test_custom_suspension_reason_displayed_on_lockout(client, app, setup_org):
    """When superadmin specifies a custom reason, manager sees that exact reason upon login."""
    custom_msg = "October SaaS hosting premium of KES 7,500 is overdue for settlement"
    with app.app_context():
        org = db.session.get(Organization, setup_org['org_id'])
        org.subscription_expires_at = datetime.utcnow() - timedelta(days=1)
        org.suspension_reason = custom_msg
        db.session.commit()

    res = client.post('/auth/login', data={
        'username': setup_org['manager_username'],
        'password': setup_org['manager_password'],
        'org_code': setup_org['org_code']
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b'Access Suspended' in res.data
    assert custom_msg.encode('utf-8') in res.data


def test_superadmin_can_update_timeline_and_unlock(client, app, setup_org):
    """Superadmin can extend timeline via POST /platform/organizations/<id>/timeline to reactivate access."""
    # First login as superadmin
    with app.app_context():
        sa = User.query.filter_by(username='admin').first()
        if not sa:
            sa = User.query.filter_by(username=setup_org['superadmin_username']).first()
        sa_username = sa.username

    # Authenticate superadmin
    res_login = client.post('/auth/login', data={
        'username': sa_username,
        'password': 'AdminPass123!' if sa_username.startswith('superadmin_') else 'admin123',
        'org_code': 'ANG0001'
    }, follow_redirects=True)
    assert res_login.status_code == 200

    # Future date for exact expiry
    future_date_str = (datetime.utcnow() + timedelta(days=60)).strftime('%Y-%m-%d')
    new_reason = "Paid via M-Pesa Till 458920 — Valid until next renewal"

    post_res = client.post(f"/platform/organizations/{setup_org['org_id']}/timeline", data={
        'expiry_date': future_date_str,
        'days': '',
        'suspension_reason': new_reason,
        'status': 'ACTIVE'
    }, follow_redirects=True)

    assert post_res.status_code == 200

    # Verify database state
    with app.app_context():
        org = db.session.get(Organization, setup_org['org_id'])
        assert org.is_expired is False
        assert org.is_active is True
        assert org.subscription_status == 'ACTIVE'
        assert org.subscription_expires_at.strftime('%Y-%m-%d') == future_date_str
        assert org.suspension_reason == new_reason

    # Logout superadmin
    client.get('/auth/logout', follow_redirects=True)

    # Manager can now successfully log in again!
    res_mgr = client.post('/auth/login', data={
        'username': setup_org['manager_username'],
        'password': setup_org['manager_password'],
        'org_code': setup_org['org_code']
    }, follow_redirects=True)

    assert res_mgr.status_code == 200
    assert b'Welcome back' in res_mgr.data or b'Dashboard' in res_mgr.data
    client.get('/auth/logout', follow_redirects=True)
