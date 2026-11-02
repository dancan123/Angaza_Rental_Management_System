from datetime import datetime
from app.extensions import db
from app.utils.currency import format_currency

class Lease(db.Model):
    __tablename__ = 'leases'
    
    id = db.Column(db.Integer, primary_key=True)
    lease_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    rental_unit_id = db.Column(db.Integer, db.ForeignKey('rental_units.id', ondelete='RESTRICT'), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, index=True)
    
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    monthly_rent_cents = db.Column(db.Integer, nullable=False)
    deposit_cents = db.Column(db.Integer, nullable=False, default=0)
    payment_due_day = db.Column(db.Integer, default=5)  # e.g. 5th of every month
    notice_period_days = db.Column(db.Integer, default=30)
    terms_and_conditions = db.Column(db.Text)
    
    # Status: ACTIVE, EXPIRED, TERMINATED, RENEWED
    status = db.Column(db.String(25), default='ACTIVE', index=True)
    signed_at = db.Column(db.DateTime, default=datetime.utcnow)
    terminated_at = db.Column(db.DateTime)
    termination_reason = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    rental_unit = db.relationship('RentalUnit', back_populates='leases')
    tenant = db.relationship('Tenant', back_populates='leases')
    rent_charges = db.relationship('RentCharge', back_populates='lease', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def rent_display(self):
        return format_currency(self.monthly_rent_cents)

    @property
    def deposit_display(self):
        return format_currency(self.deposit_cents)

    def __repr__(self):
        return f"<Lease {self.lease_number} ({self.status})>"

class TenancyRecord(db.Model):
    __tablename__ = 'tenancy_records'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    rental_unit_id = db.Column(db.Integer, db.ForeignKey('rental_units.id', ondelete='CASCADE'), nullable=False, index=True)
    
    move_in_date = db.Column(db.Date, nullable=False)
    move_out_date = db.Column(db.Date)
    move_in_inspection_notes = db.Column(db.Text)
    move_out_inspection_notes = db.Column(db.Text)
    transfer_reason = db.Column(db.String(255))
    deposit_refunded_cents = db.Column(db.Integer, default=0)
    deposit_deductions_cents = db.Column(db.Integer, default=0)
    deduction_reason = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tenant = db.relationship('Tenant')
    rental_unit = db.relationship('RentalUnit')

    def __repr__(self):
        return f"<TenancyRecord Tenant:{self.tenant_id} Unit:{self.rental_unit_id}>"

