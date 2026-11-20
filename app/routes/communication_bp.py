from datetime import datetime
from typing import Any, cast
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models.communication import InternalMessage, Notification
from app.models.property import Property
from app.models.user import User

communication_bp = Blueprint('communication', __name__, url_prefix='/communication')

@communication_bp.route('/')
@login_required
def index():
    tab = request.args.get('tab', 'inbox')
    user = cast(Any, current_user)
    user_id = user.id
    
    # Query received messages
    if user.is_superadmin():
        received_query = InternalMessage.query
    else:
        received_query = InternalMessage.query.filter(
            (InternalMessage.recipient_id == user_id) | 
            (InternalMessage.recipient_id.is_(None))
        )
    inbox = received_query.order_by(InternalMessage.created_at.desc()).all()

    # Query sent messages
    outbox = InternalMessage.query.filter_by(sender_id=user_id).order_by(InternalMessage.created_at.desc()).all()

    # System notifications feed
    notifications = Notification.query.order_by(Notification.created_at.desc()).limit(50).all()

    # Active properties and potential recipients — scoped to organization
    org_id = getattr(current_user, 'organization_id', None) if not current_user.is_superadmin() else None
    if org_id:
        properties = Property.query.filter_by(management_status='ACTIVE', organization_id=org_id).all()
        recipients = User.query.filter(User.id != user_id, User.is_active.is_(True), User.organization_id == org_id).all()
    else:
        properties = Property.query.filter_by(management_status='ACTIVE').all()
        recipients = User.query.filter(User.id != user_id, User.is_active.is_(True)).all()

    # Twilio configuration
    from app.services.sms_service import SmsService
    twilio_creds = SmsService.get_twilio_credentials()

    return render_template(
        'communication/index.html',
        inbox=inbox,
        outbox=outbox,
        notifications=notifications,
        properties=properties,
        recipients=recipients,
        twilio_creds=twilio_creds,
        active_tab=tab
    )

@communication_bp.route('/send', methods=['POST'])
@login_required
def send_message():
    user = cast(Any, current_user)
    user_id = user.id
    recipient_id = request.form.get('recipient_id', type=int)
    property_id = request.form.get('property_id', type=int)
    unit_id = request.form.get('unit_id', type=int)
    subject = request.form.get('subject', '').strip()
    message = request.form.get('message', '').strip()
    msg_type = request.form.get('message_type', 'REQUEST')
    priority = request.form.get('priority', 'NORMAL')

    if not subject or not message:
        flash('Subject and message content are required.', 'danger')
        return redirect(url_for('communication.index', tab='new'))

    msg = InternalMessage(
        sender_id=user_id,
        recipient_id=recipient_id if recipient_id else None,
        property_id=property_id if property_id else None,
        unit_id=unit_id if unit_id else None,
        subject=subject,
        message=message,
        message_type=msg_type,
        priority=priority,
        status='OPEN'
    )
    db.session.add(msg)

    # In-App Notification alert for the recipient
    if recipient_id:
        role_label = user.role.display_name if getattr(user, 'role', None) else 'Staff'
        notif = Notification(
            recipient_user_id=recipient_id,
            title=f"New Staff Message: {subject}",
            message=f"From {user.full_name} ({role_label}):\n{message[:200]}",
            channel='IN_APP',
            notification_type='STAFF_MESSAGE',
            sent_status='SENT',
            sent_at=datetime.utcnow()
        )
        db.session.add(notif)

    db.session.commit()
    flash(f"Internal communication message '{subject}' dispatched successfully.", 'success')
    return redirect(url_for('communication.index', tab='outbox'))

@communication_bp.route('/<int:msg_id>/reply', methods=['POST'])
@login_required
def reply_message(msg_id):
    msg = db.session.get(InternalMessage, msg_id)
    if not msg:
        from flask import abort; abort(404)
    response_text = request.form.get('response', '').strip()
    new_status = request.form.get('status', 'RESOLVED')

    if response_text:
        msg.response = response_text
    msg.status = new_status
    if new_status in ['RESOLVED', 'CLOSED']:
        msg.resolved_at = datetime.utcnow()

    db.session.commit()
    flash(f"Response saved and request marked as {new_status}.", 'success')
    return redirect(url_for('communication.index', tab='inbox'))

