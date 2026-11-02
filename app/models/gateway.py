from datetime import datetime
from app.extensions import db
from app.utils.currency import format_currency

class PaymentGatewayConfig(db.Model):
    __tablename__ = 'payment_gateway_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    landlord_id = db.Column(db.Integer, db.ForeignKey('landlords.id', ondelete='CASCADE'), nullable=True, index=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id', ondelete='CASCADE'), nullable=True, index=True)
    
    # MPESA_PAYBILL, MPESA_TILL, BANK
    gateway_type = db.Column(db.String(30), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)  # Display name e.g. "Primary Paybill 247247"
    shortcode = db.Column(db.String(50))              # Paybill or Store Number
    till_number = db.Column(db.String(50))            # Buy Goods Till
    consumer_key = db.Column(db.String(255))
    consumer_secret = db.Column(db.String(255))
    passkey = db.Column(db.String(255))
    callback_url = db.Column(db.String(255))
    account_reference_pattern = db.Column(db.String(100), default='{UNIT_NUMBER}')
    
    is_active = db.Column(db.Boolean, default=True)
    is_sandbox = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    landlord = db.relationship('Landlord')
    property = db.relationship('Property', back_populates='gateway_configs')

    def __repr__(self):
        return f"<PaymentGatewayConfig {self.name} ({self.gateway_type})>"

class PaymentCallback(db.Model):
    __tablename__ = 'payment_callbacks'
    
    id = db.Column(db.Integer, primary_key=True)
    gateway_type = db.Column(db.String(30), nullable=False, index=True)
    transaction_reference = db.Column(db.String(100), unique=True, nullable=False, index=True)
    payload_json = db.Column(db.Text, nullable=False)
    
    # RECEIVED, VERIFIED, PROCESSED, FAILED, DUPLICATE
    status = db.Column(db.String(25), default='RECEIVED', index=True)
    error_message = db.Column(db.Text)
    processed_payment_id = db.Column(db.Integer, db.ForeignKey('payments.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    processed_payment = db.relationship('Payment')

    def __repr__(self):
        return f"<PaymentCallback {self.transaction_reference} ({self.status})>"

class BankAccount(db.Model):
    __tablename__ = 'bank_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    landlord_id = db.Column(db.Integer, db.ForeignKey('landlords.id', ondelete='CASCADE'), nullable=True, index=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id', ondelete='CASCADE'), nullable=True, index=True)
    
    bank_name = db.Column(db.String(100), nullable=False)
    account_name = db.Column(db.String(150), nullable=False)
    account_number = db.Column(db.String(50), nullable=False, index=True)
    branch = db.Column(db.String(100))
    currency = db.Column(db.String(10), default='KES')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    landlord = db.relationship('Landlord')
    property = db.relationship('Property', back_populates='bank_accounts')
    transactions = db.relationship('BankTransaction', back_populates='bank_account', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<BankAccount {self.bank_name} - {self.account_number}>"

class BankTransaction(db.Model):
    __tablename__ = 'bank_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    bank_account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id', ondelete='CASCADE'), nullable=False, index=True)
    transaction_date = db.Column(db.Date, nullable=False, index=True)
    value_date = db.Column(db.Date)
    reference = db.Column(db.String(100), index=True)
    description = db.Column(db.Text, nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    transaction_type = db.Column(db.String(10), default='CREDIT')  # CREDIT, DEBIT
    
    # UNMATCHED, MATCHED, MANUALLY_RECONCILED, IGNORED
    reconciliation_status = db.Column(db.String(25), default='UNMATCHED', index=True)
    matched_payment_id = db.Column(db.Integer, db.ForeignKey('payments.id', ondelete='SET NULL'), nullable=True)
    reconciled_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reconciled_at = db.Column(db.DateTime)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    bank_account = db.relationship('BankAccount', back_populates='transactions')
    matched_payment = db.relationship('Payment')
    reconciled_by = db.relationship('User', foreign_keys=[reconciled_by_user_id])

    @property
    def amount_display(self):
        return format_currency(self.amount_cents)

    def __repr__(self):
        return f"<BankTransaction Ref:{self.reference} ({self.reconciliation_status})>"

