import builtins
from datetime import datetime
from app.extensions import db
from app.utils.currency import format_currency

class Property(db.Model):
    __tablename__ = 'properties'
    
    id = db.Column(db.Integer, primary_key=True)
    landlord_id = db.Column(db.Integer, db.ForeignKey('landlords.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    ref_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    property_type = db.Column(db.String(50), nullable=False, default='APARTMENT')  # APARTMENT, RESIDENTIAL, BEDSITTER, COMMERCIAL, etc.
    location = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(255))
    total_floors = db.Column(db.Integer, default=1)
    management_status = db.Column(db.String(20), default='ACTIVE', index=True)  # ACTIVE, INACTIVE
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    landlord = db.relationship('Landlord', back_populates='properties')
    buildings = db.relationship('Building', back_populates='property', lazy='dynamic', cascade='all, delete-orphan')
    rental_units = db.relationship('RentalUnit', back_populates='property', lazy='dynamic', cascade='all, delete-orphan')
    expenses = db.relationship('Expense', back_populates='property', lazy='dynamic', cascade='all, delete-orphan')
    bank_accounts = db.relationship('BankAccount', back_populates='property', lazy='dynamic')
    gateway_configs = db.relationship('PaymentGatewayConfig', back_populates='property', lazy='dynamic')

    def __repr__(self):
        return f"<Property {self.name} ({self.ref_number})>"

class Building(db.Model):
    __tablename__ = 'buildings'
    
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(50))
    description = db.Column(db.String(255))
    total_floors = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    property = db.relationship('Property', back_populates='buildings')
    floors = db.relationship('Floor', back_populates='building', lazy='dynamic', cascade='all, delete-orphan')
    rental_units = db.relationship('RentalUnit', back_populates='building', lazy='dynamic')

    def __repr__(self):
        return f"<Building {self.name}>"

class Floor(db.Model):
    __tablename__ = 'floors'
    
    id = db.Column(db.Integer, primary_key=True)
    building_id = db.Column(db.Integer, db.ForeignKey('buildings.id', ondelete='CASCADE'), nullable=False, index=True)
    floor_number = db.Column(db.Integer, nullable=False)
    floor_name = db.Column(db.String(50), nullable=False)  # e.g. "Ground Floor", "1st Floor"
    
    building = db.relationship('Building', back_populates='floors')
    rental_units = db.relationship('RentalUnit', back_populates='floor', lazy='dynamic')

    def __repr__(self):
        return f"<Floor {self.floor_name}>"

class RentalUnit(db.Model):
    __tablename__ = 'rental_units'
    
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id', ondelete='CASCADE'), nullable=False, index=True)
    building_id = db.Column(db.Integer, db.ForeignKey('buildings.id', ondelete='SET NULL'), nullable=True, index=True)
    floor_id = db.Column(db.Integer, db.ForeignKey('floors.id', ondelete='SET NULL'), nullable=True, index=True)
    
    unit_number = db.Column(db.String(50), nullable=False, index=True)  # e.g. "A101", "Shop 4"
    unit_type = db.Column(db.String(50), nullable=False, default='APARTMENT')  # Bedsitter, 1 Bedroom, 2 Bedroom, Shop, etc.
    rent_amount_cents = db.Column(db.Integer, nullable=False, default=0)
    deposit_amount_cents = db.Column(db.Integer, nullable=False, default=0)
    bedrooms = db.Column(db.Integer, default=1)
    bathrooms = db.Column(db.Integer, default=1)
    amenities = db.Column(db.Text)  # JSON or comma-separated list of amenities
    description = db.Column(db.Text)
    
    # Status: VACANT, OCCUPIED, RESERVED, MAINTENANCE, INACTIVE
    occupancy_status = db.Column(db.String(20), nullable=False, default='VACANT', index=True)
    current_tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='SET NULL'), nullable=True, index=True)
    availability_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    property = db.relationship('Property', back_populates='rental_units')
    building = db.relationship('Building', back_populates='rental_units')
    floor = db.relationship('Floor', back_populates='rental_units')
    current_tenant = db.relationship('Tenant', foreign_keys=[current_tenant_id], back_populates='current_unit')
    
    bookings = db.relationship('Booking', back_populates='rental_unit', lazy='dynamic', cascade='all, delete-orphan')
    leases = db.relationship('Lease', back_populates='rental_unit', lazy='dynamic', cascade='all, delete-orphan')
    maintenance_requests = db.relationship('MaintenanceRequest', back_populates='rental_unit', lazy='dynamic')
    expenses = db.relationship('Expense', back_populates='rental_unit', lazy='dynamic')

    __table_args__ = (
        db.UniqueConstraint('property_id', 'unit_number', name='uq_property_unit_number'),
    )

    @builtins.property
    def rent_display(self):
        return format_currency(self.rent_amount_cents)

    @builtins.property
    def deposit_display(self):
        return format_currency(self.deposit_amount_cents)

    def __repr__(self):
        return f"<RentalUnit {self.unit_number} ({self.occupancy_status})>"
