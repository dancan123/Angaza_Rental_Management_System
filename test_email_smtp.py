"""
SMTP & Email Activation Test Script for Angaza Rentals System
Usage:
    python test_email_smtp.py [recipient_email]
Example:
    python test_email_smtp.py dancanmbaabu1@gmail.com
"""
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from app.services.email_auth_service import EmailAuthService

def run_test(recipient=None):
    app = create_app('development')
    with app.app_context():
        target_email = recipient or os.environ.get('MAIL_USERNAME') or 'test@angazarentals.com'
        print("=" * 60)
        print("Angaza Rentals — Email Delivery Diagnostic Tool")
        print("=" * 60)
        print(f"Target Recipient: {target_email}")
        print(f"APP_BASE_URL:     {app.config.get('APP_BASE_URL') or '(Not set - using request context)'}")
        print(f"MAIL_SERVER:      {app.config.get('MAIL_SERVER') or '(Unconfigured - Simulation Mode)'}")
        print(f"MAIL_PORT:        {app.config.get('MAIL_PORT')}")
        print(f"MAIL_USERNAME:    {app.config.get('MAIL_USERNAME') or '(None)'}")
        print(f"MAIL_DEFAULT_SDR: {app.config.get('MAIL_DEFAULT_SENDER')}")
        print("-" * 60)

        # 1. Test External URL Generator
        token = EmailAuthService.generate_activation_token(1, 1)
        ext_url = EmailAuthService.build_external_url('auth.activate_account', token=token)
        print(f"[1] Generated Activation URL:\n    {ext_url}")
        print("-" * 60)

        # 2. Test Email Dispatch
        print(f"[2] Dispatching Test Activation Email to {target_email}...")
        result = EmailAuthService.send_email(
            to_email=target_email,
            subject="Angaza Rentals — Live Activation Test Email",
            html_body=f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #059669; border-radius: 8px;">
                <h2 style="color: #059669;">Angaza Rentals — Live Activation Test</h2>
                <p>Hello,</p>
                <p>This is a live test email sent from your Angaza Rentals System.</p>
                <p>Click below to verify that your account activation link works:</p>
                <p><a href="{ext_url}" style="background-color: #059669; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">Activate Account</a></p>
                <p style="color: #64748b; font-size: 12px;">Link: {ext_url}</p>
            </div>
            """,
            text_body=f"Angaza Rentals Test Email.\nActivate at: {ext_url}",
            notification_type='ACCOUNT_ACTIVATION'
        )

        print(f"[3] Result Status: {result.get('status')}")
        if result.get('status') == 'SENT':
            print(">>> SUCCESS: Live email successfully sent and received by SMTP server!")
        elif result.get('status') == 'SIMULATED':
            print(">>> NOTICE: Running in SIMULATION MODE because MAIL_SERVER/MAIL_USERNAME are unconfigured.")
            print("    To send real emails to your Gmail/inbox, add MAIL_SERVER and MAIL_PASSWORD in your .env file.")
        else:
            print(f">>> FAILED: SMTP Error: {result.get('error')}")
        print("=" * 60)

if __name__ == '__main__':
    recipient = sys.argv[1] if len(sys.argv) > 1 else None
    run_test(recipient)
