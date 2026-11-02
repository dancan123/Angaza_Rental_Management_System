from datetime import datetime
from app.extensions import db
from app.models.communication import Notification
from app.models.user import User, Role
from app.models.finance import RentCharge
from app.utils.currency import format_currency

class NotificationService:
    @staticmethod
    def notify_rent_payment(payment):
        """
        Dispatches rent payment confirmation directly to:
        1. The Landlord (Property Owner)
        2. The Property Manager(s)
        3. The Caretaker(s) on-site
        """
        prop = payment.property
        landlord = prop.landlord if prop else None
        tenant = payment.tenant
        unit = payment.rental_unit

        from app.services.tenant_service import TenantService
        summary = TenantService.get_tenant_financial_summary(tenant.id) if tenant else {'outstanding_cents': 0}
        balance_str = format_currency(summary['outstanding_cents'])

        base_details = (
            f"Property: {prop.name if prop else 'N/A'}\n"
            f"Unit/House: {unit.unit_number if unit else 'N/A'}\n"
            f"Tenant: {tenant.full_name if tenant else 'N/A'}\n"
            f"Amount Paid: {payment.amount_display}\n"
            f"Method: {payment.payment_method}\n"
            f"Transaction Ref: {payment.transaction_reference or 'N/A'}\n"
            f"Receipt No: {payment.receipt_number}\n"
            f"Date: {payment.payment_date.strftime('%d/%m/%Y %H:%M')}\n"
            f"Remaining Balance: {balance_str}"
        )

        created_notifs = []

        # 1. Dispatch to Landlord (Property Owner)
        if landlord:
            landlord_msg = f"RENT PAYMENT RECEIVED — PROPERTY OWNER NOTICE\n{base_details}\nYour account will be credited as per schedule."
            notif_landlord = Notification(
                landlord_id=landlord.id,
                title=f"Rent Paid: Unit {unit.unit_number} ({payment.amount_display})",
                message=landlord_msg,
                channel='IN_APP',
                notification_type='RENT_PAYMENT_CONFIRMED',
                sent_status='SENT',
                sent_at=datetime.utcnow()
            )
            db.session.add(notif_landlord)
            created_notifs.append(notif_landlord)

        # 2. Dispatch to Property Managers & Admins
        managers = User.query.join(Role).filter(
            Role.name.in_(['SUPERADMIN', 'PROPERTY_MANAGER']),
            User.is_active.is_(True)
        ).all()
        for mgr in managers:
            mgr_msg = f"MANAGER PAYMENT ALERT\n{base_details}\nStatus: Verified and allocated to rent account."
            notif_mgr = Notification(
                recipient_user_id=mgr.id,
                landlord_id=landlord.id if landlord else None,
                title=f"Payment Received: {unit.unit_number} ({tenant.full_name})",
                message=mgr_msg,
                channel='IN_APP',
                notification_type='RENT_PAYMENT_CONFIRMED',
                sent_status='SENT',
                sent_at=datetime.utcnow()
            )
            db.session.add(notif_mgr)
            created_notifs.append(notif_mgr)

        # 3. Dispatch to Caretakers (On-site notification that tenant has cleared/paid)
        caretakers = User.query.join(Role).filter(
            Role.name == 'CARETAKER',
            User.is_active.is_(True)
        ).all()
        for ct in caretakers:
            ct_msg = (
                f"CARETAKER PAYMENT NOTICE\n"
                f"Room/Unit {unit.unit_number} in {prop.name} has been paid by {tenant.full_name}.\n"
                f"Amount: {payment.amount_display} (Ref: {payment.transaction_reference or 'N/A'}).\n"
                f"Current Status: Rent Paid / Confirmed. Update physical inspection records."
            )
            notif_ct = Notification(
                recipient_user_id=ct.id,
                landlord_id=landlord.id if landlord else None,
                title=f"Caretaker Alert: Unit {unit.unit_number} Paid ({payment.amount_display})",
                message=ct_msg,
                channel='IN_APP',
                notification_type='RENT_PAYMENT_CONFIRMED',
                sent_status='SENT',
                sent_at=datetime.utcnow()
            )
            db.session.add(notif_ct)
            created_notifs.append(notif_ct)

        db.session.commit()
        return created_notifs[0] if created_notifs else None

    @staticmethod
    def send_rent_due_reminders():
        """
        Scans unpaid/pending rent invoices for the current period and dispatches rent payment reminders.
        """
        now = datetime.utcnow()
        charges = RentCharge.query.filter(
            RentCharge.period_month == now.month,
            RentCharge.period_year == now.year,
            RentCharge.status.in_(['PENDING', 'PARTIALLY_PAID'])
        ).all()

        reminders_sent = 0
        for c in charges:
            tenant = c.tenant
            unit = c.rental_unit
            prop = unit.property if unit else None
            due_str = c.due_date.strftime('%d/%m/%Y') if c.due_date else '5th of this month'
            bal_str = format_currency(c.balance_cents)

            msg = (
                f"RENT PAYMENT REMINDER\n"
                f"Dear {tenant.full_name},\n"
                f"Your rent invoice ({c.invoice_number}) for Unit {unit.unit_number} at {prop.name} is due on {due_str}.\n"
                f"Outstanding Balance: {bal_str}.\n"
                f"Please pay before the due date to avoid late payment penalty fees.\n"
                f"Pay via M-Pesa Paybill with your Unit Number ({unit.unit_number}) as the Account Number."
            )

            # In-App alert
            notif = Notification(
                landlord_id=prop.landlord_id if prop else None,
                title=f"Rent Reminder: Unit {unit.unit_number} Due ({bal_str})",
                message=msg,
                channel='SMS',
                notification_type='RENT_REMINDER',
                sent_status='SENT',
                sent_at=datetime.utcnow()
            )
            db.session.add(notif)
            reminders_sent += 1

        db.session.commit()
        return reminders_sent

    @staticmethod
    def send_late_penalty_notification(charge, penalty_amount_cents):
        """
        Notifies the tenant, manager, and landlord that rent exceeded the grace period and late fee has been added.
        """
        tenant = charge.tenant
        unit = charge.rental_unit
        prop = unit.property if unit else None
        penalty_str = format_currency(penalty_amount_cents)
        new_total_str = format_currency(charge.balance_cents)

        msg = (
            f"LATE PAYMENT PENALTY NOTICE\n"
            f"Dear {tenant.full_name},\n"
            f"Rent for Unit {unit.unit_number} ({prop.name}) was due on {charge.due_date.strftime('%d/%m/%Y')}.\n"
            f"Since payment was not received within the grace period, a late payment fee of {penalty_str} has been added.\n"
            f"Updated Total Balance Due: {new_total_str}.\n"
            f"Please settle immediately to avoid further tenancy enforcement action."
        )

        notif = Notification(
            landlord_id=prop.landlord_id if prop else None,
            title=f"Late Penalty Applied: Unit {unit.unit_number} (+{penalty_str})",
            message=msg,
            channel='IN_APP',
            notification_type='RENT_OVERDUE',
            sent_status='SENT',
            sent_at=datetime.utcnow()
        )
        db.session.add(notif)
        db.session.commit()
        return notif

    @staticmethod
    def notify_event(landlord_id, event_type, title, message):
        notif = Notification(
            landlord_id=landlord_id,
            title=title,
            message=message,
            channel='IN_APP',
            notification_type=event_type,
            sent_status='SENT',
            sent_at=datetime.utcnow()
        )
        db.session.add(notif)
        db.session.commit()
        return notif
