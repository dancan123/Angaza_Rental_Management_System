import builtins
from datetime import datetime, date
from app.extensions import db
from app.utils.currency import format_currency

class Meter(db.Model):
    __tablename__ = 'meters'
    
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id', ondelete='CASCADE'), nullable=False, index=True)
    rental_unit_id = db.Column(db.Integer, db.ForeignKey('rental_units.id', ondelete='CASCADE'), nullable=False, index=True)
    
    meter_number = db.Column(db.String(50), nullable=False, index=True)
    meter_type = db.Column(db.String(20), nullable=False, default='WATER', index=True)  # WATER, ELECTRICITY
    rate_per_unit_cents = db.Column(db.Integer, nullable=False, default=15000)  # e.g. 150.00 KES per m3/kWh
    initial_reading = db.Column(db.Float, default=0.0)
    last_reading = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    property = db.relationship('Property')
    rental_unit = db.relationship('RentalUnit')
    readings = db.relationship('MeterReading', back_populates='meter', lazy='dynamic', cascade='all, delete-orphan')

    @builtins.property
    def rate_display(self):
        return format_currency(self.rate_per_unit_cents)

    def __repr__(self):
        return f"<Meter {self.meter_type} {self.meter_number} (Unit: {self.rental_unit_id})>"

class MeterReading(db.Model):
    __tablename__ = 'meter_readings'
    
    id = db.Column(db.Integer, primary_key=True)
    meter_id = db.Column(db.Integer, db.ForeignKey('meters.id', ondelete='CASCADE'), nullable=False, index=True)
    
    reading_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    previous_reading = db.Column(db.Float, nullable=False)
    current_reading = db.Column(db.Float, nullable=False)
    units_consumed = db.Column(db.Float, nullable=False)
    rate_per_unit_cents = db.Column(db.Integer, nullable=False)
    total_cost_cents = db.Column(db.Integer, nullable=False)
    
    billed_status = db.Column(db.String(20), default='PENDING', index=True)  # PENDING, BILLED
    rent_charge_id = db.Column(db.Integer, db.ForeignKey('rent_charges.id', ondelete='SET NULL'), nullable=True)
    photo_url = db.Column(db.String(255))
    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    meter = db.relationship('Meter', back_populates='readings')
    rent_charge = db.relationship('RentCharge')
    recorded_by = db.relationship('User', foreign_keys=[recorded_by_user_id])

    @property
    def cost_display(self):
        return format_currency(self.total_cost_cents)

    def __repr__(self):
        return f"<MeterReading Meter:{self.meter_id} Consumed:{self.units_consumed} Cost:{self.total_cost_cents}>"
