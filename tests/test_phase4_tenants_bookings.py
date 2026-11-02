import pytest
from datetime import date, timedelta
from app import create_app
from app.extensions import db
from app.models.user import Role, User, Landlord
from app.models.property import Property, RentalUnit
from app.models.tenant import Tenant
from app.models.booking import Booking
from app.models.lease import Lease, TenancyRecord
from app.services.tenant_service import TenantService
from app.services.booking_service import BookingService
from app.services.property_service import PropertyService

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        admin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        db.session.add(admin_role)
        db.session.commit()

        admin = User(
            username='admin_bkg',
            email='admin_bkg@test.com',
            full_name='Booking Admin',
            role=admin_role,
            is_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)

        landlord = Landlord(name='Crown Real Estate', phone='+254711333444')
        db.session.add(landlord)
        db.session.commit()

        prop = PropertyService.create_property(landlord.id, 'Crown Suites', 'CRW-01', 'APARTMENT', 'Westlands')
        PropertyService.create_unit(prop.id, 'C-101', '1_BEDROOM', 30000, 30000)
        PropertyService.create_unit(prop.id, 'C-102', '2_BEDROOM', 45000, 45000)

        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_tenant_creation_and_duplicate_guard(app):
    with app.app_context():
        t1 = TenantService.create_tenant('Alice', 'Wanjiru', 'ID-123456', '+254700000001', 'alice@test.com')
        assert t1.id is not None
        assert t1.full_name == 'Alice Wanjiru'

        # Duplicate ID must raise ValueError
        with pytest.raises(ValueError) as excinfo:
            TenantService.create_tenant('Another', 'Person', 'ID-123456', '+254700000002')
        assert "already registered" in str(excinfo.value)

def test_booking_workflow_and_double_booking_prevention(app):
    with app.app_context():
        unit1 = RentalUnit.query.filter_by(unit_number='C-101').first()
        assert unit1.occupancy_status == 'VACANT'

        # 1. Create reservation
        move_in = date.today() + timedelta(days=5)
        bkg = BookingService.create_booking(
            rental_unit_id=unit1.id,
            prospective_name='David Otieno',
            prospective_phone='+254711999111',
            expected_move_in_date=move_in,
            booking_deposit=5000
        )
        assert bkg.status == 'ACTIVE'
        # Unit must automatically change to RESERVED
        u1_refreshed = RentalUnit.query.get(unit1.id)
        assert u1_refreshed.occupancy_status == 'RESERVED'

        # 2. Double-booking prevention: attempting to book C-101 again must raise ValueError
        with pytest.raises(ValueError) as excinfo:
            BookingService.create_booking(
                rental_unit_id=unit1.id,
                prospective_name='Second Person',
                prospective_phone='+254799888777',
                expected_move_in_date=move_in
            )
        assert "already has an active reservation" in str(excinfo.value)

        # 3. Convert reservation to active tenancy (Move-in)
        tenant, lease = BookingService.convert_to_tenancy(bkg.id)
        assert tenant.full_name == 'David Otieno'
        assert lease.status == 'ACTIVE'
        assert bkg.status == 'CONFIRMED_MOVE_IN'
        assert u1_refreshed.occupancy_status == 'OCCUPIED'
        assert u1_refreshed.current_tenant_id == tenant.id

def test_booking_cancellation(app):
    with app.app_context():
        unit2 = RentalUnit.query.filter_by(unit_number='C-102').first()
        bkg = BookingService.create_booking(
            rental_unit_id=unit2.id,
            prospective_name='Mercy Achieng',
            prospective_phone='+254733444555',
            expected_move_in_date=date.today() + timedelta(days=3)
        )
        assert unit2.occupancy_status == 'RESERVED'

        # Cancel reservation
        BookingService.cancel_booking(bkg.id, reason='Client cancelled')
        assert bkg.status == 'CANCELLED'
        # Unit must be released back to VACANT
        assert unit2.occupancy_status == 'VACANT'

def test_tenant_transfer_and_move_out(app):
    with app.app_context():
        unit1 = RentalUnit.query.filter_by(unit_number='C-101').first()
        unit2 = RentalUnit.query.filter_by(unit_number='C-102').first()

        # Place tenant in unit1
        tenant = TenantService.create_tenant('Bob', 'Mwangi', 'ID-778899', '+254722112233')
        unit1.occupancy_status = 'OCCUPIED'
        unit1.current_tenant_id = tenant.id
        lease1 = Lease(
            lease_number='LSE-TEST-001',
            rental_unit_id=unit1.id,
            tenant_id=tenant.id,
            start_date=date.today(),
            monthly_rent_cents=unit1.rent_amount_cents,
            deposit_cents=unit1.deposit_amount_cents,
            status='ACTIVE'
        )
        db.session.add(lease1)
        db.session.commit()

        # 1. Transfer Bob from unit1 to unit2
        new_lease = TenantService.transfer_unit(tenant.id, unit2.id, transfer_reason='Room upgrade')
        assert unit1.occupancy_status == 'VACANT'
        assert unit1.current_tenant_id is None
        assert unit2.occupancy_status == 'OCCUPIED'
        assert unit2.current_tenant_id == tenant.id
        assert new_lease.rental_unit_id == unit2.id

        # 2. Process Move-out from unit2
        record = TenantService.process_move_out(
            tenant.id,
            move_out_date=date.today(),
            inspection_notes='Good condition, keys returned',
            deposit_refunded=40000,
            deposit_deductions=5000,
            deduction_reason='Painting touched up'
        )
        assert record.deposit_refunded_cents == 4000000
        assert unit2.occupancy_status == 'VACANT'
        assert unit2.current_tenant_id is None
        assert tenant.is_active is False

