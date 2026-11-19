"""
Phase 18 – Consolidated Financial Summary & Executive P&L Tests
Tests:
  1. Aggregation of Rental Revenue (Payments)
  2. Aggregation of Hospitality Revenue (Short-Stay Stays)
  3. Operating Expenses aggregation
  4. Net Operating Income (NOI) and Profit Margin calculations
  5. Executive Consolidated Report route rendering
"""
import pytest
from datetime import date, timedelta
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.property import Property, RentalUnit
from app.models.tenant import Tenant
from app.models.finance import RentCharge, Payment
from app.models.maintenance import Expense
from app.models.hospitality import Guest, HospitalityReservation
from app.services.report_service import ReportService
from app.utils.currency import to_cents


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        admin_role = Role(name='SUPERADMIN', display_name='Super Admin', is_system=True)
        perms = [
            Permission(code='reports.view', module='reports', description='View reports'),
        ]
        db.session.add(admin_role)
        db.session.add_all(perms)
        db.session.commit()

        admin = User(
            username='cfo_user',
            email='cfo@angaza.co.ke',
            full_name='Chief Financial Officer',
            role=admin_role,
            is_active=True
        )
        admin.set_password('CfoPass2026!')
        db.session.add(admin)

        ll = Landlord(name='Apex Portfolio Ltd', phone='+254711888999')
        db.session.add(ll)
        db.session.commit()

        # Property
        prop = Property(
            landlord_id=ll.id,
            name='Apex Towers & Suites',
            ref_number='ATS-001',
            property_type='MIXED_USE',
            location='Upperhill, Nairobi'
        )
        db.session.add(prop)
        db.session.commit()

        # Rental Unit
        rental_unit = RentalUnit(
            property_id=prop.id,
            unit_number='A101',
            operational_type='LONG_TERM',
            rent_amount_cents=to_cents(50000)
        )
        # Short-stay Unit
        hosp_unit = RentalUnit(
            property_id=prop.id,
            unit_number='S201',
            operational_type='SHORT_STAY',
            daily_rate_cents=to_cents(6000)
        )
        db.session.add_all([rental_unit, hosp_unit])
        db.session.commit()

        # Tenant & Rental Payment
        tenant = Tenant(
            first_name='John',
            last_name='Kamau',
            id_passport_number='ID99887766',
            phone='+254722334455',
            is_active=True
        )
        db.session.add(tenant)
        db.session.commit()

        today = date.today()
        payment = Payment(
            tenant_id=tenant.id,
            rental_unit_id=rental_unit.id,
            property_id=prop.id,
            payment_number='PAY-TEST-001',
            receipt_number='REC-TEST-001',
            amount_cents=to_cents(50000),
            payment_date=today,
            payment_method='MPESA_PAYBILL',
            transaction_reference='QA12345678',
            payment_status='CONFIRMED'
        )
        db.session.add(payment)

        # Hospitality Guest & Reservation
        guest = Guest(first_name='Alice', last_name='Wanjiku', phone='+254733112233')
        db.session.add(guest)
        db.session.commit()

        res = HospitalityReservation(
            reservation_code='STAY-TEST-001',
            guest_id=guest.id,
            rental_unit_id=hosp_unit.id,
            check_in_date=today,
            check_out_date=today + timedelta(days=3),
            num_nights=3,
            daily_rate_cents=to_cents(6000),
            total_stay_cents=to_cents(18000),
            paid_amount_cents=to_cents(18000),
            status='CONFIRMED'
        )
        db.session.add(res)

        # Operational Expense
        exp = Expense(
            property_id=prop.id,
            category='UTILITIES',
            amount_cents=to_cents(8000),
            expense_date=today,
            description='Generator Fuel & Power'
        )
        db.session.add(exp)
        db.session.commit()

        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_consolidated_financial_summary_service(app):
    """Verify ReportService.get_consolidated_financial_summary aggregates correctly."""
    with app.app_context():
        today = date.today()
        summary = ReportService.get_consolidated_financial_summary(
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=5)
        )

        assert summary['rental_income_cents'] == to_cents(50000)
        assert summary['hospitality_income_cents'] == to_cents(18000)
        assert summary['total_revenue_cents'] == to_cents(68000)
        assert summary['total_expenses_cents'] == to_cents(8000)
        assert summary['net_operating_income_cents'] == to_cents(60000)
        assert summary['profit_margin_pct'] == 88.2  # 60000 / 68000 * 100


def test_consolidated_report_route(app, client):
    """Verify the /reports/consolidated endpoint renders executive financial metrics."""
    client.post('/auth/login', data={
        'username': 'cfo_user',
        'password': 'CfoPass2026!'
    }, follow_redirects=True)

    res = client.get('/reports/consolidated')
    assert res.status_code == 200
    assert b'Consolidated Executive P' in res.data
    assert b'68,000' in res.data or b'60,000' in res.data
