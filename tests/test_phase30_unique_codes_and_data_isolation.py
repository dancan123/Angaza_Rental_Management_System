import pytest
from app import create_app, db
from app.models.user import User, Role
from app.models.organization import Organization
from app.models.tenant import Tenant
from app.models.finance import Payment, RentCharge
from app.models.hospitality import Guest, HospitalityReservation

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        with app.app_context():
            yield client

def test_superadmin_login_with_ang0001(client):
    """
    Ensure entering 'ANG0001' routes directly to Super Admin account,
    granting platform-level cross-organization management.
    """
    response = client.post('/auth/login', data={
        'org_code': 'ANG0001',
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Welcome back" in response.data or b"Dashboard" in response.data or b"Super Admin" in response.data

def test_client_login_with_ang_codes(client):
    """
    Ensure logging in with 'ANG0002' vs 'ANG0003' routes to the correct isolated organization.
    """
    # 1. Login to Org 2 (Angaza Premier)
    res1 = client.post('/auth/login', data={
        'org_code': 'ANG0002',
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert res1.status_code == 200
    assert b"Welcome back" in res1.data

    # Logout
    client.get('/auth/logout', follow_redirects=True)

    # 2. Login to Org 3 (Mama Sarah)
    res2 = client.post('/auth/login', data={
        'org_code': 'ANG0003',
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert res2.status_code == 200
    assert b"Welcome back" in res2.data

def test_slash_and_at_notation_with_ang_code(client):
    """
    Ensure 'ANG0002/admin' or 'admin@ANG0002' properly signs in with org isolation.
    """
    res = client.post('/auth/login', data={
        'org_code': '',
        'username': 'ANG0002/admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"Welcome back" in res.data

def test_auto_generation_of_unique_org_code(client):
    """
    Ensure system auto-generates sequential 'ANGxxxx' unique codes.
    """
    next_code = Organization.generate_unique_org_code()
    assert next_code.startswith("ANG")
    assert len(next_code) == 7  # 'ANG' + 4 digits e.g. 'ANG0005'
    num_part = int(next_code[3:])
    assert num_part >= 5

def test_self_registration_assigns_unique_ang_code(client):
    """
    Ensure public self-registration generates and assigns a unique ANG code.
    """
    import random
    rand_id = random.randint(1000, 9999)
    email = f"lead_{rand_id}@example.com"
    org_name = f"Apex Properties {rand_id}"

    res = client.post('/auth/register', data={
        'organization_name': org_name,
        'full_name': 'Apex Director',
        'email': email,
        'phone': f'+254700{rand_id}',
        'password': 'Password123!',
        'subscription_tier': 'COMBINED_SUITE'
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"Account Ready" in res.data
    assert b"Business Code" in res.data

    # Check DB
    new_org = Organization.query.filter_by(name=org_name).first()
    assert new_org is not None
    assert new_org.org_code is not None
    assert new_org.org_code.startswith("ANG")

def test_cross_organization_data_isolation(client):
    """
    Ensure strict data integrity:
    Org A (ANG0002) user cannot view or download tenant records or receipts belonging to Org B (ANG0003).
    """
    # 1. Login as Org 2 (Angaza Premier)
    client.post('/auth/login', data={
        'org_code': 'ANG0002',
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)

    # Find a tenant belonging to Org 3 (Mama Sarah)
    tenant_org3 = Tenant.query.filter_by(organization_id=2).first()
    if tenant_org3:
        # Attempting to access Org 3 tenant details from Org 1 session must return 404
        res_tenant = client.get(f'/tenants/{tenant_org3.id}')
        assert res_tenant.status_code == 404

        # Attempting to download Org 3 tenant statement must return 404
        res_stmt = client.get(f'/tenants/{tenant_org3.id}/statement/pdf')
        assert res_stmt.status_code == 404

    # Find a payment belonging to Org 3 (Mama Sarah)
    payment_org3 = Payment.query.filter_by(organization_id=2).first()
    if payment_org3:
        # Attempting to view receipt must return 404
        res_rec = client.get(f'/billing/receipt/{payment_org3.id}/view')
        assert res_rec.status_code == 404

        # Attempting to download receipt PDF must return 404
        res_pdf = client.get(f'/billing/receipt/{payment_org3.id}/pdf')
        assert res_pdf.status_code == 404

    # Find a charge belonging to Org 3 (Mama Sarah)
    charge_org3 = RentCharge.query.filter_by(organization_id=2).first()
    if charge_org3:
        # Attempting to download invoice PDF must return 404
        res_inv = client.get(f'/billing/invoices/{charge_org3.id}/pdf')
        assert res_inv.status_code == 404

def test_register_with_admin_email_resolves_username_collision(client):
    """
    Ensure registering with an email like 'admin@gmail.com' (where 'admin' username already exists)
    does NOT crash with a UNIQUE constraint failed on users.username,
    and instead assigns a collision-safe username like 'angxxxx_admin'.
    """
    import random
    rand_id = random.randint(10000, 99999)
    email = f"admin{rand_id}@newlandlord.co.ke"
    # Even if someone uses an email where the prefix is 'admin' by setting base
    org_name = f"Admin Estate {rand_id}"

    res = client.post('/auth/register', data={
        'organization_name': org_name,
        'full_name': 'Mwende John',
        'email': f"admin_{rand_id}@gmail.com",
        'phone': f'+254746{rand_id}',
        'password': 'Password123!',
        'subscription_tier': 'COMBINED_SUITE'
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b"Account Ready" in res.data

    # Log out first user before testing second registration
    client.get('/auth/logout', follow_redirects=True)

    # Now register another one with exact 'admin' prefix email to trigger collision handling
    org_name_2 = f"Mwende Agency {rand_id}"
    email_2 = f"admin@clientdomain{rand_id}.com"

    res2 = client.post('/auth/register', data={
        'organization_name': org_name_2,
        'full_name': 'Mwende John Second',
        'email': email_2,
        'phone': f'+2547460{rand_id}',
        'password': 'Password123!',
        'subscription_tier': 'COMBINED_SUITE'
    }, follow_redirects=True)

    assert res2.status_code == 200
    assert b"Account Ready" in res2.data
    # Verify user was created with a collision-free prefixed username
    user = User.query.filter_by(email=email_2).first()
    assert user is not None
    assert user.username != "admin"
    assert "admin" in user.username


def test_newly_registered_account_starts_with_zero_data(client):
    """
    Ensure newly created organization starts with pristine ZERO DATA:
    - Dedicated success screen displays unique ANGxxxx code
    - Logging into the new account shows 0 properties, 0 units, 0 tenants, KES 0.00 financials
    - No cross-tenant data leaks from other businesses in the system
    """
    import random
    rand_id = random.randint(100000, 999999)
    email = f"purity_{rand_id}@brandnewestate.co.ke"
    org_name = f"Purity Haven {rand_id}"
    password = "SecurePassword123!"

    # 1. Register new organization
    res_reg = client.post('/auth/register', data={
        'organization_name': org_name,
        'full_name': 'Purity Wanjiku',
        'email': email,
        'phone': f'+254711{rand_id}',
        'password': password,
        'subscription_tier': 'COMBINED_SUITE'
    }, follow_redirects=True)

    assert res_reg.status_code == 200
    assert b"Account Ready!" in res_reg.data
    assert b"Your Unique Business Code" in res_reg.data
    assert b"Data Integrity Guaranteed" in res_reg.data
    assert b"zero data" in res_reg.data
    assert b"Proceed to Sign In" in res_reg.data

    # Query created organization from DB
    new_org = Organization.query.filter_by(name=org_name).first()
    assert new_org is not None
    org_code = new_org.org_code
    assert org_code.startswith("ANG")

    # Ensure registration did NOT auto-login (client session should be unauthenticated)
    res_dash_unauth = client.get('/dashboard')
    assert res_dash_unauth.status_code == 302  # redirected to login

    # 2. Login using newly generated business code & email
    res_login = client.post('/auth/login', data={
        'org_code': org_code,
        'username': email,
        'password': password
    }, follow_redirects=True)

    assert res_login.status_code == 200
    assert b"Welcome back" in res_login.data

    # 3. Check Dashboard metrics: absolute zero data
    res_dash = client.get('/dashboard')
    assert res_dash.status_code == 200
    # Dashboard confirms isolated metrics
    assert b"Expected Income" in res_dash.data
    assert b"Collected Rent" in res_dash.data
    assert b"KES 0.00" in res_dash.data
    # No other org's properties leak through
    assert b"Angaza Premier" not in res_dash.data
    assert b"Mama Sarah" not in res_dash.data
    assert b"Capital Heights" not in res_dash.data

    # 4. Check Properties listing: empty
    res_props = client.get('/properties/')
    assert res_props.status_code == 200
    assert b"No Properties Found" in res_props.data or b"Register New Property" in res_props.data

    # 5. Check Tenants listing: empty
    res_tenants = client.get('/tenants/')
    assert res_tenants.status_code == 200
    assert b"No Tenants Found" in res_tenants.data

    # 6. Check Reports: empty
    res_reports = client.get('/reports/collection')
    assert res_reports.status_code == 200
    assert b"0.00" in res_reports.data
