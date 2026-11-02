import pytest
from datetime import date
from app import create_app
from app.extensions import db
from app.models.user import Role, User, Landlord
from app.models.property import RentalUnit
from app.models.tenant import Tenant
from app.models.lease import Lease
from app.models.maintenance import Expense
from app.services.property_service import PropertyService
from app.services.tenant_service import TenantService
from app.services.rent_service import RentService
from app.services.payment_service import PaymentService
from app.services.report_service import ReportService
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
            username='admin_rpt',
            email='admin_rpt@test.com',
            full_name='Reports Admin',
            role=admin_role,
            is_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)

        # Landlord 1
        l1 = Landlord(name='Prestige Holdings', phone='+254700111222')
        db.session.add(l1)
        db.session.commit()

        prop = PropertyService.create_property(l1.id, 'Prestige Towers', 'PT-01', 'APARTMENT', 'Kilimani')
        unit = PropertyService.create_unit(prop.id, 'PT-101', '2_BEDROOM', 50000, 50000)

        tenant = TenantService.create_tenant('Charles', 'Mugo', 'ID-990011', '+254722334455')
        unit.occupancy_status = 'OCCUPIED'
        unit.current_tenant_id = tenant.id

        lease = Lease(
            lease_number='LSE-PT-101',
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            start_date=date(2026, 1, 1),
            monthly_rent_cents=to_cents(50000),
            status='ACTIVE'
        )
        db.session.add(lease)
        db.session.commit()

        # Generate invoice of 50,000 for month 10 and 11
        RentService.generate_monthly_charges(10, 2026)
        RentService.generate_monthly_charges(11, 2026)

        # Pay 50,000 via M-Pesa Paybill
        PaymentService.record_payment(
            tenant_id=tenant.id,
            amount=50000,
            payment_method='MPESA_PAYBILL',
            transaction_reference='RPT12345',
            auto_confirm=True
        )

        # Record Expense of 5,000 for plumbing
        exp = Expense(
            property_id=prop.id,
            category='PLUMBING',
            amount_cents=to_cents(5000),
            expense_date=date.today(),
            description='Repair leaking pipe in basement'
        )
        db.session.add(exp)
        db.session.commit()

        yield app
        db.session.remove()
        db.drop_all()

def test_collection_report(app):
    with app.app_context():
        report = ReportService.get_collection_report()
        assert report['count'] == 1
        assert report['total_cents'] == 5000000
        assert report['by_method']['MPESA_PAYBILL'] == 5000000

def test_arrears_report(app):
    with app.app_context():
        report = ReportService.get_arrears_report()
        # Month 11 charge of 50,000 is still unpaid
        assert report['count'] == 1
        assert report['total_arrears_cents'] == 5000000
        assert len(report['by_tenant']) == 1
        assert report['by_tenant'][0]['tenant'].full_name == 'Charles Mugo'

def test_income_statement(app):
    with app.app_context():
        pnl = ReportService.get_income_statement()
        assert pnl['total_income_cents'] == 5000000
        assert pnl['total_expenses_cents'] == 500000
        assert pnl['net_operating_income_cents'] == 4500000
        assert pnl['exp_by_category']['PLUMBING'] == 500000

def test_landlord_statement(app):
    with app.app_context():
        l1 = Landlord.query.first()
        stmt = ReportService.get_landlord_statement(l1.id)
        assert stmt['landlord'].id == l1.id
        assert stmt['gross_income_cents'] == 5000000
        assert stmt['total_expenses_cents'] == 500000
        assert stmt['net_payout_cents'] == 4500000

def test_excel_export(app):
    with app.app_context():
        report = ReportService.get_collection_report()
        xlsx_bytes = ReportService.export_collection_excel(report)
        assert xlsx_bytes is not None
        assert len(xlsx_bytes) > 1000
        # Check ZIP / XLSX magic bytes (PK\x03\x04)
        assert xlsx_bytes.startswith(b'PK\x03\x04')

