import os
import requests
from datetime import datetime
from app.extensions import db
from app.models.communication import Notification
from app.services.personalization_service import PersonalizationService

class SmsService:
    """
    Twilio SMS integration service.
    Handles message composition, E.164 phone number formatting (Kenya +254 and international),
    Twilio HTTP REST API dispatch, delivery logging, and sandbox/simulation fallbacks.
    """

    @staticmethod
    def format_phone_number(phone: str) -> str:
        """
        Formats phone number into standard E.164 format.
        Supports Kenyan formats:
          0712345678 -> +254712345678
          0112345678 -> +254112345678
          254712345678 -> +254712345678
          +254712345678 -> +254712345678
        """
        if not phone:
            return ""
        clean = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').strip()
        if clean.startswith('+'):
            return clean
        if clean.startswith('0'):
            return '+254' + clean[1:]
        if clean.startswith('254'):
            return '+' + clean
        if clean.startswith('7') or clean.startswith('1'):
            return '+254' + clean
        return '+' + clean

    @classmethod
    def get_twilio_credentials(cls, organization=None):
        """
        Retrieves Twilio configuration from organization or system settings fallback.
        """
        if organization and getattr(organization, 'twilio_account_sid', None) and getattr(organization, 'twilio_auth_token', None):
            return {
                'account_sid': organization.twilio_account_sid.strip(),
                'auth_token': organization.twilio_auth_token.strip(),
                'from_number': (organization.twilio_from_number or '').strip(),
                'is_enabled': True
            }

        account_sid = PersonalizationService.get_setting('twilio_account_sid', os.environ.get('TWILIO_ACCOUNT_SID', ''))
        auth_token = PersonalizationService.get_setting('twilio_auth_token', os.environ.get('TWILIO_AUTH_TOKEN', ''))
        from_number = PersonalizationService.get_setting('twilio_from_number', os.environ.get('TWILIO_FROM_NUMBER', ''))
        is_enabled = PersonalizationService.get_setting('twilio_sms_enabled', 'false').lower() in ('true', '1', 'yes')

        return {
            'account_sid': account_sid.strip() if account_sid else '',
            'auth_token': auth_token.strip() if auth_token else '',
            'from_number': from_number.strip() if from_number else '',
            'is_enabled': is_enabled
        }

    @classmethod
    def send_sms(cls, to_phone: str, message: str, notification_type='GENERAL', landlord_id=None, recipient_user_id=None, organization_id=None):
        """
        Sends an SMS to the target recipient.
        Deducts from organization's SMS credit balance if applicable.
        If Twilio credentials are not set or disabled, logs a SIMULATED notification.
        """
        formatted_phone = cls.format_phone_number(to_phone)
        if not formatted_phone:
            return {'success': False, 'error': 'Invalid recipient phone number'}

        # Verify Organization SMS credit balance
        from flask_login import current_user
        from app.models.organization import Organization
        target_org = None
        if organization_id:
            target_org = db.session.get(Organization, organization_id)
        elif current_user and current_user.is_authenticated:
            org_id = getattr(current_user, 'organization_id', None)
            if org_id:
                target_org = db.session.get(Organization, org_id)
                if target_org:
                    db.session.refresh(target_org)
            if not target_org:
                target_org = getattr(current_user, 'active_organization', None)
                if target_org:
                    db.session.refresh(target_org)

        # Superadmin has unlimited SMS bypass
        is_admin_bypass = current_user and current_user.is_authenticated and current_user.is_superadmin()
        if target_org and not is_admin_bypass:
            if target_org.sms_credits <= 0:
                return {
                    'success': False,
                    'error': f"Insufficient SMS credits. Organization '{target_org.name}' has 0 credits remaining. Please contact Superadmin to top up."
                }

        creds = cls.get_twilio_credentials(organization=target_org)

        notif = Notification(
            recipient_user_id=recipient_user_id,
            landlord_id=landlord_id,
            title=f"SMS to {formatted_phone}",
            message=message,
            channel='SMS',
            notification_type=notification_type,
            sent_status='PENDING'
        )
        db.session.add(notif)
        db.session.commit()

        # Deduct SMS credit from organization wallet
        if target_org and not is_admin_bypass:
            target_org.sms_credits = max(0, target_org.sms_credits - 1)
            db.session.commit()

        # If credentials are not configured or SMS is disabled, log as SIMULATED
        if not creds['is_enabled'] or not creds['account_sid'] or not creds['auth_token'] or not creds['from_number']:
            notif.sent_status = 'SIMULATED'
            notif.sent_at = datetime.utcnow()
            notif.error_details = 'Simulated delivery (Twilio credentials not configured or disabled)'
            db.session.commit()
            return {'success': True, 'simulated': True, 'notification_id': notif.id}

        # Dispatch via Twilio REST API
        url = f"https://api.twilio.com/2010-04-01/Accounts/{creds['account_sid']}/Messages.json"
        data = {
            'To': formatted_phone,
            'From': creds['from_number'],
            'Body': message
        }

        try:
            resp = requests.post(url, data=data, auth=(creds['account_sid'], creds['auth_token']), timeout=10)
            if resp.status_code in (200, 201):
                res_json = resp.json()
                notif.sent_status = 'SENT'
                notif.sent_at = datetime.utcnow()
                notif.error_details = f"Twilio SID: {res_json.get('sid', '')}"
                db.session.commit()
                return {'success': True, 'sid': res_json.get('sid'), 'notification_id': notif.id}
            else:
                err_msg = f"Twilio error [{resp.status_code}]: {resp.text}"
                notif.sent_status = 'FAILED'
                notif.error_details = err_msg
                db.session.commit()
                return {'success': False, 'error': err_msg, 'notification_id': notif.id}
        except requests.RequestException as e:
            err_msg = f"Network error contacting Twilio: {str(e)}"
            notif.sent_status = 'FAILED'
            notif.error_details = err_msg
            db.session.commit()
            return {'success': False, 'error': err_msg, 'notification_id': notif.id}

    @classmethod
    def send_payment_sms(cls, payment):
        """
        Triggered after a successful verified payment.
        Sends SMS to:
          1. Tenant: Payment receipt confirmation with remaining balance.
          2. Landlord: Notification of revenue received.
        Personalizes sender header with organization name.
        """
        tenant = payment.tenant
        unit = payment.rental_unit
        prop = payment.property
        landlord = prop.landlord if prop else None
        org = prop.organization if prop and hasattr(prop, 'organization') else None
        org_name = org.name if org else "Property Management"

        from app.services.tenant_service import TenantService
        summary = TenantService.get_tenant_financial_summary(tenant.id) if tenant else {'outstanding_cents': 0}
        from app.utils.currency import format_currency
        balance_str = format_currency(summary['outstanding_cents'])

        # 1. SMS to Tenant
        if tenant and tenant.phone:
            tenant_msg = (
                f"[{org_name}] Dear {tenant.first_name}, payment of {payment.amount_display} for Unit {unit.unit_number} ({prop.name}) "
                f"has been confirmed. Receipt: {payment.receipt_number}. Remaining Balance: {balance_str}. Thank you!"
            )
            cls.send_sms(
                to_phone=tenant.phone,
                message=tenant_msg,
                notification_type='RENT_PAYMENT_CONFIRMED',
                landlord_id=landlord.id if landlord else None,
                organization_id=org.id if org else None
            )

        # 2. SMS to Landlord
        if landlord and landlord.phone:
            landlord_msg = (
                f"[{org_name}] Payment Alert: Rent {payment.amount_display} received from {tenant.full_name} for Unit {unit.unit_number} "
                f"({prop.name}). Ref: {payment.transaction_reference or payment.receipt_number}."
            )
            cls.send_sms(
                to_phone=landlord.phone,
                message=landlord_msg,
                notification_type='RENT_PAYMENT_CONFIRMED',
                landlord_id=landlord.id,
                organization_id=org.id if org else None
            )

    @classmethod
    def send_booking_sms(cls, booking):
        """
        Dispatches booking confirmation SMS to prospective tenant/guest.
        Personalizes sender header with organization name.
        """
        if not booking.prospective_phone:
            return
        unit = booking.rental_unit
        prop = unit.property if unit else None
        org = prop.organization if prop and hasattr(prop, 'organization') else None
        org_name = org.name if org else "Property Management"

        msg = (
            f"[{org_name}] Dear {booking.prospective_name}, your reservation for Unit {unit.unit_number} at {prop.name} "
            f"has been received! Ref: {booking.booking_reference}. Move-in date: {booking.expected_move_in_date}. "
            f"Our team will contact you shortly."
        )
        cls.send_sms(
            to_phone=booking.prospective_phone,
            message=msg,
            notification_type='BOOKING_CREATED',
            landlord_id=prop.landlord_id if prop else None,
            organization_id=org.id if org else None
        )
