from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.finance import RentCharge, Payment
from app.models.maintenance import MaintenanceRequest
from app.models.communication import Notification
from app.models.utility import Meter
from app.services.mpesa_service import DarajaClient
from app.services.personalization_service import PersonalizationService

tenant_portal_bp = Blueprint('tenant_portal', __name__, url_prefix='/portal/tenant')

def get_current_tenant():
    if not current_user.is_authenticated:
        return None
    user_id = getattr(current_user, 'id', None)
    tenant = Tenant.query.filter_by(user_id=user_id).first()
    if not tenant:
        # Fallback by email or phone match
        email = getattr(current_user, 'email', None)
        phone = getattr(current_user, 'phone', None)
        if email:
            tenant = Tenant.query.filter_by(email=email).first()
        if not tenant and phone:
            tenant = Tenant.query.filter_by(phone=phone).first()
    return tenant

@tenant_portal_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        tenant = get_current_tenant()
        if tenant:
            return redirect(url_for('tenant_portal.dashboard'))
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        login_identifier = request.form.get('login_id', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        
        user = User.query.filter(
            (User.username == login_identifier) | 
            (User.email == login_identifier) | 
            (User.phone == login_identifier)
        ).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact your property manager.', 'danger')
                return render_template('portal/tenant_login.html')
                
            login_user(user, remember=remember)
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            
            tenant = get_current_tenant()
            if tenant:
                flash(f"Welcome back, {tenant.first_name}!", 'success')
                return redirect(url_for('tenant_portal.dashboard'))
            return redirect(url_for('dashboard.index'))
        else:
            flash('Invalid phone number, email, or password.', 'danger')
            
    return render_template('portal/tenant_login.html')

@tenant_portal_bp.route('/dashboard')
@login_required
def dashboard():
    tenant = get_current_tenant()
    if not tenant:
        flash('No linked tenant profile found for your login. Redirected to staff dashboard.', 'warning')
        return redirect(url_for('dashboard.index'))
        
    unit = tenant.current_unit
    prop = unit.property if unit else None
    
    # Active Lease
    lease = tenant.leases.filter_by(status='ACTIVE').first()
    
    # Outstanding charges
    unpaid_charges = RentCharge.query.filter(
        RentCharge.tenant_id == tenant.id,
        RentCharge.status.in_(['UNPAID', 'PARTIALLY_PAID'])
    ).order_by(RentCharge.due_date.asc()).all()
    
    total_due_cents = sum(c.balance_cents for c in unpaid_charges)
    
    # Recent payments
    payments = Payment.query.filter_by(tenant_id=tenant.id).order_by(Payment.payment_date.desc(), Payment.id.desc()).limit(10).all()
    
    # Maintenance requests
    maintenance = MaintenanceRequest.query.filter_by(tenant_id=tenant.id).order_by(MaintenanceRequest.reported_date.desc()).all()
    
    # Meters
    meters = Meter.query.filter_by(rental_unit_id=unit.id).all() if unit else []
    
    currency = PersonalizationService.get_setting('currency', 'KES')
    
    return render_template(
        'portal/tenant_dashboard.html',
        tenant=tenant,
        unit=unit,
        property=prop,
        lease=lease,
        unpaid_charges=unpaid_charges,
        total_due_cents=total_due_cents,
        payments=payments,
        maintenance=maintenance,
        meters=meters,
        currency=currency
    )

@tenant_portal_bp.route('/pay-stk', methods=['POST'])
@login_required
def pay_stk():
    tenant = get_current_tenant()
    if not tenant or not tenant.current_unit:
        flash('You must have an assigned rental unit to pay rent.', 'danger')
        return redirect(url_for('tenant_portal.dashboard'))
        
    amount = request.form.get('amount', type=float)
    phone = request.form.get('phone', tenant.phone).strip()
    
    if not amount or amount <= 0:
        flash('Please enter a valid amount greater than zero.', 'danger')
        return redirect(url_for('tenant_portal.dashboard'))
        
    unit = tenant.current_unit
    
    try:
        response = DarajaClient.initiate_stk_push(
            phone=phone,
            amount=int(amount),
            account_reference=unit.unit_number,
            transaction_desc=f"Rent Payment - {unit.unit_number}",
            property_id=unit.property_id
        )
        if response.get('ResponseCode') == '0':
            flash(f"STK Push prompt sent to {phone}! Check your phone and enter your M-Pesa PIN to complete payment of {amount:,.2f}.", 'success')
        else:
            flash(f"M-Pesa Gateway returned: {response.get('ResponseDescription', 'Initiation failed.')}", 'warning')
    except Exception as e:
        flash(f"Payment initiation error: {str(e)}", 'danger')
        
    return redirect(url_for('tenant_portal.dashboard'))

@tenant_portal_bp.route('/submit-ticket', methods=['POST'])
@login_required
def submit_ticket():
    tenant = get_current_tenant()
    if not tenant or not tenant.current_unit:
        flash('You must have an assigned unit to submit a repair ticket.', 'danger')
        return redirect(url_for('tenant_portal.dashboard'))
        
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    priority = request.form.get('priority', 'MEDIUM')
    
    if not title or not description:
        flash('Issue title and description are required.', 'danger')
        return redirect(url_for('tenant_portal.dashboard'))
        
    unit = tenant.current_unit
    ticket = MaintenanceRequest(
        rental_unit_id=unit.id,
        tenant_id=tenant.id,
        title=title,
        description=description,
        priority=priority,
        status='PENDING',
        reported_date=date.today()
    )
    db.session.add(ticket)
    
    # Notify property owner and management
    notif = Notification(
        landlord_id=unit.property.landlord_id if unit.property else None,
        title=f"New Maintenance Ticket: Unit {unit.unit_number} ({priority})",
        message=f"Tenant {tenant.full_name} reported: {title}\nDetails: {description}",
        channel='IN_APP',
        notification_type='MAINTENANCE_LOGGED',
        sent_status='SENT',
        sent_at=datetime.utcnow()
    )
    db.session.add(notif)
    db.session.commit()
    
    flash(f"Maintenance ticket '{title}' logged successfully. The property manager has been notified.", 'success')
    return redirect(url_for('tenant_portal.dashboard'))

@tenant_portal_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been securely signed out of the Tenant Portal.', 'info')
    return redirect(url_for('tenant_portal.login'))

