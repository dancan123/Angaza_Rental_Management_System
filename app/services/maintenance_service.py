from datetime import date
from app.extensions import db
from app.models.maintenance import Expense, MaintenanceRequest, MaintenanceRecord
from app.models.property import RentalUnit
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.utils.currency import to_cents

class MaintenanceService:
    @staticmethod
    def log_request(rental_unit_id: int, title: str, description: str, priority='MEDIUM', tenant_id=None, photo_url=None):
        unit = RentalUnit.query.get_or_404(rental_unit_id)
        effective_tenant_id = tenant_id or unit.current_tenant_id

        req = MaintenanceRequest(
            rental_unit_id=unit.id,
            tenant_id=effective_tenant_id,
            title=title.strip(),
            description=description.strip(),
            priority=priority,
            status='PENDING',
            reported_date=date.today(),
            photo_url=photo_url
        )
        db.session.add(req)
        db.session.commit()

        # Notify Landlord of maintenance request
        if unit.property and unit.property.landlord:
            NotificationService.notify_event(
                landlord_id=unit.property.landlord.id,
                event_type='MAINTENANCE_LOGGED',
                title=f"Maintenance Ticket: {unit.unit_number} - {title}",
                message=f"New {priority} maintenance issue reported for Unit {unit.unit_number} ({unit.property.name}): {title} - {description}"
            )

        AuditService.log('LOG_MAINTENANCE', 'MaintenanceRequest', req.id, new_values={'unit': unit.unit_number, 'priority': priority})
        return req

    @staticmethod
    def assign_technician(request_id: int, technician_name: str, technician_contact: str = None):
        req = MaintenanceRequest.query.get_or_404(request_id)
        req.assigned_to_technician = technician_name.strip()
        req.technician_contact = technician_contact.strip() if technician_contact else None
        req.status = 'ASSIGNED'
        db.session.commit()
        return req

    @staticmethod
    def resolve_request(request_id: int, work_summary: str, cost=0, completed_by=None, user_id=None):
        req = MaintenanceRequest.query.get_or_404(request_id)
        cost_cents = to_cents(cost)

        expense = None
        if cost_cents > 0:
            # Automatically create linked property expense
            expense = Expense(
                property_id=req.rental_unit.property_id,
                rental_unit_id=req.rental_unit_id,
                category='REPAIRS',
                amount_cents=cost_cents,
                expense_date=date.today(),
                supplier_name=completed_by or req.assigned_to_technician,
                description=f"Repair Cost for Ticket #{req.id}: {req.title} - {work_summary}",
                recorded_by_user_id=user_id
            )
            db.session.add(expense)
            db.session.flush()

        record = MaintenanceRecord(
            maintenance_request_id=req.id,
            expense_id=expense.id if expense else None,
            work_summary=work_summary.strip(),
            cost_cents=cost_cents,
            completed_by=completed_by or req.assigned_to_technician,
            completion_date=date.today()
        )
        db.session.add(record)

        req.status = 'RESOLVED'
        req.resolved_date = date.today()
        db.session.commit()

        AuditService.log('RESOLVE_MAINTENANCE', 'MaintenanceRequest', req.id, new_values={'cost': cost_cents, 'summary': work_summary})
        return record

    @staticmethod
    def record_expense(property_id: int, category: str, amount: float, description: str, rental_unit_id=None, supplier_name=None, expense_date=None, user_id=None, receipt_file_url=None):
        cents = to_cents(amount)
        exp = Expense(
            property_id=property_id,
            rental_unit_id=rental_unit_id,
            category=category,
            amount_cents=cents,
            expense_date=expense_date or date.today(),
            supplier_name=supplier_name,
            description=description,
            receipt_file_url=receipt_file_url,
            recorded_by_user_id=user_id
        )
        db.session.add(exp)
        db.session.commit()
        AuditService.log('CREATE_EXPENSE', 'Expense', exp.id, new_values={'category': category, 'amount': cents, 'property_id': property_id})
        return exp
