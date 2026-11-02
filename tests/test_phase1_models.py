import pytest
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.property import Property, Building, Floor, RentalUnit
from app.models.tenant import Tenant
from app.models.booking import Booking
from app.models.lease import Lease
from app.models.finance import RentCharge, Payment, PaymentAllocation
from app.services.personalization_service import PersonalizationService
from app.utils.currency import to_cents, from_cents, format_currency
from decimal import Decimal
from datetime import date

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_currency_helpers():
    assert to_cents(100) == 10000
    assert to_cents(1250.50) == 125050
    assert to_cents('450.75') == 45075
    assert from_cents(125050) == Decimal('1250.50')
    assert format_currency(125050, 'KES') == 'KES 1,250.50'

def test_roles_and_permissions(app):
    with app.app_context():
        perm_view = Permission(code='properties.view', module='properties', description='View properties')
        perm_manage = Permission(code='properties.manage', module='properties', description='Manage properties')
        db.session.add_all([perm_view, perm_manage])
        db.session.commit()

        role_caretaker = Role(name='CARETAKER', display_name='Caretaker')
        role_caretaker.permissions = [perm_view]
        role_super = Role(name='SUPERADMIN', display_name='Super Administrator')
        db.session.add_all([role_caretaker, role_super])
        db.session.commit()

        user1 = User(username='caretaker1', email='ct@rentals.com', full_name='John Caretaker', role=role_caretaker)
        user1.set_password('Secret123!')
        
        user2 = User(username='super1', email='super@rentals.com', full_name='Admin Boss', role=role_super)
        user2.set_password('Admin123!')
        
        db.session.add_all([user1, user2])
        db.session.commit()

        assert user1.check_password('Secret123!') is True
        assert user1.check_password('WrongPass') is False
        assert user1.has_permission('properties.view') is True
        assert user1.has_permission('properties.manage') is False
        assert user2.has_permission('properties.manage') is True  # Superadmin has wildcard access

def test_property_and_unit_hierarchy(app):
    with app.app_context():
        landlord = Landlord(name='Apex Holdings', phone='+254711223344', email='apex@holdings.co.ke')
        db.session.add(landlord)
        db.session.commit()

        prop = Property(
            landlord_id=landlord.id,
            name='Green View Heights',
            ref_number='GVH-001',
            location='Kilimani, Nairobi',
            property_type='APARTMENT'
        )
        db.session.add(prop)
        db.session.commit()

        bld = Building(property_id=prop.id, name='Block A', code='BLK-A')
        db.session.add(bld)
        db.session.commit()

        flr = Floor(building_id=bld.id, floor_number=1, floor_name='First Floor')
        db.session.add(flr)
        db.session.commit()

        unit = RentalUnit(
            property_id=prop.id,
            building_id=bld.id,
            floor_id=flr.id,
            unit_number='A-101',
            unit_type='2_BEDROOM',
            rent_amount_cents=to_cents(35000),
            deposit_amount_cents=to_cents(35000),
            occupancy_status='VACANT'
        )
        db.session.add(unit)
        db.session.commit()

        assert unit.property.name == 'Green View Heights'
        assert unit.building.name == 'Block A'
        assert unit.floor.floor_name == 'First Floor'
        assert unit.rent_display == 'KES 35,000.00'
        assert unit.deposit_display == 'KES 35,000.00'
        assert unit.occupancy_status == 'VACANT'

def test_personalization_service(app):
    with app.app_context():
        PersonalizationService.initialize_default_settings()
        currency = PersonalizationService.get_setting('currency')
        assert currency == 'KES'

        # Update setting
        PersonalizationService.update_settings({'currency': 'USD', 'business_name': 'Global Estates'})
        assert PersonalizationService.get_setting('currency') == 'USD'
        assert PersonalizationService.get_setting('business_name') == 'Global Estates'

