import base64
import json
import requests
from datetime import datetime
from app.extensions import db
from app.models.gateway import PaymentGatewayConfig, PaymentCallback
from app.models.property import RentalUnit
from app.models.tenant import Tenant
from app.services.payment_service import PaymentService

SANDBOX_URL = "https://sandbox.safaricom.co.ke"
PROD_URL = "https://api.safaricom.co.ke"

class DarajaClient:
    def __init__(self, config: PaymentGatewayConfig):
        self.config = config
        self.base_url = SANDBOX_URL if config.is_sandbox else PROD_URL

    def get_access_token(self):
        """
        Retrieves OAuth access token using HTTP Basic Auth (Consumer Key:Secret).
        """
        if not self.config.consumer_key or not self.config.consumer_secret:
            raise ValueError("Consumer Key and Consumer Secret are required for Daraja authentication.")

        auth_string = f"{self.config.consumer_key}:{self.config.consumer_secret}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode('utf-8')

        headers = {
            "Authorization": f"Basic {encoded_auth}"
        }
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('access_token')
            raise ValueError(f"Daraja OAuth failed [{resp.status_code}]: {resp.text}")
        except requests.RequestException as e:
            raise ConnectionError(f"Network error connecting to Safaricom Daraja: {str(e)}")

    def initiate_stk_push(self, phone_number: str, amount: int, account_reference: str, transaction_desc="Rent Payment"):
        """
        Triggers STK Push (Lipa na M-Pesa Online) prompt to customer's handset.
        """
        token = self.get_access_token()
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        shortcode = self.config.shortcode
        passkey = self.config.passkey

        if not shortcode or not passkey:
            raise ValueError("Shortcode and Passkey are required for STK Push.")

        password_str = f"{shortcode}{passkey}{timestamp}"
        password = base64.b64encode(password_str.encode()).decode('utf-8')

        # Format phone: must be 2547XXXXXXXX
        clean_phone = phone_number.replace('+', '').replace(' ', '').strip()
        if clean_phone.startswith('0'):
            clean_phone = '254' + clean_phone[1:]
        elif clean_phone.startswith('7') or clean_phone.startswith('1'):
            clean_phone = '254' + clean_phone

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        payload = {
            "BusinessShortCode": shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline" if self.config.gateway_type == 'MPESA_PAYBILL' else "CustomerBuyGoodsOnline",
            "Amount": int(amount),
            "PartyA": clean_phone,
            "PartyB": shortcode,
            "PhoneNumber": clean_phone,
            "CallBackURL": self.config.callback_url or "https://example.com/mpesa/stk/callback",
            "AccountReference": account_reference[:12],
            "TransactionDesc": transaction_desc[:12]
        }

        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        return resp.json()


