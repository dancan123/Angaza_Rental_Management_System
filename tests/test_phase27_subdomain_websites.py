"""
Phase 27 Multi-Tenant Subdomain & External Lead-Gen Websites Test
Verifies:
  1. Accessing public tenant website via /site/<slug> loads only the organization's properties.
  2. Data isolation between distinct business sites (e.g. ANGAZA vs SARAH).
  3. Automatic subdomain-per-tenant routing on root path '/'.
  4. Prospective tenant rental lead submission (/site/<slug>/inquire).
  5. Airbnb / Short-stay reservation request submission (/site/<slug>/airbnb-inquire).
  6. Anti-tampering check: inquiries on units belonging to another organization are rejected.
"""
import pytest
from datetime import date, datetime
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.organization import Organization
from app.models.property import Property, RentalUnit
from app.models.booking import Booking
from app.models.hospitality import Guest, HospitalityReservation
from app.models.communication import Notification


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        superadmin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        manager_role = Role(name='PROPERTY_MANAGER', display_name='Property Manager')
        db.session.add_all([superadmin_role, manager_role])
        db.session.commit()

        # 1. Organization A: Angaza Premier
        org_a = Organization(
            name='Angaza Premier Properties',
            slug='angaza-premier',
            org_code='ANGAZA',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
            enable_rentals=True,
            enable_hospitality=True,
            contact_phone='+254711111111'
        )
        # 2. Organization B: Mama Sarah Estates
        org_b = Organization(
            name='Mama Sarah Estates',
            slug='sarah-estates',
            org_code='SARAH',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
            enable_rentals=True,
            enable_hospitality=True,
            contact_phone='+254722222222'
        )
        db.session.add_all([org_a, org_b])
        db.session.flush()

        # Landlords
        landlord_a = Landlord(name='Kamau Landlord', email='kamau@example.com', phone='+254711111111')
        landlord_b = Landlord(name='Sarah Landlord', email='sarah@example.com', phone='+254722222222')
        db.session.add_all([landlord_a, landlord_b])
        db.session.flush()

        # Properties
        prop_a = Property(
            name='Angaza Heights',
            ref_number='PROP-ANG-01',
            organization_id=org_a.id,
            landlord_id=landlord_a.id,
            location='Westlands, Nairobi',
            property_type='APARTMENT'
        )
        prop_b = Property(
            name='Sarah Garden Villas',
            ref_number='PROP-SAR-01',
            organization_id=org_b.id,
            landlord_id=landlord_b.id,
            location='Kilimani, Nairobi',
            property_type='APARTMENT'
        )
        db.session.add_all([prop_a, prop_b])
        db.session.flush()

        # Units in Org A: 1 Vacant Long-term Rental, 1 Airbnb Suite
        unit_a_rental = RentalUnit(
            property_id=prop_a.id,
            unit_number='A-101',
            unit_type='TWO_BEDROOM',
            rent_amount_cents=4500000,
            deposit_amount_cents=4500000,
            occupancy_status='VACANT',
            operational_type='LONG_TERM'
        )
        unit_a_airbnb = RentalUnit(
            property_id=prop_a.id,
            unit_number='A-STAY-1',
            unit_type='STUDIO',
            daily_rate_cents=600000,
            max_guests=2,
            occupancy_status='VACANT',
            operational_type='SHORT_STAY'
        )

        # Units in Org B: 1 Vacant Long-term Rental
        unit_b_rental = RentalUnit(
            property_id=prop_b.id,
            unit_number='B-202',
            unit_type='ONE_BEDROOM',
            rent_amount_cents=3000000,
            deposit_amount_cents=3000000,
            occupancy_status='VACANT',
            operational_type='LONG_TERM'
        )

        db.session.add_all([unit_a_rental, unit_a_airbnb, unit_b_rental])
        db.session.commit()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_tenant_website_data_isolation(client):
    # 1. Access Org A's public website via slug
    resp_a = client.get('/site/angaza-premier')
    assert resp_a.status_code == 200
    assert b'Angaza Premier Properties' in resp_a.data
    assert b'Angaza Heights' in resp_a.data
    assert b'Unit A-101' in resp_a.data
    assert b'A-STAY-1' in resp_a.data
    # Must NOT contain Org B's property or units!
    assert b'Sarah Garden Villas' not in resp_a.data
    assert b'B-202' not in resp_a.data

    # 2. Access Org B's public website via business code 'SARAH'
    resp_b = client.get('/site/SARAH')
    assert resp_b.status_code == 200
    assert b'Mama Sarah Estates' in resp_b.data
    assert b'Sarah Garden Villas' in resp_b.data
    assert b'B-202' in resp_b.data
    # Must NOT contain Org A's property or units!
    assert b'Angaza Heights' not in resp_b.data
    assert b'Unit A-101' not in resp_b.data


