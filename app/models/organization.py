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
    org_code = db.Column(db.String(30), unique=True, nullable=True, index=True)
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
    sms_credits = db.Column(db.Integer, default=50)
    enable_rentals = db.Column(db.Boolean, default=True)
    enable_hospitality = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    properties = db.relationship('Property', back_populates='organization', lazy='dynamic')
    users = db.relationship('User', back_populates='organization', lazy='dynamic')

    @property
    def business_code(self) -> str:
        return self.org_code or (self.slug.upper().replace('-', '_') if self.slug else f"ORG{self.id}")

    @property
    def is_trial(self) -> bool:
        return self.subscription_status == 'TRIAL'

    @property
    def days_remaining(self) -> int:
        if not self.subscription_expires_at:
            return 999
        from datetime import datetime as _dt
        diff = (self.subscription_expires_at - _dt.utcnow()).days
        return max(0, diff)

    def can_access_rental_module(self) -> bool:
        if self.enable_rentals is False:
            return False
        return self.subscription_tier in ['RENTAL_STANDARD', 'COMBINED_SUITE', 'ENTERPRISE']

    def can_access_hospitality_module(self) -> bool:
        if self.enable_hospitality is False:
            return False
        return self.subscription_tier in ['HOSPITALITY_STANDARD', 'COMBINED_SUITE', 'ENTERPRISE']

    def is_within_unit_limit(self, current_units_count: int) -> bool:
        return current_units_count < self.max_units

    def __repr__(self):
        return f"<Organization {self.name} ({self.subscription_tier}: {self.subscription_status})>"
