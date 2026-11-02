
import pytest
from app import create_app
from app.extensions import db
from app.models.user import Role, Permission, User
from app.services.personalization_service import PersonalizationService

@pytest.fixture
def app():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        # Seed basic roles
        admin_role = Role(name='SUPERADMIN', display_name='Super Admin')
        caretaker_role = Role(name='CARETAKER', display_name='Caretaker')
        perm_users = Permission(code='users.manage', module='admin', description='Manage users')
        perm_settings = Permission(code='settings.manage', module='admin', description='Manage settings')
        db.session.add_all([admin_role, caretaker_role, perm_users, perm_settings])
        db.session.commit()

        # Seed admin user
        admin = User(
            username='admin_test',
            email='admin@test.com',
            full_name='Test Admin',
            role=admin_role,
            is_active=True
        )
        admin.set_password('AdminPass123!')

        caretaker = User(
            username='caretaker_test',
            email='caretaker@test.com',
            full_name='Test Caretaker',
            role=caretaker_role,
            is_active=True
        )
        caretaker.set_password('Caretaker123!')

        db.session.add_all([admin, caretaker])
        PersonalizationService.initialize_default_settings()
        db.session.commit()

        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

def test_login_flow(client, app):
    # Test GET login page
    res = client.get('/auth/login')
    assert res.status_code == 200
    assert b'Sign In to Dashboard' in res.data

    # Test POST invalid credentials
    res = client.post('/auth/login', data={'username': 'admin_test', 'password': 'WrongPassword'}, follow_redirects=True)
    assert b'Invalid username/email or password.' in res.data

    # Test POST valid credentials
    res = client.post('/auth/login', data={'username': 'admin_test', 'password': 'AdminPass123!'}, follow_redirects=True)
    assert res.status_code == 200
    assert b'Welcome back, Test Admin!' in res.data
    assert b'Executive Dashboard' in res.data

    # Test Logout
    res = client.get('/auth/logout', follow_redirects=True)
    assert b'You have been securely logged out.' in res.data

def test_access_control_and_permissions(client, app):
    # Login as caretaker (no settings.manage permission)
    client.post('/auth/login', data={'username': 'caretaker_test', 'password': 'Caretaker123!'}, follow_redirects=True)
    
    # Try accessing settings -> should be 403 Forbidden
    res = client.get('/settings/')
    assert res.status_code == 403

    # Logout and login as admin -> should be 200 OK
    client.get('/auth/logout')
    client.post('/auth/login', data={'username': 'admin_test', 'password': 'AdminPass123!'}, follow_redirects=True)
    res = client.get('/settings/')
    assert res.status_code == 200
    assert b'System Personalization & Configuration' in res.data

def test_update_settings_flow(client, app):
    client.post('/auth/login', data={'username': 'admin_test', 'password': 'AdminPass123!'}, follow_redirects=True)
    
    # Update general settings
    res = client.post('/settings/general', data={
        'app_name': 'Horizon Prime Management',
        'business_name': 'Horizon Properties Kenya Ltd',
        'business_address': 'Westlands, Nairobi',
        'business_phone': '+254711999888',
        'business_email': 'info@horizonproperties.co.ke',
        'landlord_name': 'David Kimani',
        'business_reg_no': 'CPR/2026/8888',
        'tax_pin': 'A009988776B'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b'General business settings updated successfully.' in res.data

    with app.app_context():
        assert PersonalizationService.get_setting('app_name') == 'Horizon Prime Management'
        assert PersonalizationService.get_setting('business_name') == 'Horizon Properties Kenya Ltd'

def test_user_creation_and_status_toggle(client, app):
    client.post('/auth/login', data={'username': 'admin_test', 'password': 'AdminPass123!'}, follow_redirects=True)
    
    with app.app_context():
        role = Role.query.filter_by(name='CARETAKER').first()
        role_id = role.id

    # Create new user
    res = client.post('/users/create', data={
        'username': 'john_new',
        'email': 'john@test.com',
        'full_name': 'John New',
        'phone': '+254700112233',
        'role_id': role_id,
        'password': 'Password2026!'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"John New" in res.data
    assert b"created successfully" in res.data

    with app.app_context():
        new_u = User.query.filter_by(username='john_new').first()
        assert new_u is not None
        assert new_u.is_active is True
        user_id = new_u.id

    # Toggle status to deactive
    res = client.post(f'/users/{user_id}/toggle-status', follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        u = User.query.get(user_id)
        assert u.is_active is False

def test_user_profile_and_password_change(client, app):
    client.post('/auth/login', data={'username': 'admin_test', 'password': 'AdminPass123!'}, follow_redirects=True)
    
    # Access profile
    res = client.get('/users/profile')
    assert res.status_code == 200
    assert b'My Profile' in res.data
    assert b'admin_test' in res.data

    # Try wrong current password
    res = client.post('/users/profile/change-password', data={
        'current_password': 'WrongPassword!',
        'new_password': 'BrandNewPassword2026!',
        'confirm_password': 'BrandNewPassword2026!'
    }, follow_redirects=True)
    assert b'Current password is incorrect.' in res.data

    # Successfully change password
    res = client.post('/users/profile/change-password', data={
        'current_password': 'AdminPass123!',
        'new_password': 'BrandNewPassword2026!',
        'confirm_password': 'BrandNewPassword2026!'
    }, follow_redirects=True)
    assert b'Your password has been updated successfully.' in res.data

    # Verify new password can login
    client.get('/auth/logout')
    res = client.post('/auth/login', data={'username': 'admin_test', 'password': 'BrandNewPassword2026!'}, follow_redirects=True)
    assert res.status_code == 200
    assert b'Welcome back' in res.data

