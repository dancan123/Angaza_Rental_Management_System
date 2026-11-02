import pytest
from datetime import date
from app import create_app
from app.extensions import db
from app.models.user import Role, User, Landlord
from app.models.tenant import Tenant
from app.models.property import Property, RentalUnit
from app.models.lease import Lease
from app.models.finance import RentCharge
from app.utils.currency import to_cents

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()

        # Seed roles
        tenant_role = Role(name='TENANT', display_name='Tenant')
        admin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        db.session.add_all([tenant_role, admin_role])
        db.session.commit()

        # Seed Landlord
        landlord = Landlord(name='Apex Landlord', phone='+254711888999', email='owner@apex.co.ke')
        db.session.add(landlord)
        db.session.commit()

        # Seed Property & Unit
        prop = Property(landlord_id=landlord.id, name='Skyline Heights', ref_number='SKH-01', property_type='APARTMENT', location='Kilimani')
        db.session.add(prop)
        db.session.commit()

        unit = RentalUnit(
            property_id=prop.id,
            unit_number='A-101',
            unit_type='1_BEDROOM',
            rent_amount_cents=to_cents(25000),
            deposit_amount_cents=to_cents(25000),
            occupancy_status='OCCUPIED'
        )
        db.session.add(unit)
        db.session.commit()

        # Seed Tenant and User account
        tenant = Tenant(
            first_name='Daniel',
            last_name='Otieno',
            id_passport_number='ID-998877',
            phone='+254711223344',
            email='daniel@tenant.test',
            is_active=True
        )
        db.session.add(tenant)
        db.session.commit()

        user = User(
            username='daniel_tenant',
            email='daniel@tenant.test',
            full_name='Daniel Otieno',
            phone='+254711223344',
            role=tenant_role,
            is_active=True
        )
        user.set_password('TenantSecret123!')
        db.session.add(user)
        db.session.commit()

        tenant.user_id = user.id
        unit.current_tenant_id = tenant.id

        # Seed active lease & charges
        lease = Lease(
            lease_number='LSE-SKH-101',
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            start_date=date(2026, 1, 1),
            monthly_rent_cents=to_cents(25000),
            deposit_cents=to_cents(25000),
            status='ACTIVE'
        )
        db.session.add(lease)

        charge = RentCharge(
            lease_id=1,
            tenant_id=tenant.id,
            rental_unit_id=unit.id,
            invoice_number='INV-202611-A101-1',
            charge_type='RENT',
            period_month=11,
            period_year=2026,
            amount_cents=to_cents(25000),
            amount_paid_cents=0,
            due_date=date(2026, 11, 5),
            status='UNPAID',
            description='Rent for November 2026'
        )
        db.session.add(charge)
        db.session.commit()

        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_tenant_portal_login_and_dashboard(client, app):
    # GET tenant login page
    res = client.get('/portal/tenant/login')
    assert res.status_code == 200
    assert b'Tenant Portal' in res.data

    # POST invalid login
    res = client.post('/portal/tenant/login', data={
        'login_id': 'daniel_tenant',
        'password': 'WrongPassword!'
    }, follow_redirects=True)
    assert b'Invalid phone number, email, or password.' in res.data

    # POST valid login
    res = client.post('/portal/tenant/login', data={
        'login_id': 'daniel_tenant',
        'password': 'TenantSecret123!'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Tenant Portal' in res.data
    assert b'Daniel' in res.data
    assert b'A-101' in res.data

def test_tenant_portal_unauthorized_redirect(client, app):
    # Direct access without logging in redirects to /auth/login (Flask-Login default)
    res = client.get('/portal/tenant/dashboard')
    assert res.status_code == 302
    assert '/auth/login' in res.headers['Location']

def test_tenant_submit_maintenance_ticket(client, app):
    # Login
    client.post('/portal/tenant/login', data={
        'login_id': 'daniel_tenant',
        'password': 'TenantSecret123!'
    }, follow_redirects=True)

    # Submit ticket
    res = client.post('/portal/tenant/submit-ticket', data={
        'title': 'Leaking Sink',
        'category': 'PLUMBING',
        'priority': 'MEDIUM',
        'description': 'Kitchen sink tap is continuously leaking.'
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"logged successfully" in res.data

    # Verify ticket in database
    with app.app_context():
        from app.models.maintenance import MaintenanceRequest
        req = MaintenanceRequest.query.filter_by(title='Leaking Sink').first()
        assert req is not None
        assert req.priority == 'MEDIUM'
        assert req.status == 'PENDING'
