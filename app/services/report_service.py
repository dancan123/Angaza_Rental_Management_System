import io
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from app.models.finance import RentCharge, Payment
from app.models.maintenance import Expense
from app.models.property import RentalUnit
from app.models.user import Landlord
from app.services.personalization_service import PersonalizationService
from app.utils.currency import from_cents

class ReportService:
    @staticmethod
    def get_collection_report(start_date=None, end_date=None, property_id=None, payment_method=None):
        query = Payment.query.filter_by(payment_status='CONFIRMED')
        if start_date:
            query = query.filter(Payment.payment_date >= start_date)
        if end_date:
            query = query.filter(Payment.payment_date <= end_date)
        if property_id:
            query = query.filter(Payment.property_id == property_id)
        if payment_method:
            query = query.filter(Payment.payment_method == payment_method)

        payments = query.order_by(Payment.payment_date.desc()).all()
        total_cents = sum(p.amount_cents for p in payments)

        by_method = {}
        for p in payments:
            by_method[p.payment_method] = by_method.get(p.payment_method, 0) + p.amount_cents

        return {
            'payments': payments,
            'total_cents': total_cents,
            'by_method': by_method,
            'count': len(payments)
        }

    @staticmethod
    def get_arrears_report(property_id=None):
        query = RentCharge.query.filter(RentCharge.status.in_(['UNPAID', 'PARTIALLY_PAID']))
        if property_id:
            query = query.join(RentalUnit).filter(RentalUnit.property_id == property_id)

        charges = query.order_by(RentCharge.due_date.asc()).all()
        total_arrears_cents = sum(c.balance_cents for c in charges)

        # Group by tenant
        by_tenant = {}
        for c in charges:
            t = c.tenant
            if t.id not in by_tenant:
                by_tenant[t.id] = {
                    'tenant': t,
                    'unit': c.rental_unit,
                    'total_balance_cents': 0,
                    'charges': []
                }
            by_tenant[t.id]['total_balance_cents'] += c.balance_cents
            by_tenant[t.id]['charges'].append(c)

        return {
            'charges': charges,
            'total_arrears_cents': total_arrears_cents,
            'by_tenant': list(by_tenant.values()),
            'count': len(charges)
        }

    @staticmethod
    def get_income_statement(start_date=None, end_date=None, property_id=None):
        # 1. Total rent collected
        pay_query = Payment.query.filter_by(payment_status='CONFIRMED')
        exp_query = Expense.query

        if start_date:
            pay_query = pay_query.filter(Payment.payment_date >= start_date)
            exp_query = exp_query.filter(Expense.expense_date >= start_date)
        if end_date:
            pay_query = pay_query.filter(Payment.payment_date <= end_date)
            exp_query = exp_query.filter(Expense.expense_date <= end_date)
        if property_id:
            pay_query = pay_query.filter(Payment.property_id == property_id)
            exp_query = exp_query.filter(Expense.property_id == property_id)

        payments = pay_query.all()
        expenses = exp_query.order_by(Expense.expense_date.desc()).all()

        total_income_cents = sum(p.amount_cents for p in payments)
        total_expenses_cents = sum(e.amount_cents for e in expenses)
        net_operating_income_cents = total_income_cents - total_expenses_cents

        # Categorize expenses
        exp_by_category = {}
        for e in expenses:
            exp_by_category[e.category] = exp_by_category.get(e.category, 0) + e.amount_cents

        return {
            'total_income_cents': total_income_cents,
            'total_expenses_cents': total_expenses_cents,
            'net_operating_income_cents': net_operating_income_cents,
            'expenses': expenses,
            'exp_by_category': exp_by_category
        }

    @staticmethod
    def get_landlord_statement(landlord_id, start_date=None, end_date=None):
        landlord = Landlord.query.get_or_404(landlord_id)
        prop_ids = [p.id for p in landlord.properties.all()]

        pay_query = Payment.query.filter(Payment.property_id.in_(prop_ids), Payment.payment_status == 'CONFIRMED') if prop_ids else Payment.query.filter(Payment.id == -1)
        exp_query = Expense.query.filter(Expense.property_id.in_(prop_ids)) if prop_ids else Expense.query.filter(Expense.id == -1)

        if start_date:
            pay_query = pay_query.filter(Payment.payment_date >= start_date)
            exp_query = exp_query.filter(Expense.expense_date >= start_date)
        if end_date:
            pay_query = pay_query.filter(Payment.payment_date <= end_date)
            exp_query = exp_query.filter(Expense.expense_date <= end_date)

        payments = pay_query.all()
        expenses = exp_query.all()

        gross_cents = sum(p.amount_cents for p in payments)
        exp_cents = sum(e.amount_cents for e in expenses)
        net_cents = gross_cents - exp_cents

        return {
            'landlord': landlord,
            'properties': landlord.properties.all(),
            'payments': payments,
            'expenses': expenses,
            'gross_income_cents': gross_cents,
            'total_expenses_cents': exp_cents,
            'net_payout_cents': net_cents
        }

    # ------------------ EXCEL EXPORT HELPERS ------------------
    @staticmethod
    def export_collection_excel(report_data):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Rent Collections"

        currency = PersonalizationService.get_setting('currency', 'KES')
        biz_name = PersonalizationService.get_setting('business_name', 'Property Management')

        # Title Header
        ws.merge_cells('A1:G1')
        ws['A1'] = f"{biz_name} - Rent Collection Report"
        ws['A1'].font = Font(name='Arial', size=14, bold=True, color='FFFFFF')
        ws['A1'].fill = PatternFill(start_color='1A56DB', end_color='1A56DB', fill_type='solid')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 30

        # Subtitle
        ws.merge_cells('A2:G2')
        ws['A2'] = f"Generated on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} | Total Collected: {currency} {from_cents(report_data['total_cents']):,.2f}"
        ws['A2'].font = Font(name='Arial', size=10, italic=True)
        ws['A2'].alignment = Alignment(horizontal='center', vertical='center')

        # Column Headers
        headers = ["Receipt No", "Date", "Property", "Unit", "Tenant", "Payment Method", f"Amount ({currency})"]
        ws.append([])
        ws.append(headers)
        header_row = 4

        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=header_row, column=col_idx)
            cell.font = Font(name='Arial', size=10, bold=True, color='FFFFFF')
            cell.fill = PatternFill(start_color='2563EB', end_color='2563EB', fill_type='solid')
            cell.alignment = Alignment(horizontal='center' if col_idx != 5 else 'left')

        # Data Rows
        for p in report_data['payments']:
            ws.append([
                p.receipt_number,
                p.payment_date.strftime('%Y-%m-%d'),
                p.rental_unit.property.name,
                p.rental_unit.unit_number,
                p.tenant.full_name,
                p.payment_method,
                float(from_cents(p.amount_cents))
            ])

        # Summary Total Row
        total_row = ws.max_row + 1
        ws.cell(row=total_row, column=6, value="TOTAL:")
        ws.cell(row=total_row, column=6).font = Font(name='Arial', bold=True)
        total_cell = ws.cell(row=total_row, column=7, value=float(from_cents(report_data['total_cents'])))
        total_cell.font = Font(name='Arial', bold=True, color='16A34A')

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return out.getvalue()






    @staticmethod
    def export_arrears_excel(report_data):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Tenant Arrears"

        currency = PersonalizationService.get_setting('currency', 'KES')
        biz_name = PersonalizationService.get_setting('business_name', 'Property Management')

        # Title
        ws.merge_cells('A1:G1')
        ws['A1'] = f"{biz_name} - Tenant Arrears & Overdue Balances"
        ws['A1'].font = Font(name='Arial', size=14, bold=True, color='FFFFFF')
        ws['A1'].fill = PatternFill(start_color='DC2626', end_color='DC2626', fill_type='solid')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 30

        headers = ["Invoice No", "Tenant", "Telephone", "Property", "Unit", "Due Date", f"Outstanding Arrears ({currency})"]
        ws.append([])
        ws.append(headers)
        header_row = 3

        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=header_row, column=col_idx)
            cell.font = Font(name='Arial', size=10, bold=True, color='FFFFFF')
            cell.fill = PatternFill(start_color='EF4444', end_color='EF4444', fill_type='solid')

        for c in report_data['charges']:
            ws.append([
                c.invoice_number,
                c.tenant.full_name,
                c.tenant.phone,
                c.rental_unit.property.name,
                c.rental_unit.unit_number,
                c.due_date.strftime('%Y-%m-%d'),
                float(from_cents(c.balance_cents))
            ])

        total_row = ws.max_row + 1
        ws.cell(row=total_row, column=6, value="TOTAL ARREARS:")
        ws.cell(row=total_row, column=6).font = Font(name='Arial', bold=True)
        total_cell = ws.cell(row=total_row, column=7, value=float(from_cents(report_data['total_arrears_cents'])))
        total_cell.font = Font(name='Arial', bold=True, color='DC2626')

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return out.getvalue()








    @staticmethod
    def export_vacant_houses_excel(property_id=None):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Vacant Houses & Rooms"

        currency = PersonalizationService.get_setting('currency', 'KES')
        biz_name = PersonalizationService.get_setting('business_name', 'Property Management System')

        # Title block
        ws.merge_cells('A1:L1')
        ws['A1'] = f"{biz_name} — Vacant Houses & Available Rental Units"
        ws['A1'].font = Font(name='Arial', size=14, bold=True, color='FFFFFF')
        ws['A1'].fill = PatternFill(start_color='0E9F6E', end_color='0E9F6E', fill_type='solid')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 32

        headers = [
            "Unit Number", "Property Name", "Physical Location", "Building", "Floor", 
            "Unit Type", f"Monthly Rent ({currency})", f"Deposit Required ({currency})", 
            "Bedrooms", "Bathrooms", "Amenities & Description", "Availability"
        ]
        ws.append([])
        ws.append(headers)
        header_row = 3

        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=header_row, column=col_idx)
            cell.font = Font(name='Arial', size=10, bold=True, color='FFFFFF')
            cell.fill = PatternFill(start_color='10B981', end_color='10B981', fill_type='solid')
            cell.alignment = Alignment(horizontal='center' if col_idx in [1, 6, 9, 10, 12] else 'left')

        query = RentalUnit.query.filter_by(occupancy_status='VACANT')
        if property_id:
            query = query.filter_by(property_id=property_id)
        vacant_units = query.order_by(RentalUnit.property_id.asc(), RentalUnit.unit_number.asc()).all()

        total_potential_rent = 0
        for u in vacant_units:
            rent_val = float(from_cents(u.rent_amount_cents))
            dep_val = float(from_cents(u.deposit_amount_cents))
            total_potential_rent += rent_val

            bldg_name = u.building.name if u.building else 'Main'
            floor_name = u.floor.floor_name if u.floor else 'Ground'
            
            ws.append([
                u.unit_number,
                u.property.name if u.property else '—',
                u.property.location if u.property else '—',
                bldg_name,
                floor_name,
                u.unit_type,
                rent_val,
                dep_val,
                u.bedrooms,
                u.bathrooms,
                u.amenities or u.description or 'Standard Finishes',
                u.availability_date.strftime('%Y-%m-%d') if u.availability_date else 'Immediate'
            ])

        # Summary Row
        summary_row = ws.max_row + 1
        ws.cell(row=summary_row, column=6, value=f"TOTAL VACANT UNITS: {len(vacant_units)}").font = Font(name='Arial', bold=True)
        tot_rent_cell = ws.cell(row=summary_row, column=7, value=total_potential_rent)
        tot_rent_cell.font = Font(name='Arial', bold=True, color='0E9F6E')
        tot_rent_cell.number_format = '#,##0.00'

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return out.getvalue()
