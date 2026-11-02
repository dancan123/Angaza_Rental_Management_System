from datetime import datetime
from app.extensions import db

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    setting_value = db.Column(db.Text)
    description = db.Column(db.String(255))
    is_public = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SystemSetting {self.setting_key}={self.setting_value}>"

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    action = db.Column(db.String(50), nullable=False, index=True)  # CREATE, UPDATE, DELETE, LOGIN, LOGOUT, REVERSAL, ALLOCATION
    entity_type = db.Column(db.String(50), nullable=False, index=True)  # Payment, Lease, Tenant, Unit, User, Setting
    entity_id = db.Column(db.String(50), index=True)
    old_values = db.Column(db.Text)  # JSON representation
    new_values = db.Column(db.Text)  # JSON representation
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user = db.relationship('User', back_populates='audit_logs')

    def __repr__(self):
        return f"<AuditLog {self.action} on {self.entity_type}:{self.entity_id}>"

class DatabaseBackup(db.Model):
    __tablename__ = 'database_backups'
    
    id = db.Column(db.Integer, primary_key=True)
    file_name = db.Column(db.String(150), unique=True, nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    file_size_bytes = db.Column(db.Integer, default=0)
    backup_type = db.Column(db.String(20), default='MANUAL')  # MANUAL, SCHEDULED
    status = db.Column(db.String(20), default='COMPLETED')     # COMPLETED, FAILED
    checksum = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<DatabaseBackup {self.file_name} ({self.status})>"

