"""
Phase 15 – Module B: Hospitality and Short-Stay Management Tests
Tests:
  1. Room operational classification and nightly pricing
  2. Guest and reservation creation with rate calculation
  3. Conflict & double-booking prevention on short-stay rooms
  4. Guest arrival check-in and departure check-out workflow
  5. Housekeeping turnover automation and room sanitization completion
  6. Hospitality KPIs (Occupancy %, ADR, RevPAR)
"""
import pytest
from datetime import date, timedelta
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.property import Property, RentalUnit
from app.models.hospitality import Guest, HospitalityReservation, HousekeepingTask
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
            Permission(code='maintenance.view', module='maintenance', description='View maintenance'),
            Permission(code='maintenance.manage', module='maintenance', description='Manage maintenance'),
            Permission(code='properties.view', module='properties', description='View properties'),
            Permission(code='properties.manage', module='properties', description='Manage properties'),
        ]
        db.session.add(admin_role)
        db.session.add_all(perms)
        db.session.commit()

        admin = User(
            username='hosp_admin',
            email='hosp_admin@test.com',
            full_name='Hospitality Manager',
            role=admin_role,
            is_active=True
        )
        admin.set_password('AdminHosp2026!')
        db.session.add(admin)

        ll = Landlord(name='Airbnb Host Ltd', phone='+254711000111', email='host@airbnb.com')
        db.session.add(ll)
        db.session.commit()

        prop = Property(
            landlord_id=ll.id,
            name='Safari Serviced Suites',
            ref_number='PROP-SAFARI-01',
            property_type='APARTMENT',
            location='Kilimani, Nairobi'
        )
        db.session.add(prop)
        db.session.commit()

        # Create 2 short-stay units and 1 long-term unit
        u1 = RentalUnit(
            property_id=prop.id,
            unit_number='SUITE-101',
            unit_type='1 Bedroom Serviced',
            rent_amount_cents=9000000,
            operational_type='SHORT_STAY',
            daily_rate_cents=450000,  # KES 4,500/night
            max_guests=2,
            cleaning_status='CLEAN',
            occupancy_status='VACANT'
        )
        u2 = RentalUnit(
            property_id=prop.id,
            unit_number='SUITE-102',
            unit_type='Studio Apartment',
            rent_amount_cents=7500000,
            operational_type='SHORT_STAY',
            daily_rate_cents=350000,  # KES 3,500/night
            max_guests=2,
            cleaning_status='CLEAN',
            occupancy_status='VACANT'
        )
        u3 = RentalUnit(
            property_id=prop.id,
            unit_number='APT-201',
            unit_type='2 Bedroom Residential',
            rent_amount_cents=4500000,
            operational_type='LONG_TERM',
            cleaning_status='CLEAN',
            occupancy_status='VACANT'
        )
        db.session.add_all([u1, u2, u3])
        db.session.commit()

        yield application

        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_room_classification_and_pricing(app):
    with app.app_context():
        u1 = RentalUnit.query.filter_by(unit_number='SUITE-101').first()
        assert u1.operational_type == 'SHORT_STAY'
        assert u1.daily_rate_cents == 450000
        assert u1.max_guests == 2
        assert u1.cleaning_status == 'CLEAN'

        u3 = RentalUnit.query.filter_by(unit_number='APT-201').first()
        assert u3.operational_type == 'LONG_TERM'

def test_guest_and_reservation_creation(app):
    with app.app_context():
        u1 = RentalUnit.query.filter_by(unit_number='SUITE-101').first()
        today = date.today()
        check_out = today + timedelta(days=3)

        guest_data = {
            'first_name': 'Wanjiku',
            'last_name': 'Mwangi',
            'phone': '0722123456',
            'email': 'wanjiku@gmail.com',
            'id_passport_number': 'A1234567',
            'nationality': 'Kenyan'
        }

        res = HospitalityService.create_reservation(
            unit_id=u1.id,
            guest_data=guest_data,
            check_in_date=today,
            check_out_date=check_out,
            num_guests=2,
            booking_source='AIRBNB',
            special_requests='Late arrival, please leave key in lockbox'
        )

        assert res.id is not None
        assert res.reservation_code.startswith('STAY-')
        assert res.num_nights == 3
        assert res.total_stay_cents == 450000 * 3  # KES 13,500
        assert res.status == 'CONFIRMED'
        assert res.guest.full_name == 'Wanjiku Mwangi'
        assert res.guest.phone == '0722123456'

