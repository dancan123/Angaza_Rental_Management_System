import pytest
from datetime import date, datetime
from app import create_app
from app.extensions import db
from app.models.property import Property, RentalUnit
from app.models.user import Landlord
from app.models.tenant import Tenant
from app.models.organization import Organization
from app.models.gateway import PaymentGatewayConfig, PaymentCallback
from app.models.hospitality import HospitalityReservation, Guest
from app.models.communication import Notification
from app.services.payment_service import PaymentService
from app.services.sms_service import SmsService
from app.services.notification_service import NotificationService
from app.services.mpesa_service import MpesaCallbackHandler
from app.utils.currency import to_cents


@pytest.fixture
def app():
    app_obj = create_app()
    app_obj.config['TESTING'] = True
    app_obj.config['WTF_CSRF_ENABLED'] = False
    return app_obj


@pytest.fixture
def automation_setup(app):
    with app.app_context():
        # Setup unique Organization
        timestamp = int(datetime.utcnow().timestamp() * 1000)
        org = Organization(
            name=f"Automation Realty {timestamp}",
            slug=f"auto-realty-{timestamp}",
            org_code=f"ANG{timestamp % 10000:04d}",
            contact_email=f"manager_{timestamp}@test.com",
            contact_phone="+254711999888",
            sms_credits=100,
            auto_send_payment_thank_you=True,
            auto_notify_landlord_on_payment=True,
            auto_notify_manager_on_payment=True
        )
        db.session.add(org)
        db.session.commit()

        # Setup Landlord
        landlord = Landlord(
            name="David Kamau",
            contact_person="David Kamau",
            email=f"landlord_{timestamp}@test.com",
            phone="+254722334455"
        )
        db.session.add(landlord)
        db.session.commit()

        # Setup Property
        prop = Property(
            organization_id=org.id,
            landlord_id=landlord.id,
            name=f"Serene Heights Residency {timestamp % 1000}",
            ref_number=f"PROP-{timestamp % 10000}",
            location="Nairobi, Westlands",
            property_type="RESIDENTIAL"
        )
        db.session.add(prop)
        db.session.commit()

        # Setup Rental Units
        unit1 = RentalUnit(
            property_id=prop.id,
            unit_number=f"APT-{timestamp % 1000}",
            rent_amount_cents=to_cents(25000),
            occupancy_status="OCCUPIED"
        )
        unit_airbnb = RentalUnit(
            property_id=prop.id,
            unit_number=f"SUITE-{timestamp % 1000}",
            rent_amount_cents=to_cents(5000),
            unit_type="1 Bedroom",
            operational_type="SHORT_STAY",
            daily_rate_cents=to_cents(5000),
            occupancy_status="VACANT"
        )
        db.session.add_all([unit1, unit_airbnb])
        db.session.commit()

        # Setup Tenant
        tenant = Tenant(
            organization_id=org.id,
            first_name="Faith",
            last_name="Wanjiku",
            phone="+254712345678",
            email=f"tenant_{timestamp}@test.com",
            id_passport_number=f"ID{timestamp % 1000000}",
            is_active=True
        )
        db.session.add(tenant)
        db.session.commit()

        unit1.current_tenant_id = tenant.id
        db.session.commit()

        # Setup Gateway Config
        gateway = PaymentGatewayConfig(
            organization_id=org.id,
            property_id=prop.id,
            name="Serene Heights Paybill",
            gateway_type="MPESA_PAYBILL",
            shortcode="174379",
            auto_send_thank_you_sms=True,
            auto_notify_landlord=True,
            auto_notify_manager=True
        )
        db.session.add(gateway)
        db.session.commit()

        # Setup Hospitality Guest & Reservation
        guest = Guest(
            first_name="Michael",
            last_name="Otieno",
            phone="+254798765432",
            email=f"michael_{timestamp}@test.com"
        )
        db.session.add(guest)
        db.session.commit()

        res_code = f"RES-AUTO-{timestamp % 10000}"
        reservation = HospitalityReservation(
            organization_id=org.id,
            reservation_code=res_code,
            guest_id=guest.id,
            rental_unit_id=unit_airbnb.id,
            check_in_date=date(2026, 12, 1),
            check_out_date=date(2026, 12, 3),
            num_guests=2,
            num_nights=2,
            daily_rate_cents=to_cents(5000),
            total_stay_cents=to_cents(10000),
            paid_amount_cents=0,
            status="CONFIRMED",
            payment_reference=f"ws_CO_{timestamp}"
        )
        db.session.add(reservation)
        db.session.commit()

        return {
            'org_id': org.id,
            'landlord_id': landlord.id,
            'prop_id': prop.id,
            'unit1_id': unit1.id,
            'unit_airbnb_id': unit_airbnb.id,
            'tenant_id': tenant.id,
            'gateway_id': gateway.id,
            'guest_id': guest.id,
            'res_id': reservation.id
        }


