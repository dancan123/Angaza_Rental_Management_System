from datetime import datetime
from app.extensions import db
from app.utils.currency import format_currency

class Guest(db.Model):
    __tablename__ = 'guests'

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(60), nullable=False)
    last_name = db.Column(db.String(60), nullable=False)
    phone = db.Column(db.String(30), nullable=False, index=True)
    email = db.Column(db.String(120), index=True)
    id_passport_number = db.Column(db.String(50), index=True)
    nationality = db.Column(db.String(60), default='Kenyan')
    emergency_contact = db.Column(db.String(100))
    emergency_phone = db.Column(db.String(30))
    special_notes = db.Column(db.Text)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organization = db.relationship('Organization')
    reservations = db.relationship('HospitalityReservation', back_populates='guest', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __repr__(self):
        return f"<Guest {self.full_name} ({self.phone})>"

class HospitalityReservation(db.Model):
    __tablename__ = 'hospitality_reservations'

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id', ondelete='SET NULL'), nullable=True, index=True)
    reservation_code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    guest_id = db.Column(db.Integer, db.ForeignKey('guests.id', ondelete='CASCADE'), nullable=False, index=True)
    rental_unit_id = db.Column(db.Integer, db.ForeignKey('rental_units.id', ondelete='RESTRICT'), nullable=False, index=True)

    check_in_date = db.Column(db.Date, nullable=False, index=True)
    check_out_date = db.Column(db.Date, nullable=False, index=True)
    num_guests = db.Column(db.Integer, nullable=False, default=1)
    num_nights = db.Column(db.Integer, nullable=False, default=1)

    daily_rate_cents = db.Column(db.Integer, nullable=False, default=0)
    total_stay_cents = db.Column(db.Integer, nullable=False, default=0)
    paid_amount_cents = db.Column(db.Integer, default=0)

    # Booking source: DIRECT, AIRBNB, BOOKING_COM, WALK_IN, WEBSITE
    booking_source = db.Column(db.String(30), nullable=False, default='DIRECT', index=True)
    # Status: CONFIRMED, CHECKED_IN, CHECKED_OUT, CANCELLED
    status = db.Column(db.String(25), nullable=False, default='CONFIRMED', index=True)

    actual_check_in_time = db.Column(db.DateTime)
    actual_check_out_time = db.Column(db.DateTime)
    special_requests = db.Column(db.Text)

    payment_method = db.Column(db.String(30), default='MPESA')
    payment_reference = db.Column(db.String(100))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    guest = db.relationship('Guest', back_populates='reservations')
    rental_unit = db.relationship('RentalUnit')
    organization = db.relationship('Organization')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])

    @property
    def total_stay_display(self):
        return format_currency(self.total_stay_cents)

    @property
    def daily_rate_display(self):
        return format_currency(self.daily_rate_cents)

    @property
    def paid_amount_display(self):
        return format_currency(self.paid_amount_cents)

    @property
    def balance_cents(self):
        return max(0, self.total_stay_cents - self.paid_amount_cents)

    @property
    def balance_display(self):
        return format_currency(self.balance_cents)

    def __repr__(self):
        return f"<HospitalityReservation {self.reservation_code} ({self.status})>"

class HousekeepingTask(db.Model):
    __tablename__ = 'housekeeping_tasks'

    id = db.Column(db.Integer, primary_key=True)
    rental_unit_id = db.Column(db.Integer, db.ForeignKey('rental_units.id', ondelete='CASCADE'), nullable=False, index=True)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)

    # Task type: TURNOVER_CLEAN, DAILY_REFRESH, DEEP_CLEAN, INSPECTION
    task_type = db.Column(db.String(30), nullable=False, default='TURNOVER_CLEAN')
    # Priority: LOW, NORMAL, HIGH, URGENT
    priority = db.Column(db.String(20), default='NORMAL')
    # Status: PENDING, IN_PROGRESS, COMPLETED
    status = db.Column(db.String(20), default='PENDING', index=True)

    scheduled_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    notes = db.Column(db.Text)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rental_unit = db.relationship('RentalUnit')
    assigned_user = db.relationship('User', foreign_keys=[assigned_user_id])

    def __repr__(self):
        return f"<HousekeepingTask Unit:{self.rental_unit_id} ({self.status})>"
