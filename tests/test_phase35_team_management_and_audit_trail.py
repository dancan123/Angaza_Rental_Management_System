"""
Phase 35: Team User Management & Audit Trail — Multi-Tenant Isolation Tests
Tests:
  1. Property Manager can create a subordinate user (staff/caretaker/receptionist) in their own org
  2. Property Manager CANNOT create a SUPERADMIN or equal/higher-level user
  3. Audit log captures organization_id of acting user
  4. Audit trail page (/audit-logs/) is scoped to current org — Org A cannot see Org B logs
  5. Super Admin sees audit logs
"""
import random
import pytest
from app import create_app, db as _db
from app.models.user import User, Role
from app.models.organization import Organization
from app.models.system import AuditLog
from app.services.audit_service import AuditService


@pytest.fixture(scope='module')
def app():
    application = create_app()
    application.config['TESTING'] = True
    application.config['WTF_CSRF_ENABLED'] = False
    return application


@pytest.fixture(scope='module')
def client(app):
    return app.test_client()


@pytest.fixture(scope='module')
def setup_data(app):
    """Create two orgs, a manager per org, and a superadmin."""
    r = random.randint(100000, 999999)
    with app.app_context():
        superadmin_role = Role.query.filter_by(name='SUPERADMIN').first()
        manager_role = Role.query.filter_by(name='PROPERTY_MANAGER').first()
        subordinate_role = Role.query.filter(Role.name.in_(['RECEPTIONIST', 'CARETAKER', 'STAFF', 'ACCOUNTANT'])).first()
        
        # Ensure subordinate role exists
        if not subordinate_role:
            subordinate_role = Role(name='CARETAKER', display_name='Field Caretaker', is_system=True)
            _db.session.add(subordinate_role)
            _db.session.flush()

        # Orgs
        org_a = Organization(
            name=f'Alpha Estate {r}', slug=f'alpha-test35-{r}',
            org_code=Organization.generate_unique_org_code(),
            subscription_status='ACTIVE'
        )
        org_b = Organization(
            name=f'Beta Estate {r}', slug=f'beta-test35-{r}',
            org_code=Organization.generate_unique_org_code(),
            subscription_status='ACTIVE'
        )
        _db.session.add_all([org_a, org_b])
        _db.session.flush()

        # Dedicated test Superadmin with known password
        sa = User(username=f'sa_{r}', email=f'sa_{r}@test.local', full_name='Super Admin 35',
                  role=superadmin_role, is_active=True)
        sa.set_password('Pass123!')
        _db.session.add(sa)
        _db.session.flush()

        mgr_a = User(username=f'mgra_{r}', email=f'mgra_{r}@test.local', full_name=f'Manager A {r}',
                     role=manager_role, organization_id=org_a.id, is_active=True)
        mgr_a.set_password('Pass123!')

        mgr_b = User(username=f'mgrb_{r}', email=f'mgrb_{r}@test.local', full_name=f'Manager B {r}',
                     role=manager_role, organization_id=org_b.id, is_active=True)
        mgr_b.set_password('Pass123!')

        _db.session.add_all([mgr_a, mgr_b])
        _db.session.commit()

        return {
            'r': r,
            'org_a_id': org_a.id, 'org_b_id': org_b.id,
            'sa_username': sa.username, 'mgr_a_username': mgr_a.username, 'mgr_b_username': mgr_b.username,
            'mgr_a_id': mgr_a.id, 'mgr_b_id': mgr_b.id,
            'subordinate_role_id': subordinate_role.id,
            'manager_role_id': manager_role.id,
            'superadmin_role_id': superadmin_role.id,
        }


def login(client, username, password='Pass123!'):
    return client.post('/auth/login', data={'username': username, 'password': password},
                       follow_redirects=True)


def logout(client):
    return client.get('/auth/logout', follow_redirects=True)


# 1. Manager can create subordinate user in their own org
def test_manager_can_create_subordinate_in_own_org(client, setup_data, app):
    r = setup_data['r']
    with app.app_context():
        login(client, setup_data['mgr_a_username'])
        new_username = f'agent_{r}'
        rv = client.post('/users/create', data={
            'username': new_username,
            'email': f'{new_username}@test.local',
            'full_name': f'Team Agent {r}',
            'phone': '+254700000035',
            'role_id': setup_data['subordinate_role_id'],
            'password': 'Pass123!secure',
        }, follow_redirects=True)
        assert rv.status_code == 200

        new_user = User.query.filter_by(username=new_username).first()
        assert new_user is not None, 'User was not created'
        assert new_user.organization_id == setup_data['org_a_id'], 'User must belong to Org A'
        logout(client)


# 2. Manager CANNOT create a SUPERADMIN
def test_manager_cannot_create_superadmin(client, setup_data, app):
    r = setup_data['r']
    with app.app_context():
        login(client, setup_data['mgr_a_username'])
        count_before = User.query.filter_by(role_id=setup_data['superadmin_role_id']).count()
        rv = client.post('/users/create', data={
            'username': f'fake_sa_{r}',
            'email': f'fakesa_{r}@test.local',
            'full_name': 'Fake SuperAdmin',
            'phone': '+254700000099',
            'role_id': setup_data['superadmin_role_id'],
            'password': 'Pass123!secure',
        }, follow_redirects=True)
        count_after = User.query.filter_by(role_id=setup_data['superadmin_role_id']).count()
        assert count_after == count_before, 'Manager must not be able to create a SUPERADMIN'
        logout(client)


# 3. AuditService captures organization_id from current_user
def test_audit_service_captures_org_id(app, setup_data):
    r = setup_data['r']
    test_entity_id = f"unit_test_{r}"
    with app.app_context():
        with app.test_request_context('/test'):
            from flask_login import login_user
            mgr_a = _db.session.get(User, setup_data['mgr_a_id'])
            login_user(mgr_a)

            AuditService.log('ALLOCATION', 'Tenant', test_entity_id,
                             description='Allocated unit test',
                             new_values={'unit': 'RNG-001'})

            log = AuditLog.query.filter_by(entity_type='Tenant', entity_id=test_entity_id).first()
            assert log is not None, 'Audit log was not recorded'
            assert log.organization_id == setup_data['org_a_id'], \
                f'Expected org_id={setup_data["org_a_id"]}, got {log.organization_id}'
            assert log.user_id == setup_data['mgr_a_id']


# 4. Org A manager cannot see Org B audit logs on /audit-logs/
def test_audit_trail_scoped_to_org(client, setup_data, app):
    r = setup_data['r']
    with app.app_context():
        # Create a log belonging to Org B
        unique_secret = f'Org_B_secret_action_{r}'
        log_b = AuditLog(
            organization_id=setup_data['org_b_id'],
            user_id=setup_data['mgr_b_id'],
            action='CREATE',
            entity_type='Property',
            entity_id=str(r),
            description=unique_secret,
        )
        _db.session.add(log_b)
        _db.session.commit()

        login(client, setup_data['mgr_a_username'])
        rv = client.get('/audit-logs/', follow_redirects=True)
        assert rv.status_code == 200
        assert unique_secret.encode('utf-8') not in rv.data, \
            'Org A manager must NOT see Org B audit entries'
        logout(client)


# 5. Super Admin sees audit logs page successfully
def test_superadmin_sees_audit_logs_page(client, setup_data, app):
    with app.app_context():
        login(client, setup_data['sa_username'])
        rv = client.get('/audit-logs/', follow_redirects=True)
        assert rv.status_code == 200
        assert b'Audit' in rv.data or b'Activity' in rv.data
        logout(client)