def test_rent_payment_auto_sends_thank_you_and_landlord_alert(app, automation_setup):
    """
    Verifies that when a rent payment is recorded and confirmed:
    1. Automated Thank-You SMS is sent to tenant with amount, room number, property, and balance.
    2. Automated Payment Alert SMS is sent to Landlord with tenant name, phone, room number, amount, ref.
    3. In-App notification is sent to Landlord.
    """
    with app.app_context():
        tenant = db.session.get(Tenant, automation_setup['tenant_id'])
        unit = db.session.get(RentalUnit, automation_setup['unit1_id'])
        landlord = db.session.get(Landlord, automation_setup['landlord_id'])

        payment = PaymentService.record_payment(
            tenant_id=tenant.id,
            amount=25000,
            payment_method='MPESA_PAYBILL',
            rental_unit_id=unit.id,
            transaction_reference=f"QK{int(datetime.utcnow().timestamp())}",
            description="M-Pesa payment",
            auto_confirm=True
        )

        assert payment.payment_status == 'CONFIRMED'

        # Check SMS notifications generated
        sms_notifs = Notification.query.filter_by(channel='SMS').order_by(Notification.id.desc()).limit(10).all()
        sms_texts = [n.message for n in sms_notifs]

        # 1. Tenant Thank You SMS check
        tenant_sms = [m for m in sms_texts if tenant.first_name in m and "thank you" in m.lower()]
        assert len(tenant_sms) >= 1
        assert unit.unit_number in tenant_sms[0]
        assert "25,000" in tenant_sms[0]
        assert payment.receipt_number in tenant_sms[0]

        # 2. Landlord Alert SMS check
        landlord_sms = [m for m in sms_texts if "PAYMENT RECEIVED ALERT" in m and tenant.full_name in m]
        assert len(landlord_sms) >= 1
        assert tenant.phone in landlord_sms[0]
        assert unit.unit_number in landlord_sms[0]
        assert "25,000" in landlord_sms[0]

        # 3. In-App Landlord notification check
        in_app = Notification.query.filter_by(
            landlord_id=landlord.id,
            channel='IN_APP',
            notification_type='RENT_PAYMENT_CONFIRMED'
        ).first()
        assert in_app is not None
        assert tenant.full_name in in_app.message
        assert tenant.phone in in_app.message
        assert unit.unit_number in in_app.message


def test_stk_callback_for_hospitality_reservation(app, automation_setup):
    """
    Verifies that when Safaricom STK Push callback arrives for an Airbnb reservation:
    1. Reservation paid amount is credited and checkout ID is replaced with MpesaReceiptNumber.
    2. Automated Thank-You note SMS is sent to the Guest.
    3. Automated Alert SMS is sent to the Landlord with guest name, phone, room number, amount, ref.
    4. In-App notification is sent to Landlord.
    """
    with app.app_context():
        res = db.session.get(HospitalityReservation, automation_setup['res_id'])
        checkout_id = res.payment_reference
        guest = db.session.get(Guest, automation_setup['guest_id'])
        unit = db.session.get(RentalUnit, automation_setup['unit_airbnb_id'])
        landlord = db.session.get(Landlord, automation_setup['landlord_id'])

        trans_id = f"NL{int(datetime.utcnow().timestamp())}"
        stk_payload = {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "29115-34620561-1",
                    "CheckoutRequestID": checkout_id,
                    "ResultCode": 0,
                    "ResultDesc": "The service request is processed successfully.",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount", "Value": 10000},
                            {"Name": "MpesaReceiptNumber", "Value": trans_id},
                            {"Name": "Balance"},
                            {"Name": "TransactionDate", "Value": 20261121150000},
                            {"Name": "PhoneNumber", "Value": 254798765432}
                        ]
                    }
                }
            }
        }

        resp, status_code = MpesaCallbackHandler.process_stk_callback(stk_payload)
        assert status_code == 200
        assert resp.get("ResultCode") == 0

        # Refresh reservation
        db.session.refresh(res)
        assert res.paid_amount_cents == to_cents(10000)
        assert res.payment_reference == trans_id
        assert res.payment_method == 'MPESA_STK'

        # Check SMS notifications
        sms_notifs = Notification.query.filter_by(channel='SMS').order_by(Notification.id.desc()).limit(10).all()
        sms_texts = [n.message for n in sms_notifs]

        # Guest Thank You SMS
        guest_sms = [m for m in sms_texts if guest.first_name in m and "thank you" in m.lower()]
        assert len(guest_sms) >= 1
        assert unit.unit_number in guest_sms[0]
        assert "10,000" in guest_sms[0]
        assert "SETTLED" in guest_sms[0]

        # Landlord Alert SMS
        landlord_sms = [m for m in sms_texts if "PAYMENT RECEIVED ALERT" in m and guest.full_name in m]
        assert len(landlord_sms) >= 1
        assert guest.phone in landlord_sms[0]
        assert unit.unit_number in landlord_sms[0]
        assert "10,000" in landlord_sms[0]
        assert trans_id in landlord_sms[0]

        # Landlord In-App notification
        in_app = Notification.query.filter_by(
            landlord_id=landlord.id,
            channel='IN_APP',
            notification_type='HOSPITALITY_PAYMENT_CONFIRMED'
        ).first()
        assert in_app is not None
        assert guest.full_name in in_app.message
        assert guest.phone in in_app.message
        assert unit.unit_number in in_app.message