def test_subdomain_resolution_on_root_path(client):
    # Simulate request with Host header containing subdomain
    resp = client.get('/', headers={'Host': 'sarah-estates.angazarentals.co.ke'})
    assert resp.status_code == 200
    assert b'Mama Sarah Estates' in resp.data
    assert b'Sarah Garden Villas' in resp.data


def test_rental_lead_inquiry_submission(client):
    with client.application.app_context():
        unit_a = RentalUnit.query.filter_by(unit_number='A-101').first()
        unit_a_id = unit_a.id

    # Submit prospective tenant application
    resp = client.post(
        '/site/angaza-premier/inquire',
        data={
            'unit_id': unit_a_id,
            'full_name': 'Martin Wachira',
            'phone': '0711998877',
            'email': 'martin@example.com',
            'expected_move_in': date.today().strftime('%Y-%m-%d'),
            'notes': 'Looking to move in starting next month.'
        },
        follow_redirects=True
    )
    assert resp.status_code == 200
    assert b'Thank you, Martin Wachira!' in resp.data

    # Verify Booking record was saved
    with client.application.app_context():
        lead = Booking.query.filter_by(prospective_phone='0711998877').first()
        assert lead is not None
        assert lead.rental_unit_id == unit_a_id
        assert lead.status == 'PENDING'

        # Verify notification was sent
        notif = Notification.query.filter(Notification.message.like('%Martin Wachira%')).first()
        assert notif is not None
        assert 'ANGAZA' in notif.message


def test_airbnb_reservation_inquiry_submission(client):
    with client.application.app_context():
        unit_stay = RentalUnit.query.filter_by(unit_number='A-STAY-1').first()
        unit_stay_id = unit_stay.id

    # Submit short-stay reservation
    resp = client.post(
        '/site/angaza-premier/airbnb-inquire',
        data={
            'unit_id': unit_stay_id,
            'guest_name': 'Grace Wanjiku',
            'phone': '0722334455',
            'check_in_date': '2026-12-01',
            'check_out_date': '2026-12-04',
            'num_guests': 2,
            'special_requests': 'Airport pickup needed'
        },
        follow_redirects=True
    )
    assert resp.status_code == 200
    assert b'Thank you, Grace Wanjiku!' in resp.data

    # Verify HospitalityReservation was saved
    with client.application.app_context():
        guest = Guest.query.filter_by(phone='0722334455').first()
        assert guest is not None
        assert guest.first_name == 'Grace'

        res = HospitalityReservation.query.filter_by(guest_id=guest.id).first()
        assert res is not None
        assert res.num_nights == 3
        assert res.total_stay_cents == 3 * 600000
        assert res.status == 'CONFIRMED'


def test_anti_tampering_cross_org_inquiry_blocked(client):
    # Try to submit an inquiry for Org B's unit using Org A's URL endpoint
    with client.application.app_context():
        unit_b = RentalUnit.query.filter_by(unit_number='B-202').first()
        unit_b_id = unit_b.id

    resp = client.post(
        '/site/angaza-premier/inquire',
        data={
            'unit_id': unit_b_id,
            'full_name': 'Hacker Seeker',
            'phone': '0700000000',
            'notes': 'Attempting cross-tenant submission'
        },
        follow_redirects=True
    )
    assert resp.status_code == 200
    assert b'Requested unit does not belong to this organization' in resp.data
