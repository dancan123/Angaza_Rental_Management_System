from datetime import datetime, date
from typing import Any, cast
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models.property import RentalUnit, Property
from app.models.hospitality import Guest, HospitalityReservation, HousekeepingTask
from app.models.user import User
from app.services.hospitality_service import HospitalityService
from app.services.audit_service import AuditService
from app.utils.decorators import permission_required
from app.utils.currency import to_cents

hospitality_bp = Blueprint('hospitality', __name__, url_prefix='/hospitality')

@hospitality_bp.route('/')
@login_required
@permission_required('bookings.view')
def index():
    """
    Dedicated Module B Dashboard:
    ADR, RevPAR, Occupancy %, Today's Arrivals & Departures, Room Status Board.
    """
    from app.utils.decorators import multi_tenant_scoped
    from app.utils.currency import format_currency
    user = cast(Any, current_user)
    org_id = user.organization_id if not user.is_superadmin() else None
    landlord_ids = [l.id for l in user.landlords] if (not user.is_superadmin() and hasattr(user, 'landlords') and user.landlords) else None

    kpis = HospitalityService.get_hospitality_dashboard_kpis(organization_id=org_id, landlord_id=landlord_ids)
    today = date.today()

    # Upcoming arrivals & departures scoped
    arrivals_q = HospitalityReservation.query.filter(
        HospitalityReservation.check_in_date == today,
        HospitalityReservation.status == 'CONFIRMED'
    )
    arrivals = multi_tenant_scoped(arrivals_q, HospitalityReservation).order_by(HospitalityReservation.id.asc()).all()

    departures_q = HospitalityReservation.query.filter(
        HospitalityReservation.check_out_date == today,
        HospitalityReservation.status == 'CHECKED_IN'
    )
    departures = multi_tenant_scoped(departures_q, HospitalityReservation).order_by(HospitalityReservation.id.asc()).all()

    in_house_q = HospitalityReservation.query.filter_by(status='CHECKED_IN')
    in_house = multi_tenant_scoped(in_house_q, HospitalityReservation).order_by(HospitalityReservation.check_out_date.asc()).all()

    # Room status grid - short-stay rooms
    rooms_q = RentalUnit.query.filter_by(operational_type='SHORT_STAY')
    rooms = multi_tenant_scoped(rooms_q, RentalUnit).order_by(RentalUnit.unit_number.asc()).all()

    # Enriched room management overview scoped to org and landlord
    overview = HospitalityService.get_rooms_management_overview(organization_id=org_id, landlord_id=landlord_ids)
    decorated_rooms = overview.get('rooms', [])

    # Count booked/vacant for SHORT_STAY rooms
    booked_count = sum(1 for r in decorated_rooms if r['is_occupied'] and r['unit'].operational_type == 'SHORT_STAY')
    vacant_count = sum(1 for r in decorated_rooms if not r['is_occupied'] and r['unit'].operational_type == 'SHORT_STAY')

    # Today's collections: sum paid_amount_cents for reservations updated today (scoped)
    today_midnight = datetime.combine(date.today(), datetime.min.time())
    today_reservations_q = HospitalityReservation.query.filter(
        HospitalityReservation.updated_at >= today_midnight
    )
    today_reservations = multi_tenant_scoped(today_reservations_q, HospitalityReservation).all()
    today_collections_cents = sum(r.paid_amount_cents or 0 for r in today_reservations)
    today_collections_display = format_currency(today_collections_cents)

    # Filter to SHORT_STAY only for the Airbnb board
    decorated_rooms = [r for r in decorated_rooms if r['unit'].operational_type == 'SHORT_STAY']
    total_all_time_income_cents = sum(r['total_collected_cents'] for r in decorated_rooms)
    total_all_time_income_display = format_currency(total_all_time_income_cents)

    # Sort decorated_rooms
    sort_by = request.args.get('sort', 'name')
    if sort_by == 'income_desc':
        decorated_rooms = sorted(decorated_rooms, key=lambda r: r['total_collected_cents'], reverse=True)
    elif sort_by == 'income_asc':
        decorated_rooms = sorted(decorated_rooms, key=lambda r: r['total_collected_cents'])
    else:
        decorated_rooms = sorted(decorated_rooms, key=lambda r: r['unit'].unit_number)

    # Group rooms by House / Property for PMS hierarchical view
    houses_dict = {}
    for r in decorated_rooms:
        prop = r['unit'].property
        prop_id = prop.id if prop else 0
        prop_name = prop.name if prop else 'Standalone Airbnb Suites'
        prop_loc = prop.location if prop else 'Prime Location'
        if prop_id not in houses_dict:
            houses_dict[prop_id] = {
                'property': prop,
                'name': prop_name,
                'location': prop_loc,
                'rooms': [],
                'total_rooms': 0,
                'occupied_rooms': 0,
                'vacant_rooms': 0,
                'dirty_rooms': 0,
                'total_collected_cents': 0,
                'total_daily_potential_cents': 0
            }
        houses_dict[prop_id]['rooms'].append(r)
        houses_dict[prop_id]['total_rooms'] += 1
        if r['is_occupied']:
            houses_dict[prop_id]['occupied_rooms'] += 1
        elif r['unit'].cleaning_status == 'DIRTY':
            houses_dict[prop_id]['dirty_rooms'] += 1
        else:
            houses_dict[prop_id]['vacant_rooms'] += 1
        houses_dict[prop_id]['total_collected_cents'] += r['total_collected_cents']
        houses_dict[prop_id]['total_daily_potential_cents'] += (r['unit'].daily_rate_cents or 0)

    for h in houses_dict.values():
        h['occupancy_pct'] = round((h['occupied_rooms'] / max(1, h['total_rooms'])) * 100, 1)
        h['total_collected_display'] = format_currency(h['total_collected_cents'])
        h['total_daily_potential_display'] = format_currency(h['total_daily_potential_cents'])

    houses = list(houses_dict.values())

    # Properties for new booking modal (scoped)
    properties = multi_tenant_scoped(Property.query.filter_by(management_status='ACTIVE'), Property).all()

    # Available short-stay units with no active reservation
    active_unit_ids = {r['unit'].id for r in decorated_rooms if r['is_occupied']}
    available_units = [
        r['unit'] for r in decorated_rooms
        if r['unit'].operational_type == 'SHORT_STAY' and r['unit'].id not in active_unit_ids
    ]

    return render_template(
        'hospitality/index.html',
        kpis=kpis,
        arrivals=arrivals,
        departures=departures,
        in_house=in_house,
        rooms=rooms,
        decorated_rooms=decorated_rooms,
        houses=houses,
        booked_count=booked_count,
        vacant_count=vacant_count,
        today_collections_cents=today_collections_cents,
        today_collections_display=today_collections_display,
        sort_by=sort_by,
        total_all_time_income_cents=total_all_time_income_cents,
        total_all_time_income_display=total_all_time_income_display,
        properties=properties,
        available_units=available_units,
        today=today
    )

