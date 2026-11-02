import pytest
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.property import Property, RentalUnit
from app.models.tenant import Tenant, NextOfKin
from app.models.lead import ExternalPropertyListing, HouseSeekerLead
from app.services.tenant_service import TenantService
from app.services.property_service import PropertyService

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        admin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        p1 = Permission(code='tenants.view', module='tenants', description='View tenants')
        p2 = Permission(code='tenants.manage', module='tenants', description='Manage tenants')
        p3 = Permission(code='properties.view', module='properties', description='View properties')
        p4 = Permission(code='properties.manage', module='properties', description='Manage properties')
        p5 = Permission(code='units.view', module='units', description='View units')
        p6 = Permission(code='units.manage', module='units', description='Manage units')
        db.session.add_all([admin_role, p1, p2, p3, p4, p5, p6])
        db.session.commit()

        admin = User(
            username='admin_market',
            email='admin_market@test.com',
            full_name='Marketplace Admin',
            role=admin_role,
            is_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)

        landlord = Landlord(name='Apex Holdings', phone='+254700112233')
        db.session.add(landlord)
        db.session.commit()

        prop = PropertyService.create_property(landlord.id, 'Apex Heights', 'APX-01', 'APARTMENT', 'Kilimani')
        PropertyService.create_unit(prop.id, 'A-101', '1_BEDROOM', 35000, 35000)

        # Seed a tenant
        TenantService.create_tenant(
            first_name='John',
            last_name='Kamau',
            id_passport_number='30112233',
            phone='+254711000111',
            email='john.kamau@test.com'
        )

        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def login_admin(client):
    return client.post('/auth/login', data={'username': 'admin_market', 'password': 'AdminPass123!'}, follow_redirects=True)

def test_tenant_search_and_detail_query(client, app):
    login_admin(client)
    # Search by national ID
    resp = client.get('/tenants/?search=30112233')
    assert resp.status_code == 200
    assert b'John' in resp.data

    # Direct search redirect when 1 match found
    resp_direct = client.get('/tenants/?search=30112233&direct=1')
    assert resp_direct.status_code == 302
    assert '/tenants/' in resp_direct.location

    # Search by phone digits
    with app.app_context():
        tenants = TenantService.get_tenants(search='711000111')
        assert len(tenants) >= 1
        assert tenants[0].id_passport_number == '30112233'