def test_reservation_double_booking_prevention(app):
    with app.app_context():
        u1 = RentalUnit.query.filter_by(unit_number='SUITE-101').first()
        today = date.today()

        guest1 = {'first_name': 'Alice', 'last_name': 'Smith', 'phone': '0711111111'}
        res1 = HospitalityService.create_reservation(
            unit_id=u1.id,
            guest_data=guest1,
            check_in_date=today + timedelta(days=5),
            check_out_date=today + timedelta(days=10)
        )
        assert res1.status == 'CONFIRMED'

        # Attempt overlapping booking on same unit
        guest2 = {'first_name': 'Bob', 'last_name': 'Jones', 'phone': '0722222222'}
        with pytest.raises(ValueError, match="not available"):
            HospitalityService.create_reservation(
                unit_id=u1.id,
                guest_data=guest2,
                check_in_date=today + timedelta(days=7),
                check_out_date=today + timedelta(days=12)
            )

        # Booking on a different unit should succeed
        u2 = RentalUnit.query.filter_by(unit_number='SUITE-102').first()
        res2 = HospitalityService.create_reservation(
            unit_id=u2.id,
            guest_data=guest2,
            check_in_date=today + timedelta(days=7),
            check_out_date=today + timedelta(days=12)
        )
        assert res2.id is not None

def test_check_in_and_check_out_workflow(app):
    with app.app_context():
        u1 = RentalUnit.query.filter_by(unit_number='SUITE-101').first()
        today = date.today()

        guest = {'first_name': 'Daniel', 'last_name': 'Kipchoge', 'phone': '0733333333'}
        res = HospitalityService.create_reservation(
            unit_id=u1.id,
            guest_data=guest,
            check_in_date=today,
            check_out_date=today + timedelta(days=2)
        )

        # 1. Check-In
        res = HospitalityService.check_in_reservation(res.id)
        assert res.status == 'CHECKED_IN'
        assert res.actual_check_in_time is not None
        assert u1.occupancy_status == 'OCCUPIED'

        # 2. Check-Out
        res = HospitalityService.check_out_reservation(
            reservation_id=res.id,
            paid_amount=9000.0,
            payment_method='MPESA',
            payment_ref='QA99XX11'
        )
        assert res.status == 'CHECKED_OUT'
        assert res.actual_check_out_time is not None
        assert u1.occupancy_status == 'VACANT'
        assert u1.cleaning_status == 'DIRTY'

        # 3. Verify automated turnover housekeeping task was generated
        task = HousekeepingTask.query.filter_by(rental_unit_id=u1.id, status='PENDING').first()
        assert task is not None
        assert task.task_type == 'TURNOVER_CLEAN'
        assert task.priority == 'HIGH'

def test_housekeeping_status_and_completion(app):
    with app.app_context():
        u1 = RentalUnit.query.filter_by(unit_number='SUITE-101').first()
        u1.cleaning_status = 'DIRTY'
        db.session.commit()

        task = HousekeepingTask(
            rental_unit_id=u1.id,
            task_type='TURNOVER_CLEAN',
            priority='HIGH',
            status='PENDING',
            notes='Clean sheets and replace toiletries'
        )
        db.session.add(task)
        db.session.commit()

        # Complete task
        task.status = 'COMPLETED'
        u1.cleaning_status = 'CLEAN'
        db.session.commit()

        refreshed_u1 = db.session.get(RentalUnit, u1.id)
        assert refreshed_u1.cleaning_status == 'CLEAN'

def test_hospitality_dashboard_kpis(app):
    with app.app_context():
        kpis = HospitalityService.get_hospitality_dashboard_kpis()
        assert 'arrivals_today' in kpis
        assert 'departures_today' in kpis
        assert 'occupancy_pct' in kpis
        assert 'adr_display' in kpis
        assert 'revpar_display' in kpis
        assert 'cleaning_counts' in kpis
        assert isinstance(kpis['cleaning_counts'], dict)
