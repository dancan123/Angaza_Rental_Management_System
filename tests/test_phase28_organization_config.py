"""
Phase 28 Organization Configuration & Operations Suite
Verifies:
  1. Per-organization integration settings (M-Pesa, Twilio, SMTP, contact person, WhatsApp number) saved via /settings/integrations.
  2. Property & Room photo update/upload functionality.
  3. WhatsApp multi-channel dispatch links on billing receipt and hospitality guest folio.
  4. Dual-mode hospitality operations & analytics report (/reports/hospitality) with ADR, RevPAR, channels.
  5. Multi-tenant SMS/Twilio credential routing with fallback.
  6. M-Pesa gateway configuration scoped per organization.
"""
import pytest
from datetime import date, datetime
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.organization import Organization
from app.models.property import Property, RentalUnit
from app.models.tenant import Tenant
from app.models.finance import RentCharge, Payment
from app.models.hospitality import Guest, HospitalityReservation
from app.models.gateway import PaymentGatewayConfig
from app.services.sms_service import SmsService
from app.services.payment_service import PaymentService


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        # Seed roles and permissions
        perm_settings = Permission(code='settings.manage', module='settings', description='Manage Settings')
        perm_properties_view = Permission(code='properties.view', module='properties', description='View Properties')
        perm_properties_manage = Permission(code='properties.manage', module='properties', description='Manage Properties')
        perm_units_view = Permission(code='units.view', module='units', description='View Units')
        perm_units_manage = Permission(code='units.manage', module='units', description='Manage Units')
        perm_billing_view = Permission(code='billing.view', module='billing', description='View Billing')
        perm_hospitality_view = Permission(code='hospitality.view', module='hospitality', description='View Hospitality')
        perm_bookings_view = Permission(code='bookings.view', module='bookings', description='View Bookings')
        perm_reports_view = Permission(code='reports.view', module='reports', description='View Reports')
        perm_mpesa = Permission(code='mpesa.manage', module='mpesa', description='Manage Mpesa')
        db.session.add_all([
            perm_settings, perm_properties_view, perm_properties_manage,
            perm_units_view, perm_units_manage,
            perm_billing_view, perm_hospitality_view, perm_bookings_view,
            perm_reports_view, perm_mpesa
        ])

        manager_role = Role(name='PROPERTY_MANAGER', display_name='Property Manager', description='Property Manager')
        manager_role.permissions.extend([
            perm_settings, perm_properties_view, perm_properties_manage,
            perm_units_view, perm_units_manage,
            perm_billing_view, perm_hospitality_view, perm_bookings_view,
            perm_reports_view, perm_mpesa
        ])
        db.session.add(manager_role)
        db.session.commit()

        # Seed Organization
        org = Organization(
            name='Nairobi Luxury Living',
            slug='nairobi-luxury',
            org_code='NLL',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
            enable_rentals=True,
            enable_hospitality=True,
            contact_phone='+254712345678'
        )
        db.session.add(org)
        db.session.commit()

        # Seed Manager User
        user = User(
            username='janemanager',
            full_name='Jane Manager',
            email='manager@nairobiluxury.com',
            role_id=manager_role.id,
            organization_id=org.id,
            is_active=True
        )
        user.set_password('Admin123!')
        db.session.add(user)

        # Landlord
        landlord = Landlord(name='John Mwangi', email='john@example.com', phone='+254700000001')
        db.session.add(landlord)
        db.session.commit()

        # Property & Units
        prop = Property(
            name='Westlands Heights',
            ref_number='PROP-001',
            property_type='APARTMENT',
            landlord_id=landlord.id,
            organization_id=org.id,
            location='Westlands, Nairobi'
        )
        db.session.add(prop)
        db.session.commit()

        # Rental Unit
        unit = RentalUnit(
            property_id=prop.id,
            unit_number='A1',
            unit_type='APARTMENT',
            rent_amount_cents=5000000,
            operational_type='RESIDENTIAL'
        )
        # Airbnb Room Unit
        room = RentalUnit(
            property_id=prop.id,
            unit_number='Suite 101',
            unit_type='APARTMENT',
            rent_amount_cents=10000000,
            daily_rate_cents=500000,
            operational_type='SHORT_STAY',
            cleaning_status='CLEAN'
        )
        db.session.add_all([unit, room])
        db.session.commit()

        # Tenant & Rent Payment for Receipt testing
        tenant = Tenant(
            first_name='David',
            last_name='Otieno',
            email='david@example.com',
            phone='+254722123456',
            id_passport_number='12345678',
            is_active=True
        )
        db.session.add(tenant)
        db.session.flush()
        unit.current_tenant_id = tenant.id

        charge = RentCharge(
            invoice_number='INV-2026-900',
            tenant_id=tenant.id,
            rental_unit_id=unit.id,
            charge_type='Rent',
            period_month=date.today().month,
            period_year=date.today().year,
            amount_cents=5000000,
            due_date=date.today(),
            status='UNPAID',
            description='Monthly Rent Charge'
        )
        db.session.add(charge)
        db.session.commit()

        payment = PaymentService.record_payment(
            tenant_id=tenant.id,
            amount=50000,
            payment_method='MPESA',
            transaction_reference='QWE123RTY',
            auto_confirm=True
        )

        # Guest & Hospitality Reservation
        guest = Guest(
            first_name='Sarah',
            last_name='Connor',
            email='sarah@terminator.com',
            phone='+254799887766',
            id_passport_number='P9876543'
        )
        db.session.add(guest)
        db.session.flush()

        res = HospitalityReservation(
            reservation_code='RES-NLL-100',
            rental_unit_id=room.id,
            guest_id=guest.id,
            check_in_date=date.today(),
            check_out_date=date.today(),
            num_nights=1,
            daily_rate_cents=500000,
            total_stay_cents=500000,
            paid_amount_cents=500000,
            status='CONFIRMED',
            booking_source='AIRBNB'
        )
        db.session.add(res)
        db.session.commit()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, org_code='NLL', username='janemanager', password='Admin123!'):
    return client.post('/auth/login', data={'org_code': org_code, 'username': username, 'password': password}, follow_redirects=True)


