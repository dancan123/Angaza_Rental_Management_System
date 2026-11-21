import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import current_app, render_template_string
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.extensions import db
from app.models.communication import Notification
from app.models.organization import Organization


class EmailAuthService:
    """
    Centralized email delivery, cryptographic token generation,
    account activation, and password reset service.
    
    Operates in live SMTP mode when organization or system SMTP is configured,
    and records transactional email dispatches to Notification logs with
    instant simulation preview when SMTP is unconfigured or in development.
    """

    SALT_PASSWORD_RESET = 'angaza-password-reset-salt-v1'
    SALT_ACCOUNT_ACTIVATION = 'angaza-account-activation-salt-v1'

    @classmethod
    def build_external_url(cls, endpoint: str, **kwargs) -> str:
        """
        Builds fully qualified public URL for external email links.
        Prioritizes APP_BASE_URL (e.g. 'https://app.angazarentals.com') from config or .env,
        falling back to Flask's standard url_for(..., _external=True).
        Handles CLI / background tasks safely without crashing on missing SERVER_NAME.
        """
        from flask import url_for, has_request_context
        base_url = (current_app.config.get('APP_BASE_URL') or os.environ.get('APP_BASE_URL', '')).rstrip('/')
        if not base_url:
            server_name = current_app.config.get('SERVER_NAME')
            scheme = current_app.config.get('PREFERRED_URL_SCHEME', 'http')
            if server_name:
                base_url = f"{scheme}://{server_name}"
            elif not has_request_context():
                base_url = "http://127.0.0.1:5000"

        if base_url:
            if has_request_context():
                relative_url = url_for(endpoint, _external=False, **kwargs)
            else:
                with current_app.test_request_context():
                    relative_url = url_for(endpoint, _external=False, **kwargs)
            return f"{base_url}{relative_url}"

        return url_for(endpoint, _external=True, **kwargs)

    @classmethod
    def get_serializer(cls):
        secret_key = current_app.config.get('SECRET_KEY') or 'angaza-rentals-system-secret-key-fallback'
        return URLSafeTimedSerializer(secret_key)

    @classmethod
    def generate_password_reset_token(cls, user_id: int) -> str:
        s = cls.get_serializer()
        return s.dumps({'user_id': user_id, 'action': 'reset'}, salt=cls.SALT_PASSWORD_RESET)

    @classmethod
    def verify_password_reset_token(cls, token: str, max_age_seconds: int = 3600):
        """Validates token. Defaults to 1 hour (3600s) expiry."""
        s = cls.get_serializer()
        try:
            data = s.loads(token, salt=cls.SALT_PASSWORD_RESET, max_age=max_age_seconds)
            return data.get('user_id')
        except (BadSignature, SignatureExpired):
            return None

    @classmethod
    def generate_activation_token(cls, org_id: int, user_id: int) -> str:
        s = cls.get_serializer()
        return s.dumps({'org_id': org_id, 'user_id': user_id, 'action': 'activate'}, salt=cls.SALT_ACCOUNT_ACTIVATION)

    @classmethod
    def verify_activation_token(cls, token: str, max_age_seconds: int = 86400 * 3):
        """Validates activation token. Valid for 3 days (259200s)."""
        s = cls.get_serializer()
        try:
            data = s.loads(token, salt=cls.SALT_ACCOUNT_ACTIVATION, max_age=max_age_seconds)
            return data.get('org_id'), data.get('user_id')
        except (BadSignature, SignatureExpired):
            return None, None

    @classmethod
    def send_email(cls, to_email: str, subject: str, html_body: str, text_body: str = None, organization_id: int = None, recipient_user_id: int = None, notification_type: str = 'EMAIL'):
        """
        Sends email via SMTP if configured; logs to Notification database with channel='EMAIL'.
        Never crashes caller if network or SMTP connection is unreachable.
        """
        sent_status = 'SIMULATED'
        error_details = None

        # Look up per-tenant SMTP settings if available
        smtp_host = None
        smtp_port = 587
        smtp_user = None
        smtp_password = None
        sender_email = 'no-reply@angaza.co.ke'
        sender_name = 'Angaza Property Management'

        if organization_id:
            org = db.session.get(Organization, organization_id)
            if org:
                if org.smtp_host and org.smtp_user and org.smtp_password:
                    smtp_host = org.smtp_host
                    smtp_port = org.smtp_port or 587
                    smtp_user = org.smtp_user
                    smtp_password = org.smtp_password
                    sender_email = org.smtp_sender_email or org.contact_email or sender_email
                    sender_name = org.name

        # If system-level SMTP is configured in app config or environment variables:
        if not smtp_host:
            smtp_host = current_app.config.get('MAIL_SERVER') or os.environ.get('MAIL_SERVER')
            smtp_port = current_app.config.get('MAIL_PORT') or os.environ.get('MAIL_PORT', 587)
            try:
                smtp_port = int(smtp_port)
            except (ValueError, TypeError):
                smtp_port = 587
            smtp_user = current_app.config.get('MAIL_USERNAME') or os.environ.get('MAIL_USERNAME')
            smtp_password = current_app.config.get('MAIL_PASSWORD') or os.environ.get('MAIL_PASSWORD')
            sender_email = current_app.config.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_DEFAULT_SENDER') or sender_email

        if smtp_host and smtp_user and smtp_password:
            try:
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = f"{sender_name} <{sender_email}>"
                msg['To'] = to_email

                if text_body:
                    msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
                if html_body:
                    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

                use_ssl = int(smtp_port) == 465 or current_app.config.get('MAIL_USE_SSL', False)
                use_tls = current_app.config.get('MAIL_USE_TLS', True) and not use_ssl

                if use_ssl:
                    server = smtplib.SMTP_SSL(smtp_host, int(smtp_port), timeout=15)
                else:
                    server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=15)
                    if use_tls:
                        server.starttls()

                server.login(smtp_user, smtp_password)
                server.sendmail(sender_email, [to_email], msg.as_string())
                server.quit()
                sent_status = 'SENT'
            except Exception as e:
                sent_status = 'FAILED'
                error_details = str(e)
        else:
            # Simulated environment: record formatted email in notifications
            sent_status = 'SIMULATED'

        # Record in Notification log
        try:
            notif = Notification(
                recipient_user_id=recipient_user_id,
                title=subject,
                message=f"To: {to_email}\nSubject: {subject}\n\n{text_body or html_body}",
                channel='EMAIL',
                notification_type=notification_type,
                sent_status=sent_status,
                error_details=error_details,
                sent_at=datetime.utcnow() if sent_status == 'SENT' else None
            )
            db.session.add(notif)
            db.session.commit()
        except Exception:
            db.session.rollback()

        return {
            'status': sent_status,
            'error': error_details,
            'to': to_email
        }
