from datetime import datetime, date
from app.extensions import db
from app.models.finance import Payment, PaymentAllocation, PaymentReversal, RentCharge
from app.models.tenant import Tenant
from app.models.property import RentalUnit
from app.services.audit_service import AuditService
from app.utils.currency import to_cents

class PaymentService:
    @staticmethod
    def generate_receipt_number():
        now = datetime.utcnow()
        count = Payment.query.count() + 1
        return f"REC-{now.strftime('%Y%m')}-{count:04d}"

    @staticmethod
    def record_payment(tenant_id, amount, payment_method, rental_unit_id=None, property_id=None, payment_date=None, transaction_reference=None, description=None, user_id=None, auto_confirm=True):
        tenant = db.session.get(Tenant, tenant_id)
        if not tenant:
            from flask import abort; abort(404)
        unit = db.session.get(RentalUnit, rental_unit_id) if rental_unit_id else tenant.current_unit
        if not unit:
            raise ValueError("A rental unit must be associated with the payment.")

        cents = to_cents(amount)
        if cents <= 0:
            raise ValueError("Payment amount must be greater than zero.")

        # Check unique transaction reference if provided (e.g. M-Pesa or Bank ref)
        if transaction_reference:
            clean_ref = transaction_reference.strip().upper()
            existing_ref = Payment.query.filter_by(transaction_reference=clean_ref).first()
            if existing_ref:
                raise ValueError(f"Duplicate payment reference: '{clean_ref}' has already been processed under Receipt {existing_ref.receipt_number}.")
        else:
            clean_ref = None

        receipt_no = PaymentService.generate_receipt_number()
        payment_no = f"PAY-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        payment = Payment(
            tenant_id=tenant.id,
            rental_unit_id=unit.id,
            property_id=unit.property_id,
            payment_number=payment_no,
            receipt_number=receipt_no,
            amount_cents=cents,
            payment_date=payment_date or date.today(),
            payment_method=payment_method,
            transaction_reference=clean_ref,
            payment_status='PENDING',
            recorded_by_user_id=user_id,
            description=description
        )
        db.session.add(payment)
        db.session.commit()

        AuditService.log('RECORD_PAYMENT', 'Payment', payment.id, new_values={'amount': cents, 'method': payment_method, 'ref': clean_ref})

        if auto_confirm:
            PaymentService.confirm_payment(payment.id, user_id=user_id)

        return payment

    @staticmethod
    def confirm_payment(payment_id, user_id=None):
        """
        Confirms a payment and allocates funds chronologically to outstanding charges.
        Ensures partial payments, exact settlements, and advance overpayments are handled safely.
        """
        payment = db.session.get(Payment, payment_id)
        if not payment:
            from flask import abort; abort(404)
        if payment.payment_status == 'CONFIRMED':
            return payment  # Already confirmed

        payment.payment_status = 'CONFIRMED'
        payment.verified_at = datetime.utcnow()

        # Find unpaid charges for this tenant, ordered chronologically (oldest first)
        unpaid_charges = RentCharge.query.filter(
            RentCharge.tenant_id == payment.tenant_id,
            RentCharge.status.in_(['UNPAID', 'PARTIALLY_PAID'])
        ).order_by(RentCharge.due_date.asc(), RentCharge.id.asc()).all()

        remaining_cents = payment.amount_cents

        for charge in unpaid_charges:
            if remaining_cents <= 0:
                break

            charge_balance = charge.balance_cents
            if charge_balance <= 0:
                continue

            allocation_amount = min(remaining_cents, charge_balance)

            # Record allocation
            allocation = PaymentAllocation(
                payment_id=payment.id,
                rent_charge_id=charge.id,
                allocated_amount_cents=allocation_amount
            )
            db.session.add(allocation)

            # Update charge balance
            charge.amount_paid_cents += allocation_amount
            if charge.amount_paid_cents >= charge.amount_cents:
                charge.status = 'PAID'
            else:
                charge.status = 'PARTIALLY_PAID'

            remaining_cents -= allocation_amount

        db.session.commit()

        # Landlord notification trigger
        from app.services.notification_service import NotificationService
        NotificationService.notify_rent_payment(payment)

        AuditService.log('CONFIRM_PAYMENT', 'Payment', payment.id, new_values={'receipt': payment.receipt_number, 'amount': payment.amount_cents})
        return payment

    @staticmethod
    def reverse_payment(payment_id, reversal_reason, user_id=None):
        """
        Reverses a confirmed payment with full audit trail:
        - Deducts allocated amounts from charges
        - Sets payment status to REVERSED
        - Records immutable PaymentReversal record
        """
        payment = db.session.get(Payment, payment_id)
        if not payment:
            from flask import abort; abort(404)
        if payment.payment_status == 'REVERSED':
            raise ValueError("Payment has already been reversed.")

        # Undo allocations
        for alloc in payment.allocations.all():
            charge = alloc.rent_charge
            if charge:
                charge.amount_paid_cents = max(0, charge.amount_paid_cents - alloc.allocated_amount_cents)
                if charge.amount_paid_cents == 0:
                    charge.status = 'UNPAID'
                else:
                    charge.status = 'PARTIALLY_PAID'
            db.session.delete(alloc)

        payment.payment_status = 'REVERSED'

        reversal = PaymentReversal(
            payment_id=payment.id,
            reversed_by_user_id=user_id,
            original_amount_cents=payment.amount_cents,
            reversal_reason=reversal_reason,
            reversed_at=datetime.utcnow()
        )
        db.session.add(reversal)
        db.session.commit()

        AuditService.log('REVERSE_PAYMENT', 'Payment', payment.id, new_values={'reason': reversal_reason})
        return payment