class MpesaCallbackHandler:
    @staticmethod
    def process_c2b_callback(payload: dict):
        """
        Processes Safaricom Daraja C2B Confirmation Webhook.
        Payload keys: TransID, TransAmount, BillRefNumber, MSISDN, FirstName, LastName, TransTime, etc.
        """
        trans_id = payload.get('TransID', '').strip().upper()
        if not trans_id:
            return {"ResultCode": 1, "ResultDesc": "Missing TransID"}, 400

        # 1. Idempotency and duplicate check
        existing_callback = PaymentCallback.query.filter_by(transaction_reference=trans_id).first()
        if existing_callback:
            return {"ResultCode": 0, "ResultDesc": "Duplicate transaction acknowledged"}, 200

        # Resolve organization by matching the incoming shortcode/till against active configs
        incoming_shortcode = payload.get('BusinessShortCode', '').strip()
        matched_cfg = PaymentGatewayConfig.query.filter(
            (PaymentGatewayConfig.shortcode == incoming_shortcode) |
            (PaymentGatewayConfig.till_number == incoming_shortcode)
        ).first()
        org_id = matched_cfg.organization_id if matched_cfg else None

        # Record incoming callback
        callback_log = PaymentCallback(
            organization_id=org_id,
            gateway_type='MPESA_C2B',
            transaction_reference=trans_id,
            payload_json=json.dumps(payload),
            status='RECEIVED'
        )
        db.session.add(callback_log)
        db.session.commit()

        # 2. Extract transaction parameters
        try:
            amount = float(payload.get('TransAmount', 0))
            bill_ref = payload.get('BillRefNumber', '').strip().upper()
            phone = payload.get('MSISDN', '').strip()
            first_name = payload.get('FirstName', '')
            last_name = payload.get('LastName', '')

            from app.models.hospitality import HospitalityReservation, Guest
            from app.utils.currency import to_cents

            # Strategy 0: Check if bill_ref or phone matches an Airbnb / Hospitality reservation
            res = None
            if bill_ref:
                res = HospitalityReservation.query.filter_by(reservation_code=bill_ref).first()
            if not res and phone:
                clean_phone = phone[-9:] if len(phone) >= 9 else phone
                guest = Guest.query.filter(Guest.phone.ilike(f"%{clean_phone}")).first()
                if guest:
                    res = HospitalityReservation.query.filter_by(guest_id=guest.id).filter(
                        HospitalityReservation.status.in_(['CONFIRMED', 'CHECKED_IN'])
                    ).order_by(HospitalityReservation.created_at.desc()).first()

            if res:
                res.paid_amount_cents += to_cents(amount)
                res.payment_method = 'MPESA_PAYBILL'
                res.payment_reference = trans_id
                callback_log.status = 'PROCESSED'
                if res.rental_unit and res.rental_unit.property:
                    callback_log.organization_id = res.rental_unit.property.organization_id
                db.session.commit()

                from app.services.sms_service import SmsService
                from app.services.notification_service import NotificationService
                from app.services.audit_service import AuditService

                SmsService.send_hospitality_payment_sms(res, amount, method='MPESA_PAYBILL', reference=trans_id)
                NotificationService.notify_hospitality_payment(res, amount, method='MPESA_PAYBILL', reference=trans_id)
                AuditService.log('C2B_HOSPITALITY_PAYMENT', 'HospitalityReservation', res.id,
                                 new_values={'amount': amount, 'trans_id': trans_id, 'bill_ref': bill_ref})

                return {"ResultCode": 0, "ResultDesc": "Hospitality payment settled and notifications sent"}, 200

            # 3. Match Tenant and Rental Unit strictly within this organization if known
            from app.models.property import Property
            unit_query = RentalUnit.query.join(Property)
            tenant_query = Tenant.query
            if org_id:
                unit_query = unit_query.filter(Property.organization_id == org_id)
                tenant_query = tenant_query.filter(Tenant.organization_id == org_id)

            # Strategy A: Match bill_ref directly against Unit Number
            unit = unit_query.filter(RentalUnit.unit_number == bill_ref).first()
            tenant = None

            if unit and unit.current_tenant:
                tenant = unit.current_tenant
            else:
                # Strategy B: Match by phone number
                clean_phone = phone[-9:] if len(phone) >= 9 else phone
                tenant = tenant_query.filter(Tenant.phone.ilike(f"%{clean_phone}")).first()
                if tenant and tenant.current_unit:
                    unit = tenant.current_unit

            if not tenant or not unit:
                # Unmatched payment: Log for manual accountant review
                callback_log.status = 'UNMATCHED'
                callback_log.error_message = f"Could not match reference '{bill_ref}' or phone '{phone}' to an active tenant or unit."
                db.session.commit()
                return {"ResultCode": 0, "ResultDesc": "Payment received into reconciliation queue"}, 200

            # Stash org_id onto the callback if it wasn't resolved by shortcode
            if not callback_log.organization_id and unit.property:
                callback_log.organization_id = unit.property.organization_id

            # 4. Record and Confirm Payment
            payment = PaymentService.record_payment(
                tenant_id=tenant.id,
                amount=amount,
                payment_method='MPESA_PAYBILL',
                rental_unit_id=unit.id,
                property_id=unit.property_id,
                transaction_reference=trans_id,
                description=f"M-Pesa C2B payment from {first_name} {last_name} ({phone}) Ref:{bill_ref}",
                auto_confirm=True
            )

            callback_log.status = 'PROCESSED'
            callback_log.processed_payment_id = payment.id
            db.session.commit()

            return {"ResultCode": 0, "ResultDesc": "Success"}, 200

        except Exception as e:
            callback_log.status = 'FAILED'
            callback_log.error_message = str(e)
            db.session.commit()
            return {"ResultCode": 1, "ResultDesc": f"Processing error: {str(e)}"}, 500

    @staticmethod
    def process_stk_callback(payload: dict):
        """
        Processes Safaricom Daraja STK Push Callback.
        """
        body = payload.get('Body', {}).get('stkCallback', {})
        result_code = body.get('ResultCode')
        result_desc = body.get('ResultDesc')

        if result_code != 0:
            # Payment cancelled or failed on handset
            return {"ResultCode": 0, "ResultDesc": f"Acknowledged failure: {result_desc}"}, 200

        # Extract items
        metadata_items = body.get('CallbackMetadata', {}).get('Item', [])
        meta_dict = {item.get('Name'): item.get('Value') for item in metadata_items if 'Name' in item}

        trans_id = str(meta_dict.get('MpesaReceiptNumber', '')).strip().upper()
        amount = float(meta_dict.get('Amount', 0))
        phone = str(meta_dict.get('PhoneNumber', ''))

        if not trans_id:
            return {"ResultCode": 1, "ResultDesc": "Missing MpesaReceiptNumber"}, 400

        # Idempotency check
        existing_callback = PaymentCallback.query.filter_by(transaction_reference=trans_id).first()
        if existing_callback:
            return {"ResultCode": 0, "ResultDesc": "Duplicate transaction acknowledged"}, 200

        callback_log = PaymentCallback(
            gateway_type='MPESA_STK',
            transaction_reference=trans_id,
            payload_json=json.dumps(payload),
            status='RECEIVED'
        )
        db.session.add(callback_log)
        db.session.commit()

        checkout_id = body.get('CheckoutRequestID', '').strip()
        from app.models.hospitality import HospitalityReservation, Guest
        from app.utils.currency import to_cents

        # 1. Match Hospitality / Airbnb reservation by checkout_id or phone
        res = None
        if checkout_id:
            res = HospitalityReservation.query.filter_by(payment_reference=checkout_id).first()
        if not res and phone:
            clean_phone = phone[-9:] if len(phone) >= 9 else phone
            guest = Guest.query.filter(Guest.phone.ilike(f"%{clean_phone}")).first()
            if guest:
                res = HospitalityReservation.query.filter_by(guest_id=guest.id).filter(
                    HospitalityReservation.status.in_(['CONFIRMED', 'CHECKED_IN'])
                ).order_by(HospitalityReservation.created_at.desc()).first()

        if res:
            res.paid_amount_cents += to_cents(amount)
            res.payment_method = 'MPESA_STK'
            res.payment_reference = trans_id
            callback_log.status = 'PROCESSED'
            if res.rental_unit and res.rental_unit.property:
                callback_log.organization_id = res.rental_unit.property.organization_id
            db.session.commit()

            from app.services.sms_service import SmsService
            from app.services.notification_service import NotificationService
            from app.services.audit_service import AuditService

            SmsService.send_hospitality_payment_sms(res, amount, method='MPESA_STK', reference=trans_id)
            NotificationService.notify_hospitality_payment(res, amount, method='MPESA_STK', reference=trans_id)
            AuditService.log('STK_HOSPITALITY_PAYMENT', 'HospitalityReservation', res.id,
                             new_values={'amount': amount, 'trans_id': trans_id, 'checkout_id': checkout_id})

            return {"ResultCode": 0, "ResultDesc": "Hospitality STK payment settled and notifications sent"}, 200

        # 2. Match long-term rental tenant by phone
        clean_phone = phone[-9:] if len(phone) >= 9 else phone
        tenant = Tenant.query.filter(Tenant.phone.ilike(f"%{clean_phone}")).first()
        unit = tenant.current_unit if tenant else None

        if tenant and unit:
            payment = PaymentService.record_payment(
                tenant_id=tenant.id,
                amount=amount,
                payment_method='MPESA_STK',
                rental_unit_id=unit.id,
                property_id=unit.property_id,
                transaction_reference=trans_id,
                description=f"M-Pesa STK Push payment from {phone}",
                auto_confirm=True
            )
            callback_log.status = 'PROCESSED'
            callback_log.processed_payment_id = payment.id
            if unit.property:
                callback_log.organization_id = unit.property.organization_id
            db.session.commit()
            return {"ResultCode": 0, "ResultDesc": "Success"}, 200

        callback_log.status = 'UNMATCHED'
        callback_log.error_message = f"Could not match STK payment from phone '{phone}' to a tenant or reservation."
        db.session.commit()
        return {"ResultCode": 0, "ResultDesc": "Payment received into reconciliation queue"}, 200

