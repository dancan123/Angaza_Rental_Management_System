"""
RoomPricingRule - Seasonal / Weekend / Event pricing rules for Hospitality Module.
Allows configuring date-range multipliers or flat override rates for specific units or all units.
"""
from datetime import datetime, date
from app.extensions import db
from app.utils.currency import format_currency


class RoomPricingRule(db.Model):
    """
    Flexible pricing rule system for hospitality units.
    Rules can apply to a specific unit or globally (rental_unit_id=NULL).
    Priority order: unit-specific rule > global rule > unit default rate.
    """
    __tablename__ = 'room_pricing_rules'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    # Null = applies to ALL units; set to restrict to one unit
    rental_unit_id = db.Column(db.Integer, db.ForeignKey('rental_units.id', ondelete='CASCADE'), nullable=True, index=True)

    # Date range (inclusive)
    start_date = db.Column(db.Date, nullable=False, index=True)
    end_date = db.Column(db.Date, nullable=False, index=True)

    # Rule type: MULTIPLIER (percentage markup/discount) or FLAT_RATE (fixed daily rate)
    rule_type = db.Column(db.String(20), nullable=False, default='MULTIPLIER')

    # For MULTIPLIER: 1.5 = +50%, 0.8 = -20%
    multiplier = db.Column(db.Float, default=1.0)
    # For FLAT_RATE: exact daily rate in KES cents
    flat_rate_cents = db.Column(db.Integer, default=0)

    # Day-of-week mask (comma-separated: MON,TUE,WED,THU,FRI,SAT,SUN; empty = all days)
    days_of_week = db.Column(db.String(50), default='')

    # Pricing category for display
    # PEAK_SEASON, LOW_SEASON, WEEKEND_PREMIUM, HOLIDAY, EVENT, DISCOUNT, CUSTOM
    category = db.Column(db.String(30), default='CUSTOM', index=True)

    is_active = db.Column(db.Boolean, default=True, index=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rental_unit = db.relationship('RentalUnit', foreign_keys=[rental_unit_id])

    def applies_on_date(self, check_date: date) -> bool:
        """Check if this rule applies on a specific date."""
        if not (self.start_date <= check_date <= self.end_date):
            return False
        if self.days_of_week:
            day_name = check_date.strftime('%A').upper()[:3]  # MON, TUE, etc.
            allowed = [d.strip().upper()[:3] for d in self.days_of_week.split(',')]
            if day_name not in allowed:
                return False
        return True

    def compute_rate_cents(self, base_rate_cents: int) -> int:
        """Compute the effective daily rate in cents given a base rate."""
        if self.rule_type == 'FLAT_RATE':
            return max(1, self.flat_rate_cents)
        else:
            return max(1, int(base_rate_cents * self.multiplier))

    @property
    def flat_rate_display(self):
        return format_currency(self.flat_rate_cents)

    @property
    def multiplier_pct_display(self):
        pct = round((self.multiplier - 1) * 100, 1)
        sign = '+' if pct >= 0 else ''
        return f"{sign}{pct}%"

    def __repr__(self):
        return f"<RoomPricingRule '{self.name}' {self.start_date}→{self.end_date}>"
