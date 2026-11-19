from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models.user import User, Role, Landlord
from app.models.organization import Organization
from app.services.audit_service import AuditService

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        org_code = request.form.get('org_code', '').strip().upper()
        username_or_email = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        # Support slash or at notation e.g. "SARAH/admin" or "admin@SARAH"
        if not org_code and ('/' in username_or_email or ('@' in username_or_email and not ('.' in username_or_email.split('@')[-1]))):
            if '/' in username_or_email:
                parts = username_or_email.split('/', 1)
                org_code = parts[0].strip().upper()
                username_or_email = parts[1].strip()
            elif '@' in username_or_email:
                parts = username_or_email.split('@', 1)
                username_or_email = parts[0].strip()
                org_code = parts[1].strip().upper()

        user = None
        if org_code and org_code != 'SYSTEM':
            # Multi-Tenant scoped login for specific business / organization
            org = Organization.query.filter(
                (Organization.org_code == org_code) |
                (Organization.slug == org_code.lower()) |
                (Organization.name.ilike(f"%{org_code}%"))
            ).first()

            if not org:
                flash(f"Business Code '{org_code}' was not found. Please verify with your system administrator.", 'danger')
                return render_template('auth/login.html')

            # 1. Look for user belonging to this organization
            user = User.query.filter(
                User.organization_id == org.id,
                (User.username == username_or_email) |
                (User.email == username_or_email) |
                (User.username == f"{org_code.lower()}_{username_or_email}")
            ).first()

            # 2. If user entered generic 'admin' or 'manager', find the organization's manager/admin
            if not user and username_or_email.lower() in ('admin', 'manager', 'owner'):
                user = User.query.filter(
                    User.organization_id == org.id,
                    User.is_active == True
                ).order_by(User.id.asc()).first()
        else:
            # Global / direct login (Superadmin or direct unique username/email)
            user = User.query.filter(
                (User.username == username_or_email) | (User.email == username_or_email)
            ).first()

            # If username is generic 'admin' and no business code given, default to Superadmin
            if not user and username_or_email.lower() == 'admin':
                user = User.query.filter(User.username == 'admin').first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact the administrator.', 'danger')
                return render_template('auth/login.html')

            # Check Organization subscription / payment active status
            if user.organization and not user.is_superadmin():
                org = user.organization
                if org.is_suspended or org.subscription_status in ('SUSPENDED', 'EXPIRED') or not org.is_active:
                    reason = getattr(org, 'suspension_reason', None) or 'Payment of monthly system usage premium is pending.'
                    flash(
                        f"Access Suspended: System access for '{org.name}' is currently deactivated. "
                        f"Reason: {reason}. "
                        "Please settle your premium or contact platform administration to restore access.",
                        'danger'
                    )
                    return render_template('auth/login.html')
                
            login_user(user, remember=remember)
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            
            AuditService.log('LOGIN', 'User', user.id, new_values={'username': user.username, 'org_code': org_code or 'GLOBAL'})
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
    session.pop('impersonator_id', None)
    AuditService.log('LOGOUT', 'User', current_user.id, old_values={'username': current_user.username})
    logout_user()
    flash('You have been securely logged out.', 'info')
    return redirect(url_for('auth.login'))


