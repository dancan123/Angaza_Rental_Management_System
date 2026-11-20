from datetime import datetime
from app.extensions import db
from app.utils.currency import format_currency

class HouseSeekerLead(db.Model):
    __tablename__ = 'house_seeker_leads'
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False, index=True)
    email = db.Column(db.String(120), nullable=True)
    
    # House seeker preferences
    preferred_unit_type = db.Column(db.String(50), nullable=True) # e.g. BEDSITTER, 1_BEDROOM, 2_BEDROOM, etc.
    preferred_locations = db.Column(db.String(255), nullable=True) # e.g. Kilimani, Westlands, Rongai, Karen
    max_budget_cents = db.Column(db.Integer, nullable=True, default=0)
    expected_move_in_date = db.Column(db.Date, nullable=True)
    
    # Preferred contact channel: WHATSAPP, SMS, EMAIL, PHONE
    preferred_contact_method = db.Column(db.String(30), default='WHATSAPP')
    notes = db.Column(db.Text, nullable=True)
    
    # Lead Status: NEW, CONTACTED, MATCHED, ARCHIVED
    status = db.Column(db.String(30), default='NEW', index=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def budget_display(self):
        if not self.max_budget_cents:
            return "Flexible"
        return format_currency(self.max_budget_cents)

    def __repr__(self):
        return f"<HouseSeekerLead {self.full_name} ({self.preferred_unit_type}: {self.phone})>"

class ExternalPropertyListing(db.Model):
    __tablename__ = 'external_property_listings'
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=True, index=True)
    owner_name = db.Column(db.String(120), nullable=False)
    owner_phone = db.Column(db.String(30), nullable=False, index=True)
    owner_email = db.Column(db.String(120), nullable=True)
    
    property_title = db.Column(db.String(150), nullable=False) # e.g. "Riverside Executive Residency"
    location = db.Column(db.String(255), nullable=False)       # e.g. "Riverside Drive, Nairobi"
    property_type = db.Column(db.String(50), default='APARTMENT')
    unit_type = db.Column(db.String(50), default='2_BEDROOM')
    bedrooms = db.Column(db.Integer, default=1)
    bathrooms = db.Column(db.Integer, default=1)
    monthly_rent_cents = db.Column(db.Integer, default=0)
    deposit_cents = db.Column(db.Integer, default=0)
    features = db.Column(db.Text, nullable=True)               # e.g. "Borehole, Lift, Balcony, Backup Generator"
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(255), nullable=True)
    youtube_url = db.Column(db.String(255), nullable=True)
    
    # Partner & Neighbor Extensions
    listing_type = db.Column(db.String(30), default='RENTAL')   # 'RENTAL', 'AIRBNB'
    daily_rate_cents = db.Column(db.Integer, default=0)
    commission_rate_pct = db.Column(db.Integer, default=10)     # e.g. 10% commission on deal
    is_partner_neighbour = db.Column(db.Boolean, default=True)
    
    # Status: PENDING, PUBLISHED, ALLOCATED, RENTED, ARCHIVED
    status = db.Column(db.String(30), default='PENDING', index=True)
    is_featured = db.Column(db.Boolean, default=False)

    # Allocation & Matching Data (Internal to Angaza staff)
    allocated_tenant_name = db.Column(db.String(120), nullable=True)
    allocated_tenant_phone = db.Column(db.String(30), nullable=True)
    allocated_at = db.Column(db.DateTime, nullable=True)
    allocation_notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def rent_display(self):
        return format_currency(self.monthly_rent_cents)

    @property
    def deposit_display(self):
        return format_currency(self.deposit_cents)

    @property
    def daily_rate_display(self):
        return format_currency(self.daily_rate_cents)

    @property
    def youtube_embed_url(self):
        if not self.youtube_url:
            return None
        import re
        url = self.youtube_url.strip()
        patterns = [
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})',
            r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]{11})',
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})',
        ]
        for p in patterns:
            match = re.search(p, url)
            if match:
                return f"https://www.youtube-nocookie.com/embed/{match.group(1)}"
        return url

    def __repr__(self):
        return f"<ExternalPropertyListing {self.property_title} ({self.status})>"


