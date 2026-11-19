import os
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file
from flask_login import login_required, current_user
from app.extensions import db
from app.models.system import DatabaseBackup
from app.models.user import Role, Permission, User
from app.models.organization import Organization
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
    active_org = getattr(current_user, 'active_organization', None)
    return render_template(
        'settings/index.html',
        settings=settings,
        backups=backups,
        roles=roles,
        permissions=permissions,
        users=users,
        active_org=active_org
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


@settings_bp.route('/integrations', methods=['POST'])
@login_required
@permission_required('settings.manage')
def update_integrations():
    """
    Updates Landlord / Organization specific contact person, M-Pesa Daraja gateway,
    Twilio SMS/WhatsApp, and SMTP Email credentials.
    """
    org = getattr(current_user, 'active_organization', None)

    # If superadmin without active org, update system-wide settings
    if not org and current_user.is_superadmin():
        updates = {
            'business_name': request.form.get('business_name', '').strip(),
            'business_phone': request.form.get('contact_phone', '').strip(),
            'business_email': request.form.get('contact_email', '').strip(),
            'whatsapp_number': request.form.get('whatsapp_number', '').strip(),
            'contact_person': request.form.get('contact_person', '').strip(),
            'twilio_account_sid': request.form.get('twilio_account_sid', '').strip(),
            'twilio_auth_token': request.form.get('twilio_auth_token', '').strip(),
            'twilio_from_number': request.form.get('twilio_from_number', '').strip(),
            'twilio_sms_enabled': 'true' if request.form.get('twilio_sms_enabled') else 'false',
            'smtp_host': request.form.get('smtp_host', '').strip(),
            'smtp_port': request.form.get('smtp_port', '587').strip(),
            'smtp_user': request.form.get('smtp_user', '').strip(),
            'smtp_password': request.form.get('smtp_password', '').strip(),
            'smtp_sender_email': request.form.get('smtp_sender_email', '').strip(),
        }
        PersonalizationService.update_settings(updates)
        flash('Platform-wide communication and contact credentials updated.', 'success')
        return redirect(url_for('settings.index', tab='integrations'))

    if not org:
        flash('No active organization found to update.', 'warning')
        return redirect(url_for('settings.index'))

    # Update organization's specific contact & integration profile
    org.contact_person = request.form.get('contact_person', '').strip()
    org.contact_phone = request.form.get('contact_phone', '').strip()
    org.contact_email = request.form.get('contact_email', '').strip()
    org.whatsapp_number = request.form.get('whatsapp_number', '').strip()
    org.tax_pin = request.form.get('tax_pin', '').strip()
    org.business_registration = request.form.get('business_registration', '').strip()

    # M-Pesa Daraja credentials
    org.mpesa_paybill = request.form.get('mpesa_paybill', '').strip()
    org.mpesa_till = request.form.get('mpesa_till', '').strip()
    org.mpesa_consumer_key = request.form.get('mpesa_consumer_key', '').strip()
    org.mpesa_consumer_secret = request.form.get('mpesa_consumer_secret', '').strip()
    org.mpesa_passkey = request.form.get('mpesa_passkey', '').strip()

    # Twilio SMS / WhatsApp credentials
    org.twilio_account_sid = request.form.get('twilio_account_sid', '').strip()
    org.twilio_auth_token = request.form.get('twilio_auth_token', '').strip()
    org.twilio_from_number = request.form.get('twilio_from_number', '').strip()

    # SMTP Mail Server
    org.smtp_host = request.form.get('smtp_host', '').strip()
    smtp_port_val = request.form.get('smtp_port', '587').strip()
    org.smtp_port = int(smtp_port_val) if smtp_port_val.isdigit() else 587
    org.smtp_user = request.form.get('smtp_user', '').strip()
    if request.form.get('smtp_password'):
        org.smtp_password = request.form.get('smtp_password').strip()
    org.smtp_sender_email = request.form.get('smtp_sender_email', '').strip()

    if request.form.get('logo_url'):
        org.logo_url = request.form.get('logo_url').strip()

    # Handle Organization Logo upload
    logo_file = request.files.get('logo_file')
    if logo_file and logo_file.filename:
        filename = secure_filename(logo_file.filename)
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext in {'png', 'jpg', 'jpeg', 'svg', 'webp'}:
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'orgs')
            os.makedirs(upload_dir, exist_ok=True)
            logo_name = f"org_{org.id}_logo.{ext}"
            dest_path = os.path.join(upload_dir, logo_name)
            logo_file.save(dest_path)
            org.logo_url = f"/static/uploads/orgs/{logo_name}"
        else:
            flash('Invalid logo file format. Supported: PNG, JPG, JPEG, WEBP, SVG.', 'warning')

    db.session.commit()
    flash(f"Organization '{org.name}' credentials & contact details updated successfully.", 'success')
    return redirect(url_for('settings.index', tab='integrations'))


