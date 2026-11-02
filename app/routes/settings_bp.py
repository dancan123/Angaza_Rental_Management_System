import os
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file
from flask_login import login_required
from app.models.system import DatabaseBackup
from app.models.user import Role, Permission, User
from app.services.personalization_service import PersonalizationService
from app.services.backup_service import BackupService
from app.services.audit_service import AuditService
from app.utils.decorators import permission_required

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/', methods=['GET'])
@login_required
@permission_required('settings.manage')
def index():
    settings = PersonalizationService.get_all_settings()
    backups = DatabaseBackup.query.order_by(DatabaseBackup.created_at.desc()).all()
    roles = Role.query.all()
    permissions = Permission.query.order_by(Permission.module, Permission.code).all()
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template(
        'settings/index.html',
        settings=settings,
        backups=backups,
        roles=roles,
        permissions=permissions,
        users=users
    )

@settings_bp.route('/general', methods=['POST'])
@login_required
@permission_required('settings.manage')
def update_general():
    updates = {
        'app_name': request.form.get('app_name', '').strip(),
        'business_name': request.form.get('business_name', '').strip(),
        'business_address': request.form.get('business_address', '').strip(),
        'business_phone': request.form.get('business_phone', '').strip(),
        'business_email': request.form.get('business_email', '').strip(),
        'landlord_name': request.form.get('landlord_name', '').strip(),
        'business_reg_no': request.form.get('business_reg_no', '').strip(),
        'tax_pin': request.form.get('tax_pin', '').strip(),
    }
    PersonalizationService.update_settings(updates)
    AuditService.log('UPDATE_SETTINGS', 'SystemSetting', new_values=updates)
    flash('General business settings updated successfully.', 'success')
    return redirect(url_for('settings.index', tab='general'))

@settings_bp.route('/branding', methods=['POST'])
@login_required
@permission_required('settings.manage')
def update_branding():
    updates = {
        'theme_primary_color': request.form.get('theme_primary_color', '#1a56db').strip(),
        'theme_secondary_color': request.form.get('theme_secondary_color', '#0e9f6e').strip(),
        'theme_dark_mode': 'true' if request.form.get('theme_dark_mode') else 'false',
    }

    # Handle logo upload
    logo_file = request.files.get('logo_file')
    if logo_file and logo_file.filename:
        filename = secure_filename(logo_file.filename)
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext in {'png', 'jpg', 'jpeg', 'svg', 'webp'}:
            logo_name = f"company_logo.{ext}"
            dest_path = os.path.join(current_app.config['UPLOAD_FOLDER'], logo_name)
            logo_file.save(dest_path)
            updates['logo_url'] = f"/static/uploads/{logo_name}"
        else:
            flash('Invalid logo file format. Please upload PNG, JPG, SVG, or WEBP.', 'danger')

    PersonalizationService.update_settings(updates)
    AuditService.log('UPDATE_BRANDING', 'SystemSetting', new_values=updates)
    flash('Branding and theme colors updated successfully.', 'success')
    return redirect(url_for('settings.index', tab='branding'))

@settings_bp.route('/financial', methods=['POST'])
@login_required
@permission_required('settings.manage')
def update_financial():
    updates = {
        'currency': request.form.get('currency', 'KES').strip().upper(),
        'default_due_day': request.form.get('default_due_day', '5').strip(),
        'grace_period_days': request.form.get('grace_period_days', '5').strip(),
        'late_fee_percentage': request.form.get('late_fee_percentage', '5').strip(),
        'financial_year_start': request.form.get('financial_year_start', '1').strip(),
        'receipt_footer': request.form.get('receipt_footer', '').strip(),
        'default_payment_instructions': request.form.get('default_payment_instructions', '').strip(),
    }
    PersonalizationService.update_settings(updates)
    AuditService.log('UPDATE_FINANCIAL_SETTINGS', 'SystemSetting', new_values=updates)
    flash('Financial policies and currency settings updated successfully.', 'success')
    return redirect(url_for('settings.index', tab='financial'))

@settings_bp.route('/backup/create', methods=['POST'])
@login_required
@permission_required('settings.manage')
def create_backup():
    try:
        backup = BackupService.create_backup(backup_type='MANUAL')
        flash(f"Hot backup created successfully: {backup.file_name} ({round(backup.file_size_bytes / 1024, 1)} KB)", 'success')
    except Exception as e:
        flash(f"Failed to create database backup: {str(e)}", 'danger')
    return redirect(url_for('settings.index', tab='backups'))

@settings_bp.route('/backup/<int:backup_id>/download', methods=['GET'])
@login_required
@permission_required('settings.manage')
def download_backup(backup_id):
    backup = DatabaseBackup.query.get_or_404(backup_id)
    if os.path.exists(backup.file_path):
        return send_file(backup.file_path, as_attachment=True, download_name=backup.file_name)
    flash('Backup file was not found on disk.', 'danger')
    return redirect(url_for('settings.index', tab='backups'))

