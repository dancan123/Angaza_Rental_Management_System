from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models.property import Property, RentalUnit
from app.models.utility import Meter
from app.services.utility_service import UtilityService
from app.services.personalization_service import PersonalizationService
from app.utils.decorators import permission_required

utilities_bp = Blueprint('utilities', __name__, url_prefix='/utilities')

@utilities_bp.route('/')
@login_required
@permission_required('properties.manage')
def index():
    property_id = request.args.get('property_id', type=int)
    meter_type = request.args.get('type')
    
    properties = Property.query.filter_by(management_status='ACTIVE').all()
    meters = UtilityService.get_property_meters(property_id=property_id)
    if meter_type:
        meters = [m for m in meters if m.meter_type == meter_type]
        
    recent_readings = UtilityService.get_recent_readings(limit=40, property_id=property_id)
    currency = PersonalizationService.get_setting('currency', 'KES')
    
    return render_template(
        'utilities/index.html',
        properties=properties,
        meters=meters,
        readings=recent_readings,
        selected_property=property_id,
        selected_type=meter_type,
        currency=currency
    )

@utilities_bp.route('/meters/create', methods=['POST'])
@login_required
@permission_required('properties.manage')
def create_meter():
    property_id = request.form.get('property_id', type=int)
    unit_id = request.form.get('rental_unit_id', type=int)
    meter_number = request.form.get('meter_number', '').strip()
    meter_type = request.form.get('meter_type', 'WATER')
    rate = request.form.get('rate_per_unit', 150.0, type=float)
    initial = request.form.get('initial_reading', 0.0, type=float)
    
    if not unit_id or not meter_number:
        flash('Rental unit and meter number are required.', 'danger')
        return redirect(url_for('utilities.index'))
        
    try:
        meter = UtilityService.register_meter(
            property_id=property_id,
            rental_unit_id=unit_id,
            meter_number=meter_number,
            meter_type=meter_type,
            rate_per_unit=rate,
            initial_reading=initial
        )
        flash(f"Meter {meter.meter_number} ({meter.meter_type}) registered successfully for unit.", 'success')
    except Exception as e:
        flash(f"Error registering meter: {str(e)}", 'danger')
        
    return redirect(url_for('utilities.index', property_id=property_id))

@utilities_bp.route('/readings/record', methods=['POST'])
@login_required
def record_reading():
    meter_id = request.form.get('meter_id', type=int)
    reading_val = request.form.get('current_reading', type=float)
    reading_date_str = request.form.get('reading_date')
    auto_bill = request.form.get('auto_bill', '1') == '1'
    
    if not meter_id or reading_val is None:
        flash('Meter and current reading value are required.', 'danger')
        return redirect(url_for('utilities.index'))
        
    reading_date = datetime.strptime(reading_date_str, '%Y-%m-%d').date() if reading_date_str else date.today()
    
    try:
        user_id = getattr(current_user, 'id', None)
        reading = UtilityService.record_reading(
            meter_id=meter_id,
            current_reading=reading_val,
            reading_date=reading_date,
            recorded_by_id=user_id,
            auto_bill=auto_bill
        )
        bill_msg = f" Bill generated: {reading.cost_display}" if reading.billed_status == 'BILLED' else ""
        flash(f"Reading recorded successfully! Consumed: {reading.units_consumed} units.{bill_msg}", 'success')
    except ValueError as ve:
        flash(str(ve), 'warning')
    except Exception as e:
        flash(f"Failed to record reading: {str(e)}", 'danger')
        
    next_url = request.form.get('next_url')
    return redirect(next_url or url_for('utilities.index'))

@utilities_bp.route('/caretaker-entry')
@login_required
def caretaker_entry():
    """
    Mobile-optimized view for Caretakers & Field Officers walking door-to-door
    """
    property_id = request.args.get('property_id', type=int)
    properties = Property.query.filter_by(management_status='ACTIVE').all()
    
    selected_prop = db.session.get(Property, property_id) if property_id else (properties[0] if properties else None)
    
    meters = []
    if selected_prop:
        meters = Meter.query.filter_by(property_id=selected_prop.id, is_active=True).join(RentalUnit).order_by(RentalUnit.unit_number.asc()).all()
        
    currency = PersonalizationService.get_setting('currency', 'KES')
    
    return render_template(
        'utilities/caretaker_entry.html',
        properties=properties,
        selected_property=selected_prop,
        meters=meters,
        currency=currency,
        today=date.today()
    )

