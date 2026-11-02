from datetime import datetime, date
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app.extensions import db
from app.models.finance import RentCharge, Payment
from app.models.tenant import Tenant
from app.models.property import Property, RentalUnit
from app.services.rent_service import RentService
from app.services.payment_service import PaymentService
from app.utils.pdf_generator import generate_receipt_pdf
from app.utils.decorators import permission_required

billing_bp = Blueprint('billing', __name__, url_prefix='/billing')

PAYMENT_METHODS = [
    ('MPESA_PAYBILL', 'M-Pesa Paybill'),
    ('MPESA_TILL', 'M-Pesa Till / Buy Goods'),
    ('BANK_TRANSFER', 'Bank Transfer / EFT'),
    ('CASH', 'Cash Payment'),
    ('CHEQUE', 'Cheque Deposit'),
    ('OTHER', 'Other Method')
]

@billing_bp.route('/')
@login_required
@permission_required('billing.view')
def index():
    now = datetime.utcnow()
    month = request.args.get('month', now.month, type=int)
    year = request.args.get('year', now.year, type=int)
    status = request.args.get('status')
    tab = request.args.get('tab', 'invoices')
    search = request.args.get('search', '').strip()
    tenant_id_filter = request.args.get('tenant_id', type=int)

    # Query Invoices / Charges
    charges_query = RentCharge.query
    if tenant_id_filter:
        charges_query = charges_query.filter_by(tenant_id=tenant_id_filter)
    elif not search:
        charges_query = charges_query.filter_by(period_month=month, period_year=year)

    if status:
        charges_query = charges_query.filter_by(status=status)
    if search:
        term = f"%{search}%"
        charges_query = charges_query.join(Tenant).filter(
            (Tenant.first_name.ilike(term)) |
            (Tenant.last_name.ilike(term)) |
            (Tenant.phone.ilike(term)) |
            (RentCharge.invoice_number.ilike(term))
        )
    charges = charges_query.order_by(RentCharge.due_date.asc()).all()

    # Query Payments
    payments = Payment.query.order_by(Payment.created_at.desc()).limit(100).all()

    # Active tenants for payment recording
    active_tenants = Tenant.query.filter_by(is_active=True).all()
    properties = Property.query.all()

    # Summary metrics for current month
    total_billed_cents = sum(c.amount_cents for c in charges)
    total_collected_cents = sum(c.amount_paid_cents for c in charges)
    total_outstanding_cents = sum(c.balance_cents for c in charges)
    collection_pct = round((total_collected_cents / total_billed_cents * 100), 1) if total_billed_cents > 0 else 0

    # Calculate comprehensive unit-by-unit house payment status breakdown
    all_units = RentalUnit.query.order_by(RentalUnit.property_id.asc(), RentalUnit.unit_number.asc()).all()
    unit_performance = []
    
    counts = {
        'total': len(all_units),
        'vacant': 0,
        'paid': 0,
        'partial': 0,
        'unpaid': 0,
        'paid_late': 0
    }

    charges_by_unit = {c.rental_unit_id: c for c in charges if c.charge_type == 'RENT'}
    late_fee_units = set(c.rental_unit_id for c in RentCharge.query.filter_by(period_month=month, period_year=year, charge_type='LATE_FEE').all())

    for u in all_units:
        if u.occupancy_status == 'VACANT':
            counts['vacant'] += 1
            status_tag = 'VACANT'
            badge_class = 'badge-vacant'
            t_name = '—'
            b_cents = 0
            p_cents = 0
            bal_cents = 0
        else:
            chg = charges_by_unit.get(u.id)
            t_name = u.current_tenant.full_name if u.current_tenant else 'Occupied'
            if chg:
                b_cents = chg.amount_cents
                p_cents = chg.amount_paid_cents
                bal_cents = chg.balance_cents
                if chg.status == 'PAID':
                    if u.id in late_fee_units:
                        status_tag = 'PAID_LATE'
                        badge_class = 'bg-warning text-dark'
                        counts['paid_late'] += 1
                    else:
                        status_tag = 'PAID'
                        badge_class = 'bg-success text-white'
                        counts['paid'] += 1
                elif chg.status == 'PARTIALLY_PAID':
                    status_tag = 'PARTIAL'
                    badge_class = 'bg-info text-white'
                    counts['partial'] += 1
                else:
                    status_tag = 'UNPAID'
                    badge_class = 'bg-danger text-white'
                    counts['unpaid'] += 1
            else:
                b_cents = u.rent_amount_cents
                p_cents = 0
                bal_cents = u.rent_amount_cents
                status_tag = 'NOT_BILLED'
                badge_class = 'bg-secondary text-white'

        unit_performance.append({
            'unit': u,
            'tenant_name': t_name,
            'billed_cents': b_cents,
            'paid_cents': p_cents,
            'balance_cents': bal_cents,
            'status_tag': status_tag,
            'badge_class': badge_class
        })

    return render_template(
        'billing/index.html',
        charges=charges,
        payments=payments,
        active_tenants=active_tenants,
        properties=properties,
        payment_methods=PAYMENT_METHODS,
        selected_month=month,
        selected_year=year,
        selected_status=status,
        search=search,
        selected_tenant_id=tenant_id_filter,
        active_tab=tab,
        total_billed_cents=total_billed_cents,
        total_collected_cents=total_collected_cents,
        total_outstanding_cents=total_outstanding_cents,
        collection_pct=collection_pct,
        unit_performance=unit_performance,
        counts=counts
    )