def test_organization_integration_settings_save(client, app):
    """Test saving per-org M-Pesa, Twilio, SMTP, contact person and WhatsApp settings."""
    with app.app_context():
        login(client)

        payload = {
            'contact_person': 'Alice Wambui',
            'whatsapp_number': '+254711223344',
            'logo_url': 'https://example.com/logo.png',
            'mpesa_paybill': '987654',
            'mpesa_till': '543210',
            'mpesa_consumer_key': 'DarajaKey123',
            'mpesa_consumer_secret': 'DarajaSecret456',
            'mpesa_passkey': 'Passkey789',
            'smtp_host': 'smtp.sendgrid.net',
            'smtp_port': '587',
            'smtp_user': 'apikey',
            'smtp_password': 'SecretPassword',
            'smtp_sender_email': 'notifications@nairobiluxury.com',
            'twilio_account_sid': 'MOCK_TWILIO_SID_12345',
            'twilio_auth_token': 'Token999888777666555',
            'twilio_from_number': '+15005550006'
        }

        resp = client.post('/settings/integrations', data=payload, follow_redirects=True)
        assert resp.status_code == 200

        # Verify DB updates
        org = Organization.query.filter_by(slug='nairobi-luxury').first()
        assert org.contact_person == 'Alice Wambui'
        assert org.whatsapp_number == '+254711223344'
        assert org.logo_url == 'https://example.com/logo.png'
        assert org.mpesa_paybill == '987654'
        assert org.mpesa_till == '543210'
        assert org.mpesa_consumer_key == 'DarajaKey123'
        assert org.smtp_host == 'smtp.sendgrid.net'
        assert org.smtp_sender_email == 'notifications@nairobiluxury.com'
        assert org.twilio_account_sid == 'MOCK_TWILIO_SID_12345'


