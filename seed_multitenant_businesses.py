#!/usr/bin/env python
"""
seed_multitenant_businesses.py — Multi-Tenant SaaS Organizations & Admin Credentials.
Configures 3 distinct business organizations with unique Business Codes:
  1. ANGAZA  -> Angaza Premier Properties & Hospitality
  2. SARAH   -> Mama Sarah Estates & Lakeside Cottages
  3. CAPITAL -> Angaza Capital Commercial Holdings

Sets passwords for all business admins and landlord accounts to 'admin123'.

Usage:
    python seed_multitenant_businesses.py
"""

import os
from datetime import datetime, date, timedelta

os.environ['FLASK_CONFIG'] = 'development'

from app import create_app
from app.extensions import db
from app.models.organization import Organization
from app.models.user import User, Role, Landlord
from app.models.property import Property, RentalUnit


def setup_multitenant_businesses():
    app = create_app('development')
    with app.app_context():
        print("=" * 70)
        print("  ANGAZA MULTI-TENANT SAAS BUSINESS ORGANIZATIONS & CODES SETUP")
        print("=" * 70)

        manager_role = Role.query.filter_by(name='PROPERTY_MANAGER').first()
        landlord_role = Role.query.filter_by(name='LANDLORD').first()

        # ── 1. Business 1: ANGAZA ──────────────────────────────────────────
        print("\n[1/3] Configuring Business 1: Code 'ANGAZA'...")
        org1 = Organization.query.filter((Organization.slug == 'angaza-premier') | (Organization.org_code == 'ANGAZA')).first()
        if not org1:
            org1 = Organization(
                name="Angaza Premier Properties & Hospitality",
                slug="angaza-premier",
                org_code="ANGAZA",
                subscription_tier="COMBINED_SUITE",
                subscription_status="ACTIVE",
                enable_rentals=True,
                enable_hospitality=True,
                sms_credits=500
            )
            db.session.add(org1)
            db.session.flush()
        else:
            org1.org_code = "ANGAZA"
            org1.enable_rentals = True
            org1.enable_hospitality = True
            org1.subscription_tier = "COMBINED_SUITE"
            db.session.flush()

        # Business 1 Admin
        admin1 = User.query.filter_by(username='angaza_admin').first()
        if not admin1:
            admin1 = User(
                username='angaza_admin',
                email='admin@angazapremier.co.ke',
                full_name='Angaza Properties Manager',
                role=manager_role,
                organization_id=org1.id,
                is_active=True
            )
            db.session.add(admin1)
        admin1.set_password('admin123')
        admin1.organization_id = org1.id

        # Also update kamau password to admin123
        kamau_user = User.query.filter_by(username='kamau').first()
        if kamau_user:
            kamau_user.set_password('admin123')
            kamau_user.organization_id = org1.id

        # Associate Dr. Kamau's properties to org1
        for pref in ['AIRBNB-WTM-001', 'AIRBNB-KLM-002', 'AIRBNB-DNA-003', 'PROP-KIL-001', 'PROP-KAR-002']:
            p = Property.query.filter((Property.ref_number == pref) | (Property.name.ilike(f"%{pref}%"))).first()
            if p:
                p.organization_id = org1.id
        # Also assign Kilimani Heights and Karen Green Villas to org1
        for pname in ['Kilimani Heights Apartments', 'Karen Green Villas', 'Watamu Palm Oceanfront Villas', 'Kilimani Skyview Serviced Suites', 'Diani Beach Garden Cottages']:
            p = Property.query.filter_by(name=pname).first()
            if p:
                p.organization_id = org1.id

        print(f"  -> Organization: '{org1.name}' (Code: ANGAZA)")
        print(f"  -> Admin user: 'angaza_admin' / 'admin' (Password: admin123)")

        # ── 2. Business 2: SARAH ───────────────────────────────────────────
        print("\n[2/3] Configuring Business 2: Code 'SARAH'...")
        org2 = Organization.query.filter((Organization.slug == 'sarah-estates') | (Organization.org_code == 'SARAH')).first()
        if not org2:
            org2 = Organization(
                name="Mama Sarah Estates & Lakeside Cottages",
                slug="sarah-estates",
                org_code="SARAH",
                contact_email="sarah.ochieng@gmail.com",
                contact_phone="+254733400500",
                subscription_tier="COMBINED_SUITE",
                subscription_status="ACTIVE",
                enable_rentals=True,
                enable_hospitality=True,
                max_properties=25,
                max_units=100,
                sms_credits=150
            )
            db.session.add(org2)
            db.session.flush()
        else:
            org2.org_code = "SARAH"
            org2.enable_rentals = True
            org2.enable_hospitality = True
            org2.subscription_tier = "COMBINED_SUITE"
            db.session.flush()

        # Business 2 Admin
        admin2 = User.query.filter_by(username='sarah_admin').first()
        if not admin2:
            admin2 = User(
                username='sarah_admin',
                email='admin@sarahproperties.co.ke',
                full_name='Sarah Estates Admin',
                role=manager_role,
                organization_id=org2.id,
                is_active=True
            )
            db.session.add(admin2)
        admin2.set_password('admin123')
        admin2.organization_id = org2.id

        # Also update sarah user password to admin123
        sarah_user = User.query.filter_by(username='sarah').first()
        if sarah_user:
            sarah_user.set_password('admin123')
            sarah_user.organization_id = org2.id

        # Associate Sarah's properties to org2
        for pname in ['Rongai Sunrise Residences', 'Naivasha Crescent Lake Breeze Cottage']:
            p = Property.query.filter_by(name=pname).first()
            if p:
                p.organization_id = org2.id

        print(f"  -> Organization: '{org2.name}' (Code: SARAH)")
        print(f"  -> Admin user: 'sarah_admin' / 'admin' (Password: admin123)")

        # ── 3. Business 3: CAPITAL ─────────────────────────────────────────
        print("\n[3/3] Configuring Business 3: Code 'CAPITAL'...")
        org3 = Organization.query.filter((Organization.slug == 'angaza-capital') | (Organization.org_code == 'CAPITAL')).first()
        if not org3:
            org3 = Organization(
                name="Angaza Capital Commercial Holdings",
                slug="angaza-capital",
                org_code="CAPITAL",
                contact_email="investments@angazacapital.co.ke",
                contact_phone="+254711888999",
                subscription_tier="RENTAL_STANDARD",
                subscription_status="ACTIVE",
                enable_rentals=True,
                enable_hospitality=False,
                max_properties=30,
                max_units=150,
                sms_credits=200
            )
            db.session.add(org3)
            db.session.flush()
        else:
            org3.org_code = "CAPITAL"
            db.session.flush()

        # Business 3 Admin
        admin3 = User.query.filter_by(username='capital_admin').first()
        if not admin3:
            admin3 = User(
                username='capital_admin',
                email='admin@angazacapital.co.ke',
                full_name='Angaza Capital Director',
                role=manager_role,
                organization_id=org3.id,
                is_active=True
            )
            db.session.add(admin3)
        admin3.set_password('admin123')
        admin3.organization_id = org3.id

        # Also update angazacapital user password to admin123
        cap_user = User.query.filter_by(username='angazacapital').first()
        if cap_user:
            cap_user.set_password('admin123')
            cap_user.organization_id = org3.id

        # Associate Westlands Plaza to org3
        westlands_p = Property.query.filter_by(name='Westlands Commercial Plaza').first()
        if westlands_p:
            westlands_p.organization_id = org3.id

        print(f"  -> Organization: '{org3.name}' (Code: CAPITAL)")
        print(f"  -> Admin user: 'capital_admin' / 'admin' (Password: admin123)")

        # ── 4. Platform Superadmin (Global) ────────────────────────────────
        superadmin = User.query.filter_by(username='admin').first()
        if superadmin:
            superadmin.set_password('admin123')
            superadmin.organization_id = None
            print("\n[Superadmin] Global platform admin password set to 'admin123'.")

        db.session.commit()
        print("\n" + "=" * 70)
        print("  ALL MULTI-TENANT ORGANIZATIONS CONFIGURED SUCCESSFULLY!")
        print("=" * 70)
        print("  How to Login from http://127.0.0.1:5000/auth/login :")
        print("  -------------------------------------------------------------")
        print("  1. Super Administrator (Platform Paramount):")
        print("     Company Code: (Leave Blank) | Username: admin | Password: admin123")
        print("  2. Angaza Premier Properties:")
        print("     Company Code: ANGAZA        | Username: admin | Password: admin123")
        print("  3. Mama Sarah Estates & Lakeside Cottages:")
        print("     Company Code: SARAH         | Username: admin | Password: admin123")
        print("  4. Angaza Capital Commercial Holdings:")
        print("     Company Code: CAPITAL       | Username: admin | Password: admin123")
        print("=" * 70)


if __name__ == '__main__':
    setup_multitenant_businesses()
