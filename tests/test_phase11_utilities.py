import pytest
from datetime import date
from app import create_app
from app.extensions import db
from app.models.user import Role, User, Landlord
from app.models.property import Property, RentalUnit
from app.models.tenant import Tenant
from app.models.finance import RentCharge
from app.services.utility_service import UtilityService

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        admin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        db.session.add(admin_role)
        db.session.commit()

        admin = User(
            username='util_admin',
            email='util_admin@test.com',
            full_name='Utility Admin',
            role=admin_role,
            is_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)

        landlord = Landlord(name='Utility Landlord', phone='+254700112233')
        db.session.add(landlord)
        db.session.commit()

        prop = Property(
            landlord_id=landlord.id,
            name='Aqua Heights',
            ref_number='AQU-01',
            property_type='APARTMENT',
            location='Nairobi'
        )
        db.session.add(prop)
        db.session.commit()

        tenant = Tenant(
            first_name='Kevin',
            last_name='Otieno',
            id_passport_number='ID-998877',
            phone='+254711223344'
        )
        db.session.add(tenant)
        db.session.commit()

        unit = RentalUnit(
            property_id=prop.id,
            unit_number='A-101',
            unit_type='1_BEDROOM',
            rent_amount_cents=2000000,
            deposit_amount_cents=2000000,
            occupancy_status='OCCUPIED',
            current_tenant_id=tenant.id
        )
        db.session.add(unit)
        db.session.commit()

        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_meter_registration_and_properties(app):
    with app.app_context():
        prop = Property.query.first()
        unit = RentalUnit.query.first()

        meter = UtilityService.register_meter(
            property_id=prop.id,
            rental_unit_id=unit.id,
            meter_number='WTR-A101',
            meter_type='WATER',
            rate_per_unit=150.0,
            initial_reading=10.0
        )
        assert meter.id is not None
        assert meter.meter_number == 'WTR-A101'
        assert meter.meter_type == 'WATER'
        assert meter.rate_per_unit_cents == 15000
        assert meter.last_reading == 10.0

def test_meter_reading_and_auto_billing(app):
    with app.app_context():
        prop = Property.query.first()
        unit = RentalUnit.query.first()
        tenant = Tenant.query.first()

        meter = UtilityService.register_meter(
            property_id=prop.id,
            rental_unit_id=unit.id,
            meter_number='WTR-A101',
            meter_type='WATER',
            rate_per_unit=150.0,
            initial_reading=10.0
        )

        # Log new reading of 25.0 (consumed 15 units -> 15 * 150 KES = 2,250 KES = 225,000 cents)
        reading = UtilityService.record_reading(
            meter_id=meter.id,
            current_reading=25.0,
            reading_date=date(2026, 11, 2),
            auto_bill=True
        )

        assert reading.units_consumed == 15.0
        assert reading.total_cost_cents == 225000
        assert reading.billed_status == 'BILLED'
        assert reading.rent_charge_id is not None

        # Verify RentCharge created for tenant
        charge = RentCharge.query.get(reading.rent_charge_id)
        assert charge is not None
        assert charge.tenant_id == tenant.id
        assert charge.rental_unit_id == unit.id
        assert charge.amount_cents == 225000
        assert charge.charge_type == 'WATER'
        assert charge.status == 'UNPAID'

def test_reading_validation_guard(app):
    with app.app_context():
        prop = Property.query.first()
        unit = RentalUnit.query.first()

        meter = UtilityService.register_meter(
            property_id=prop.id,
            rental_unit_id=unit.id,
            meter_number='ELEC-01',
            meter_type='ELECTRICITY',
            rate_per_unit=25.0,
            initial_reading=50.0
        )

        # Attempt to record lower reading (e.g. 40.0)
        with pytest.raises(ValueError) as excinfo:
            UtilityService.record_reading(
                meter_id=meter.id,
                current_reading=40.0
            )
        assert "cannot be lower than previous reading" in str(excinfo.value)

def test_utilities_web_routes(client, app):
    # Login as admin
    client.post('/auth/login', data={'username': 'util_admin', 'password': 'AdminPass123!'}, follow_redirects=True)

    # Access utilities dashboard
    res = client.get('/utilities/')
    assert res.status_code == 200
    assert b'Water &amp; Electricity Meter Management' in res.data or b'Water' in res.data

    # Access caretaker entry page
    res = client.get('/utilities/caretaker-entry')
    assert res.status_code == 200
    assert b'Caretaker Meter Walkthrough' in res.data
