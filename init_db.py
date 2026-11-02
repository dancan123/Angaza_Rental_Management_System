#!/usr/bin/env python
"""
Database initialization script for Angaza Rentals System.
Run this once before starting the application for the first time.

Usage:
    python init_db.py           # Initializes tables, roles, and admin
    python init_db.py --demo    # Also populates rich realistic demo properties & tenants
"""
import sys
import os

os.environ['FLASK_CONFIG'] = 'development'

from app import create_app
from app.extensions import db
from app.routes.auth_bp import seed_initial_data

print("=" * 60)
print("  ANGAZA RENTALS SYSTEM — Database Initialization")
print("=" * 60)

app = create_app('development')

with app.app_context():
    print("\n[1/3] Creating database tables...")
    db.create_all()
    print("      Done.")
    
    print("\n[2/3] Seeding initial data (roles, permissions, admin user)...")
    seed_initial_data()
    print("      Done.")
    
    print("\n[3/3] Verifying setup...")
    from app.models.user import User, Role
    admin = User.query.filter_by(username='admin').first()
    roles = Role.query.count()
    print(f"      Admin user: {admin.username} ({admin.email})")
    print(f"      Roles created: {roles}")

if '--demo' in sys.argv:
    print("\n[+ Demo Mode] Running full operational demo data seeding...")
    from seed_demo_data import run_seed
    run_seed()
    
print("\n" + "=" * 60)
print("  Setup complete!")
print("  Default credentials:")
print("    Username: admin")
print("    Password: AdminPassword2026!")
print("\n  IMPORTANT: Change the password after first login!")
print("=" * 60)
print("\nStart the application with: python run.py")


