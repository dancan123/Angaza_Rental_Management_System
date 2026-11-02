from datetime import datetime, date, timedelta
from app.extensions import db
from app.models.booking import Booking
from app.models.property import RentalUnit
from app.models.tenant import Tenant
from app.models.lease import Lease
from app.services.audit_service import AuditService
from app.utils.currency import to_cents

class BookingService:
    @staticmethod
    def get_bookings(status=None):
        query = Booking.query
        if status:
            query = query.filter_by(status=status)
        return query.order_by(Booking.created_at.desc()).all()

    @staticmethod
    def create_booking(rental_unit_id, prospective_name, prospective_phone, expected_move_in_date, expiry_date=None, prospective_email=None, prospective_id_number=None, booking_deposit=0, notes=None, user_id=None):
        unit = RentalUnit.query.get_or_404(rental_unit_id)

        # 1. Double-booking check: Unit must not be OCCUPIED or MAINTENANCE
        if unit.occupancy_status in ['OCCUPIED', 'MAINTENANCE', 'INACTIVE']:
            raise ValueError(f"Cannot book Unit {unit.unit_number}: it is currently {unit.occupancy_status}.")

        # 2. Check for existing ACTIVE booking on this unit
        existing_active_booking = Booking.query.filter_by(rental_unit_id=unit.id, status='ACTIVE').first()
        if existing_active_booking:
            raise ValueError(f"Unit {unit.unit_number} already has an active reservation (Ref: {existing_active_booking.booking_reference}) reserved by {existing_active_booking.prospective_name}.")

        # Auto-compute expiry date if not provided (default 7 days)
        if not expiry_date:
            expiry_date = date.today() + timedelta(days=7)

        # Generate unique reference
        ref = f"BKG-{unit.unit_number}-{datetime.utcnow().strftime('%Y%m%d%H%M')}"

        booking = Booking(
            rental_unit_id=unit.id,
            booking_reference=ref,
            prospective_name=prospective_name.strip(),
            prospective_phone=prospective_phone.strip(),
            prospective_email=prospective_email.strip().lower() if prospective_email else None,
            prospective_id_number=prospective_id_number.strip().upper() if prospective_id_number else None,
            booking_date=date.today(),
            expected_move_in_date=expected_move_in_date,
            booking_deposit_cents=to_cents(booking_deposit),
            expiry_date=expiry_date,
            status='ACTIVE',
            notes=notes,
            created_by_user_id=user_id
        )

        # Update unit status to RESERVED automatically
        unit.occupancy_status = 'RESERVED'

        db.session.add(booking)
        db.session.commit()

        AuditService.log('CREATE_BOOKING', 'Booking', booking.id, new_values={'ref': ref, 'unit': unit.unit_number, 'name': prospective_name})
        return booking

    @staticmethod
    def approve_booking(booking_id, holding_deposit=0):
        booking = Booking.query.get_or_404(booking_id)
        if booking.status != 'PENDING':
            raise ValueError(f"Cannot approve booking with status '{booking.status}'. Only pending inquiries can be approved.")

        unit = booking.rental_unit
        if unit.occupancy_status in ['OCCUPIED', 'MAINTENANCE', 'INACTIVE']:
            raise ValueError(f"Cannot reserve Unit {unit.unit_number}: it is currently {unit.occupancy_status}.")

        booking.status = 'ACTIVE'
        if holding_deposit > 0:
            booking.booking_deposit_cents = to_cents(holding_deposit)
        unit.occupancy_status = 'RESERVED'
        db.session.commit()
        AuditService.log('APPROVE_BOOKING', 'Booking', booking.id, new_values={'unit': unit.unit_number, 'name': booking.prospective_name})
        return booking

    @staticmethod
    def cancel_booking(booking_id, reason=None):
        booking = Booking.query.get_or_404(booking_id)
        if booking.status not in ['ACTIVE', 'PENDING']:
            raise ValueError(f"Cannot cancel booking with status '{booking.status}'.")

        booking.status = 'CANCELLED'
        if reason:
            booking.notes = (booking.notes or '') + f"\n[Cancelled: {reason}]"

        # Release unit back to VACANT if it was reserved
        unit = booking.rental_unit
        if unit and unit.occupancy_status == 'RESERVED':
            unit.occupancy_status = 'VACANT'

        db.session.commit()
        AuditService.log('CANCEL_BOOKING', 'Booking', booking.id, new_values={'reason': reason})
        return booking

    @staticmethod
    def convert_to_tenancy(booking_id, move_in_date=None, monthly_rent=None, deposit_amount=None):
        """
        Completes the move-in process:
        - Creates / links Tenant profile
        - Assigns Unit and sets status to OCCUPIED
        - Creates active Lease
        - Marks booking as CONFIRMED_MOVE_IN
        """
        booking = Booking.query.get_or_404(booking_id)
        if booking.status not in ['ACTIVE', 'PENDING']:
            raise ValueError(f"Cannot convert booking with status '{booking.status}'. Only active or pending bookings can be converted.")

        unit = booking.rental_unit
        if not unit:
            raise ValueError("Associated rental unit not found.")

        # Check if tenant with this ID or phone already exists
        id_number = booking.prospective_id_number or f"TEMP-{datetime.utcnow().strftime('%Y%m%d%H%M')}"
        tenant = Tenant.query.filter((Tenant.id_passport_number == id_number) | (Tenant.phone == booking.prospective_phone)).first()
        
        if not tenant:
            names = booking.prospective_name.split(' ', 1)
            first_name = names[0]
            last_name = names[1] if len(names) > 1 else 'Tenant'

            tenant = Tenant(
                first_name=first_name,
                last_name=last_name,
                id_passport_number=id_number,
                phone=booking.prospective_phone,
                email=booking.prospective_email,
                is_active=True
            )
            db.session.add(tenant)
            db.session.flush()

        # Assign unit to tenant
        unit.occupancy_status = 'OCCUPIED'
        unit.current_tenant_id = tenant.id
        unit.availability_date = move_in_date or booking.expected_move_in_date

        rent_cents = to_cents(monthly_rent) if monthly_rent is not None else unit.rent_amount_cents
        deposit_cents = to_cents(deposit_amount) if deposit_amount is not None else unit.deposit_amount_cents

        # Create active lease
        lease_number = f"LSE-{unit.unit_number}-{datetime.utcnow().strftime('%Y%m%d%H%M')}"
        lease = Lease(
            lease_number=lease_number,
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            start_date=move_in_date or booking.expected_move_in_date,
            monthly_rent_cents=rent_cents,
            deposit_cents=deposit_cents,
            status='ACTIVE'
        )
        db.session.add(lease)

        # Mark booking confirmed
        booking.status = 'CONFIRMED_MOVE_IN'
        booking.tenant_id = tenant.id

        db.session.commit()
        AuditService.log('CONVERT_BOOKING', 'Booking', booking.id, new_values={'tenant_id': tenant.id, 'lease': lease_number})
        return tenant, lease