# ─── Public Self-Onboarding (14-Day Free Trial) ──────────────────────────────

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    Public self-onboarding portal for external landlords & property management businesses.
    Automatically provisions a logical Organization tenant with a 14-day free trial
    and 50 complimentary SMS credits.
    """
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        org_name = request.form.get('organization_name', '').strip()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        suite_tier = request.form.get('subscription_tier', 'COMBINED_SUITE')

        if not org_name or not email or not password or not full_name:
            flash('Organization name, full name, work email, and password are required.', 'danger')
            return render_template('auth/register.html')

        # Check existing user/email
        if User.query.filter((User.email == email) | (User.username == email)).first():
            flash('An account with this email address already exists. Please log in instead.', 'warning')
            return redirect(url_for('auth.login'))

        slug = org_name.lower().replace(' ', '-').replace("'", '')[:50]
        # Ensure unique slug
        base_slug = slug
        counter = 1
        while Organization.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        # 1. Provision customer Organization tenant with 14-day trial & 50 SMS credits
        trial_expiry = datetime.utcnow() + timedelta(days=14)
        org = Organization(
            name=org_name,
            slug=slug,
            contact_email=email,
            contact_phone=phone if phone else None,
            subscription_tier=suite_tier,
            subscription_status='TRIAL',
            subscription_expires_at=trial_expiry,
            max_properties=25,
            max_units=100,
            max_users=5,
            sms_credits=50
        )
        db.session.add(org)
        db.session.flush()

        # 2. Create primary Property Manager role user
        manager_role = Role.query.filter_by(name='PROPERTY_MANAGER').first()
        if not manager_role:
            manager_role = Role.query.filter_by(name='SUPERADMIN').first()

        user = User(
            username=email.split('@')[0],
            email=email,
            phone=phone if phone else None,
            full_name=full_name,
            organization_id=org.id,
            role=manager_role,
            is_active=True
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        # 3. Create default Landlord record for immediate property onboarding
        landlord = Landlord(
            name=org_name,
            contact_person=full_name,
            email=email,
            phone=phone if phone else '+254700000000',
            is_active=True
        )
        db.session.add(landlord)
        db.session.commit()

        # Auto-login to system
        login_user(user)
        AuditService.log('SELF_ONBOARDING_TRIAL', 'Organization', org.id, new_values={'name': org_name, 'tier': suite_tier, 'expires_at': str(trial_expiry)})

        flash(
            f"🎉 Welcome to Angaza, {full_name}! Your 14-day complimentary trial for '{org_name}' "
            f"is now active with 50 free SMS credits. Explore your dedicated management suite!",
            'success'
        )
        return redirect(url_for('dashboard.index'))

    return render_template('auth/register.html')


# ─── Super Admin User Impersonation ──────────────────────────────────────────

@auth_bp.route('/impersonate/<int:user_id>')
@login_required
def impersonate(user_id):
    """
    Superadmin capability: impersonate any junior user, manager, or landlord
    to inspect their dashboard and resolve issues directly on their behalf.
    """
    if not current_user.is_superadmin():
        flash('Unauthorized: Platform Superadmin privileges required to impersonate accounts.', 'danger')
        return redirect(url_for('dashboard.index'))

    target_user = db.session.get(User, user_id)
    if not target_user:
        flash('Target account not found.', 'danger')
        return redirect(url_for('users.index'))

    if target_user.id == current_user.id:
        flash('You cannot impersonate your own active superadmin session.', 'warning')
        return redirect(url_for('users.index'))

    # Store real superadmin ID in session before switching
    session['impersonator_id'] = current_user.id
    target_name = target_user.full_name
    target_role = target_user.role.display_name if target_user.role else 'Staff'

    login_user(target_user)
    AuditService.log('IMPERSONATE_USER', 'User', target_user.id, new_values={'target': target_name, 'role': target_role})

    flash(f"⚡ Switched into account: {target_name} ({target_role}). You are now operating as this user.", 'info')
    return redirect(url_for('dashboard.index'))


@auth_bp.route('/stop-impersonation')
@login_required
def stop_impersonation():
    """Exit impersonation mode and return to Superadmin session."""
    impersonator_id = session.pop('impersonator_id', None)
    if not impersonator_id:
        return redirect(url_for('dashboard.index'))

    admin_user = db.session.get(User, impersonator_id)
    if admin_user and admin_user.is_superadmin():
        login_user(admin_user)
        AuditService.log('STOP_IMPERSONATION', 'User', admin_user.id)
        flash('✅ Returned to your Platform Superadmin session.', 'success')
        return redirect(url_for('platform.organizations'))

    return redirect(url_for('auth.logout'))


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
        'LANDLORD': ('Property Owner / Landlord', [
            perm_map[c] for c in [
                'properties.view', 'properties.manage',
                'tenants.view',
                'bookings.view', 'bookings.manage',
                'billing.view',
                'reports.view', 'reports.export',
                'maintenance.view',
                'leases.view',
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
        admin_user.set_password('admin123')
        db.session.add(admin_user)
    
    # Initialize default system settings
    PersonalizationService.initialize_default_settings()
    
    db.session.commit()
    print("[Seed] Initial data seeded successfully.")

