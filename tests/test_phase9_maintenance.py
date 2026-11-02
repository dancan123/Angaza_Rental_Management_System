import pytest
from datetime import date
from app import create_app
from app.extensions import db
from app.models.user import Role, User, Landlord
from app.models.property import RentalUnit
from app.models.tenant import Tenant
from app.models.maintenance import Expense, MaintenanceRequest, MaintenanceRecord
from app.models.communication import Notification
from app.services.property_service import PropertyService
from app.services.tenant_service import TenantService
from app.services.maintenance_service import MaintenanceService
from app.utils.currency import to_cents

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        admin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        db.session.add(admin_role)
        db.session.commit()

        admin = User(
            username='admin_maint',
            email='admin_maint@test.com',
            full_name='Maintenance Admin',
            role=admin_role,
            is_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)

        landlord = Landlord(name='Falcon Realty', phone='+254711555666', email='owner@falcon.co.ke')
        db.session.add(landlord)
        db.session.commit()

        prop = PropertyService.create_property(landlord.id, 'Falcon Gardens', 'FLC-01', 'APARTMENT', 'Madaraka')
        unit = PropertyService.create_unit(prop.id, 'F-204', '2_BEDROOM', 35000, 35000)

        tenant = TenantService.create_tenant('Diana', 'Chebet', 'ID-881122', '+254722556677')
        unit.occupancy_status = 'OCCUPIED'
        unit.current_tenant_id = tenant.id
        db.session.commit()

        yield app
        db.session.remove()
        db.drop_all()

def test_maintenance_lifecycle_and_auto_expense(app):
    with app.app_context():
        unit = RentalUnit.query.first()
        landlord = Landlord.query.first()

        # 1. Log maintenance issue
        req = MaintenanceService.log_request(
            rental_unit_id=unit.id,
            title='Leaking Kitchen Tap',
            description='Water dripping continuously under sink cabinet',
            priority='HIGH'
        )
        assert req.status == 'PENDING'
        assert req.priority == 'HIGH'

        # Check landlord alert
        notif = Notification.query.filter_by(landlord_id=landlord.id, notification_type='MAINTENANCE_LOGGED').first()
        assert notif is not None
        assert "Leaking Kitchen Tap" in notif.message

        # 2. Assign technician
        MaintenanceService.assign_technician(req.id, 'Joshua Plumber', '+254700998877')
        req_refreshed = MaintenanceRequest.query.get(req.id)
        assert req_refreshed.status == 'ASSIGNED'
        assert req_refreshed.assigned_to_technician == 'Joshua Plumber'

        # 3. Resolve request with repair cost of 2,500 KES
        rec = MaintenanceService.resolve_request(
            request_id=req.id,
            work_summary='Replaced faulty valve washers and sealed joints',
            cost=2500,
            completed_by='Joshua Plumber'
        )
        assert rec.cost_cents == 250000
        assert req_refreshed.status == 'RESOLVED'

        # Check linked expense was automatically created
        assert rec.expense_id is not None
        linked_exp = Expense.query.get(rec.expense_id)
        assert linked_exp is not None
        assert linked_exp.category == 'REPAIRS'
        assert linked_exp.amount_cents == 250000

def test_direct_operating_expenses(app):
    with app.app_context():
        prop = RentalUnit.query.first().property
        exp = MaintenanceService.record_expense(
            property_id=prop.id,
            category='SECURITY',
            amount=15000,
            description='Monthly compound guard services',
            supplier_name='SecureGuard Kenya Ltd'
        )
        assert exp.id is not None
        assert exp.category == 'SECURITY'
        assert exp.amount_cents == 1500000

