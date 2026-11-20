import pytest
from datetime import date, timedelta
from app import create_app, db
from app.models.organization import Organization
from app.models.property import Property, RentalUnit
from app.models.lead import ExternalPropertyListing
from app.models.hospitality import Guest, HospitalityReservation
from app.models.user import User

@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app

@pytest.fixture
def client(app_instance):
    return app_instance.test_client()

def test_vacancies_org_portal_renders_sections(client, app_instance):
    with app_instance.app_context():
        org = Organization.query.filter_by(org_code='ANG0003').first()
        assert org is not None

        # Check default rental section
        resp = client.get('/vacancies/ANG0003')
        assert resp.status_code == 200
        html = resp.data.decode('utf-8')
        assert 'Mama Sarah Estates' in html
        assert 'Long-Term Rentals' in html
        assert 'Short-Stay / Airbnb' in html
        assert 'Neighbouring &amp; Partner' in html or 'Neighbouring & Partner' in html

        # Check airbnb section
        resp_ab = client.get('/vacancies/ANG0003?section=airbnb')
        assert resp_ab.status_code == 200
        html_ab = resp_ab.data.decode('utf-8')
        assert 'Book This Room' in html_ab or 'Book Now' in html_ab or 'Cottage' in html_ab

        # Check partner section
        resp_pt = client.get('/vacancies/ANG0003?section=partner')
        assert resp_pt.status_code == 200

def test_youtube_embed_url_conversion(app_instance):
    with app_instance.app_context():
        unit = RentalUnit(
            property_id=1,
            unit_number='TEST-YT-1',
            unit_type='1_BEDROOM',
            rent_amount_cents=1500000,
            youtube_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ'
        )
        assert unit.youtube_embed_url == 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'

        ext = ExternalPropertyListing(
            property_title='Partner Villa',
            location='Karen, Nairobi',
            owner_name='John Doe',
            owner_phone='+254700000000',
            monthly_rent_cents=8000000,
            youtube_url='https://youtu.be/dQw4w9WgXcQ'
        )
        assert ext.youtube_embed_url == 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'

def test_airbnb_online_booking_creation(client, app_instance):
    with app_instance.app_context():
        org = Organization.query.filter_by(org_code='ANG0003').first()
        unit = RentalUnit.query.join(RentalUnit.property).filter(
            Property.organization_id == org.id,
            RentalUnit.operational_type == 'SHORT_STAY'
        ).first()
        assert unit is not None

        booking_data = {
            'unit_id': unit.id,
            'guest_name': 'Grace Muthoni',
            'phone': '+254799887766',
            'email': 'grace.muthoni@example.com',
            'check_in_date': (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
            'check_out_date': (date.today() + timedelta(days=8)).strftime('%Y-%m-%d'),
            'num_guests': 2,
            'special_requests': 'Airport pickup needed',
            'org_code': 'ANG0003'
        }

        resp = client.post('/vacancies/airbnb-book', data=booking_data, follow_redirects=True)
        assert resp.status_code == 200

        # Verify reservation was created
        res = HospitalityReservation.query.filter_by(rental_unit_id=unit.id).order_by(HospitalityReservation.id.desc()).first()
        assert res is not None
        assert res.guest.phone == '+254799887766'
        assert res.num_nights == 3
        assert res.status == 'PENDING'
        assert res.booking_source == 'WEBSITE'

def test_airbnb_booking_cross_tenant_isolation(client, app_instance):
    with app_instance.app_context():
        # Try to book unit from ANG0003 claiming it belongs to ANG0002
        org3 = Organization.query.filter_by(org_code='ANG0003').first()
        unit3 = RentalUnit.query.join(RentalUnit.property).filter(
            Property.organization_id == org3.id,
            RentalUnit.operational_type == 'SHORT_STAY'
        ).first()

        booking_data = {
            'unit_id': unit3.id,
            'guest_name': 'Attacker Test',
            'phone': '+254711223344',
            'check_in_date': (date.today() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'check_out_date': (date.today() + timedelta(days=2)).strftime('%Y-%m-%d'),
            'org_code': 'ANG0002'  # Mismatched org code
        }

        resp = client.post('/vacancies/airbnb-book', data=booking_data, follow_redirects=True)
        html = resp.data.decode('utf-8')
        assert 'This room does not belong to the selected organization' in html

def test_api_vacant_units_multitenancy(client, app_instance):
    with app_instance.app_context():
        resp = client.get('/api/v1/vacant-units?org_code=ANG0003')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert data['count'] > 0

        # All returned units must belong to ANG0003
        org3 = Organization.query.filter_by(org_code='ANG0003').first()
        for u in data['vacant_units']:
            unit_db = db.session.get(RentalUnit, u['id'])
            assert unit_db.property.organization_id == org3.id
