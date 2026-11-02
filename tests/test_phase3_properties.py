import pytest
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.property import Property, Building, Floor, RentalUnit
from app.services.property_service import PropertyService
from app.utils.currency import to_cents

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        admin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        db.session.add(admin_role)
        db.session.commit()

        admin = User(
            username='admin_prop',
            email='admin_prop@test.com',
            full_name='Property SuperAdmin',
            role=admin_role,
            is_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)

        landlord = Landlord(name='Savannah Heights Ltd', phone='+254722000111', email='info@savannah.co.ke')
        db.session.add(landlord)
        db.session.commit()

        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_property_and_unit_service(app):
    with app.app_context():
        landlord = Landlord.query.first()
        prop = PropertyService.create_property(
            landlord_id=landlord.id,
            name='Savannah Palace',
            ref_number='SAV-001',
            property_type='APARTMENT',
            location='Kileleshwa, Nairobi',
            total_floors=4
        )
        assert prop.id is not None
        assert prop.name == 'Savannah Palace'

        bld = PropertyService.add_building(prop.id, 'Tower A', 'TOW-A')
        flr = PropertyService.add_floor(bld.id, 1, 'First Floor')

        unit1 = PropertyService.create_unit(
            property_id=prop.id,
            building_id=bld.id,
            floor_id=flr.id,
            unit_number='A1',
            unit_type='2_BEDROOM',
            rent_amount=40000,
            deposit_amount=40000
        )
        unit2 = PropertyService.create_unit(
            property_id=prop.id,
            building_id=bld.id,
            floor_id=flr.id,
            unit_number='A2',
            unit_type='1_BEDROOM',
            rent_amount=28000,
            deposit_amount=28000
        )

        assert unit1.occupancy_status == 'VACANT'
        assert unit2.occupancy_status == 'VACANT'

        # Update status of unit1 to MAINTENANCE
        PropertyService.update_unit_status(unit1.id, 'MAINTENANCE', reason='Painting walls')
        u1_updated = RentalUnit.query.get(unit1.id)
        assert u1_updated.occupancy_status == 'MAINTENANCE'

        # Check occupancy stats
        stats = PropertyService.get_property_occupancy_stats(prop.id)
        assert stats['total'] == 2
        assert stats['vacant'] == 1
        assert stats['maintenance'] == 1
        assert stats['occupied'] == 0

def test_property_routes_flow(client, app):
    client.post('/auth/login', data={'username': 'admin_prop', 'password': 'AdminPass123!'}, follow_redirects=True)

    with app.app_context():
        landlord = Landlord.query.first()
        landlord_id = landlord.id

    # Create new property via HTTP POST
    res = client.post('/properties/create', data={
        'name': 'Golden View Villas',
        'ref_number': 'GVV-100',
        'property_type': 'RESIDENTIAL',
        'landlord_id': landlord_id,
        'location': 'Lavington, Nairobi',
        'total_floors': 2,
        'description': 'Luxury villas'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"Golden View Villas" in res.data

    with app.app_context():
        prop = Property.query.filter_by(ref_number='GVV-100').first()
        prop_id = prop.id

    # Add Unit to property
    res = client.post(f'/properties/{prop_id}/units/create', data={
        'unit_number': 'VILLA-1',
        'unit_type': '4_BEDROOM',
        'rent_amount': '85000',
        'deposit_amount': '85000',
        'bedrooms': '4',
        'bathrooms': '4',
        'amenities': 'Garden, Solar, Borehole'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"VILLA-1" in res.data

    # Check Visual Occupancy Grid page
    res = client.get('/properties/occupancy')
    assert res.status_code == 200
    assert b"Visual Property Occupancy Interface" in res.data
    assert b"VILLA-1" in res.data

