from datetime import datetime
from app.extensions import db

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    landlord_id = db.Column(db.Integer, db.ForeignKey('landlords.id', ondelete='CASCADE'), nullable=True, index=True)
    
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    # Channel: SMS, EMAIL, WHATSAPP, IN_APP
    channel = db.Column(db.String(20), nullable=False, default='IN_APP', index=True)
    # Type: RENT_PAYMENT_CONFIRMED, RENT_OVERDUE, NEW_TENANT, BOOKING_CREATED, TENANT_MOVE_OUT, MAINTENANCE_LOGGED, UNMATCHED_PAYMENT
    notification_type = db.Column(db.String(50), nullable=False, index=True)
    
    is_read = db.Column(db.Boolean, default=False, index=True)
    # Status: PENDING, SENT, FAILED
    sent_status = db.Column(db.String(20), default='PENDING', index=True)
    error_details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    sent_at = db.Column(db.DateTime)
    
    recipient = db.relationship('User', back_populates='notifications')
    landlord = db.relationship('Landlord')

    def __repr__(self):
        return f"<Notification {self.title} ({self.channel}: {self.sent_status})>"

class NotificationSetting(db.Model):
    __tablename__ = 'notification_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    landlord_id = db.Column(db.Integer, db.ForeignKey('landlords.id', ondelete='CASCADE'), nullable=False, index=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    
    enable_sms = db.Column(db.Boolean, default=True)
    enable_email = db.Column(db.Boolean, default=True)
    enable_in_app = db.Column(db.Boolean, default=True)
    sms_template = db.Column(db.Text)
    email_template = db.Column(db.Text)
    
    landlord = db.relationship('Landlord', back_populates='notification_settings')

    __table_args__ = (
        db.UniqueConstraint('landlord_id', 'event_type', name='uq_landlord_event_setting'),
    )

    def __repr__(self):
        return f"<NotificationSetting Landlord:{self.landlord_id} Event:{self.event_type}>"

class InternalMessage(db.Model):
    __tablename__ = 'internal_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id', ondelete='CASCADE'), nullable=True, index=True)
    unit_id = db.Column(db.Integer, db.ForeignKey('rental_units.id', ondelete='SET NULL'), nullable=True)
    
    subject = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    # Message types: REQUEST, INCIDENT, MAINTENANCE, GENERAL
    message_type = db.Column(db.String(50), default='REQUEST', index=True)
    # Priority: LOW, NORMAL, HIGH, URGENT
    priority = db.Column(db.String(20), default='NORMAL', index=True)
    # Status: OPEN, IN_PROGRESS, RESOLVED, CLOSED
    status = db.Column(db.String(20), default='OPEN', index=True)
    response = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    resolved_at = db.Column(db.DateTime)
    
    sender = db.relationship('User', foreign_keys=[sender_id])
    recipient = db.relationship('User', foreign_keys=[recipient_id])
    property = db.relationship('Property')
    rental_unit = db.relationship('RentalUnit')

    def __repr__(self):
        return f"<InternalMessage {self.subject} ({self.status})>"


