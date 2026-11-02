import os
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, RolePermission, User
from app.services.personalization_service import PersonalizationService

ROLES_PERMISSIONS = {
    'SUPERADMIN': {
        'display_name': 'Super Administrator',
        'description': 'Full access to all system configurations, properties, and users.',
        'permissions': ['*']  # Wildcard
    },
    'PROPERTY_MANAGER': {
        'display_name': 'Property Manager',
        'description': 'Manages assigned properties, units, tenants, bookings, and operations.',
        'permissions': [
            'properties.view', 'properties.manage',
            'units.view', 'units.manage',
            'tenants.view', 'tenants.manage',
            'bookings.view', 'bookings.manage',
            'leases.view', 'leases.manage',
            'billing.view', 'billing.manage',
            'maintenance.view', 'maintenance.manage',
            'reports.view', 'reports.export'
        ]
    },
    'LANDLORD': {
        'display_name': 'Property Owner / Landlord',
        'description': 'Owner with access to their properties, income reports, and expenses.',
        'permissions': [
            'properties.view',
            'units.view',
            'tenants.view',
            'leases.view',
            'billing.view',
            'maintenance.view',
            'reports.view', 'reports.export'
        ]
    },
    'ACCOUNTANT': {
        'display_name': 'Accountant',
        'description': 'Financial operations: payments, invoices, reconciliation, and audit reports.',
        'permissions': [
            'properties.view',
            'units.view',
            'tenants.view',
            'billing.view', 'billing.manage',
            'mpesa.manage',
            'banking.manage',
            'reports.view', 'reports.export'
        ]
    },
    'CARETAKER': {
        'display_name': 'Caretaker',
        'description': 'On-site officer: visual occupancy inspection and maintenance logging.',
        'permissions': [
            'properties.view',
            'units.view',
            'maintenance.view', 'maintenance.manage'
        ]
    },
    'RECEPTIONIST': {
        'display_name': 'Receptionist',
        'description': 'Front office: handles enquiries, house reservations, and visitors.',
        'permissions': [
            'properties.view',
            'units.view',
            'tenants.view',
            'bookings.view', 'bookings.manage'
        ]
    },
    'TENANT': {
        'display_name': 'Tenant',
        'description': 'Tenant self-service portal: view lease, receipts, and log maintenance.',
        'permissions': [
            'portal.view'
        ]
    }
}

PERMISSIONS_CATALOG = [
    ('properties.view', 'properties', 'View property listings'),
    ('properties.manage', 'properties', 'Create, update, or remove properties'),
    ('units.view', 'units', 'View rental units and occupancy grid'),
    ('units.manage', 'units', 'Add, modify, or change status of rental units'),
    ('tenants.view', 'tenants', 'View tenant profiles and history'),
    ('tenants.manage', 'tenants', 'Register, update, or offboard tenants'),
    ('bookings.view', 'bookings', 'View house reservations'),
    ('bookings.manage', 'bookings', 'Create, convert, or cancel reservations'),
    ('leases.view', 'leases', 'View rental agreements and contracts'),
    ('leases.manage', 'leases', 'Draft, renew, or terminate leases'),
    ('billing.view', 'billing', 'View rent invoices, charges, and payment records'),
    ('billing.manage', 'billing', 'Record payments, issue invoices, apply late fees, reversals'),
    ('mpesa.manage', 'fintech', 'Configure and verify M-Pesa gateways and callbacks'),
    ('banking.manage', 'fintech', 'Upload bank statements and perform reconciliation'),
    ('maintenance.view', 'maintenance', 'View maintenance requests and tickets'),
    ('maintenance.manage', 'maintenance', 'Assign work orders, update status, and record expenses'),
    ('reports.view', 'reports', 'View financial, occupancy, and collection reports'),
    ('reports.export', 'reports', 'Download reports as PDF and Excel spreadsheets'),
    ('users.manage', 'admin', 'Manage user accounts, roles, and permissions'),
    ('settings.manage', 'admin', 'Personalize company branding, currency, and system settings'),
    ('portal.view', 'tenant_portal', 'Access tenant portal dashboard and statements')
]

def seed_database():
    app = create_app('development')
    with app.app_context():
        print("Ensuring tables are created...")
        db.create_all()
        
        print("Seeding permissions...")
        perm_map = {}
        for code, module, desc in PERMISSIONS_CATALOG:
            perm = Permission.query.filter_by(code=code).first()
            if not perm:
                perm = Permission(code=code, module=module, description=desc)
                db.session.add(perm)
                db.session.flush()
            perm_map[code] = perm
            
        print("Seeding roles and mapping permissions...")
        role_map = {}
        for role_name, data in ROLES_PERMISSIONS.items():
            role = Role.query.filter_by(name=role_name).first()
            if not role:
                role = Role(name=role_name, display_name=data['display_name'], description=data['description'])
                db.session.add(role)
                db.session.flush()
            role_map[role_name] = role
            
            # Associate permissions
            target_perms = []
            if '*' in data['permissions']:
                target_perms = list(perm_map.values())
            else:
                target_perms = [perm_map[p] for p in data['permissions'] if p in perm_map]
            role.permissions = target_perms

        print("Initializing system personalization settings...")
        PersonalizationService.initialize_default_settings()
        
        print("Seeding default Super Administrator user...")
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@primerent.co.ke',
                phone='+254700000000',
                full_name='Super Administrator',
                role=role_map['SUPERADMIN'],
                is_active=True
            )
            admin.set_password('AdminPassword2026!')
            db.session.add(admin)
            print("Default admin created: username='admin', password='AdminPassword2026!'")
        else:
            print("Admin user already exists.")

        db.session.commit()
        print("Database seeding completed successfully!")

if __name__ == '__main__':
    seed_database()

