import csv
import io
from datetime import datetime, date
import openpyxl
from app.extensions import db
from app.models.gateway import BankAccount, BankTransaction
from app.models.property import RentalUnit
from app.models.tenant import Tenant
from app.services.payment_service import PaymentService
from app.services.audit_service import AuditService
from app.utils.currency import to_cents

class BankService:
    @staticmethod
    def create_bank_account(bank_name, account_name, account_number, branch=None, currency='KES', landlord_id=None, property_id=None):
        acc = BankAccount(
            bank_name=bank_name.strip(),
            account_name=account_name.strip(),
            account_number=account_number.strip(),
            branch=branch.strip() if branch else None,
            currency=currency.upper(),
            landlord_id=landlord_id,
            property_id=property_id,
            is_active=True
        )
        db.session.add(acc)
        db.session.commit()
        AuditService.log('CREATE_BANK_ACCOUNT', 'BankAccount', acc.id, new_values={'bank': bank_name, 'acc': account_number})
        return acc

    @staticmethod
    def parse_and_import_statement(bank_account_id: int, file_stream, filename: str):
        """
        Parses CSV or Excel bank statement and imports credit transactions into the reconciliation ledger.
        Runs the automated matching algorithm on newly imported rows.
        """
        bank_account = BankAccount.query.get_or_404(bank_account_id)
        imported_count = 0
        matched_count = 0
        lower_name = filename.lower()

        rows = []
        if lower_name.endswith('.csv'):
            stream = io.StringIO(file_stream.read().decode('utf-8', errors='ignore'))
            reader = csv.reader(stream)
            headers = [h.strip().lower() for h in next(reader, [])]
            for row in reader:
                if row and any(row):
                    rows.append(row)
        elif lower_name.endswith('.xlsx') or lower_name.endswith('.xls'):
            wb = openpyxl.load_workbook(file_stream, data_only=True)
            ws = wb.active
            iter_rows = ws.iter_rows(values_only=True)
            headers = [str(h or '').strip().lower() for h in next(iter_rows, [])]
            for row in iter_rows:
                if row and any(row):
                    rows.append([str(c or '') for c in row])
        else:
            raise ValueError("Unsupported format. Please upload a CSV or XLSX bank statement.")

        # Determine column indexes with fuzzy mapping
        # Common bank statement headers: Date, Reference, Particulars/Description, Credit/Amount
        date_idx = 0
        ref_idx = 1
        desc_idx = 2
        amount_idx = 3

        for idx, h in enumerate(headers):
            if any(k in h for k in ['date', 'trans date', 'value date']):
                date_idx = idx
            elif any(k in h for k in ['ref', 'reference', 'trn id', 'cheque']):
                ref_idx = idx
            elif any(k in h for k in ['description', 'particulars', 'narration', 'details']):
                desc_idx = idx
            elif any(k in h for k in ['credit', 'deposit', 'amount', 'cr']):
                amount_idx = idx

        for r in rows:
            if len(r) <= max(date_idx, desc_idx, amount_idx):
                continue

            raw_date = str(r[date_idx]).strip()
            raw_ref = str(r[ref_idx]).strip() if len(r) > ref_idx else f"TX-{datetime.utcnow().strftime('%f')}"
            raw_desc = str(r[desc_idx]).strip()
            raw_amount = str(r[amount_idx]).replace(',', '').replace('KES', '').strip()

            # Skip header or zero/debit rows
            try:
                amount_val = float(raw_amount)
                if amount_val <= 0:
                    continue
            except ValueError:
                continue

            # Parse transaction date
            trans_date = date.today()
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
                try:
                    trans_date = datetime.strptime(raw_date.split()[0], fmt).date()
                    break
                except Exception:
                    pass

            cents = to_cents(amount_val)

            # Check if reference already exists for this bank account
            existing = BankTransaction.query.filter_by(bank_account_id=bank_account.id, reference=raw_ref).first()
            if existing:
                continue

            tx = BankTransaction(
                bank_account_id=bank_account.id,
                transaction_date=trans_date,
                reference=raw_ref,
                description=raw_desc,
                amount_cents=cents,
                transaction_type='CREDIT',
                reconciliation_status='UNMATCHED'
            )
            db.session.add(tx)
            db.session.flush()
            imported_count += 1

            # Run automated matching logic
            matched_unit = BankService._auto_match_unit(raw_desc)
            if matched_unit and matched_unit.current_tenant:
                tx.reconciliation_status = 'MATCHED'
                matched_count += 1

        db.session.commit()
        return {'imported_count': imported_count, 'matched_count': matched_count}

    @staticmethod
    def _auto_match_unit(narration: str):
        """
        Scans narration for rental unit numbers (e.g. A-101, B12, SHOP-4) or tenant names.
        """
        units = RentalUnit.query.all()
        clean_narration = narration.upper()
        for u in units:
            if u.unit_number.upper() in clean_narration:
                return u
        return None

    @staticmethod
    def reconcile_transaction(transaction_id: int, tenant_id: int, user_id=None):
        """
        Accountant verifies unmatched transaction, links to tenant, creates confirmed payment & receipt.
        """
        tx = BankTransaction.query.get_or_404(transaction_id)
        if tx.reconciliation_status in ['MANUALLY_RECONCILED']:
            raise ValueError("This bank transaction has already been reconciled.")

        tenant = Tenant.query.get_or_404(tenant_id)
        unit = tenant.current_unit
        if not unit:
            raise ValueError(f"Tenant {tenant.full_name} does not have an active unit assigned.")

        # Record payment through payment service
        payment = PaymentService.record_payment(
            tenant_id=tenant.id,
            amount=tx.amount_display.split()[-1].replace(',', ''),
            payment_method='BANK_TRANSFER',
            rental_unit_id=unit.id,
            property_id=unit.property_id,
            payment_date=tx.transaction_date,
            transaction_reference=tx.reference,
            description=f"Bank statement reconciliation: {tx.description}",
            user_id=user_id,
            auto_confirm=True
        )

        tx.reconciliation_status = 'MANUALLY_RECONCILED'
        tx.matched_payment_id = payment.id
        tx.reconciled_by_user_id = user_id
        tx.reconciled_at = datetime.utcnow()

        db.session.commit()
        AuditService.log('RECONCILE_BANK_TX', 'BankTransaction', tx.id, new_values={'payment_id': payment.id, 'tenant': tenant.full_name})
        return payment

    @staticmethod
    def ignore_transaction(transaction_id: int, user_id=None):
        tx = BankTransaction.query.get_or_404(transaction_id)
        tx.reconciliation_status = 'IGNORED'
        tx.reconciled_by_user_id = user_id
        tx.reconciled_at = datetime.utcnow()
        db.session.commit()
        return tx

