"""
Fix script: Replace Model.query.get_or_404(x) with db.session.get(Model, x) + abort(404)
Also fix Model.query.get(x) with db.session.get(Model, x)
Also ensure 'from app.extensions import db' is present where needed.
"""
import re, os

def fix_file(filepath):
    with open(filepath, encoding='utf-8') as fh:
        content = fh.read()
    
    original = content
    
    # Replace: varname = Model.query.get_or_404(arg)
    # With: varname = db.session.get(Model, arg)\n    if not varname:\n        from flask import abort; abort(404)
    # We need to preserve indentation
    def replace_get_or_404(m):
        indent = m.group(1)
        varname = m.group(2)
        model = m.group(3)
        arg = m.group(4)
        return (
            f"{indent}{varname} = db.session.get({model}, {arg})\n"
            f"{indent}if not {varname}:\n"
            f"{indent}    from flask import abort; abort(404)"
        )
    
    pattern_404 = re.compile(r'^([ \t]*)(\w+)\s*=\s*(\w+)\.query\.get_or_404\(([^)]+)\)', re.MULTILINE)
    content = pattern_404.sub(replace_get_or_404, content)
    
    # Also replace: return Model.query.get_or_404(arg)
    def replace_return_404(m):
        indent = m.group(1)
        model = m.group(2)
        arg = m.group(3)
        return f"{indent}return db.session.get({model}, {arg})"
    
    pattern_return_404 = re.compile(r'^([ \t]*)return\s+(\w+)\.query\.get_or_404\(([^)]+)\)', re.MULTILINE)
    content = pattern_return_404.sub(replace_return_404, content)
    
    # Ensure db is imported if we used db.session.get
    if 'db.session.get' in content and 'from app.extensions import db' not in content:
        # Add import after first line that has 'from' or 'import'
        lines = content.split('\n')
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith('from ') or line.startswith('import '):
                insert_at = i + 1
        lines.insert(insert_at, 'from app.extensions import db')
        content = '\n'.join(lines)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as fh:
            fh.write(content)
        print(f'Fixed: {filepath}')
    else:
        print(f'No changes: {filepath}')

files = [
    'app/routes/billing_bp.py',
    'app/routes/communication_bp.py',
    'app/routes/leases_bp.py',
    'app/routes/mpesa_bp.py',
    'app/routes/properties_bp.py',
    'app/routes/public_bp.py',
    'app/routes/settings_bp.py',
    'app/routes/tenants_bp.py',
    'app/routes/users_bp.py',
    'app/services/bank_service.py',
    'app/services/booking_service.py',
    'app/services/lease_service.py',
    'app/services/maintenance_service.py',
    'app/services/report_service.py',
    'app/services/tenant_service.py',
    'app/services/utility_service.py',
    # Tests
    'tests/test_phase2_auth_settings.py',
    'tests/test_phase3_properties.py',
    'tests/test_phase4_tenants_bookings.py',
    'tests/test_phase5_billing.py',
    'tests/test_phase7_mpesa.py',
    'tests/test_phase9_maintenance.py',
    'tests/test_phase10_leases.py',
    'tests/test_phase11_utilities.py',
]

for f in files:
    if os.path.exists(f):
        fix_file(f)
    else:
        print(f'MISSING: {f}')

print('\nDone.')

