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
    def get_or_create_guest(first_name, last_name, phone, email=None, id_passport_number=None, nationality='Kenyan', emergency_contact=None, emergency_phone=None, organization_id=None):
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
                emergency_phone=emergency_phone,
                organization_id=organization_id
            )
            db.session.add(guest)
            db.session.flush()
        else:
            if organization_id and not guest.organization_id:
                guest.organization_id = organization_id
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

        org_id = unit.property.organization_id if (unit and unit.property) else None

        # Retrieve or create guest
        guest = HospitalityService.get_or_create_guest(
            first_name=guest_data.get('first_name', ''),
            last_name=guest_data.get('last_name', ''),
            phone=guest_data.get('phone', ''),
            email=guest_data.get('email'),
            id_passport_number=guest_data.get('id_passport_number'),
            nationality=guest_data.get('nationality', 'Kenyan'),
            emergency_contact=guest_data.get('emergency_contact'),
            emergency_phone=guest_data.get('emergency_phone'),
            organization_id=org_id
        )

        num_nights = (check_out_date - check_in_date).days
        base_rate_cents = to_cents(daily_rate) if daily_rate is not None else unit.daily_rate_cents
        if base_rate_cents <= 0:
            # Fallback: estimate from monthly rent (rent / 30)
            base_rate_cents = max(200000, unit.rent_amount_cents // 30)

        # Apply seasonal/pricing rules — compute rate per night
        try:
            from app.models.pricing import RoomPricingRule
            active_rules = RoomPricingRule.query.filter_by(is_active=True).all()
        except Exception:
            active_rules = []

        total_cents = 0
        rate_cents = base_rate_cents  # representative rate for display
        from datetime import timedelta
        current_day = check_in_date
        while current_day < check_out_date:
            night_rate = base_rate_cents
            # Find applicable rule (unit-specific first, then global)
            unit_rule = None
            global_rule = None
            for r in active_rules:
                if not r.applies_on_date(current_day):
                    continue
                if r.rental_unit_id == unit.id:
                    unit_rule = r
                elif r.rental_unit_id is None:
                    global_rule = r
            applicable = unit_rule or global_rule
            if applicable:
                night_rate = applicable.compute_rate_cents(base_rate_cents)
            total_cents += night_rate
            current_day = current_day + timedelta(days=1)

        if total_cents <= 0:
            total_cents = base_rate_cents * num_nights
        res_code = f"STAY-{datetime.utcnow().strftime('%Y%m')}-{HospitalityReservation.query.count() + 1:04d}"

        reservation = HospitalityReservation(
            reservation_code=res_code,
            guest_id=guest.id,
            rental_unit_id=unit.id,
            organization_id=org_id,
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
    def get_hospitality_dashboard_kpis(organization_id=None, landlord_id=None):
        """
        Computes industry-standard hospitality performance metrics:
        - Total Units assigned to short-stay / hospitality
        - Today's Arrivals, Today's Departures, Current In-House Guests
        - Occupancy %, ADR (Average Daily Rate), RevPAR (Revenue Per Available Room)
        Scoped strictly to short-stay / Airbnb units for the tenant/landlord organization.
        """
        from app.models.property import Property
        today = date.today()
        first_of_month = date(today.year, today.month, 1)

        # 1. Properties scoped
        prop_query = Property.query
        if organization_id:
            prop_query = prop_query.filter(
                (Property.organization_id == organization_id) | (Property.organization_id.is_(None))
            )
        if landlord_id:
            if isinstance(landlord_id, list):
                prop_query = prop_query.filter(Property.landlord_id.in_(landlord_id))
            else:
                prop_query = prop_query.filter(Property.landlord_id == landlord_id)

        prop_ids = [p.id for p in prop_query.all()]

        # 2. Short-stay units only
        unit_query = RentalUnit.query.filter_by(operational_type='SHORT_STAY')
        if prop_ids:
            unit_query = unit_query.filter(RentalUnit.property_id.in_(prop_ids))
        elif organization_id or landlord_id:
            unit_query = unit_query.filter(RentalUnit.id == -1)

        short_stay_units = unit_query.all()
        total_units_count = len(short_stay_units)
        unit_ids = [u.id for u in short_stay_units]

        # 3. Activity metrics strictly for short-stay units
        if unit_ids:
            arrivals_today = HospitalityReservation.query.filter(
                HospitalityReservation.rental_unit_id.in_(unit_ids),
                HospitalityReservation.check_in_date == today,
                HospitalityReservation.status == 'CONFIRMED'
            ).count()

            departures_today = HospitalityReservation.query.filter(
                HospitalityReservation.rental_unit_id.in_(unit_ids),
                HospitalityReservation.check_out_date == today,
                HospitalityReservation.status == 'CHECKED_IN'
            ).count()

            in_house_reservations = HospitalityReservation.query.filter(
                HospitalityReservation.rental_unit_id.in_(unit_ids),
                HospitalityReservation.status == 'CHECKED_IN'
            ).all()
            in_house_count = len(in_house_reservations)

            monthly_reservations = HospitalityReservation.query.filter(
                HospitalityReservation.rental_unit_id.in_(unit_ids),
                HospitalityReservation.check_in_date >= first_of_month,
                HospitalityReservation.status.in_(['CHECKED_IN', 'CHECKED_OUT', 'CONFIRMED'])
            ).all()

            total_revenue_cents = sum(r.total_stay_cents for r in monthly_reservations)
            total_nights_sold = sum(r.num_nights for r in monthly_reservations) or 1
            adr_cents = total_revenue_cents // total_nights_sold if total_revenue_cents > 0 else 0
            occupancy_pct = round((in_house_count / max(1, total_units_count)) * 100, 1)

            days_in_month = today.day
            total_available_room_nights = total_units_count * days_in_month
            revpar_cents = total_revenue_cents // max(1, total_available_room_nights) if total_available_room_nights > 0 else 0
        else:
            arrivals_today = 0
            departures_today = 0
            in_house_count = 0
            total_revenue_cents = 0
            adr_cents = 0
            occupancy_pct = 0.0
            revpar_cents = 0

        # 4. Housekeeping status breakdown strictly for short-stay units
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

    @classmethod
    def get_rooms_management_overview(cls, organization_id=None, landlord_id=None):
        """
        Retrieves all accommodation rooms/units with:
        - Scoped to organization and landlord if provided
        - Current active reservation details (guest, check-in, check-out, status)
        - Financials: Daily rate, monthly potential/rate, and total historical collected amounts
        - Aggregate financial & operational KPIs for administrative management
        """
        from app.models.property import Property
        from sqlalchemy import func
        from app.utils.currency import format_currency
        today = date.today()

        # Query properties scoped to organization & landlord
        prop_query = Property.query
        if organization_id:
            prop_query = prop_query.filter(
                (Property.organization_id == organization_id) | (Property.organization_id.is_(None))
            )
        if landlord_id:
            if isinstance(landlord_id, list):
                prop_query = prop_query.filter(Property.landlord_id.in_(landlord_id))
            else:
                prop_query = prop_query.filter(Property.landlord_id == landlord_id)

        properties = prop_query.order_by(Property.name.asc()).all()
        prop_ids = [p.id for p in properties]

        if not prop_ids:
            return {
                'rooms': [],
                'properties': [],
                'stats': {
                    'total_rooms': 0,
                    'short_stay_count': 0,
                    'occupied_count': 0,
                    'vacant_count': 0,
                    'occupancy_rate': 0.0,
                    'total_daily_rate_cents': 0,
                    'total_monthly_potential_cents': 0,
                    'total_collected_cents': 0,
                    'total_daily_rate_display': format_currency(0),
                    'total_monthly_potential_display': format_currency(0),
                    'total_collected_display': format_currency(0),
                }
            }

        # Query units for those properties
        units = RentalUnit.query.filter(RentalUnit.property_id.in_(prop_ids)).order_by(RentalUnit.unit_number.asc()).all()
        unit_ids = [u.id for u in units]

        # Query active / in-house reservations for today
        active_reservations = HospitalityReservation.query.filter(
            HospitalityReservation.rental_unit_id.in_(unit_ids),
            HospitalityReservation.check_in_date <= today,
            HospitalityReservation.check_out_date > today,
            HospitalityReservation.status.in_(['CHECKED_IN', 'CONFIRMED'])
        ).all()
        active_res_by_unit = {r.rental_unit_id: r for r in active_reservations}

        # Query all-time collected amounts per unit from HospitalityReservation
        collected_data = db.session.query(
            HospitalityReservation.rental_unit_id,
            func.coalesce(func.sum(HospitalityReservation.paid_amount_cents), 0).label('total_paid')
        ).filter(
            HospitalityReservation.rental_unit_id.in_(unit_ids),
            HospitalityReservation.status != 'CANCELLED'
        ).group_by(HospitalityReservation.rental_unit_id).all()
        collected_by_unit = {row[0]: int(row[1]) for row in collected_data}

        # Decorate each unit with computed administrative metadata
        decorated_rooms = []
        total_daily_rate_cents = 0
        total_monthly_potential_cents = 0
        total_collected_all_cents = 0
        occupied_count = 0
        short_stay_count = 0

        for u in units:
            active_res = active_res_by_unit.get(u.id)
            collected_cents = collected_by_unit.get(u.id, 0)
            
            # Daily rate
            daily_cents = u.daily_rate_cents or 0
            
            # Monthly potential: explicit rent_amount_cents or daily_rate * 30
            monthly_cents = u.rent_amount_cents if u.rent_amount_cents > 0 else (daily_cents * 30)

            is_occupied = active_res is not None or u.occupancy_status == 'OCCUPIED'
            is_short_stay = (u.operational_type == 'SHORT_STAY')

            if is_short_stay:
                short_stay_count += 1
                total_daily_rate_cents += daily_cents
                total_monthly_potential_cents += monthly_cents
                total_collected_all_cents += collected_cents
                if is_occupied:
                    occupied_count += 1

            room_info = {
                'unit': u,
                'active_reservation': active_res,
                'is_occupied': is_occupied,
                'daily_rate_cents': daily_cents,
                'monthly_potential_cents': monthly_cents,
                'total_collected_cents': collected_cents,
                'daily_rate_display': format_currency(daily_cents),
                'monthly_potential_display': format_currency(monthly_cents),
                'total_collected_display': format_currency(collected_cents),
            }
            decorated_rooms.append(room_info)

        occupancy_rate = round((occupied_count / max(1, short_stay_count)) * 100, 1)

        stats = {
            'total_rooms': len(units),
            'short_stay_count': short_stay_count,
            'occupied_count': occupied_count,
            'vacant_count': max(0, short_stay_count - occupied_count),
            'occupancy_rate': occupancy_rate,
            'total_daily_rate_cents': total_daily_rate_cents,
            'total_monthly_potential_cents': total_monthly_potential_cents,
            'total_collected_cents': total_collected_all_cents,
            'total_daily_rate_display': format_currency(total_daily_rate_cents),
            'total_monthly_potential_display': format_currency(total_monthly_potential_cents),
            'total_collected_display': format_currency(total_collected_all_cents),
        }

        return {
            'rooms': decorated_rooms,
            'properties': properties,
            'stats': stats
        }

    @classmethod
    def record_guest_walkout(cls, unit_id: int, user_id: int = None):
        """
        Executes immediate guest walk-out / departure logic:
        1. Checks out any active in-house reservation on the room
        2. Sets room occupancy to VACANT
        3. Automatically flags cleaning status as DIRTY
        4. Spawns an automated HIGH priority turnover housekeeping task
        """
        unit = db.session.get(RentalUnit, unit_id)
        if not unit:
            from flask import abort; abort(404)

        today = date.today()

        # Check out any active in-house reservation
        active_res = HospitalityReservation.query.filter(
            HospitalityReservation.rental_unit_id == unit.id,
            HospitalityReservation.status == 'CHECKED_IN'
        ).first()

        guest_name = "Guest"
        if active_res:
            active_res.status = 'CHECKED_OUT'
            active_res.actual_check_out_time = datetime.utcnow()
            guest_name = active_res.guest.full_name if active_res.guest else "Guest"

        unit.occupancy_status = 'VACANT'
        unit.cleaning_status = 'DIRTY'

        # Create or ensure turnover cleaning task exists
        existing_task = HousekeepingTask.query.filter(
            HousekeepingTask.rental_unit_id == unit.id,
            HousekeepingTask.status.in_(['PENDING', 'IN_PROGRESS'])
        ).first()

        if not existing_task:
            task = HousekeepingTask(
                rental_unit_id=unit.id,
                task_type='TURNOVER_CLEAN',
                priority='HIGH',
                status='PENDING',
                scheduled_date=today,
                notes=f"Turnover cleaning: {guest_name} walked out / vacated Room {unit.unit_number}.",
                assigned_user_id=user_id
            )
            db.session.add(task)

        db.session.commit()
        return unit
