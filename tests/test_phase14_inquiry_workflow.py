"""
Phase 14 – Web Inquiry → Booking Review → Move-In Workflow
Tests the full lifecycle:
  1. Prospective tenant submits inquiry from public vacancies page
  2. Booking is created with status=PENDING
  3. Admin reviews and approves (reserves) via /bookings/<id>/approve
  4. Admin converts to tenancy via /bookings/<id>/convert
  5. Tenant record created, unit becomes OCCUPIED, active lease generated
"""
import pytest
from datetime import date, timedelta
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.property import Property, RentalUnit
from app.models.booking import Booking
from app.models.tenant import Tenant
from app.models.lease import Lease
from app.services.property_service import PropertyService


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        # Seed roles & permissions
        admin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        perms = [
            Permission(code='bookings.view',   module='bookings',  description='View bookings'),
            Permission(code='bookings.manage', module='bookings',  description='Manage bookings'),
            Permission(code='tenants.view',    module='tenants',   description='View tenants'),
            Permission(code='tenants.manage',  module='tenants',   description='Manage tenants'),
            Permission(code='properties.view', module='properties', description='View properties'),
        ]
        db.session.add(admin_role)
        db.session.add_all(perms)
        db.session.commit()

        admin = User(
            username='admin14',
            email='admin14@test.com',
            full_name='Phase14 Admin',
            role=admin_role,
            is_active=True
        )
        admin.set_password('Admin14Pass!')
        db.session.add(admin)

        landlord = Landlord(name='Test Landlord Phase14', phone='+254700999000')
        db.session.add(landlord)
        db.session.commit()

        prop = PropertyService.create_property(landlord.id, 'Garden Heights', 'GH-01', 'APARTMENT', 'Kilimani')
        PropertyService.create_unit(prop.id, 'GH-101', '1_BEDROOM', 25000, 25000)

        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login_admin(client):
    client.post('/auth/login', data={'username': 'admin14', 'password': 'Admin14Pass!'}, follow_redirects=True)


def get_unit_id(app):
    with app.app_context():
        unit = RentalUnit.query.filter_by(unit_number='GH-101').first()
        return unit.id if unit else None


def submit_inquiry(client, unit_id, name, phone, email='', id_num='', move_in=None, notes=''):
    """Helper: submit public inquiry using actual form field names."""
    if move_in is None:
        move_in = (date.today() + timedelta(days=14)).strftime('%Y-%m-%d')
    return client.post('/vacancies/inquire', data={
        'unit_id': unit_id,
        'full_name': name,
        'phone': phone,
        'email': email,
        'id_number': id_num,
        'expected_move_in': move_in,
        'notes': notes,
    }, follow_redirects=True)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: Public inquiry creates PENDING booking
# ─────────────────────────────────────────────────────────────────────────────
def test_public_inquiry_creates_pending_booking(client, app):
    unit_id = get_unit_id(app)
    assert unit_id is not None

    resp = submit_inquiry(client, unit_id,
                          name='Grace Wambui',
                          phone='+254712345678',
                          email='grace@gmail.com',
                          id_num='29384756',
                          notes='I prefer a quiet unit on upper floor please.')
    assert resp.status_code == 200

    with app.app_context():
        booking = Booking.query.filter_by(prospective_phone='+254712345678').first()
        assert booking is not None, "Expected a PENDING booking to be created from public inquiry"
        assert booking.status == 'PENDING'
        assert booking.prospective_name == 'Grace Wambui'
        assert booking.prospective_id_number == '29384756'
        assert 'INQ-' in booking.booking_reference


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: Admin approves PENDING inquiry → status becomes ACTIVE (reserved)
# ─────────────────────────────────────────────────────────────────────────────
def test_admin_approves_pending_inquiry(client, app):
    unit_id = get_unit_id(app)

    submit_inquiry(client, unit_id,
                   name='James Otieno',
                   phone='+254723456789')

    with app.app_context():
        booking = Booking.query.filter_by(prospective_phone='+254723456789').first()
        assert booking is not None, "Expected booking to be created for James Otieno"
        assert booking.status == 'PENDING'
        booking_id = booking.id

    login_admin(client)
    resp = client.post(f'/bookings/{booking_id}/approve', data={
        'holding_deposit': '5000',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        assert booking.status == 'ACTIVE'
        unit = db.session.get(RentalUnit, unit_id)
        assert unit.occupancy_status == 'RESERVED'


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: Admin converts PENDING inquiry directly to tenancy (allocate & move in)
# ─────────────────────────────────────────────────────────────────────────────
def test_admin_converts_pending_to_tenancy(client, app):
    # Create a second unit for this test
    with app.app_context():
        prop = Property.query.filter_by(name='Garden Heights').first()
        PropertyService.create_unit(prop.id, 'GH-102', '2_BEDROOM', 35000, 35000)
        unit2 = RentalUnit.query.filter_by(unit_number='GH-102').first()
        unit2_id = unit2.id

    submit_inquiry(client, unit2_id,
                   name='Faith Njeri',
                   phone='+254798765432',
                   email='faith@gmail.com',
                   id_num='33445566',
                   notes='Looking to move in urgently.')

    with app.app_context():
        booking = Booking.query.filter_by(prospective_phone='+254798765432').first()
        assert booking is not None, "Expected booking to be created for Faith Njeri"
        assert booking.status == 'PENDING'
        booking_id = booking.id

    login_admin(client)
    resp = client.post(f'/bookings/{booking_id}/convert', follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        assert booking.status == 'CONFIRMED_MOVE_IN'

        tenant = Tenant.query.filter_by(phone='+254798765432').first()
        assert tenant is not None
        assert tenant.first_name == 'Faith'

        lease = Lease.query.filter_by(tenant_id=tenant.id, status='ACTIVE').first()
        assert lease is not None

        unit = db.session.get(RentalUnit, unit2_id)
        assert unit.occupancy_status == 'OCCUPIED'
        assert unit.current_tenant_id == tenant.id


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: Admin declines (cancels) a PENDING inquiry → unit stays VACANT
# ─────────────────────────────────────────────────────────────────────────────
def test_admin_declines_pending_inquiry(client, app):
    with app.app_context():
        prop = Property.query.filter_by(name='Garden Heights').first()
        PropertyService.create_unit(prop.id, 'GH-103', 'BEDSITTER', 15000, 15000)
        unit3 = RentalUnit.query.filter_by(unit_number='GH-103').first()
        unit3_id = unit3.id

    submit_inquiry(client, unit3_id,
                   name='Peter Mwangi',
                   phone='+254711223344')

    with app.app_context():
        booking = Booking.query.filter_by(prospective_phone='+254711223344').first()
        assert booking is not None, "Expected booking to be created for Peter Mwangi"
        booking_id = booking.id
        assert booking.status == 'PENDING'

    login_admin(client)
    resp = client.post(f'/bookings/{booking_id}/cancel', data={
        'cancel_reason': 'Client did not proceed with viewing',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        assert booking.status == 'CANCELLED'
        unit = db.session.get(RentalUnit, unit3_id)
        assert unit.occupancy_status == 'VACANT'
