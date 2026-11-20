from app.models.system import SystemSetting
from app.extensions import db

DEFAULT_SETTINGS = {
    'app_name': 'PrimeRent Property Manager',
    'business_name': 'Prime Property Management Ltd',
    'logo_url': '/static/img/logo.png',
    'business_address': 'P.O. Box 12345-00100, Nairobi, Kenya',
    'business_phone': '+254 700 000 000',
    'business_email': 'info@primerent.co.ke',
    'landlord_name': 'Property Management Office',
    'currency': 'KES',
    'business_reg_no': 'CPR/2026/012345',
    'tax_pin': 'P051234567Z',
    'receipt_footer': 'Thank you for choosing us. Rent is payable on or before the 5th of every month.',
    'theme_primary_color': '#1a56db',      # Modern royal blue
    'theme_secondary_color': '#0e9f6e',    # Emerald accent
    'theme_dark_mode': 'false',
    'default_due_day': '5',
    'grace_period_days': '5',
    'late_fee_percentage': '5',
    'financial_year_start': '1',           # January
    'default_payment_instructions': 'Pay via M-Pesa Paybill 247247, Account: [Unit Number] or Bank: Equity Bank A/C 0123456789',
    
    # Airbnb & Short-Stay Hospitality Configurations
    'airbnb_business_name': '',
    'airbnb_checkin_time': '14:00',
    'airbnb_checkout_time': '10:00',
    'airbnb_default_cleaning_fee': '1500',
    'airbnb_tourism_levy_percentage': '2',
    'airbnb_cancellation_policy': 'FLEXIBLE_24H',
    'airbnb_house_rules': '1. No smoking inside premises.\n2. Quiet hours from 10:00 PM.\n3. Valid Government ID required upon check-in.\n4. Turn off AC and lighting when vacating.',
    'airbnb_wifi_ssid': '',
    'airbnb_wifi_password': '',
    'airbnb_guest_welcome_note': 'Welcome to your short-stay suite! We wish you a peaceful, relaxing, and memorable stay.',
    'airbnb_require_guest_id': 'true',
    'airbnb_mpesa_instructions': 'Pay via Safaricom Buy Goods Till or M-Pesa Paybill. Quote your Reservation Code.'
}

class PersonalizationService:
    @staticmethod
    def _resolve_org_id(organization_id=None):
        if organization_id is not None:
            return organization_id
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated and not current_user.is_superadmin():
                return getattr(current_user, 'organization_id', None)
        except Exception:
            pass
        return None

    @staticmethod
    def get_setting(key: str, default: str = None, organization_id=None) -> str:
        org_id = PersonalizationService._resolve_org_id(organization_id)
        try:
            # 1. Look for organization-specific setting
            if org_id:
                org_setting = SystemSetting.query.filter_by(setting_key=key, organization_id=org_id).first()
                if org_setting and org_setting.setting_value is not None:
                    return org_setting.setting_value

            # 2. Look for global platform setting (organization_id IS NULL)
            setting = SystemSetting.query.filter_by(setting_key=key, organization_id=None).first()
            if setting and setting.setting_value is not None:
                return setting.setting_value
        except Exception:
            pass
        return default if default is not None else DEFAULT_SETTINGS.get(key, '')

    @staticmethod
    def get_all_settings(organization_id=None) -> dict:
        settings_dict = dict(DEFAULT_SETTINGS)
        org_id = PersonalizationService._resolve_org_id(organization_id)
        try:
            # 1. Load global settings
            db_settings = SystemSetting.query.filter_by(organization_id=None).all()
            for s in db_settings:
                if s.setting_value is not None:
                    settings_dict[s.setting_key] = s.setting_value

            # 2. Overlay with organization-specific overrides
            if org_id:
                org_settings = SystemSetting.query.filter_by(organization_id=org_id).all()
                for s in org_settings:
                    if s.setting_value is not None:
                        settings_dict[s.setting_key] = s.setting_value
        except Exception:
            pass
        return settings_dict

    @staticmethod
    def update_settings(updates: dict, organization_id=None):
        org_id = PersonalizationService._resolve_org_id(organization_id)
        for key, value in updates.items():
            setting = SystemSetting.query.filter_by(setting_key=key, organization_id=org_id).first()
            if not setting:
                setting = SystemSetting(setting_key=key, setting_value=str(value), organization_id=org_id, is_public=True)
                db.session.add(setting)
            else:
                setting.setting_value = str(value)
        db.session.commit()

    @staticmethod
    def initialize_default_settings():
        for key, val in DEFAULT_SETTINGS.items():
            exists = SystemSetting.query.filter_by(setting_key=key).first()
            if not exists:
                setting = SystemSetting(
                    setting_key=key,
                    setting_value=val,
                    description=f"System configuration for {key}",
                    is_public=True
                )
                db.session.add(setting)
        db.session.commit()

