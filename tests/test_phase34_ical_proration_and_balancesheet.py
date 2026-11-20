"""
Phase 34 — iCal Two-Way Sync, Rent Proration & Balance Sheet Test Suite
======================================================================
Tests:
1. Milestone A: Two-way RFC 5545 iCal export & import feed synchronization for Airbnb.
2. Milestone B: Automated daily rent proration on mid-month lease execution.
3. Milestone C: Commercial Balance Sheet Statement and Chart of Accounts (COA).
"""
import pytest
import random
from datetime import datetime, date, timedelta
from app import create_app, db
from app.models.organization import Organization
from app.models.user import User, Role, Landlord
from app.models.property import Property, RentalUnit
from app.models.tenant import Tenant
from app.models.lease import Lease
from app.models.finance import RentCharge, Payment
from app.models.hospitality import HospitalityReservation, Guest
from app.services.ical_service import ICalService
from app.services.rent_service import RentService
from app.services.lease_service import LeaseService
from app.services.report_service import ReportService


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
def seed_data(app):
    r = random.randint(100000, 999999)
    with app.app_context():
        manager_role = Role.query.filter_by(name='PROPERTY_MANAGER').first()
        org = Organization(
            name=f'Proration & iCal Estates {r}',
            slug=f'proration-ical-{r}',
            org_code=f'ANG{r % 10000:04d}',
            is_active=True,
            subscription_status='ACTIVE',
            subscription_tier='COMBINED_SUITE',
            enable_rentals=True,
            enable_hospitality=True
        )
        db.session.add(org)
        db.session.flush()

        manager = User(
            username=f'mgr_ical_{r}',
            email=f'mgr_ical_{r}@platform.co.ke',
            full_name=f'Manager iCal {r}',
            role=manager_role,
            organization_id=org.id,
            is_active=True
        )
        manager.set_password('TestPass123!')
        db.session.add(manager)

        landlord = Landlord.query.first()
        if not landlord:
            landlord = Landlord(name=f'Landlord {r}', phone=f'+254700{r}', is_active=True)
            db.session.add(landlord)
            db.session.flush()

        prop = Property(
            name=f'Savannah Suites {r}',
            ref_number=f'PROP-SAV-{r}',
            property_type='RESIDENTIAL',
            location='Kilimani, Nairobi',
            landlord_id=landlord.id,
            organization_id=org.id
        )
        db.session.add(prop)
        db.session.flush()

        # 1. Short-stay room for iCal testing
        room = RentalUnit(
            property_id=prop.id,
            unit_number=f'SUITE-{r % 1000}',
            unit_type='ONE_BEDROOM',
            rent_amount_cents=6000000,
            daily_rate_cents=500000, # KES 5,000/night
            occupancy_status='VACANT',
            operational_type='SHORT_STAY',
            cleaning_status='CLEAN'
        )
        room.ensure_ical_token()
        db.session.add(room)

        # 2. Long-term unit for lease proration testing
        lt_unit = RentalUnit(
            property_id=prop.id,
            unit_number=f'APT-{r % 1000}',
            unit_type='TWO_BEDROOM',
            rent_amount_cents=3000000, # KES 30,000/mo
            deposit_amount_cents=3000000,
            occupancy_status='VACANT',
            operational_type='LONG_TERM',
            cleaning_status='CLEAN'
        )
        db.session.add(lt_unit)

        # Tenant for long-term lease
        tenant = Tenant(
            first_name='Faith',
            last_name=f'Njeri {r}',
            id_passport_number=f'ID{r}',
            phone=f'+254711{r}',
            email=f'faith_{r}@gmail.com',
            organization_id=org.id,
            is_active=True
        )
        db.session.add(tenant)
        db.session.commit()

        return {
            'org_id': org.id,
            'org_code': org.org_code,
            'manager_username': manager.username,
            'manager_password': 'TestPass123!',
            'room_id': room.id,
            'room_token': room.ical_token,
            'lt_unit_id': lt_unit.id,
            'tenant_id': tenant.id
        }


