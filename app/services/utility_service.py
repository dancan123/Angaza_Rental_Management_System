from datetime import datetime, date
from app.extensions import db
from app.models.utility import Meter, MeterReading
from app.models.property import RentalUnit
from app.models.finance import RentCharge
from app.services.audit_service import AuditService
from app.utils.currency import to_cents

class UtilityService:
    @staticmethod
    def register_meter(property_id: int, rental_unit_id: int, meter_number: str, meter_type: str = 'WATER', rate_per_unit: float = 150.0, initial_reading: float = 0.0):
        unit = RentalUnit.query.get_or_404(rental_unit_id)
        rate_cents = to_cents(rate_per_unit)
        
        meter = Meter(
            property_id=property_id or unit.property_id,
            rental_unit_id=unit.id,
            meter_number=meter_number.strip().upper(),
            meter_type=meter_type.upper(),
            rate_per_unit_cents=rate_cents,
            initial_reading=float(initial_reading),
            last_reading=float(initial_reading),
            is_active=True
        )
        db.session.add(meter)
        db.session.commit()
        AuditService.log('REGISTER_METER', 'Meter', meter.id, new_values={'number': meter.meter_number, 'type': meter.meter_type, 'unit': unit.unit_number})
        return meter

    @staticmethod
    def record_reading(meter_id: int, current_reading: float, reading_date: date = None, recorded_by_id: int = None, photo_url: str = None, auto_bill: bool = True):
        meter = Meter.query.get_or_404(meter_id)
        current_val = float(current_reading)
        previous_val = float(meter.last_reading)
        
        if current_val < previous_val:
            raise ValueError(f"Current reading ({current_val}) cannot be lower than previous reading ({previous_val}).")
            
        units_consumed = round(current_val - previous_val, 2)
        total_cost_cents = int(round(units_consumed * meter.rate_per_unit_cents))
        
        r_date = reading_date or date.today()
        
        reading = MeterReading(
            meter_id=meter.id,
            reading_date=r_date,
            previous_reading=previous_val,
            current_reading=current_val,
            units_consumed=units_consumed,
            rate_per_unit_cents=meter.rate_per_unit_cents,
            total_cost_cents=total_cost_cents,
            billed_status='PENDING',
            photo_url=photo_url,
            recorded_by_user_id=recorded_by_id
        )
        db.session.add(reading)
        meter.last_reading = current_val

        # Auto-bill current tenant of this unit if active lease exists
        if auto_bill and total_cost_cents > 0:
            unit = meter.rental_unit
            tenant = unit.current_tenant if unit else None
            
            if tenant:
                inv_number = f"UTL-{meter.meter_type[:3]}-{r_date.strftime('%Y%m')}-{unit.unit_number}-{int(datetime.utcnow().timestamp()) % 10000}"
                charge = RentCharge(
                    tenant_id=tenant.id,
                    rental_unit_id=unit.id,
                    invoice_number=inv_number,
                    charge_type=meter.meter_type,
                    period_month=r_date.month,
                    period_year=r_date.year,
                    amount_cents=total_cost_cents,
                    amount_paid_cents=0,
                    due_date=r_date,
                    status='UNPAID',
                    description=f"{meter.meter_type.capitalize()} bill for {r_date.strftime('%B %Y')} ({units_consumed} units @ {meter.rate_display}/unit; prev: {previous_val}, cur: {current_val})"
                )
                db.session.add(charge)
                db.session.flush()
                reading.rent_charge_id = charge.id
                reading.billed_status = 'BILLED'

        db.session.commit()
        AuditService.log('RECORD_METER_READING', 'MeterReading', reading.id, new_values={'meter': meter.meter_number, 'units': units_consumed, 'cost': total_cost_cents})
        return reading

    @staticmethod
    def get_property_meters(property_id: int = None):
        query = Meter.query.filter_by(is_active=True)
        if property_id:
            query = query.filter_by(property_id=property_id)
        return query.order_by(Meter.property_id.asc(), Meter.rental_unit_id.asc()).all()

    @staticmethod
    def get_recent_readings(limit: int = 50, property_id: int = None):
        query = MeterReading.query.join(Meter)
        if property_id:
            query = query.filter(Meter.property_id == property_id)
        return query.order_by(MeterReading.reading_date.desc(), MeterReading.id.desc()).limit(limit).all()

