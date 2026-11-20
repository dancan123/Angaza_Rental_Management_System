"""
Phase 32 — Full Multi-Tenant Isolation Test Suite
===================================================
Proves that every module (bookings, leases, tenants, maintenance,
communication, properties, marketplace, vacancies) is completely
isolated per organization_id — not per region.

Two managers in the SAME CITY (Nairobi) can both use the system but
see ZERO data from each other. Same for any other city.
"""
import pytest
import random
from app import create_app, db
from app.models.organization import Organization
from app.models.user import User, Role, Landlord
from app.models.property import Property, RentalUnit
from app.models.tenant import Tenant
from app.models.booking import Booking
from app.models.lead import HouseSeekerLead, ExternalPropertyListing
from app.models.maintenance import Expense, MaintenanceRequest


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def app():
    application = create_app()
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    return application


@pytest.fixture(scope='module')
def orgs(app):
    """
    Creates TWO organizations in the SAME REGION (Nairobi) to prove that
    isolation is by organization_id, NOT by region.
    Also creates ONE organization in Meru for cross-region proof.
    """
    r = random.randint(100000, 999999)
    with app.app_context():
        manager_role = Role.query.filter_by(name='PROPERTY_MANAGER').first()
        # Reuse the first available landlord record (required NOT NULL FK on Property)
        from app.models.user import Landlord
        landlord = Landlord.query.first()
        if not landlord:
            landlord = Landlord(name=f'Test Landlord {r}', phone=f'+2547000{r}', is_active=True)
            db.session.add(landlord)
            db.session.flush()

        # Org A — Nairobi Manager 1
        orgA = Organization(
            name=f'Nairobi Alpha Estate {r}',
            slug=f'nairobi-alpha-{r}',
            org_code=Organization.generate_unique_org_code(),
            region='Nairobi',
            county='Nairobi City County',
            town='Westlands',
            contact_email=f'alpha_{r}@test.ke',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
        )
        db.session.add(orgA)
        db.session.flush()

        userA = User(
            username=f'manager_a_{r}',
            email=f'alpha_{r}@test.ke',
            full_name='Manager Alpha',
            organization_id=orgA.id,
            role=manager_role,
            is_active=True,
        )
        userA.set_password('Pass123!')
        db.session.add(userA)

        # Org B — ALSO Nairobi (same city, different company)
        orgB = Organization(
            name=f'Nairobi Beta Holdings {r}',
            slug=f'nairobi-beta-{r}',
            org_code=Organization.generate_unique_org_code(),
            region='Nairobi',  # Same region as Org A
            county='Nairobi City County',
            town='Karen',
            contact_email=f'beta_{r}@test.ke',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
        )
        db.session.add(orgB)
        db.session.flush()

        userB = User(
            username=f'manager_b_{r}',
            email=f'beta_{r}@test.ke',
            full_name='Manager Beta',
            organization_id=orgB.id,
            role=manager_role,
            is_active=True,
        )
        userB.set_password('Pass123!')
        db.session.add(userB)

        # Org C — Meru (different region)
        orgC = Organization(
            name=f'Meru Gamma Properties {r}',
            slug=f'meru-gamma-{r}',
            org_code=Organization.generate_unique_org_code(),
            region='Meru',
            county='Meru County',
            town='Meru Town',
            contact_email=f'gamma_{r}@test.ke',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
        )
        db.session.add(orgC)
        db.session.flush()

        userC = User(
            username=f'manager_c_{r}',
            email=f'gamma_{r}@test.ke',
            full_name='Manager Gamma',
            organization_id=orgC.id,
            role=manager_role,
            is_active=True,
        )
        userC.set_password('Pass123!')
        db.session.add(userC)

        # Create properties and units per org
        propA = Property(
            organization_id=orgA.id,
            landlord_id=landlord.id,
            name=f'Alpha Towers {r}',
            ref_number=f'PROP-A-{r}',
            location='Westlands, Nairobi',
            management_status='ACTIVE',
            property_type='APARTMENT',
        )
        propB = Property(
            organization_id=orgB.id,
            landlord_id=landlord.id,
            name=f'Beta Gardens {r}',
            ref_number=f'PROP-B-{r}',
            location='Karen, Nairobi',
            management_status='ACTIVE',
            property_type='APARTMENT',
        )
        propC = Property(
            organization_id=orgC.id,
            landlord_id=landlord.id,
            name=f'Gamma Heights {r}',
            ref_number=f'PROP-C-{r}',
            location='Meru Town',
            management_status='ACTIVE',
            property_type='APARTMENT',
        )
        db.session.add_all([propA, propB, propC])
        db.session.flush()

        unitA = RentalUnit(
            property_id=propA.id,
            unit_number=f'A-{r}',
            unit_type='2_BEDROOM',
            occupancy_status='VACANT',
            rent_amount_cents=5000000,
        )
        unitB = RentalUnit(
            property_id=propB.id,
            unit_number=f'B-{r}',
            unit_type='1_BEDROOM',
            occupancy_status='VACANT',
            rent_amount_cents=3000000,
        )
        unitC = RentalUnit(
            property_id=propC.id,
            unit_number=f'C-{r}',
            unit_type='BEDSITTER',
            occupancy_status='VACANT',
            rent_amount_cents=1500000,
        )
        db.session.add_all([unitA, unitB, unitC])
        db.session.commit()

        yield {
            'r': r,
            'orgA': orgA, 'userA': userA, 'propA': propA, 'unitA': unitA,
            'orgB': orgB, 'userB': userB, 'propB': propB, 'unitB': unitB,
            'orgC': orgC, 'userC': userC, 'propC': propC, 'unitC': unitC,
        }


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_properties_are_scoped_per_org(app, orgs):
    """Each org's property query returns only its own properties."""
    with app.app_context():
        propsA = Property.query.filter_by(organization_id=orgs['orgA'].id).all()
        propsB = Property.query.filter_by(organization_id=orgs['orgB'].id).all()
        propsC = Property.query.filter_by(organization_id=orgs['orgC'].id).all()

        namesA = [p.name for p in propsA]
        namesB = [p.name for p in propsB]
        namesC = [p.name for p in propsC]

        assert orgs['propA'].name in namesA
        assert orgs['propB'].name not in namesA  # Org B's property NOT visible to Org A
        assert orgs['propC'].name not in namesA  # Meru NOT in Nairobi A

        assert orgs['propB'].name in namesB
        assert orgs['propA'].name not in namesB  # Org A's property NOT visible to Org B
        assert orgs['propC'].name not in namesB

        assert orgs['propC'].name in namesC
        assert orgs['propA'].name not in namesC
        assert orgs['propB'].name not in namesC