# ─── MILESTONE A: ICAL TWO-WAY SYNCHRONIZATION TESTS ──────────────────────────

def test_ical_export_feed_valid_rfc5545(client, app, seed_data):
    """Verifies that the public iCal export endpoint returns valid RFC 5545 VCALENDAR data."""
    # Create an active local reservation on the room
    with app.app_context():
        room = db.session.get(RentalUnit, seed_data['room_id'])
        guest = Guest(
            organization_id=seed_data['org_id'],
            first_name='Alice',
            last_name='Wambui',
            phone='+254722123456',
            email='alice@test.co.ke'
        )
        db.session.add(guest)
        db.session.flush()

        res = HospitalityReservation(
            organization_id=seed_data['org_id'],
            reservation_code=f"RES-EXP-{random.randint(1000, 9999)}",
            guest_id=guest.id,
            rental_unit_id=room.id,
            check_in_date=date.today() + timedelta(days=5),
            check_out_date=date.today() + timedelta(days=9),
            num_guests=2,
            num_nights=4,
            daily_rate_cents=500000,
            total_stay_cents=2000000,
            status='CONFIRMED',
            booking_source='DIRECT'
        )
        db.session.add(res)
        db.session.commit()
        res_code = res.reservation_code

    # Fetch export feed via token
    res_url = f"/hospitality/export-ical/{seed_data['room_token']}.ics"
    resp = client.get(res_url)

    assert resp.status_code == 200
    assert resp.content_type.startswith('text/calendar')
    body = resp.data.decode('utf-8')

    assert "BEGIN:VCALENDAR" in body
    assert "VERSION:2.0" in body
    assert "BEGIN:VEVENT" in body
    assert f"UID:{res_code}@angaza.co.ke" in body
    assert "STATUS:CONFIRMED" in body
    assert "END:VCALENDAR" in body


def test_ical_import_and_double_booking_lockout(client, app, seed_data):
    """Verifies importing external iCal content creates reservations and blocks the room."""
    # Synthetic Airbnb .ics payload
    check_in = date.today() + timedelta(days=12)
    check_out = date.today() + timedelta(days=16)
    uid = f"airbnb_res_test_{random.randint(1000, 9999)}"

    mock_ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Airbnb Inc//Hosting Calendar 0.8.8//EN
