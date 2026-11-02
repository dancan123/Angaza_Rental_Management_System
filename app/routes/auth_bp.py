from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models.user import User
from app.services.audit_service import AuditService

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        username_or_email = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact the administrator.', 'danger')
                return render_template('auth/login.html')
                
            login_user(user, remember=remember)
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            
            AuditService.log('LOGIN', 'User', user.id, new_values={'username': user.username})
            flash(f'Welcome back, {user.full_name}!', 'success')
            
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('dashboard.index'))
        else:
            flash('Invalid username/email or password.', 'danger')
            
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    AuditService.log('LOGOUT', 'User', current_user.id, old_values={'username': current_user.username})
    logout_user()
    flash('You have been securely logged out.', 'info')
    return redirect(url_for('auth.login'))


def seed_initial_data():
    """Seed initial roles, permissions, and admin user. Safe to call multiple times."""
    from app.models.user import Role, Permission, User
    from app.services.personalization_service import PersonalizationService
    
    # All permissions the system uses
    all_permissions = [
        ('properties.view', 'properties', 'View properties and units'),
        ('properties.manage', 'properties', 'Create/edit/delete properties and units'),
        ('tenants.view', 'tenants', 'View tenant records'),
        ('tenants.manage', 'tenants', 'Create/edit/move-out tenants'),
        ('bookings.view', 'bookings', 'View bookings/reservations'),
        ('bookings.manage', 'bookings', 'Create/cancel/convert bookings'),
        ('billing.view', 'billing', 'View rent charges and payments'),
        ('billing.manage', 'billing', 'Record payments, generate charges, issue receipts'),
        ('reports.view', 'reports', 'View financial reports'),
        ('reports.export', 'reports', 'Export reports to PDF/Excel'),
        ('mpesa.manage', 'mpesa', 'Configure M-Pesa integration'),
        ('banking.manage', 'banking', 'Import bank statements and reconcile'),
        ('maintenance.view', 'maintenance', 'View maintenance requests and expenses'),
        ('maintenance.manage', 'maintenance', 'Create/resolve maintenance requests and log expenses'),
        ('leases.view', 'leases', 'View lease agreements'),
        ('leases.manage', 'leases', 'Create/terminate lease agreements'),
        ('users.manage', 'admin', 'Manage system users and roles'),
        ('settings.manage', 'admin', 'Manage system settings and personalization'),
    ]
    
    # Ensure all permissions exist
    perm_map = {}
    for code, module, desc in all_permissions:
        perm = Permission.query.filter_by(code=code).first()
        if not perm:
            perm = Permission(code=code, module=module, description=desc)
            db.session.add(perm)
        perm_map[code] = perm
    db.session.flush()
    
    # Create/update roles
    roles_config = {
        'SUPERADMIN': ('Super Administrator', list(perm_map.values())),
        'PROPERTY_MANAGER': ('Property Manager', [
            perm_map[c] for c in [
                'properties.view', 'properties.manage',
                'tenants.view', 'tenants.manage',
                'bookings.view', 'bookings.manage',
                'billing.view', 'billing.manage',
                'reports.view', 'reports.export',
                'maintenance.view', 'maintenance.manage',
                'leases.view', 'leases.manage',
            ]
        ]),
        'CARETAKER': ('Caretaker', [
            perm_map[c] for c in [
                'properties.view', 'tenants.view',
                'bookings.view', 'billing.view',
                'maintenance.view', 'maintenance.manage',
            ]
        ]),
        'ACCOUNTANT': ('Accountant', [
            perm_map[c] for c in [
                'billing.view', 'billing.manage',
                'reports.view', 'reports.export',
                'banking.manage',
            ]
        ]),
        'VIEWER': ('Read-Only Viewer', [
            perm_map[c] for c in [
                'properties.view', 'tenants.view',
                'bookings.view', 'billing.view',
                'reports.view', 'maintenance.view',
                'leases.view',
            ]
        ]),
    }
    
    role_map = {}
    for role_name, (display_name, perms) in roles_config.items():
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name, display_name=display_name)
            db.session.add(role)
        role.display_name = display_name
        role.permissions = perms
        role_map[role_name] = role
    db.session.flush()
    
    # Create default admin user if none exists
    if not User.query.filter_by(username='admin').first():
        admin_user = User(
            username='admin',
            email='admin@rentalsystem.local',
            full_name='System Administrator',
            role=role_map['SUPERADMIN'],
            is_active=True
        )
        admin_user.set_password('AdminPassword2026!')
        db.session.add(admin_user)
    
    # Initialize default system settings
    PersonalizationService.initialize_default_settings()
    
    db.session.commit()
    print("[Seed] Initial data seeded successfully.")

