from typing import Any, cast
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models.organization import Organization
from app.models.property import Property, RentalUnit


platform_bp = Blueprint('platform', __name__, url_prefix='/platform')


def superadmin_only():
    user = cast(Any, current_user)
    if not user.is_authenticated or not user.is_superadmin():
        flash('Unauthorized: Platform Super Admin privileges required.', 'danger')
        return False
    return True

@platform_bp.route('/organizations')
@login_required
def organizations():
    if not superadmin_only():
        return redirect(url_for('dashboard.index'))

    status = request.args.get('status')
    tier = request.args.get('tier')
    search = request.args.get('q', '').strip()

    query = Organization.query
    if status:
        query = query.filter_by(subscription_status=status)
    if tier:
        query = query.filter_by(subscription_tier=tier)
    if search:
        query = query.filter(
            (Organization.name.ilike(f"%{search}%")) |
            (Organization.slug.ilike(f"%{search}%")) |
            (Organization.contact_email.ilike(f"%{search}%")) |
            (Organization.contact_phone.ilike(f"%{search}%"))
        )

    all_orgs = query.order_by(Organization.created_at.desc()).all()

    # Platform Analytics Metrics
    total_orgs = Organization.query.count()
    active_orgs = Organization.query.filter_by(subscription_status='ACTIVE').count()
    total_units_managed = RentalUnit.query.count()
    total_properties_managed = Property.query.count()

    return render_template(
        'platform/organizations.html',
        organizations=all_orgs,
        total_orgs=total_orgs,
        active_orgs=active_orgs,
        total_units_managed=total_units_managed,
        total_properties_managed=total_properties_managed,
        status_filter=status,
        tier_filter=tier,
        search=search
    )

@platform_bp.route('/organizations/create', methods=['POST'])
@login_required
def create_organization():
    if not superadmin_only():
        return redirect(url_for('dashboard.index'))

    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip().lower().replace(' ', '-')
    contact_email = request.form.get('contact_email', '').strip().lower()
    contact_phone = request.form.get('contact_phone', '').strip()
    tax_pin = request.form.get('tax_pin', '').strip().upper()
    tier = request.form.get('subscription_tier', 'COMBINED_SUITE')
    max_props = request.form.get('max_properties', type=int) or 50
    max_units = request.form.get('max_units', type=int) or 250
    max_users = request.form.get('max_users', type=int) or 15

    # Checkpoint module toggles
    if 'enable_rentals' in request.form or 'enable_hospitality' in request.form:
        enable_rentals = request.form.get('enable_rentals') in ('1', 'true', 'on', 'yes')
        enable_hospitality = request.form.get('enable_hospitality') in ('1', 'true', 'on', 'yes')
        if not enable_rentals and not enable_hospitality:
            enable_rentals = True
        if enable_rentals and enable_hospitality:
            tier = 'COMBINED_SUITE'
        elif enable_rentals:
            tier = 'RENTAL_STANDARD'
        else:
            tier = 'HOSPITALITY_STANDARD'
    elif tier == 'RENTAL_STANDARD':
        enable_rentals = True
        enable_hospitality = False
    elif tier == 'HOSPITALITY_STANDARD':
        enable_rentals = False
        enable_hospitality = True
    else:
        enable_rentals = True
        enable_hospitality = True

    if not name or not slug:
        flash('Organization name and unique slug are required.', 'danger')
        return redirect(url_for('platform.organizations'))

    existing = Organization.query.filter((Organization.name == name) | (Organization.slug == slug)).first()
    if existing:
        flash(f"An organization with name '{name}' or slug '{slug}' already exists.", 'danger')
        return redirect(url_for('platform.organizations'))

    org = Organization(
        name=name,
        slug=slug,
        contact_email=contact_email if contact_email else None,
        contact_phone=contact_phone if contact_phone else None,
        tax_pin=tax_pin if tax_pin else None,
        subscription_tier=tier,
        subscription_status='ACTIVE',
        max_properties=max_props,
        max_units=max_units,
        max_users=max_users,
        enable_rentals=enable_rentals,
        enable_hospitality=enable_hospitality
    )
    db.session.add(org)
    db.session.commit()

    flash(f"Organization '{org.name}' ({tier}) registered successfully.", 'success')
    return redirect(url_for('platform.organizations'))

