import os
import sys
import hashlib

# Python 3.8 32-bit compatibility: mask numpy so openpyxl uses native numbers without 0xc0000008 ctypes crash
if 'numpy' not in sys.modules:
    sys.modules['numpy'] = None

# Python 3.8 compatibility patch for ReportLab md5 usedforsecurity
_orig_md5 = hashlib.md5
def _safe_md5(*args, **kwargs):
    kwargs.pop('usedforsecurity', None)
    return _orig_md5(*args, **kwargs)
hashlib.md5 = _safe_md5

from flask import Flask
from config import config_by_name
from app.extensions import db, migrate, login_manager, csrf
from app.utils.currency import format_currency, from_cents

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')
        
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_by_name[config_name])
    
    # Ensure instance and upload directories exist
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except Exception:
        pass
    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    except Exception:
        pass
    try:
        os.makedirs(os.path.join(app.root_path, '..', 'backups'), exist_ok=True)
    except Exception:
        pass
    
    # Initialize Flask extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Register Jinja context processors & filters
    from app.services.personalization_service import PersonalizationService
    
    @app.context_processor
    def inject_personalization():
        try:
            settings = PersonalizationService.get_all_settings()
        except Exception:
            settings = {}
        return dict(
            sys_settings=settings,
            app_name=settings.get('app_name', 'Rental Property Manager'),
            business_name=settings.get('business_name', 'Property Management System'),
            logo_url=settings.get('logo_url', '/static/img/logo.png'),
            currency=settings.get('currency', 'KES')
        )
        
    @app.context_processor
    def inject_globals():
        from datetime import date, datetime
        from flask_login import current_user
        pending_inquiry_count = 0
        try:
            if current_user.is_authenticated:
                from app.models.booking import Booking
                pending_inquiry_count = Booking.query.filter_by(status='PENDING').count()
        except Exception:
            pass
        return dict(date=date, datetime=datetime, now=datetime.utcnow(),
                    pending_inquiry_count=pending_inquiry_count)
        
    @app.template_filter('currency')
    def currency_filter(cents, currency=None):
        if currency is None:
            currency = PersonalizationService.get_setting('currency', 'KES')
        return format_currency(cents, currency)
        
    @app.template_filter('from_cents')
    def from_cents_filter(cents):
        return from_cents(cents)

    # Register blueprints
    from app.routes.auth_bp import auth_bp
    from app.routes.dashboard_bp import dashboard_bp
    from app.routes.settings_bp import settings_bp
    from app.routes.users_bp import users_bp
    from app.routes.properties_bp import properties_bp
    from app.routes.tenants_bp import tenants_bp
    from app.routes.bookings_bp import bookings_bp
    from app.routes.billing_bp import billing_bp
    from app.routes.reports_bp import reports_bp
    from app.routes.mpesa_bp import mpesa_bp
    from app.routes.banking_bp import banking_bp
    from app.routes.maintenance_bp import maintenance_bp
    from app.routes.leases_bp import leases_bp
    from app.routes.public_bp import public_bp
    from app.routes.communication_bp import communication_bp
    from app.routes.utilities_bp import utilities_bp
    from app.routes.tenant_portal_bp import tenant_portal_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(properties_bp)
    app.register_blueprint(tenants_bp)
    app.register_blueprint(bookings_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(mpesa_bp)
    app.register_blueprint(banking_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(leases_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(communication_bp)
    app.register_blueprint(utilities_bp)
    app.register_blueprint(tenant_portal_bp)
    
    return app
