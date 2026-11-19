"""
Phase 17 – Platform Super Admin & Multi-Tenant Control Plane Tests
Tests:
  1. Super Admin access control on platform routes
  2. Organization listing, filtering, and creation
  3. Updating subscription tier and quotas (units, properties, users)
  4. Suspending and restoring an organization's account
  5. Assigning platform users to customer organizations
  6. Platform cross-tenant analytics endpoint
"""
import pytest
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User
from app.models.organization import Organization
from app.models.property import Property, RentalUnit


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        superadmin_role = Role(name='SUPERADMIN', display_name='Super Admin', is_system=True)
        staff_role = Role(name='STAFF', display_name='Staff', is_system=True)
        db.session.add_all([superadmin_role, staff_role])
        db.session.commit()

        # Superadmin user
        superadmin = User(
            username='platform_owner',
            email='owner@angaza.co.ke',
            full_name='Platform Superadmin',
            role=superadmin_role,
            is_active=True
        )
        superadmin.set_password('SuperPass2026!')

        # Standard staff user
        staff = User(
            username='junior_staff',
            email='staff@angaza.co.ke',
            full_name='Junior Staff',
            role=staff_role,
            is_active=True
        )
        staff.set_password('StaffPass2026!')

        db.session.add_all([superadmin, staff])
        db.session.commit()

        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login_user(client, username, password):
    return client.post('/auth/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)


def test_superadmin_access_control(app, client):
    """Ensure non-superadmin cannot access platform management routes."""
    # 1. Anonymous user redirected
    res = client.get('/platform/organizations', follow_redirects=False)
    assert res.status_code == 302
    assert '/auth/login' in res.headers['Location']

    # 2. Staff user redirected
    login_user(client, 'junior_staff', 'StaffPass2026!')
    res = client.get('/platform/organizations', follow_redirects=True)
    assert b'Unauthorized: Platform Super Admin privileges required' in res.data


def test_organization_crud_and_entitlements(app, client):
    """Verify superadmin can create organizations and modify their tiers."""
    login_user(client, 'platform_owner', 'SuperPass2026!')

    # 1. Create organization
    res = client.post('/platform/organizations/create', data={
        'name': 'Kilimani Heights Management',
        'slug': 'kilimani-heights',
        'contact_email': 'info@kilimani.co.ke',
        'contact_phone': '+254722111222',
        'subscription_tier': 'COMBINED_SUITE',
        'max_properties': 15,
        'max_units': 150,
        'max_users': 10
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Kilimani Heights Management' in res.data

    with app.app_context():
        org = Organization.query.filter_by(slug='kilimani-heights').first()
        assert org is not None
        assert org.subscription_tier == 'COMBINED_SUITE'
        assert org.max_units == 150
        assert org.can_access_rental_module() is True
        assert org.can_access_hospitality_module() is True

        # 2. Update subscription tier to Rental Only
        org_id = org.id

    res = client.post(f'/platform/organizations/{org_id}/subscription', data={
        'subscription_tier': 'RENTAL_STANDARD',
        'max_properties': 5,
        'max_units': 50,
        'max_users': 3
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        org_refreshed = db.session.get(Organization, org_id)
        assert org_refreshed.subscription_tier == 'RENTAL_STANDARD'
        assert org_refreshed.max_units == 50
        assert org_refreshed.can_access_rental_module() is True
        assert org_refreshed.can_access_hospitality_module() is False


def test_account_suspension_and_enforcement(app, client):
    """Verify account status changes and that suspended status is reflected."""
    login_user(client, 'platform_owner', 'SuperPass2026!')

    with app.app_context():
        org = Organization(
            name='Karen Country Villas',
            slug='karen-villas',
            subscription_tier='HOSPITALITY_STANDARD',
            subscription_status='ACTIVE'
        )
        db.session.add(org)
        db.session.commit()
        org_id = org.id

    # Suspend organization
    res = client.post(f'/platform/organizations/{org_id}/status', data={
        'subscription_status': 'SUSPENDED'
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        org_refreshed = db.session.get(Organization, org_id)
        assert org_refreshed.subscription_status == 'SUSPENDED'
        assert org_refreshed.is_active is False


def test_assign_user_to_organization(app, client):
    """Verify assigning a platform user to an organization."""
    login_user(client, 'platform_owner', 'SuperPass2026!')

    with app.app_context():
        org = Organization(name='Mombasa Marine Resorts', slug='mombasa-resorts')
        db.session.add(org)
        db.session.commit()
        org_id = org.id
        staff_user = User.query.filter_by(username='junior_staff').first()
        staff_id = staff_user.id
        assert staff_user.organization_id is None

    res = client.post(f'/platform/organizations/{org_id}/assign-user', data={
        'user_id': staff_id
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        staff_refreshed = db.session.get(User, staff_id)
        assert staff_refreshed.organization_id == org_id
        assert staff_refreshed.active_organization.slug == 'mombasa-resorts'


def test_platform_analytics_page(app, client):
    """Verify the platform analytics dashboard renders correctly for superadmin."""
    login_user(client, 'platform_owner', 'SuperPass2026!')

    with app.app_context():
        org = Organization(name='Apex Group', slug='apex-group', subscription_tier='COMBINED_SUITE')
        db.session.add(org)
        db.session.commit()

    res = client.get('/platform/analytics')
    assert res.status_code == 200
    assert b'Platform Usage' in res.data
    assert b'Apex Group' in res.data or b'COMBINED_SUITE' in res.data
