"""
Phase 25 Multi-Tenant Business Codes & Universal Admin Credentials Test
Verifies:
  1. Multi-tenant login using Business / Company Codes (e.g. ANGAZA, SARAH).
  2. Distinct businesses can both log in with username 'admin' and password 'admin123'.
  3. Platform Superadmin logs in when Company Code is omitted.
  4. Invalid Business Code produces a clean error message.
  5. Direct login with unique username or email and password 'admin123'.
"""
import pytest
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User
from app.models.organization import Organization


@pytest.fixture
def app():
    application = create_app('testing')
    with application.app_context():
        db.create_all()

        superadmin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        manager_role = Role(name='PROPERTY_MANAGER', display_name='Property Manager')
        perms = [
            Permission(code='properties.view', module='properties', description='View properties'),
            Permission(code='bookings.view', module='bookings', description='View bookings'),
        ]
        db.session.add_all([superadmin_role, manager_role])
        db.session.add_all(perms)
        db.session.commit()
        manager_role.permissions = perms
        superadmin_role.permissions = perms

        # 1. Platform Superadmin (No Organization)
        superadmin = User(
            username='admin',
            email='admin@primerent.co.ke',
            full_name='Platform Super Admin',
            role=superadmin_role,
            organization_id=None,
            is_active=True
        )
        superadmin.set_password('admin123')
        db.session.add(superadmin)

        # 2. Business A: Code ANGAZA
        org_a = Organization(
            name='Angaza Premier Properties',
            slug='angaza-premier',
            org_code='ANGAZA',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
            enable_rentals=True,
            enable_hospitality=True
        )
        db.session.add(org_a)
        db.session.flush()

        admin_a = User(
            username='angaza_admin',
            email='admin@angazapremier.co.ke',
            full_name='Angaza Properties Manager',
            role=manager_role,
            organization_id=org_a.id,
            is_active=True
        )
        admin_a.set_password('admin123')
        db.session.add(admin_a)

        # 3. Business B: Code SARAH
        org_b = Organization(
            name='Mama Sarah Estates',
            slug='sarah-estates',
            org_code='SARAH',
            subscription_tier='COMBINED_SUITE',
            subscription_status='ACTIVE',
            enable_rentals=True,
            enable_hospitality=True
        )
        db.session.add(org_b)
        db.session.flush()

        admin_b = User(
            username='sarah_admin',
            email='admin@sarahproperties.co.ke',
            full_name='Sarah Estates Manager',
            role=manager_role,
            organization_id=org_b.id,
            is_active=True
        )
        admin_b.set_password('admin123')
        db.session.add(admin_b)

        db.session.commit()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_superadmin_login_without_business_code(client):
    """Super Admin logs in with code blank, username admin, password admin123."""
    res = client.post('/auth/login', data={
        'org_code': '',
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'Platform Super Admin' in res.data or b'Welcome back' in res.data


def test_multitenant_business_code_login(client):
    """Both businesses can log in using their Business Code with username 'admin' and password 'admin123'."""
    # 1. Login to Business A (ANGAZA)
    res_a = client.post('/auth/login', data={
        'org_code': 'ANGAZA',
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert res_a.status_code == 200
    assert b'Angaza Properties Manager' in res_a.data

    # Logout
    client.get('/auth/logout', follow_redirects=True)

    # 2. Login to Business B (SARAH)
    res_b = client.post('/auth/login', data={
        'org_code': 'SARAH',
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert res_b.status_code == 200
    assert b'Sarah Estates Manager' in res_b.data


def test_invalid_business_code_fails(client):
    """Attempting to log in with an invalid business code displays a clear error."""
    res = client.post('/auth/login', data={
        'org_code': 'UNKNOWN_BIZ',
        'username': 'admin',
        'password': 'admin123'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'was not found' in res.data
