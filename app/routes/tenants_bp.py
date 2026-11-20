from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.tenant import Tenant
from app.models.property import RentalUnit
from app.models.lease import TenancyRecord
from app.services.tenant_service import TenantService
from app.utils.decorators import permission_required, multi_tenant_scoped

tenants_bp = Blueprint('tenants', __name__, url_prefix='/tenants')

@tenants_bp.route('/')
@login_required
@permission_required('tenants.view')
def index():
    search = request.args.get('search', '').strip()
    direct = request.args.get('direct') == '1'
    status_filter = request.args.get('active')
    is_active = True if status_filter is None or status_filter == '1' else (False if status_filter == '0' else None)

    tenants = TenantService.get_tenants(search=search, is_active=is_active)
    
    # If single exact match from quick search bar with direct=1, go straight to tenant profile
    if direct and search and len(tenants) == 1:
        return redirect(url_for('tenants.detail', tenant_id=tenants[0].id))

    # Pre-calculate financial balances and tenancy data for all matched tenants
    tenant_data = []
    for t in tenants:
        summary = TenantService.get_tenant_financial_summary(t.id)
        active_lease = t.leases.filter_by(status='ACTIVE').first()
        deposit_cents = active_lease.deposit_cents if active_lease else 0
        rent_cents = active_lease.monthly_rent_cents if active_lease else (t.current_unit.rent_amount_cents if t.current_unit else 0)
        nok = t.next_of_kin.first()
        tenant_data.append({
            'tenant': t,
            'summary': summary,
            'active_lease': active_lease,
            'rent_cents': rent_cents,
            'deposit_cents': deposit_cents,
            'outstanding_cents': summary.get('outstanding_cents', 0),
            'next_of_kin': nok
        })

    vacant_units = multi_tenant_scoped(RentalUnit.query.filter_by(occupancy_status='VACANT'), RentalUnit).all()

    return render_template(
        'tenants/index.html',
        tenants=tenants,
        tenant_data=tenant_data,
        vacant_units=vacant_units,
        search=search,
        status_filter=status_filter
    )

@tenants_bp.route('/create', methods=['POST'])
@login_required
@permission_required('tenants.manage')
def create_tenant():
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    id_passport = request.form.get('id_passport_number', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    emergency_contact = request.form.get('emergency_contact', '').strip()
    emergency_phone = request.form.get('emergency_phone', '').strip()
    physical_address = request.form.get('physical_address', '').strip()
    occupation = request.form.get('occupation', '').strip()

    # Next of Kin
    kin_name = request.form.get('kin_name', '').strip()
    kin_rel = request.form.get('kin_relationship', '').strip()
    kin_phone = request.form.get('kin_phone', '').strip()
    next_of_kin_data = {'full_name': kin_name, 'relationship': kin_rel, 'phone': kin_phone} if kin_name and kin_phone else None

    if not first_name or not last_name or not id_passport or not phone:
        flash('First name, last name, ID/Passport number, and telephone are required.', 'danger')
        return redirect(url_for('tenants.index'))

    try:
        tenant = TenantService.create_tenant(
            first_name=first_name,
            last_name=last_name,
            id_passport_number=id_passport,
            phone=phone,
            email=email,
            emergency_contact=emergency_contact,
            emergency_phone=emergency_phone,
            physical_address=physical_address,
            occupation=occupation,
            next_of_kin_data=next_of_kin_data
        )

        # Optional immediate room allocation
        unit_id = request.form.get('rental_unit_id', type=int)
        if unit_id:
            from app.models.property import RentalUnit
            from app.services.lease_service import LeaseService
            from datetime import date as _dt_date
            unit = db.session.get(RentalUnit, unit_id)
            if unit and unit.occupancy_status == 'VACANT':
                rent = request.form.get('monthly_rent', type=float) or (unit.rent_amount_cents / 100 if unit.rent_amount_cents else 0)
                deposit = request.form.get('deposit_amount', type=float) or (unit.deposit_amount_cents / 100 if unit.deposit_amount_cents else rent)
                start_date_str = request.form.get('start_date')
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else _dt_date.today()
                prorate = request.form.get('prorate_first_month') in ('1', 'true', 'on', 'yes')

                LeaseService.create_lease(
                    rental_unit_id=unit.id,
                    tenant_id=tenant.id,
                    start_date=start_date,
                    monthly_rent=rent,
                    deposit_amount=deposit,
                    prorate_first_month=prorate
                )
                flash(f"Tenant '{tenant.full_name}' registered and allocated to Unit {unit.unit_number} ({unit.property.name}).", 'success')
                return redirect(url_for('tenants.detail', tenant_id=tenant.id))

        flash(f"Tenant '{tenant.full_name}' registered successfully.", 'success')
        return redirect(url_for('tenants.detail', tenant_id=tenant.id))
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('tenants.index'))

