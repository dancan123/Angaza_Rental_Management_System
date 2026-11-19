from datetime import datetime, date
from app.extensions import db
from app.models.property import RentalUnit
from app.models.hospitality import Guest, HospitalityReservation, HousekeepingTask
from app.services.audit_service import AuditService
from app.utils.currency import to_cents

class HospitalityService:
    """
    Dedicated Service for Module B: Hospitality and Short-Stay Management.
    Handles guest profiles, room availability verification, reservation workflows,
    check-in / check-out, automated turnover housekeeping, and ADR / RevPAR KPIs.
    """

    @staticmethod
    def is_unit_available(unit_id: int, check_in: date, check_out: date, exclude_res_id=None) -> bool:
        """
        Verifies that a rental unit is available for the given date range.
        Ensures:
          1. Unit is not leased by a long-term tenant (occupancy_status not OCCUPIED).
          2. No overlapping active reservation (CONFIRMED or CHECKED_IN) exists.
        """
        unit = db.session.get(RentalUnit, unit_id)
        if not unit:
            return False

        # Long-term tenant check
        if unit.current_tenant_id is not None:
            return False

        # Date overlap check
        query = HospitalityReservation.query.filter(
            HospitalityReservation.rental_unit_id == unit_id,
            HospitalityReservation.status.in_(['CONFIRMED', 'CHECKED_IN']),
            HospitalityReservation.check_in_date < check_out,
            HospitalityReservation.check_out_date > check_in
        )
        if exclude_res_id:
            query = query.filter(HospitalityReservation.id != exclude_res_id)

        overlapping = query.first()
        return overlapping is None

    @staticmethod
    def get_or_create_guest(first_name, last_name, phone, email=None, id_passport_number=None, nationality='Kenyan', emergency_contact=None, emergency_phone=None):
        clean_phone = phone.strip()
        guest = Guest.query.filter_by(phone=clean_phone).first()
        if not guest and id_passport_number:
            guest = Guest.query.filter_by(id_passport_number=id_passport_number.strip().upper()).first()

        if not guest:
            guest = Guest(
                first_name=first_name.strip(),
                last_name=last_name.strip(),
                phone=clean_phone,
                email=email.strip().lower() if email else None,
                id_passport_number=id_passport_number.strip().upper() if id_passport_number else None,
                nationality=nationality or 'Kenyan',
                emergency_contact=emergency_contact,
                emergency_phone=emergency_phone
            )
            db.session.add(guest)
            db.session.flush()
        else:
            # Update contact info if provided
            if email:
                guest.email = email.strip().lower()
            if id_passport_number:
                guest.id_passport_number = id_passport_number.strip().upper()
            if nationality:
                guest.nationality = nationality

        return guest

    @staticmethod
    def create_reservation(unit_id: int, guest_data: dict, check_in_date: date, check_out_date: date, num_guests: int = 1, daily_rate: float = None, booking_source: str = 'DIRECT', special_requests: str = None, user_id: int = None):
        """
        Creates a new hospitality booking with conflict prevention and rate computation.
        """
        if check_in_date >= check_out_date:
            raise ValueError("Check-out date must be strictly after check-in date.")

        unit = db.session.get(RentalUnit, unit_id)
        if not unit:
            from flask import abort; abort(404)

        if not HospitalityService.is_unit_available(unit_id, check_in_date, check_out_date):
            raise ValueError(f"Unit {unit.unit_number} is not available between {check_in_date} and {check_out_date}.")

        # Retrieve or create guest
        guest = HospitalityService.get_or_create_guest(
            first_name=guest_data.get('first_name', ''),
            last_name=guest_data.get('last_name', ''),
            phone=guest_data.get('phone', ''),
            email=guest_data.get('email'),
            id_passport_number=guest_data.get('id_passport_number'),
            nationality=guest_data.get('nationality', 'Kenyan'),
            emergency_contact=guest_data.get('emergency_contact'),
            emergency_phone=guest_data.get('emergency_phone')
        )

        num_nights = (check_out_date - check_in_date).days
        rate_cents = to_cents(daily_rate) if daily_rate is not None else unit.daily_rate_cents
        if rate_cents <= 0:
            # Fallback: estimate from monthly rent (rent / 30)
            rate_cents = max(200000, unit.rent_amount_cents // 30)

        total_cents = rate_cents * num_nights
        res_code = f"STAY-{datetime.utcnow().strftime('%Y%m')}-{HospitalityReservation.query.count() + 1:04d}"

        reservation = HospitalityReservation(
            reservation_code=res_code,
            guest_id=guest.id,
            rental_unit_id=unit.id,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            num_guests=num_guests,
            num_nights=num_nights,
            daily_rate_cents=rate_cents,
            total_stay_cents=total_cents,
            paid_amount_cents=0,
            booking_source=booking_source,
            status='CONFIRMED',
            special_requests=special_requests,
            created_by_user_id=user_id
        )
        db.session.add(reservation)
        db.session.commit()

        # Send confirmation SMS to guest
        from app.services.sms_service import SmsService
        if guest.phone:
            prop_name = unit.property.name if unit.property else "Angaza Stays"
            sms_text = (
                f"Dear {guest.first_name}, your short-stay booking at {prop_name} (Unit {unit.unit_number}) "
                f"is CONFIRMED! Ref: {res_code}. Check-in: {check_in_date}. Total: {reservation.total_stay_display}. "
                f"We look forward to hosting you!"
            )
            try:
                SmsService.send_sms(to_phone=guest.phone, message=sms_text, notification_type='HOSPITALITY_RESERVATION')
            except Exception:
                pass

        AuditService.log('CREATE_RESERVATION', 'HospitalityReservation', reservation.id, new_values={'code': res_code, 'unit': unit.unit_number, 'guest': guest.full_name})
        return reservation

    @staticmethod
    def check_in_reservation(reservation_id: int, user_id: int = None):
        """
        Executes guest arrival: records check-in timestamp and marks room as occupied.
        """
        res = db.session.get(HospitalityReservation, reservation_id)
        if not res:
            from flask import abort; abort(404)
        if res.status != 'CONFIRMED':
            raise ValueError(f"Cannot check in reservation with status '{res.status}'.")

        res.status = 'CHECKED_IN'
        res.actual_check_in_time = datetime.utcnow()
        res.rental_unit.occupancy_status = 'OCCUPIED'

        db.session.commit()
        AuditService.log('GUEST_CHECK_IN', 'HospitalityReservation', res.id, new_values={'code': res.reservation_code, 'unit': res.rental_unit.unit_number})
        return res

    @staticmethod
    def check_out_reservation(reservation_id: int, paid_amount: float = None, payment_method: str = 'MPESA', payment_ref: str = None, user_id: int = None):
        """
        Executes guest departure:
        - Updates financial payment records
        - Marks reservation as CHECKED_OUT
        - Sets room status to VACANT and cleaning status to DIRTY
        - Creates an automated TURNOVER housekeeping task
        """
        res = db.session.get(HospitalityReservation, reservation_id)
        if not res:
            from flask import abort; abort(404)
        if res.status != 'CHECKED_IN':
            raise ValueError(f"Cannot check out reservation with status '{res.status}'.")

        if paid_amount is not None:
            res.paid_amount_cents += to_cents(paid_amount)
        if payment_method:
            res.payment_method = payment_method
        if payment_ref:
            res.payment_reference = payment_ref

        res.status = 'CHECKED_OUT'
        res.actual_check_out_time = datetime.utcnow()

        # Free the unit and flag for housekeeping
        unit = res.rental_unit
        unit.occupancy_status = 'VACANT'
        unit.cleaning_status = 'DIRTY'

        # Automated turnover task
        task = HousekeepingTask(
            rental_unit_id=unit.id,
            task_type='TURNOVER_CLEAN',
            priority='HIGH',
            status='PENDING',
            scheduled_date=date.today(),
            notes=f"Turnover cleaning following check-out of guest {res.guest.full_name} ({res.reservation_code})"
        )
        db.session.add(task)
        db.session.commit()

        AuditService.log('GUEST_CHECK_OUT', 'HospitalityReservation', res.id, new_values={'code': res.reservation_code, 'unit': unit.unit_number})
        return res

    @staticmethod
    def cancel_reservation(reservation_id: int, reason: str = None, user_id: int = None):
        res = db.session.get(HospitalityReservation, reservation_id)
        if not res:
            from flask import abort; abort(404)
        if res.status in ['CHECKED_IN', 'CHECKED_OUT']:
            raise ValueError(f"Cannot cancel a reservation that is already {res.status}.")

        res.status = 'CANCELLED'
        if reason:
            res.special_requests = (res.special_requests or '') + f"\n[Cancelled: {reason}]"

        db.session.commit()
        AuditService.log('CANCEL_RESERVATION', 'HospitalityReservation', res.id, new_values={'code': res.reservation_code, 'reason': reason})
        return res

    @staticmethod
    def update_cleaning_status(unit_id: int, new_status: str, user_id: int = None):
        valid = ['CLEAN', 'DIRTY', 'INSPECTED', 'OUT_OF_SERVICE']
        if new_status not in valid:
            raise ValueError(f"Invalid status: {new_status}. Allowed: {valid}")

        unit = db.session.get(RentalUnit, unit_id)
        if not unit:
            from flask import abort; abort(404)
        unit.cleaning_status = new_status
        db.session.commit()
        AuditService.log('UPDATE_CLEANING_STATUS', 'RentalUnit', unit.id, new_values={'status': new_status})
        return unit

    @staticmethod
    def get_hospitality_dashboard_kpis():
        """
        Computes industry-standard hospitality performance metrics:
        - Total Units assigned to short-stay / hospitality
        - Today's Arrivals, Today's Departures, Current In-House Guests
        - Occupancy %, ADR (Average Daily Rate), RevPAR (Revenue Per Available Room)
        """
        today = date.today()
        first_of_month = date(today.year, today.month, 1)

        # 1. Short-stay units
        short_stay_units = RentalUnit.query.filter_by(operational_type='SHORT_STAY').all()
        total_units_count = len(short_stay_units)
        if total_units_count == 0:
            # Fallback to total vacant/unoccupied units if none marked short-stay yet
            short_stay_units = RentalUnit.query.all()
            total_units_count = len(short_stay_units) or 1

        # 2. Activity metrics
        arrivals_today = HospitalityReservation.query.filter(
            HospitalityReservation.check_in_date == today,
            HospitalityReservation.status == 'CONFIRMED'
        ).count()

        departures_today = HospitalityReservation.query.filter(
            HospitalityReservation.check_out_date == today,
            HospitalityReservation.status == 'CHECKED_IN'
        ).count()

        in_house_reservations = HospitalityReservation.query.filter_by(status='CHECKED_IN').all()
        in_house_count = len(in_house_reservations)

        # 3. Monthly Financials & Revenue
        monthly_reservations = HospitalityReservation.query.filter(
            HospitalityReservation.check_in_date >= first_of_month,
            HospitalityReservation.status.in_(['CHECKED_IN', 'CHECKED_OUT', 'CONFIRMED'])
        ).all()

        total_revenue_cents = sum(r.total_stay_cents for r in monthly_reservations)
        total_nights_sold = sum(r.num_nights for r in monthly_reservations) or 1

        # ADR: Total Revenue / Rooms Sold
        adr_cents = total_revenue_cents // total_nights_sold

        # Occupancy %
        occupancy_pct = round((in_house_count / max(1, total_units_count)) * 100, 1)

        # RevPAR: (Occupancy Rate * ADR) or (Total Revenue / Total Available Room-Nights)
        days_in_month = today.day
        total_available_room_nights = total_units_count * days_in_month
        revpar_cents = total_revenue_cents // max(1, total_available_room_nights)

        # 4. Housekeeping status breakdown
        cleaning_counts = {
            'CLEAN': sum(1 for u in short_stay_units if u.cleaning_status == 'CLEAN'),
            'DIRTY': sum(1 for u in short_stay_units if u.cleaning_status == 'DIRTY'),
            'INSPECTED': sum(1 for u in short_stay_units if u.cleaning_status == 'INSPECTED'),
            'OUT_OF_SERVICE': sum(1 for u in short_stay_units if u.cleaning_status == 'OUT_OF_SERVICE')
        }

        from app.utils.currency import format_currency

        return {
            'total_units': total_units_count,
            'arrivals_today': arrivals_today,
            'departures_today': departures_today,
            'in_house_count': in_house_count,
            'occupancy_pct': occupancy_pct,
            'adr_display': format_currency(adr_cents),
            'revpar_display': format_currency(revpar_cents),
            'monthly_revenue_display': format_currency(total_revenue_cents),
            'cleaning_counts': cleaning_counts
        }
