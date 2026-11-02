import builtins
from datetime import datetime
from app.extensions import db
from app.utils.currency import format_currency

class RentCharge(db.Model):
    __tablename__ = 'rent_charges'
    
    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey('leases.id', ondelete='SET NULL'), nullable=True, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, index=True)
    rental_unit_id = db.Column(db.Integer, db.ForeignKey('rental_units.id', ondelete='RESTRICT'), nullable=False, index=True)
    
    invoice_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    # RENT, DEPOSIT, LATE_FEE, WATER, ELECTRICITY, SERVICE_CHARGE, PENALTY, ADJUSTMENT
    charge_type = db.Column(db.String(30), nullable=False, default='RENT', index=True)
    period_month = db.Column(db.Integer, nullable=False)  # 1-12
    period_year = db.Column(db.Integer, nullable=False)   # e.g. 2026
    
    amount_cents = db.Column(db.Integer, nullable=False)
    amount_paid_cents = db.Column(db.Integer, default=0)
    due_date = db.Column(db.Date, nullable=False, index=True)
    
    # UNPAID, PARTIALLY_PAID, PAID, WAIVED
    status = db.Column(db.String(25), default='UNPAID', index=True)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    lease = db.relationship('Lease', back_populates='rent_charges')
    tenant = db.relationship('Tenant', back_populates='rent_charges')
    rental_unit = db.relationship('RentalUnit')
    allocations = db.relationship('PaymentAllocation', back_populates='rent_charge', lazy='dynamic', cascade='all, delete-orphan')

    @property
    def balance_cents(self):
        return max(0, self.amount_cents - self.amount_paid_cents)

    @builtins.property
    def amount_display(self):
        return format_currency(self.amount_cents)

    @property
    def paid_display(self):
        return format_currency(self.amount_paid_cents)

    @property
    def balance_display(self):
        return format_currency(self.balance_cents)

    def __repr__(self):
        return f"<RentCharge {self.invoice_number} ({self.charge_type}: {self.status})>"

class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='RESTRICT'), nullable=False, index=True)
    rental_unit_id = db.Column(db.Integer, db.ForeignKey('rental_units.id', ondelete='RESTRICT'), nullable=False, index=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id', ondelete='RESTRICT'), nullable=False, index=True)
    
    payment_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    receipt_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    payment_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date, index=True)
    
    # MPESA_TILL, MPESA_PAYBILL, BANK_TRANSFER, CASH, CHEQUE, OTHER
    payment_method = db.Column(db.String(30), nullable=False, default='CASH', index=True)
    transaction_reference = db.Column(db.String(100), unique=True, nullable=True, index=True)
    
    # PENDING, CONFIRMED, FAILED, REVERSED
    payment_status = db.Column(db.String(25), default='PENDING', index=True)
    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    description = db.Column(db.Text)
    verified_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    tenant = db.relationship('Tenant', back_populates='payments')
    rental_unit = db.relationship('RentalUnit')
    property = db.relationship('Property')
    recorded_by = db.relationship('User', foreign_keys=[recorded_by_user_id])
    allocations = db.relationship('PaymentAllocation', back_populates='payment', lazy='dynamic', cascade='all, delete-orphan')
    reversal = db.relationship('PaymentReversal', back_populates='payment', uselist=False, cascade='all, delete-orphan')

    @builtins.property
    def amount_display(self):
        return format_currency(self.amount_cents)

    def __repr__(self):
        return f"<Payment {self.receipt_number} ({self.payment_status}: {self.amount_cents})>"

class PaymentAllocation(db.Model):
    __tablename__ = 'payment_allocations'
    
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id', ondelete='CASCADE'), nullable=False, index=True)
    rent_charge_id = db.Column(db.Integer, db.ForeignKey('rent_charges.id', ondelete='CASCADE'), nullable=False, index=True)
    allocated_amount_cents = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    payment = db.relationship('Payment', back_populates='allocations')
    rent_charge = db.relationship('RentCharge', back_populates='allocations')

    @property
    def amount_display(self):
        return format_currency(self.allocated_amount_cents)

    def __repr__(self):
        return f"<PaymentAllocation Pay:{self.payment_id} Charge:{self.rent_charge_id} Cents:{self.allocated_amount_cents}>"

class PaymentReversal(db.Model):
    __tablename__ = 'payment_reversals'
    
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id', ondelete='CASCADE'), unique=True, nullable=False)
    reversed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    original_amount_cents = db.Column(db.Integer, nullable=False)
    reversal_reason = db.Column(db.Text, nullable=False)
    reversed_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    payment = db.relationship('Payment', back_populates='reversal')
    reversed_by = db.relationship('User', foreign_keys=[reversed_by_user_id])

    def __repr__(self):
        return f"<PaymentReversal Payment:{self.payment_id}>"
