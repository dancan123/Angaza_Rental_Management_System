import io
from datetime import datetime, date, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from app.extensions import db
from app.models.lease import Lease
from app.models.property import RentalUnit
from app.models.tenant import Tenant
from app.services.personalization_service import PersonalizationService
from app.services.audit_service import AuditService
from app.utils.currency import to_cents

class LeaseService:
    @staticmethod
    def create_lease(rental_unit_id: int, tenant_id: int, start_date: date, monthly_rent: float, deposit_amount: float, end_date: date = None, payment_due_day: int = 5, notice_period_days: int = 30, terms_and_conditions: str = None):
        unit = RentalUnit.query.get_or_404(rental_unit_id)
        tenant = Tenant.query.get_or_404(tenant_id)

        lease_no = f"LSE-{unit.unit_number}-{datetime.utcnow().strftime('%Y%m%d%H%M')}"
        rent_cents = to_cents(monthly_rent)
        deposit_cents = to_cents(deposit_amount)

        # Default standard lease terms if none provided
        if not terms_and_conditions:
            terms_and_conditions = (
                "1. The Tenant shall pay rent on or before the due date specified without deduction.\n"
                "2. The Tenant shall use the demised premises strictly for private residential purposes.\n"
                "3. The Tenant shall not assign, sublet, or part with possession of the premises without written consent.\n"
                "4. Either party may terminate this agreement by issuing the agreed written notice period.\n"
                "5. The security deposit is refundable upon termination subject to inspection and deduction for damages."
            )

        lease = Lease(
            lease_number=lease_no,
            rental_unit_id=unit.id,
            tenant_id=tenant.id,
            start_date=start_date,
            end_date=end_date,
            monthly_rent_cents=rent_cents,
            deposit_cents=deposit_cents,
            payment_due_day=payment_due_day,
            notice_period_days=notice_period_days,
            terms_and_conditions=terms_and_conditions,
            status='ACTIVE'
        )
        db.session.add(lease)

        # Update unit and tenant assignment
        unit.occupancy_status = 'OCCUPIED'
        unit.current_tenant_id = tenant.id
        tenant.is_active = True

        db.session.commit()
        AuditService.log('CREATE_LEASE', 'Lease', lease.id, new_values={'lease_no': lease_no, 'unit': unit.unit_number, 'tenant': tenant.full_name})
        return lease

    @staticmethod
    def get_expiring_leases(days_ahead=30):
        cutoff = date.today() + timedelta(days=days_ahead)
        return Lease.query.filter(
            Lease.status == 'ACTIVE',
            Lease.end_date != None,
            Lease.end_date <= cutoff
        ).order_by(Lease.end_date.asc()).all()

    @staticmethod
    def generate_lease_pdf(lease: Lease):
        """
        Generates a formal legal Tenancy Agreement PDF using ReportLab.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        settings = PersonalizationService.get_all_settings()
        biz_name = settings.get('business_name', 'Property Management Agency')
        biz_addr = settings.get('business_address', 'Nairobi, Kenya')
        landlord_name = lease.rental_unit.property.landlord.name

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'AgreementTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=16,
            textColor=colors.HexColor('#1a56db'),
            alignment=1, # Center
            spaceAfter=6
        )
        subtitle_style = ParagraphStyle(
            'AgreementSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            alignment=1,
            textColor=colors.HexColor('#475569')
        )
        body_style = ParagraphStyle(
            'AgreementBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#1e293b')
        )
        bold_style = ParagraphStyle(
            'AgreementBold',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            textColor=colors.HexColor('#1e293b')
        )

        story = []

        # 1. Agreement Header
        story.append(Paragraph(f"<b>{biz_name.upper()}</b>", title_style))
        story.append(Paragraph("<b>STANDARD RESIDENTIAL TENANCY AGREEMENT</b>", title_style))
        story.append(Paragraph(f"Agreement Reference: <b>{lease.lease_number}</b> | Execution Date: {lease.signed_at.strftime('%d/%m/%Y')}", subtitle_style))
        story.append(Spacer(1, 15))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1a56db'), spaceAfter=15))

        # 2. Parties Clause
        parties_text = (
            f"THIS TENANCY AGREEMENT is made between <b>{landlord_name}</b> (represented by <b>{biz_name}</b>, {biz_addr}) "
            f"(hereinafter called the '<b>LANDLORD</b>') of the one part, and <b>{lease.tenant.full_name}</b>, "
            f"Holder of National ID/Passport No. <b>{lease.tenant.id_passport_number}</b>, Telephone: <b>{lease.tenant.phone}</b> "
            f"(hereinafter called the '<b>TENANT</b>') of the other part."
        )
        story.append(Paragraph(parties_text, body_style))
        story.append(Spacer(1, 12))

        # 3. Schedule Table
        unit = lease.rental_unit
        end_date_str = lease.end_date.strftime('%d/%m/%Y') if lease.end_date else "Periodic (Month to Month)"
        schedule_data = [
            [Paragraph("<b>PROPERTY / PREMISES:</b>", bold_style), Paragraph(f"{unit.property.name}, {unit.property.location}", body_style)],
            [Paragraph("<b>RENTAL UNIT NUMBER:</b>", bold_style), Paragraph(f"{unit.unit_number} ({unit.unit_type})", body_style)],
            [Paragraph("<b>COMMENCEMENT DATE:</b>", bold_style), Paragraph(lease.start_date.strftime('%d/%m/%Y'), body_style)],
            [Paragraph("<b>EXPIRATION DATE:</b>", bold_style), Paragraph(end_date_str, body_style)],
            [Paragraph("<b>MONTHLY RENT:</b>", bold_style), Paragraph(f"<b>{lease.rent_display}</b> (Payable on/before the {lease.payment_due_day}th of every month)", body_style)],
            [Paragraph("<b>SECURITY DEPOSIT:</b>", bold_style), Paragraph(f"<b>{lease.deposit_display}</b> (Refundable under contract terms)", body_style)],
            [Paragraph("<b>NOTICE PERIOD:</b>", bold_style), Paragraph(f"{lease.notice_period_days} Days written notice prior to termination", body_style)]
        ]
        sched_table = Table(schedule_data, colWidths=[170, 370])
        sched_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(sched_table)
        story.append(Spacer(1, 15))

        # 4. Standard Terms & Conditions
        story.append(Paragraph("<b>SPECIAL COVENANTS, TERMS AND CONDITIONS:</b>", bold_style))
        story.append(Spacer(1, 4))
        for line in (lease.terms_and_conditions or "").splitlines():
            if line.strip():
                story.append(Paragraph(line.strip(), body_style))
                story.append(Spacer(1, 3))

        story.append(Spacer(1, 25))

        # 5. Signatures Block
        sig_data = [
            [
                Paragraph("<b>FOR THE LANDLORD / AGENT:</b><br/><br/>Signature: ______________________<br/>Name: Authorized Signatory<br/>Date: ________________________", body_style),
                Paragraph(f"<b>FOR THE TENANT:</b><br/><br/>Signature: ______________________<br/>Name: {lease.tenant.full_name}<br/>Date: ________________________", body_style)
            ]
        ]
        sig_table = Table(sig_data, colWidths=[270, 270])
        story.append(sig_table)

        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

