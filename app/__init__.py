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
        from flask_login import current_user
        org_name = current_user.organization.name if (current_user and current_user.is_authenticated and getattr(current_user, 'organization', None)) else None
        return dict(
            sys_settings=settings,
            app_name=settings.get('app_name', 'Rental Property Manager'),
            business_name=settings.get('business_name') or org_name or 'Property Management System',
            logo_url=settings.get('logo_url', '/static/img/logo.png'),
            currency=settings.get('currency', 'KES')
        )
        
    @app.context_processor
    def inject_globals():
        from datetime import date, datetime
        from flask import session as _sess, request as _req
        from flask_login import current_user
        pending_inquiry_count = 0
        try:
            if current_user.is_authenticated:
                from app.models.booking import Booking
                from app.utils.decorators import multi_tenant_scoped
                pending_inquiry_count = multi_tenant_scoped(
                    Booking.query.filter_by(status='PENDING'),
                    Booking
                ).count()
        except Exception:
            pass

        # Resolve Dual-Mode Workspace: 'RENTALS' vs 'AIRBNB'
        current_mode = 'RENTALS'
        endpoint = _req.endpoint or ''
        if endpoint.startswith('hospitality.'):
            current_mode = 'AIRBNB'
            _sess['active_mode'] = 'AIRBNB'
        else:
            org = getattr(current_user, 'active_organization', None) if (current_user and current_user.is_authenticated) else None
            can_rent = (not org or org.can_access_rental_module() or current_user.is_superadmin()) if (current_user and current_user.is_authenticated) else True
            can_airbnb = (not org or org.can_access_hospitality_module() or current_user.is_superadmin()) if (current_user and current_user.is_authenticated) else True

            if can_airbnb and not can_rent:
                current_mode = 'AIRBNB'
            elif can_rent and not can_airbnb:
                current_mode = 'RENTALS'
            else:
                current_mode = _sess.get('active_mode', 'RENTALS')

        return dict(
            date=date,
            datetime=datetime,
            now=datetime.utcnow(),
            pending_inquiry_count=pending_inquiry_count,
            current_mode=current_mode
        )

    # Subdomain-per-tenant external website resolution middleware
    @app.before_request
    def resolve_subdomain_routing():
        from flask import request as req
        if req.path.startswith(('/static/', '/site/', '/auth/', '/portal/', '/mpesa/')):
            return None
        host_parts = req.host.split(':')[0].lower().split('.')
        if len(host_parts) >= 2:
            subdomain = host_parts[0]
            if subdomain not in ('www', 'app', 'portal', 'api', 'admin', 'localhost', '127'):
                from app.routes.public_bp import _find_organization_by_slug_or_code
                org = _find_organization_by_slug_or_code(subdomain)
                if org and req.path == '/':
                    from app.routes.public_bp import tenant_site
                    return tenant_site(org.slug)
        return None

    # Subscription suspension enforcement middleware
    @app.before_request
    def enforce_subscription_status():
        from flask import request as req, redirect, url_for, flash
        from flask_login import current_user as cu
        # Skip static files, login/logout, auth routes, portal, public, and suspension page
        exempted_prefixes = ('/static/', '/auth/', '/portal/', '/public/', '/site/', '/mpesa/callback')
        exempted_endpoints = ('auth.login', 'auth.logout', 'platform.organizations',
                              'platform.update_organization_status', 'platform.update_organization_subscription',
                              'platform.create_organization', 'platform.analytics')
        if any(req.path.startswith(p) for p in exempted_prefixes):
            return None
        if req.endpoint in exempted_endpoints:
            return None
        if not cu or not cu.is_authenticated:
            return None
        if cu.is_superadmin():
            return None
        try:
            org = getattr(cu, 'active_organization', None)
            if org and org.subscription_expires_at:
                from datetime import datetime as _dt
                if org.subscription_expires_at < _dt.utcnow():
                    if org.subscription_status != 'EXPIRED':
                        org.subscription_status = 'EXPIRED'
                        db.session.commit()
                    if req.endpoint not in ('auth.login', 'auth.logout'):
                        flash(
                            'Your 14-day trial / subscription period has ended. '
                            'Please contact support or upgrade your plan to restore access.',
                            'warning'
                        )
                        return redirect(url_for('auth.login'))

            if org and (org.subscription_status in ('SUSPENDED', 'EXPIRED') or not org.is_active):
                if req.endpoint not in ('auth.login', 'auth.logout'):
                    from flask_login import logout_user
                    reason = getattr(org, 'suspension_reason', None) or 'Payment of monthly system usage premium is pending.'
                    flash(
                        f"Access Suspended: System access for '{org.name}' is currently deactivated. "
                        f"Reason: {reason}. Please settle your premium or contact Angaza platform support.",
                        'danger'
                    )
                    logout_user()
                    return redirect(url_for('auth.login'))
        except Exception:
            pass
        return None
        
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
    from app.routes.hospitality_bp import hospitality_bp
    from app.routes.platform_bp import platform_bp
    
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
    app.register_blueprint(hospitality_bp)
    app.register_blueprint(platform_bp)
    
    return app
