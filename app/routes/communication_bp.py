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

    # Active properties and potential recipients
    properties = Property.query.filter_by(management_status='ACTIVE').all()
    recipients = User.query.filter(User.id != user_id, User.is_active.is_(True)).all()

    return render_template(
        'communication/index.html',
        inbox=inbox,
        outbox=outbox,
        notifications=notifications,
        properties=properties,
        recipients=recipients,
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
