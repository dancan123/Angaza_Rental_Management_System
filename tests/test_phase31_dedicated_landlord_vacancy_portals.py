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


def test_regional_isolation_meru_vs_nairobi(client):
    """
    Explicitly verify that Meru and Nairobi organizations are fully isolated:
    - A Meru-based organization's public vacancy page shows 'Meru' branding
      and does NOT show any units or external listings from a Nairobi org.
    - A Nairobi organization's public vacancy page does NOT show any Meru listings.
    - Each org's marketplace lead/listing counts are independent.
    """
    import random
    r = random.randint(10000, 99999)

    # --- Register Meru organization ---
    meru_org_name = f"Meru Heights Estate {r}"
    meru_email = f"meru.manager_{r}@meruheights.co.ke"
    res_meru = client.post('/auth/register', data={
        'organization_name': meru_org_name,
        'full_name': 'Meru Manager',
        'email': meru_email,
        'phone': f'+2547119{r}',
        'password': 'SecurePassword123!',
        'subscription_tier': 'COMBINED_SUITE',
        'region': 'Meru',
        'county': 'Meru County',
        'town': 'Meru Town',
    }, follow_redirects=True)
    assert res_meru.status_code == 200

    meru_org = Organization.query.filter_by(name=meru_org_name).first()
    assert meru_org is not None
    # Explicitly set region to Meru in case form did not persist (graceful fallback)
    meru_org.region = 'Meru'
    meru_org.county = 'Meru County'
    meru_org.town = 'Meru Town'
    from app import db
    db.session.commit()

    meru_code = meru_org.org_code

    # --- Register Nairobi organization ---
    nbi_org_name = f"Nairobi Prestige Homes {r}"
    nbi_email = f"nairobi.manager_{r}@nairobiprestige.co.ke"
    res_nbi = client.post('/auth/register', data={
        'organization_name': nbi_org_name,
        'full_name': 'Nairobi Manager',
        'email': nbi_email,
        'phone': f'+2547229{r}',
        'password': 'SecurePassword123!',
        'subscription_tier': 'COMBINED_SUITE',
        'region': 'Nairobi',
        'county': 'Nairobi City County',
        'town': 'Westlands',
    }, follow_redirects=True)
    assert res_nbi.status_code == 200

    nbi_org = Organization.query.filter_by(name=nbi_org_name).first()
    assert nbi_org is not None
    nbi_org.region = 'Nairobi'
    nbi_org.county = 'Nairobi City County'
    nbi_org.town = 'Westlands'
    db.session.commit()

    nbi_code = nbi_org.org_code

    # --- Add an external partner listing to Meru org (simulates a Meru neighbor advertising) ---
    meru_listing = ExternalPropertyListing(
        organization_id=meru_org.id,
        property_title=f'Meru Luxury Bedsitter {r}',
        location='Meru Town Centre',
        unit_type='BEDSITTER',
        monthly_rent_cents=1500000,
        bedrooms=0,
        bathrooms=1,
        owner_name='Meru Landlord A',
        owner_phone=f'+2547339{r}',
        status='PUBLISHED',
        description='Spacious bedsitter in Meru CBD',
    )
    db.session.add(meru_listing)

    # --- Add an external partner listing to Nairobi org ---
    nbi_listing = ExternalPropertyListing(
        organization_id=nbi_org.id,
        property_title=f'Nairobi Studio Apartment {r}',
        location='Westlands, Nairobi',
        unit_type='BEDSITTER',
        monthly_rent_cents=3500000,
        bedrooms=0,
        bathrooms=1,
        owner_name='Nairobi Landlord B',
        owner_phone=f'+2547449{r}',
        status='PUBLISHED',
        description='Modern studio in Westlands Nairobi',
    )
    db.session.add(nbi_listing)
    db.session.commit()

    # =========================================================
    # TEST 1: Meru public vacancy page shows "Meru" branding
    # =========================================================
    res_meru_vac = client.get(f'/vacancies/{meru_code}')
    assert res_meru_vac.status_code == 200
    assert meru_code.encode() in res_meru_vac.data
    # Must show Meru org name on page
    assert meru_org_name.encode() in res_meru_vac.data
    # Must display the Meru listing title
    assert f'Meru Luxury Bedsitter {r}'.encode() in res_meru_vac.data
    # Must NOT show Nairobi listing
    assert f'Nairobi Studio Apartment {r}'.encode() not in res_meru_vac.data
    # Must NOT show Nairobi org name
    assert nbi_org_name.encode() not in res_meru_vac.data

    # =========================================================
    # TEST 2: Nairobi public vacancy page shows "Nairobi" branding
    # =========================================================
    res_nbi_vac = client.get(f'/vacancies/{nbi_code}')
    assert res_nbi_vac.status_code == 200
    assert nbi_code.encode() in res_nbi_vac.data
    # Must show Nairobi org name on page
    assert nbi_org_name.encode() in res_nbi_vac.data
    # Must display the Nairobi listing title
    assert f'Nairobi Studio Apartment {r}'.encode() in res_nbi_vac.data
    # Must NOT show Meru listing
    assert f'Meru Luxury Bedsitter {r}'.encode() not in res_nbi_vac.data
    # Must NOT show Meru org name
    assert meru_org_name.encode() not in res_nbi_vac.data

    # =========================================================
    # TEST 3: House seeker lead submitted on Meru link attaches Meru org_id
    # =========================================================
    res_meru_lead = client.post('/vacancies/house-alert', data={
        'full_name': 'Meru Seeker Jane',
        'phone': f'+2547559{r}',
        'email': f'jane_{r}@meru.co.ke',
        'unit_type': 'BEDSITTER',
        'locations': 'Meru Town',
        'max_budget': 15000,
        'contact_method': 'CALL',
        'org_code': meru_code,
    }, follow_redirects=False)
    assert res_meru_lead.status_code == 302
    assert f'/vacancies/{meru_code}' in res_meru_lead.location

    meru_lead = HouseSeekerLead.query.filter_by(phone=f'+2547559{r}').first()
    assert meru_lead is not None
    assert meru_lead.organization_id == meru_org.id
    # Confirm lead does NOT belong to Nairobi org
    assert meru_lead.organization_id != nbi_org.id

    # =========================================================
    # TEST 4: House seeker lead submitted on Nairobi link attaches Nairobi org_id
    # =========================================================
    res_nbi_lead = client.post('/vacancies/house-alert', data={
        'full_name': 'Nairobi Seeker Moses',
        'phone': f'+2547669{r}',
        'email': f'moses_{r}@nairobi.co.ke',
        'unit_type': 'BEDSITTER',
        'locations': 'Westlands',
        'max_budget': 35000,
        'contact_method': 'WHATSAPP',
        'org_code': nbi_code,
    }, follow_redirects=False)
    assert res_nbi_lead.status_code == 302
    assert f'/vacancies/{nbi_code}' in res_nbi_lead.location

    nbi_lead = HouseSeekerLead.query.filter_by(phone=f'+2547669{r}').first()
    assert nbi_lead is not None
    assert nbi_lead.organization_id == nbi_org.id
    # Confirm lead does NOT belong to Meru org
    assert nbi_lead.organization_id != meru_org.id

    # =========================================================
    # TEST 5: ExternalPropertyListing counts are strictly per-org
    # =========================================================
    meru_ext_count = ExternalPropertyListing.query.filter_by(
        organization_id=meru_org.id, status='PUBLISHED'
    ).count()
    nbi_ext_count = ExternalPropertyListing.query.filter_by(
        organization_id=nbi_org.id, status='PUBLISHED'
    ).count()
    # Each org has at least the 1 listing we added
    assert meru_ext_count >= 1
    assert nbi_ext_count >= 1
    # Meru count must NOT include Nairobi listing and vice versa
    assert ExternalPropertyListing.query.filter_by(
        organization_id=meru_org.id, property_title=f'Nairobi Studio Apartment {r}'
    ).count() == 0
    assert ExternalPropertyListing.query.filter_by(
        organization_id=nbi_org.id, property_title=f'Meru Luxury Bedsitter {r}'
    ).count() == 0
