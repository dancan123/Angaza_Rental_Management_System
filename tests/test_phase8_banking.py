import io
import pytest
from datetime import date
from app import create_app
from app.extensions import db
from app.models.user import Role, User, Landlord
from app.models.property import RentalUnit
from app.models.tenant import Tenant
from app.models.lease import Lease
from app.models.finance import RentCharge, Payment
from app.models.gateway import BankAccount, BankTransaction
from app.services.property_service import PropertyService
from app.services.tenant_service import TenantService
from app.services.rent_service import RentService
from app.services.bank_service import BankService
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
            username='admin_bnk',
            email='admin_bnk@test.com',
            full_name='Banking Admin',
            role=admin_role,
            is_active=True
        )
        admin.set_password('AdminPass123!')
        db.session.add(admin)

        landlord = Landlord(name='Equator Properties', phone='+254700888111')
        db.session.add(landlord)
        db.session.commit()

        prop = PropertyService.create_property(landlord.id, 'Equator Plaza', 'EQ-01', 'COMMERCIAL', 'Upperhill')
        unit = PropertyService.create_unit(prop.id, 'OFFICE-3B', 'OFFICE_SPACE', 60000, 60000)

        tenant = TenantService.create_tenant('Samuel', 'Kariuki', 'ID-334455', '+254711334455')
        unit.occupancy_status = 'OCCUPIED'
        unit.current_tenant_id = tenant.id

        lease = Lease(
            lease_number='LSE-EQ-3B',
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            start_date=date(2026, 1, 1),
            monthly_rent_cents=to_cents(60000),
            status='ACTIVE'
        )
        db.session.add(lease)
        db.session.commit()

        # Monthly rent charge of 60,000
        RentService.generate_monthly_charges(11, 2026)

        yield app
        db.session.remove()
        db.drop_all()

def test_bank_statement_csv_import_and_reconciliation(app):
    with app.app_context():
        tenant = Tenant.query.first()
        acc = BankService.create_bank_account('KCB Bank', 'Equator Rent Collection', '1122334455', 'Upperhill')
        assert acc.id is not None

        # Prepare mock CSV statement data
        csv_content = (
            "Date,Reference,Description,Credit\n"
            "2026-11-02,EFT-998811,RENT PAYMENT FOR OFFICE-3B SAMUEL,60000.00\n"
            "2026-11-02,EFT-998822,UNKNOWN DIRECT TRANSFER REF 8877,25000.00\n"
        ).encode('utf-8')

        stream = io.BytesIO(csv_content)
        result = BankService.parse_and_import_statement(acc.id, stream, 'kcb_statement.csv')
        assert result['imported_count'] == 2

        # First transaction had 'OFFICE-3B' in narration so it should be MATCHED
        tx1 = BankTransaction.query.filter_by(reference='EFT-998811').first()
        assert tx1 is not None
        assert tx1.reconciliation_status == 'MATCHED'
        assert tx1.amount_cents == 6000000

        # Second transaction is UNMATCHED
        tx2 = BankTransaction.query.filter_by(reference='EFT-998822').first()
        assert tx2 is not None
        assert tx2.reconciliation_status == 'UNMATCHED'
        assert tx2.amount_cents == 2500000

        # Accountant performs manual reconciliation on tx2
        payment = BankService.reconcile_transaction(tx2.id, tenant.id)
        assert payment.payment_status == 'CONFIRMED'
        assert payment.receipt_number.startswith('REC-')
        assert tx2.reconciliation_status == 'MANUALLY_RECONCILED'
        assert tx2.matched_payment_id == payment.id

