from functools import wraps
from flask import abort, flash, redirect, url_for, request
from flask_login import current_user

def permission_required(permission_code):
    """
    Decorator to restrict view access based on user role permissions.
    Superadmin bypasses all checks.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login', next=request.path))
            if not current_user.has_permission(permission_code):
                flash('You do not have permission to access this resource.', 'danger')
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def role_required(*role_names):
    """
    Decorator to restrict view access to specific roles.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login', next=request.path))
            if current_user.role.name not in role_names and not current_user.is_superadmin():
                flash('Access restricted to authorized personnel.', 'danger')
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def subscription_required(module_name):
    """
    Decorator to enforce modular SaaS subscription entitlements:
    'rental' -> Organization must have RENTAL_STANDARD, COMBINED_SUITE, or ENTERPRISE
    'hospitality' -> Organization must have HOSPITALITY_STANDARD, COMBINED_SUITE, or ENTERPRISE
    Platform Superadmin bypasses all subscription restrictions.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login', next=request.path))
            if current_user.is_superadmin():
                return f(*args, **kwargs)

            org = getattr(current_user, 'active_organization', None)
            if org:
                if module_name == 'rental' and not org.can_access_rental_module():
                    flash('Your organization subscription does not include the Rental Property Management module. Please upgrade your plan to access this feature.', 'warning')
                    return redirect(url_for('hospitality.index'))
                elif module_name == 'hospitality' and not org.can_access_hospitality_module():
                    flash('Your organization subscription does not include the Hospitality & Short-Stay module. Please upgrade your plan to access this feature.', 'warning')
                    return redirect(url_for('dashboard.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator

def landlord_scoped(query, model):
    """
    Utility helper that scopes an SQLAlchemy query to the current user's assigned landlords,
    unless the current user is a Superadmin or global Property Manager.
    """
    if current_user.is_superadmin():
        return query
    if hasattr(current_user, 'landlords') and current_user.landlords:
        landlord_ids = [l.id for l in current_user.landlords]
        if hasattr(model, 'landlord_id'):
            return query.filter(model.landlord_id.in_(landlord_ids))
        elif hasattr(model, 'property') and hasattr(model.property.property.entity.class_, 'landlord_id'):
            return query.join(model.property).filter(model.property.property.entity.class_.landlord_id.in_(landlord_ids))
    return query

