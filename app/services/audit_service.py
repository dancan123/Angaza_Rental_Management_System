import json
from flask import request
from flask_login import current_user
from app.extensions import db
from app.models.system import AuditLog

class AuditService:
    @staticmethod
    def log(action: str, entity_type: str, entity_id=None, old_values=None, new_values=None, user_id=None):
        try:
            effective_user_id = user_id
            if effective_user_id is None and current_user and current_user.is_authenticated:
                effective_user_id = current_user.id
                
            ip_addr = request.remote_addr if request else None
            user_agent = request.headers.get('User-Agent', '')[:255] if request else None
            
            log_entry = AuditLog(
                user_id=effective_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                old_values=json.dumps(old_values, default=str) if old_values else None,
                new_values=json.dumps(new_values, default=str) if new_values else None,
                ip_address=ip_addr,
                user_agent=user_agent
            )
            db.session.add(log_entry)
            db.session.commit()
        except Exception as e:
            # Audit logging failure should not crash primary operations but be safely caught
            db.session.rollback()
            print(f"Failed to record audit log: {e}")