@platform_bp.route('/organizations/<int:org_id>/status', methods=['POST'])
@login_required
def update_organization_status(org_id):
    if not superadmin_only():
        return redirect(url_for('dashboard.index'))

    org = db.session.get(Organization, org_id)
    if not org:
        from flask import abort; abort(404)

    new_status = request.form.get('subscription_status', 'ACTIVE')
    org.subscription_status = new_status
    org.is_active = (new_status in ['ACTIVE', 'TRIAL'])
    db.session.commit()

    flash(f"Organization '{org.name}' status updated to {new_status}.", 'success')
    return redirect(url_for('platform.organizations'))

@platform_bp.route('/organizations/<int:org_id>/subscription', methods=['POST'])
@login_required
def update_organization_subscription(org_id):
    if not superadmin_only():
        return redirect(url_for('dashboard.index'))

    org = db.session.get(Organization, org_id)
    if not org:
        from flask import abort; abort(404)

    tier = request.form.get('subscription_tier', org.subscription_tier)
    max_props = request.form.get('max_properties', type=int) or org.max_properties
    max_units = request.form.get('max_units', type=int) or org.max_units
    max_users = request.form.get('max_users', type=int) or org.max_users

    # Checkpoint toggles
    if 'enable_rentals' in request.form or 'enable_hospitality' in request.form:
        enable_rentals = request.form.get('enable_rentals') in ('1', 'true', 'on', 'yes')
        enable_hospitality = request.form.get('enable_hospitality') in ('1', 'true', 'on', 'yes')
        org.enable_rentals = enable_rentals
        org.enable_hospitality = enable_hospitality
        if enable_rentals and enable_hospitality:
            tier = 'COMBINED_SUITE'
        elif enable_rentals and not enable_hospitality:
            tier = 'RENTAL_STANDARD'
        elif enable_hospitality and not enable_rentals:
            tier = 'HOSPITALITY_STANDARD'
        else:
            tier = 'RENTAL_STANDARD'
            org.enable_rentals = True
    elif tier:
        if tier == 'RENTAL_STANDARD':
            org.enable_rentals = True
            org.enable_hospitality = False
        elif tier == 'HOSPITALITY_STANDARD':
            org.enable_rentals = False
            org.enable_hospitality = True
        else:
            org.enable_rentals = True
            org.enable_hospitality = True

    org.subscription_tier = tier
    org.max_properties = max_props
    org.max_units = max_units
    org.max_users = max_users
    db.session.commit()

    flash(f"Premises '{org.name}' checkpoints updated: Rentals={'ON' if org.enable_rentals else 'OFF'}, Airbnb={'ON' if org.enable_hospitality else 'OFF'} ({tier}).", 'success')
    return redirect(url_for('platform.organizations'))


@platform_bp.route('/organizations/<int:org_id>/toggle-module', methods=['POST'])
@login_required
def toggle_organization_module(org_id):
    """1-click module checkpoint toggle for superadmin."""
    if not superadmin_only():
        return redirect(url_for('dashboard.index'))

    org = db.session.get(Organization, org_id)
    if not org:
        from flask import abort; abort(404)

    mod = request.form.get('module')  # 'rentals' or 'hospitality'
    if mod == 'rentals':
        org.enable_rentals = not org.enable_rentals
        if not org.enable_rentals and not org.enable_hospitality:
            # Ensure at least one module is always enabled
            org.enable_hospitality = True
    elif mod == 'hospitality':
        org.enable_hospitality = not org.enable_hospitality
        if not org.enable_rentals and not org.enable_hospitality:
            # Ensure at least one module is always enabled
            org.enable_rentals = True

    # Synchronize subscription_tier with the active modules
    if org.enable_rentals and org.enable_hospitality:
        org.subscription_tier = 'COMBINED_SUITE'
    elif org.enable_rentals and not org.enable_hospitality:
        org.subscription_tier = 'RENTAL_STANDARD'
    elif org.enable_hospitality and not org.enable_rentals:
        org.subscription_tier = 'HOSPITALITY_STANDARD'

    db.session.commit()
    flash(f"Premises '{org.name}' checkpoint changed: Rentals={'ON' if org.enable_rentals else 'OFF'}, Airbnb={'ON' if org.enable_hospitality else 'OFF'}.", "success")
    return redirect(request.referrer or url_for('platform.organizations'))


