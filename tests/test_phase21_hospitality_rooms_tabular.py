"""
Phase 21 – Tabular Airbnb Room Management, Custom Renaming & Financial Totals Tests
Tests:
  1. Tabular rooms view with Daily Rate, Monthly Rate, Total Collected, and live status
  2. Landlord custom room renaming and rate reconfiguration
  3. 1-click room cleaning status toggle
  4. Room-level guest SMS communication dispatch
"""
import pytest
from datetime import date, timedelta
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.property import Property, RentalUnit
from app.models.hospitality import Guest, HospitalityReservation
from app.models.organization import Organization
from app.services.hospitality_service import HospitalityService


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        admin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        perms = [
            Permission(code='bookings.view', module='bookings', description='View bookings'),
            Permission(code='bookings.manage', module='bookings', description='Manage bookings'),
            Permission(code='properties.view', module='properties', description='View properties'),
            Permission(code='properties.manage', module='properties', description='Manage properties'),
        ]
        db.session.add(admin_role)
        db.session.add_all(perms)
        db.session.commit()

        org = Organization(
            name='Safari Suites Collection',
            slug='safari-suites',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
            sms_credits=100
        )
        db.session.add(org)
        db.session.flush()

        admin = User(
            username='safari_admin',
            email='admin@safarisuites.co.ke',
            full_name='Safari Admin',
            role=admin_role,
            organization_id=org.id,
            is_active=True
        )
        admin.set_password('SafariPass2026!')
        db.session.add(admin)

        ll = Landlord(name='Safari Host Ltd', phone='+254711999888', email='host@safari.com')
        db.session.add(ll)
        db.session.flush()

        prop = Property(
            name='Diani Beachfront Villas',
            ref_number='PROP-DIANI-001',
            property_type='COMMERCIAL',
            location='Diani Beach Road, Diani',
            landlord_id=ll.id,
            organization_id=org.id
        )
        db.session.add(prop)
        db.session.flush()

        # Create 2 rooms
        room1 = RentalUnit(
            property_id=prop.id,
            unit_number='Villa 1 - Ocean View',
            unit_type='Villa',
            operational_type='SHORT_STAY',
            daily_rate_cents=750000,   # KES 7,500/day
            rent_amount_cents=18000000, # KES 180,000/mo
            max_guests=4,
            cleaning_status='CLEAN',
            occupancy_status='OCCUPIED'
        )
        room2 = RentalUnit(
            property_id=prop.id,
            unit_number='Villa 2 - Garden Suite',
            unit_type='Suite',
            operational_type='SHORT_STAY',
            daily_rate_cents=500000,   # KES 5,000/day
            rent_amount_cents=12000000, # KES 120,000/mo
            max_guests=2,
            cleaning_status='CLEAN',
            occupancy_status='VACANT'
        )
        db.session.add_all([room1, room2])
        db.session.flush()

        # Add guest & reservation for room1
        guest = Guest(first_name='David', last_name='Ochieng', phone='+254712000111', email='david@example.com')
        db.session.add(guest)
        db.session.flush()

        today = date.today()
        res = HospitalityReservation(
            reservation_code='RES-DIANI-001',
            guest_id=guest.id,
            rental_unit_id=room1.id,
            check_in_date=today - timedelta(days=1),
            check_out_date=today + timedelta(days=2),
            num_guests=2,
            num_nights=3,
            daily_rate_cents=750000,
            total_stay_cents=2250000,
            paid_amount_cents=2250000,  # Fully paid KES 22,500
            status='CHECKED_IN'
        )
        db.session.add(res)
        db.session.commit()

        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_tabular_rooms_overview_and_financials(app, client):
    """Verify tabular view displays room names, daily rate, monthly rate, and total collected."""
    client.post('/auth/login', data={
        'username': 'safari_admin',
        'password': 'SafariPass2026!'
    }, follow_redirects=True)

    res = client.get('/hospitality/rooms')
    assert res.status_code == 200

    # 1. Custom Room Names
    assert b'Villa 1 - Ocean View' in res.data
    assert b'Villa 2 - Garden Suite' in res.data

    # 2. Daily Rate & Monthly Potential
    assert b'Rate / Day' in res.data
    assert b'Rate / Month' in res.data
    assert b'Total Collected' in res.data
    assert b'7,500' in res.data
    assert b'5,000' in res.data

    # 3. Total Collected Amount for Villa 1 (KES 22,500)
    assert b'22,500' in res.data

    # 4. Live Status & Timelines
    assert b'Occupied / In-House' in res.data
    assert b'David Ochieng' in res.data
    assert b'Vacant &amp; Ready' in res.data or b'Vacant' in res.data

    # 5. Service Overview check
    with app.app_context():
        overview = HospitalityService.get_rooms_management_overview()
        assert overview['stats']['total_rooms'] == 2
        assert overview['stats']['short_stay_count'] == 2
        assert overview['stats']['occupied_count'] == 1
        assert overview['stats']['vacant_count'] == 1
        assert overview['stats']['total_collected_cents'] == 2250000


