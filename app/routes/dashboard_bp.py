from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models.property import Property, Building, RentalUnit
from app.models.tenant import Tenant
from app.models.finance import RentCharge, Payment
from app.models.maintenance import Expense
from app.models.communication import Notification
from app.utils.currency import format_currency
from datetime import datetime

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@dashboard_bp.route('/dashboard')
@login_required
def index():
    now = datetime.utcnow()
    current_month = now.month
    current_year = now.year
    
    # Query high-level stats
    # Filter by landlord if user is scoped
    properties_query = Property.query
    if not current_user.is_superadmin() and current_user.landlords:
        landlord_ids = [l.id for l in current_user.landlords]
        properties_query = properties_query.filter(Property.landlord_id.in_(landlord_ids))
        
    total_properties = properties_query.count()
    property_ids = [p.id for p in properties_query.all()]
    
    units_query = RentalUnit.query.filter(RentalUnit.property_id.in_(property_ids)) if property_ids else RentalUnit.query.filter_by(id=-1)
    
    total_units = units_query.count()
    occupied_units = units_query.filter_by(occupancy_status='OCCUPIED').count()
    vacant_units = units_query.filter_by(occupancy_status='VACANT').count()
    reserved_units = units_query.filter_by(occupancy_status='RESERVED').count()
    maintenance_units = units_query.filter_by(occupancy_status='MAINTENANCE').count()
    
    total_buildings = Building.query.filter(Building.property_id.in_(property_ids)).count() if property_ids else 0
    total_tenants = Tenant.query.filter_by(is_active=True).count()
    
    # Financial metrics for current month
    charges = RentCharge.query.filter(
        RentCharge.period_month == current_month,
        RentCharge.period_year == current_year
    ).all()
    
    expected_rent_cents = sum(c.amount_cents for c in charges)
    rent_collected_cents = sum(c.amount_paid_cents for c in charges)
    outstanding_rent_cents = sum(c.balance_cents for c in charges)
    
    collection_rate = (rent_collected_cents / expected_rent_cents * 100) if expected_rent_cents > 0 else 0
    
    # Total expenses this month
    expenses = Expense.query.filter(
        Expense.property_id.in_(property_ids) if property_ids else Expense.id == -1
    ).all()
    total_expenses_cents = sum(e.amount_cents for e in expenses)
    net_income_cents = rent_collected_cents - total_expenses_cents
    
    # Recent activities (Payments, Maintenance, Notifications)
    recent_payments = Payment.query.order_by(Payment.created_at.desc()).limit(5).all()
    recent_notifications = Notification.query.order_by(Notification.created_at.desc()).limit(5).all()
    
    stats = {
        'total_properties': total_properties,
        'total_buildings': total_buildings,
        'total_units': total_units,
        'occupied_units': occupied_units,
        'vacant_units': vacant_units,
        'reserved_units': reserved_units,
        'maintenance_units': maintenance_units,
        'total_tenants': total_tenants,
        'expected_rent': format_currency(expected_rent_cents),
        'rent_collected': format_currency(rent_collected_cents),
        'outstanding_rent': format_currency(outstanding_rent_cents),
        'collection_rate': round(collection_rate, 1),
        'total_expenses': format_currency(total_expenses_cents),
        'net_income': format_currency(net_income_cents),
        'raw': {
            'occupied': occupied_units,
            'vacant': vacant_units,
            'reserved': reserved_units,
            'maintenance': maintenance_units,
            'collected_cents': rent_collected_cents,
            'outstanding_cents': outstanding_rent_cents,
            'expenses_cents': total_expenses_cents
        }
    }
    
    return render_template(
        'dashboard/index.html',
        stats=stats,
        recent_payments=recent_payments,
        recent_notifications=recent_notifications
    )

