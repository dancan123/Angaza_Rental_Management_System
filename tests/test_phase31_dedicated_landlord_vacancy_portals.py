import pytest
from app import create_app, db
from app.models.organization import Organization
from app.models.property import Property, RentalUnit
from app.models.lead import HouseSeekerLead, ExternalPropertyListing
from app.models.booking import Booking

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        with app.app_context():
            yield client

def test_dedicated_vacancies_page_for_org2_angaza_premier(client):
    """
    Ensure /vacancies/ANG0002 only displays Org 2 properties/units,
    and brands the page with Org 2's name and contact information.
    """
    res = client.get('/vacancies/ANG0002')
    assert res.status_code == 200
    assert b"ANG0002" in res.data
    assert b"Angaza Premier" in res.data
    # Should not mention Mama Sarah
    assert b"Mama Sarah" not in res.data

def test_dedicated_vacancies_page_for_org3_mama_sarah(client):
    """
    Ensure /vacancies/ANG0003 only displays Org 3 properties/units,
    and brands the page with Org 3's name and contact information.
    """
    res = client.get('/vacancies/ANG0003')
    assert res.status_code == 200
    assert b"ANG0003" in res.data
    assert b"Mama Sarah" in res.data
    # Should not mention Angaza Premier
    assert b"Angaza Premier" not in res.data

def test_short_url_v_org_code_routes_correctly(client):
    """
    Ensure /v/ANG0002 works as a short marketing URL for WhatsApp and flyers.
    """
    res = client.get('/v/ANG0002')
    assert res.status_code == 200
    assert b"ANG0002" in res.data
    assert b"Angaza Premier" in res.data

def test_new_organization_has_isolated_zero_vacancies_on_public_link(client):
    """
    Ensure newly created organization's public vacancy link does NOT leak
    units or properties from other organizations.
    """
    import random
    rand_id = random.randint(10000, 99999)
    org_name = f"Eldoret Heights {rand_id}"
    email = f"manager_{rand_id}@eldoretheights.co.ke"

    # Register new organization
    res_reg = client.post('/auth/register', data={
        'organization_name': org_name,
        'full_name': 'Eldoret Manager',
        'email': email,
        'phone': f'+254722{rand_id}',
        'password': 'SecurePassword123!',
        'subscription_tier': 'COMBINED_SUITE'
    }, follow_redirects=True)
    assert res_reg.status_code == 200

    new_org = Organization.query.filter_by(name=org_name).first()
    assert new_org is not None
    org_code = new_org.org_code

    # Visit the new org's public vacancy page
    res_vac = client.get(f'/vacancies/{org_code}')
    assert res_vac.status_code == 200
    assert org_code.encode('utf-8') in res_vac.data
    assert org_name.encode('utf-8') in res_vac.data

    # Zero units from other orgs leak in
    assert b"Angaza Premier" not in res_vac.data
    assert b"Mama Sarah" not in res_vac.data
    assert b"Available Vacant Units (0)" in res_vac.data
    assert b"All Units Are Currently Fully Occupied!" in res_vac.data

def test_prospective_tenant_inquiry_on_org_vacancies_attaches_org_id(client):
    """
    Ensure inquiries submitted on an organization's vacancy page:
    1. Attach organization_id to the Booking record
    2. Redirect back to that organization's dedicated vacancy page
    """
    # Find a vacant unit in Org 2
    unit = RentalUnit.query.join(Property).filter(Property.organization_id == 2, RentalUnit.occupancy_status == 'VACANT').first()
    if unit:
        res = client.post('/vacancies/inquire', data={
            'unit_id': unit.id,
            'full_name': 'Prospective Tenant Kevin',
            'phone': '+254722888999',
            'email': 'kevin@gmail.com',
            'expected_move_in': '2026-12-01',
            'notes': 'Interested in 2-year lease',
            'org_code': 'ANG0002'
        }, follow_redirects=False)

        assert res.status_code == 302
        assert '/vacancies/ANG0002' in res.location

        # Check booking in DB
        booking = Booking.query.filter_by(prospective_phone='+254722888999').order_by(Booking.id.desc()).first()
        assert booking is not None
        assert booking.organization_id == unit.property.organization_id

def test_house_alert_lead_on_org_vacancies_attaches_org_id(client):
    """
    Ensure house seeker waitlist lead submitted on an organization's vacancy page:
    1. Attaches organization_id to HouseSeekerLead
    2. Redirects back to that organization's dedicated vacancy page
    """
    res = client.post('/vacancies/house-alert', data={
        'full_name': 'Seeker Beatrice',
        'phone': '+254733444555',
        'email': 'beatrice@gmail.com',
        'unit_type': '2_BEDROOM',
        'locations': 'Kilimani / Kileleshwa',
        'max_budget': 45000,
        'contact_method': 'WHATSAPP',
        'notes': 'Must have borehole',
        'org_code': 'ANG0002'
    }, follow_redirects=False)

    assert res.status_code == 302
    assert '/vacancies/ANG0002' in res.location

    # Check lead in DB
    lead = HouseSeekerLead.query.filter_by(phone='+254733444555').order_by(HouseSeekerLead.id.desc()).first()
    assert lead is not None
    org2 = Organization.query.filter_by(org_code='ANG0002').first()
    assert lead.organization_id == org2.id
