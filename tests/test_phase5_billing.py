
import pytest
from datetime import date
from app import create_app
from app.extensions import db
from app.models.user import Role, User, Landlord
from app.models.tenant import Tenant
from app.models.lease import Lease
from app.models.finance import RentCharge, PaymentReversal
from app.models.communication import Notification
from app.services.property_service import PropertyService
from app.services.tenant_service import TenantService
from app.services.rent_service import RentService
from app.services.payment_service import PaymentService
from app.utils.pdf_generator import generate_receipt_pdf
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
            username='admin_bill',
            email='admin_bill@test.com',
            full_name='Billing Admin',
            role=admin_role,
            is_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)

        landlord = Landlord(name='Apex Landlord', phone='+254711888999', email='owner@apex.co.ke')
        db.session.add(landlord)
        db.session.commit()

        prop = PropertyService.create_property(landlord.id, 'Apex Heights', 'APX-01', 'APARTMENT', 'Kilimani')
        unit = PropertyService.create_unit(prop.id, 'U-201', '2_BEDROOM', 30000, 30000)

        tenant = TenantService.create_tenant('Grace', 'Njeri', 'ID-556677', '+254700556677')
        unit.occupancy_status = 'OCCUPIED'
        unit.current_tenant_id = tenant.id

        lease = Lease(
            lease_number='LSE-APX-201',
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            start_date=date(2026, 1, 1),
            monthly_rent_cents=to_cents(30000),
            deposit_cents=to_cents(30000),
            status='ACTIVE'
        )
        db.session.add(lease)
        db.session.commit()

        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_monthly_rent_generation_and_idempotency(app):
    with app.app_context():
        # First run: generates 1 charge for Month 11, Year 2026
        res1 = RentService.generate_monthly_charges(11, 2026)
        assert res1['created_count'] == 1
        assert res1['total_amount_cents'] == to_cents(30000)

        charge = RentCharge.query.filter_by(period_month=11, period_year=2026).first()
        assert charge is not None
        assert charge.status == 'UNPAID'
        assert charge.amount_cents == 3000000
        assert charge.amount_paid_cents == 0

        # Second run for same period: must skip and create 0 charges (idempotent)
        res2 = RentService.generate_monthly_charges(11, 2026)
        assert res2['created_count'] == 0

def test_payment_recording_and_chronological_allocation(app):
    with app.app_context():
        tenant = Tenant.query.first()
        # Generate 2 months charges: Month 10 (30,000) and Month 11 (30,000)
        RentService.generate_monthly_charges(10, 2026)
        RentService.generate_monthly_charges(11, 2026)

        c10 = RentCharge.query.filter_by(period_month=10, period_year=2026).first()
        c11 = RentCharge.query.filter_by(period_month=11, period_year=2026).first()
        assert c10.balance_cents == 3000000
        assert c11.balance_cents == 3000000

        # Tenant makes a partial payment of 40,000 KES
        # It must completely settle Month 10 (30,000) and partially settle Month 11 with 10,000!
        payment = PaymentService.record_payment(
            tenant_id=tenant.id,
            amount=40000,
            payment_method='MPESA_PAYBILL',
            transaction_reference='MPESA12345',
            auto_confirm=True
        )

        assert payment.payment_status == 'CONFIRMED'
        assert payment.receipt_number.startswith('REC-')

        # Check allocations
        c10_refreshed = RentCharge.query.get(c10.id)
        c11_refreshed = RentCharge.query.get(c11.id)

        assert c10_refreshed.status == 'PAID'
        assert c10_refreshed.amount_paid_cents == 3000000
        assert c10_refreshed.balance_cents == 0

        assert c11_refreshed.status == 'PARTIALLY_PAID'
        assert c11_refreshed.amount_paid_cents == 1000000
        assert c11_refreshed.balance_cents == 2000000

        # Verify duplicate transaction reference guard
        with pytest.raises(ValueError) as excinfo:
            PaymentService.record_payment(
                tenant_id=tenant.id,
                amount=5000,
                payment_method='MPESA_PAYBILL',
                transaction_reference='MPESA12345'
            )
        assert "Duplicate payment reference" in str(excinfo.value)

def test_payment_reversal_workflow(app):
    with app.app_context():
        tenant = Tenant.query.first()
        RentService.generate_monthly_charges(11, 2026)
        charge = RentCharge.query.filter_by(period_month=11, period_year=2026).first()

        # Record payment of 30,000
        payment = PaymentService.record_payment(
            tenant_id=tenant.id,
            amount=30000,
            payment_method='BANK_TRANSFER',
            transaction_reference='BNK-REV-001',
            auto_confirm=True
        )
        assert charge.status == 'PAID'

        # Reverse payment
        reversed_pay = PaymentService.reverse_payment(payment.id, reversal_reason='Bank reversed cheque')
        assert reversed_pay.payment_status == 'REVERSED'

        # Charge must be restored to UNPAID
        charge_after = RentCharge.query.get(charge.id)
        assert charge_after.status == 'UNPAID'
        assert charge_after.amount_paid_cents == 0
        assert charge_after.balance_cents == 3000000

        # Check reversal record
        reversal = PaymentReversal.query.filter_by(payment_id=payment.id).first()
        assert reversal is not None
        assert reversal.reversal_reason == 'Bank reversed cheque'

def test_landlord_notification_on_payment(app):
    with app.app_context():
        tenant = Tenant.query.first()
        landlord = Landlord.query.first()

        _ = PaymentService.record_payment(
            tenant_id=tenant.id,
            amount=15000,
            payment_method='CASH',
            auto_confirm=True
        )

        # Landlord notifications must have been generated
        notifs = Notification.query.filter_by(landlord_id=landlord.id).all()
        assert len(notifs) >= 1
        rent_notif = next((n for n in notifs if n.notification_type == 'RENT_PAYMENT_CONFIRMED'), None)
        assert rent_notif is not None
        assert "RENT PAYMENT RECEIVED" in rent_notif.message
        assert tenant.full_name in rent_notif.message

def test_pdf_receipt_generation(app):
    with app.app_context():
        tenant = Tenant.query.first()
        payment = PaymentService.record_payment(
            tenant_id=tenant.id,
            amount=20000,
            payment_method='MPESA_TILL',
            transaction_reference='TIL987654',
            auto_confirm=True
        )

        pdf_bytes = generate_receipt_pdf(payment)
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 500  # Valid non-empty PDF bytes
        assert pdf_bytes.startswith(b'%PDF')