@platform_bp.route('/organizations/<int:org_id>/add-sms', methods=['POST'])
@login_required
def add_organization_sms(org_id):
    """Sell / allocate SMS credits to a customer organization."""
    if not superadmin_only():
        return redirect(url_for('dashboard.index'))
    org = db.session.get(Organization, org_id)
    if not org:
        from flask import abort; abort(404)

    credits_to_add = request.form.get('credits', type=int) or 0
    if credits_to_add <= 0:
        flash('Please enter a positive number of SMS credits to allocate.', 'warning')
        return redirect(url_for('platform.organizations'))

    org.sms_credits = (org.sms_credits or 0) + credits_to_add
    db.session.commit()
    from app.services.audit_service import AuditService
    AuditService.log('ADD_SMS_CREDITS', 'Organization', org.id, new_values={'added': credits_to_add, 'new_total': org.sms_credits})
    flash(f"Successfully allocated {credits_to_add} SMS credits to '{org.name}'. New balance: {org.sms_credits} SMS.", 'success')
    return redirect(url_for('platform.organizations'))


@platform_bp.route('/organizations/<int:org_id>/timeline', methods=['POST'])
@login_required
def update_organization_timeline(org_id):
    """Manage customer organization trial/subscription timeline and expiration."""
    if not superadmin_only():
        return redirect(url_for('dashboard.index'))
    org = db.session.get(Organization, org_id)
    if not org:
        from flask import abort; abort(404)

    days_to_add = request.form.get('days', type=int) or 0
    status_override = request.form.get('status')
    from datetime import datetime as _dt, timedelta as _td

    base_time = org.subscription_expires_at if (org.subscription_expires_at and org.subscription_expires_at > _dt.utcnow()) else _dt.utcnow()
    org.subscription_expires_at = base_time + _td(days=days_to_add)
    if status_override:
        org.subscription_status = status_override
    elif org.subscription_status == 'EXPIRED':
        org.subscription_status = 'ACTIVE'
    org.is_active = True
    db.session.commit()

    from app.services.audit_service import AuditService
    AuditService.log('EXTEND_SUBSCRIPTION_TIMELINE', 'Organization', org.id, new_values={'days_added': days_to_add, 'new_expiry': str(org.subscription_expires_at)})
    flash(f"Subscription timeline for '{org.name}' extended by {days_to_add} days (Expires: {org.subscription_expires_at.strftime('%d %b %Y')}).", 'success')
    return redirect(url_for('platform.organizations'))


@platform_bp.route('/sms/broadcast', methods=['POST'])
@login_required
def superadmin_broadcast_sms():
    """Superadmin master SMS broadcast across organizations/tenants."""
    if not superadmin_only():
        return redirect(url_for('dashboard.index'))

    target_group = request.form.get('target_group', 'ALL_ORGANIZATIONS')
    message = request.form.get('message', '').strip()

    if not message:
        flash('Broadcast message text is required.', 'danger')
        return redirect(url_for('communication.sms_history'))

    from app.models.tenant import Tenant
    from app.services.sms_service import SmsService

    count = 0
    if target_group in ('ALL_ORGANIZATIONS', 'ORGANIZATION_OWNERS'):
        orgs = Organization.query.filter_by(is_active=True).all()
        for o in orgs:
            if o.contact_phone:
                SmsService.send_sms(to_phone=o.contact_phone, message=f"[Angaza Platform Alert]\n{message}", notification_type='PLATFORM_BROADCAST')
                count += 1
    elif target_group == 'ALL_TENANTS':
        tenants = Tenant.query.filter_by(is_active=True).all()
        for t in tenants:
            if t.phone:
                SmsService.send_sms(to_phone=t.phone, message=message, notification_type='PLATFORM_BROADCAST')
                count += 1

    flash(f"Platform master SMS broadcast dispatched to {count} recipient(s) via Twilio gateway.", 'success')
    return redirect(url_for('communication.sms_history'))