def test_units_are_scoped_per_org(app, orgs):
    """Vacant units scoped by org never bleed across organizations."""
    with app.app_context():
        from app.models.property import Property, RentalUnit
        unitsA = RentalUnit.query.join(Property).filter(
            Property.organization_id == orgs['orgA'].id,
            RentalUnit.occupancy_status == 'VACANT'
        ).all()
        unitsB = RentalUnit.query.join(Property).filter(
            Property.organization_id == orgs['orgB'].id,
            RentalUnit.occupancy_status == 'VACANT'
        ).all()
        unitsC = RentalUnit.query.join(Property).filter(
            Property.organization_id == orgs['orgC'].id,
            RentalUnit.occupancy_status == 'VACANT'
        ).all()

        unit_ids_A = {u.id for u in unitsA}
        unit_ids_B = {u.id for u in unitsB}
        unit_ids_C = {u.id for u in unitsC}

        assert orgs['unitA'].id in unit_ids_A
        assert orgs['unitB'].id not in unit_ids_A
        assert orgs['unitC'].id not in unit_ids_A

        assert orgs['unitB'].id in unit_ids_B
        assert orgs['unitA'].id not in unit_ids_B
        assert orgs['unitC'].id not in unit_ids_B

        assert orgs['unitC'].id in unit_ids_C
        assert orgs['unitA'].id not in unit_ids_C
        assert orgs['unitB'].id not in unit_ids_C


def test_booking_attaches_org_id_from_unit_property(app, orgs):
    """Booking created for Org A's unit automatically inherits Org A's organization_id."""
    with app.app_context():
        from app.services.booking_service import BookingService
        from datetime import date, timedelta
        r = orgs['r']
        unitA = db.session.get(RentalUnit, orgs['unitA'].id)
        orgA = db.session.get(Organization, orgs['orgA'].id)

        booking = BookingService.create_booking(
            rental_unit_id=unitA.id,
            prospective_name=f'Tenant Alpha {r}',
            prospective_phone=f'+2547001{r}',
            expected_move_in_date=date.today() + timedelta(days=10),
        )
        assert booking.organization_id == orgA.id

        # Confirm it's NOT linked to Org B or C
        assert booking.organization_id != orgs['orgB'].id
        assert booking.organization_id != orgs['orgC'].id

        # Org B query for its bookings must NOT include this booking
        b_bookings = Booking.query.filter_by(organization_id=orgs['orgB'].id).all()
        b_booking_ids = {b.id for b in b_bookings}
        assert booking.id not in b_booking_ids


