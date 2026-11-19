"""
Phase 26 PDF Document Generation Suite Test
Verifies:
  1. Rent Invoice PDF generation & download (/billing/invoices/<id>/pdf)
  2. Airbnb Guest Folio PDF generation & download (/hospitality/reservations/<id>/pdf)
  3. Tenant Statement of Account PDF generation & download (/tenants/<id>/statement/pdf)
  4. Landlord Remittance Statement PDF generation & download (/reports/landlord-statement/<id>/pdf)
"""
import pytest
from datetime import datetime, date
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.organization import Organization
from app.models.property import Property, RentalUnit
from app.models.tenant import Tenant
from app.models.finance import RentCharge
from app.models.hospitality import HospitalityReservation, Guest


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        superadmin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        perms = [
            Permission(code='properties.view', module='properties', description='View properties'),
            Permission(code='billing.view', module='billing', description='View billing'),
            Permission(code='tenants.view', module='tenants', description='View tenants'),
            Permission(code='reports.view', module='reports', description='View reports'),
            Permission(code='hospitality.view', module='hospitality', description='View hospitality'),
        ]
        db.session.add(superadmin_role)
        db.session.add_all(perms)
        db.session.commit()
        superadmin_role.permissions = perms

        admin = User(
            username='admin',
            email='admin@primerent.co.ke',
            full_name='Admin User',
            role=superadmin_role,
            is_active=True
        )
        admin.set_password('admin123')
        db.session.add(admin)

        org = Organization(
            name='Test Org',
            slug='test-org',
            org_code='TESTORG',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
            enable_rentals=True,
            enable_hospitality=True
        )
        db.session.add(org)
        db.session.flush()

        landlord = Landlord(
            name='John Landlord',
            email='john@example.com',
            phone='+254711000000'
        )
        db.session.add(landlord)
        db.session.flush()

        prop = Property(
            name='Sunset Heights',
            ref_number='PROP-SUNSET-01',
            organization_id=org.id,
            landlord_id=landlord.id,
            location='Westlands, Nairobi',
            property_type='APARTMENT'
        )
        db.session.add(prop)
        db.session.flush()

        unit = RentalUnit(
            property_id=prop.id,
            unit_number='A101',
            unit_type='TWO_BEDROOM',
            rent_amount_cents=3500000,
            occupancy_status='OCCUPIED',
            operational_type='SHORT_STAY',
            daily_rate_cents=450000
        )
        db.session.add(unit)
        db.session.flush()

        tenant = Tenant(
            first_name='David',
            last_name='Mwangi',
            email='david@example.com',
            phone='+254722112233',
            id_passport_number='12345678',
            is_active=True
        )
        db.session.add(tenant)
        db.session.flush()
        unit.current_tenant_id = tenant.id

        charge = RentCharge(
            invoice_number='INV-2026-001',
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            charge_type='Rent',
            period_month=11,
            period_year=2026,
            amount_cents=3500000,
            due_date=date.today(),
            status='UNPAID',
            description='Monthly Rent Charge'
        )
        db.session.add(charge)

        guest = Guest(
            first_name='Alice',
            last_name='Smith',
            phone='+254733445566',
            email='alice@example.com',
            id_passport_number='A998877'
        )
        db.session.add(guest)
        db.session.flush()

        res = HospitalityReservation(
            rental_unit_id=unit.id,
            guest_id=guest.id,
            reservation_code='RES-2026-999',
            check_in_date=date.today(),
            check_out_date=date.today(),
            num_nights=3,
            daily_rate_cents=450000,
            total_stay_cents=1350000,
            paid_amount_cents=1350000,
            status='CHECKED_IN'
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


def test_pdf_downloads(client):
    # Log in
    resp = client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
    assert resp.status_code == 200

    # Retrieve IDs from db
    with client.application.app_context():
        charge = RentCharge.query.first()
        res = HospitalityReservation.query.first()
        tenant = Tenant.query.first()
        landlord = Landlord.query.first()
        charge_id = charge.id
        res_id = res.id
        tenant_id = tenant.id
        landlord_id = landlord.id

    # 1. Invoice PDF Route
    resp = client.get(f'/billing/invoices/{charge_id}/pdf')
    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'application/pdf'
    assert resp.data[:4] == b'%PDF'

    # 2. Guest Folio PDF Route
    resp = client.get(f'/hospitality/reservations/{res_id}/pdf')
    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'application/pdf'
    assert resp.data[:4] == b'%PDF'

    # 3. Tenant Statement PDF Route
    resp = client.get(f'/tenants/{tenant_id}/statement/pdf')
    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'application/pdf'
    assert resp.data[:4] == b'%PDF'

    # 4. Landlord Remittance Statement PDF Route
    resp = client.get(f'/reports/landlord-statement/{landlord_id}/pdf')
    assert resp.status_code == 200
    assert resp.headers['Content-Type'] == 'application/pdf'
    assert resp.data[:4] == b'%PDF'
