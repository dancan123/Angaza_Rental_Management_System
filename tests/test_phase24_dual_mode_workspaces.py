"""
Phase 24 Dual-Mode Workspaces Test
Verifies:
  1. 1-click mode switcher (/switch-mode/airbnb and /switch-mode/rentals).
  2. Session persistence of active workspace mode.
  3. Clean sidebar isolation: in Airbnb mode, rentals-only menus are hidden.
  4. Clean sidebar isolation: in Rentals mode, airbnb-only menus are hidden.
  5. Convenience alias routes /airbnb and /rentals.
"""
import pytest
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.organization import Organization


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        superadmin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        landlord_role = Role(name='LANDLORD', display_name='Landlord')
        perms = [
            Permission(code='properties.view', module='properties', description='View properties'),
            Permission(code='properties.manage', module='properties', description='Manage properties'),
            Permission(code='bookings.view', module='bookings', description='View bookings'),
            Permission(code='bookings.manage', module='bookings', description='Manage bookings'),
            Permission(code='maintenance.view', module='maintenance', description='View maintenance'),
            Permission(code='maintenance.manage', module='maintenance', description='Manage maintenance'),
        ]
        db.session.add_all([superadmin_role, landlord_role])
        db.session.add_all(perms)
        db.session.commit()

        landlord_role.permissions = perms
        db.session.commit()

        # Organization with BOTH modules enabled
        org = Organization(
            name='Dual Suite Hostings',
            slug='dual-suite',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
            enable_rentals=True,
            enable_hospitality=True,
            sms_credits=50
        )
        db.session.add(org)
        db.session.flush()

        ll = Landlord(name='Dual Host', phone='+254700112233')
        db.session.add(ll)
        db.session.flush()

        user = User(
            username='dual_user',
            email='dual@host.com',
            full_name='Dual Suite Manager',
            role=landlord_role,
            organization_id=org.id,
            is_active=True
        )
        user.set_password('DualPass2026!')
        user.landlords.append(ll)
        db.session.add(user)
        db.session.commit()

        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_dual_mode_switcher_toggle_and_redirects(app, client):
    """Verify switching to airbnb mode and rentals mode updates session and redirects appropriately."""
    client.post('/auth/login', data={'username': 'dual_user', 'password': 'DualPass2026!'}, follow_redirects=True)

    # 1. Switch to Airbnb mode
    res_airbnb = client.get('/switch-mode/airbnb', follow_redirects=False)
    assert res_airbnb.status_code == 302
    assert '/hospitality' in res_airbnb.headers['Location']

    # 2. Switch to Rentals mode
    res_rentals = client.get('/switch-mode/rentals', follow_redirects=False)
    assert res_rentals.status_code == 302
    assert '/dashboard' in res_rentals.headers['Location']

    # 3. Direct convenience aliases
    res_alias_airbnb = client.get('/airbnb', follow_redirects=False)
    assert res_alias_airbnb.status_code == 302
    assert '/hospitality' in res_alias_airbnb.headers['Location']

    res_alias_rentals = client.get('/rentals', follow_redirects=False)
    assert res_alias_rentals.status_code == 302
    assert '/dashboard' in res_alias_rentals.headers['Location']


def test_sidebar_isolation_between_airbnb_and_rentals_modes(app, client):
    """Verify clean sidebar isolation: Airbnb mode hides long-term rental clutter, and Rentals mode hides Airbnb clutter."""
    client.post('/auth/login', data={'username': 'dual_user', 'password': 'DualPass2026!'}, follow_redirects=True)

    # In Airbnb mode:
    client.get('/switch-mode/airbnb', follow_redirects=True)
    res_airbnb = client.get('/hospitality/')
    assert res_airbnb.status_code == 200

    # Airbnb items ARE visible
    assert b'Hospitality &amp; Short-Stay' in res_airbnb.data
    assert b'Daily Rates &amp; Inventory' in res_airbnb.data
    assert b'Availability Calendar' in res_airbnb.data

    # Rentals items ARE HIDDEN
    assert b'Visual Occupancy Grid' not in res_airbnb.data
    assert b'Lease Agreements' not in res_airbnb.data
    assert b'Water &amp; Meter Utilities' not in res_airbnb.data

    # Switch to Rentals mode:
    client.get('/switch-mode/rentals', follow_redirects=True)
    res_rentals = client.get('/dashboard')
    assert res_rentals.status_code == 200

    # Rentals items ARE visible
    assert b'Visual Occupancy Grid' in res_rentals.data
    assert b'Lease Agreements' in res_rentals.data
    assert b'Water &amp; Meter Utilities' in res_rentals.data

    # Airbnb items ARE HIDDEN
    assert b'Availability Calendar' not in res_rentals.data
    assert b'Daily Rates &amp; Inventory' not in res_rentals.data
    assert b'Housekeeping &amp; Rooms' not in res_rentals.data