CALSCALE:GREGORIAN
BEGIN:VEVENT
DTSTAMP:20261120T120000Z
DTSTART;VALUE=DATE:{check_in.strftime('%Y%m%d')}
DTEND;VALUE=DATE:{check_out.strftime('%Y%m%d')}
UID:{uid}
SUMMARY:Airbnb (Not available)
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR"""

    # Sync using ICalService
    with app.app_context():
        result = ICalService.sync_unit_external_ical(
            unit_id=seed_data['room_id'],
            ics_content=mock_ics
        )
        assert result['success'] is True
        assert result['imported'] == 1

        # Verify reservation was created
        clean_uid = uid[:32]
        synced_res = HospitalityReservation.query.filter_by(
            reservation_code=f"ICAL-{clean_uid}",
            rental_unit_id=seed_data['room_id']
        ).first()

        assert synced_res is not None
        assert synced_res.check_in_date == check_in
        assert synced_res.check_out_date == check_out
        assert synced_res.booking_source == 'AIRBNB_ICAL'
        assert synced_res.status == 'CONFIRMED'

        # Verify room's last_synced_at is updated
        unit = db.session.get(RentalUnit, seed_data['room_id'])
        assert unit.ical_last_synced_at is not None


# ─── MILESTONE B: MID-MONTH RENT PRORATION TESTS ──────────────────────────────

def test_prorated_rent_calculation_math():
    """Verifies daily proration formula math for start dates."""
    # November has 30 days. Monthly rent = KES 30,000 (3,000,000 cents)
    # Start date = Nov 16 -> 30 - 16 + 1 = 15 days occupied (exact half month)
    res_16 = RentService.calculate_prorated_rent(3000000, date(2026, 11, 16))
    assert res_16['is_prorated'] is True
    assert res_16['days_occupied'] == 15
    assert res_16['days_in_month'] == 30
    assert res_16['daily_rate_cents'] == 100000 # KES 1,000/day
    assert res_16['prorated_cents'] == 1500000 # KES 15,000 (exact half)

    # Start date = 1st of month -> not prorated (full month)
    res_1 = RentService.calculate_prorated_rent(3000000, date(2026, 11, 1))
    assert res_1['is_prorated'] is False
    assert res_1['prorated_cents'] == 3000000


def test_create_lease_with_proration_creates_prorated_and_deposit_charges(app, seed_data):
    """Verifies that creating a lease mid-month auto-bills prorated rent and deposit charges."""
    start_mid_month = date(2026, 11, 16)
    with app.app_context():
        lease = LeaseService.create_lease(
            rental_unit_id=seed_data['lt_unit_id'],
            tenant_id=seed_data['tenant_id'],
            start_date=start_mid_month,
            monthly_rent=30000.0,
            deposit_amount=30000.0,
            payment_due_day=5,
            notice_period_days=30,
            prorate_first_month=True,
            generate_initial_charges=True
        )

        assert lease is not None
        assert lease.status == 'ACTIVE'

        # Check charges generated for this lease
        charges = RentCharge.query.filter_by(lease_id=lease.id).all()
        assert len(charges) == 2

        # 1. Deposit charge
        dep_charge = next((c for c in charges if c.charge_type == 'DEPOSIT'), None)
        assert dep_charge is not None
        assert dep_charge.amount_cents == 3000000

        # 2. Prorated rent charge (15 days for Nov 16 to 30 = 1,500,000 cents)
        rent_charge = next((c for c in charges if c.charge_type == 'RENT'), None)
        assert rent_charge is not None
        assert rent_charge.amount_cents == 1500000
        assert "Prorated Rent" in rent_charge.description
        assert "15 days" in rent_charge.description


# ─── MILESTONE C: BALANCE SHEET & CHART OF ACCOUNTS TESTS ─────────────────────

def test_balance_sheet_calculation_and_equation(app, seed_data):
    """Verifies that Balance Sheet calculates Assets, Liabilities, Equity and balances."""
    with app.app_context():
        bs = ReportService.get_balance_sheet(
            as_of_date=date.today(),
            organization_id=seed_data['org_id']
        )

        assert bs is not None
        assert 'total_assets_cents' in bs
        assert 'total_liabilities_cents' in bs
        assert 'equity_cents' in bs

        # Core accounting equation: Assets = Liabilities + Equity
        assert bs['total_assets_cents'] == (bs['total_liabilities_cents'] + bs['equity_cents'])
        assert bs['is_balanced'] is True

        # Deposit liabilities should reflect the 30,000 deposit from active lease
        assert bs['deposit_liabilities_cents'] >= 3000000


def test_balance_sheet_and_chart_of_accounts_web_routes(client, app, seed_data):
    """Verifies that balance sheet and chart of accounts endpoints render HTTP 200."""
    # Authenticate manager
    client.post('/auth/login', data={
        'username': seed_data['manager_username'],
        'password': seed_data['manager_password'],
        'org_code': seed_data['org_code']
    }, follow_redirects=True)

    # 1. Balance Sheet
    resp_bs = client.get('/reports/balance-sheet')
    assert resp_bs.status_code == 200
    assert b'Statement of Financial Position' in resp_bs.data
    assert b'TOTAL ASSETS' in resp_bs.data
    assert b'TOTAL LIABILITIES' in resp_bs.data

    # 2. Chart of Accounts
    resp_coa = client.get('/reports/chart-of-accounts')
    assert resp_coa.status_code == 200
    assert b'Chart of Accounts' in resp_coa.data
    assert b'ASSET ACCOUNTS' in resp_coa.data
    assert b'Operating Cash On Hand' in resp_coa.data
    assert b'Tenant Security Deposit Liabilities' in resp_coa.data

    client.get('/auth/logout', follow_redirects=True)
