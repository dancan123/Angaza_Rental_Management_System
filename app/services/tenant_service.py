from datetime import datetime, date
from app.extensions import db
from app.models.tenant import Tenant, NextOfKin
from app.models.property import RentalUnit
from app.models.lease import Lease, TenancyRecord
from app.models.finance import RentCharge, Payment
from app.services.audit_service import AuditService
from app.utils.currency import to_cents

class TenantService:
    @staticmethod
    def get_tenants(search=None, is_active=True):
        query = Tenant.query
        if is_active is not None:
            query = query.filter_by(is_active=is_active)
        if search:
            clean_search = search.strip()
            term = f"%{clean_search}%"
            # Extract digits for flexible phone searching
            clean_digits = ''.join(c for c in clean_search if c.isdigit())

            conditions = [
                Tenant.first_name.ilike(term),
                Tenant.last_name.ilike(term),
                (Tenant.first_name + ' ' + Tenant.last_name).ilike(term),
                Tenant.phone.ilike(term),
                Tenant.id_passport_number.ilike(term),
                Tenant.email.ilike(term)
            ]
            if clean_digits and len(clean_digits) >= 4:
                conditions.append(Tenant.phone.ilike(f"%{clean_digits}%"))

            query = query.filter(db.or_(*conditions))
        return query.order_by(Tenant.created_at.desc()).all()

    @staticmethod
    def create_tenant(first_name, last_name, id_passport_number, phone, email=None, emergency_contact=None, emergency_phone=None, physical_address=None, occupation=None, next_of_kin_data=None):
        existing = Tenant.query.filter_by(id_passport_number=id_passport_number).first()
        if existing:
            raise ValueError(f"Tenant with ID/Passport {id_passport_number} is already registered.")

        tenant = Tenant(
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            id_passport_number=id_passport_number.strip().upper(),
            phone=phone.strip(),
            email=email.strip().lower() if email else None,
            emergency_contact=emergency_contact,
            emergency_phone=emergency_phone,
            physical_address=physical_address,
            occupation=occupation,
            is_active=True
        )
        db.session.add(tenant)
        db.session.flush()

        if next_of_kin_data:
            kin = NextOfKin(
                tenant_id=tenant.id,
                full_name=next_of_kin_data.get('full_name', ''),
                relationship=next_of_kin_data.get('relationship', 'Next of Kin'),
                phone=next_of_kin_data.get('phone', ''),
                email=next_of_kin_data.get('email'),
                physical_address=next_of_kin_data.get('address')
            )
            db.session.add(kin)

        db.session.commit()
        AuditService.log('CREATE', 'Tenant', tenant.id, new_values={'name': tenant.full_name, 'id': tenant.id_passport_number})
        return tenant

    @staticmethod
    def get_tenant_financial_summary(tenant_id):
        charges = RentCharge.query.filter_by(tenant_id=tenant_id).all()
        total_billed_cents = sum(c.amount_cents for c in charges)
        total_paid_cents = sum(c.amount_paid_cents for c in charges)
        outstanding_cents = max(0, total_billed_cents - total_paid_cents)

        payments = Payment.query.filter_by(tenant_id=tenant_id, payment_status='CONFIRMED').all()
        direct_payments_cents = sum(p.amount_cents for p in payments)

        return {
            'total_billed_cents': total_billed_cents,
            'total_paid_cents': total_paid_cents,
            'outstanding_cents': outstanding_cents,
            'direct_payments_cents': direct_payments_cents
        }

    @staticmethod
    def process_move_out(tenant_id, move_out_date=None, inspection_notes=None, deposit_refunded=0, deposit_deductions=0, deduction_reason=None):
        tenant = Tenant.query.get_or_404(tenant_id)
        current_unit = tenant.current_unit
        if not current_unit:
            raise ValueError("Tenant has no active unit assigned.")

        # Find active lease
        lease = Lease.query.filter_by(tenant_id=tenant.id, rental_unit_id=current_unit.id, status='ACTIVE').first()
        move_in = lease.start_date if lease else (current_unit.availability_date or date.today())
        
        # Create TenancyRecord
        record = TenancyRecord(
            tenant_id=tenant.id,
            rental_unit_id=current_unit.id,
            move_in_date=move_in,
            move_out_date=move_out_date or date.today(),
            move_out_inspection_notes=inspection_notes,
            deposit_refunded_cents=to_cents(deposit_refunded),
            deposit_deductions_cents=to_cents(deposit_deductions),
            deduction_reason=deduction_reason
        )
        db.session.add(record)

        if lease:
            lease.status = 'TERMINATED'
            lease.terminated_at = datetime.utcnow()
            lease.termination_reason = inspection_notes or 'End of Tenancy Move-out'

        # Free the unit
        current_unit.occupancy_status = 'VACANT'
        current_unit.current_tenant_id = None
        current_unit.availability_date = date.today()

        tenant.is_active = False
        db.session.commit()

        AuditService.log('MOVE_OUT', 'Tenant', tenant.id, new_values={'unit': current_unit.unit_number, 'refund': deposit_refunded})
        return record

    @staticmethod
    def transfer_unit(tenant_id, new_unit_id, transfer_date=None, transfer_reason=None):
        tenant = Tenant.query.get_or_404(tenant_id)
        old_unit = tenant.current_unit
        if not old_unit:
            raise ValueError("Tenant is not currently occupying any unit.")

        new_unit = RentalUnit.query.get_or_404(new_unit_id)
        if new_unit.occupancy_status != 'VACANT':
            raise ValueError(f"Target unit {new_unit.unit_number} is not vacant (status: {new_unit.occupancy_status}).")

        # Record old tenancy history
        old_lease = Lease.query.filter_by(tenant_id=tenant.id, rental_unit_id=old_unit.id, status='ACTIVE').first()
        history = TenancyRecord(
            tenant_id=tenant.id,
            rental_unit_id=old_unit.id,
            move_in_date=old_lease.start_date if old_lease else date.today(),
            move_out_date=transfer_date or date.today(),
            transfer_reason=transfer_reason or f"Transferred to Unit {new_unit.unit_number}"
        )
        db.session.add(history)

        if old_lease:
            old_lease.status = 'TERMINATED'
            old_lease.terminated_at = datetime.utcnow()
            old_lease.termination_reason = f"Transferred to {new_unit.unit_number}"

        # Release old unit
        old_unit.occupancy_status = 'VACANT'
        old_unit.current_tenant_id = None

        # Assign new unit
        new_unit.occupancy_status = 'OCCUPIED'
        new_unit.current_tenant_id = tenant.id

        # Create new lease for the new unit
        new_lease = Lease(
            lease_number=f"LSE-{new_unit.unit_number}-{datetime.utcnow().strftime('%Y%m%d%H%M')}",
            rental_unit_id=new_unit.id,
            tenant_id=tenant.id,
            start_date=transfer_date or date.today(),
            monthly_rent_cents=new_unit.rent_amount_cents,
            deposit_cents=new_unit.deposit_amount_cents,
            status='ACTIVE'
        )
        db.session.add(new_lease)
        db.session.commit()

        AuditService.log('TRANSFER_UNIT', 'Tenant', tenant.id, old_values={'from_unit': old_unit.unit_number}, new_values={'to_unit': new_unit.unit_number})
        return new_lease

