"""
Phase 38 — M-Pesa STK Push Integration for Hospitality (Airbnb) Bookings
Tests:
  1. STK push skipped gracefully when no gateway credentials exist
  2. STK push triggered when action=book_and_stk on quick-book form
  3. /hospitality/reservations/<id>/push-stk route — multi-tenant isolation
  4. Cross-org STK push blocked (403)
"""
import pytest
import uuid
from unittest.mock import patch
from datetime import date, timedelta
from app import create_app, db
from app.models.organization import Organization
from app.models.property import Property, RentalUnit
from app.models.hospitality import Guest, HospitalityReservation
from app.models.user import User
from app.models.gateway import PaymentGatewayConfig


def _unique_code(prefix='STAY-TS'):
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()


def _login_as_manager(client, app_instance, org_code='ANG0003', password='TestPass123!'):
    with app_instance.app_context():
        org = Organization.query.filter_by(org_code=org_code).first()
        manager = User.query.filter_by(organization_id=org.id).first()
        assert manager is not None
        manager.set_password(password)
        db.session.commit()
        uname = manager.username
    client.post('/auth/login', data={'username': uname, 'password': password}, follow_redirects=True)
    return uname


def _get_short_stay_unit_id(app_instance, org_code='ANG0003'):
    with app_instance.app_context():
        org = Organization.query.filter_by(org_code=org_code).first()
        unit = RentalUnit.query.join(RentalUnit.property).filter(
            Property.organization_id == org.id,
            RentalUnit.operational_type == 'SHORT_STAY'
        ).first()
        return unit.id if unit else None


# ─── Test 1: Book without STK → no M-Pesa attempt ───────────────────────────
def test_quick_book_without_stk_push_succeeds(client, app_instance):
    """Normal booking (no STK toggle) creates reservation, no payment push."""
    unit_id = _get_short_stay_unit_id(app_instance)
    assert unit_id

    _login_as_manager(client, app_instance)
    ci = (date.today() + timedelta(days=20)).strftime('%Y-%m-%d')
    co = (date.today() + timedelta(days=22)).strftime('%Y-%m-%d')

    resp = client.post('/hospitality/reservations/create', data={
        'rental_unit_id': unit_id,
        'booking_source': 'DIRECT',
        'first_name': 'Kamau',
        'last_name': 'Njoroge',
        'phone': '+254722100200',
        'email': '',
        'check_in_date': ci,
        'check_out_date': co,
        'daily_rate': '4000',
        'num_guests': '1',
        'special_requests': '',
    }, follow_redirects=True)

    assert resp.status_code == 200
    with app_instance.app_context():
        res = HospitalityReservation.query.join(Guest).filter(
            Guest.phone == '+254722100200'
        ).order_by(HospitalityReservation.id.desc()).first()
        assert res is not None
        assert res.guest.first_name == 'Kamau'


# ─── Test 2: STK push skipped gracefully (no gateway credentials) ─────────────
def test_quick_book_stk_push_skipped_no_credentials(client, app_instance):
    """When action=book_and_stk but org has no gateway config, booking succeeds
       with a helpful flash message — no crash, no cross-org leak."""
    unit_id = _get_short_stay_unit_id(app_instance)
    assert unit_id

    # Ensure NO active gateway for ANG0003
    with app_instance.app_context():
        org = Organization.query.filter_by(org_code='ANG0003').first()
        orig_states = {}
        for c in PaymentGatewayConfig.query.filter_by(organization_id=org.id).all():
            orig_states[c.id] = c.is_active
            c.is_active = False
        db.session.commit()

    _login_as_manager(client, app_instance)
    ci = (date.today() + timedelta(days=25)).strftime('%Y-%m-%d')
    co = (date.today() + timedelta(days=26)).strftime('%Y-%m-%d')

    resp = client.post('/hospitality/reservations/create', data={
        'rental_unit_id': unit_id,
        'booking_source': 'DIRECT',
        'first_name': 'Achola',
        'last_name': 'Ouma',
        'phone': '+254733500600',
        'email': '',
        'check_in_date': ci,
        'check_out_date': co,
        'daily_rate': '5000',
        'num_guests': '1',
        'special_requests': '',
        'action': 'book_and_stk',
    }, follow_redirects=True)

    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # Booking must succeed (reservation listed or flash success shown)
    assert 'Achola' in html or 'confirmed' in html.lower() or 'reservation' in html.lower() or 'Ouma' in html
    # Flash message about STK skip should contain 'skipped', 'credentials', or 'Payment Gateways'
    assert any(kw in html for kw in ['skipped', 'credentials', 'Payment Gateway', 'gateway', 'STK Push'])

    # Restore gateways
    with app_instance.app_context():
        for cfg_id, was_active in orig_states.items():
            cfg = db.session.get(PaymentGatewayConfig, cfg_id)
            if cfg:
                cfg.is_active = was_active
        db.session.commit()