@tenants_bp.route('/<int:tenant_id>')
@login_required
@permission_required('tenants.view')
def detail(tenant_id):
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        abort(404)
    if not current_user.is_superadmin() and tenant.organization_id and current_user.organization_id and tenant.organization_id != current_user.organization_id:
        abort(404)
    summary = TenantService.get_tenant_financial_summary(tenant.id)
    active_lease = tenant.leases.filter_by(status='ACTIVE').first()
    if active_lease:
        summary['deposit_held_cents'] = active_lease.deposit_cents
    else:
        summary['deposit_held_cents'] = 0

    tenancy_records = TenancyRecord.query.filter_by(tenant_id=tenant.id).order_by(TenancyRecord.created_at.desc()).all()
    charges = tenant.rent_charges.order_by(db.desc('due_date')).all()
    payments = tenant.payments.order_by(db.desc('payment_date')).all()
    vacant_units = multi_tenant_scoped(RentalUnit.query.filter_by(occupancy_status='VACANT'), RentalUnit).all()

    return render_template(
        'tenants/detail.html',
        tenant=tenant,
        summary=summary,
        active_lease=active_lease,
        tenancy_records=tenancy_records,
        charges=charges,
        payments=payments,
        vacant_units=vacant_units
    )

@tenants_bp.route('/<int:tenant_id>/allocate-unit', methods=['POST'])
@login_required
@permission_required('tenants.manage')
def allocate_unit(tenant_id):
    """Allocate a vacant rental unit / house to an existing tenant and create lease."""
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        abort(404)
    if not current_user.is_superadmin() and tenant.organization_id and current_user.organization_id and tenant.organization_id != current_user.organization_id:
        abort(404)

    unit_id = request.form.get('rental_unit_id', type=int)
    if not unit_id:
        flash('Please select a vacant unit to allocate.', 'danger')
        return redirect(url_for('tenants.detail', tenant_id=tenant.id))

    from app.models.property import RentalUnit
    from app.services.lease_service import LeaseService
    from datetime import date as _dt_date

    unit = db.session.get(RentalUnit, unit_id)
    if not unit or unit.occupancy_status != 'VACANT':
        flash('Selected unit is no longer vacant or does not exist.', 'danger')
        return redirect(url_for('tenants.detail', tenant_id=tenant.id))

    rent = request.form.get('monthly_rent', type=float) or (unit.rent_amount_cents / 100 if unit.rent_amount_cents else 0)
    deposit = request.form.get('deposit_amount', type=float) or (unit.deposit_amount_cents / 100 if unit.deposit_amount_cents else rent)
    start_date_str = request.form.get('start_date')
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else _dt_date.today()
    prorate = request.form.get('prorate_first_month') in ('1', 'true', 'on', 'yes')

    try:
        lease = LeaseService.create_lease(
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            start_date=start_date,
            monthly_rent=rent,
            deposit_amount=deposit,
            prorate_first_month=prorate
        )
        flash(f"Unit '{unit.unit_number}' ({unit.property.name}) successfully allocated to {tenant.full_name}! Tenancy Agreement {lease.lease_number} activated.", 'success')
    except Exception as e:
        flash(f"Allocation failed: {str(e)}", 'danger')

    return redirect(url_for('tenants.detail', tenant_id=tenant.id))

