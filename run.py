import os
from app import create_app
from app.extensions import db

app = create_app(os.environ.get('FLASK_CONFIG', 'default'))

@app.shell_context_processor
def make_shell_context():
    from app import models
    return dict(db=db, **{name: getattr(models, name) for name in models.__all__})

def initialize_database():
    """Create all tables and seed initial data."""
    with app.app_context():
        db.create_all()
        
        # Ensure new columns on rental_units exist for SQLite backward compatibility
        try:
            conn = db.engine.raw_connection()
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(rental_units)")
            existing_cols = [r[1] for r in cursor.fetchall()]
            
            schema_updates = [
                ("operational_type", "VARCHAR(30) DEFAULT 'LONG_TERM'"),
                ("daily_rate_cents", "INTEGER DEFAULT 0"),
                ("max_guests", "INTEGER DEFAULT 2"),
                ("cleaning_status", "VARCHAR(30) DEFAULT 'CLEAN'")
            ]
            for col_name, col_def in schema_updates:
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE rental_units ADD COLUMN {col_name} {col_def}")
            # Check organization_id on properties and users
            cursor.execute("PRAGMA table_info(properties)")
            prop_cols = [r[1] for r in cursor.fetchall()]
            if 'organization_id' not in prop_cols:
                cursor.execute("ALTER TABLE properties ADD COLUMN organization_id INTEGER")

            cursor.execute("PRAGMA table_info(users)")
            user_cols = [r[1] for r in cursor.fetchall()]
            if 'organization_id' not in user_cols:
                cursor.execute("ALTER TABLE users ADD COLUMN organization_id INTEGER")

            cursor.execute("PRAGMA table_info(payment_gateway_configs)")
            gw_cols = [r[1] for r in cursor.fetchall()]
            if 'organization_id' not in gw_cols:
                cursor.execute("ALTER TABLE payment_gateway_configs ADD COLUMN organization_id INTEGER")

            cursor.execute("PRAGMA table_info(bank_accounts)")
            bank_cols = [r[1] for r in cursor.fetchall()]
            if 'organization_id' not in bank_cols:
                cursor.execute("ALTER TABLE bank_accounts ADD COLUMN organization_id INTEGER")

            cursor.execute("PRAGMA table_info(organizations)")
            org_cols = [r[1] for r in cursor.fetchall()]
            if 'sms_credits' not in org_cols:
                cursor.execute("ALTER TABLE organizations ADD COLUMN sms_credits INTEGER DEFAULT 50")

            conn.commit()
        except Exception as e:
            print(f"[Startup Warning] Schema check: {e}")

        # Seed default Organization for SaaS multi-tenancy
        try:
            from app.models.organization import Organization
            if not Organization.query.first():
                default_org = Organization(
                    name="Angaza Premier Properties",
                    slug="angaza-premier",
                    contact_email="admin@primerent.co.ke",
                    contact_phone="+254712345678",
                    subscription_tier="COMBINED_SUITE",
                    subscription_status="ACTIVE",
                    max_properties=100,
                    max_units=500,
                    max_users=25
                )
                db.session.add(default_org)
                db.session.commit()
                print("[Startup] Seeded default Organization.")
        except Exception as e:
            print(f"[Startup Warning] Org seed: {e}")

        from app.routes.auth_bp import seed_initial_data
        seed_initial_data()
        print("[Startup] Database initialized and ready.")

if __name__ == '__main__':
    initialize_database()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
