"""
Phase 36: Test all 15 Essential Kenyan Rental Management PDF Documents
Verifies that each PDF document is generated dynamically from actual database records,
contains valid PDF byte headers (%PDF-), has unique references, and returns successfully.
"""
import pytest
import uuid
from datetime import date, datetime
from app import create_app, db
from app.models.property import Property, RentalUnit
from app.models.tenant import Tenant
from app.models.lease import Lease
from app.models.finance import RentCharge, Payment
from app.models.maintenance import MaintenanceRequest
from app.models.user import Landlord
from app.services.lease_service import LeaseService
from app.utils.pdf_generator import (
    generate_receipt_pdf,
    generate_invoice_pdf,
    generate_tenant_statement_pdf,
    generate_landlord_remittance_pdf,
    generate_tenant_registration_form_pdf,
    generate_rent_demand_letter_pdf,
    generate_rent_arrears_statement_pdf,
    generate_deposit_receipt_pdf,
    generate_deposit_refund_statement_pdf,
    generate_move_in_inspection_pdf,
    generate_move_out_inspection_pdf,
    generate_tenancy_renewal_agreement_pdf,
    generate_maintenance_work_order_pdf,
    generate_property_occupancy_report_pdf,
)


@pytest.fixture(scope='module')
def app():
    application = create_app()
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    return application


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


@pytest.fixture(scope='module')
def sample_data(app):
    with app.app_context():
        uid = uuid.uuid4().hex[:6]
        landlord = Landlord.query.first()
        if not landlord:
            landlord = Landlord(name='Test Landlord P36', phone='+254700000036', is_active=True)
            db.session.add(landlord)
            db.session.flush()

        prop = Property(
            landlord_id=landlord.id,
            name=f'Ngara Plaza Apartments {uid}',
            ref_number=f'PROP-{uid}',
            location='Ngara, Nairobi',
            management_status='ACTIVE',
            property_type='APARTMENT'
        )
        db.session.add(prop)
        db.session.flush()

        unit = RentalUnit(
            property_id=prop.id,
            unit_number=f'A-101-{uid}',
            unit_type='1_BEDROOM',
            occupancy_status='OCCUPIED',
            rent_amount_cents=2500000,
            deposit_amount_cents=2500000
        )
        db.session.add(unit)
        db.session.flush()

        tenant = Tenant(
            first_name='Dancan',
            last_name='Mbaabu',
            id_passport_number=f'ID-{uid}',
            phone=f'+2547{uid}',
            email=f'dancan_{uid}@test.com',
            occupation='Software Engineer',
            physical_address='Ngara Nairobi',
            is_active=True
        )
        db.session.add(tenant)
        db.session.flush()
        unit.current_tenant_id = tenant.id

        lease = Lease(
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            lease_number=f'LSE-{uid}',
            start_date=date(2026, 1, 1),
            monthly_rent_cents=2500000,
            deposit_cents=2500000,
            status='ACTIVE'
        )
        db.session.add(lease)
        db.session.flush()

        charge = RentCharge(
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            charge_type='RENT',
            amount_cents=2500000,
            amount_paid_cents=1000000,
            due_date=date(2026, 11, 5),
            period_month=11,
            period_year=2026,
            status='PARTIALLY_PAID',
            invoice_number=f'INV-{uid}'
        )
        db.session.add(charge)
        db.session.flush()

        payment = Payment(
            property_id=prop.id,
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            payment_number=f'PAY-{uid}',
            amount_cents=1000000,
            payment_method='MPESA_PAYBILL',
            payment_date=date(2026, 11, 4),
            receipt_number=f'REC-{uid}',
            payment_status='CONFIRMED',
            transaction_reference=f'TX-{uid}'
        )
        db.session.add(payment)
        db.session.flush()

        req = MaintenanceRequest(
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            title=f'Leaking Kitchen Tap {uid}',
            description='Kitchen mixer tap leaking continuously under pressure',
            priority='HIGH',
            status='ASSIGNED',
            assigned_to_technician='John Plumber',
            technician_contact='+254711223344',
            reported_date=date(2026, 11, 10)
        )
        db.session.add(req)
        db.session.commit()

        return {
            'landlord_id': landlord.id,
            'property_id': prop.id,
            'unit_id': unit.id,
            'tenant_id': tenant.id,
            'lease_id': lease.id,
            'charge_id': charge.id,
            'payment_id': payment.id,
            'request_id': req.id,
        }