@tenants_bp.route('/<int:tenant_id>/edit', methods=['POST'])
@login_required
@permission_required('tenants.manage')
def edit_tenant(tenant_id):
    """
    Update tenant primary profile, contact information, KYC, and next of kin details.
    """
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        abort(404)
    if not current_user.is_superadmin() and tenant.organization_id and current_user.organization_id and tenant.organization_id != current_user.organization_id:
        abort(404)

    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    id_passport = request.form.get('id_passport_number', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    occupation = request.form.get('occupation', '').strip()
    physical_address = request.form.get('physical_address', '').strip()
    emergency_contact = request.form.get('emergency_contact', '').strip()
    emergency_phone = request.form.get('emergency_phone', '').strip()

    if not first_name or not last_name or not id_passport or not phone:
        flash('First name, last name, ID/Passport, and phone are mandatory.', 'danger')
        return redirect(url_for('tenants.detail', tenant_id=tenant_id))

    # Update basic fields
    tenant.first_name = first_name
    tenant.last_name = last_name
    tenant.id_passport_number = id_passport.upper()
    tenant.phone = phone
    tenant.email = email if email else None
    tenant.occupation = occupation
    tenant.physical_address = physical_address
    tenant.emergency_contact = emergency_contact
    tenant.emergency_phone = emergency_phone

    # Update or add Next of Kin
    kin_name = request.form.get('kin_name', '').strip()
    kin_rel = request.form.get('kin_relationship', '').strip()
    kin_phone = request.form.get('kin_phone', '').strip()
    if kin_name and kin_phone:
        from app.models.tenant import NextOfKin
        kin = tenant.next_of_kin.first()
        if kin:
            kin.full_name = kin_name
            kin.relationship = kin_rel
            kin.phone = kin_phone
        else:
            new_kin = NextOfKin(
                tenant_id=tenant.id,
                full_name=kin_name,
                relationship=kin_rel,
                phone=kin_phone
            )
            db.session.add(new_kin)

    db.session.commit()
    flash(f"Tenant profile for '{tenant.full_name}' updated successfully.", 'success')
    return redirect(url_for('tenants.detail', tenant_id=tenant_id))

@tenants_bp.route('/<int:tenant_id>/delete', methods=['POST'])
@login_required
@permission_required('tenants.manage')
def delete_tenant(tenant_id):
    """
    Safely delete or archive tenant. Prevent deletion if active occupied unit exists.
    """
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        abort(404)
    if not current_user.is_superadmin() and tenant.organization_id and current_user.organization_id and tenant.organization_id != current_user.organization_id:
        abort(404)

    if tenant.current_unit:
        flash(f"Cannot delete tenant while assigned to Unit {tenant.current_unit.unit_number}. Process move-out first.", 'danger')
        return redirect(url_for('tenants.detail', tenant_id=tenant_id))

    name = tenant.full_name
    tenant.is_active = False
    db.session.commit()
    flash(f"Tenant record for '{name}' has been deactivated and archived.", 'info')
    return redirect(url_for('tenants.index'))

@tenants_bp.route('/<int:tenant_id>/transfer', methods=['POST'])
@login_required
@permission_required('tenants.manage')
def transfer_unit(tenant_id):
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        abort(404)
    if not current_user.is_superadmin() and tenant.organization_id and current_user.organization_id and tenant.organization_id != current_user.organization_id:
        abort(404)
    new_unit_id = request.form.get('new_unit_id', type=int)
    transfer_reason = request.form.get('transfer_reason', '').strip()

    if not new_unit_id:
        flash('Please select a valid vacant unit for transfer.', 'danger')
        return redirect(url_for('tenants.detail', tenant_id=tenant_id))

    try:
        lease = TenantService.transfer_unit(tenant_id, new_unit_id, transfer_reason=transfer_reason)
        flash(f"Tenant transferred successfully to Unit {lease.rental_unit.unit_number}.", 'success')
    except Exception as e:
        flash(f"Transfer failed: {str(e)}", 'danger')

    return redirect(url_for('tenants.detail', tenant_id=tenant_id))

@tenants_bp.route('/<int:tenant_id>/move-out', methods=['POST'])
@login_required
@permission_required('tenants.manage')
def move_out(tenant_id):
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        abort(404)
    if not current_user.is_superadmin() and tenant.organization_id and current_user.organization_id and tenant.organization_id != current_user.organization_id:
        abort(404)
    inspection_notes = request.form.get('inspection_notes', '').strip()
    deposit_refunded = request.form.get('deposit_refunded', 0, type=float)
    deposit_deductions = request.form.get('deposit_deductions', 0, type=float)
    deduction_reason = request.form.get('deduction_reason', '').strip()

    try:
        TenantService.process_move_out(
            tenant_id=tenant_id,
            inspection_notes=inspection_notes,
            deposit_refunded=deposit_refunded,
            deposit_deductions=deposit_deductions,
            deduction_reason=deduction_reason
        )
        flash('Tenant move-out completed. Unit has been restored to Vacant status.', 'info')
    except Exception as e:
        flash(f"Move-out failed: {str(e)}", 'danger')

    return redirect(url_for('tenants.detail', tenant_id=tenant_id))


@tenants_bp.route('/<int:tenant_id>/statement/pdf')
@login_required
@permission_required('tenants.view')
def download_statement_pdf(tenant_id):
    from io import BytesIO
    from flask import send_file
    from app.utils.pdf_generator import generate_tenant_statement_pdf
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        abort(404)
    if not current_user.is_superadmin() and tenant.organization_id and current_user.organization_id and tenant.organization_id != current_user.organization_id:
        abort(404)
    pdf_bytes = generate_tenant_statement_pdf(tenant)
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Statement_{tenant.id_passport_number}.pdf"
    )

