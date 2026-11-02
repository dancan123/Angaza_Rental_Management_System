from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db

class Role(db.Model):
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))
    is_system = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    users = db.relationship('User', back_populates='role', lazy='dynamic')
    permissions = db.relationship('Permission', secondary='role_permissions', back_populates='roles')

    def __repr__(self):
        return f"<Role {self.name}>"

class Permission(db.Model):
    __tablename__ = 'permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    module = db.Column(db.String(50), nullable=False, index=True)
    description = db.Column(db.String(255))
    
    roles = db.relationship('Role', secondary='role_permissions', back_populates='permissions')

    def __repr__(self):
        return f"<Permission {self.code}>"

class RolePermission(db.Model):
    __tablename__ = 'role_permissions'
    
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)
    permission_id = db.Column(db.Integer, db.ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True)

class Landlord(db.Model):
    __tablename__ = 'landlords'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, index=True)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), index=True)
    tax_pin = db.Column(db.String(50))
    address = db.Column(db.String(255))
    bank_account_info = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    properties = db.relationship('Property', back_populates='landlord', lazy='dynamic', cascade='all, delete-orphan')
    users = db.relationship('User', secondary='landlord_users', back_populates='landlords')
    notification_settings = db.relationship('NotificationSetting', back_populates='landlord', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Landlord {self.name}>"

class LandlordUser(db.Model):
    __tablename__ = 'landlord_users'
    
    landlord_id = db.Column(db.Integer, db.ForeignKey('landlords.id', ondelete='CASCADE'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30), index=True)
    full_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    role = db.relationship('Role', back_populates='users')
    landlords = db.relationship('Landlord', secondary='landlord_users', back_populates='users')
    audit_logs = db.relationship('AuditLog', back_populates='user', lazy='dynamic')
    notifications = db.relationship('Notification', back_populates='recipient', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_permission(self, permission_code):
        if not self.is_active or not self.role:
            return False
        if self.role.name == 'SUPERADMIN':
            return True
        return any(p.code == permission_code for p in self.role.permissions)

    def is_superadmin(self):
        return self.role and self.role.name == 'SUPERADMIN'

    def __repr__(self):
        return f"<User {self.username}>"

from app.extensions import login_manager

@login_manager.user_loader
def load_user(user_id):
    from app.extensions import db
    return db.session.get(User, int(user_id))

