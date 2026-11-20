"""
Phase 23 – Hospitality Dashboard Strict Data Mapping, Distinct Occupied Styling & Functional Calendar Buttons Tests
Verifies:
  1. Hospitality Dashboard KPI cards accurately map only to short-stay / Airbnb units (does not bleed into long-term units).
  2. Airbnb tabular room view formats OCCUPIED rooms in distinct red highlighting and bold badge.
  3. Availability Calendar date cells are functional buttons with quick-booking modals and reservation action modals.
  4. Landlord can add short-stay rooms and update room / house details.
"""
import pytest
from datetime import date, timedelta
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.property import Property, RentalUnit
from app.models.hospitality import Guest, HospitalityReservation
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

        org = Organization(
            name='Watamu Oceanfront Retreat',
            slug='watamu-retreat',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
            sms_credits=50
        )
        db.session.add(org)
        db.session.flush()

        ll = Landlord(name='Watamu Host Ltd', phone='+254711888999', email='host@watamu.co.ke')
        db.session.add(ll)
        db.session.flush()

        # Landlord user
        ll_user = User(
            username='watamu_host',
            email='host@watamu.co.ke',
            full_name='Watamu Host',
            role=landlord_role,
            organization_id=org.id,
            is_active=True
        )
        ll_user.set_password('WatamuPass2026!')
        ll_user.landlords.append(ll)
        db.session.add(ll_user)

        prop = Property(
            name='Watamu Palm Villas',
            ref_number='PROP-WATAMU-001',
            property_type='COMMERCIAL',
            location='Turtle Bay Road, Watamu',
            landlord_id=ll.id,
            organization_id=org.id
        )
        db.session.add(prop)
        db.session.flush()

        # 1 Short-Stay Airbnb Room
        room_airbnb = RentalUnit(
            property_id=prop.id,
            unit_number='Suite 101 - Sunset View',
            unit_type='Suite',
            operational_type='SHORT_STAY',
            daily_rate_cents=600000,   # KES 6,000 / day
            rent_amount_cents=15000000, # KES 150,000 / mo
            max_guests=2,
            cleaning_status='CLEAN',
            occupancy_status='OCCUPIED'
        )

        # 1 Long-Term Apartment (should NOT bleed into short-stay dashboard KPIs)
        room_longterm = RentalUnit(
            property_id=prop.id,
            unit_number='Apt 201 - Residential',
            unit_type='2-Bedroom Apartment',
            operational_type='LONG_TERM',
            rent_amount_cents=4500000, # KES 45,000 / mo
            max_guests=4,
            cleaning_status='CLEAN',
            occupancy_status='OCCUPIED'
        )
        db.session.add_all([room_airbnb, room_longterm])
        db.session.flush()

        # In-House Guest for the Airbnb suite
        guest = Guest(first_name='Faith', last_name='Achieng', phone='+254722111222', email='faith@example.com')
        db.session.add(guest)
        db.session.flush()

        today = date.today()
        res = HospitalityReservation(
            organization_id=org.id,
            reservation_code='RES-WAT-001',
            guest_id=guest.id,
            rental_unit_id=room_airbnb.id,
            check_in_date=today - timedelta(days=1),
            check_out_date=today + timedelta(days=2),
            num_guests=2,
            num_nights=3,
            daily_rate_cents=600000,
            total_stay_cents=1800000,
            paid_amount_cents=1800000,
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


def test_hospitality_dashboard_kpis_accurate_data_mapping(app, client):
    """Verify hospitality dashboard cards only calculate short-stay units and ignore long-term units."""
    client.post('/auth/login', data={
        'username': 'watamu_host',
        'password': 'WatamuPass2026!'
    }, follow_redirects=True)

    res = client.get('/hospitality/')
    assert res.status_code == 200

    # 1. Total short-stay units is exactly 1 (Apt 201 LONG_TERM is excluded)
    assert b'1 of 1 short-stay units' in res.data
    assert b'100.0%' in res.data  # 1 of 1 occupied = 100%

    # 2. In-house guest card maps correctly
    assert b'Faith Achieng' in res.data
    assert b'Suite 101 - Sunset View' in res.data

    # 3. Long-term unit should NOT appear in short-stay in-house guests
    assert b'Apt 201 - Residential' not in res.data


def test_airbnb_occupied_room_distinct_color_and_badge(app, client):
    """Verify Airbnb rooms table styles occupied rooms with distinct table highlight and bold badge."""
    client.post('/auth/login', data={
        'username': 'watamu_host',
        'password': 'WatamuPass2026!'
    }, follow_redirects=True)

    res = client.get('/hospitality/rooms')
    assert res.status_code == 200

    # Distinct highlight row styling
    assert b'table-danger-subtle border-start border-4 border-danger' in res.data

    # Distinct bold red OCCUPIED badge
    assert b'Occupied / In-House' in res.data
    assert b'Faith Achieng' in res.data


def test_availability_calendar_functional_buttons_and_modals(app, client):
    """Verify availability calendar has functional interactive buttons for booking and reservation details."""
    client.post('/auth/login', data={
        'username': 'watamu_host',
        'password': 'WatamuPass2026!'
    }, follow_redirects=True)

    res = client.get('/hospitality/calendar')
    assert res.status_code == 200

    # 1. By default, shows Short-Stay / Airbnb only
    assert b'Airbnb / Short-Stay Only' in res.data
    assert b'Suite 101 - Sunset View' in res.data

    # 2. Available slots have functional quick book button
    assert b'cal-book-btn' in res.data
    assert b'data-bs-target="#quickBookModal"' in res.data
    assert b'id="quickBookModal"' in res.data

    # 3. Occupied slots have functional reservation details button
    assert b'data-bs-target="#resModal' in res.data
    assert b'Complete Check-Out &amp; Turnover' in res.data


def test_landlord_can_add_room_and_update_details(app, client):
    """Verify landlord can create a new short-stay room and update/rename existing room details."""
    client.post('/auth/login', data={
        'username': 'watamu_host',
        'password': 'WatamuPass2026!'
    }, follow_redirects=True)

    with app.app_context():
        prop = Property.query.filter_by(ref_number='PROP-WATAMU-001').first()
        prop_id = prop.id

    # 1. Landlord creates a new room
    res = client.post('/hospitality/rooms/create', data={
        'property_id': str(prop_id),
        'unit_number': 'Cottage 3 - Garden Breeze',
        'unit_type': 'Cottage',
        'daily_rate': '4500',
        'monthly_rent': '120000',
        'max_guests': '3',
        'cleaning_status': 'CLEAN',
        'description': 'Cozy self-catering garden cottage'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Cottage 3 - Garden Breeze' in res.data

    with app.app_context():
        new_room = RentalUnit.query.filter_by(unit_number='Cottage 3 - Garden Breeze').first()
        assert new_room is not None
        assert new_room.operational_type == 'SHORT_STAY'
        assert new_room.daily_rate_cents == 450000
        new_room_id = new_room.id

    # 2. Landlord updates / renames the room and changes rate
    update_res = client.post(f'/hospitality/rooms/{new_room_id}/update', data={
        'unit_number': 'Executive Suite 3 - Ocean Breeze',
        'unit_type': 'Executive Suite',
        'operational_type': 'SHORT_STAY',
        'daily_rate': '5500',
        'monthly_rent': '140000',
        'max_guests': '4',
        'cleaning_status': 'CLEAN',
        'description': 'Upgraded executive oceanfront cottage'
    }, follow_redirects=True)
    assert update_res.status_code == 200
    assert b'Executive Suite 3 - Ocean Breeze' in update_res.data

    with app.app_context():
        updated_room = db.session.get(RentalUnit, new_room_id)
        assert updated_room.unit_number == 'Executive Suite 3 - Ocean Breeze'
        assert updated_room.daily_rate_cents == 550000
        assert updated_room.max_guests == 4
