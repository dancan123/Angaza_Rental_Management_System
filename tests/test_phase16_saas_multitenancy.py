"""
Phase 16 – SaaS Multi-Tenancy & Modular Subscriptions Tests
Tests:
  1. Organization creation and subscription tiers
  2. Modular entitlements (Rental vs Hospitality access)
  3. Quota and unit limits enforcement
  4. Associating properties and users to tenant organizations
"""
import pytest
from app import create_app
from app.extensions import db
from app.models.organization import Organization
from app.models.property import Property
from app.models.user import User, Role, Landlord

@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()

def test_organization_creation_and_tiers(app):
    with app.app_context():
        org = Organization(
            name="Apex Horizon Properties Ltd",
            slug="apex-horizon",
            contact_email="director@apex.co.ke",
            contact_phone="+254700123456",
            subscription_tier="COMBINED_SUITE",
            max_properties=20,
            max_units=100
        )
        db.session.add(org)
        db.session.commit()

        assert org.id is not None
        assert org.can_access_rental_module() is True
        assert org.can_access_hospitality_module() is True
        assert org.is_within_unit_limit(50) is True
        assert org.is_within_unit_limit(105) is False

def test_modular_subscription_entitlements(app):
    with app.app_context():
        # Rental Only organization
        rental_org = Organization(
            name="Nairobi Rentals Agency",
            slug="nairobi-rentals",
            subscription_tier="RENTAL_STANDARD"
        )
        # Hospitality Only organization
        hosp_org = Organization(
            name="Coastal Vacation Villas",
            slug="coastal-villas",
            subscription_tier="HOSPITALITY_STANDARD"
        )
        db.session.add_all([rental_org, hosp_org])
        db.session.commit()

        assert rental_org.can_access_rental_module() is True
        assert rental_org.can_access_hospitality_module() is False

        assert hosp_org.can_access_rental_module() is False
        assert hosp_org.can_access_hospitality_module() is True

def test_property_and_user_org_association(app):
    with app.app_context():
        org = Organization(name="Westlands Estates Ltd", slug="westlands-estates")
        role = Role(name="MANAGER", display_name="Manager")
        db.session.add_all([org, role])
        db.session.commit()

        ll = Landlord(name="Kariuki Holdings", phone="+254711222333")
        db.session.add(ll)
        db.session.commit()

        prop = Property(
            organization_id=org.id,
            landlord_id=ll.id,
            name="Westlands Heights",
            ref_number="WH-001",
            property_type="COMMERCIAL",
            location="Westlands, Nairobi"
        )
        db.session.add(prop)
        db.session.commit()

        assert prop.organization_id == org.id
        assert org.properties.count() == 1
        assert org.properties.first().name == "Westlands Heights"