def test_landlord_custom_room_renaming(app, client):
    """Verify landlord can rename their rooms to custom identifiers and update rates."""
    client.post('/auth/login', data={
        'username': 'safari_admin',
        'password': 'SafariPass2026!'
    }, follow_redirects=True)

    with app.app_context():
        room = RentalUnit.query.filter_by(unit_number='Villa 2 - Garden Suite').first()
        room_id = room.id

    # Landlord renames room to "Presidential Honeymoon Suite 501"
    res = client.post(f'/hospitality/rooms/{room_id}/update', data={
        'unit_number': 'Presidential Honeymoon Suite 501',
        'unit_type': 'Honeymoon Penthouse',
        'operational_type': 'SHORT_STAY',
        'daily_rate': 12500,        # KES 12,500/night
        'monthly_rent': 320000,     # KES 320,000/mo
        'max_guests': 3,
        'cleaning_status': 'CLEAN',
        'description': 'Private infinity plunge pool, smart home automation.'
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b'Presidential Honeymoon Suite 501' in res.data
    assert b'12,500' in res.data

    with app.app_context():
        updated_room = db.session.get(RentalUnit, room_id)
        assert updated_room.unit_number == 'Presidential Honeymoon Suite 501'
        assert updated_room.daily_rate_cents == 1250000
        assert updated_room.rent_amount_cents == 32000000
        assert updated_room.max_guests == 3
        assert 'infinity plunge pool' in updated_room.description


def test_room_cleaning_status_toggle(app, client):
    """Verify 1-click room cleaning status toggle."""
    client.post('/auth/login', data={
        'username': 'safari_admin',
        'password': 'SafariPass2026!'
    }, follow_redirects=True)

    with app.app_context():
        room = RentalUnit.query.filter_by(unit_number='Villa 2 - Garden Suite').first()
        room_id = room.id
        assert room.cleaning_status == 'CLEAN'

    # Toggle to DIRTY
    res = client.post(f'/hospitality/rooms/{room_id}/toggle-cleaning', follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        room_refreshed = db.session.get(RentalUnit, room_id)
        assert room_refreshed.cleaning_status == 'DIRTY'

    # Toggle back to CLEAN
    res = client.post(f'/hospitality/rooms/{room_id}/toggle-cleaning', follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        room_refreshed = db.session.get(RentalUnit, room_id)
        assert room_refreshed.cleaning_status == 'CLEAN'


def test_room_guest_sms_dispatch(app, client):
    """Verify direct room communication dispatching SMS to guest."""
    client.post('/auth/login', data={
        'username': 'safari_admin',
        'password': 'SafariPass2026!'
    }, follow_redirects=True)

    with app.app_context():
        room = RentalUnit.query.filter_by(unit_number='Villa 1 - Ocean View').first()
        room_id = room.id

    res = client.post(f'/hospitality/rooms/{room_id}/send-sms', data={
        'phone': '+254712000111',
        'message': 'Welcome to Diani! Your keybox pin code is 8842.'
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b'SMS successfully sent' in res.data
