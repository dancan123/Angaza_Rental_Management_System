from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.extensions import db
from app.models.user import User, Role, Landlord
from app.utils.decorators import permission_required
from app.services.audit_service import AuditService

users_bp = Blueprint('users', __name__, url_prefix='/users')

@users_bp.route('/')
@login_required
@permission_required('users.manage')
def index():
    users = User.query.order_by(User.created_at.desc()).all()
    roles = Role.query.all()
    landlords = Landlord.query.filter_by(is_active=True).all()
    return render_template('users/index.html', users=users, roles=roles, landlords=landlords)

@users_bp.route('/create', methods=['POST'])
@login_required
@permission_required('users.manage')
def create_user():
    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip().lower()
    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    role_id = request.form.get('role_id', type=int)
    password = request.form.get('password', '')
    landlord_id = request.form.get('landlord_id', type=int)

    if not username or not email or not password or not role_id:
        flash('Username, email, password, and role are required fields.', 'danger')
        return redirect(url_for('users.index'))

    if User.query.filter((User.username == username) | (User.email == email)).first():
        flash('A user with that username or email already exists.', 'danger')
        return redirect(url_for('users.index'))

    role = db.session.get(Role, role_id)
    if not role:
        flash('Invalid role selected.', 'danger')
        return redirect(url_for('users.index'))

    new_user = User(
        username=username,
        email=email,
        full_name=full_name,
        phone=phone,
        role=role,
        is_active=True
    )
    new_user.set_password(password)

    if landlord_id:
        landlord = db.session.get(Landlord, landlord_id)
        if landlord:
            new_user.landlords.append(landlord)

    db.session.add(new_user)
    db.session.commit()

    AuditService.log('CREATE', 'User', new_user.id, new_values={'username': username, 'role': role.name})
    flash(f"User '{full_name}' created successfully.", 'success')
    return redirect(url_for('users.index'))

@users_bp.route('/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('users.manage')
def toggle_status(user_id):
    user = User.query.get_or_404(user_id)
    if current_user.id == user_id:
        flash('You cannot deactivate your own account.', 'warning')
        return redirect(url_for('users.index'))

    if not current_user.can_manage_user(user):
        flash(f"Access Denied: You do not have hierarchical authority to modify the account status for {user.full_name} ({user.role.display_name if user.role else 'User'}).", 'danger')
        return redirect(url_for('users.index'))

    old_status = user.is_active
    user.is_active = not user.is_active
    db.session.commit()

    action = 'ACTIVATED' if user.is_active else 'DEACTIVATED'
    AuditService.log('UPDATE', 'User', user.id, old_values={'is_active': old_status}, new_values={'is_active': user.is_active})
    flash(f"User '{user.username}' has been {action}.", 'info')
    return redirect(url_for('users.index'))

@users_bp.route('/<int:user_id>/reset-password', methods=['POST'])
@login_required
@permission_required('users.manage')
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    if not current_user.can_reset_password_for(user):
        flash(f"Access Denied: You can only reset passwords for subordinate/junior accounts. Super Administrator and senior accounts are protected.", 'danger')
        return redirect(url_for('users.index'))

    new_password = request.form.get('new_password', '').strip()
    if not new_password or len(new_password) < 6:
        flash('Password must be at least 6 characters long.', 'danger')
        return redirect(url_for('users.index'))

    user.set_password(new_password)
    db.session.commit()

    AuditService.log('PASSWORD_RESET', 'User', user.id, new_values={'reset_by': current_user.username, 'target': user.username})
    flash(f"Password for '{user.username}' ({user.role.display_name if user.role else 'User'}) has been successfully reset.", 'success')
    return redirect(url_for('users.index'))

@users_bp.route('/roles/<int:role_id>/permissions', methods=['POST'])
@login_required
@permission_required('settings.manage')
def update_role_permissions(role_id):
    if not current_user.is_superadmin():
        flash('Only the Super Administrator has authority to modify the Role Access Matrix.', 'danger')
        return redirect(url_for('settings.index') + '#tab-rbac')

    role = db.session.get(Role, role_id)
    if not role:
        flash('Role not found.', 'danger')
        return redirect(url_for('settings.index') + '#tab-rbac')

    if role.name == 'SUPERADMIN':
        flash('The Super Administrator role maintains immutable paramount access across all system modules.', 'warning')
        return redirect(url_for('settings.index') + '#tab-rbac')

    from app.models.user import Permission
    permission_codes = request.form.getlist('permissions')
    selected_perms = Permission.query.filter(Permission.code.in_(permission_codes)).all()
    
    role.permissions = selected_perms
    db.session.commit()

    AuditService.log('UPDATE_ROLE_PERMS', 'Role', role.id, new_values={'role': role.name, 'permissions': permission_codes})
    flash(f"Access privileges for role '{role.display_name}' have been successfully updated.", 'success')
    return redirect(url_for('settings.index') + '#tab-rbac')

@users_bp.route('/profile')
@login_required
def profile():
    return render_template('users/profile.html')

@users_bp.route('/profile/change-password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not current_user.check_password(current_password):
        flash('Current password is incorrect.', 'danger')
        return redirect(url_for('users.profile'))

    if not new_password or len(new_password) < 8:
        flash('New password must be at least 8 characters long.', 'danger')
        return redirect(url_for('users.profile'))

    if new_password != confirm_password:
        flash('New password and confirmation do not match.', 'danger')
        return redirect(url_for('users.profile'))

    current_user.set_password(new_password)
    db.session.commit()

    AuditService.log('PASSWORD_CHANGE', 'User', current_user.id)
    flash('Your password has been updated successfully.', 'success')
    return redirect(url_for('users.profile'))


