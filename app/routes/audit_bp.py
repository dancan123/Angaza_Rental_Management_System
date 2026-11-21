"""
Audit Trail Blueprint — /audit-logs/
Every organisation sees only its own logs; Super Admin sees all with org-filter.
"""
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models.system import AuditLog
from app.models.user import User
from app.utils.decorators import permission_required

audit_bp = Blueprint('audit', __name__, url_prefix='/audit-logs')

# Action labels for the UI
ACTION_LABELS = {
    'CREATE':          ('success', 'bi-plus-circle-fill',  'Created'),
    'UPDATE':          ('primary', 'bi-pencil-fill',        'Updated'),
    'DELETE':          ('danger',  'bi-trash-fill',         'Deleted'),
    'ACTIVATED':       ('success', 'bi-person-check-fill',  'Activated'),
    'DEACTIVATED':     ('warning', 'bi-person-x-fill',      'Deactivated'),
    'PASSWORD_RESET':  ('warning', 'bi-key-fill',           'Password Reset'),
    'PASSWORD_RESET_REQUEST': ('info', 'bi-envelope-exclamation', 'Password Reset Requested'),
    'ACCOUNT_ACTIVATION':     ('success', 'bi-envelope-check-fill', 'Account Activated via Email'),
    'PASSWORD_CHANGE': ('secondary','bi-shield-lock-fill',  'Password Changed'),
    'LOGIN':           ('info',    'bi-box-arrow-in-right', 'Logged In'),
    'LOGOUT':          ('secondary','bi-box-arrow-left',    'Logged Out'),
    'ALLOCATION':      ('success', 'bi-house-door-fill',    'Unit Allocated'),
    'MOVE_OUT':        ('danger',  'bi-box-arrow-right',    'Move-Out'),
    'TRANSFER':        ('info',    'bi-arrows-move',        'Unit Transfer'),
    'RECEIVE_PAYMENT': ('success', 'bi-cash-stack',         'Payment Received'),
    'REVERSAL':        ('danger',  'bi-arrow-counterclockwise','Reversal'),
    'PUBLISH':         ('success', 'bi-broadcast',          'Published'),
    'UNPUBLISH':       ('warning', 'bi-broadcast-pin',      'Unpublished'),
    'ONBOARD':         ('primary', 'bi-building-add',       'Onboarded'),
    'UPDATE_ROLE_PERMS':('warning','bi-shield-shaded',      'Role Permissions Updated'),
}


@audit_bp.route('/')
@login_required
@permission_required('settings.view')
def index():
    page      = request.args.get('page', 1, type=int)
    per_page  = 50
    action_f  = request.args.get('action', '').strip().upper()
    entity_f  = request.args.get('entity', '').strip()
    user_f    = request.args.get('user_id', type=int)
    search_f  = request.args.get('search', '').strip()

    # Base query — always scoped to org (superadmin sees all)
    q = AuditLog.query
    if not current_user.is_superadmin():
        q = q.filter_by(organization_id=current_user.organization_id)
    elif request.args.get('org_id'):
        q = q.filter_by(organization_id=request.args.get('org_id', type=int))

    if action_f:
        q = q.filter(AuditLog.action == action_f)
    if entity_f:
        q = q.filter(AuditLog.entity_type.ilike(f'%{entity_f}%'))
    if user_f:
        q = q.filter(AuditLog.user_id == user_f)
    if search_f:
        q = q.filter(
            db.or_(
                AuditLog.description.ilike(f'%{search_f}%'),
                AuditLog.entity_type.ilike(f'%{search_f}%'),
                AuditLog.entity_id.ilike(f'%{search_f}%'),
            )
        )

    logs = q.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    # Distinct actions in this org for the filter dropdown
    distinct_actions_q = db.session.query(AuditLog.action).distinct()
    if not current_user.is_superadmin():
        distinct_actions_q = distinct_actions_q.filter(AuditLog.organization_id == current_user.organization_id)
    distinct_actions = sorted([row[0] for row in distinct_actions_q.all()])

    # Users in org for filter dropdown
    if current_user.is_superadmin():
        team_users = User.query.order_by(User.full_name).all()
    else:
        team_users = User.query.filter_by(organization_id=current_user.organization_id).order_by(User.full_name).all()

    return render_template(
        'audit/index.html',
        logs=logs,
        action_labels=ACTION_LABELS,
        distinct_actions=distinct_actions,
        team_users=team_users,
        filters={'action': action_f, 'entity': entity_f, 'user_id': user_f, 'search': search_f},
    )
