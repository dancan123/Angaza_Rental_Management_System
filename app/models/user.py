from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db

ROLE_HIERARCHY = {
    'SUPERADMIN': 100,
    'PROPERTY_MANAGER': 80,
    'ACCOUNTANT': 70,
    'LANDLORD': 50,
    'CARETAKER': 40,
    'RECEPTIONIST': 30,
    'STAFF': 30,
    'VIEWER': 20,
    'TENANT': 10
}

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

    @property
    def hierarchy_level(self):
        return ROLE_HIERARCHY.get(self.name.upper(), 10)

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

    @property
    def role_level(self):
        if not self.role:
            return 0
        return self.role.hierarchy_level

    def can_manage_user(self, target_user):
        """
        Determines if current user can activate, deactivate, or edit target user.
        Superadmin can manage any non-self user.
        Higher levels can manage strictly lower levels.
        """
        if not self.is_active or not self.role:
            return False
        if self.id == target_user.id:
            return False  # Cannot deactivate oneself
        if self.is_superadmin():
            return True
        if target_user.is_superadmin():
            return False  # Only superadmins can touch superadmins
        return self.has_permission('users.manage') and (self.role_level > target_user.role_level)

    def can_reset_password_for(self, target_user):
        """
        Determines if current user can reset password for target user.
        Superadmin can reset for anyone.
        Senior staff can reset for subordinate/junior roles.
        """
        if not self.is_active or not self.role:
            return False
        if self.is_superadmin():
            return True  # Superadmin is paramount system owner
        if target_user.is_superadmin():
            return False  # Junior/equal cannot reset Superadmin password
        if self.id == target_user.id:
            return True
        return self.has_permission('users.manage') and (self.role_level > target_user.role_level)

    def __repr__(self):
        return f"<User {self.username}>"

from app.extensions import login_manager

@login_manager.user_loader
def load_user(user_id):
    from app.extensions import db
    return db.session.get(User, int(user_id))

