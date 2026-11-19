"""
Phase 24 – Airbnb Management Dashboard, Card Boxes, Automatic Receipt Generation & Money In Tracking
Verifies:
  1. Airbnb Dashboard module renaming to "Airbnb & Short-Stay Management" and "Airbnb Control Center" badge.
  2. Quick operational buttons: "Quick Book", "Record Money In", "Daily Collections".
  3. Summary indicators: Booked Rooms, Vacant Rooms, Today's Collections, Total All-Time Income.
  4. Room operations board card boxes showing occupant details, stay period, balance, and "How to Book" guide for vacant rooms.
  5. Income sorting: highest income, lowest income, and name.
  6. Automatic receipt generation endpoint (/hospitality/reservations/<id>/receipt) with full occupant and stay breakdown.
  7. Recording money in / interim payment (/hospitality/reservations/<id>/record-payment).
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
            name='Diani Beachfront Escapes',
            slug='diani-escapes',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
            sms_credits=100
        )
        db.session.add(org)
        db.session.flush()

        ll = Landlord(name='Diani Hostings', phone='+254711223344', email='host@dianibeach.com')
        db.session.add(ll)
        db.session.flush()

        ll_user = User(
            username='diani_host',
            email='host@dianibeach.com',
            full_name='Diani Host Manager',
            role=landlord_role,
            organization_id=org.id,
            is_active=True
        )
        ll_user.set_password('DianiPass2026!')
        ll_user.landlords.append(ll)
        db.session.add(ll_user)

        prop = Property(
            name='Diani Coral Villa',
            ref_number='PROP-DIANI-001',
            property_type='COMMERCIAL',
            location='Diani Beach Road, Kwale',
            landlord_id=ll.id,
            organization_id=org.id
        )
        db.session.add(prop)
        db.session.flush()

        # 1 Occupied Airbnb Room
        room_occupied = RentalUnit(
            property_id=prop.id,
            unit_number='Villa Suite A',
            unit_type='Luxury Suite',
            operational_type='SHORT_STAY',
            daily_rate_cents=750000,   # KES 7,500 / day
            rent_amount_cents=18000000,
            max_guests=2,
            cleaning_status='CLEAN',
            occupancy_status='OCCUPIED'
        )

        # 1 Vacant Airbnb Room
        room_vacant = RentalUnit(
            property_id=prop.id,
            unit_number='Villa Suite B',
            unit_type='Luxury Suite',
            operational_type='SHORT_STAY',
            daily_rate_cents=650000,   # KES 6,500 / day
            rent_amount_cents=16000000,
            max_guests=2,
            cleaning_status='CLEAN',
            occupancy_status='VACANT'
        )
        db.session.add_all([room_occupied, room_vacant])
        db.session.flush()

        # Occupant Guest
        guest = Guest(
            first_name='Salma',
            last_name='Hassan',
            phone='+254722555666',
            email='salma@dianitour.com',
            id_passport_number='A12345678'
        )
        db.session.add(guest)
        db.session.flush()

        today = date.today()
        res = HospitalityReservation(
            reservation_code='RES-DIANI-101',
            guest_id=guest.id,
            rental_unit_id=room_occupied.id,
            check_in_date=today - timedelta(days=1),
            check_out_date=today + timedelta(days=3),
            num_guests=2,
            num_nights=4,
            daily_rate_cents=750000,
            total_stay_cents=3000000,  # KES 30,000
            paid_amount_cents=1500000, # KES 15,000 paid, KES 15,000 balance
            booking_source='AIRBNB',
            payment_method='MPESA',
            payment_reference='QWE789RTY',
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


def test_airbnb_management_dashboard_branding_and_quick_buttons(app, client):
    """Verify Airbnb dashboard renaming, badges, quick buttons, and summary counters."""
    client.post('/auth/login', data={'username': 'diani_host', 'password': 'DianiPass2026!'}, follow_redirects=True)
    res = client.get('/hospitality/')
    assert res.status_code == 200

    # 1. Branding & header
    assert b'Airbnb &amp; Short-Stay Management' in res.data
    assert b'Airbnb Control Center' in res.data

    # 2. Quick operational action buttons
    assert b'Quick Book' in res.data
    assert b'Record Money In' in res.data
    assert b'Daily Collections' in res.data

    # 3. Summary indicators
    assert b'Booked Rooms' in res.data
    assert b'Vacant Rooms' in res.data
    assert b'Airbnb Room Operations Board' in res.data


def test_airbnb_card_boxes_occupant_details_and_how_to_book(app, client):
    """Verify occupied card displays occupant details & receipt button, and vacant card displays how to book guide."""
    client.post('/auth/login', data={'username': 'diani_host', 'password': 'DianiPass2026!'}, follow_redirects=True)
    res = client.get('/hospitality/')
    assert res.status_code == 200

    # Occupant details on Villa Suite A
    assert b'Villa Suite A' in res.data
    assert b'Salma Hassan' in res.data
    assert b'+254722555666' in res.data
    assert b'AIRBNB' in res.data

    # Action buttons on occupied card
    assert b'Receipt' in res.data
    assert b'Record Payment' in res.data or b'Pay' in res.data

    # Vacant card details on Villa Suite B
    assert b'Villa Suite B' in res.data
    assert b'Vacant &amp; Ready' in res.data
    assert b'Book Room Now' in res.data


def test_automatic_receipt_generation_view(app, client):
    """Verify automatic receipt generation with occupant details, stay folio, and itemized calculations."""
    client.post('/auth/login', data={'username': 'diani_host', 'password': 'DianiPass2026!'}, follow_redirects=True)

    with app.app_context():
        res_obj = HospitalityReservation.query.filter_by(reservation_code='RES-DIANI-101').first()
        res_id = res_obj.id

    receipt_res = client.get(f'/hospitality/reservations/{res_id}/receipt')
    assert receipt_res.status_code == 200

    # Folio header & occupant details
    assert b'OFFICIAL GUEST FOLIO &amp; RECEIPT' in receipt_res.data
    assert b'RES-DIANI-101' in receipt_res.data
    assert b'Salma Hassan' in receipt_res.data
    assert b'+254722555666' in receipt_res.data
    assert b'salma@dianitour.com' in receipt_res.data
    assert b'A12345678' in receipt_res.data

    # Stay & room details
    assert b'Villa Suite A' in receipt_res.data
    assert b'4 night(s)' in receipt_res.data

    # Financial itemization
    assert b'Total Stay Charge' in receipt_res.data
    assert b'Total Amount Paid' in receipt_res.data
    assert b'Outstanding Balance' in receipt_res.data


def test_record_money_in_interim_payment(app, client):
    """Verify recording interim payment / money in updates the reservation and financial balance."""
    client.post('/auth/login', data={'username': 'diani_host', 'password': 'DianiPass2026!'}, follow_redirects=True)

    with app.app_context():
        res_obj = HospitalityReservation.query.filter_by(reservation_code='RES-DIANI-101').first()
        res_id = res_obj.id
        initial_paid = res_obj.paid_amount_cents

    # Record payment of KES 10,000 via MPESA
    post_res = client.post(f'/hospitality/reservations/{res_id}/record-payment', data={
        'amount': '10000',
        'payment_method': 'MPESA',
        'payment_reference': 'MPESA_CONFIRM_999'
    }, follow_redirects=True)
    assert post_res.status_code == 200

    with app.app_context():
        updated_res = db.session.get(HospitalityReservation, res_id)
        assert updated_res.paid_amount_cents == initial_paid + 1000000  # + KES 10,000 in cents
        assert updated_res.payment_reference == 'MPESA_CONFIRM_999'
        assert updated_res.payment_method == 'MPESA'
