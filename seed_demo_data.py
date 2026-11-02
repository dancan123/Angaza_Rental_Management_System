#!/usr/bin/env python
"""
seed_demo_data.py — Rich Realistic Demo Data for Angaza Rentals System.
Populates the database with realistic Kenyan landlords, properties, units,
tenants, leases, bookings, rent charges, payments, and maintenance records.

Usage:
    python seed_demo_data.py
"""

import os
from datetime import datetime, date, timedelta

os.environ['FLASK_CONFIG'] = 'development'

from app import create_app
from app.extensions import db
from app.routes.auth_bp import seed_initial_data
from app.models.user import Landlord, User, Role
from app.models.property import Property, Building, Floor, RentalUnit
from app.models.tenant import Tenant, NextOfKin
from app.models.lease import Lease
from app.models.booking import Booking
from app.models.finance import RentCharge, Payment, PaymentAllocation
from app.models.maintenance import MaintenanceRequest, Expense
from app.models.utility import Meter, MeterReading
from app.models.gateway import PaymentGatewayConfig, BankAccount
from app.models.communication import Notification
from app.utils.currency import to_cents

def run_seed():
    app = create_app('development')
    with app.app_context():
        print("=" * 65)
        print("  ANGAZA RENTALS SYSTEM — SEEDING REALISTIC OPERATIONAL DATA")
        print("=" * 65)

        # 1. Initialize schema and default roles/admin
        print("\n[1/10] Verifying database schema & initial roles/admin...")
        db.create_all()
        seed_initial_data()
        admin = User.query.filter_by(username='admin').first()

        # Check if already seeded to prevent duplicate demo data
        if Property.query.first():
            print("  [INFO] Existing properties found. Cleaning old demo operational data...")
            # Clean in reverse dependency order
            PaymentAllocation.query.delete()
            Payment.query.delete()
            RentCharge.query.delete()
            Booking.query.delete()
            Lease.query.delete()
            MaintenanceRequest.query.delete()
            Expense.query.delete()
            RentalUnit.query.delete()
            Floor.query.delete()
            Building.query.delete()
            Property.query.delete()
            NextOfKin.query.delete()
            Tenant.query.delete()
            Landlord.query.delete()
            PaymentGatewayConfig.query.delete()
            BankAccount.query.delete()
            Notification.query.delete()
            db.session.commit()
            print("  Old operational data cleared.")

        # 2. Seed Landlords (Property Owners)
        print("\n[2/10] Seeding Landlords (Property Owners)...")
        landlord1 = Landlord(
            name="Dr. Joseph M. Kamau",
            contact_person="Dr. Joseph Kamau",
            phone="+254722100200",
            email="kamau@africarealty.co.ke",
            tax_pin="A001234567X",
            address="P.O. Box 45210-00100, Nairobi",
            bank_account_info="KCB Bank Kenya, Westlands Branch, Acc: 1122334455",
            is_active=True
        )
        landlord2 = Landlord(
            name="Mama Sarah W. Ochieng",
            contact_person="Sarah Ochieng",
            phone="+254733400500",
            email="sarah.ochieng@gmail.com",
            tax_pin="A009876543Y",
            address="P.O. Box 12890-00200, Nairobi",
            bank_account_info="Equity Bank, Upper Hill Branch, Acc: 018029384756",
            is_active=True
        )
        landlord3 = Landlord(
            name="Angaza Capital Holdings Ltd",
            contact_person="David Mwangi (Managing Director)",
            phone="+254711888999",
            email="investments@angazacapital.co.ke",
            tax_pin="P051284920K",
            address="Kilimani Business Park, 4th Floor, Nairobi",
            bank_account_info="Standard Chartered Bank, Chiromo Branch, Acc: 870023419",
            is_active=True
        )
        db.session.add_all([landlord1, landlord2, landlord3])
        db.session.flush()
        print(f"  Created 3 Landlords: {landlord1.name}, {landlord2.name}, {landlord3.name}")

        # 3. Seed Properties & Buildings & Floors
        print("\n[3/10] Seeding Properties, Buildings & Floors...")
        
        # Property 1: Kilimani Heights Apartments (Residential Apartments)
        prop1 = Property(
            landlord_id=landlord1.id,
            name="Kilimani Heights Apartments",
            ref_number="PROP-KLM-001",
            property_type="APARTMENT",
            location="Argwings Kodhek Road, Kilimani, Nairobi",
            description="Modern executive apartments with high-speed elevators, backup generator, borehole water, and 24/7 manned security.",
            image_url="/static/img/property_kilimani.jpg",
            total_floors=4,
            management_status="ACTIVE"
        )
        db.session.add(prop1)
        db.session.flush()

        bldg1_A = Building(property_id=prop1.id, name="Block A - Executive Wings", total_floors=4)
        bldg1_B = Building(property_id=prop1.id, name="Block B - Garden Wings", total_floors=4)
        db.session.add_all([bldg1_A, bldg1_B])
        db.session.flush()

        # Floors for Block A & B
        floors_prop1 = []
        for bldg in [bldg1_A, bldg1_B]:
            for fn in range(1, 4):
                fl = Floor(building_id=bldg.id, floor_number=fn, floor_name=f"Floor {fn}")
                floors_prop1.append(fl)
        db.session.add_all(floors_prop1)
        db.session.flush()

        # Property 2: Westlands Commercial Plaza
        prop2 = Property(
            landlord_id=landlord3.id,
            name="Westlands Commercial Plaza",
            ref_number="PROP-WST-002",
            property_type="COMMERCIAL",
            location="Muthithi Road, Westlands, Nairobi",
            description="High-footfall commercial complex ideal for retail outlets, banking halls, tech firms, and professional consultancies.",
            image_url="/static/img/property_westlands.jpg",
            total_floors=3,
            management_status="ACTIVE"
        )
        db.session.add(prop2)
        db.session.flush()

        bldg2_main = Building(property_id=prop2.id, name="Main Commercial Tower", total_floors=3)
        db.session.add(bldg2_main)
        db.session.flush()

        fl2_g = Floor(building_id=bldg2_main.id, floor_number=0, floor_name="Ground Floor (Retail)")
        fl2_1 = Floor(building_id=bldg2_main.id, floor_number=1, floor_name="1st Floor (Office Suites)")
        fl2_2 = Floor(building_id=bldg2_main.id, floor_number=2, floor_name="2nd Floor (Corporate Offices)")
        db.session.add_all([fl2_g, fl2_1, fl2_2])
        db.session.flush()

        # Property 3: Rongai Sunrise Residences (Bedsitters & 1-Bedrooms)
        prop3 = Property(
            landlord_id=landlord2.id,
            name="Rongai Sunrise Residences",
            ref_number="PROP-RNG-003",
            property_type="BEDSITTER",
            location="Magadi Road, Ongata Rongai, Kajiado County",
            description="Affordable residential units near shopping centers and university hubs, featuring constant water supply and prepaid electricity.",
            image_url="/static/img/property_rongai.jpg",
            total_floors=3,
            management_status="ACTIVE"
        )
        db.session.add(prop3)
        db.session.flush()

        bldg3_main = Building(property_id=prop3.id, name="Sunrise Block", total_floors=3)
        db.session.add(bldg3_main)
        db.session.flush()

        fl3_1 = Floor(building_id=bldg3_main.id, floor_number=1, floor_name="Ground Floor")
        fl3_2 = Floor(building_id=bldg3_main.id, floor_number=2, floor_name="1st Floor")
        db.session.add_all([fl3_1, fl3_2])
        db.session.flush()

        # Property 4: Karen Green Villas (Residential Villas)
        prop4 = Property(
            landlord_id=landlord1.id,
            name="Karen Green Villas",
            ref_number="PROP-KRN-004",
            property_type="RESIDENTIAL",
            location="Mbagathi Ridge, Karen, Nairobi",
            description="Exclusive luxury 4-bedroom townhouses with private landscaped gardens, DSQ, clubhouse, and solar water heating.",
            image_url="/static/img/property_karen.jpg",
            total_floors=2,
            management_status="ACTIVE"
        )
        db.session.add(prop4)
        db.session.flush()

        bldg4_main = Building(property_id=prop4.id, name="The Enclave", total_floors=2)
        db.session.add(bldg4_main)
        db.session.flush()

        fl4_g = Floor(building_id=bldg4_main.id, floor_number=1, floor_name="Ground & Upper Level")
        db.session.add(fl4_g)
        db.session.flush()

        print("  Created 4 diverse properties, 5 buildings, and 12 floors.")

        # 4. Seed Rental Units
        print("\n[4/10] Seeding Rental Units with diverse occupancy states...")
        units_to_create = [
            # Kilimani Heights (Block A)
            (prop1.id, bldg1_A.id, floors_prop1[0].id, "A-101", "2_BEDROOM", 55000, 55000, 2, 2, "Borehole, Lift, Balcony, Fitted Kitchen", "OCCUPIED"),
            (prop1.id, bldg1_A.id, floors_prop1[0].id, "A-102", "2_BEDROOM", 55000, 55000, 2, 2, "Borehole, Lift, Balcony", "OCCUPIED"),
            (prop1.id, bldg1_A.id, floors_prop1[1].id, "A-201", "3_BEDROOM", 75000, 75000, 3, 3, "Master Ensuite, Balcony, Generator", "OCCUPIED"),
            (prop1.id, bldg1_A.id, floors_prop1[1].id, "A-202", "3_BEDROOM", 75000, 75000, 3, 3, "Master Ensuite, High Floor, Pantry", "MAINTENANCE"),
            (prop1.id, bldg1_A.id, floors_prop1[2].id, "A-301", "3_BEDROOM", 80000, 80000, 3, 3, "Penthouse Level, Panoramic View", "VACANT"),
            (prop1.id, bldg1_A.id, floors_prop1[2].id, "A-302", "3_BEDROOM", 80000, 80000, 3, 3, "Penthouse Level, Modern Finishings", "RESERVED"),

            # Kilimani Heights (Block B)
            (prop1.id, bldg1_B.id, floors_prop1[3].id, "B-101", "1_BEDROOM", 38000, 38000, 1, 1, "Garden View, Secure Parking", "OCCUPIED"),
            (prop1.id, bldg1_B.id, floors_prop1[3].id, "B-102", "1_BEDROOM", 38000, 38000, 1, 1, "Garden View, Inbuilt Wardrobes", "OCCUPIED"),
            (prop1.id, bldg1_B.id, floors_prop1[4].id, "B-201", "2_BEDROOM", 52000, 52000, 2, 2, "Balcony, Spacious Lounge", "OCCUPIED"),
            (prop1.id, bldg1_B.id, floors_prop1[5].id, "B-301", "2_BEDROOM", 52000, 52000, 2, 2, "Top Floor, Natural Lighting", "VACANT"),

            # Westlands Commercial Plaza
            (prop2.id, bldg2_main.id, fl2_g.id, "SHOP-01", "COMMERCIAL_SHOP", 95000, 190000, 0, 1, "Road Frontage, Large Display Glass, 3-Phase Power", "OCCUPIED"),
            (prop2.id, bldg2_main.id, fl2_g.id, "SHOP-02", "COMMERCIAL_SHOP", 85000, 170000, 0, 1, "Direct Arcade Access, Water Connection", "OCCUPIED"),
            (prop2.id, bldg2_main.id, fl2_1.id, "OFFICE-101", "OFFICE_SPACE", 65000, 130000, 0, 2, "Partially Partitioned, High-Speed Internet ready", "OCCUPIED"),
            (prop2.id, bldg2_main.id, fl2_1.id, "OFFICE-102", "OFFICE_SPACE", 60000, 120000, 0, 1, "Open Plan Office, Central Air conditioning", "VACANT"),
            (prop2.id, bldg2_main.id, fl2_2.id, "OFFICE-201", "OFFICE_SPACE", 120000, 240000, 0, 2, "Executive Suite, Dedicated Boardroom, Kitchenette", "RESERVED"),

            # Rongai Sunrise Residences
            (prop3.id, bldg3_main.id, fl3_1.id, "RNG-G01", "BEDSITTER", 12000, 12000, 0, 1, "Tiled Floor, Constant Water, Balcony", "OCCUPIED"),
            (prop3.id, bldg3_main.id, fl3_1.id, "RNG-G02", "BEDSITTER", 12000, 12000, 0, 1, "Prepaid Token Meter, Good Security", "OCCUPIED"),
            (prop3.id, bldg3_main.id, fl3_1.id, "RNG-G03", "1_BEDROOM", 18000, 18000, 1, 1, "Spacious Kitchenette, Security Door", "OCCUPIED"),
            (prop3.id, bldg3_main.id, fl3_2.id, "RNG-101", "BEDSITTER", 12000, 12000, 0, 1, "Natural Light, Roof Clotheslines", "VACANT"),
            (prop3.id, bldg3_main.id, fl3_2.id, "RNG-102", "1_BEDROOM", 18000, 18000, 1, 1, "Separate Bedroom, Private Balcony", "VACANT"),

            # Karen Green Villas
            (prop4.id, bldg4_main.id, fl4_g.id, "VILLA-01", "4_BEDROOM", 180000, 360000, 4, 4, "Private Garden, 2 DSQs, Solar Heating, Electric Fence", "OCCUPIED"),
            (prop4.id, bldg4_main.id, fl4_g.id, "VILLA-02", "4_BEDROOM", 180000, 360000, 4, 4, "Corner Villa, Large Gazebo, Double Garage", "OCCUPIED"),
            (prop4.id, bldg4_main.id, fl4_g.id, "VILLA-03", "4_BEDROOM", 180000, 360000, 4, 4, "Perimeter Forest View, Jacuzzi Master", "VACANT"),
        ]

        units_map = {}
        for (pid, bid, fid, unum, utype, rent, dep, beds, baths, amens, status) in units_to_create:
            unit = RentalUnit(
                property_id=pid,
                building_id=bid,
                floor_id=fid,
                unit_number=unum,
                unit_type=utype,
                rent_amount_cents=to_cents(rent),
                deposit_amount_cents=to_cents(dep),
                bedrooms=beds,
                bathrooms=baths,
                amenities=amens,
                description=f"Standard unit {unum} in good order.",
                occupancy_status=status
            )
            db.session.add(unit)
            units_map[unum] = unit

        db.session.flush()
        print(f"  Created {len(units_to_create)} rental units across residential, commercial, and luxury classes.")

        # 5. Seed Tenants
        print("\n[5/10] Seeding Tenants & Next-of-Kin KYC records...")
        tenants_data = [
            ("Brian", "Kiprop", "29482103", "+254712345678", "brian.kiprop@safari.co.ke", "Software Engineer at Safaricom", "P.O. Box 30100 Nairobi", "Mercy Chebet", "Sister", "+254722998877"),
            ("Faith", "Wambui", "31849204", "+254721456789", "faith.wambui@kcbgroup.com", "Financial Analyst at KCB", "Argwings Kodhek, Nairobi", "John Wambui", "Father", "+254720112233"),
            ("Kevin", "Otieno", "27591823", "+254733567890", "kevin.otieno@gmail.com", "Civil Engineer at KenHA", "Kilimani, Nairobi", "Brenda Atieno", "Spouse", "+254735889900"),
            ("Grace", "Muthoni", "33918245", "+254701234567", "muthoni.grace@lawfirm.co.ke", "Senior Associate Advocate", "Kilimani, Nairobi", "Peter Kamau", "Brother", "+254705123456"),
            ("Samuel", "Njoroge", "28374912", "+254722678901", "samuel.njoroge@translogistics.co.ke", "Logistics Manager", "Ongata Rongai", "Agnes Wanjiru", "Spouse", "+254721334455"),
            ("Dr. Allan", "Makori", "25192834", "+254711223344", "allan.makori@knh.or.ke", "Consultant Surgeon KNH", "Karen, Nairobi", "Dr. Christine Nyaboke", "Spouse", "+254712556677"),
            ("Fatuma", "Hassan", "30291847", "+254728990011", "fatuma.hassan@coastventures.com", "Managing Director", "Karen Mbagathi, Nairobi", "Ali Hassan", "Brother", "+254729112233"),
            ("James", "Kimani", "26481920", "+254710998877", "james@quickmartretail.co.ke", "Franchise Retail Director", "Westlands, Nairobi", "Ann Kimani", "Spouse", "+254710113355"),
            ("Dennis", "Mwangi", "32091834", "+254708776655", "dennis@innovatetech.io", "Tech Startup Founder", "Westlands, Nairobi", "Eric Mwangi", "Brother", "+254708112244"),
            ("Cynthia", "Moraa", "29182736", "+254720998811", "cynthia.moraa@consultancy.co.ke", "Management Consultant", "Westlands, Nairobi", "Dan Moraa", "Brother", "+254720113344"),
            ("Mercy", "Chepngetich", "34918273", "+254724889900", "mercy.chep@gmail.com", "University Postgraduate Student", "Multimedia Univ Area, Rongai", "Caleb Cheruiyot", "Uncle", "+254722445566"),
            ("Paul", "Omondi", "35129384", "+254790112233", "paul.omondi@freelance.net", "Digital Marketer & Copywriter", "Tuala, Rongai", "Susan Achieng", "Mother", "+254790445566"),
            ("Esther", "Akinyi", "31029384", "+254714556677", "esther.akinyi@standardgroup.co.ke", "Senior Journalist", "Rongai, Kajiado", "George Oduor", "Brother", "+254714889900"),
        ]

        tenants_map = {}
        for (fn, ln, idnum, phone, email, occ, addr, kin_name, kin_rel, kin_phone) in tenants_data:
            t = Tenant(
                first_name=fn,
                last_name=ln,
                id_passport_number=idnum,
                phone=phone,
                email=email,
                physical_address=addr,
                occupation=occ,
                emergency_contact=kin_name,
                emergency_phone=kin_phone,
                is_active=True
            )
            db.session.add(t)
            db.session.flush()

            kin = NextOfKin(
                tenant_id=t.id,
                full_name=kin_name,
                relationship=kin_rel,
                phone=kin_phone
            )
            db.session.add(kin)
            tenants_map[f"{fn} {ln}"] = t

        db.session.flush()
        print(f"  Created {len(tenants_data)} tenant KYC records with verified next-of-kin contacts.")

        # 6. Assign Tenants to Units & Create Leases
        print("\n[6/10] Assigning Tenants to Occupied Units and executing Leases...")
        occupancy_assignments = [
            # Unit, Tenant Name, Monthly Rent, Start Date
            ("A-101", "Brian Kiprop", 55000, date(2025, 1, 1)),
            ("A-102", "Faith Wambui", 55000, date(2025, 3, 1)),
            ("A-201", "Kevin Otieno", 75000, date(2025, 2, 1)),
            ("B-101", "Grace Muthoni", 38000, date(2025, 4, 1)),
            ("B-102", "Samuel Njoroge", 38000, date(2025, 5, 1)),
            ("B-201", "Esther Akinyi", 52000, date(2025, 6, 1)),
            ("SHOP-01", "James Kimani", 95000, date(2024, 11, 1)),
            ("SHOP-02", "Dennis Mwangi", 85000, date(2025, 1, 15)),
            ("OFFICE-101", "Cynthia Moraa", 65000, date(2025, 2, 1)),
            ("RNG-G01", "Mercy Chepngetich", 12000, date(2025, 7, 1)),
            ("RNG-G02", "Paul Omondi", 12000, date(2025, 8, 1)),
            ("VILLA-01", "Dr. Allan Makori", 180000, date(2024, 9, 1)),
            ("VILLA-02", "Fatuma Hassan", 180000, date(2024, 12, 1)),
        ]

        leases_map = {}
        for (unum, tname, rent_val, sdate) in occupancy_assignments:
            unit = units_map[unum]
            tenant = tenants_map[tname]
            unit.current_tenant_id = tenant.id
            unit.occupancy_status = "OCCUPIED"

            lease_code = f"LS-{unum}-{sdate.year}"
            lease = Lease(
                lease_number=lease_code,
                rental_unit_id=unit.id,
                tenant_id=tenant.id,
                start_date=sdate,
                end_date=sdate + timedelta(days=365),
                monthly_rent_cents=to_cents(rent_val),
                deposit_cents=unit.deposit_amount_cents,
                payment_due_day=5,
                notice_period_days=30,
                terms_and_conditions="Standard residential/commercial lease under the Kenyan Landlord and Tenant Act. Rent payable on or before 5th of each month.",
                status="ACTIVE",
                signed_at=datetime.combine(sdate, datetime.min.time())
            )
            db.session.add(lease)
            leases_map[unum] = (lease, unit, tenant, rent_val)

        db.session.flush()
        print(f"  Executed {len(occupancy_assignments)} active lease contracts with automatic unit linking.")

        # 7. Seed Bookings / Reservations
        print("\n[7/10] Seeding Prospective Tenant Bookings...")
        booking1 = Booking(
            rental_unit_id=units_map["A-302"].id,
            booking_reference="BK-2026-001",
            prospective_name="Charles Mutiso",
            prospective_phone="+254718554433",
            prospective_email="charles.mutiso@outlook.com",
            prospective_id_number="28471920",
            booking_date=date.today() - timedelta(days=5),
            expected_move_in_date=date.today() + timedelta(days=10),
            booking_deposit_cents=to_cents(40000),
            expiry_date=date.today() + timedelta(days=15),
            status="CONFIRMED",
            notes="Paid KES 40,000 reservation commitment via M-Pesa. Move-in scheduled for 15th."
        )
        booking2 = Booking(
            rental_unit_id=units_map["OFFICE-201"].id,
            booking_reference="BK-2026-002",
            prospective_name="Nairobi FinTech Labs Ltd (Attn: Walter Koech)",
            prospective_phone="+254722339900",
            prospective_email="operations@fintechlabs.ke",
            prospective_id_number="CPR/2024/9102",
            booking_date=date.today() - timedelta(days=2),
            expected_move_in_date=date.today() + timedelta(days=20),
            booking_deposit_cents=to_cents(120000),
            expiry_date=date.today() + timedelta(days=25),
            status="CONFIRMED",
            notes="Corporate booking for the full executive 2nd floor suite."
        )
        db.session.add_all([booking1, booking2])
        db.session.flush()
        print("  Created 2 confirmed unit reservations with booking deposits.")

        # 8. Seed Rent Billing (Invoices), Payments & Allocations
        print("\n[8/10] Seeding Invoices, Rent Payments (M-Pesa, Bank, Cash) & Receipts...")
        today = date.today()
        current_month = today.month
        current_year = today.year

        # Previous month
        prev_month = 12 if current_month == 1 else current_month - 1
        prev_year = current_year - 1 if current_month == 1 else current_year

        payment_counter = 1001
        receipt_counter = 5001

        for unum, (lease, unit, tenant, rent_val) in leases_map.items():
            # A) Generate previous month charge
            inv_prev = f"INV-{prev_year}{prev_month:02d}-{unum}"
            charge_prev = RentCharge(
                lease_id=lease.id,
                tenant_id=tenant.id,
                rental_unit_id=unit.id,
                invoice_number=inv_prev,
                charge_type="RENT",
                period_month=prev_month,
                period_year=prev_year,
                amount_cents=to_cents(rent_val),
                amount_paid_cents=to_cents(rent_val),  # Fully paid
                due_date=date(prev_year, prev_month, 5),
                status="PAID",
                description=f"Monthly Rent for {date(prev_year, prev_month, 1).strftime('%B %Y')} - Unit {unum}"
            )
            db.session.add(charge_prev)
            db.session.flush()

            # Record previous month payment
            pay_prev = Payment(
                tenant_id=tenant.id,
                rental_unit_id=unit.id,
                property_id=unit.property_id,
                payment_number=f"PAY-{payment_counter}",
                receipt_number=f"RCP-{receipt_counter}",
                amount_cents=to_cents(rent_val),
                payment_date=datetime(prev_year, prev_month, 4, 10, 30),
                payment_method="MPESA_PAYBILL" if payment_counter % 2 == 0 else "BANK_TRANSFER",
                transaction_reference=f"SDF{payment_counter}LK{prev_month}",
                payment_status="CONFIRMED",
                recorded_by_user_id=admin.id if admin else None,
                description=f"Rent settlement for {date(prev_year, prev_month, 1).strftime('%B %Y')}",
                verified_at=datetime(prev_year, prev_month, 4, 10, 31)
            )
            payment_counter += 1
            receipt_counter += 1
            db.session.add(pay_prev)
            db.session.flush()

            alloc_prev = PaymentAllocation(
                payment_id=pay_prev.id,
                rent_charge_id=charge_prev.id,
                allocated_amount_cents=to_cents(rent_val)
            )
            db.session.add(alloc_prev)

            # B) Generate current month charge
            inv_curr = f"INV-{current_year}{current_month:02d}-{unum}"
            due_d = date(current_year, current_month, 5)

            # Distribute realistic payment statuses across units
            # 60% fully paid, 20% partial, 20% unpaid (arrears)
            if unum in ["A-101", "B-101", "SHOP-01", "VILLA-01", "RNG-G01"]:
                # Fully Paid
                paid_amt = rent_val
                st = "PAID"
            elif unum in ["A-102", "SHOP-02", "VILLA-02"]:
                # Partial Payment
                paid_amt = rent_val // 2
                st = "PARTIALLY_PAID"
            else:
                # Unpaid / Arrears
                paid_amt = 0
                st = "PENDING"

            charge_curr = RentCharge(
                lease_id=lease.id,
                tenant_id=tenant.id,
                rental_unit_id=unit.id,
                invoice_number=inv_curr,
                charge_type="RENT",
                period_month=current_month,
                period_year=current_year,
                amount_cents=to_cents(rent_val),
                amount_paid_cents=to_cents(paid_amt),
                due_date=due_d,
                status=st,
                description=f"Monthly Rent for {date(current_year, current_month, 1).strftime('%B %Y')} - Unit {unum}"
            )
            db.session.add(charge_curr)
            db.session.flush()

            # Record payment if paid_amt > 0
            if paid_amt > 0:
                pay_curr = Payment(
                    tenant_id=tenant.id,
                    rental_unit_id=unit.id,
                    property_id=unit.property_id,
                    payment_number=f"PAY-{payment_counter}",
                    receipt_number=f"RCP-{receipt_counter}",
                    amount_cents=to_cents(paid_amt),
                    payment_date=datetime.utcnow() - timedelta(days=2),
                    payment_method="MPESA_PAYBILL" if unum != "VILLA-01" else "BANK_TRANSFER",
                    transaction_reference=f"QWE{payment_counter}MPESA",
                    payment_status="CONFIRMED",
                    recorded_by_user_id=admin.id if admin else None,
                    description=f"Rent settlement for {date(current_year, current_month, 1).strftime('%B %Y')}",
                    verified_at=datetime.utcnow() - timedelta(days=2)
                )
                payment_counter += 1
                receipt_counter += 1
                db.session.add(pay_curr)
                db.session.flush()

                alloc_curr = PaymentAllocation(
                    payment_id=pay_curr.id,
                    rent_charge_id=charge_curr.id,
                    allocated_amount_cents=to_cents(paid_amt)
                )
                db.session.add(alloc_curr)

        db.session.flush()
        print(f"  Generated {len(leases_map) * 2} monthly rent invoices and verified payment allocations.")

        # 9. Seed Maintenance Tickets & Operating Expenses
        print("\n[9/10] Seeding Maintenance Tickets & Property Operating Expenses...")
        maint1 = MaintenanceRequest(
            rental_unit_id=units_map["A-202"].id,
            tenant_id=None,
            title="Kitchen Sink Pipe Leakage & Water Pressure Rectification",
            description="Under-sink flexi connector ruptured causing slight flooding on kitchen floor tiles. Unit undergoing repair before new tenant occupancy.",
            priority="HIGH",
            status="IN_PROGRESS",
            reported_date=datetime.utcnow() - timedelta(days=3),
            assigned_to_technician="Mwangi Plumbers & Sanitary Works",
            technician_contact="+254722881122"
        )
        maint2 = MaintenanceRequest(
            rental_unit_id=units_map["B-101"].id,
            tenant_id=tenants_map["Grace Muthoni"].id,
            title="Circuit Breaker Frequent Tripping in Master Bedroom",
            description="Tenant reported that instantaneous shower causes main MCB to trip when run on high setting.",
            priority="MEDIUM",
            status="REPORTED",
            reported_date=datetime.utcnow() - timedelta(days=1),
            assigned_to_technician="Kariuki Electrical Contractors",
            technician_contact="+254710332211"
        )
        maint3 = MaintenanceRequest(
            rental_unit_id=units_map["VILLA-01"].id,
            tenant_id=tenants_map["Dr. Allan Makori"].id,
            title="Borehole Pressure Pump Automatic Switch Replacement",
            description="Automatic pressure sensor failed, preventing auto-cutoff when rooftop tank reaches capacity.",
            priority="EMERGENCY",
            status="RESOLVED",
            reported_date=datetime.utcnow() - timedelta(days=10),
            assigned_to_technician="Davis & Shirtliff Technical Support",
            technician_contact="+254711079000",
            resolved_date=datetime.utcnow() - timedelta(days=8)
        )
        db.session.add_all([maint1, maint2, maint3])
        db.session.flush()

        # Property Operating Expenses
        exp1 = Expense(
            property_id=prop4.id,
            rental_unit_id=units_map["VILLA-01"].id,
            category="MAINTENANCE",
            amount_cents=to_cents(24500),
            expense_date=date.today() - timedelta(days=8),
            supplier_name="Davis & Shirtliff Ltd",
            description="Supply and installation of digital borehole pressure cutoff sensor kit.",
            recorded_by_user_id=admin.id if admin else None
        )
        exp2 = Expense(
            property_id=prop1.id,
            rental_unit_id=None,
            category="SECURITY",
            amount_cents=to_cents(45000),
            expense_date=date.today() - timedelta(days=5),
            supplier_name="SecureGuard East Africa Ltd",
            description="Monthly guard services for Kilimani Heights (2 Day Guards, 2 Night Guards).",
            recorded_by_user_id=admin.id if admin else None
        )
        exp3 = Expense(
            property_id=prop2.id,
            rental_unit_id=None,
            category="UTILITIES",
            amount_cents=to_cents(32000),
            expense_date=date.today() - timedelta(days=4),
            supplier_name="Kenya Power (KPLC)",
            description="Common area electricity bill for Westlands Commercial Plaza (elevators & exterior lighting).",
            recorded_by_user_id=admin.id if admin else None
        )
        db.session.add_all([exp1, exp2, exp3])
        db.session.flush()
        print("  Created 3 realistic maintenance work orders and 3 logged operating expenses.")

        # 9b. Seed Utility Sub-Meters & Meter Readings
        print("\n[9b/10] Seeding Water & Electricity Sub-Meters...")
        sample_meters = [
            (prop1.id, units_map["A-101"].id, "WTR-KLM-101", "WATER", 15000, 35.5, 48.2),
            (prop1.id, units_map["A-102"].id, "WTR-KLM-102", "WATER", 15000, 20.0, 31.4),
            (prop1.id, units_map["A-201"].id, "WTR-KLM-201", "WATER", 15000, 42.0, 56.8),
            (prop1.id, units_map["A-202"].id, "WTR-KLM-202", "WATER", 15000, 15.0, 26.5),
            (prop2.id, units_map["SHOP-01"].id, "WTR-WST-S01", "WATER", 18000, 110.0, 134.2),
            (prop2.id, units_map["SHOP-01"].id, "PWR-WST-S01", "ELECTRICITY", 2500, 450.0, 580.0),
            (prop3.id, units_map["B-101"].id, "WTR-RNG-101", "WATER", 12000, 12.0, 19.5),
            (prop4.id, units_map["VILLA-01"].id, "WTR-KRN-V01", "WATER", 16000, 85.0, 112.4),
        ]
        created_meters = []
        for (pid, uid, mnum, mtype, rate, prev, cur) in sample_meters:
            m = Meter(
                property_id=pid,
                rental_unit_id=uid,
                meter_number=mnum,
                meter_type=mtype,
                rate_per_unit_cents=rate,
                initial_reading=prev,
                last_reading=cur,
                is_active=True
            )
            db.session.add(m)
            created_meters.append((m, prev, cur))
        db.session.flush()

        for (m, prev, cur) in created_meters:
            units_used = round(cur - prev, 2)
            cost = int(round(units_used * m.rate_per_unit_cents))
            reading = MeterReading(
                meter_id=m.id,
                reading_date=date.today() - timedelta(days=2),
                previous_reading=prev,
                current_reading=cur,
                units_consumed=units_used,
                rate_per_unit_cents=m.rate_per_unit_cents,
                total_cost_cents=cost,
                billed_status='BILLED'
            )
            db.session.add(reading)
        db.session.flush()
        print(f"  Created {len(sample_meters)} water & electricity sub-meters with verified baseline readings.")

        # 10. Seed Payment Gateways & Bank Accounts
        print("\n[10/10] Seeding M-Pesa Gateways & Bank Accounts...")
        mpesa_cfg = PaymentGatewayConfig(
            landlord_id=landlord1.id,
            property_id=prop1.id,
            gateway_type="MPESA_PAYBILL",
            name="Kilimani Heights Safaricom Paybill",
            shortcode="174379",
            consumer_key="demo_consumer_key_xyz123",
            consumer_secret="demo_consumer_secret_abc456",
            passkey="bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919",
            callback_url="https://api.angazarentals.co.ke/mpesa/c2b-callback",
            account_reference_pattern="{unit_number}",
            is_active=True,
            is_sandbox=True
        )
        bank_acc = BankAccount(
            landlord_id=landlord1.id,
            property_id=prop1.id,
            bank_name="KCB Bank Kenya",
            account_name="Angaza Rentals Client Account",
            account_number="1289384756",
            branch="Westlands Branch",
            currency="KES",
            is_active=True
        )
        db.session.add_all([mpesa_cfg, bank_acc])

        # Notifications
        notif1 = Notification(
            title="Rent Payment Confirmed",
            message=f"Received KES 55,000 for Unit A-101 from Brian Kiprop via M-Pesa Ref QWE1014MPESA.",
            notification_type="PAYMENT",
            channel="SYSTEM"
        )
        notif2 = Notification(
            title="New Maintenance Request Logged",
            message="Kitchen Sink Pipe Leakage reported for Unit A-202 (High Priority).",
            notification_type="MAINTENANCE",
            channel="SYSTEM"
        )
        db.session.add_all([notif1, notif2])

        db.session.commit()
        print("\n" + "=" * 65)
        print("  DEMO DATA SEEDING COMPLETE!")
        print("=" * 65)
        print("  Summary of populated assets:")
        print(f"    - Landlords:           {Landlord.query.count()}")
        print(f"    - Properties:          {Property.query.count()}")
        print(f"    - Buildings:           {Building.query.count()}")
        print(f"    - Rental Units:        {RentalUnit.query.count()}")
        print(f"      * Occupied:          {RentalUnit.query.filter_by(occupancy_status='OCCUPIED').count()}")
        print(f"      * Vacant:            {RentalUnit.query.filter_by(occupancy_status='VACANT').count()}")
        print(f"      * Reserved:          {RentalUnit.query.filter_by(occupancy_status='RESERVED').count()}")
        print(f"      * Under Maint:       {RentalUnit.query.filter_by(occupancy_status='MAINTENANCE').count()}")
        print(f"    - Active Tenants:      {Tenant.query.count()}")
        print(f"    - Executed Leases:     {Lease.query.count()}")
        print(f"    - Unit Bookings:       {Booking.query.count()}")
        print(f"    - Invoices / Charges:  {RentCharge.query.count()}")
        print(f"    - Verified Payments:   {Payment.query.count()}")
        print(f"    - Maintenance Orders:  {MaintenanceRequest.query.count()}")
        print(f"    - Operating Expenses:  {Expense.query.count()}")
        print("=" * 65)
        print("  You can now start the application with: python run.py")
        print("=" * 65)

if __name__ == '__main__':
    run_seed()