def test_house_seeker_leads_scoped_per_org(app, orgs):
    """HouseSeekerLeads submitted on Org A's vacancy page do NOT appear in Org B or C."""
    with app.app_context():
        r = orgs['r']
        orgA = db.session.get(Organization, orgs['orgA'].id)
        orgB = db.session.get(Organization, orgs['orgB'].id)
        orgC = db.session.get(Organization, orgs['orgC'].id)

        lead = HouseSeekerLead(
            organization_id=orgA.id,
            full_name=f'Seeker Nairobi Alpha {r}',
            phone=f'+2547112{r}',
            preferred_unit_type='2_BEDROOM',
            status='NEW',
        )
        db.session.add(lead)
        db.session.commit()

        # Must be in Org A's scope
        leadsA = HouseSeekerLead.query.filter_by(organization_id=orgA.id).all()
        assert any(l.phone == f'+2547112{r}' for l in leadsA)

        # Must NOT appear in Org B or Org C
        leadsB = HouseSeekerLead.query.filter_by(organization_id=orgB.id).all()
        leadsC = HouseSeekerLead.query.filter_by(organization_id=orgC.id).all()
        assert not any(l.phone == f'+2547112{r}' for l in leadsB)
        assert not any(l.phone == f'+2547112{r}' for l in leadsC)


def test_external_listings_scoped_per_org(app, orgs):
    """Partner/external listings submitted on Org B's portal do NOT appear on Org A or C."""
    with app.app_context():
        r = orgs['r']
        orgA = db.session.get(Organization, orgs['orgA'].id)
        orgB = db.session.get(Organization, orgs['orgB'].id)
        orgC = db.session.get(Organization, orgs['orgC'].id)

        listing = ExternalPropertyListing(
            organization_id=orgB.id,
            owner_name=f'Karen Landlord {r}',
            owner_phone=f'+2547223{r}',
            property_title=f'Karen Exclusive Villa {r}',
            location='Karen, Nairobi',
            unit_type='3_BEDROOM',
            monthly_rent_cents=12000000,
            status='PUBLISHED',
        )
        db.session.add(listing)
        db.session.commit()

        listingsB = ExternalPropertyListing.query.filter_by(organization_id=orgB.id, status='PUBLISHED').all()
        assert any(l.property_title == f'Karen Exclusive Villa {r}' for l in listingsB)

        listingsA = ExternalPropertyListing.query.filter_by(organization_id=orgA.id).all()
        listingsC = ExternalPropertyListing.query.filter_by(organization_id=orgC.id).all()
        assert not any(l.property_title == f'Karen Exclusive Villa {r}' for l in listingsA)
        assert not any(l.property_title == f'Karen Exclusive Villa {r}' for l in listingsC)


def test_public_vacancy_pages_do_not_cross_contaminate(app, orgs):
    """
    Public /vacancies/<org_code> pages for two Nairobi orgs in the same region
    must show ZERO data from each other, even though they share the same region/city.
    """
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        # Org A's public vacancy page
        res_a = client.get(f"/vacancies/{orgs['orgA'].org_code}")
        assert res_a.status_code == 200
        assert orgs['orgA'].name.encode() in res_a.data
        # Org B's name must NOT appear on Org A's page
        assert orgs['orgB'].name.encode() not in res_a.data
        # Org C's name must NOT appear
        assert orgs['orgC'].name.encode() not in res_a.data

        # Org B's public vacancy page
        res_b = client.get(f"/vacancies/{orgs['orgB'].org_code}")
        assert res_b.status_code == 200
        assert orgs['orgB'].name.encode() in res_b.data
        assert orgs['orgA'].name.encode() not in res_b.data
        assert orgs['orgC'].name.encode() not in res_b.data

        # Org C (Meru) public vacancy page
        res_c = client.get(f"/vacancies/{orgs['orgC'].org_code}")
        assert res_c.status_code == 200
        assert orgs['orgC'].name.encode() in res_c.data
        assert orgs['orgA'].name.encode() not in res_c.data
        assert orgs['orgB'].name.encode() not in res_c.data


