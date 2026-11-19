"""
Phase 22 – Per-Premises Module Checkpoints (Rentals & Airbnb Toggles) Tests
Verifies:
  1. Superadmin can view and 1-click toggle Rentals and Airbnb/Hospitality modules per organization.
  2. Organization model methods can_access_rental_module() and can_access_hospitality_module() honor checkpoint flags.
  3. Tier automatically synchronizes with active modules (COMBINED_SUITE, RENTAL_STANDARD, HOSPITALITY_STANDARD).
  4. Explicit module selection in the subscription edit modal and new organization registration.
  5. Navigation sidebar hides gated module sections for non-superadmin users based on premises checkpoints.
"""
import pytest
from app import create_app
from app.extensions import db
from app.models.user import Role, User
from app.models.organization import Organization


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        superadmin_role = Role(name='SUPERADMIN', display_name='Platform Super Admin')
        landlord_role = Role(name='LANDLORD', display_name='Landlord')
        db.session.add_all([superadmin_role, landlord_role])
        db.session.commit()

        # Organization 1: Combined suite (both active)
        org1 = Organization(
            name='Kilimani Apartments Group',
            slug='kilimani-apts',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
            enable_rentals=True,
            enable_hospitality=True,
            sms_credits=50
        )
        db.session.add(org1)
        db.session.flush()

        # Superadmin user
        superadmin = User(
            username='platform_superadmin',
            email='superadmin@angaza.co.ke',
            full_name='Platform Super Admin',
            role=superadmin_role,
            is_active=True
        )
        superadmin.set_password('SuperSecret2026!')

        # Regular landlord user tied to org1
        landlord_user = User(
            username='kilimani_landlord',
            email='landlord@kilimani.co.ke',
            full_name='Kilimani Landlord',
            role=landlord_role,
            organization_id=org1.id,
            is_active=True
        )
        landlord_user.set_password('LandlordPass2026!')

        db.session.add_all([superadmin, landlord_user])
        db.session.commit()

        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_superadmin_module_checkpoint_toggle(app, client):
    """Test 1-click toggling of Rentals and Airbnb modules for an organization."""
    # Login as superadmin
    client.post('/auth/login', data={
        'username': 'platform_superadmin',
        'password': 'SuperSecret2026!'
    }, follow_redirects=True)

    with app.app_context():
        org = Organization.query.filter_by(slug='kilimani-apts').first()
        org_id = org.id
        assert org.enable_rentals is True
        assert org.enable_hospitality is True
        assert org.subscription_tier == 'COMBINED_SUITE'

    # 1. Toggle hospitality OFF
    res = client.post(f'/platform/organizations/{org_id}/toggle-module', data={
        'module': 'hospitality'
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        db.session.expire_all()
        org = db.session.get(Organization, org_id)
        assert org.enable_hospitality is False
        assert org.enable_rentals is True
        assert org.subscription_tier == 'RENTAL_STANDARD'
        assert org.can_access_rental_module() is True
        assert org.can_access_hospitality_module() is False

    # 2. Toggle rentals OFF -> activates hospitality so premises remains functional
    res = client.post(f'/platform/organizations/{org_id}/toggle-module', data={
        'module': 'rentals'
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        db.session.expire_all()
        org = db.session.get(Organization, org_id)
        assert org.enable_rentals is False
        assert org.enable_hospitality is True
        assert org.subscription_tier == 'HOSPITALITY_STANDARD'
        assert org.can_access_rental_module() is False
        assert org.can_access_hospitality_module() is True

    # 3. Toggle rentals back ON -> both active -> COMBINED_SUITE
    res = client.post(f'/platform/organizations/{org_id}/toggle-module', data={
        'module': 'rentals'
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        db.session.expire_all()
        org = db.session.get(Organization, org_id)
        assert org.enable_rentals is True
        assert org.enable_hospitality is True
        assert org.subscription_tier == 'COMBINED_SUITE'
        assert org.can_access_rental_module() is True
        assert org.can_access_hospitality_module() is True


def test_subscription_modal_explicit_checkpoints(app, client):
    """Test saving explicit module checkpoint switches from the edit modal."""
    client.post('/auth/login', data={
        'username': 'platform_superadmin',
        'password': 'SuperSecret2026!'
    }, follow_redirects=True)

    with app.app_context():
        org = Organization.query.filter_by(slug='kilimani-apts').first()
        org_id = org.id

    # Update subscription to Rentals Only via explicit checkboxes
    res = client.post(f'/platform/organizations/{org_id}/subscription', data={
        'enable_rentals': '1',
        # enable_hospitality omitted = False
        'max_properties': '60',
        'max_units': '300',
        'max_users': '20'
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        org = db.session.get(Organization, org_id)
        assert org.enable_rentals is True
        assert org.enable_hospitality is False
        assert org.subscription_tier == 'RENTAL_STANDARD'
        assert org.max_properties == 60


def test_create_organization_with_checkpoints(app, client):
    """Test creating a new organization with specific module checkpoints."""
    client.post('/auth/login', data={
        'username': 'platform_superadmin',
        'password': 'SuperSecret2026!'
    }, follow_redirects=True)

    res = client.post('/platform/organizations/create', data={
        'name': 'Diani Holiday Cottages',
        'slug': 'diani-cottages',
        'contact_email': 'stay@dianicottages.co.ke',
        'subscription_tier': 'HOSPITALITY_STANDARD',
        'enable_hospitality': '1',
        'max_properties': '10',
        'max_units': '50',
        'max_users': '5'
    }, follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        org = Organization.query.filter_by(slug='diani-cottages').first()
        assert org is not None
        assert org.enable_hospitality is True
        assert org.enable_rentals is False
        assert org.subscription_tier == 'HOSPITALITY_STANDARD'
        assert org.can_access_rental_module() is False
        assert org.can_access_hospitality_module() is True


def test_sidebar_gating_hospitality_only(app, client):
    """Verify sidebar hides rental module operations when premises only uses Airbnb/hospitality."""
    with app.app_context():
        org = Organization.query.filter_by(slug='kilimani-apts').first()
        org.enable_rentals = False
        org.enable_hospitality = True
        org.subscription_tier = 'HOSPITALITY_STANDARD'
        db.session.commit()

    client.post('/auth/login', data={
        'username': 'kilimani_landlord',
        'password': 'LandlordPass2026!'
    }, follow_redirects=True)

    res = client.get('/dashboard')
    assert res.status_code == 200

    # Hospitality section SHOULD be visible
    assert b'Hospitality &amp; Short-Stay' in res.data
    assert b'Daily Rates &amp; Inventory' in res.data
    # Rental section SHOULD NOT be visible
    assert b'Property Operations' not in res.data
    assert b'Visual Occupancy Grid' not in res.data
    assert b'Lease Agreements' not in res.data


def test_sidebar_gating_rentals_only(app, client):
    """Verify sidebar hides hospitality module when premises only uses rentals."""
    with app.app_context():
        org = Organization.query.filter_by(slug='kilimani-apts').first()
        org.enable_rentals = True
        org.enable_hospitality = False
        org.subscription_tier = 'RENTAL_STANDARD'
        db.session.commit()

    client.post('/auth/login', data={
        'username': 'kilimani_landlord',
        'password': 'LandlordPass2026!'
    }, follow_redirects=True)

    res = client.get('/dashboard')
    assert res.status_code == 200

    # Rental section SHOULD be visible
    assert b'Property Operations' in res.data
    assert b'Visual Occupancy Grid' in res.data
    assert b'Lease Agreements' in res.data
    # Hospitality section SHOULD NOT be visible
    assert b'Hospitality &amp; Short-Stay' not in res.data
    assert b'Daily Rates &amp; Inventory' not in res.data


def test_platform_organizations_view_renders_module_checkpoints(app, client):
    """Verify the platform organizations list table displays the 1-click module toggle buttons."""
    client.post('/auth/login', data={
        'username': 'platform_superadmin',
        'password': 'SuperSecret2026!'
    }, follow_redirects=True)

    res = client.get('/platform/organizations')
    assert res.status_code == 200
    assert b'Module Checkpoints' in res.data
    assert b'Rentals' in res.data
    assert b'Airbnb' in res.data
    assert b'toggle-module' in res.data
