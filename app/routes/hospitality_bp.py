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

    # Pending online reservations needing logistics / confirmation
    pending_online_q = HospitalityReservation.query.filter(
        HospitalityReservation.status == 'PENDING'
    )
    pending_online = multi_tenant_scoped(pending_online_q, HospitalityReservation).order_by(
        HospitalityReservation.check_in_date.asc(), HospitalityReservation.id.desc()
    ).all()

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
        overview_stats=overview.get('stats', {}),
        sort_by=sort_by,
        total_all_time_income_cents=total_all_time_income_cents,
        total_all_time_income_display=total_all_time_income_display,
        properties=properties,
        available_units=available_units,
        pending_online=pending_online,
        today=today
    )

@hospitality_bp.route('/reservations')
@login_required
@permission_required('bookings.view')
def reservations():
    user = cast(Any, current_user)
    org_id = user.organization_id if not user.is_superadmin() else None

    status = request.args.get('status')
    source = request.args.get('source')
    search = request.args.get('q', '').strip()

    query = HospitalityReservation.query.join(Guest).join(RentalUnit)
    if org_id:
        query = query.join(Property, RentalUnit.property_id == Property.id).filter(Property.organization_id == org_id)

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
    if org_id:
        properties = Property.query.filter_by(organization_id=org_id, management_status='ACTIVE').all()
        available_units = RentalUnit.query.join(Property).filter(
            Property.organization_id == org_id,
            RentalUnit.current_tenant_id.is_(None)
        ).all()
    else:
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