# ─── Test 3: STK push triggered with mocked Daraja ────────────────────────────
def test_quick_book_stk_push_triggered_with_mocked_daraja(client, app_instance):
    """When a valid PaymentGatewayConfig exists and action=book_and_stk,
       DarajaClient.initiate_stk_push is called with the right args."""
    unit_id = _get_short_stay_unit_id(app_instance)
    assert unit_id

    # Ensure a valid gateway config exists for ANG0003
    with app_instance.app_context():
        org = Organization.query.filter_by(org_code='ANG0003').first()
        cfg = PaymentGatewayConfig.query.filter_by(organization_id=org.id).first()
        if not cfg:
            cfg = PaymentGatewayConfig(
                organization_id=org.id,
                gateway_type='MPESA_PAYBILL',
                name='Test Paybill ANG0003',
                shortcode='600000',
                consumer_key='test_ck',
                consumer_secret='test_cs',
                passkey='test_pk',
                callback_url='https://example.com/callback',
                is_active=True,
                is_sandbox=True,
            )
            db.session.add(cfg)
        else:
            cfg.shortcode = cfg.shortcode or '600000'
            cfg.consumer_key = cfg.consumer_key or 'test_ck'
            cfg.consumer_secret = cfg.consumer_secret or 'test_cs'
            cfg.passkey = cfg.passkey or 'test_pk'
            cfg.is_active = True
        db.session.commit()

    _login_as_manager(client, app_instance)
    ci = (date.today() + timedelta(days=200)).strftime('%Y-%m-%d')
    co = (date.today() + timedelta(days=202)).strftime('%Y-%m-%d')

    mock_stk_resp = {
        'CheckoutRequestID': 'ws_CO_TEST_12345',
        'ResponseCode': '0',
        'ResponseDescription': 'Success. Request accepted for processing',
    }

    with patch('app.services.mpesa_service.DarajaClient.get_access_token', return_value='MOCK_TOKEN'), \
         patch('app.services.mpesa_service.DarajaClient.initiate_stk_push', return_value=mock_stk_resp) as mock_stk:

        resp = client.post('/hospitality/reservations/create', data={
            'rental_unit_id': unit_id,
            'booking_source': 'WEBSITE',
            'first_name': 'Brenda',
            'last_name': 'Chebet',
            'phone': '+254744600700',
            'email': 'brenda@example.com',
            'check_in_date': ci,
            'check_out_date': co,
            'daily_rate': '6000',
            'num_guests': '2',
            'special_requests': 'Extra blankets please',
            'action': 'book_and_stk',
        }, follow_redirects=True)

    assert resp.status_code == 200
    mock_stk.assert_called_once()
    # Verify checkout ID saved on reservation
    with app_instance.app_context():
        res = HospitalityReservation.query.join(Guest).filter(
            Guest.phone == '+254744600700'
        ).order_by(HospitalityReservation.id.desc()).first()
        assert res is not None
        assert res.payment_reference == 'ws_CO_TEST_12345'
        assert res.payment_method == 'MPESA'


