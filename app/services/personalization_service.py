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
    'default_payment_instructions': 'Pay via M-Pesa Paybill 247247, Account: [Unit Number] or Bank: Equity Bank A/C 0123456789'
}

class PersonalizationService:
    @staticmethod
    def get_setting(key: str, default: str = None) -> str:
        try:
            setting = SystemSetting.query.filter_by(setting_key=key).first()
            if setting and setting.setting_value is not None:
                return setting.setting_value
        except Exception:
            pass
        return default if default is not None else DEFAULT_SETTINGS.get(key, '')

    @staticmethod
    def get_all_settings() -> dict:
        settings_dict = dict(DEFAULT_SETTINGS)
        try:
            db_settings = SystemSetting.query.all()
            for s in db_settings:
                if s.setting_value is not None:
                    settings_dict[s.setting_key] = s.setting_value
        except Exception:
            pass
        return settings_dict

    @staticmethod
    def update_settings(updates: dict):
        for key, value in updates.items():
            setting = SystemSetting.query.filter_by(setting_key=key).first()
            if not setting:
                setting = SystemSetting(setting_key=key, setting_value=str(value), is_public=True)
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

