import sqlite3
import re

def migrate():
    conn = sqlite3.connect('instance/rental_management.db')
    c = conn.cursor()

    # 1. Inspect & add organization_id columns where missing
    table_cols = {
        'tenants': 'organization_id INTEGER REFERENCES organizations(id)',
        'payments': 'organization_id INTEGER REFERENCES organizations(id)',
        'rent_charges': 'organization_id INTEGER REFERENCES organizations(id)',
        'hospitality_reservations': 'organization_id INTEGER REFERENCES organizations(id)',
        'guests': 'organization_id INTEGER REFERENCES organizations(id)'
    }

    for table, col_def in table_cols.items():
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
        if 'organization_id' not in cols:
            print(f"Adding organization_id column to {table}...")
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        else:
            print(f"organization_id already exists in {table}")

    # 2. Update existing org codes:
    # 1 -> ANG0002
    # 2 -> ANG0003
    # 3 -> ANG0004
    # (ANG0001 is reserved for Super Admin!)
    c.execute("UPDATE organizations SET org_code = 'ANG0002' WHERE id = 1")
    c.execute("UPDATE organizations SET org_code = 'ANG0003' WHERE id = 2")
    c.execute("UPDATE organizations SET org_code = 'ANG0004' WHERE id = 3")

    # 3. Backfill tenants organization_id
    c.execute("""
        UPDATE tenants
        SET organization_id = COALESCE(
            (SELECT p.organization_id FROM rental_units u JOIN properties p ON u.property_id = p.id WHERE u.current_tenant_id = tenants.id LIMIT 1),
            (SELECT p.organization_id FROM leases l JOIN rental_units u ON l.rental_unit_id = u.id JOIN properties p ON u.property_id = p.id WHERE l.tenant_id = tenants.id LIMIT 1),
            1
        )
        WHERE organization_id IS NULL
    """)

    # 4. Backfill payments organization_id
    c.execute("""
        UPDATE payments
        SET organization_id = COALESCE(
            (SELECT p.organization_id FROM properties p WHERE p.id = payments.property_id),
            1
        )
        WHERE organization_id IS NULL
    """)

    # 5. Backfill rent_charges organization_id
    c.execute("""
        UPDATE rent_charges
        SET organization_id = COALESCE(
            (SELECT p.organization_id FROM rental_units u JOIN properties p ON u.property_id = p.id WHERE u.id = rent_charges.rental_unit_id),
            1
        )
        WHERE organization_id IS NULL
    """)

    # 6. Backfill hospitality_reservations organization_id
    c.execute("""
        UPDATE hospitality_reservations
        SET organization_id = COALESCE(
            (SELECT p.organization_id FROM rental_units u JOIN properties p ON u.property_id = p.id WHERE u.id = hospitality_reservations.rental_unit_id),
            2
        )
        WHERE organization_id IS NULL
    """)

    # 7. Backfill guests organization_id
    c.execute("""
        UPDATE guests
        SET organization_id = COALESCE(
            (SELECT hr.organization_id FROM hospitality_reservations hr WHERE hr.guest_id = guests.id LIMIT 1),
            2
        )
        WHERE organization_id IS NULL
    """)

    conn.commit()
    print("Migration committed successfully!")
    print("Organizations:", c.execute("SELECT id, name, org_code, slug FROM organizations").fetchall())
    print("Tenants by org_id:", c.execute("SELECT organization_id, count(*) FROM tenants GROUP BY organization_id").fetchall())
    print("Payments by org_id:", c.execute("SELECT organization_id, count(*) FROM payments GROUP BY organization_id").fetchall())
    print("Rent charges by org_id:", c.execute("SELECT organization_id, count(*) FROM rent_charges GROUP BY organization_id").fetchall())
    print("Reservations by org_id:", c.execute("SELECT organization_id, count(*) FROM hospitality_reservations GROUP BY organization_id").fetchall())
    print("Guests by org_id:", c.execute("SELECT organization_id, count(*) FROM guests GROUP BY organization_id").fetchall())
    conn.close()

if __name__ == '__main__':
    migrate()
