#!/usr/bin/env python
"""
seed_landlords_demo.py — Provision Landlord User Logins & Multi-Tenant Scoped Demo Data.
Sets up dedicated login user accounts for Landlords (Dr. Joseph Kamau, Mama Sarah Ochieng,
and Angaza Capital Holdings) with distinct apartments, rentals, and Airbnb cottages.

Usage:
    python seed_landlords_demo.py
"""

import os
from datetime import datetime, date, timedelta

os.environ['FLASK_CONFIG'] = 'development'

from app import create_app
from app.extensions import db
from app.models.organization import Organization
from app.models.user import Landlord, User, Role
from app.models.property import Property, RentalUnit
from app.models.hospitality import Guest, HospitalityReservation, HousekeepingTask
from app.models.pricing import RoomPricingRule
from app.utils.currency import to_cents


def seed_landlords_and_data():
    app = create_app('development')
    with app.app_context():
        print("=" * 70)
        print("  ANGAZA MULTI-LANDLORD ONBOARDING & DEMO DATA SEEDER")
        print("=" * 70)

        org = Organization.query.first()
        if not org:
            org = Organization(
                name="Angaza Premier Properties",
                slug="angaza-premier",
                subscription_tier="COMBINED_SUITE",
                subscription_status="ACTIVE",
                enable_rentals=True,
                enable_hospitality=True,
                sms_credits=500
            )
            db.session.add(org)
            db.session.flush()

        ll_role = Role.query.filter_by(name='LANDLORD').first()
        today = date.today()

        # ── 1. Landlord 1: Dr. Joseph M. Kamau ─────────────────────────────
        print("\n[1/3] Setting up Landlord 1: Dr. Joseph M. Kamau...")
        l1 = Landlord.query.filter_by(id=1).first()
        if not l1:
            l1 = Landlord(
                name="Dr. Joseph M. Kamau",
                contact_person="Dr. Joseph Kamau",
                phone="+254722100200",
                email="kamau@africarealty.co.ke",
                is_active=True
            )
            db.session.add(l1)
            db.session.flush()

        u1 = User.query.filter_by(username='kamau').first()
        if not u1:
            u1 = User(
                username='kamau',
                email='kamau@africarealty.co.ke',
                phone='+254722100200',
                full_name='Dr. Joseph M. Kamau',
                role=ll_role,
                organization_id=org.id,
                is_active=True
            )
            u1.set_password('Kamau2026!')
            db.session.add(u1)
            db.session.flush()
        else:
            u1.set_password('Kamau2026!')

        if l1 not in u1.landlords:
            u1.landlords.append(l1)
        print("  -> User 'kamau' (Password: Kamau2026!) active and linked to Landlord 1.")

        # ── 2. Landlord 2: Mama Sarah W. Ochieng ───────────────────────────
        print("\n[2/3] Setting up Landlord 2: Mama Sarah W. Ochieng...")
        l2 = Landlord.query.filter_by(email='sarah.ochieng@gmail.com').first()
        if not l2:
            l2 = Landlord(
                name="Mama Sarah W. Ochieng",
                contact_person="Sarah Ochieng",
                phone="+254733400500",
                email="sarah.ochieng@gmail.com",
                is_active=True
            )
            db.session.add(l2)
            db.session.flush()

        u2 = User.query.filter_by(username='sarah').first()
        if not u2:
            u2 = User(
                username='sarah',
                email='sarah.ochieng@gmail.com',
                phone='+254733400500',
                full_name='Mama Sarah W. Ochieng',
                role=ll_role,
                organization_id=org.id,
                is_active=True
            )
            u2.set_password('Sarah2026!')
            db.session.add(u2)
            db.session.flush()
        else:
            u2.set_password('Sarah2026!')

        if l2 not in u2.landlords:
            u2.landlords.append(l2)
        print("  -> User 'sarah' (Password: Sarah2026!) active and linked to Landlord 2.")

        # Add an Airbnb holiday property for Mama Sarah in Naivasha!
        sarah_airbnb = Property.query.filter_by(ref_number='AIRBNB-NVS-004').first()
        if not sarah_airbnb:
            sarah_airbnb = Property(
                name="Naivasha Crescent Lake Breeze Cottage",
                ref_number="AIRBNB-NVS-004",
                property_type="COMMERCIAL",
                location="Moi South Lake Road, Naivasha",
                description="Peaceful lakeside holiday cottage with scenic views of Lake Naivasha and roaming wildlife.",
                landlord_id=l2.id,
                organization_id=org.id,
                management_status="ACTIVE"
            )
            db.session.add(sarah_airbnb)
            db.session.flush()
            print("  -> Added Airbnb Property: 'Naivasha Crescent Lake Breeze Cottage'")

        # Units for Sarah's Airbnb
        nvs_u1 = RentalUnit.query.filter_by(property_id=sarah_airbnb.id, unit_number="Cottage A — Flamingo Haven").first()
        if not nvs_u1:
            nvs_u1 = RentalUnit(
                property_id=sarah_airbnb.id,
                unit_number="Cottage A — Flamingo Haven",
                unit_type="Cottage",
                operational_type="SHORT_STAY",
                daily_rate_cents=to_cents(6000),
                rent_amount_cents=to_cents(180000),
                max_guests=4,
                occupancy_status="OCCUPIED",
                cleaning_status="CLEAN"
            )
            db.session.add(nvs_u1)
            db.session.flush()

        nvs_u2 = RentalUnit.query.filter_by(property_id=sarah_airbnb.id, unit_number="Cottage B — Acacia Sunrise Suite").first()
        if not nvs_u2:
            nvs_u2 = RentalUnit(
                property_id=sarah_airbnb.id,
                unit_number="Cottage B — Acacia Sunrise Suite",
                unit_type="Suite",
                operational_type="SHORT_STAY",
                daily_rate_cents=to_cents(5500),
                rent_amount_cents=to_cents(165000),
                max_guests=2,
                occupancy_status="VACANT",
                cleaning_status="CLEAN"
            )
            db.session.add(nvs_u2)
            db.session.flush()

        # Add guest & active reservation for Sarah's Airbnb
        sarah_guest = Guest.query.filter_by(phone="+254711223344").first()
        if not sarah_guest:
            sarah_guest = Guest(
                first_name="Fatuma",
                last_name="Hassan",
                phone="+254711223344",
                email="fatuma.hassan@coastpost.co.ke",
                id_passport_number="ID-FATUMA-2026",
                nationality="Kenyan"
            )
            db.session.add(sarah_guest)
            db.session.flush()

        sarah_res = HospitalityReservation.query.filter_by(reservation_code="RES-NVS-401").first()
        if not sarah_res:
            sarah_res = HospitalityReservation(
                reservation_code="RES-NVS-401",
                guest_id=sarah_guest.id,
                rental_unit_id=nvs_u1.id,
                check_in_date=today - timedelta(days=2),
                check_out_date=today + timedelta(days=2),
                num_guests=2,
                num_nights=4,
                daily_rate_cents=to_cents(6000),
                total_stay_cents=to_cents(24000),
                paid_amount_cents=to_cents(24000),
                status="CHECKED_IN",
                booking_source="AIRBNB",
                payment_method="MPESA",
                payment_reference="QZ99FATUMA"
            )
            db.session.add(sarah_res)
            db.session.flush()
            print("  -> Seeded active in-house reservation for Fatuma Hassan at Cottage A.")

        # ── 3. Landlord 3: Angaza Capital Holdings Ltd ────────────────────
        print("\n[3/3] Setting up Landlord 3: Angaza Capital Holdings Ltd...")
        l3 = Landlord.query.filter_by(email='investments@angazacapital.co.ke').first()
        if not l3:
            l3 = Landlord(
                name="Angaza Capital Holdings Ltd",
                contact_person="Brian Mwangi (Investment Director)",
                phone="+254711888999",
                email="investments@angazacapital.co.ke",
                is_active=True
            )
            db.session.add(l3)
            db.session.flush()

        u3 = User.query.filter_by(username='angazacapital').first()
        if not u3:
            u3 = User(
                username='angazacapital',
                email='investments@angazacapital.co.ke',
                phone='+254711888999',
                full_name='Brian Mwangi (Angaza Capital)',
                role=ll_role,
                organization_id=org.id,
                is_active=True
            )
            u3.set_password('Capital2026!')
            db.session.add(u3)
            db.session.flush()
        else:
            u3.set_password('Capital2026!')

        if l3 not in u3.landlords:
            u3.landlords.append(l3)
        print("  -> User 'angazacapital' (Password: Capital2026!) active and linked to Landlord 3.")

        db.session.commit()
        print("\n" + "=" * 70)
        print("  ALL LANDLORD LOGINS & SCOPED DEMO DATA POPULATED SUCCESSFULLY!")
        print("=" * 70)
        print("  Available Landlord Logins for Testing:")
        print("  1. Dr. Joseph M. Kamau:")
        print("     Username: kamau         | Password: Kamau2026!")
        print("     Properties: Kilimani Heights, Karen Villas, Watamu Villas, Kilimani Skyview, Diani Cottages")
        print("  2. Mama Sarah W. Ochieng:")
        print("     Username: sarah         | Password: Sarah2026!")
        print("     Properties: Rongai Sunrise Residences (Rentals) + Naivasha Lake Breeze Cottage (Airbnb)")
        print("  3. Angaza Capital Holdings Ltd:")
        print("     Username: angazacapital | Password: Capital2026!")
        print("     Properties: Westlands Commercial Plaza (Commercial Retail & Offices)")
        print("=" * 70)


if __name__ == '__main__':
    seed_landlords_and_data()