def test_property_and_unit_photo_edit(client, app):
    """Test updating property photo and unit photo via URLs."""
    with app.app_context():
        login(client)
        prop = Property.query.first()
        unit = RentalUnit.query.first()

        # Update property photo
        resp = client.post(f'/properties/{prop.id}/edit', data={
            'name': prop.name,
            'property_type': prop.property_type,
            'landlord_id': prop.landlord_id,
            'location': 'Kilimani, Nairobi',
            'image_url': 'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00'
        }, follow_redirects=True)
        assert resp.status_code == 200

        prop_refreshed = db.session.get(Property, prop.id)
        assert prop_refreshed.image_url == 'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00'
        assert prop_refreshed.location == 'Kilimani, Nairobi'

        # Update unit photo
        resp_unit = client.post(f'/properties/units/{unit.id}/edit', data={
            'unit_number': unit.unit_number,
            'unit_type': unit.unit_type,
            'rent_amount': 55000,
            'image_url': 'https://images.unsplash.com/photo-1522708323590-d24dbb6b0267'
        }, follow_redirects=True)
        assert resp_unit.status_code == 200

        unit_refreshed = db.session.get(RentalUnit, unit.id)
        assert unit_refreshed.image_url == 'https://images.unsplash.com/photo-1522708323590-d24dbb6b0267'


def test_whatsapp_reception_buttons(client, app):
    """Test WhatsApp reception dispatch links on billing receipt & hospitality folio."""
    with app.app_context():
        login(client)

        payment = Payment.query.first()
        res = HospitalityReservation.query.first()

        # 1. Billing receipt
        resp_receipt = client.get(f'/billing/receipt/{payment.id}/view')
        assert resp_receipt.status_code == 200
        assert b'wa.me' in resp_receipt.data
        assert b'254722123456' in resp_receipt.data

        # 2. Hospitality folio receipt
        resp_folio = client.get(f'/hospitality/reservations/{res.id}/receipt')
        assert resp_folio.status_code == 200
        assert b'wa.me' in resp_folio.data
        assert b'254799887766' in resp_folio.data


def test_hospitality_analytics_report(client, app):
    """Test loading hospitality operations report with ADR, RevPAR, and Channels."""
    with app.app_context():
        login(client)

        resp = client.get('/reports/hospitality')
        assert resp.status_code == 200
        assert b'Airbnb &amp; Hospitality Operations Report' in resp.data
        assert b'ADR (Avg Daily Rate)' in resp.data
        assert b'RevPAR' in resp.data
        assert b'Booking Acquisition Channels' in resp.data
        assert b'Housekeeping &amp; Turnaround Health' in resp.data


def test_twilio_credentials_per_organization(app):
    """Test Twilio credentials helper with per-organization settings and fallback."""
    with app.app_context():
        org = Organization.query.first()
        org.twilio_account_sid = 'MOCK_TWILIO_ORG_TEST'
        org.twilio_auth_token = 'TOKEN_ORG_TEST'
        org.twilio_from_number = '+254700000000'
        db.session.commit()

        creds = SmsService.get_twilio_credentials(organization=org)
        assert creds['account_sid'] == 'MOCK_TWILIO_ORG_TEST'
        assert creds['auth_token'] == 'TOKEN_ORG_TEST'
        assert creds['from_number'] == '+254700000000'
        assert creds['is_enabled'] is True

        # Fallback when organization has no Twilio credentials
        org.twilio_account_sid = None
        db.session.commit()
        creds_fb = SmsService.get_twilio_credentials(organization=org)
        assert creds_fb['account_sid'] != 'MOCK_TWILIO_ORG_TEST'


def test_mpesa_config_scoping_per_organization(client, app):
    """Test M-Pesa gateway config creation sets organization_id."""
    with app.app_context():
        login(client)
        org = Organization.query.first()

        resp = client.post('/mpesa/config/save', data={
            'name': 'Primary Paybill',
            'gateway_type': 'MPESA_PAYBILL',
            'shortcode': '247247',
            'till_number': '',
            'consumer_key': 'DarajaKey',
            'consumer_secret': 'DarajaSecret',
            'passkey': 'DarajaPasskey',
            'callback_url': 'https://example.com/mpesa/c2b',
            'is_sandbox': 'on'
        }, follow_redirects=True)
        assert resp.status_code == 200

        cfg = PaymentGatewayConfig.query.filter_by(shortcode='247247').first()
        assert cfg is not None
        assert cfg.organization_id == org.id