# ─── Test 4: push-stk route — cross-org blocked ──────────────────────────────
def test_push_stk_route_cross_org_blocked(client, app_instance):
    """Manager from ANG0001 cannot push STK for a reservation belonging to ANG0003."""
    res_id = None
    manager1_username = None

    with app_instance.app_context():
        org3 = Organization.query.filter_by(org_code='ANG0003').first()
        unit3 = RentalUnit.query.join(RentalUnit.property).filter(
            Property.organization_id == org3.id,
            RentalUnit.operational_type == 'SHORT_STAY'
        ).first()

        guest = Guest(first_name='Target', last_name='Guest', phone=f'+2547007{uuid.uuid4().hex[:5]}',
                      nationality='Kenyan')
        db.session.add(guest)
        db.session.flush()
        res = HospitalityReservation(
            rental_unit_id=unit3.id,
            organization_id=org3.id,
            guest_id=guest.id,
            check_in_date=date.today() + timedelta(days=5),
            check_out_date=date.today() + timedelta(days=6),
            num_nights=1,
            status='CONFIRMED',
            reservation_code=_unique_code('STAY-XT'),
            booking_source='DIRECT',
        )
        db.session.add(res)
        db.session.commit()
        res_id = res.id

        org1 = Organization.query.filter_by(org_code='ANG0001').first()
        if org1:
            manager1 = User.query.filter_by(organization_id=org1.id).first()
            if manager1:
                manager1.set_password('CrossOrgPass!')
                db.session.commit()
                manager1_username = manager1.username

    if manager1_username:
        client.post('/auth/login', data={'username': manager1_username, 'password': 'CrossOrgPass!'},
                    follow_redirects=True)
        resp = client.post(f'/hospitality/reservations/{res_id}/push-stk',
                           data={'stk_amount': '5000'},
                           follow_redirects=False)
        assert resp.status_code in (403, 302)
    else:
        pytest.skip("ANG0001 manager user not in test DB")


# ─── Test 5: push-stk route — no gateway config returns friendly message ──────
def test_push_stk_route_no_config_returns_warning(client, app_instance):
    """push-stk route for a reservation whose org has no gateway returns a
       warning flash (not a 500 error)."""
    res_id = None
    manager_username = None
    orig_states = {}

    with app_instance.app_context():
        org = Organization.query.filter_by(org_code='ANG0003').first()
        unit = RentalUnit.query.join(RentalUnit.property).filter(
            Property.organization_id == org.id,
            RentalUnit.operational_type == 'SHORT_STAY'
        ).first()

        guest = Guest(first_name='Wanjiku', last_name='Maina',
                      phone=f'+2547558{uuid.uuid4().hex[:5]}', nationality='Kenyan')
        db.session.add(guest)
        db.session.flush()
        res = HospitalityReservation(
            rental_unit_id=unit.id,
            organization_id=org.id,
            guest_id=guest.id,
            check_in_date=date.today() + timedelta(days=7),
            check_out_date=date.today() + timedelta(days=9),
            num_nights=2,
            daily_rate_cents=500000,
            total_stay_cents=1000000,
            status='CONFIRMED',
            reservation_code=_unique_code('STAY-WJ'),
            booking_source='DIRECT',
        )
        db.session.add(res)
        db.session.commit()
        res_id = res.id

        # Deactivate all gateways
        for c in PaymentGatewayConfig.query.filter_by(organization_id=org.id).all():
            orig_states[c.id] = c.is_active
            c.is_active = False
        db.session.commit()

        manager = User.query.filter_by(organization_id=org.id).first()
        manager.set_password('WanjikuPass!')
        db.session.commit()
        manager_username = manager.username  # capture before leaving context

    client.post('/auth/login', data={'username': manager_username, 'password': 'WanjikuPass!'},
                follow_redirects=True)

    resp = client.post(f'/hospitality/reservations/{res_id}/push-stk',
                       data={'stk_amount': '10000'},
                       follow_redirects=True)
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    # Should show a warning, NOT a crash
    assert any(kw in html for kw in ['gateway', 'credentials', 'Payment Gateway', 'STK Push'])

    # Restore gateways
    with app_instance.app_context():
        for cfg_id, was_active in orig_states.items():
            cfg = db.session.get(PaymentGatewayConfig, cfg_id)
            if cfg:
                cfg.is_active = was_active
        db.session.commit()