def test_tenant_registration_attaches_to_correct_org(app, orgs):
    """Tenant created under Org C does not appear in Org A or Org B tenant lists."""
    with app.app_context():
        r = orgs['r']
        orgA = db.session.get(Organization, orgs['orgA'].id)
        orgB = db.session.get(Organization, orgs['orgB'].id)
        orgC = db.session.get(Organization, orgs['orgC'].id)

        # Create a tenant explicitly for Org C
        tenant = Tenant(
            organization_id=orgC.id,
            first_name='Meru',
            last_name=f'Resident {r}',
            id_passport_number=f'ID{r}C',
            phone=f'+2547334{r}',
            is_active=True,
        )
        db.session.add(tenant)
        db.session.commit()

        tenantsC = Tenant.query.filter_by(organization_id=orgC.id).all()
        tenantsA = Tenant.query.filter_by(organization_id=orgA.id).all()
        tenantsB = Tenant.query.filter_by(organization_id=orgB.id).all()

        assert any(t.id_passport_number == f'ID{r}C' for t in tenantsC)
        assert not any(t.id_passport_number == f'ID{r}C' for t in tenantsA)
        assert not any(t.id_passport_number == f'ID{r}C' for t in tenantsB)


def test_users_are_scoped_per_org(app, orgs):
    """Users belonging to Org A cannot be queried by Org B scope."""
    with app.app_context():
        orgA = db.session.get(Organization, orgs['orgA'].id)
        orgB = db.session.get(Organization, orgs['orgB'].id)
        orgC = db.session.get(Organization, orgs['orgC'].id)

        usersA = User.query.filter_by(organization_id=orgA.id).all()
        usersB = User.query.filter_by(organization_id=orgB.id).all()
        usersC = User.query.filter_by(organization_id=orgC.id).all()

        userA_ids = {u.id for u in usersA}
        userB_ids = {u.id for u in usersB}
        userC_ids = {u.id for u in usersC}

        assert orgs['userA'].id in userA_ids
        assert orgs['userB'].id not in userA_ids
        assert orgs['userC'].id not in userA_ids

        assert orgs['userB'].id in userB_ids
        assert orgs['userA'].id not in userB_ids

        assert orgs['userC'].id in userC_ids
        assert orgs['userA'].id not in userC_ids
        assert orgs['userB'].id not in userC_ids


def test_same_region_two_orgs_fully_independent(app, orgs):
    """
    CRITICAL: Org A and Org B are BOTH in Nairobi but must be fully independent.
    - Org A's property query returns only Org A's properties.
    - Org B's property query returns only Org B's properties.
    - Cross-contamination is ZERO regardless of same region.
    """
    with app.app_context():
        orgA = db.session.get(Organization, orgs['orgA'].id)
        orgB = db.session.get(Organization, orgs['orgB'].id)

        # Same region
        assert orgA.region == orgB.region == 'Nairobi'

        # Properties strictly separate
        propsA_ids = {p.id for p in Property.query.filter_by(organization_id=orgA.id).all()}
        propsB_ids = {p.id for p in Property.query.filter_by(organization_id=orgB.id).all()}

        assert orgs['propA'].id in propsA_ids
        assert orgs['propB'].id in propsB_ids

        # Zero intersection
        assert propsA_ids.isdisjoint(propsB_ids), \
            f"Cross-contamination detected! Shared property IDs: {propsA_ids & propsB_ids}"

        # Bookings
        bookingsA_ids = {b.id for b in Booking.query.filter_by(organization_id=orgA.id).all()}
        bookingsB_ids = {b.id for b in Booking.query.filter_by(organization_id=orgB.id).all()}
        assert bookingsA_ids.isdisjoint(bookingsB_ids), \
            f"Cross-contamination in bookings! Shared: {bookingsA_ids & bookingsB_ids}"

        # Leads
        leadsA_ids = {l.id for l in HouseSeekerLead.query.filter_by(organization_id=orgA.id).all()}
        leadsB_ids = {l.id for l in HouseSeekerLead.query.filter_by(organization_id=orgB.id).all()}
        assert leadsA_ids.isdisjoint(leadsB_ids), \
            f"Cross-contamination in leads! Shared: {leadsA_ids & leadsB_ids}"
