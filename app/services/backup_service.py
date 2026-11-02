import os
import sqlite3
import hashlib
from datetime import datetime
from flask import current_app
from app.extensions import db
from app.models.system import DatabaseBackup
from app.services.audit_service import AuditService

class BackupService:
    @staticmethod
    def create_backup(backup_type='MANUAL') -> DatabaseBackup:
        """
        Performs an online safe hot backup of the SQLite database.
        """
        now_str = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"rental_management_backup_{now_str}.db"
        backups_dir = os.path.join(current_app.root_path, '..', 'backups')
        os.makedirs(backups_dir, exist_ok=True)
        backup_dest_path = os.path.join(backups_dir, backup_filename)

        # Source db path
        source_db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')

        try:
            # Safe SQLite online backup API
            src_conn = sqlite3.connect(source_db_path)
            dest_conn = sqlite3.connect(backup_dest_path)
            src_conn.backup(dest_conn)
            dest_conn.close()
            src_conn.close()

            file_size = os.path.getsize(backup_dest_path)

            # Compute sha256 checksum
            sha256 = hashlib.sha256()
            with open(backup_dest_path, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    sha256.update(chunk)
            checksum = sha256.hexdigest()

            backup_record = DatabaseBackup(
                file_name=backup_filename,
                file_path=backup_dest_path,
                file_size_bytes=file_size,
                backup_type=backup_type,
                status='COMPLETED',
                checksum=checksum
            )
            db.session.add(backup_record)
            db.session.commit()

            AuditService.log('BACKUP_CREATED', 'DatabaseBackup', backup_record.id, new_values={'filename': backup_filename})
            return backup_record
        except Exception as e:
            backup_record = DatabaseBackup(
                file_name=backup_filename,
                file_path=backup_dest_path,
                backup_type=backup_type,
                status='FAILED'
            )
            db.session.add(backup_record)
            db.session.commit()
            raise e

