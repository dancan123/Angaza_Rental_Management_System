from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.gateway import BankAccount, BankTransaction
from app.models.property import Property
from app.models.tenant import Tenant
from app.models.user import Landlord
from app.services.bank_service import BankService
from app.utils.decorators import permission_required

banking_bp = Blueprint('banking', __name__, url_prefix='/banking')

@banking_bp.route('/')
@login_required
@permission_required('banking.manage')
def index():
    accounts = BankAccount.query.all()
    queue = BankTransaction.query.filter_by(reconciliation_status='UNMATCHED').order_by(BankTransaction.transaction_date.desc()).all()
    reconciled = BankTransaction.query.filter(BankTransaction.reconciliation_status.in_(['MATCHED', 'MANUALLY_RECONCILED'])).order_by(BankTransaction.reconciled_at.desc()).limit(50).all()
    properties = Property.query.all()
    landlords = Landlord.query.filter_by(is_active=True).all()
    active_tenants = Tenant.query.filter_by(is_active=True).all()

    return render_template(
        'banking/index.html',
        accounts=accounts,
        queue=queue,
        reconciled=reconciled,
        properties=properties,
        landlords=landlords,
        tenants=active_tenants
    )

@banking_bp.route('/accounts/create', methods=['POST'])
@login_required
@permission_required('banking.manage')
def create_account():
    bank_name = request.form.get('bank_name', '').strip()
    account_name = request.form.get('account_name', '').strip()
    account_number = request.form.get('account_number', '').strip()
    branch = request.form.get('branch', '').strip()
    currency = request.form.get('currency', 'KES').strip()
    landlord_id = request.form.get('landlord_id', type=int)
    property_id = request.form.get('property_id', type=int)

    if not bank_name or not account_name or not account_number:
        flash('Bank name, account name, and account number are required.', 'danger')
        return redirect(url_for('banking.index'))

    BankService.create_bank_account(
        bank_name=bank_name,
        account_name=account_name,
        account_number=account_number,
        branch=branch,
        currency=currency,
        landlord_id=landlord_id,
        property_id=property_id
    )
    flash(f"Bank account '{bank_name} - {account_number}' configured.", 'success')
    return redirect(url_for('banking.index'))

@banking_bp.route('/upload-statement', methods=['POST'])
@login_required
@permission_required('banking.manage')
def upload_statement():
    bank_account_id = request.form.get('bank_account_id', type=int)
    file = request.files.get('statement_file')

    if not bank_account_id or not file or not file.filename:
        flash('Please select a bank account and statement file.', 'danger')
        return redirect(url_for('banking.index'))

    try:
        result = BankService.parse_and_import_statement(bank_account_id, file.stream, file.filename)
        flash(f"Statement parsed! Imported {result['imported_count']} new transactions ({result['matched_count']} auto-matched).", 'success')
    except Exception as e:
        flash(f"Statement import failed: {str(e)}", 'danger')

    return redirect(url_for('banking.index'))

@banking_bp.route('/reconcile/<int:transaction_id>', methods=['POST'])
@login_required
@permission_required('banking.manage')
def reconcile_transaction(transaction_id):
    tenant_id = request.form.get('tenant_id', type=int)
    if not tenant_id:
        flash('Please select a tenant to reconcile this payment.', 'danger')
        return redirect(url_for('banking.index'))

    try:
        payment = BankService.reconcile_transaction(transaction_id, tenant_id, user_id=current_user.id)
        flash(f"Transaction successfully reconciled! Confirmed payment under Receipt {payment.receipt_number}.", 'success')
    except Exception as e:
        flash(f"Reconciliation failed: {str(e)}", 'danger')

    return redirect(url_for('banking.index'))

@banking_bp.route('/ignore/<int:transaction_id>', methods=['POST'])
@login_required
@permission_required('banking.manage')
def ignore_transaction(transaction_id):
    BankService.ignore_transaction(transaction_id, user_id=current_user.id)
    flash('Transaction ignored from reconciliation queue.', 'info')
    return redirect(url_for('banking.index'))

