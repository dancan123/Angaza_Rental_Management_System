from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.booking import Booking
from app.models.property import RentalUnit
from app.services.booking_service import BookingService
from app.utils.decorators import permission_required

bookings_bp = Blueprint('bookings', __name__, url_prefix='/bookings')

@bookings_bp.route('/')
@login_required
@permission_required('bookings.view')
def index():
    status = request.args.get('status')
    search = request.args.get('search', '').strip()

    query = Booking.query
    if status:
        query = query.filter_by(status=status)
    if search:
        term = f"%{search}%"
        query = query.filter(
            (Booking.prospective_name.ilike(term)) |
            (Booking.prospective_phone.ilike(term)) |
            (Booking.booking_reference.ilike(term))
        )
    bookings = query.order_by(Booking.created_at.desc()).all()

    vacant_units = RentalUnit.query.filter_by(occupancy_status='VACANT').all()
    pending_count = Booking.query.filter_by(status='PENDING').count()
    active_count = Booking.query.filter_by(status='ACTIVE').count()

    return render_template(
        'bookings/index.html',
        bookings=bookings,
        vacant_units=vacant_units,
        selected_status=status,
        search=search,
        pending_count=pending_count,
        active_count=active_count
    )

@bookings_bp.route('/<int:booking_id>/approve', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def approve_booking(booking_id):
    deposit = request.form.get('holding_deposit', 0, type=float)
    try:
        booking = BookingService.approve_booking(booking_id, holding_deposit=deposit)
        flash(f"Viewing inquiry approved! Unit {booking.rental_unit.unit_number} has been reserved for {booking.prospective_name}.", 'success')
    except Exception as e:
        flash(f"Approval failed: {str(e)}", 'danger')
    return redirect(url_for('bookings.index', status='ACTIVE'))

@bookings_bp.route('/create', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def create_booking():
    rental_unit_id = request.form.get('rental_unit_id', type=int)
    prospective_name = request.form.get('prospective_name', '').strip()
    prospective_phone = request.form.get('prospective_phone', '').strip()
    prospective_email = request.form.get('prospective_email', '').strip()
    prospective_id_number = request.form.get('prospective_id_number', '').strip()
    move_in_str = request.form.get('expected_move_in_date')
    expiry_str = request.form.get('expiry_date')
    deposit = request.form.get('booking_deposit', 0, type=float)
    notes = request.form.get('notes', '').strip()

    if not rental_unit_id or not prospective_name or not prospective_phone or not move_in_str:
        flash('Rental unit, prospective tenant name, phone, and expected move-in date are required.', 'danger')
        return redirect(url_for('bookings.index'))

    try:
        expected_move_in = datetime.strptime(move_in_str, '%Y-%m-%d').date()
        expiry_date = datetime.strptime(expiry_str, '%Y-%m-%d').date() if expiry_str else None

        booking = BookingService.create_booking(
            rental_unit_id=rental_unit_id,
            prospective_name=prospective_name,
            prospective_phone=prospective_phone,
            expected_move_in_date=expected_move_in,
            expiry_date=expiry_date,
            prospective_email=prospective_email,
            prospective_id_number=prospective_id_number,
            booking_deposit=deposit,
            notes=notes,
            user_id=current_user.id
        )
        flash(f"Reservation created successfully (Ref: {booking.booking_reference}). Unit {booking.rental_unit.unit_number} marked as RESERVED.", 'success')
    except Exception as e:
        flash(f"Booking failed: {str(e)}", 'danger')

    return redirect(url_for('bookings.index'))

@bookings_bp.route('/<int:booking_id>/convert', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def convert_to_tenancy(booking_id):
    try:
        tenant, lease = BookingService.convert_to_tenancy(booking_id)
        flash(f"Move-in completed! Active tenancy and lease agreement ({lease.lease_number}) established for {tenant.full_name}.", 'success')
        return redirect(url_for('tenants.detail', tenant_id=tenant.id))
    except Exception as e:
        flash(f"Move-in conversion failed: {str(e)}", 'danger')
        return redirect(url_for('bookings.index'))

@bookings_bp.route('/<int:booking_id>/cancel', methods=['POST'])
@login_required
@permission_required('bookings.manage')
def cancel_booking(booking_id):
    reason = request.form.get('cancel_reason', '').strip()
    try:
        booking = BookingService.cancel_booking(booking_id, reason=reason)
        flash(f"Booking {booking.booking_reference} cancelled. Unit {booking.rental_unit.unit_number} has been released to VACANT.", 'info')
    except Exception as e:
        flash(f"Cancellation failed: {str(e)}", 'danger')

    return redirect(url_for('bookings.index'))