@hospitality_bp.route('/reservations')
@login_required
@permission_required('bookings.view')
def reservations():
    status = request.args.get('status')
    source = request.args.get('source')
    search = request.args.get('q', '').strip()

    query = HospitalityReservation.query.join(Guest).join(RentalUnit)

    if status:
        query = query.filter(HospitalityReservation.status == status)
    if source:
        query = query.filter(HospitalityReservation.booking_source == source)
    if search:
        query = query.filter(
            (Guest.first_name.ilike(f"%{search}%")) |
            (Guest.last_name.ilike(f"%{search}%")) |
            (Guest.phone.ilike(f"%{search}%")) |
            (RentalUnit.unit_number.ilike(f"%{search}%")) |
            (HospitalityReservation.reservation_code.ilike(f"%{search}%"))
        )

    all_reservations = query.order_by(HospitalityReservation.check_in_date.desc(), HospitalityReservation.id.desc()).all()
    properties = Property.query.filter_by(management_status='ACTIVE').all()
    available_units = RentalUnit.query.filter(RentalUnit.current_tenant_id.is_(None)).all()

    return render_template(
        'hospitality/reservations.html',
        reservations=all_reservations,
        properties=properties,
        available_units=available_units,
        status_filter=status,
        source_filter=source,
        search=search
    )

