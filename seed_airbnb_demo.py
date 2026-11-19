#!/usr/bin/env python
"""
seed_airbnb_demo.py — Populate Rich Operational Dummy Data for Airbnb & Short-Stay Management.
Adds realistic coastal villas, urban serviced apartments, cottages, in-house guests,
today's arrivals/departures, booking sources, folio payments, and housekeeping turnover tasks.

Usage:
    python seed_airbnb_demo.py
"""

import os
from datetime import datetime, date, timedelta

os.environ['FLASK_CONFIG'] = 'development'

from app import create_app
from app.extensions import db
from app.models.organization import Organization
from app.models.user import Landlord, User
from app.models.property import Property, RentalUnit
from app.models.hospitality import Guest, HospitalityReservation, HousekeepingTask
from app.models.pricing import RoomPricingRule
from app.utils.currency import to_cents


def run_airbnb_seed():
    app = create_app('development')
    with app.app_context():
        print("=" * 70)
        print("  ANGAZA AIRBNB MANAGEMENT — SEEDING REALISTIC OPERATIONAL DEMO DATA")
        print("=" * 70)

        # 1. Update or activate Combined Suite on Organization
        print("\n[1/6] Enabling Airbnb / Hospitality module on Organization...")
        org = Organization.query.first()
        if not org:
            org = Organization(
                name="Angaza Premier Properties & Hospitality",
                slug="angaza-premier",
                subscription_tier="COMBINED_SUITE",
                subscription_status="ACTIVE",
                enable_rentals=True,
                enable_hospitality=True,
                sms_credits=250
            )
            db.session.add(org)
            db.session.flush()
        else:
            org.enable_hospitality = True
            org.enable_rentals = True
            org.subscription_tier = "COMBINED_SUITE"
            org.sms_credits = max(org.sms_credits or 0, 250)
            db.session.flush()

        landlord = Landlord.query.first()
        if not landlord:
            landlord = Landlord(
                name="Dr. Joseph M. Kamau",
                contact_person="Dr. Joseph Kamau",
                phone="+254722100200",
                email="kamau@africarealty.co.ke",
                is_active=True
            )
            db.session.add(landlord)
            db.session.flush()

        # 2. Seed Airbnb Houses / Properties
        print("\n[2/6] Seeding 3 Airbnb Properties / Houses...")
        today = date.today()

        houses_spec = [
            {
                "name": "Watamu Palm Oceanfront Villas",
                "ref": "AIRBNB-WTM-001",
                "location": "Turtle Bay Road, Watamu Beachfront",
                "type": "COMMERCIAL",
                "desc": "Ultra-luxury beachfront suites with direct ocean access and private swimming pools."
            },
            {
                "name": "Kilimani Skyview Serviced Suites",
                "ref": "AIRBNB-KLM-002",
                "location": "Wood Avenue, Kilimani, Nairobi",
                "type": "RESIDENTIAL",
                "desc": "Modern high-rise executive serviced apartments ideal for business travelers and digital nomads."
            },
            {
                "name": "Diani Beach Garden Cottages",
                "ref": "AIRBNB-DNA-003",
                "location": "Diani Beach Road, South Coast",
                "type": "COMMERCIAL",
                "desc": "Cozy tropical self-catering cottages surrounded by lush botanical gardens."
            }
        ]

        properties = {}
        for spec in houses_spec:
            prop = Property.query.filter_by(ref_number=spec["ref"]).first()
            if not prop:
                prop = Property(
                    name=spec["name"],
                    ref_number=spec["ref"],
                    property_type=spec["type"],
                    location=spec["location"],
                    description=spec["desc"],
                    landlord_id=landlord.id,
                    organization_id=org.id,
                    management_status="ACTIVE"
                )
                db.session.add(prop)
                db.session.flush()
            else:
                prop.organization_id = org.id
                prop.management_status = "ACTIVE"
            properties[spec["ref"]] = prop

        print(f"  Verified {len(properties)} Airbnb Properties.")

        # 3. Seed Rooms / Units
        print("\n[3/6] Seeding Airbnb Rooms & Daily Inventory...")
        rooms_spec = [
            # Watamu Palm Oceanfront Villas
            ("AIRBNB-WTM-001", "Villa 1 — Oceanfront Master Suite", "Master Suite", 12000, 4, "OCCUPIED", "CLEAN"),
            ("AIRBNB-WTM-001", "Villa 2 — Coral Sunrise Suite", "Deluxe Suite", 9500, 2, "VACANT", "CLEAN"),
            ("AIRBNB-WTM-001", "Villa 3 — Palm Garden Suite", "Garden Villa", 8000, 3, "VACANT", "DIRTY"),
            # Kilimani Skyview Serviced Suites
            ("AIRBNB-KLM-002", "Penthouse A-14 — Skyline Executive", "Penthouse", 8500, 2, "OCCUPIED", "CLEAN"),
            ("AIRBNB-KLM-002", "Studio 502 — Urban Cozy Stay", "Studio", 4500, 2, "OCCUPIED", "CLEAN"),
            ("AIRBNB-KLM-002", "Suite 304 — Modern 1-Bedroom", "1-Bedroom Suite", 6000, 2, "VACANT", "CLEAN"),
            ("AIRBNB-KLM-002", "Suite 201 — Business Traveler Pod", "Studio", 5000, 1, "VACANT", "INSPECTED"),
            # Diani Beach Garden Cottages
            ("AIRBNB-DNA-003", "Cottage 1 — Baobab Haven", "Cottage", 7500, 4, "OCCUPIED", "CLEAN"),
            ("AIRBNB-DNA-003", "Cottage 2 — Frangipani Hideaway", "Cottage", 6500, 2, "VACANT", "CLEAN"),
        ]

        units_dict = {}
        for prop_ref, unit_num, utype, daily_kes, max_g, occ_stat, clean_stat in rooms_spec:
            prop = properties[prop_ref]
            unit = RentalUnit.query.filter_by(property_id=prop.id, unit_number=unit_num).first()
            if not unit:
                unit = RentalUnit(
                    property_id=prop.id,
                    unit_number=unit_num,
                    unit_type=utype,
                    operational_type="SHORT_STAY",
                    daily_rate_cents=to_cents(daily_kes),
                    rent_amount_cents=to_cents(daily_kes * 30),
                    max_guests=max_g,
                    occupancy_status=occ_stat,
                    cleaning_status=clean_stat
                )
                db.session.add(unit)
                db.session.flush()
            else:
                unit.operational_type = "SHORT_STAY"
                unit.daily_rate_cents = to_cents(daily_kes)
                unit.max_guests = max_g
                unit.occupancy_status = occ_stat
                unit.cleaning_status = clean_stat
            units_dict[unit_num] = unit

        print(f"  Verified {len(units_dict)} short-stay units across 3 properties.")

        # 4. Seed Realistic Guests
        print("\n[4/6] Seeding Guest Profiles...")
        guests_spec = [
            ("Marcus", "Vance", "+254711900111", "marcus.vance@uktour.co.uk", "GBR998877", "British"),
            ("Dr. Amina", "Wanjiku", "+254722345678", "amina.wanjiku@knh.or.ke", "ID28994411", "Kenyan"),
            ("David", "Kimani", "+254733456789", "dkimani@safaricom.co.ke", "ID31002233", "Kenyan"),
            ("Elena", "Rostova", "+254799887766", "elena.rostova@nomad.io", "RUS445566", "Russian"),
            ("Claire", "Dubois", "+254744556677", "claire@dubois-design.fr", "FRA778899", "French"),
            ("James", "Ondieki", "+254712334455", "j.ondieki@kisii.go.ke", "ID25447788", "Kenyan")
        ]

        guests_dict = {}
        for fname, lname, phone, email, doc, nat in guests_spec:
            guest = Guest.query.filter_by(phone=phone).first()
            if not guest:
                guest = Guest(
                    first_name=fname,
                    last_name=lname,
                    phone=phone,
                    email=email,
                    id_passport_number=doc,
                    nationality=nat
                )
                db.session.add(guest)
                db.session.flush()
            guests_dict[fname] = guest

        # 5. Seed Reservations (In-House, Departures Today, Arrivals Today, Settled History)
        print("\n[5/6] Seeding Live In-House Reservations, Arrivals & Folio Payments...")
        reservations_spec = [
            # 1. Marcus Vance — Villa 1 (In-House, Settled)
            {
                "code": "RES-WTM-201",
                "guest": guests_dict["Marcus"],
                "unit": units_dict["Villa 1 — Oceanfront Master Suite"],
                "check_in": today - timedelta(days=2),
                "check_out": today + timedelta(days=2),
                "nights": 4,
                "daily_rate": 12000,
                "paid": 48000,
                "status": "CHECKED_IN",
                "source": "AIRBNB",
                "method": "CARD",
                "ref": "STRIPE_CH_994821"
            },
            # 2. Dr. Amina Wanjiku — Penthouse A-14 (In-House, Partial Payment)
            {
                "code": "RES-KLM-104",
                "guest": guests_dict["Dr. Amina"],
                "unit": units_dict["Penthouse A-14 — Skyline Executive"],
                "check_in": today - timedelta(days=1),
                "check_out": today + timedelta(days=3),
                "nights": 4,
                "daily_rate": 8500,
                "paid": 20000, # total 34,000, bal 14,000
                "status": "CHECKED_IN",
                "source": "BOOKING_COM",
                "method": "MPESA",
                "ref": "QK88B49MPESA"
            },
            # 3. David Kimani — Studio 502 (In-House, Departures Today!)
            {
                "code": "RES-KLM-502",
                "guest": guests_dict["David"],
                "unit": units_dict["Studio 502 — Urban Cozy Stay"],
                "check_in": today - timedelta(days=1),
                "check_out": today,
                "nights": 1,
                "daily_rate": 4500,
                "paid": 4500,
                "status": "CHECKED_IN",
                "source": "DIRECT",
                "method": "MPESA",
                "ref": "QJ77M12MPESA"
            },
            # 4. Elena Rostova — Cottage 1 (In-House, Settled)
            {
                "code": "RES-DNA-301",
                "guest": guests_dict["Elena"],
                "unit": units_dict["Cottage 1 — Baobab Haven"],
                "check_in": today - timedelta(days=3),
                "check_out": today + timedelta(days=2),
                "nights": 5,
                "daily_rate": 7500,
                "paid": 37500,
                "status": "CHECKED_IN",
                "source": "AIRBNB",
                "method": "CARD",
                "ref": "AIRBNB_PAY_8899"
            },
            # 5. Claire Dubois — Villa 2 (Arrivals Today!)
            {
                "code": "RES-WTM-202",
                "guest": guests_dict["Claire"],
                "unit": units_dict["Villa 2 — Coral Sunrise Suite"],
                "check_in": today,
                "check_out": today + timedelta(days=4),
                "nights": 4,
                "daily_rate": 9500,
                "paid": 38000,
                "status": "CONFIRMED",
                "source": "AIRBNB",
                "method": "CARD",
                "ref": "AIRBNB_CONF_7712"
            },
            # 6. James Ondieki — Historical / Checked Out yesterday
            {
                "code": "RES-KLM-099",
                "guest": guests_dict["James"],
                "unit": units_dict["Suite 304 — Modern 1-Bedroom"],
                "check_in": today - timedelta(days=4),
                "check_out": today - timedelta(days=1),
                "nights": 3,
                "daily_rate": 6000,
                "paid": 18000,
                "status": "CHECKED_OUT",
                "source": "DIRECT",
                "method": "MPESA",
                "ref": "QI55K88MPESA"
            }
        ]

        for rspec in reservations_spec:
            res = HospitalityReservation.query.filter_by(reservation_code=rspec["code"]).first()
            total_cents = to_cents(rspec["daily_rate"] * rspec["nights"])
            paid_cents = to_cents(rspec["paid"])
            if not res:
                res = HospitalityReservation(
                    reservation_code=rspec["code"],
                    guest_id=rspec["guest"].id,
                    rental_unit_id=rspec["unit"].id,
                    check_in_date=rspec["check_in"],
                    check_out_date=rspec["check_out"],
                    num_guests=rspec["unit"].max_guests,
                    num_nights=rspec["nights"],
                    daily_rate_cents=to_cents(rspec["daily_rate"]),
                    total_stay_cents=total_cents,
                    paid_amount_cents=paid_cents,
                    booking_source=rspec["source"],
                    payment_method=rspec["method"],
                    payment_reference=rspec["ref"],
                    status=rspec["status"],
                    created_at=datetime.utcnow() - timedelta(days=rspec["nights"])
                )
                db.session.add(res)
            else:
                res.status = rspec["status"]
                res.check_in_date = rspec["check_in"]
                res.check_out_date = rspec["check_out"]
                res.paid_amount_cents = paid_cents
                res.total_stay_cents = total_cents

        # 6. Seed Turnover Housekeeping Task & Dynamic Pricing Rules
        print("\n[6/6] Seeding Housekeeping Turnover Tasks & Dynamic Pricing Rules...")
        dirty_unit = units_dict["Villa 3 — Palm Garden Suite"]
        task = HousekeepingTask.query.filter_by(rental_unit_id=dirty_unit.id, status='PENDING').first()
        if not task:
            task = HousekeepingTask(
                rental_unit_id=dirty_unit.id,
                task_type="TURNOVER_CLEAN",
                priority="HIGH",
                status="PENDING",
                scheduled_date=today,
                notes="Guest departed. Perform full turnover: change linens, deep clean bathroom, restock amenities."
            )
            db.session.add(task)

        # Dynamic Pricing Rules
        rule1 = RoomPricingRule.query.filter_by(name="High-Season Coastal Surge").first()
        if not rule1:
            rule1 = RoomPricingRule(
                name="High-Season Coastal Surge",
                start_date=date(today.year, 12, 15),
                end_date=date(today.year + 1, 1, 10),
                rule_type="MULTIPLIER",
                multiplier=1.35,
                category="HOLIDAY",
                notes="+35% Holiday festive season multiplier for all coastal and urban suites."
            )
            db.session.add(rule1)

        rule2 = RoomPricingRule.query.filter_by(name="Weekend Getaway Surge").first()
        if not rule2:
            rule2 = RoomPricingRule(
                name="Weekend Getaway Surge",
                start_date=date(today.year, 1, 1),
                end_date=date(today.year, 12, 31),
                rule_type="MULTIPLIER",
                multiplier=1.15,
                days_of_week="4,5,6", # Fri, Sat, Sun
                category="WEEKEND",
                notes="+15% Weekend rate increase for Friday through Sunday bookings."
            )
            db.session.add(rule2)

        db.session.commit()

        print("\n" + "=" * 70)
        print("  AIRBNB DEMO DATA SEEDED SUCCESSFULLY!")
        print("=" * 70)
        print("  Summary of populated assets:")
        print(f"    - Airbnb Properties:        {len(properties)}")
        print(f"    - Airbnb Rooms / Suites:    {len(units_dict)}")
        print(f"    - Active In-House Guests:   {HospitalityReservation.query.filter_by(status='CHECKED_IN').count()}")
        print(f"    - Today's Arrivals:         {HospitalityReservation.query.filter_by(check_in_date=today, status='CONFIRMED').count()}")
        print(f"    - Today's Departures:       {HospitalityReservation.query.filter_by(check_out_date=today, status='CHECKED_IN').count()}")
        print(f"    - Total Reservations:       {HospitalityReservation.query.count()}")
        print(f"    - Housekeeping Tasks:       {HousekeepingTask.query.count()}")
        print(f"    - Dynamic Pricing Rules:    {RoomPricingRule.query.count()}")
        print("=" * 70)
        print("  Open http://127.0.0.1:5000/hospitality/ to monitor operations!")
        print("=" * 70)


if __name__ == '__main__':
    run_airbnb_seed()
