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
        max_users=max_users
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

    org.subscription_tier = tier
    org.max_properties = max_props
    org.max_units = max_units
    org.max_users = max_users
    db.session.commit()

    flash(f"Organization '{org.name}' subscription updated to {tier} (Limit: {max_units} units).", 'success')
    return redirect(url_for('platform.organizations'))