@hospitality_bp.route('/reservations/create', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def create_reservation():
    user = cast(Any, current_user)
    try:
        unit_id = request.form.get('rental_unit_id', type=int)
        check_in = datetime.strptime(request.form.get('check_in_date', ''), '%Y-%m-%d').date()
        check_out = datetime.strptime(request.form.get('check_out_date', ''), '%Y-%m-%d').date()
        num_guests = request.form.get('num_guests', type=int) or 1
        daily_rate = float(request.form.get('daily_rate', 0)) if request.form.get('daily_rate') else None
        source = request.form.get('booking_source', 'DIRECT')
        notes = request.form.get('special_requests', '').strip()

        guest_data = {
            'first_name': request.form.get('first_name', '').strip(),
            'last_name': request.form.get('last_name', '').strip(),
            'phone': request.form.get('phone', '').strip(),
            'email': request.form.get('email', '').strip(),
            'id_passport_number': request.form.get('id_passport_number', '').strip(),
            'nationality': request.form.get('nationality', 'Kenyan').strip(),
            'emergency_contact': request.form.get('emergency_contact', '').strip(),
            'emergency_phone': request.form.get('emergency_phone', '').strip()
        }

        if not guest_data['first_name'] or not guest_data['phone']:
            flash('Guest name and phone number are required.', 'danger')
            return redirect(url_for('hospitality.reservations'))

        res = HospitalityService.create_reservation(
            unit_id=unit_id,
            guest_data=guest_data,
            check_in_date=check_in,
            check_out_date=check_out,
            num_guests=num_guests,
            daily_rate=daily_rate,
            booking_source=source,
            special_requests=notes,
            user_id=user.id
        )

        flash(f"Hospitality reservation {res.reservation_code} confirmed for {res.guest.full_name}!", 'success')
    except Exception as e:
        flash(f"Booking Error: {str(e)}", 'danger')

    return redirect(url_for('hospitality.reservations'))

@hospitality_bp.route('/reservations/<int:res_id>/check-in', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def check_in(res_id):
    user = cast(Any, current_user)
    try:
        res = HospitalityService.check_in_reservation(res_id, user_id=user.id)
        flash(f"Guest {res.guest.full_name} successfully checked into Unit {res.rental_unit.unit_number}.", 'success')
    except Exception as e:
        flash(f"Check-In Error: {str(e)}", 'danger')

    return redirect(request.referrer or url_for('hospitality.index'))

@hospitality_bp.route('/reservations/<int:res_id>/check-out', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def check_out(res_id):
    user = cast(Any, current_user)
    try:
        paid_amount = float(request.form.get('payment_amount', 0)) if request.form.get('payment_amount') else None
        method = request.form.get('payment_method', 'MPESA')
        ref = request.form.get('payment_reference', '').strip()

        res = HospitalityService.check_out_reservation(
            reservation_id=res_id,
            paid_amount=paid_amount,
            payment_method=method,
            payment_ref=ref,
            user_id=user.id
        )
        flash(f"Guest {res.guest.full_name} checked out. Room {res.rental_unit.unit_number} flagged for turnover cleaning.", 'success')
    except Exception as e:
        flash(f"Check-Out Error: {str(e)}", 'danger')

    return redirect(request.referrer or url_for('hospitality.index'))

@hospitality_bp.route('/reservations/<int:res_id>/cancel', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def cancel_reservation(res_id):
    user = cast(Any, current_user)
    reason = request.form.get('cancellation_reason', '').strip()
    try:
        res = HospitalityService.cancel_reservation(res_id, reason=reason, user_id=user.id)
        flash(f"Reservation {res.reservation_code} has been cancelled.", 'info')
    except Exception as e:
        flash(f"Cancellation Error: {str(e)}", 'danger')

    return redirect(url_for('hospitality.reservations'))


@hospitality_bp.route('/reservations/<int:res_id>/record-payment', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def record_payment(res_id):
    res = db.session.get(HospitalityReservation, res_id)
    if not res:
        from flask import abort; abort(404)

    amount = float(request.form.get('amount', 0))
    method = request.form.get('payment_method', 'CASH')
    ref = request.form.get('payment_reference', '').strip()

    if amount <= 0:
        flash('Payment amount must be greater than zero.', 'danger')
        return redirect(url_for('hospitality.index'))

    res.paid_amount_cents += to_cents(amount)
    res.payment_method = method
    res.payment_reference = ref
    db.session.commit()

    AuditService.log('RECORD_RESERVATION_PAYMENT', 'HospitalityReservation', res.id,
                     new_values={'amount': amount, 'method': method})
    flash(f"Payment of KES {amount:,.0f} recorded for {res.guest.full_name} (Res: {res.reservation_code}).", 'success')
    return redirect(url_for('hospitality.index'))


@hospitality_bp.route('/reservations/<int:res_id>/receipt')
@login_required
@permission_required('bookings.view')
def view_receipt(res_id):
    res = db.session.get(HospitalityReservation, res_id)
    if not res:
        from flask import abort; abort(404)
    return render_template('hospitality/receipt.html', res=res)


@hospitality_bp.route('/housekeeping')
@login_required
@permission_required('maintenance.view')
def housekeeping():
    rooms = RentalUnit.query.order_by(RentalUnit.unit_number.asc()).all()
    tasks = HousekeepingTask.query.order_by(HousekeepingTask.scheduled_date.desc(), HousekeepingTask.id.desc()).all()
    staff = User.query.filter_by(is_active=True).all()

    return render_template(
        'hospitality/housekeeping.html',
        rooms=rooms,
        tasks=tasks,
        staff=staff
    )

@hospitality_bp.route('/housekeeping/status', methods=['POST'])
@login_required
@permission_required('maintenance.manage')
def update_cleaning_status():
    user = cast(Any, current_user)
    unit_id = request.form.get('unit_id', type=int)
    new_status = request.form.get('cleaning_status', 'CLEAN')
    try:
        unit = HospitalityService.update_cleaning_status(unit_id, new_status, user_id=user.id)
        flash(f"Unit {unit.unit_number} cleaning status updated to {new_status}.", 'success')
    except Exception as e:
        flash(f"Error: {str(e)}", 'danger')

    return redirect(url_for('hospitality.housekeeping'))

@hospitality_bp.route('/housekeeping/tasks/create', methods=['POST'])
@login_required
@permission_required('maintenance.manage')
def create_housekeeping_task():
    try:
        unit_id = request.form.get('rental_unit_id', type=int)
        assigned_user_id = request.form.get('assigned_user_id', type=int)
        task_type = request.form.get('task_type', 'TURNOVER_CLEAN')
        priority = request.form.get('priority', 'NORMAL')
        notes = request.form.get('notes', '').strip()

        task = HousekeepingTask(
            rental_unit_id=unit_id,
            assigned_user_id=assigned_user_id if assigned_user_id else None,
            task_type=task_type,
            priority=priority,
            status='PENDING',
            notes=notes
        )
        db.session.add(task)
        db.session.commit()
        flash('Housekeeping task created and assigned successfully.', 'success')
    except Exception as e:
        flash(f"Error creating task: {str(e)}", 'danger')

    return redirect(url_for('hospitality.housekeeping'))

@hospitality_bp.route('/housekeeping/tasks/<int:task_id>/complete', methods=['POST'])
@login_required
@permission_required('maintenance.manage')
def complete_housekeeping_task(task_id):
    task = db.session.get(HousekeepingTask, task_id)
    if not task:
        from flask import abort; abort(404)

    task.status = 'COMPLETED'
    task.completed_at = datetime.utcnow()
    # Auto-update room cleaning status to CLEAN
    task.rental_unit.cleaning_status = 'CLEAN'
    db.session.commit()

    flash(f"Housekeeping task marked complete. Unit {task.rental_unit.unit_number} is now CLEAN & ready for guests.", 'success')
    return redirect(url_for('hospitality.housekeeping'))

@hospitality_bp.route('/rooms')
@login_required
@permission_required('properties.manage')
def rooms():
    user = cast(Any, current_user)
    org_id = user.organization_id if not user.is_superadmin() else None
    data = HospitalityService.get_rooms_management_overview(organization_id=org_id)
    return render_template(
        'hospitality/rooms.html',
        rooms=data['rooms'],
        properties=data['properties'],
        stats=data['stats']
    )

@hospitality_bp.route('/rooms/create', methods=['POST'])
@login_required
@permission_required('properties.manage')
def create_room():
    property_id = request.form.get('property_id', type=int)
    unit_number = request.form.get('unit_number', '').strip()
    unit_type = request.form.get('unit_type', 'Studio').strip()
    daily_rate = float(request.form.get('daily_rate', 0) or 0)
    monthly_rent = float(request.form.get('monthly_rent', 0) or 0)
    max_guests = request.form.get('max_guests', type=int) or 2
    cleaning_status = request.form.get('cleaning_status', 'CLEAN')
    description = request.form.get('description', '').strip()

    if not property_id:
        flash("Please select a property for this room.", "danger")
        return redirect(url_for('hospitality.rooms'))

    if not unit_number:
        flash("Room / Suite name is required.", "danger")
        return redirect(url_for('hospitality.rooms'))

    if daily_rate <= 0:
        flash("A valid nightly/daily rate is required for short-stay units.", "danger")
        return redirect(url_for('hospitality.rooms'))

    # Check for duplicate unit name within the same property
    existing = RentalUnit.query.filter_by(property_id=property_id, unit_number=unit_number).first()
    if existing:
        flash(f"A room named '{unit_number}' already exists in this property.", "danger")
        return redirect(url_for('hospitality.rooms'))

    # Multi-tenant quota check
    user = cast(Any, current_user)
    if user.active_organization and not user.is_superadmin():
        org = user.active_organization
        current_unit_count = RentalUnit.query.join(Property).filter(Property.organization_id == org.id).count()
        if not org.is_within_unit_limit(current_unit_count):
            flash(f"Unit limit reached ({current_unit_count}/{org.max_units}). Please upgrade your subscription tier.", "danger")
            return redirect(url_for('hospitality.rooms'))

    unit = RentalUnit(
        property_id=property_id,
        unit_number=unit_number,
        unit_type=unit_type,
        operational_type='SHORT_STAY',
        daily_rate_cents=to_cents(daily_rate),
        rent_amount_cents=to_cents(monthly_rent) if monthly_rent > 0 else to_cents(daily_rate * 30),
        max_guests=max_guests,
        cleaning_status=cleaning_status,
        occupancy_status='VACANT',
        description=description
    )
    db.session.add(unit)
    db.session.commit()

    flash(f"Short-Stay Room '{unit.unit_number}' successfully created and added to inventory!", "success")
    return redirect(url_for('hospitality.rooms'))

@hospitality_bp.route('/rooms/<int:unit_id>/update', methods=['POST'])
@login_required
@permission_required('properties.manage')
def update_room_config(unit_id):
    unit = db.session.get(RentalUnit, unit_id)
    if not unit:
        from flask import abort; abort(404)

    # Allow custom room renaming
    new_unit_number = request.form.get('unit_number', '').strip()
    if new_unit_number:
        unit.unit_number = new_unit_number

    unit_type = request.form.get('unit_type', '').strip()
    if unit_type:
        unit.unit_type = unit_type

    op_type = request.form.get('operational_type', 'LONG_TERM')
    daily_rate = float(request.form.get('daily_rate', 0) or 0)
    monthly_rent = float(request.form.get('monthly_rent', 0) or 0)
    max_guests = request.form.get('max_guests', type=int) or 2
    cleaning_status = request.form.get('cleaning_status', 'CLEAN')
    description = request.form.get('description', '').strip()

    unit.operational_type = op_type
    unit.daily_rate_cents = to_cents(daily_rate)
    if monthly_rent > 0:
        unit.rent_amount_cents = to_cents(monthly_rent)
    unit.max_guests = max_guests
    unit.cleaning_status = cleaning_status
    if description:
        unit.description = description
    db.session.commit()

    flash(f"Room '{unit.unit_number}' configuration updated successfully ({op_type}).", 'success')
    return redirect(url_for('hospitality.rooms'))

@hospitality_bp.route('/rooms/<int:unit_id>/toggle-cleaning', methods=['POST'])
@login_required
@permission_required('properties.manage')
def toggle_room_cleaning(unit_id):
    unit = db.session.get(RentalUnit, unit_id)
    if not unit:
        from flask import abort; abort(404)
    target = 'DIRTY' if unit.cleaning_status == 'CLEAN' else 'CLEAN'
    user = cast(Any, current_user)
    HospitalityService.update_cleaning_status(unit.id, target, user_id=user.id)
    flash(f"Room '{unit.unit_number}' cleaning status updated to {target}.", 'success')
    return redirect(request.referrer or url_for('hospitality.rooms'))

@hospitality_bp.route('/rooms/<int:unit_id>/send-sms', methods=['POST'])
@login_required
@permission_required('properties.manage')
def send_room_sms(unit_id):
    unit = db.session.get(RentalUnit, unit_id)
    if not unit:
        from flask import abort; abort(404)

    phone = request.form.get('phone', '').strip()
    message = request.form.get('message', '').strip()
    if not phone or not message:
        flash("Phone number and message are required to send SMS.", "warning")
        return redirect(request.referrer or url_for('hospitality.rooms'))

    from app.services.sms_service import SmsService
    org_id = unit.property.organization_id if unit.property else None
    res = SmsService.send_sms(
        to_phone=phone,
        message=message,
        notification_type='ROOM_COMMUNICATION',
        organization_id=org_id
    )
    if res.get('success'):
        flash(f"SMS successfully sent to {phone} for Room '{unit.unit_number}'.", "success")
    else:
        flash(f"SMS dispatch failed: {res.get('error')}", "danger")
    return redirect(request.referrer or url_for('hospitality.rooms'))

@hospitality_bp.route('/rooms/<int:unit_id>/walk-out', methods=['POST'])
@login_required
@permission_required('properties.manage')
def record_walk_out(unit_id):
    user = cast(Any, current_user)
    unit = HospitalityService.record_guest_walkout(unit_id, user_id=user.id)
    flash(f"Guest walk-out recorded for Room '{unit.unit_number}'. Room is now VACANT and automatically flagged as DIRTY for turnover housekeeping.", "warning")
    return redirect(request.referrer or url_for('hospitality.rooms'))


# ─── Seasonal / Pricing Rules ────────────────────────────────────────────────

@hospitality_bp.route('/pricing')
@login_required
@permission_required('properties.manage')
def pricing_rules():
    """Seasonal and event-based pricing rules management."""
    from app.models.pricing import RoomPricingRule
    rules = RoomPricingRule.query.order_by(RoomPricingRule.start_date.desc()).all()
    units = RentalUnit.query.order_by(RentalUnit.unit_number.asc()).all()
    return render_template('hospitality/pricing.html', rules=rules, units=units)


@hospitality_bp.route('/pricing/create', methods=['POST'])
@login_required
@permission_required('properties.manage')
def create_pricing_rule():
    from app.models.pricing import RoomPricingRule
    from datetime import date as _date

    name = request.form.get('name', '').strip()
    unit_id = request.form.get('rental_unit_id', type=int) or None
    start_str = request.form.get('start_date', '')
    end_str = request.form.get('end_date', '')
    rule_type = request.form.get('rule_type', 'MULTIPLIER')
    multiplier = float(request.form.get('multiplier', 1.0))
    flat_rate = float(request.form.get('flat_rate', 0))
    days_of_week = request.form.get('days_of_week', '')
    category = request.form.get('category', 'CUSTOM')
    notes = request.form.get('notes', '').strip()

    if not name or not start_str or not end_str:
        flash('Rule name, start date and end date are required.', 'danger')
        return redirect(url_for('hospitality.pricing_rules'))

    try:
        start_date = _date.fromisoformat(start_str)
        end_date = _date.fromisoformat(end_str)
        if end_date < start_date:
            flash('End date must be after start date.', 'danger')
            return redirect(url_for('hospitality.pricing_rules'))
    except ValueError:
        flash('Invalid date format.', 'danger')
        return redirect(url_for('hospitality.pricing_rules'))

    rule = RoomPricingRule(
        name=name,
        rental_unit_id=unit_id,
        start_date=start_date,
        end_date=end_date,
        rule_type=rule_type,
        multiplier=multiplier,
        flat_rate_cents=to_cents(flat_rate),
        days_of_week=days_of_week,
        category=category,
        notes=notes if notes else None
    )
    db.session.add(rule)
    db.session.commit()
    flash(f"Pricing rule '{name}' created for {start_date} → {end_date}.", 'success')
    return redirect(url_for('hospitality.pricing_rules'))


@hospitality_bp.route('/pricing/<int:rule_id>/toggle', methods=['POST'])
@login_required
@permission_required('properties.manage')
def toggle_pricing_rule(rule_id):
    from app.models.pricing import RoomPricingRule
    rule = db.session.get(RoomPricingRule, rule_id)
    if not rule:
        from flask import abort; abort(404)
    rule.is_active = not rule.is_active
    db.session.commit()
    status_txt = 'activated' if rule.is_active else 'deactivated'
    flash(f"Pricing rule '{rule.name}' {status_txt}.", 'success')
    return redirect(url_for('hospitality.pricing_rules'))


@hospitality_bp.route('/pricing/<int:rule_id>/delete', methods=['POST'])
@login_required
@permission_required('properties.manage')
def delete_pricing_rule(rule_id):
    from app.models.pricing import RoomPricingRule
    rule = db.session.get(RoomPricingRule, rule_id)
    if not rule:
        from flask import abort; abort(404)
    db.session.delete(rule)
    db.session.commit()
    flash(f"Pricing rule '{rule.name}' deleted.", 'success')
    return redirect(url_for('hospitality.pricing_rules'))


# ─── Booking Calendar View ───────────────────────────────────────────────────

@hospitality_bp.route('/calendar')
@login_required
@permission_required('bookings.view')
def calendar():
    """Visual booking availability calendar — 30-day rolling view with functional buttons."""
    from datetime import date as _date, timedelta
    from app.utils.decorators import multi_tenant_scoped
    today = _date.today()
    start_date = _date.fromisoformat(request.args.get('start', today.isoformat()))
    days_range = 30
    end_date = start_date + timedelta(days=days_range - 1)
    view_filter = request.args.get('filter', 'shortstay')  # 'shortstay' (default) or 'all'

    # Filter rooms: by default, show SHORT_STAY (Airbnb) rooms so long-term units don't clutter the calendar
    base_rooms_q = RentalUnit.query
    if view_filter != 'all':
        base_rooms_q = base_rooms_q.filter_by(operational_type='SHORT_STAY')
    rooms = multi_tenant_scoped(base_rooms_q, RentalUnit).order_by(RentalUnit.unit_number.asc()).all()

    # Total counts for filter pill toggles
    short_stay_count = multi_tenant_scoped(RentalUnit.query.filter_by(operational_type='SHORT_STAY'), RentalUnit).count()
    all_units_count = multi_tenant_scoped(RentalUnit.query, RentalUnit).count()

    # Fetch reservations in range
    res_q = HospitalityReservation.query.filter(
        HospitalityReservation.check_in_date <= end_date,
        HospitalityReservation.check_out_date >= start_date,
        HospitalityReservation.status.in_(['CONFIRMED', 'CHECKED_IN', 'CHECKED_OUT'])
    )
    reservations = multi_tenant_scoped(res_q, HospitalityReservation).all()

    # Build a lookup: (unit_id, date_str) -> reservation
    cal_map = {}
    distinct_reservations = {}
    for res in reservations:
        distinct_reservations[res.id] = res
        d = res.check_in_date
        while d < res.check_out_date:
            if start_date <= d <= end_date:
                cal_map[(res.rental_unit_id, d.isoformat())] = res
            d = d + timedelta(days=1)

    calendar_days = [start_date + timedelta(days=i) for i in range(days_range)]
    prev_start = start_date - timedelta(days=15)
    next_start = start_date + timedelta(days=15)

    return render_template(
        'hospitality/calendar.html',
        rooms=rooms,
        calendar_days=calendar_days,
        cal_map=cal_map,
        distinct_reservations=list(distinct_reservations.values()),
        start_date=start_date,
        end_date=end_date,
        prev_start=prev_start,
        next_start=next_start,
        today=today,
        days_range=days_range,
        view_filter=view_filter,
        short_stay_count=short_stay_count,
        all_units_count=all_units_count
    )
