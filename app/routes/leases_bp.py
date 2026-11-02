from datetime import datetime
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required
from app.extensions import db
from app.models.lease import Lease
from app.models.property import RentalUnit
from app.models.tenant import Tenant
from app.services.lease_service import LeaseService
from app.utils.decorators import permission_required

leases_bp = Blueprint('leases', __name__, url_prefix='/leases')

@leases_bp.route('/')
@login_required
@permission_required('leases.view')
def index():
    status = request.args.get('status')
    query = Lease.query
    if status:
        query = query.filter_by(status=status)
    leases = query.order_by(Lease.created_at.desc()).all()
    expiring = LeaseService.get_expiring_leases(days_ahead=45)
    vacant_units = RentalUnit.query.filter_by(occupancy_status='VACANT').all()
    tenants = Tenant.query.filter_by(is_active=True).all()

    return render_template(
        'leases/index.html',
        leases=leases,
        expiring=expiring,
        vacant_units=vacant_units,
        tenants=tenants,
        selected_status=status
    )

@leases_bp.route('/create', methods=['POST'])
@login_required
@permission_required('leases.manage')
def create_lease():
    rental_unit_id = request.form.get('rental_unit_id', type=int)
    tenant_id = request.form.get('tenant_id', type=int)
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    monthly_rent = request.form.get('monthly_rent', type=float)
    deposit = request.form.get('deposit_amount', 0, type=float)
    due_day = request.form.get('payment_due_day', 5, type=int)
    notice = request.form.get('notice_period_days', 30, type=int)
    terms = request.form.get('terms_and_conditions')

    if not rental_unit_id or not tenant_id or not start_date_str or not monthly_rent:
        flash('Rental unit, tenant, start date, and rent are mandatory.', 'danger')
        return redirect(url_for('leases.index'))

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None

    try:
        lease = LeaseService.create_lease(
            rental_unit_id=rental_unit_id,
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            monthly_rent=monthly_rent,
            deposit_amount=deposit,
            payment_due_day=due_day,
            notice_period_days=notice,
            terms_and_conditions=terms
        )
        flash(f"Tenancy Agreement {lease.lease_number} created and executed.", 'success')
        return redirect(url_for('leases.detail', lease_id=lease.id))
    except Exception as e:
        flash(f"Failed to create lease: {str(e)}", 'danger')
        return redirect(url_for('leases.index'))

@leases_bp.route('/<int:lease_id>')
@login_required
@permission_required('leases.view')
def detail(lease_id):
    lease = db.session.get(Lease, lease_id)
    if not lease:
        from flask import abort; abort(404)
    return render_template('leases/detail.html', lease=lease)

@leases_bp.route('/<int:lease_id>/pdf')
@login_required
@permission_required('leases.view')
def download_lease_pdf(lease_id):
    lease = db.session.get(Lease, lease_id)
    if not lease:
        from flask import abort; abort(404)
    pdf_bytes = LeaseService.generate_lease_pdf(lease)
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Tenancy_Agreement_{lease.lease_number}.pdf"
    )

@leases_bp.route('/<int:lease_id>/terminate', methods=['POST'])
@login_required
@permission_required('leases.manage')
def terminate_lease(lease_id):
    lease = db.session.get(Lease, lease_id)
    if not lease:
        from flask import abort; abort(404)
    reason = request.form.get('reason', '').strip()
    lease.status = 'TERMINATED'
    lease.terminated_at = datetime.utcnow()
    lease.termination_reason = reason or 'Contract Terminated by Landlord/Manager'
    lease.rental_unit.occupancy_status = 'VACANT'
    lease.rental_unit.current_tenant_id = None
    db.session.commit()
    flash(f"Lease {lease.lease_number} has been terminated.", 'info')
    return redirect(url_for('leases.index'))

