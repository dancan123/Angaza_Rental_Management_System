import pytest
from datetime import date, timedelta
from app import create_app
from app.extensions import db
from app.models.user import Role, User, Landlord
from app.models.property import RentalUnit
from app.models.tenant import Tenant
from app.models.lease import Lease
from app.services.property_service import PropertyService
from app.services.tenant_service import TenantService
from app.services.lease_service import LeaseService
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
            username='admin_lse',
            email='admin_lse@test.com',
            full_name='Lease Admin',
            role=admin_role,
            is_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)

        landlord = Landlord(name='Riverside Properties', phone='+254711444555')
        db.session.add(landlord)
        db.session.commit()

        prop = PropertyService.create_property(landlord.id, 'Riverside Courts', 'RS-01', 'APARTMENT', 'Riverside')
        unit = PropertyService.create_unit(prop.id, 'R-401', '2_BEDROOM', 45000, 45000)

        tenant = TenantService.create_tenant('Faith', 'Wambui', 'ID-667788', '+254712998877')
        db.session.commit()

        yield app
        db.session.remove()
        db.drop_all()

def test_lease_creation_and_pdf(app):
    with app.app_context():
        unit = RentalUnit.query.first()
        tenant = Tenant.query.first()
        assert unit.occupancy_status == 'VACANT'

        start = date(2026, 1, 1)
        end = date(2026, 12, 31)

        lease = LeaseService.create_lease(
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            start_date=start,
            end_date=end,
            monthly_rent=45000,
            deposit_amount=45000,
            notice_period_days=30
        )
        assert lease.id is not None
        assert lease.status == 'ACTIVE'
        assert lease.monthly_rent_cents == 4500000

        # Unit must now be OCCUPIED
        unit_refreshed = RentalUnit.query.get(unit.id)
        assert unit_refreshed.occupancy_status == 'OCCUPIED'
        assert unit_refreshed.current_tenant_id == tenant.id

        # Generate legal PDF agreement
        pdf_bytes = LeaseService.generate_lease_pdf(lease)
        assert pdf_bytes is not None
        assert len(pdf_bytes) > 500
        assert pdf_bytes.startswith(b'%PDF')

def test_expiring_leases_query(app):
    with app.app_context():
        unit = RentalUnit.query.first()
        tenant = Tenant.query.first()

        # Create lease expiring in 10 days
        expiry = date.today() + timedelta(days=10)
        LeaseService.create_lease(
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            start_date=date.today() - timedelta(days=350),
            end_date=expiry,
            monthly_rent=45000,
            deposit_amount=45000
        )

        expiring = LeaseService.get_expiring_leases(days_ahead=30)
        assert len(expiring) == 1
        assert expiring[0].end_date == expiry

