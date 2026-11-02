from datetime import datetime
from app.extensions import db

class Tenant(db.Model):
    __tablename__ = 'tenants'
    
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(60), nullable=False)
    last_name = db.Column(db.String(60), nullable=False)
    id_passport_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30), nullable=False, index=True)
    email = db.Column(db.String(120), index=True)
    emergency_contact = db.Column(db.String(100))
    emergency_phone = db.Column(db.String(30))
    physical_address = db.Column(db.String(255))
    occupation = db.Column(db.String(100))
    photo_url = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User')
    current_unit = db.relationship('RentalUnit', foreign_keys='RentalUnit.current_tenant_id', back_populates='current_tenant', uselist=False)
    documents = db.relationship('TenantDocument', back_populates='tenant', lazy='dynamic', cascade='all, delete-orphan')
    next_of_kin = db.relationship('NextOfKin', back_populates='tenant', lazy='dynamic', cascade='all, delete-orphan')
    leases = db.relationship('Lease', back_populates='tenant', lazy='dynamic', cascade='all, delete-orphan')
    bookings = db.relationship('Booking', back_populates='tenant', lazy='dynamic')
    payments = db.relationship('Payment', back_populates='tenant', lazy='dynamic')
    rent_charges = db.relationship('RentCharge', back_populates='tenant', lazy='dynamic')
    maintenance_requests = db.relationship('MaintenanceRequest', back_populates='tenant', lazy='dynamic')

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __repr__(self):
        return f"<Tenant {self.full_name} ({self.id_passport_number})>"

class TenantDocument(db.Model):
    __tablename__ = 'tenant_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    document_type = db.Column(db.String(50), nullable=False)  # NATIONAL_ID, PASSPORT, KRA_PIN, LEASE_AGREEMENT, OTHER
    document_name = db.Column(db.String(150), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    file_size_bytes = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    tenant = db.relationship('Tenant', back_populates='documents')

    def __repr__(self):
        return f"<TenantDocument {self.document_name}>"

class NextOfKin(db.Model):
    __tablename__ = 'next_of_kin'
    
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    relationship = db.Column(db.String(50), nullable=False)  # Spouse, Parent, Sibling, Child, Friend
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120))
    physical_address = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    tenant = db.relationship('Tenant', back_populates='next_of_kin')

    def __repr__(self):
        return f"<NextOfKin {self.full_name} ({self.relationship})>"