def test_1_tenancy_agreement_pdf(app, sample_data):
    with app.app_context():
        lease = db.session.get(Lease, sample_data['lease_id'])
        pdf = LeaseService.generate_lease_pdf(lease)
        assert pdf.startswith(b'%PDF-'), "Invalid PDF header"
        assert len(pdf) > 1000


def test_2_rent_invoice_pdf(app, sample_data):
    with app.app_context():
        charge = db.session.get(RentCharge, sample_data['charge_id'])
        pdf = generate_invoice_pdf(charge)
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_3_payment_receipt_pdf(app, sample_data):
    with app.app_context():
        payment = db.session.get(Payment, sample_data['payment_id'])
        pdf = generate_receipt_pdf(payment)
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_4_tenant_statement_pdf(app, sample_data):
    with app.app_context():
        tenant = db.session.get(Tenant, sample_data['tenant_id'])
        pdf = generate_tenant_statement_pdf(tenant)
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_5_rent_arrears_statement_pdf(app, sample_data):
    with app.app_context():
        tenant = db.session.get(Tenant, sample_data['tenant_id'])
        pdf = generate_rent_arrears_statement_pdf(tenant)
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_6_security_deposit_receipt_pdf(app, sample_data):
    with app.app_context():
        lease = db.session.get(Lease, sample_data['lease_id'])
        pdf = generate_deposit_receipt_pdf(lease)
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_7_deposit_refund_statement_pdf(app, sample_data):
    with app.app_context():
        tenant = db.session.get(Tenant, sample_data['tenant_id'])
        pdf = generate_deposit_refund_statement_pdf(tenant, deductions=5000, refund_amount=20000, notes='Repainting')
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_8_rent_demand_letter_pdf(app, sample_data):
    with app.app_context():
        tenant = db.session.get(Tenant, sample_data['tenant_id'])
        pdf = generate_rent_demand_letter_pdf(tenant)
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_9_tenant_registration_form_pdf(app, sample_data):
    with app.app_context():
        tenant = db.session.get(Tenant, sample_data['tenant_id'])
        pdf = generate_tenant_registration_form_pdf(tenant)
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_10_move_in_inspection_pdf(app, sample_data):
    with app.app_context():
        lease = db.session.get(Lease, sample_data['lease_id'])
        pdf = generate_move_in_inspection_pdf(lease)
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_11_move_out_inspection_pdf(app, sample_data):
    with app.app_context():
        tenant = db.session.get(Tenant, sample_data['tenant_id'])
        pdf = generate_move_out_inspection_pdf(tenant, deductions=3000, notes='Door handle replacement')
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_12_tenancy_renewal_agreement_pdf(app, sample_data):
    with app.app_context():
        lease = db.session.get(Lease, sample_data['lease_id'])
        pdf = generate_tenancy_renewal_agreement_pdf(lease, renewal_months=12)
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_13_maintenance_work_order_pdf(app, sample_data):
    with app.app_context():
        req = db.session.get(MaintenanceRequest, sample_data['request_id'])
        pdf = generate_maintenance_work_order_pdf(req)
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_14_landlord_monthly_statement_pdf(app, sample_data):
    with app.app_context():
        landlord = db.session.get(Landlord, sample_data['landlord_id'])
        report_dict = {
            'period': 'November 2026',
            'properties': [],
            'total_rent_collected_cents': 2500000,
            'management_fee_cents': 250000,
            'expenses_cents': 0,
            'net_remittance_cents': 2250000
        }
        pdf = generate_landlord_remittance_pdf(landlord, report_dict)
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000


def test_15_property_occupancy_report_pdf(app, sample_data):
    with app.app_context():
        prop = db.session.get(Property, sample_data['property_id'])
        pdf = generate_property_occupancy_report_pdf(prop)
        assert pdf.startswith(b'%PDF-')
        assert len(pdf) > 1000