@communication_bp.route('/twilio/save', methods=['POST'])
@login_required
def save_twilio_config():
    user = cast(Any, current_user)
    if not user.is_superadmin() and not user.has_permission('settings.manage'):
        flash('Unauthorized: Administrative permission required to update Twilio settings.', 'danger')
        return redirect(url_for('communication.index', tab='sms'))

    from app.services.personalization_service import PersonalizationService
    sid = request.form.get('twilio_account_sid', '').strip()
    token = request.form.get('twilio_auth_token', '').strip()
    from_num = request.form.get('twilio_from_number', '').strip()
    enabled = 'true' if request.form.get('twilio_sms_enabled') else 'false'

    PersonalizationService.set_setting('twilio_account_sid', sid, 'Twilio Account SID for live SMS')
    PersonalizationService.set_setting('twilio_auth_token', token, 'Twilio Auth Token')
    PersonalizationService.set_setting('twilio_from_number', from_num, 'Twilio verified Sender ID or Phone Number')
    PersonalizationService.set_setting('twilio_sms_enabled', enabled, 'Flag indicating whether live SMS dispatch is active')

    flash('Twilio SMS gateway configuration saved successfully.', 'success')
    return redirect(url_for('communication.index', tab='sms'))

@communication_bp.route('/twilio/test', methods=['POST'])
@login_required
def test_twilio_sms():
    phone = request.form.get('test_phone', '').strip()
    msg = request.form.get('test_message', 'Test message from Angaza Property Management System. Twilio gateway operational!').strip()

    if not phone:
        flash('Recipient phone number is required for test SMS.', 'danger')
        return redirect(url_for('communication.index', tab='sms'))

    from app.services.sms_service import SmsService
    res = SmsService.send_sms(to_phone=phone, message=msg, notification_type='TEST_SMS')

    if res.get('success'):
        if res.get('simulated'):
            flash(f"Test SMS simulation logged successfully for {phone}. (Twilio credentials not configured/active)", 'info')
        else:
            flash(f"Live Test SMS successfully dispatched to {phone} via Twilio! (SID: {res.get('sid')})", 'success')
    else:
        flash(f"Twilio SMS dispatch failed: {res.get('error')}", 'danger')

    return redirect(url_for('communication.index', tab='sms'))

@communication_bp.route('/bulk-sms', methods=['POST'])
@login_required
def send_bulk_sms():
    user = cast(Any, current_user)
    if not user.has_permission('tenants.manage') and not user.is_superadmin():
        flash('Unauthorized: Permission required to send bulk SMS.', 'danger')
        return redirect(url_for('communication.index', tab='bulk'))

    property_id = request.form.get('property_id', type=int)
    message = request.form.get('bulk_message', '').strip()

    if not message:
        flash('Message text is required for bulk dispatch.', 'danger')
        return redirect(url_for('communication.index', tab='bulk'))

    from app.models.tenant import Tenant
    from app.models.property import RentalUnit
    from app.services.sms_service import SmsService

    query = Tenant.query.filter_by(is_active=True)
    if property_id:
        query = query.join(RentalUnit, Tenant.id == RentalUnit.current_tenant_id).filter(RentalUnit.property_id == property_id)

    tenants = query.all()
    count = 0
    for t in tenants:
        if t.phone:
            personalized_msg = message.replace('{name}', t.first_name).replace('{full_name}', t.full_name)
            SmsService.send_sms(to_phone=t.phone, message=personalized_msg, notification_type='BULK_SMS')
            count += 1

    flash(f"Bulk SMS broadcast queued and dispatched to {count} active tenant(s).", 'success')
    return redirect(url_for('communication.index', tab='bulk'))


@communication_bp.route('/sms-history')
@login_required
def sms_history():
    """SMS delivery history and status report."""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    ntype_filter = request.args.get('type', '')
    search = request.args.get('q', '').strip()

    query = Notification.query.filter(Notification.channel == 'SMS')
    if status_filter:
        query = query.filter(Notification.sent_status == status_filter)
    if ntype_filter:
        query = query.filter(Notification.notification_type == ntype_filter)
    if search:
        query = query.filter(
            Notification.message.ilike(f'%{search}%') |
            Notification.title.ilike(f'%{search}%')
        )

    pagination = query.order_by(Notification.created_at.desc()).paginate(page=page, per_page=25, error_out=False)
    sms_logs = pagination.items

    # Summary stats
    total_sent = Notification.query.filter_by(channel='SMS', sent_status='SENT').count()
    total_failed = Notification.query.filter_by(channel='SMS', sent_status='FAILED').count()
    total_pending = Notification.query.filter_by(channel='SMS', sent_status='PENDING').count()
    total_simulated = Notification.query.filter(
        Notification.channel == 'SMS',
        Notification.error_details.ilike('%simulated%')
    ).count()

    return render_template(
        'communication/sms_history.html',
        sms_logs=sms_logs,
        pagination=pagination,
        total_sent=total_sent,
        total_failed=total_failed,
        total_pending=total_pending,
        total_simulated=total_simulated,
        status_filter=status_filter,
        ntype_filter=ntype_filter,
        search=search
    )

