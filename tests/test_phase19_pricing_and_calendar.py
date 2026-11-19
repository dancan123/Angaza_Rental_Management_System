"""
Phase 19 – Seasonal Pricing Rules and Availability Calendar Tests
Tests:
  1. RoomPricingRule model creation, date matching, and multiplier calculations
  2. Dynamic rate adjustment applied during HospitalityService.create_reservation()
  3. Pricing rules CRUD routes and toggling
  4. Availability calendar view rendering
  5. SMS history report rendering
"""
import pytest
from datetime import date, timedelta
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User, Landlord
from app.models.property import Property, RentalUnit
from app.models.pricing import RoomPricingRule
from app.models.hospitality import Guest, HospitalityReservation
from app.services.hospitality_service import HospitalityService
from app.utils.currency import to_cents


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        admin_role = Role(name='SUPERADMIN', display_name='Super Admin', is_system=True)
        perms = [
            Permission(code='bookings.view', module='bookings', description='View bookings'),
            Permission(code='properties.manage', module='properties', description='Manage properties'),
            Permission(code='communication.view', module='communication', description='View messages'),
        ]
        db.session.add(admin_role)
        db.session.add_all(perms)
        db.session.commit()

        admin = User(
            username='yield_manager',
            email='yield@angaza.co.ke',
            full_name='Revenue Manager',
            role=admin_role,
            is_active=True
        )
        admin.set_password('YieldPass2026!')
        db.session.add(admin)

        ll = Landlord(name='Coastal Retreats', phone='+254711777888')
        db.session.add(ll)
        db.session.commit()

        prop = Property(
            landlord_id=ll.id,
            name='Diani Beachfront Villas',
            ref_number='DBV-001',
            property_type='HOSPITALITY',
            location='Diani, Kwale'
        )
        db.session.add(prop)
        db.session.commit()

        unit = RentalUnit(
            property_id=prop.id,
            unit_number='V-101',
            operational_type='SHORT_STAY',
            daily_rate_cents=to_cents(10000)  # Base rate: 10,000 KES
        )
        db.session.add(unit)
        db.session.commit()

        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_pricing_rule_model_logic(app):
    """Verify rule application and multiplier calculations."""
    with app.app_context():
        today = date.today()
        rule = RoomPricingRule(
            name='Easter Holiday Peak',
            start_date=today,
            end_date=today + timedelta(days=5),
            rule_type='MULTIPLIER',
            multiplier=1.5,  # +50%
            category='PEAK_SEASON'
        )
        db.session.add(rule)
        db.session.commit()

        assert rule.applies_on_date(today) is True
        assert rule.applies_on_date(today + timedelta(days=2)) is True
        assert rule.applies_on_date(today + timedelta(days=10)) is False

        # 10,000 base * 1.5 = 15,000
        effective_rate = rule.compute_rate_cents(to_cents(10000))
        assert effective_rate == to_cents(15000)
        assert rule.multiplier_pct_display == '+50.0%'


def test_reservation_creation_with_pricing_rule(app):
    """Verify HospitalityService uses active pricing rule when calculating total stay."""
    with app.app_context():
        unit = RentalUnit.query.first()
        today = date.today()

        # Add 50% peak season rule for this unit
        rule = RoomPricingRule(
            name='High Season Markup',
            rental_unit_id=unit.id,
            start_date=today,
            end_date=today + timedelta(days=10),
            rule_type='MULTIPLIER',
            multiplier=1.5,
            is_active=True
        )
        db.session.add(rule)
        db.session.commit()

        # Create 2-night reservation
        res = HospitalityService.create_reservation(
            unit_id=unit.id,
            guest_data={
                'first_name': 'Mary',
                'last_name': 'Atieno',
                'phone': '+254700998877'
            },
            check_in_date=today,
            check_out_date=today + timedelta(days=2)
        )

        assert res.id is not None
        assert res.num_nights == 2
        # 10,000 * 1.5 * 2 nights = 30,000 KES (3,000,000 cents)
        assert res.total_stay_cents == to_cents(30000)


def test_pricing_routes_crud(app, client):
    """Test pricing rule creation and toggling via routes."""
    client.post('/auth/login', data={
        'username': 'yield_manager',
        'password': 'YieldPass2026!'
    }, follow_redirects=True)

    today = date.today()
    res = client.post('/hospitality/pricing/create', data={
        'name': 'Christmas 2026 Peak',
        'category': 'PEAK_SEASON',
        'start_date': today.isoformat(),
        'end_date': (today + timedelta(days=7)).isoformat(),
        'rule_type': 'MULTIPLIER',
        'multiplier': '1.30',
        'flat_rate': '0'
    }, follow_redirects=True)

    assert res.status_code == 200
    assert b'Christmas 2026 Peak' in res.data

    with app.app_context():
        rule = RoomPricingRule.query.filter_by(name='Christmas 2026 Peak').first()
        assert rule is not None
        assert rule.multiplier == 1.3
        rule_id = rule.id

    # Toggle rule
    res = client.post(f'/hospitality/pricing/{rule_id}/toggle', follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        rule_refreshed = db.session.get(RoomPricingRule, rule_id)
        assert rule_refreshed.is_active is False


def test_calendar_and_sms_history_views(app, client):
    """Verify availability calendar and SMS delivery history routes."""
    client.post('/auth/login', data={
        'username': 'yield_manager',
        'password': 'YieldPass2026!'
    }, follow_redirects=True)

    # 1. Calendar view
    res = client.get('/hospitality/calendar')
    assert res.status_code == 200
    assert b'Multi-Room Booking &amp; Availability Calendar' in res.data
    assert b'V-101' in res.data

    # 2. SMS History view
    res = client.get('/communication/sms-history')
    assert res.status_code == 200
    assert b'SMS Delivery History &amp; Logs' in res.data