@billing_bp.route('/generate-monthly', methods=['POST'])
@login_required
@permission_required('billing.manage')
def generate_monthly():
    month = request.form.get('month', type=int) or datetime.utcnow().month
    year = request.form.get('year', type=int) or datetime.utcnow().year

    result = RentService.generate_monthly_charges(month=month, year=year)
    flash(f"Monthly rent billing completed! Generated {result['created_count']} new invoices for {date(year, month, 1).strftime('%B %Y')}.", 'success')
    return redirect(url_for('billing.index', month=month, year=year, tab='invoices'))

@billing_bp.route('/apply-penalties', methods=['POST'])
@login_required
@permission_required('billing.manage')
def apply_penalties():
    count = RentService.apply_late_penalties()
    flash(f"Late payment penalties audit completed: {count} overdue invoices updated with late fees.", 'info')
    return redirect(url_for('billing.index', tab='invoices'))

@billing_bp.route('/send-reminders', methods=['POST'])
@login_required
@permission_required('billing.manage')
def send_reminders():
    from app.services.notification_service import NotificationService
    sent_count = NotificationService.send_rent_due_reminders()
    flash(f"Payment reminders successfully dispatched to {sent_count} tenants with pending balances.", 'success')
    return redirect(url_for('billing.index', tab='invoices'))


@billing_bp.route('/payments/record', methods=['POST'])
@login_required
@permission_required('billing.manage')
def record_payment():
    tenant_id = request.form.get('tenant_id', type=int)
    amount = request.form.get('amount', type=float)
    payment_method = request.form.get('payment_method', 'CASH')
    payment_date_str = request.form.get('payment_date')
    ref = request.form.get('transaction_reference', '').strip()
    description = request.form.get('description', '').strip()

    if not tenant_id or not amount or amount <= 0:
        flash('Valid tenant and payment amount are required.', 'danger')
        return redirect(url_for('billing.index', tab='payments'))

    payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date() if payment_date_str else date.today()

    try:
        payment = PaymentService.record_payment(
            tenant_id=tenant_id,
            amount=amount,
            payment_method=payment_method,
            payment_date=payment_date,
            transaction_reference=ref if ref else None,
            description=description,
            user_id=current_user.id,
            auto_confirm=True
        )
        flash(f"Payment recorded and confirmed successfully under Receipt {payment.receipt_number}.", 'success')
        return redirect(url_for('billing.view_receipt', payment_id=payment.id))
    except Exception as e:
        flash(f"Failed to record payment: {str(e)}", 'danger')
        return redirect(url_for('billing.index', tab='payments'))

@billing_bp.route('/payments/<int:payment_id>/reverse', methods=['POST'])
@login_required
@permission_required('billing.manage')
def reverse_payment(payment_id):
    reason = request.form.get('reversal_reason', '').strip()
    if not reason:
        flash('A reason is required to reverse a confirmed payment.', 'danger')
        return redirect(url_for('billing.index', tab='payments'))

    try:
        PaymentService.reverse_payment(payment_id, reversal_reason=reason, user_id=current_user.id)
        flash('Payment has been reversed. Allocated charges have been restored to unpaid status.', 'warning')
    except Exception as e:
        flash(f"Reversal failed: {str(e)}", 'danger')

    return redirect(url_for('billing.index', tab='payments'))

@billing_bp.route('/receipt/<int:payment_id>/view')
@login_required
@permission_required('billing.view')
def view_receipt(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment:
        from flask import abort; abort(404)
    return render_template('billing/receipt.html', payment=payment)

@billing_bp.route('/receipt/<int:payment_id>/pdf')
@login_required
@permission_required('billing.view')
def download_receipt_pdf(payment_id):
    payment = db.session.get(Payment, payment_id)
    if not payment:
        from flask import abort; abort(404)
    pdf_bytes = generate_receipt_pdf(payment)
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Receipt_{payment.receipt_number}.pdf"
    )

