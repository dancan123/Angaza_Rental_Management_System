import builtins
from datetime import datetime
from app.extensions import db
from app.utils.currency import format_currency

class Expense(db.Model):
    __tablename__ = 'expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id', ondelete='CASCADE'), nullable=False, index=True)
    rental_unit_id = db.Column(db.Integer, db.ForeignKey('rental_units.id', ondelete='SET NULL'), nullable=True, index=True)
    
    # REPAIRS, PLUMBING, ELECTRICITY, WATER, SECURITY, CLEANING, GARBAGE, INSURANCE, TAXES, MANAGEMENT_FEE, OTHER
    category = db.Column(db.String(50), nullable=False, index=True)
    amount_cents = db.Column(db.Integer, nullable=False)
    expense_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date, index=True)
    supplier_name = db.Column(db.String(120))
    description = db.Column(db.Text, nullable=False)
    receipt_file_url = db.Column(db.String(255))
    recorded_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    property = db.relationship('Property', back_populates='expenses')
    rental_unit = db.relationship('RentalUnit', back_populates='expenses')
    recorded_by = db.relationship('User', foreign_keys=[recorded_by_user_id])
    maintenance_records = db.relationship('MaintenanceRecord', back_populates='expense', lazy='dynamic')

    @builtins.property
    def amount_display(self):
        return format_currency(self.amount_cents)

    def __repr__(self):
        return f"<Expense {self.category}: {self.amount_cents}>"

class MaintenanceRequest(db.Model):
    __tablename__ = 'maintenance_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    rental_unit_id = db.Column(db.Integer, db.ForeignKey('rental_units.id', ondelete='CASCADE'), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='SET NULL'), nullable=True, index=True)
    
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    # Priority: LOW, MEDIUM, HIGH, EMERGENCY
    priority = db.Column(db.String(20), default='MEDIUM', index=True)
    # Status: PENDING, ASSIGNED, IN_PROGRESS, RESOLVED, CANCELLED
    status = db.Column(db.String(25), default='PENDING', index=True)
    
    reported_date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    assigned_to_technician = db.Column(db.String(100))
    technician_contact = db.Column(db.String(50))
    resolved_date = db.Column(db.Date)
    photo_url = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    rental_unit = db.relationship('RentalUnit', back_populates='maintenance_requests')
    tenant = db.relationship('Tenant', back_populates='maintenance_requests')
    records = db.relationship('MaintenanceRecord', back_populates='maintenance_request', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<MaintenanceRequest {self.title} ({self.status})>"

class MaintenanceRecord(db.Model):
    __tablename__ = 'maintenance_records'
    
    id = db.Column(db.Integer, primary_key=True)
    maintenance_request_id = db.Column(db.Integer, db.ForeignKey('maintenance_requests.id', ondelete='CASCADE'), nullable=False, index=True)
    expense_id = db.Column(db.Integer, db.ForeignKey('expenses.id', ondelete='SET NULL'), nullable=True)
    
    work_summary = db.Column(db.Text, nullable=False)
    cost_cents = db.Column(db.Integer, default=0)
    completed_by = db.Column(db.String(100))
    completion_date = db.Column(db.Date, default=datetime.utcnow().date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    maintenance_request = db.relationship('MaintenanceRequest', back_populates='records')
    expense = db.relationship('Expense', back_populates='maintenance_records')

    @property
    def cost_display(self):
        return format_currency(self.cost_cents)

    def __repr__(self):
        return f"<MaintenanceRecord Req:{self.maintenance_request_id} Cost:{self.cost_cents}>"
