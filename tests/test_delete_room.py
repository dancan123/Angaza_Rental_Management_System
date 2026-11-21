import pytest
from app import create_app, db
from app.models.property import Property, RentalUnit
from app.models.hospitality import HousekeepingTask, HospitalityReservation
from app.models.user import User

@pytest.fixture
def client():
    app = create_app('testing')
    with app.app_context():
        db.create_all()
        from app.models.user import Role
        # Ensure superadmin role & user
        role = Role.query.filter_by(name='SUPERADMIN').first()
        if not role:
            role = Role(name='SUPERADMIN', display_name='Super Administrator', description='Super Administrator')
            db.session.add(role)
            db.session.flush()

        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', email='admin@test.com', full_name='Admin', role_id=role.id)
            admin.set_password('admin123')
            admin.is_active = True
            db.session.add(admin)
            db.session.commit()

        from app.models.user import Landlord
        # Ensure landlord
        landlord = Landlord.query.first()
        if not landlord:
            landlord = Landlord(name="Test Landlord", email="landlord@test.com", phone="+254700000000")
            db.session.add(landlord)
            db.session.flush()

        # Create test property & room
        prop = Property(name="Test Resort", location="Diani", ref_number="PROP-TEST-DEL", landlord_id=landlord.id)
        db.session.add(prop)
        db.session.flush()

        room = RentalUnit(
            property_id=prop.id,
            unit_number="Villa 99 — Test Suite",
            operational_type='SHORT_STAY',
            cleaning_status='CLEAN',
            occupancy_status='VACANT'
        )
        db.session.add(room)
        db.session.flush()

        task = HousekeepingTask(rental_unit_id=room.id, status='PENDING')
        db.session.add(task)
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(admin.id)
                sess['_fresh'] = True
            yield client

def test_delete_room_success(client):
    room = RentalUnit.query.filter_by(unit_number="Villa 99 — Test Suite").first()
    assert room is not None
    room_id = room.id

    resp = client.post(f'/hospitality/rooms/{room_id}/delete', follow_redirects=True)
    assert resp.status_code == 200

    deleted_room = db.session.get(RentalUnit, room_id)
    assert deleted_room is None

    # Housekeeping tasks also cleaned up
    remaining_tasks = HousekeepingTask.query.filter_by(rental_unit_id=room_id).count()
    assert remaining_tasks == 0

def test_delete_room_blocked_for_manager_if_occupied(client):
    from app.models.user import Role
    prop = Property.query.first()
    
    # Create non-superadmin manager
    mgr_role = Role.query.filter_by(name='PROPERTY_MANAGER').first()
    if not mgr_role:
        mgr_role = Role(name='PROPERTY_MANAGER', display_name='Property Manager', description='Manager')
        db.session.add(mgr_role)
        db.session.flush()

    manager = User(username='test_mgr_100', email='mgr100@test.com', full_name='Mgr', role_id=mgr_role.id, organization_id=prop.organization_id or 1)
    manager.set_password('pass123')
    db.session.add(manager)

    occupied_room = RentalUnit(
        property_id=prop.id,
        unit_number="Villa 100 — Occupied",
        operational_type='SHORT_STAY',
        cleaning_status='CLEAN',
        occupancy_status='OCCUPIED'
    )
    db.session.add(occupied_room)
    db.session.commit()

    # Log in as manager
    with client.session_transaction() as sess:
        sess['_user_id'] = str(manager.id)
        sess['_fresh'] = True

    resp = client.post(f'/hospitality/rooms/{occupied_room.id}/delete', follow_redirects=True)
    assert resp.status_code == 200
    assert b"Cannot delete room" in resp.data

    still_exists = db.session.get(RentalUnit, occupied_room.id)
    assert still_exists is not None
