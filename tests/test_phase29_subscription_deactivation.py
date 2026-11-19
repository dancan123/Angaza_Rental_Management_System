"""
Phase 29 Super Admin Subscription & Organization Activation / Deactivation Suite
Verifies:
  1. Super Admin can deactivate / suspend an organization for unpaid premiums or overdue fees.
  2. Setting custom suspension reasons (e.g., 'Unpaid Monthly System Subscription Premium').
  3. Non-superadmin users of a deactivated organization are blocked from logging in with a clear explanation.
  4. Active sessions for deactivated organizations are intercepted and logged out by enforce_subscription_status.
  5. Super Admin 1-click reactivation restores full system access and extends subscription validity.
  6. Public website (/site/<slug>) returns 503 service notice when organization is deactivated.
"""
import pytest
from datetime import date, datetime, timedelta
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.organization import Organization
from app.models.property import Property, RentalUnit


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        # Seed roles
        superadmin_role = Role(name='SUPERADMIN', display_name='Super Administrator', description='Super Admin')
        manager_role = Role(name='PROPERTY_MANAGER', display_name='Property Manager', description='Property Manager')
        perm_dashboard = Permission(code='dashboard.view', module='dashboard', description='View Dashboard')
        db.session.add_all([superadmin_role, manager_role, perm_dashboard])
        manager_role.permissions.append(perm_dashboard)
        db.session.commit()

        # 1. Superadmin User
        superadmin = User(
            username='masteradmin',
            full_name='Super Admin User',
            email='superadmin@angazarentals.com',
            role_id=superadmin_role.id,
            is_active=True
        )
        superadmin.set_password('SuperSecret123!')

        # 2. Organization: Highland Estates
        org = Organization(
            name='Highland Estates Kenya',
            slug='highland-estates',
            org_code='HIGHLAND',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
            subscription_expires_at=datetime.utcnow() + timedelta(days=15),
            is_active=True,
            enable_rentals=True,
            enable_hospitality=True,
            contact_phone='+254700112233',
            contact_email='info@highland.co.ke'
        )
        db.session.add_all([superadmin, org])
        db.session.commit()

        # 3. Manager User under Highland Estates
        manager = User(
            username='highlandmanager',
            full_name='Peter Ochieng',
            email='peter@highland.co.ke',
            role_id=manager_role.id,
            organization_id=org.id,
            is_active=True
        )
        manager.set_password('Highland2026!')
        db.session.add(manager)

        # 4. Property and Vacant Unit
        landlord = Landlord(name='Highland Owner', phone='+254700000002')
        db.session.add(landlord)
        db.session.commit()

        prop = Property(
            name='Highland Towers',
            ref_number='HL-001',
            landlord_id=landlord.id,
            organization_id=org.id,
            location='Upperhill, Nairobi'
        )
        db.session.add(prop)
        db.session.commit()

        unit = RentalUnit(
            property_id=prop.id,
            unit_number='B4',
            unit_type='APARTMENT',
            rent_amount_cents=6000000,
            operational_type='LONG_TERM',
            occupancy_status='VACANT'
        )
        db.session.add(unit)
        db.session.commit()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login_as_superadmin(client):
    return client.post('/auth/login', data={
        'username': 'masteradmin',
        'password': 'SuperSecret123!'
    }, follow_redirects=True)


def login_as_manager(client):
    return client.post('/auth/login', data={
        'org_code': 'HIGHLAND',
        'username': 'highlandmanager',
        'password': 'Highland2026!'
    }, follow_redirects=True)


def test_superadmin_deactivates_organization_for_unpaid_premium(client, app):
    """Test superadmin deactivating an organization with a specific suspension reason."""
    with app.app_context():
        login_as_superadmin(client)
        org = Organization.query.filter_by(slug='highland-estates').first()

        # Deactivate via status update
        resp = client.post(f'/platform/organizations/{org.id}/status', data={
            'subscription_status': 'SUSPENDED',
            'suspension_reason': 'Unpaid Monthly System Premium - KES 10,000 Overdue'
        }, follow_redirects=True)
        assert resp.status_code == 200

        org_refreshed = db.session.get(Organization, org.id)
        assert org_refreshed.subscription_status == 'SUSPENDED'
        assert org_refreshed.is_active is False
        assert org_refreshed.is_suspended is True
        assert 'Unpaid Monthly System Premium' in org_refreshed.suspension_reason


def test_deactivated_organization_user_blocked_at_login(client, app):
    """Test that users of a deactivated organization are rejected at login with reason displayed."""
    with app.app_context():
        org = Organization.query.filter_by(slug='highland-estates').first()
        org.subscription_status = 'SUSPENDED'
        org.is_active = False
        org.suspension_reason = 'Unpaid Monthly System Premium'
        db.session.commit()

        # Attempt to log in as organization manager
        resp = login_as_manager(client)
        assert resp.status_code == 200
        assert b'Access Suspended' in resp.data
        assert b'Unpaid Monthly System Premium' in resp.data


def test_active_session_intercepted_on_deactivation(client, app):
    """Test that already logged-in users are intercepted and logged out when org is deactivated."""
    with app.app_context():
        # First log in while active
        resp_login = login_as_manager(client)
        assert resp_login.status_code == 200

        # Now deactivate the organization
        org = Organization.query.filter_by(slug='highland-estates').first()
        org.subscription_status = 'SUSPENDED'
        org.is_active = False
        org.suspension_reason = 'Payment overdue'
        db.session.commit()

        # Access protected route
        resp = client.get('/dashboard/', follow_redirects=True)
        assert resp.status_code == 200
        assert b'Access Suspended' in resp.data


def test_superadmin_1click_reactivation(client, app):
    """Test superadmin 1-click toggle reactivation restoring full access and 30-day validity."""
    with app.app_context():
        org = Organization.query.filter_by(slug='highland-estates').first()
        org.subscription_status = 'SUSPENDED'
        org.is_active = False
        org.suspension_reason = 'Unpaid Premium'
        db.session.commit()

        login_as_superadmin(client)

        # 1-click toggle reactivation
        resp = client.post(f'/platform/organizations/{org.id}/toggle-status', follow_redirects=True)
        assert resp.status_code == 200

        org_refreshed = db.session.get(Organization, org.id)
        assert org_refreshed.subscription_status == 'ACTIVE'
        assert org_refreshed.is_active is True
        assert org_refreshed.is_suspended is False
        assert org_refreshed.suspension_reason is None

        # Verify manager can now log in
        client.get('/auth/logout')
        resp_mgr = login_as_manager(client)
        assert resp_mgr.status_code == 200
        assert b'Welcome back, Peter Ochieng' in resp_mgr.data


def test_public_website_shows_notice_when_deactivated(client, app):
    """Test that public site returns 503 service notice when organization is deactivated."""
    with app.app_context():
        org = Organization.query.filter_by(slug='highland-estates').first()
        org.subscription_status = 'SUSPENDED'
        org.is_active = False
        db.session.commit()

        resp = client.get('/site/highland-estates')
        assert resp.status_code == 503
        assert b'Website Temporarily Unavailable' in resp.data
        assert b'Highland Estates Kenya' in resp.data
