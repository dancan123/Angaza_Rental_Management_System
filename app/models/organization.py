from datetime import datetime
from app.extensions import db

class Organization(db.Model):
    """
    SaaS Multi-Tenant Account / Organization entity.
    Isolates property management companies, estate agencies, and hospitality operators.
    Enforces modular subscription tiers and entitlement limits.
    """
    __tablename__ = 'organizations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False, index=True)
    slug = db.Column(db.String(60), unique=True, nullable=False, index=True)
    contact_email = db.Column(db.String(120), index=True)
    contact_phone = db.Column(db.String(30))
    tax_pin = db.Column(db.String(50))
    business_registration = db.Column(db.String(100))

    # Subscription tiers: RENTAL_STANDARD, HOSPITALITY_STANDARD, COMBINED_SUITE, ENTERPRISE
    subscription_tier = db.Column(db.String(30), nullable=False, default='COMBINED_SUITE', index=True)
    # Status: ACTIVE, TRIAL, SUSPENDED, EXPIRED
    subscription_status = db.Column(db.String(20), nullable=False, default='ACTIVE', index=True)
    subscription_expires_at = db.Column(db.DateTime)

    # Entitlement Limits
    max_properties = db.Column(db.Integer, default=50)
    max_units = db.Column(db.Integer, default=250)
    max_users = db.Column(db.Integer, default=15)
    is_active = db.Column(db.Boolean, default=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    properties = db.relationship('Property', back_populates='organization', lazy='dynamic')
    users = db.relationship('User', back_populates='organization', lazy='dynamic')

    def can_access_rental_module(self) -> bool:
        return self.subscription_tier in ['RENTAL_STANDARD', 'COMBINED_SUITE', 'ENTERPRISE']

    def can_access_hospitality_module(self) -> bool:
        return self.subscription_tier in ['HOSPITALITY_STANDARD', 'COMBINED_SUITE', 'ENTERPRISE']

    def is_within_unit_limit(self, current_units_count: int) -> bool:
        return current_units_count < self.max_units

    def __repr__(self):
        return f"<Organization {self.name} ({self.subscription_tier}: {self.subscription_status})>"
