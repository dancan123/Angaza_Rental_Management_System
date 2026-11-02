from datetime import datetime, date
from app.extensions import db
from app.models.lease import Lease
from app.models.finance import RentCharge
from app.models.property import RentalUnit
from app.services.personalization_service import PersonalizationService
from app.services.audit_service import AuditService
from app.utils.currency import to_cents

class RentService:
    @staticmethod
    def generate_monthly_charges(month: int, year: int, landlord_id=None):
        """
        Generates monthly rent charges for all active leases for the specified month and year.
        Idempotent: skips units/leases that have already been billed for the given period.
        """
        active_leases = Lease.query.filter_by(status='ACTIVE')
        if landlord_id:
            active_leases = active_leases.join(RentalUnit).filter(RentalUnit.property.has(landlord_id=landlord_id))
            
        leases = active_leases.all()
        created_count = 0
        total_amount_cents = 0

        # Retrieve default due day from settings (e.g. 5th)
        due_day = int(PersonalizationService.get_setting('default_due_day', '5'))
        try:
            due_date = date(year, month, min(due_day, 28))
        except Exception:
            due_date = date(year, month, 5)

        for lease in leases:
            # Check if charge already exists
            existing = RentCharge.query.filter_by(
                lease_id=lease.id,
                period_month=month,
                period_year=year,
                charge_type='RENT'
            ).first()

            if not existing:
                unit_num = lease.rental_unit.unit_number if lease.rental_unit else f"UNIT-{lease.rental_unit_id}"
                inv_number = f"INV-{year}{month:02d}-{unit_num}-{lease.tenant_id}"
                charge = RentCharge(
                    lease_id=lease.id,
                    tenant_id=lease.tenant_id,
                    rental_unit_id=lease.rental_unit_id,
                    invoice_number=inv_number,
                    charge_type='RENT',
                    period_month=month,
                    period_year=year,
                    amount_cents=lease.monthly_rent_cents,
                    amount_paid_cents=0,
                    due_date=due_date,
                    status='UNPAID',
                    description=f"Monthly Rent for {date(year, month, 1).strftime('%B %Y')}"
                )
                db.session.add(charge)
                created_count += 1
                total_amount_cents += lease.monthly_rent_cents

        db.session.commit()
        AuditService.log('GENERATE_MONTHLY_CHARGES', 'RentCharge', new_values={'month': month, 'year': year, 'count': created_count})
        return {'created_count': created_count, 'total_amount_cents': total_amount_cents}

    @staticmethod
    def apply_late_penalties(current_date=None):
        """
        Applies late fee penalties on overdue, unpaid rent charges where grace period has elapsed.
        """
        if current_date is None:
            current_date = date.today()

        grace_days = int(PersonalizationService.get_setting('grace_period_days', '5'))
        late_pct = float(PersonalizationService.get_setting('late_fee_percentage', '5'))

        if late_pct <= 0:
            return 0

        unpaid_charges = RentCharge.query.filter(
            RentCharge.status.in_(['UNPAID', 'PARTIALLY_PAID']),
            RentCharge.charge_type == 'RENT'
        ).all()

        penalty_count = 0
        for charge in unpaid_charges:
            days_overdue = (current_date - charge.due_date).days
            if days_overdue > grace_days:
                # Check if penalty already applied for this invoice
                penalty_inv = f"PEN-{charge.invoice_number}"
                existing_pen = RentCharge.query.filter_by(invoice_number=penalty_inv).first()
                if not existing_pen and charge.balance_cents > 0:
                    penalty_amount_cents = int(charge.balance_cents * (late_pct / 100))
                    if penalty_amount_cents > 0:
                        penalty_charge = RentCharge(
                            lease_id=charge.lease_id,
                            tenant_id=charge.tenant_id,
                            rental_unit_id=charge.rental_unit_id,
                            invoice_number=penalty_inv,
                            charge_type='LATE_FEE',
                            period_month=charge.period_month,
                            period_year=charge.period_year,
                            amount_cents=penalty_amount_cents,
                            amount_paid_cents=0,
                            due_date=current_date,
                            status='UNPAID',
                            description=f"Late payment penalty ({late_pct}%) on {charge.invoice_number}"
                        )
                        db.session.add(penalty_charge)
                        penalty_count += 1
                        try:
                            from app.services.notification_service import NotificationService
                            NotificationService.send_late_penalty_notification(charge, penalty_amount_cents)
                        except Exception:
                            pass

        db.session.commit()
        return penalty_count

    @staticmethod
    def add_custom_charge(tenant_id, rental_unit_id, charge_type, amount, description, due_date=None, month=None, year=None):
        today = date.today()
        m = month or today.month
        y = year or today.year
        cents = to_cents(amount)
        inv = f"CHG-{y}{m:02d}-{tenant_id}-{datetime.utcnow().strftime('%H%M%S')}"

        charge = RentCharge(
            tenant_id=tenant_id,
            rental_unit_id=rental_unit_id,
            invoice_number=inv,
            charge_type=charge_type,
            period_month=m,
            period_year=y,
            amount_cents=cents,
            amount_paid_cents=0,
            due_date=due_date or today,
            status='UNPAID',
            description=description
        )
        db.session.add(charge)
        db.session.commit()
        AuditService.log('ADD_CUSTOM_CHARGE', 'RentCharge', charge.id, new_values={'type': charge_type, 'amount': cents})
        return charge
