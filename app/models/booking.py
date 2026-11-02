from datetime import datetime
from app.extensions import db
from app.utils.currency import format_currency

class Booking(db.Model):
    __tablename__ = 'bookings'
    
    id = db.Column(db.Integer, primary_key=True)
    rental_unit_id = db.Column(db.Integer, db.ForeignKey('rental_units.id', ondelete='CASCADE'), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='SET NULL'), nullable=True, index=True)
    
    booking_reference = db.Column(db.String(50), unique=True, nullable=False, index=True)
    prospective_name = db.Column(db.String(120), nullable=False)
    prospective_phone = db.Column(db.String(30), nullable=False, index=True)
    prospective_email = db.Column(db.String(120))
    prospective_id_number = db.Column(db.String(50))
    
    booking_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    expected_move_in_date = db.Column(db.Date, nullable=False)
    booking_deposit_cents = db.Column(db.Integer, default=0)
    expiry_date = db.Column(db.Date, nullable=False)
    
    # Status: ACTIVE, CONFIRMED_MOVE_IN, CANCELLED, EXPIRED
    status = db.Column(db.String(25), default='ACTIVE', index=True)
    notes = db.Column(db.Text)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    rental_unit = db.relationship('RentalUnit', back_populates='bookings')
    tenant = db.relationship('Tenant', back_populates='bookings')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])

    @property
    def deposit_display(self):
        return format_currency(self.booking_deposit_cents)

    def __repr__(self):
        return f"<Booking {self.booking_reference} ({self.status})>"