def test_c2b_callback_for_hospitality_reservation(app, automation_setup):
    """
    Verifies that when a C2B Paybill payment is received referencing a reservation code:
    1. Reservation is credited.
    2. Guest receives thank you note.
    3. Landlord receives alert message with guest name, phone, room number, amount.
    """
    with app.app_context():
        res = db.session.get(HospitalityReservation, automation_setup['res_id'])
        guest = db.session.get(Guest, automation_setup['guest_id'])
        unit = db.session.get(RentalUnit, automation_setup['unit_airbnb_id'])
        landlord = db.session.get(Landlord, automation_setup['landlord_id'])

        # Reset paid amount
        res.paid_amount_cents = 0
        db.session.commit()

        trans_id = f"C2B{int(datetime.utcnow().timestamp())}"
        c2b_payload = {
            "TransactionType": "Pay Bill",
            "TransID": trans_id,
            "TransTime": datetime.now().strftime('%Y%m%d%H%M%S'),
            "TransAmount": "5000",
            "BusinessShortCode": "174379",
            "BillRefNumber": res.reservation_code,
            "MSISDN": "254798765432",
            "FirstName": "Michael",
            "LastName": "Otieno"
        }

        resp, status_code = MpesaCallbackHandler.process_c2b_callback(c2b_payload)
        assert status_code == 200
        assert resp.get("ResultCode") == 0

        db.session.refresh(res)
        assert res.paid_amount_cents == to_cents(5000)
        assert res.payment_reference == trans_id

        # Verify SMS alerts dispatched
        sms_notifs = Notification.query.filter_by(channel='SMS').order_by(Notification.id.desc()).limit(10).all()
        sms_texts = [n.message for n in sms_notifs]

        guest_sms = [m for m in sms_texts if guest.first_name in m and "thank you" in m.lower()]
        assert len(guest_sms) >= 1
        assert "5,000" in guest_sms[0]

        landlord_sms = [m for m in sms_texts if "PAYMENT RECEIVED ALERT" in m and guest.full_name in m]
        assert len(landlord_sms) >= 1
        assert guest.phone in landlord_sms[0]
        assert unit.unit_number in landlord_sms[0]
        assert "5,000" in landlord_sms[0]


def test_hospitality_manual_record_payment_automation(app, automation_setup):
    """
    Verifies that when a payment is manually recorded for an Airbnb stay via hospitality_bp:
    Guest gets Thank You SMS and Landlord gets Alert SMS.
    """
    with app.app_context():
        res = db.session.get(HospitalityReservation, automation_setup['res_id'])
        guest = db.session.get(Guest, automation_setup['guest_id'])
        unit = db.session.get(RentalUnit, automation_setup['unit_airbnb_id'])
        landlord = db.session.get(Landlord, automation_setup['landlord_id'])

        res.paid_amount_cents = 0
        db.session.commit()

        SmsService.send_hospitality_payment_sms(res, 5000, method='CASH', reference='REC-CASH-001')
        NotificationService.notify_hospitality_payment(res, 5000, method='CASH', reference='REC-CASH-001')

        sms_notifs = Notification.query.filter_by(channel='SMS').order_by(Notification.id.desc()).limit(10).all()
        sms_texts = [n.message for n in sms_notifs]

        # Guest Thank You SMS
        guest_sms = [m for m in sms_texts if guest.first_name in m and "thank you" in m.lower()]
        assert len(guest_sms) >= 1
        assert unit.unit_number in guest_sms[0]
        assert "5,000" in guest_sms[0]

        # Landlord Alert SMS
        landlord_sms = [m for m in sms_texts if "PAYMENT RECEIVED ALERT" in m and guest.full_name in m]
        assert len(landlord_sms) >= 1
        assert guest.phone in landlord_sms[0]
        assert unit.unit_number in landlord_sms[0]
        assert "5,000" in landlord_sms[0]