@platform_bp.route('/analytics')
@login_required
def analytics():
    """Platform-level usage analytics dashboard for superadmin."""
    if not superadmin_only():
        return redirect(url_for('dashboard.index'))

    from datetime import date, timedelta
    from app.models.communication import Notification
    from app.models.finance import Payment
    from app.models.hospitality import HospitalityReservation
    from app.models.user import User
    from app.models.tenant import Tenant

    today = date.today()
    first_of_month = date(today.year, today.month, 1)
    last_30 = today - timedelta(days=30)

    # Organization breakdown
    all_orgs = Organization.query.order_by(Organization.created_at.desc()).all()
    org_tier_breakdown = {
        'RENTAL_STANDARD': sum(1 for o in all_orgs if o.subscription_tier == 'RENTAL_STANDARD'),
        'HOSPITALITY_STANDARD': sum(1 for o in all_orgs if o.subscription_tier == 'HOSPITALITY_STANDARD'),
        'COMBINED_SUITE': sum(1 for o in all_orgs if o.subscription_tier == 'COMBINED_SUITE'),
        'ENTERPRISE': sum(1 for o in all_orgs if o.subscription_tier == 'ENTERPRISE'),
    }
    org_status_breakdown = {
        'ACTIVE': sum(1 for o in all_orgs if o.subscription_status == 'ACTIVE'),
        'TRIAL': sum(1 for o in all_orgs if o.subscription_status == 'TRIAL'),
        'SUSPENDED': sum(1 for o in all_orgs if o.subscription_status == 'SUSPENDED'),
        'EXPIRED': sum(1 for o in all_orgs if o.subscription_status == 'EXPIRED'),
    }

    # Platform usage metrics
    total_users = User.query.count()
    total_properties = Property.query.count()
    total_units = RentalUnit.query.count()
    total_tenants = Tenant.query.count()

    # SMS metrics (last 30 days)
    sms_sent = Notification.query.filter(
        Notification.channel == 'SMS',
        Notification.sent_status == 'SENT',
        Notification.created_at >= last_30
    ).count()
    sms_failed = Notification.query.filter(
        Notification.channel == 'SMS',
        Notification.sent_status == 'FAILED',
        Notification.created_at >= last_30
    ).count()

    # Rental revenue (MTD)
    rental_payments_mtd = Payment.query.filter(
        Payment.payment_date >= first_of_month
    ).all()
    rental_revenue_mtd_cents = sum(p.amount_cents for p in rental_payments_mtd)

    # Hospitality revenue (MTD)
    hosp_res_mtd = HospitalityReservation.query.filter(
        HospitalityReservation.check_in_date >= first_of_month,
        HospitalityReservation.status.in_(['CONFIRMED', 'CHECKED_IN', 'CHECKED_OUT'])
    ).all()
    hosp_revenue_mtd_cents = sum(r.total_stay_cents for r in hosp_res_mtd)

    from app.utils.currency import format_currency

    return render_template(
        'platform/analytics.html',
        all_orgs=all_orgs,
        total_orgs=len(all_orgs),
        active_orgs=org_status_breakdown['ACTIVE'],
        org_tier_breakdown=org_tier_breakdown,
        org_status_breakdown=org_status_breakdown,
        total_users=total_users,
        total_properties=total_properties,
        total_units=total_units,
        total_tenants=total_tenants,
        sms_sent=sms_sent,
        sms_failed=sms_failed,
        rental_revenue_mtd=format_currency(rental_revenue_mtd_cents),
        hosp_revenue_mtd=format_currency(hosp_revenue_mtd_cents),
        combined_revenue_mtd=format_currency(rental_revenue_mtd_cents + hosp_revenue_mtd_cents),
        today=today,
        first_of_month=first_of_month
    )


@platform_bp.route('/organizations/<int:org_id>/users')
@login_required
def organization_users(org_id):
    """List and manage users assigned to a specific organization."""
    if not superadmin_only():
        return redirect(url_for('dashboard.index'))

    from app.models.user import User
    org = db.session.get(Organization, org_id)
    if not org:
        from flask import abort; abort(404)

    org_users = User.query.filter_by(organization_id=org_id).all()
    unassigned_users = User.query.filter_by(organization_id=None).all()

    return render_template(
        'platform/org_users.html',
        org=org,
        org_users=org_users,
        unassigned_users=unassigned_users
    )


@platform_bp.route('/organizations/<int:org_id>/assign-user', methods=['POST'])
@login_required
def assign_user_to_org(org_id):
    """Assign an existing user to an organization."""
    if not superadmin_only():
        return redirect(url_for('dashboard.index'))

    from app.models.user import User
    org = db.session.get(Organization, org_id)
    if not org:
        from flask import abort; abort(404)

    user_id = request.form.get('user_id', type=int)
    user = db.session.get(User, user_id) if user_id else None
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('platform.organization_users', org_id=org_id))

    user.organization_id = org_id
    db.session.commit()
    flash(f"User '{user.full_name}' assigned to organization '{org.name}'.", 'success')
    return redirect(url_for('platform.organization_users', org_id=org_id))