def test_tenant_edit_profile(client, app):
    login_admin(client)
    with app.app_context():
        t = Tenant.query.filter_by(id_passport_number='30112233').first()
        assert t is not None
        tenant_id = t.id

    edit_data = {
        'first_name': 'Johnathan',
        'last_name': 'Kamau',
        'id_passport_number': '30112233',
        'phone': '+254711999888',
        'email': 'johnathan.kamau@example.com',
        'occupation': 'Senior Architect',
        'physical_address': 'Kilimani, Nairobi',
        'kin_name': 'Sarah Kamau',
        'kin_relationship': 'Spouse',
        'kin_phone': '+254722888999',
        'emergency_contact': 'Sarah Kamau',
        'emergency_phone': '+254722888999'
    }
    resp = client.post(f'/tenants/{tenant_id}/edit', data=edit_data, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        refreshed = db.session.get(Tenant, tenant_id)
        assert refreshed.first_name == 'Johnathan'
        assert refreshed.occupation == 'Senior Architect'

def test_external_property_listing_workflow(client, app):
    login_admin(client)
    # 1. Admin creates and publishes an external apartment
    listing_data = {
        'property_title': 'Kilimani Garden Suites 4B',
        'location': 'Wood Avenue, Kilimani',
        'unit_type': '2_BEDROOM',
        'monthly_rent': '65000',
        'deposit': '65000',
        'bedrooms': '2',
        'bathrooms': '2',
        'features': 'Lift, Borehole, Solar Water Heater, Balcony',
        'description': 'Executive 2 bedroom master ensuite apartment',
        'owner_name': 'Peter Njoroge',
        'owner_phone': '+254722334455',
        'owner_email': 'peter@investments.co.ke',
        'status': 'PUBLISHED'
    }
    resp = client.post('/properties/external-listings/create', data=listing_data, follow_redirects=True)
    assert resp.status_code == 200
    assert b'Kilimani Garden Suites 4B' in resp.data

    with app.app_context():
        listing = ExternalPropertyListing.query.filter_by(property_title='Kilimani Garden Suites 4B').first()
        assert listing is not None
        assert listing.status == 'PUBLISHED'
        assert listing.monthly_rent_cents == 6500000
        listing_id = listing.id

    # 2. Verify external listing reflects on public vacancies website without exposing landlord primaries
    pub_resp = client.get('/vacancies')
    assert pub_resp.status_code == 200
    assert b'Kilimani Garden Suites 4B' in pub_resp.data
    assert b'Partner Listing' in pub_resp.data
    # Ensure landlord personal phone number is NOT exposed on public site
    assert b'+254722334455' not in pub_resp.data

    # 3. Prospective tenant submits an inquiry for this partner listing
    inq_data = {
        'listing_id': str(listing_id),
        'full_name': 'Grace Wambui',
        'phone': '+254733445566',
        'email': 'grace@example.com',
        'expected_move_in': '2026-11-15',
        'notes': 'Interested in viewing on Saturday.'
    }
    inq_resp = client.post('/vacancies/inquire-external', data=inq_data, follow_redirects=True)
    assert inq_resp.status_code == 200
    assert b'Grace Wambui' in inq_resp.data

    # 4. Angaza staff allocates / links the house to Grace Wambui
    alloc_data = {
        'tenant_name': 'Grace Wambui',
        'tenant_phone': '+254733445566',
        'allocation_notes': 'Physical viewing done on 05/11, deposit cleared.'
    }
    alloc_resp = client.post(f'/properties/external-listings/{listing_id}/allocate', data=alloc_data, follow_redirects=True)
    assert alloc_resp.status_code == 200
    with app.app_context():
        refreshed_listing = db.session.get(ExternalPropertyListing, listing_id)
        assert refreshed_listing.status == 'ALLOCATED'
        assert refreshed_listing.allocated_tenant_name == 'Grace Wambui'

    # 5. Onboard to core managed property
    onboard_resp = client.post(f'/properties/external-listings/{listing_id}/onboard-managed', follow_redirects=True)
    assert onboard_resp.status_code == 200
    with app.app_context():
        refreshed_listing = db.session.get(ExternalPropertyListing, listing_id)
        assert refreshed_listing.status == 'RENTED'
        onboarded_prop = Property.query.filter_by(name='Kilimani Garden Suites 4B').first()
        assert onboarded_prop is not None

    # 6. Delete listing
    del_resp = client.post(f'/properties/external-listings/{listing_id}/delete', follow_redirects=True)
    assert del_resp.status_code == 200
    with app.app_context():
        assert db.session.get(ExternalPropertyListing, listing_id) is None

def test_unit_edit_workflow(client, app):
    login_admin(client)
    with app.app_context():
        prop = Property.query.first()
        assert prop is not None
        prop_id = prop.id

    # Create a test vacant unit
    unit_data = {
        'unit_number': 'TEST-UNIT-99',
        'unit_type': '1_BEDROOM',
        'rent_amount': '25000',
        'deposit_amount': '25000',
        'bedrooms': '1',
        'bathrooms': '1',
        'amenities': 'Balcony',
        'description': 'Cozy 1 bedroom apartment'
    }
    client.post(f'/properties/{prop_id}/units/create', data=unit_data, follow_redirects=True)
    
    with app.app_context():
        unit = RentalUnit.query.filter_by(unit_number='TEST-UNIT-99', property_id=prop_id).first()
        assert unit is not None
        unit_id = unit.id

    # Edit unit details
    edit_data = {
        'unit_number': 'TEST-UNIT-99B',
        'unit_type': '2_BEDROOM',
        'rent_amount': '32000',
        'deposit_amount': '32000',
        'bedrooms': '2',
        'bathrooms': '1',
        'amenities': 'Renovated, Balcony, Top Floor',
        'description': 'Upgraded 2 bedroom unit',
        'occupancy_status': 'VACANT'
    }
    resp = client.post(f'/properties/units/{unit_id}/edit', data=edit_data, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        refreshed = db.session.get(RentalUnit, unit_id)
        assert refreshed.unit_number == 'TEST-UNIT-99B'
        assert refreshed.rent_amount_cents == 3200000
        assert refreshed.bedrooms == 2

    # Delete unit
    del_resp = client.post(f'/properties/units/{unit_id}/delete', follow_redirects=True)
    assert del_resp.status_code == 200
    with app.app_context():
        assert db.session.get(RentalUnit, unit_id) is None