@hospitality_bp.route('/reservations/<int:res_id>/confirm', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def confirm_reservation(res_id):
    reservation = db.session.get(HospitalityReservation, res_id)
    if not reservation:
        flash('Reservation not found.', 'danger')
        return redirect(url_for('hospitality.reservations'))

    # Security check: multi-tenant isolation
    user = cast(Any, current_user)
    org_id = user.organization_id if not user.is_superadmin() else None
    if org_id and reservation.organization_id and reservation.organization_id != org_id:
        from flask import abort
        abort(403)

    reservation.status = 'CONFIRMED'
    db.session.commit()

    # Send confirmation SMS to guest
    guest = reservation.guest
    unit = reservation.rental_unit
    org = unit.property.organization if (unit and unit.property) else None
    first_name = guest.first_name if guest else 'Guest'
    check_in_str = reservation.check_in_date.strftime('%d/%m/%Y') if reservation.check_in_date else 'your arrival date'

    try:
        from app.services.sms_service import SmsService
        sms_text = (
            f"Dear {first_name}, your booking for {unit.unit_number if unit else 'Room'} is CONFIRMED! "
            f"Ref: {reservation.reservation_code}. Check-In: {check_in_str}. "
            f"We look forward to hosting you at {org.name if org else 'our residence'}!"
        )
        SmsService.send_sms(
            to_phone=guest.phone,
            message=sms_text,
            notification_type='HOSPITALITY_RESERVATION',
            organization_id=org.id if org else None
        )
    except Exception:
        pass

    flash(f"Reservation #{reservation.reservation_code} for {guest.full_name if guest else 'Guest'} has been CONFIRMED. Confirmation SMS sent to {guest.phone if guest else ''}.", 'success')
    return redirect(request.referrer or url_for('hospitality.reservations'))

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

        # Initial payment record (Cash, M-Pesa, etc.)
        init_paid = float(request.form.get('paid_amount', 0) or 0)
        pay_method = request.form.get('payment_method', 'CASH').strip().upper()
        pay_ref = request.form.get('payment_reference', '').strip()
        if init_paid > 0:
            res.paid_amount_cents = to_cents(init_paid)
            res.payment_method = pay_method
            res.payment_reference = pay_ref or (f"CASH-{res.reservation_code}" if pay_method == 'CASH' else 'SETTLED')
            db.session.commit()

        # ── M-Pesa STK Push (optional) ──
        push_stk = request.form.get('push_stk') or (request.form.get('action') == 'book_and_stk')
        stk_result_msg = ''
        if push_stk:
            try:
                from app.models.gateway import PaymentGatewayConfig
                from app.services.mpesa_service import DarajaClient

                # Resolve org strictly from unit → property → organization (multi-tenant isolation)
                stk_unit = db.session.get(RentalUnit, unit_id)
                stk_org = stk_unit.property.organization if (stk_unit and stk_unit.property) else None
                stk_org_id = stk_org.id if stk_org else None

                cfg = None
                if stk_org_id:
                    cfg = PaymentGatewayConfig.query.filter_by(
                        organization_id=stk_org_id, is_active=True
                    ).first()

                if cfg and cfg.consumer_key and cfg.consumer_secret and cfg.shortcode and cfg.passkey:
                    guest_phone = guest_data.get('phone', '').strip()
                    total_amount = int(res.total_stay_cents / 100) if res.total_stay_cents else int(daily_rate or 0)
                    account_ref = res.reservation_code[:12]
                    client = DarajaClient(cfg)
                    stk_resp = client.initiate_stk_push(
                        phone_number=guest_phone,
                        amount=max(1, total_amount),
                        account_reference=account_ref,
                        transaction_desc='Airbnb Stay'
                    )
                    checkout_id = stk_resp.get('CheckoutRequestID', '')
                    if checkout_id:
                        res.payment_method = 'MPESA'
                        res.payment_reference = checkout_id
                        db.session.commit()
                        stk_result_msg = f' M-Pesa STK Push sent to {guest_phone} (Checkout ID: {checkout_id}).'
                    else:
                        err = stk_resp.get('errorMessage') or stk_resp.get('ResponseDescription', 'Daraja error')
                        stk_result_msg = f' STK Push attempted but got: {err}.'
                else:
                    org_name = stk_org.name if stk_org else 'this Organization'
                    stk_result_msg = (
                        f' M-Pesa STK Push skipped — no active M-Pesa gateway credentials configured for '
                        f'{org_name}. Set them under System Settings → Payment Gateways.'
                    )
            except Exception as stk_err:
                stk_result_msg = f' STK Push error: {str(stk_err)}'

        flash(f"Hospitality reservation {res.reservation_code} confirmed for {res.guest.full_name}!{stk_result_msg}", 'success')
    except Exception as e:
        flash(f"Booking Error: {str(e)}", 'danger')

    return redirect(url_for('hospitality.reservations'))


@hospitality_bp.route('/reservations/<int:res_id>/push-stk', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def push_stk_for_reservation(res_id):
    """
    Re-push M-Pesa STK prompt for an existing reservation from the dashboard/logistics modal.
    Multi-tenant: credentials are always resolved from the reservation's owning organization only.
    """
    res = db.session.get(HospitalityReservation, res_id)
    if not res:
        from flask import abort; abort(404)

    # Tenant isolation guard
    user = cast(Any, current_user)
    org_id = user.organization_id if not user.is_superadmin() else None
    if org_id and res.organization_id and res.organization_id != org_id:
        from flask import abort; abort(403)

    try:
        from app.models.gateway import PaymentGatewayConfig
        from app.services.mpesa_service import DarajaClient

        unit = res.rental_unit
        stk_org = unit.property.organization if (unit and unit.property) else None
        stk_org_id = stk_org.id if stk_org else res.organization_id

        cfg = None
        if stk_org_id:
            cfg = PaymentGatewayConfig.query.filter_by(
                organization_id=stk_org_id, is_active=True
            ).first()

        if not (cfg and cfg.consumer_key and cfg.consumer_secret and cfg.shortcode and cfg.passkey):
            org_name = stk_org.name if stk_org else 'this Organization'
            flash(
                f'M-Pesa STK Push failed — no active gateway credentials configured for {org_name}. '
                f'Go to System Settings → Payment Gateways to add them.',
                'warning'
            )
            return redirect(request.referrer or url_for('hospitality.index'))

        guest = res.guest
        guest_phone = guest.phone if guest else ''
        total_amount = int(res.total_stay_cents / 100) if res.total_stay_cents else 0
        # Allow partial / custom amount from form
        custom_amount = request.form.get('stk_amount', type=int)
        if custom_amount and custom_amount > 0:
            total_amount = custom_amount

        if not guest_phone or total_amount <= 0:
            flash('Guest phone number and a valid amount are required for STK Push.', 'danger')
            return redirect(request.referrer or url_for('hospitality.index'))

        account_ref = res.reservation_code[:12]
        client = DarajaClient(cfg)
        stk_resp = client.initiate_stk_push(
            phone_number=guest_phone,
            amount=total_amount,
            account_reference=account_ref,
            transaction_desc='Airbnb Stay'
        )
        checkout_id = stk_resp.get('CheckoutRequestID', '')
        if checkout_id:
            res.payment_method = 'MPESA'
            res.payment_reference = checkout_id
            db.session.commit()
            flash(
                f'M-Pesa STK Push sent to {guest_phone} for KES {total_amount:,} '
                f'(Ref: {res.reservation_code}). Checkout ID: {checkout_id}.',
                'success'
            )
        else:
            err = stk_resp.get('errorMessage') or stk_resp.get('ResponseDescription', 'Unknown error')
            flash(f'STK Push attempted but Safaricom responded: {err}', 'warning')

    except Exception as e:
        flash(f'STK Push error: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('hospitality.index'))


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

        # Auto-send thank you / departure settlement SMS
        if res.guest and res.guest.phone:
            from app.services.sms_service import SmsService
            prop_name = res.rental_unit.property.name if res.rental_unit and res.rental_unit.property else "Angaza Stays"
            paid_text = f" Settlement payment of KES {paid_amount:,.0f} via {method} ({ref or 'Settled'}) received." if (paid_amount and paid_amount > 0) else ""
            sms_msg = (
                f"Dear {res.guest.first_name}, thank you for staying with us at {prop_name} (Room {res.rental_unit.unit_number})."
                f"{paid_text} Your check-out has been completed. We wish you safe travels and hope to host you again soon!"
            )
            try:
                SmsService.send_sms(
                    to_phone=res.guest.phone,
                    message=sms_msg,
                    notification_type='CHECKOUT_THANK_YOU',
                    organization_id=res.organization_id
                )
            except Exception:
                pass

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


@hospitality_bp.route('/reservations/<int:res_id>/update', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def update_reservation(res_id):
    """
    Updates reservation details including guest information, dates, pricing,
    payment method (CASH, MPESA, BANK, CARD), payment reference, and status.
    """
    res = db.session.get(HospitalityReservation, res_id)
    if not res:
        from flask import abort; abort(404)

    try:
        # 1. Update Guest Details
        guest = res.guest
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        phone = request.form.get('phone', '').strip()
        if first_name: guest.first_name = first_name
        if last_name: guest.last_name = last_name
        if phone: guest.phone = phone
        guest.email = request.form.get('email', '').strip() or None
        guest.id_passport_number = request.form.get('id_passport_number', '').strip() or None
        guest.nationality = request.form.get('nationality', 'Kenyan').strip()

        # 2. Update Accommodation Unit
        unit_id = request.form.get('rental_unit_id', type=int)
        if unit_id and unit_id != res.rental_unit_id:
            res.rental_unit_id = unit_id

        # 3. Update Dates & Nights
        check_in_str = request.form.get('check_in_date', '').strip()
        check_out_str = request.form.get('check_out_date', '').strip()
        if check_in_str and check_out_str:
            new_check_in = datetime.strptime(check_in_str, '%Y-%m-%d').date()
            new_check_out = datetime.strptime(check_out_str, '%Y-%m-%d').date()
            if new_check_in >= new_check_out:
                flash('Check-out date must be strictly after check-in date.', 'danger')
                return redirect(request.referrer or url_for('hospitality.view_receipt', res_id=res.id))
            res.check_in_date = new_check_in
            res.check_out_date = new_check_out
            res.num_nights = max(1, (new_check_out - new_check_in).days)

        num_guests = request.form.get('num_guests', type=int)
        if num_guests:
            res.num_guests = num_guests

        daily_rate = request.form.get('daily_rate')
        if daily_rate is not None and daily_rate != '':
            res.daily_rate_cents = to_cents(float(daily_rate))

        # Recompute total charges
        res.total_stay_cents = res.daily_rate_cents * res.num_nights

        # 4. Payment Method & Reference (Accommodates Cash & M-Pesa)
        payment_method = request.form.get('payment_method', '').strip()
        if payment_method:
            res.payment_method = payment_method.upper()

        payment_ref = request.form.get('payment_reference', '').strip()
        if payment_ref:
            res.payment_reference = payment_ref
        elif res.payment_method == 'CASH' and not res.payment_reference:
            res.payment_reference = f"CASH-{res.reservation_code}"

        paid_amount = request.form.get('paid_amount')
        if paid_amount is not None and paid_amount != '':
            res.paid_amount_cents = to_cents(float(paid_amount))

        # 5. Status Management
        new_status = request.form.get('status', '').strip()
        if new_status and new_status in ('CONFIRMED', 'CHECKED_IN', 'CHECKED_OUT', 'CANCELLED'):
            res.status = new_status
            if new_status == 'CHECKED_IN':
                res.rental_unit.occupancy_status = 'OCCUPIED'
            elif new_status in ('CHECKED_OUT', 'CANCELLED'):
                res.rental_unit.occupancy_status = 'VACANT'

        # 6. Source and Special Requests
        source = request.form.get('booking_source', '').strip()
        if source:
            res.booking_source = source
        notes = request.form.get('special_requests', '').strip()
        if notes is not None:
            res.special_requests = notes

        db.session.commit()
        AuditService.log('UPDATE_RESERVATION', 'HospitalityReservation', res.id, new_values={'code': res.reservation_code})
        flash(f"Reservation {res.reservation_code} updated successfully.", 'success')
    except Exception as e:
        flash(f"Update Error: {str(e)}", 'danger')

    return redirect(request.referrer or url_for('hospitality.view_receipt', res_id=res.id))


@hospitality_bp.route('/reservations/<int:res_id>/delete', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def delete_reservation(res_id):
    """
    Safely deletes a reservation and restores unit status to VACANT if needed.
    """
    res = db.session.get(HospitalityReservation, res_id)
    if not res:
        from flask import abort; abort(404)

    code = res.reservation_code
    try:
        # Free unit if occupied by this reservation
        if res.rental_unit and res.status == 'CHECKED_IN':
            res.rental_unit.occupancy_status = 'VACANT'

        db.session.delete(res)
        db.session.commit()
        AuditService.log('DELETE_RESERVATION', 'HospitalityReservation', res_id, new_values={'code': code})
        flash(f"Reservation {code} has been permanently deleted.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Delete Error: {str(e)}", 'danger')

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

    # Auto-send thank you to guest & payment alert to landlord / property owner
    from app.services.sms_service import SmsService
    from app.services.notification_service import NotificationService
    try:
        SmsService.send_hospitality_payment_sms(res, amount, method=method, reference=ref)
    except Exception:
        pass
    try:
        NotificationService.notify_hospitality_payment(res, amount, method=method, reference=ref)
    except Exception:
        pass

    AuditService.log('RECORD_RESERVATION_PAYMENT', 'HospitalityReservation', res.id,
                     new_values={'amount': amount, 'method': method})
    flash(f"Payment of KES {amount:,.0f} recorded for {res.guest.full_name} (Res: {res.reservation_code}).", 'success')
    return redirect(url_for('hospitality.index'))


@hospitality_bp.route('/reservations/<int:res_id>/receipt', endpoint='receipt')
@hospitality_bp.route('/reservations/<int:res_id>/receipt', endpoint='view_receipt')
@login_required
@permission_required('bookings.view')
def view_receipt(res_id):
    res = db.session.get(HospitalityReservation, res_id)
    if not res:
        from flask import abort; abort(404)
    units = RentalUnit.query.filter_by(operational_type='SHORT_STAY').order_by(RentalUnit.unit_number.asc()).all()
    return render_template('hospitality/receipt.html', res=res, units=units)


@hospitality_bp.route('/reservations/<int:res_id>/pdf')
@login_required
@permission_required('bookings.view')
def download_guest_folio_pdf(res_id):
    from io import BytesIO
    from flask import send_file
    from app.utils.pdf_generator import generate_guest_folio_pdf
    res = db.session.get(HospitalityReservation, res_id)
    if not res:
        from flask import abort; abort(404)
    pdf_bytes = generate_guest_folio_pdf(res)
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Guest_Folio_{res.reservation_code}.pdf"
    )


@hospitality_bp.route('/reservations/<int:res_id>/thermal-pdf')
@login_required
@permission_required('bookings.view')
def download_thermal_receipt_pdf(res_id):
    from io import BytesIO
    from flask import send_file
    from app.utils.pdf_generator import generate_thermal_receipt_pdf
    res = db.session.get(HospitalityReservation, res_id)
    if not res:
        from flask import abort; abort(404)
    pdf_bytes = generate_thermal_receipt_pdf(res)
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Receipt_80mm_{res.reservation_code}.pdf"
    )


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


# ══════════════════════════════════════════════════════════════════════════════
# TWO-WAY ICAL (.ICS) CALENDAR SYNCHRONIZATION (AIRBNB / BOOKING.COM / VRBO)
# ══════════════════════════════════════════════════════════════════════════════

@hospitality_bp.route('/units/<int:unit_id>/calendar.ics')
@hospitality_bp.route('/export-ical/<string:token>.ics')
def export_unit_ical(unit_id=None, token=None):
    """
    Public RFC 5545 iCal export feed for an accommodation unit.
    Allows external platforms (Airbnb, Booking.com, VRBO, Google Calendar, Apple Calendar)
    to automatically subscribe and block dates when local reservations occur.
    """
    import re
    from flask import Response
    from app.services.ical_service import ICalService

    if token:
        unit = RentalUnit.query.filter_by(ical_token=token).first()
    elif unit_id:
        unit = db.session.get(RentalUnit, unit_id)
    else:
        unit = None

    if not unit:
        from flask import abort; abort(404)

    ics_content = ICalService.generate_unit_ical(unit)
    safe_num = re.sub(r'[^A-Za-z0-9_-]', '_', unit.unit_number or 'unit')
    filename = f"calendar_{safe_num}.ics"

    return Response(
        ics_content,
        mimetype='text/calendar; charset=utf-8',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )


@hospitality_bp.route('/units/<int:unit_id>/sync-ical', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def sync_unit_ical(unit_id):
    """
    Synchronizes an external iCal feed (from Airbnb, Booking.com, or direct paste)
    into local reservations for the specified short-stay room.
    """
    from app.services.ical_service import ICalService
    unit = db.session.get(RentalUnit, unit_id)
    if not unit:
        from flask import abort; abort(404)

    feed_url = request.form.get('ical_import_url', '').strip()
    raw_content = request.form.get('raw_ical_content', '').strip() or None

    if feed_url:
        unit.ical_import_url = feed_url
        db.session.commit()

    result = ICalService.sync_unit_external_ical(unit.id, feed_url=feed_url or unit.ical_import_url, ics_content=raw_content)

    if result.get('success'):
        imp = result.get('imported', 0)
        upd = result.get('updated', 0)
        flash(
            f"iCal Calendar sync successful for Room '{unit.unit_number}'. "
            f"Imported: {imp} new block(s), Updated: {upd} reservation(s). "
            f"Calendar is locked against double bookings.",
            'success'
        )
    else:
        err = result.get('error', 'Unknown synchronization failure')
        flash(f"iCal Sync failed for Room '{unit.unit_number}': {err}", 'danger')

    return redirect(request.referrer or url_for('hospitality.rooms'))

