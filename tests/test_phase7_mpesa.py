import pytest
from datetime import date
from app import create_app
from app.extensions import db
from app.models.user import Role, User, Landlord
from app.models.property import RentalUnit
from app.models.tenant import Tenant
from app.models.lease import Lease
from app.models.finance import RentCharge, Payment
from app.models.gateway import PaymentCallback
from app.models.communication import Notification
from app.services.property_service import PropertyService
from app.services.tenant_service import TenantService
from app.services.rent_service import RentService
from app.services.mpesa_service import MpesaCallbackHandler
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
            username='admin_mpesa',
            email='admin_mpesa@test.com',
            full_name='M-Pesa Admin',
            role=admin_role,
            is_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)

        landlord = Landlord(name='Samaki Heights', phone='+254711000999', email='samaki@landlord.co.ke')
        db.session.add(landlord)
        db.session.commit()

        prop = PropertyService.create_property(landlord.id, 'Samaki Court', 'SMK-01', 'APARTMENT', 'Nairobi West')
        unit = PropertyService.create_unit(prop.id, 'S-101', '1_BEDROOM', 20000, 20000)

        tenant = TenantService.create_tenant('John', 'Kamau', 'ID-112233', '+254712345678')
        unit.occupancy_status = 'OCCUPIED'
        unit.current_tenant_id = tenant.id

        lease = Lease(
            lease_number='LSE-SMK-101',
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            start_date=date(2026, 1, 1),
            monthly_rent_cents=to_cents(20000),
            status='ACTIVE'
        )
        db.session.add(lease)
        db.session.commit()

        # Invoiced rent of 20,000 for current month
        RentService.generate_monthly_charges(11, 2026)

        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_c2b_callback_success_flow(app):
    with app.app_context():
        charge = RentCharge.query.filter_by(period_month=11, period_year=2026).first()
        assert charge.balance_cents == 2000000
        assert charge.status == 'UNPAID'

        payload = {
            "TransactionType": "Pay Bill",
            "TransID": "QWE123XYZ",
            "TransTime": "20261102120000",
            "TransAmount": "20000.00",
            "BusinessShortCode": "247247",
            "BillRefNumber": "S-101",
            "MSISDN": "254712345678",
            "FirstName": "John",
            "LastName": "Kamau"
        }

        res, status = MpesaCallbackHandler.process_c2b_callback(payload)
        assert status == 200
        assert res['ResultCode'] == 0

        # Check payment record
        payment = Payment.query.filter_by(transaction_reference='QWE123XYZ').first()
        assert payment is not None
        assert payment.payment_status == 'CONFIRMED'
        assert payment.amount_cents == 2000000
        assert payment.rental_unit.unit_number == 'S-101'

        # Check charge settlement
        charge_updated = RentCharge.query.get(charge.id)
        assert charge_updated.status == 'PAID'
        assert charge_updated.balance_cents == 0

        # Check landlord alert
        notif = Notification.query.filter_by(notification_type='RENT_PAYMENT_CONFIRMED').first()
        assert notif is not None
        assert "QWE123XYZ" in notif.message
        assert "Samaki Court" in notif.message
        assert "S-101" in notif.message

def test_c2b_callback_duplicate_idempotency(app):
    with app.app_context():
        payload = {
            "TransactionType": "Pay Bill",
            "TransID": "DUP999000",
            "TransTime": "20261102120000",
            "TransAmount": "10000.00",
            "BusinessShortCode": "247247",
            "BillRefNumber": "S-101",
            "MSISDN": "254712345678",
            "FirstName": "John",
            "LastName": "Kamau"
        }

        # First call
        res1, status1 = MpesaCallbackHandler.process_c2b_callback(payload)
        assert status1 == 200
        assert res1['ResultCode'] == 0

        payments_count1 = Payment.query.filter_by(transaction_reference='DUP999000').count()
        assert payments_count1 == 1

        # Second call with exact same TransID (replay attack or network duplicate)
        res2, status2 = MpesaCallbackHandler.process_c2b_callback(payload)
        assert status2 == 200
        assert res2['ResultCode'] == 0
        assert "Duplicate transaction acknowledged" in res2['ResultDesc']

        # Count must remain 1
        payments_count2 = Payment.query.filter_by(transaction_reference='DUP999000').count()
        assert payments_count2 == 1

def test_c2b_unmatched_reference(app):
    with app.app_context():
        payload = {
            "TransactionType": "Pay Bill",
            "TransID": "UNMATCHED777",
            "TransTime": "20261102120000",
            "TransAmount": "15000.00",
            "BusinessShortCode": "247247",
            "BillRefNumber": "NON_EXISTENT_UNIT",
            "MSISDN": "254799000000",
            "FirstName": "Stranger",
            "LastName": "Person"
        }

        res, status = MpesaCallbackHandler.process_c2b_callback(payload)
        assert status == 200
        assert res['ResultCode'] == 0

        cb = PaymentCallback.query.filter_by(transaction_reference='UNMATCHED777').first()
        assert cb is not None
        assert cb.status == 'UNMATCHED'

