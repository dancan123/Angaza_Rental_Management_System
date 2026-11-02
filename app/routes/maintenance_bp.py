from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.maintenance import Expense, MaintenanceRequest
from app.models.property import Property, RentalUnit
from app.services.maintenance_service import MaintenanceService
from app.utils.decorators import permission_required

maintenance_bp = Blueprint('maintenance', __name__, url_prefix='/maintenance')

EXPENSE_CATEGORIES = [
    ('REPAIRS', 'Repairs & Renovations'),
    ('PLUMBING', 'Plumbing & Drainage'),
    ('ELECTRICITY', 'Electricity & Electricals'),
    ('WATER', 'Water Bills & Tanker Delivery'),
    ('SECURITY', 'Security Guard Services'),
    ('CLEANING', 'Cleaning & Caretaker Supplies'),
    ('GARBAGE', 'Garbage Collection'),
    ('INSURANCE', 'Property Fire/Loss Insurance'),
    ('TAXES', 'County Land Rates & Taxes'),
    ('MANAGEMENT_FEE', 'Property Management Agency Fee'),
    ('OTHER', 'Other Operating Expenses')
]

PRIORITIES = [
    ('LOW', 'Low Priority'),
    ('MEDIUM', 'Medium Priority'),
    ('HIGH', 'High Priority'),
    ('EMERGENCY', 'Emergency / Urgent')
]

@maintenance_bp.route('/')
@login_required
@permission_required('maintenance.view')
def index():
    tab = request.args.get('tab', 'tickets')
    requests = MaintenanceRequest.query.order_by(MaintenanceRequest.created_at.desc()).all()
    expenses = Expense.query.order_by(Expense.expense_date.desc()).all()
    properties = Property.query.all()
    units = RentalUnit.query.all()

    total_expense_cents = sum(e.amount_cents for e in expenses)
    pending_tickets = sum(1 for r in requests if r.status in ['PENDING', 'ASSIGNED', 'IN_PROGRESS'])

    return render_template(
        'maintenance/index.html',
        requests=requests,
        expenses=expenses,
        properties=properties,
        units=units,
        categories=EXPENSE_CATEGORIES,
        priorities=PRIORITIES,
        active_tab=tab,
        total_expense_cents=total_expense_cents,
        pending_tickets=pending_tickets
    )

@maintenance_bp.route('/requests/create', methods=['POST'])
@login_required
@permission_required('maintenance.manage')
def create_request():
    rental_unit_id = request.form.get('rental_unit_id', type=int)
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    priority = request.form.get('priority', 'MEDIUM')

    if not rental_unit_id or not title or not description:
        flash('Rental unit, title, and issue description are required.', 'danger')
        return redirect(url_for('maintenance.index', tab='tickets'))

    MaintenanceService.log_request(
        rental_unit_id=rental_unit_id,
        title=title,
        description=description,
        priority=priority
    )
    flash(f"Maintenance ticket '{title}' logged successfully. Property owner notified.", 'success')
    return redirect(url_for('maintenance.index', tab='tickets'))

@maintenance_bp.route('/requests/<int:request_id>/assign', methods=['POST'])
@login_required
@permission_required('maintenance.manage')
def assign_technician(request_id):
    technician = request.form.get('technician_name', '').strip()
    contact = request.form.get('technician_contact', '').strip()

    if not technician:
        flash('Technician name is required.', 'danger')
        return redirect(url_for('maintenance.index', tab='tickets'))

    MaintenanceService.assign_technician(request_id, technician, contact)
    flash(f"Work order assigned to technician '{technician}'.", 'info')
    return redirect(url_for('maintenance.index', tab='tickets'))

@maintenance_bp.route('/requests/<int:request_id>/resolve', methods=['POST'])
@login_required
@permission_required('maintenance.manage')
def resolve_request(request_id):
    summary = request.form.get('work_summary', '').strip()
    cost = request.form.get('cost', 0, type=float)
    completed_by = request.form.get('completed_by', '').strip()

    if not summary:
        flash('Work summary is required.', 'danger')
        return redirect(url_for('maintenance.index', tab='tickets'))

    MaintenanceService.resolve_request(
        request_id=request_id,
        work_summary=summary,
        cost=cost,
        completed_by=completed_by,
        user_id=current_user.id
    )
    flash('Maintenance ticket marked as resolved. Repair cost linked to property expenses.', 'success')
    return redirect(url_for('maintenance.index', tab='tickets'))

@maintenance_bp.route('/expenses/create', methods=['POST'])
@login_required
@permission_required('maintenance.manage')
def create_expense():
    property_id = request.form.get('property_id', type=int)
    rental_unit_id = request.form.get('rental_unit_id', type=int)
    category = request.form.get('category', 'OTHER')
    amount = request.form.get('amount', type=float)
    supplier = request.form.get('supplier_name', '').strip()
    description = request.form.get('description', '').strip()
    date_str = request.form.get('expense_date')

    if not property_id or not amount or amount <= 0 or not description:
        flash('Property, valid expense amount, and description are required.', 'danger')
        return redirect(url_for('maintenance.index', tab='expenses'))

    expense_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()

    MaintenanceService.record_expense(
        property_id=property_id,
        category=category,
        amount=amount,
        description=description,
        rental_unit_id=rental_unit_id if rental_unit_id else None,
        supplier_name=supplier,
        expense_date=expense_date,
        user_id=current_user.id
    )
    flash(f"Operating expense recorded under category '{category}'.", 'success')
    return redirect(url_for('maintenance.index', tab='expenses'))

