"""
Module providing advanced Kenyan Tenancy & Property Management PDF documents:
- Tenant Registration Form / KYC Profile
- Rent Demand Letter
- Rent Arrears Statement
- Security Deposit Receipt
- Security Deposit Refund Statement
- Move-in Condition Inspection Report
- Move-out Condition Inspection Report
- Tenancy Renewal Agreement Addendum
- Maintenance Work Order
- Property Occupancy Report
"""
import io
from datetime import datetime, date
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from app.services.personalization_service import PersonalizationService
from app.utils.currency import format_currency


def _get_org_meta(entity):
    org = None
    if hasattr(entity, 'organization') and entity.organization:
        org = entity.organization
    elif hasattr(entity, 'property') and entity.property and getattr(entity.property, 'organization', None):
        org = entity.property.organization
    elif hasattr(entity, 'rental_unit') and entity.rental_unit and entity.rental_unit.property:
        org = getattr(entity.rental_unit.property, 'organization', None)

    org_id = org.id if org else None
    settings = PersonalizationService.get_all_settings(organization_id=org_id)
    biz_name = (org.name if org else None) or settings.get('business_name', 'Property Management System')
    biz_addr = (f"{org.town}, {org.county}" if org and (org.town or org.county) else None) or settings.get('business_address', 'Nairobi, Kenya')
    biz_phone = (org.contact_phone if org else None) or settings.get('business_phone', '+254 700 000 000')
    biz_email = (org.contact_email if org else None) or settings.get('business_email', 'info@primerent.co.ke')
    biz_code = f"Business Code: {org.org_code} | " if org and org.org_code else ""
    return {
        'org': org,
        'biz_name': biz_name,
        'biz_addr': biz_addr,
        'biz_phone': biz_phone,
        'biz_email': biz_email,
        'biz_code': biz_code,
    }


def _get_styles():
    styles = getSampleStyleSheet()
    bold = ParagraphStyle('AdvBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#1e293b'))
    normal = ParagraphStyle('AdvNorm', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#334155'), leading=12)
    sub = ParagraphStyle('AdvSub', parent=styles['Normal'], fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#64748b'), leading=11)
    title = ParagraphStyle('AdvTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14, textColor=colors.HexColor('#1a56db'), leading=18)
    return bold, normal, sub, title


# ─────────────────────────────────────────────────────────────────────────────
# 1. Tenant Registration Form / KYC Profile
# ─────────────────────────────────────────────────────────────────────────────
def generate_tenant_registration_form_pdf(tenant):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    meta = _get_org_meta(tenant)
    bold, normal, sub, title = _get_styles()
    story = []

    # Header
    ref_no = f"REG-{tenant.id_passport_number}-{tenant.id}"
    header_data = [
        [
            Paragraph(f"<b>{meta['biz_name']}</b><br/>{meta['biz_code']}{meta['biz_addr']}<br/>Tel: {meta['biz_phone']} | Email: {meta['biz_email']}", sub),
            Paragraph(f"<font color='#1a56db'><b>TENANT REGISTRATION &amp; KYC PROFILE</b></font><br/><b>Form Ref:</b> {ref_no}<br/><b>Date:</b> {datetime.utcnow().strftime('%d/%m/%Y')}", sub)
        ]
    ]
    t = Table(header_data, colWidths=[320, 220])
    t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (1,0), (1,-1), 'RIGHT')]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1a56db'), spaceAfter=12))

    # Tenant Personal Details
    story.append(Paragraph("<b>1. PERSONAL IDENTIFICATION &amp; CONTACT INFORMATION</b>", bold))
    story.append(Spacer(1, 4))
    unit = tenant.current_unit
    lease = tenant.leases.filter_by(status='ACTIVE').first()
    info_rows = [
        [Paragraph("<b>Full Name:</b>", bold), Paragraph(tenant.full_name, normal), Paragraph("<b>National ID / Passport:</b>", bold), Paragraph(tenant.id_passport_number, normal)],
        [Paragraph("<b>Telephone:</b>", bold), Paragraph(tenant.phone, normal), Paragraph("<b>Email Address:</b>", bold), Paragraph(tenant.email or 'N/A', normal)],
        [Paragraph("<b>Occupation / Employer:</b>", bold), Paragraph(tenant.occupation or 'N/A', normal), Paragraph("<b>Physical Address:</b>", bold), Paragraph(tenant.physical_address or 'N/A', normal)],
        [Paragraph("<b>Account Status:</b>", bold), Paragraph('Active Tenant' if tenant.is_active else 'Archived', normal), Paragraph("<b>Registered On:</b>", bold), Paragraph(tenant.created_at.strftime('%d/%m/%Y'), normal)],
    ]
    t_info = Table(info_rows, colWidths=[120, 150, 130, 140])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_info)
    story.append(Spacer(1, 12))

    # Assigned Premises
    story.append(Paragraph("<b>2. ASSIGNED PREMISES &amp; TENANCY TERMS</b>", bold))
    story.append(Spacer(1, 4))
    premise_rows = [
        [Paragraph("<b>Assigned Property:</b>", bold), Paragraph(unit.property.name if unit else 'Unassigned', normal), Paragraph("<b>Unit / Room Number:</b>", bold), Paragraph(unit.unit_number if unit else 'Unassigned', normal)],
        [Paragraph("<b>Unit Type:</b>", bold), Paragraph(unit.unit_type if unit else 'N/A', normal), Paragraph("<b>Monthly Rent:</b>", bold), Paragraph(format_currency(lease.monthly_rent_cents if lease else (unit.rent_amount_cents if unit else 0)), normal)],
        [Paragraph("<b>Deposit Held:</b>", bold), Paragraph(format_currency(lease.deposit_cents if lease else 0), normal), Paragraph("<b>Lease Agreement No:</b>", bold), Paragraph(lease.lease_number if lease else 'No Active Lease', normal)],
    ]
    t_prem = Table(premise_rows, colWidths=[120, 150, 130, 140])
    t_prem.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_prem)
    story.append(Spacer(1, 12))

    # Next of Kin
    story.append(Paragraph("<b>3. NEXT OF KIN &amp; EMERGENCY CONTACT</b>", bold))
    story.append(Spacer(1, 4))
    nok = tenant.next_of_kin.first()
    nok_rows = [
        [Paragraph("<b>Contact Person:</b>", bold), Paragraph(nok.full_name if nok else (tenant.emergency_contact or 'N/A'), normal), Paragraph("<b>Relationship:</b>", bold), Paragraph(nok.relationship if nok else 'Family', normal)],
        [Paragraph("<b>Emergency Phone:</b>", bold), Paragraph(nok.phone if nok else (tenant.emergency_phone or 'N/A'), normal), Paragraph("<b>Verified KYC:</b>", bold), Paragraph("Verified by Property Manager", normal)],
    ]
    t_nok = Table(nok_rows, colWidths=[120, 150, 130, 140])
    t_nok.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_nok)
    story.append(Spacer(1, 15))

    # Signatures
    story.append(Paragraph("<b>4. DECLARATION &amp; SIGNATURES</b>", bold))
    story.append(Paragraph("I certify that the information provided above is true and accurate. I agree to abide by the tenancy terms, rules and regulations of the property.", sub))
    story.append(Spacer(1, 12))
    sig_data = [
        [Paragraph("<b>Tenant Signature:</b> ___________________________<br/>Date: ________________________", normal),
         Paragraph("<b>Property Manager:</b> ___________________________<br/>Official Stamp &amp; Date: ________________________", normal)]
    ]
    t_sig = Table(sig_data, colWidths=[270, 270])
    t_sig.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
    story.append(t_sig)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Rent Demand Letter (Notice of Default)
# ─────────────────────────────────────────────────────────────────────────────
def generate_rent_demand_letter_pdf(tenant):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    meta = _get_org_meta(tenant)
    bold, normal, sub, title = _get_styles()
    story = []

    summary = tenant.get_financial_summary() if hasattr(tenant, 'get_financial_summary') else {}
    from app.services.tenant_service import TenantService
    summary = TenantService.get_tenant_financial_summary(tenant.id)
    arrears_cents = summary.get('outstanding_cents', 0)
    unit = tenant.current_unit
    ref_no = f"DEMAND-{tenant.id_passport_number}-{datetime.utcnow().strftime('%Y%m')}"

    # Header
    header_data = [
        [
            Paragraph(f"<b>{meta['biz_name']}</b><br/>{meta['biz_code']}{meta['biz_addr']}<br/>Tel: {meta['biz_phone']} | Email: {meta['biz_email']}", sub),
            Paragraph(f"<font color='#dc2626'><b>FORMAL RENT DEMAND LETTER</b></font><br/><b>Notice Ref:</b> {ref_no}<br/><b>Date:</b> {datetime.utcnow().strftime('%d %B %Y')}", sub)
        ]
    ]
    t = Table(header_data, colWidths=[320, 220])
    t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (1,0), (1,-1), 'RIGHT')]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#dc2626'), spaceAfter=12))

    # Addressee
    story.append(Paragraph(f"<b>TO:</b> {tenant.full_name}<br/><b>TENANT ID:</b> {tenant.id_passport_number}<br/><b>UNIT:</b> {unit.unit_number if unit else 'N/A'} - {unit.property.name if unit else 'N/A'}<br/><b>TELEPHONE:</b> {tenant.phone}", normal))
    story.append(Spacer(1, 12))

    # Subject
    story.append(Paragraph(f"<b>RE: DEMAND FOR PAYMENT OF OVERDUE RENT ARREARS — {format_currency(arrears_cents).upper()}</b>", bold))
    story.append(Spacer(1, 8))

    body_text = (
        f"This letter serves as formal notice that your rent account for Unit <b>{unit.unit_number if unit else 'N/A'}</b> at "
        f"<b>{unit.property.name if unit else 'the premises'}</b> is currently in default with an outstanding balance of "
        f"<b>{format_currency(arrears_cents)}</b> as of <b>{datetime.utcnow().strftime('%d %B %Y')}</b>.<br/><br/>"
        "Under the terms of your Tenancy Agreement and Kenyan tenancy legislation, rent is payable on or before the agreed due date. "
        "Despite earlier reminders, the aforementioned amount remains unpaid.<br/><br/>"
        "<b>YOU ARE HEREBY GIVEN SEVEN (7) DAYS</b> from the date of this letter to settle the entire outstanding sum. "
        "Failure to clear the balance or agree upon an approved payment arrangement will lead to immediate escalation, including "
        "statutory penalty charges, issuance of a formal Notice to Vacate, and legal proceedings to recover the arrears at your cost."
    )
    story.append(Paragraph(body_text, normal))
    story.append(Spacer(1, 12))

    # Overdue Invoices Breakdown
    from app.models.finance import RentCharge
    all_charges = tenant.rent_charges.order_by(RentCharge.due_date.asc()).all()
    charges = [c for c in all_charges if c.balance_cents > 0]
    rows = [[Paragraph("<b>Invoice No</b>", bold), Paragraph("<b>Period / Description</b>", bold), Paragraph("<b>Due Date</b>", bold), Paragraph("<b>Overdue Balance</b>", bold)]]
    for c in charges[:10]:
        rows.append([
            Paragraph(c.invoice_number, normal),
            Paragraph(f"{c.period_month}/{c.period_year} ({c.charge_type})", normal),
            Paragraph(c.due_date.strftime('%d/%m/%Y'), normal),
            Paragraph(format_currency(c.balance_cents), bold)
        ])
    rows.append([Paragraph("<b>TOTAL AMOUNT DUE IMMEDIATELY:</b>", bold), "", "", Paragraph(f"<b>{format_currency(arrears_cents)}</b>", bold)])

    t_chg = Table(rows, colWidths=[120, 180, 110, 130])
    t_chg.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#fee2e2')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#fca5a5')),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#fef2f2')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_chg)
    story.append(Spacer(1, 15))

    # Payment Channels
    story.append(Paragraph("<b>HOW TO PAY:</b> Please settle via official property payment channels (M-Pesa Paybill / Till or Bank). Quote your Unit Number or Tenant Name as account reference. Retain your payment confirmation.", normal))
    story.append(Spacer(1, 15))

    # Signoff
    sig_data = [
        [Paragraph(f"Yours faithfully,<br/><br/><b>Estate Management &amp; Accounts</b><br/>{meta['biz_name']}<br/>Tel: {meta['biz_phone']}", normal),
         Paragraph("<b>Tenant Acknowledgment:</b><br/><br/>Signature: __________________________<br/>Date: _______________________________", normal)]
    ]
    t_sig = Table(sig_data, colWidths=[300, 240])
    t_sig.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
    story.append(t_sig)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Rent Arrears Statement
# ─────────────────────────────────────────────────────────────────────────────
def generate_rent_arrears_statement_pdf(tenant):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    meta = _get_org_meta(tenant)
    bold, normal, sub, title = _get_styles()
    story = []

    from app.services.tenant_service import TenantService
    summary = TenantService.get_tenant_financial_summary(tenant.id)
    arrears_cents = summary.get('outstanding_cents', 0)
    unit = tenant.current_unit
    ref_no = f"ARR-{tenant.id_passport_number}-{tenant.id}"

    # Header
    header_data = [
        [
            Paragraph(f"<b>{meta['biz_name']}</b><br/>{meta['biz_code']}{meta['biz_addr']}<br/>Tel: {meta['biz_phone']} | Email: {meta['biz_email']}", sub),
            Paragraph(f"<font color='#dc2626'><b>STATEMENT OF RENT ARREARS</b></font><br/><b>Ref:</b> {ref_no}<br/><b>As Of:</b> {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}", sub)
        ]
    ]
    t = Table(header_data, colWidths=[320, 220])
    t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (1,0), (1,-1), 'RIGHT')]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#dc2626'), spaceAfter=12))

    # Tenant Details
    tenant_info = [
        [Paragraph("<b>Tenant Name:</b>", bold), Paragraph(tenant.full_name, normal), Paragraph("<b>National ID:</b>", bold), Paragraph(tenant.id_passport_number, normal)],
        [Paragraph("<b>Assigned Unit:</b>", bold), Paragraph(f"{unit.unit_number} ({unit.property.name})" if unit else 'Unassigned', normal), Paragraph("<b>Phone:</b>", bold), Paragraph(tenant.phone, normal)],
        [Paragraph("<b>Current Arrears:</b>", bold), Paragraph(f"<font color='#dc2626'><b>{format_currency(arrears_cents)}</b></font>", bold), Paragraph("<b>Status:</b>", bold), Paragraph("OVERDUE" if arrears_cents > 0 else "ZERO ARREARS", normal)],
    ]
    t_ti = Table(tenant_info, colWidths=[110, 160, 110, 160])
    t_ti.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_ti)
    story.append(Spacer(1, 12))

    # Charges Table
    story.append(Paragraph("<b>ITEMIZED OVERDUE INVOICES &amp; UNPAID CHARGES</b>", bold))
    story.append(Spacer(1, 4))
    from app.models.finance import RentCharge
    charges = tenant.rent_charges.order_by(RentCharge.due_date.asc()).all()
    rows = [[Paragraph("<b>Invoice No</b>", bold), Paragraph("<b>Period</b>", bold), Paragraph("<b>Due Date</b>", bold), Paragraph("<b>Billed</b>", bold), Paragraph("<b>Paid</b>", bold), Paragraph("<b>Balance Due</b>", bold)]]
    for c in charges:
        if c.balance_cents > 0:
            rows.append([
                Paragraph(c.invoice_number, normal),
                Paragraph(f"{c.period_month}/{c.period_year}", normal),
                Paragraph(c.due_date.strftime('%d/%m/%Y'), normal),
                Paragraph(format_currency(c.amount_cents), normal),
                Paragraph(format_currency(c.amount_paid_cents), normal),
                Paragraph(f"<b>{format_currency(c.balance_cents)}</b>", bold)
            ])
    rows.append(["", "", "", Paragraph("<b>TOTAL DUE:</b>", bold), "", Paragraph(f"<b>{format_currency(arrears_cents)}</b>", bold)])

    t_chg = Table(rows, colWidths=[95, 65, 80, 100, 100, 100])
    t_chg.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#fee2e2')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#fca5a5')),
        ('ALIGN', (3,0), (-1,-1), 'RIGHT'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_chg)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Please reconcile or settle the overdue amount at your earliest convenience to avoid tenancy suspension.", sub))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Security Deposit Receipt
# ─────────────────────────────────────────────────────────────────────────────
def generate_deposit_receipt_pdf(lease):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    meta = _get_org_meta(lease)
    bold, normal, sub, title = _get_styles()
    story = []

    tenant = lease.tenant
    unit = lease.rental_unit
    ref_no = f"DEP-REC-{lease.lease_number}"

    # Header
    header_data = [
        [
            Paragraph(f"<b>{meta['biz_name']}</b><br/>{meta['biz_code']}{meta['biz_addr']}<br/>Tel: {meta['biz_phone']} | Email: {meta['biz_email']}", sub),
            Paragraph(f"<font color='#0e9f6e'><b>OFFICIAL SECURITY DEPOSIT RECEIPT</b></font><br/><b>Receipt Ref:</b> {ref_no}<br/><b>Date:</b> {lease.created_at.strftime('%d/%m/%Y')}", sub)
        ]
    ]
    t = Table(header_data, colWidths=[320, 220])
    t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (1,0), (1,-1), 'RIGHT')]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0e9f6e'), spaceAfter=12))

    # Body
    rows = [
        [Paragraph("<b>Received From:</b>", bold), Paragraph(tenant.full_name, normal), Paragraph("<b>National ID:</b>", bold), Paragraph(tenant.id_passport_number, normal)],
        [Paragraph("<b>Property Name:</b>", bold), Paragraph(unit.property.name, normal), Paragraph("<b>Unit / Room:</b>", bold), Paragraph(unit.unit_number, normal)],
        [Paragraph("<b>Deposit Amount:</b>", bold), Paragraph(f"<font color='#0e9f6e'><b>{format_currency(lease.deposit_cents)}</b></font>", bold), Paragraph("<b>Lease Ref:</b>", bold), Paragraph(lease.lease_number, normal)],
        [Paragraph("<b>Status:</b>", bold), Paragraph("HELD IN TRUST (REFUNDABLE)", normal), Paragraph("<b>Start Date:</b>", bold), Paragraph(lease.start_date.strftime('%d/%m/%Y'), normal)],
    ]
    t_b = Table(rows, colWidths=[120, 150, 130, 140])
    t_b.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_b)
    story.append(Spacer(1, 15))

    terms = (
        "<b>TERMS OF SECURITY DEPOSIT:</b><br/>"
        "1. This deposit is refundable upon termination of tenancy subject to successful move-out inspection.<br/>"
        "2. The deposit cannot be used by the tenant to offset monthly rent during the active tenancy.<br/>"
        "3. Permissible deductions include repairing damages beyond normal wear and tear, settling pending utility balances (KPLC/Water), and outstanding rent arrears.<br/>"
        "4. Any net balance shall be refunded to the tenant within 14 days of keys handover."
    )
    story.append(Paragraph(terms, normal))
    story.append(Spacer(1, 20))

    sig_data = [
        [Paragraph("<b>Received By (Management):</b><br/><br/>Signature: __________________________<br/>Date: _______________________________", normal),
         Paragraph("<b>Tenant Acknowledgment:</b><br/><br/>Signature: __________________________<br/>Date: _______________________________", normal)]
    ]
    t_sig = Table(sig_data, colWidths=[270, 270])
    story.append(t_sig)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 5. Security Deposit Refund Statement
# ─────────────────────────────────────────────────────────────────────────────
def generate_deposit_refund_statement_pdf(tenant, deductions=0, refund_amount=0, notes=''):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    meta = _get_org_meta(tenant)
    bold, normal, sub, title = _get_styles()
    story = []

    unit = tenant.current_unit
    from app.models.lease import Lease
    lease = tenant.leases.order_by(Lease.created_at.desc()).first()
    gross_deposit = (lease.deposit_cents / 100) if lease else 0
    ref_no = f"DEP-REF-{tenant.id_passport_number}-{tenant.id}"

    # Header
    header_data = [
        [
            Paragraph(f"<b>{meta['biz_name']}</b><br/>{meta['biz_code']}{meta['biz_addr']}<br/>Tel: {meta['biz_phone']} | Email: {meta['biz_email']}", sub),
            Paragraph(f"<font color='#1a56db'><b>DEPOSIT REFUND &amp; CLEARANCE STATEMENT</b></font><br/><b>Ref:</b> {ref_no}<br/><b>Exit Date:</b> {datetime.utcnow().strftime('%d/%m/%Y')}", sub)
        ]
    ]
    t = Table(header_data, colWidths=[320, 220])
    t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (1,0), (1,-1), 'RIGHT')]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1a56db'), spaceAfter=12))

    rows = [
        [Paragraph("<b>Tenant Name:</b>", bold), Paragraph(tenant.full_name, normal), Paragraph("<b>National ID:</b>", bold), Paragraph(tenant.id_passport_number, normal)],
        [Paragraph("<b>Unit Vacated:</b>", bold), Paragraph(f"{unit.unit_number if unit else 'N/A'} - {unit.property.name if unit else 'N/A'}", normal), Paragraph("<b>Phone:</b>", bold), Paragraph(tenant.phone, normal)],
    ]
    t_b = Table(rows, colWidths=[120, 150, 130, 140])
    t_b.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_b)
    story.append(Spacer(1, 12))

    # Financial Reconciliation Table
    calc_rows = [
        [Paragraph("<b>Item / Description</b>", bold), Paragraph("<b>Amount (KES)</b>", bold)],
        [Paragraph("Gross Refundable Deposit Held:", normal), Paragraph(f"KES {gross_deposit:,.2f}", normal)],
        [Paragraph(f"Less: Move-Out Deductions &amp; Repairs ({notes or 'Repainting/Cleaning/Damages'}):", normal), Paragraph(f"- KES {deductions:,.2f}", normal)],
        [Paragraph("<b>NET REFUND AMOUNT PAYABLE TO TENANT:</b>", bold), Paragraph(f"<b>KES {refund_amount:,.2f}</b>", bold)],
    ]
    t_calc = Table(calc_rows, colWidths=[380, 160])
    t_calc.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_calc)
    story.append(Spacer(1, 20))

    sig_data = [
        [Paragraph("<b>Prepared By:</b><br/><br/>Management Sign: ____________________<br/>Date: _______________________________", normal),
         Paragraph("<b>Tenant Clearance &amp; Acceptance:</b><br/><br/>I accept the above reconciliation in full settlement.<br/>Signature: __________________________<br/>Date: _______________________________", normal)]
    ]
    t_sig = Table(sig_data, colWidths=[270, 270])
    story.append(t_sig)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Move-in Condition Inspection Report
# ─────────────────────────────────────────────────────────────────────────────
def generate_move_in_inspection_pdf(lease):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    meta = _get_org_meta(lease)
    bold, normal, sub, title = _get_styles()
    story = []

    tenant = lease.tenant
    unit = lease.rental_unit
    ref_no = f"INSPECT-IN-{lease.lease_number}"

    # Header
    header_data = [
        [
            Paragraph(f"<b>{meta['biz_name']}</b><br/>{meta['biz_code']}{meta['biz_addr']}<br/>Tel: {meta['biz_phone']} | Email: {meta['biz_email']}", sub),
            Paragraph(f"<font color='#1a56db'><b>MOVE-IN CONDITION INSPECTION REPORT</b></font><br/><b>Inspection Ref:</b> {ref_no}<br/><b>Handover Date:</b> {lease.start_date.strftime('%d/%m/%Y')}", sub)
        ]
    ]
    t = Table(header_data, colWidths=[320, 220])
    t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (1,0), (1,-1), 'RIGHT')]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1a56db'), spaceAfter=10))

    # Details
    info = [
        [Paragraph("<b>Tenant:</b>", bold), Paragraph(tenant.full_name, normal), Paragraph("<b>Unit / Room:</b>", bold), Paragraph(f"{unit.unit_number} ({unit.property.name})", normal)],
        [Paragraph("<b>Electricity Meter:</b>", bold), Paragraph("Verified Working / Token No: Assigned", normal), Paragraph("<b>Water Meter Reading:</b>", bold), Paragraph("Reading Recorded at Entry", normal)],
    ]
    t_i = Table(info, colWidths=[110, 160, 130, 140])
    t_i.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1'))]))
    story.append(t_i)
    story.append(Spacer(1, 10))

    # Room-by-Room Checklist
    items = [
        ("Keys & Locks", "Front door, internal doors, padlock keys handed over", "Good / Working"),
        ("Walls & Paintwork", "Freshly painted, no unauthorized drill holes or marks", "Good Condition"),
        ("Ceilings & Roofing", "No water stains, leakages or damp patches", "Good Condition"),
        ("Windows & Glazing", "All glass panes intact, latches and stays working", "Good Condition"),
        ("Electrical & Lights", "Switches, sockets, bulb holders tested and working", "Working"),
        ("Plumbing & Taps", "Sinks, wash basins, faucets free of leaks, good pressure", "Working"),
        ("Bathroom & Toilet", "WC flushing properly, shower head working, no clogs", "Good Condition"),
        ("Kitchen & Cabinets", "Counters clean, shelves and hinges intact", "Good Condition"),
    ]
    ck_rows = [[Paragraph("<b>Inspection Area / Fixture</b>", bold), Paragraph("<b>Condition Description</b>", bold), Paragraph("<b>Status</b>", bold)]]
    for area, desc, status in items:
        ck_rows.append([Paragraph(area, bold), Paragraph(desc, normal), Paragraph(status, normal)])

    t_ck = Table(ck_rows, colWidths=[140, 290, 110])
    t_ck.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e2e8f0')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_ck)
    story.append(Spacer(1, 12))

    sig_data = [
        [Paragraph("<b>Tenant Acceptance:</b><br/>I confirm receipt of keys and that the unit condition is as described.<br/>Signature: ______________________ Date: ___________", normal),
         Paragraph("<b>Inspected By (Caretaker/Manager):</b><br/>Signature: ______________________ Date: ___________", normal)]
    ]
    t_sig = Table(sig_data, colWidths=[270, 270])
    story.append(t_sig)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 7. Move-out Condition Inspection Report
# ─────────────────────────────────────────────────────────────────────────────
def generate_move_out_inspection_pdf(tenant, deductions=0, notes=''):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    meta = _get_org_meta(tenant)
    bold, normal, sub, title = _get_styles()
    story = []

    unit = tenant.current_unit
    ref_no = f"INSPECT-OUT-{tenant.id_passport_number}-{tenant.id}"

    # Header
    header_data = [
        [
            Paragraph(f"<b>{meta['biz_name']}</b><br/>{meta['biz_code']}{meta['biz_addr']}<br/>Tel: {meta['biz_phone']} | Email: {meta['biz_email']}", sub),
            Paragraph(f"<font color='#dc2626'><b>MOVE-OUT CONDITION INSPECTION REPORT</b></font><br/><b>Inspection Ref:</b> {ref_no}<br/><b>Exit Date:</b> {datetime.utcnow().strftime('%d/%m/%Y')}", sub)
        ]
    ]
    t = Table(header_data, colWidths=[320, 220])
    t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (1,0), (1,-1), 'RIGHT')]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#dc2626'), spaceAfter=10))

    info = [
        [Paragraph("<b>Vacating Tenant:</b>", bold), Paragraph(tenant.full_name, normal), Paragraph("<b>Unit / Property:</b>", bold), Paragraph(f"{unit.unit_number} ({unit.property.name})" if unit else 'N/A', normal)],
        [Paragraph("<b>Phone:</b>", bold), Paragraph(tenant.phone, normal), Paragraph("<b>Keys Returned:</b>", bold), Paragraph("All keys verified and returned", normal)],
    ]
    t_i = Table(info, colWidths=[110, 160, 130, 140])
    t_i.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1'))]))
    story.append(t_i)
    story.append(Spacer(1, 10))

    # Damage Assessment
    story.append(Paragraph("<b>EXIT DAMAGE &amp; CLEARANCE ASSESSMENT</b>", bold))
    story.append(Spacer(1, 4))
    items = [
        ("Keys & Handover", "All unit keys returned intact", "Cleared"),
        ("Wall Paint & Holes", "Inspection for excessive holes, repaint needs", "Assessed"),
        ("Plumbing & Taps", "Faucets, flush, sinks checked for blockage or breakage", "Cleared"),
        ("Electrical Fixtures", "Switches, socket covers, breakers verified", "Cleared"),
        ("Cleaning & Garbage", "Unit cleaned and cleared of personal items", "Assessed"),
    ]
    ck_rows = [[Paragraph("<b>Inspection Item</b>", bold), Paragraph("<b>Inspection Finding</b>", bold), Paragraph("<b>Status</b>", bold)]]
    for area, desc, status in items:
        ck_rows.append([Paragraph(area, bold), Paragraph(desc, normal), Paragraph(status, normal)])

    t_ck = Table(ck_rows, colWidths=[140, 290, 110])
    t_ck.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#fee2e2')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_ck)
    story.append(Spacer(1, 10))

    if notes or deductions:
        story.append(Paragraph(f"<b>Noted Damage &amp; Repair Deductions:</b> {notes or 'Standard repainting and minor fixes'} &bull; <b>Total Deductions: KES {deductions:,.2f}</b>", normal))
        story.append(Spacer(1, 10))

    sig_data = [
        [Paragraph("<b>Tenant Signoff:</b><br/>Signature: ______________________ Date: ___________", normal),
         Paragraph("<b>Property Inspector Signoff:</b><br/>Signature: ______________________ Date: ___________", normal)]
    ]
    t_sig = Table(sig_data, colWidths=[270, 270])
    story.append(t_sig)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 8. Tenancy Renewal Agreement Addendum
# ─────────────────────────────────────────────────────────────────────────────
def generate_tenancy_renewal_agreement_pdf(lease, renewal_months=12, new_rent=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    meta = _get_org_meta(lease)
    bold, normal, sub, title = _get_styles()
    story = []

    tenant = lease.tenant
    unit = lease.rental_unit
    ref_no = f"RENEW-{lease.lease_number}"
    rent_cents = int(new_rent * 100) if new_rent else lease.monthly_rent_cents

    header_data = [
        [
            Paragraph(f"<b>{meta['biz_name']}</b><br/>{meta['biz_code']}{meta['biz_addr']}<br/>Tel: {meta['biz_phone']} | Email: {meta['biz_email']}", sub),
            Paragraph(f"<font color='#1a56db'><b>TENANCY RENEWAL AGREEMENT ADDENDUM</b></font><br/><b>Renewal Ref:</b> {ref_no}<br/><b>Date:</b> {datetime.utcnow().strftime('%d/%m/%Y')}", sub)
        ]
    ]
    t = Table(header_data, colWidths=[320, 220])
    t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (1,0), (1,-1), 'RIGHT')]))
    story.append(t)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1a56db'), spaceAfter=12))

    body_text = (
        f"This Tenancy Renewal Agreement is entered into between <b>{meta['biz_name']}</b> (the 'Landlord/Manager') "
        f"and <b>{tenant.full_name}</b> (National ID: <b>{tenant.id_passport_number}</b>, the 'Tenant') for the renewal of tenancy "
        f"at <b>Unit {unit.unit_number}</b>, <b>{unit.property.name}</b>.<br/><br/>"
        f"1. <b>RENEWAL TERM:</b> The tenancy agreement original contract reference <b>{lease.lease_number}</b> is hereby extended for an additional period of <b>{renewal_months} Months</b> commencing from the expiration of the preceding term.<br/>"
        f"2. <b>MONTHLY RENT:</b> The agreed monthly rent during the renewal period shall be <b>{format_currency(rent_cents)}</b> payable in advance on or before the 5th day of each calendar month.<br/>"
        f"3. <b>DEPOSIT:</b> The existing security deposit of <b>{format_currency(lease.deposit_cents)}</b> remains held in trust under the terms of the original agreement.<br/>"
        "4. <b>COVENANTS:</b> All other terms, rules, and covenants contained in the principal Tenancy Agreement shall remain in full force and effect."
    )
    story.append(Paragraph(body_text, normal))
    story.append(Spacer(1, 25))

    sig_data = [
        [Paragraph(f"<b>For the Landlord / Management:</b><br/><br/>Signature: __________________________<br/>Name: _______________________________<br/>Date: {datetime.utcnow().strftime('%d/%m/%Y')}", normal),
         Paragraph(f"<b>For the Tenant:</b><br/><br/>Signature: __________________________<br/>Name: {tenant.full_name}<br/>Date: {datetime.utcnow().strftime('%d/%m/%Y')}", normal)]
    ]
    t_sig = Table(sig_data, colWidths=[270, 270])
    story.append(t_sig)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 9. Maintenance Work Order
# ─────────────────────────────────────────────────────────────────────────────
def generate_maintenance_work_order_pdf(req):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    meta = _get_org_meta(req)
    bold, normal, sub, title = _get_styles()
    story = []

    unit = req.rental_unit
    tenant = req.tenant
    ref_no = f"WO-{req.id:04d}"

    header_data = [
        [
            Paragraph(f"<b>{meta['biz_name']}</b><br/>{meta['biz_code']}{meta['biz_addr']}<br/>Tel: {meta['biz_phone']} | Email: {meta['biz_email']}", sub),
            Paragraph(f"<font color='#d97706'><b>OFFICIAL MAINTENANCE WORK ORDER</b></font><br/><b>Work Order Ref:</b> {ref_no}<br/><b>Date Issued:</b> {req.reported_date.strftime('%d/%m/%Y')}", sub)
        ]
    ]
    t = Table(header_data, colWidths=[320, 220])
    t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (1,0), (1,-1), 'RIGHT')]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#d97706'), spaceAfter=10))

    info = [
        [Paragraph("<b>Job Title / Issue:</b>", bold), Paragraph(req.title, normal), Paragraph("<b>Priority:</b>", bold), Paragraph(f"<b>{req.priority}</b>", normal)],
        [Paragraph("<b>Property:</b>", bold), Paragraph(unit.property.name if unit else 'N/A', normal), Paragraph("<b>Unit / Room:</b>", bold), Paragraph(unit.unit_number if unit else 'N/A', normal)],
        [Paragraph("<b>Resident / Tenant:</b>", bold), Paragraph(tenant.full_name if tenant else 'Vacant Unit', normal), Paragraph("<b>Tenant Phone:</b>", bold), Paragraph(tenant.phone if tenant else 'N/A', normal)],
        [Paragraph("<b>Assigned Technician:</b>", bold), Paragraph(req.assigned_to_technician or 'Unassigned', normal), Paragraph("<b>Tech Contact:</b>", bold), Paragraph(req.technician_contact or 'N/A', normal)],
    ]
    t_i = Table(info, colWidths=[120, 150, 120, 150])
    t_i.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')), ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1'))]))
    story.append(t_i)
    story.append(Spacer(1, 10))

    # Scope of Work
    story.append(Paragraph("<b>SCOPE OF WORK &amp; REPORTED DEFECT</b>", bold))
    story.append(Spacer(1, 4))
    story.append(Paragraph(req.description, normal))
    story.append(Spacer(1, 12))

    # Materials / Cost Tracking
    mat_rows = [
        [Paragraph("<b>Work Item / Material Description</b>", bold), Paragraph("<b>Qty</b>", bold), Paragraph("<b>Estimated Cost (KES)</b>", bold), Paragraph("<b>Actual Cost (KES)</b>", bold)],
        [Paragraph("Primary Repairs &amp; Labor", normal), Paragraph("1", normal), Paragraph("Pending", normal), Paragraph("—", normal)],
        [Paragraph("Materials &amp; Spares", normal), Paragraph("As needed", normal), Paragraph("Pending", normal), Paragraph("—", normal)],
    ]
    t_mat = Table(mat_rows, colWidths=[240, 60, 120, 120])
    t_mat.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#fef3c7')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#fde68a')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_mat)
    story.append(Spacer(1, 20))

    sig_data = [
        [Paragraph("<b>Technician Signoff Upon Completion:</b><br/><br/>Signature: __________________________ Date: ___________", normal),
         Paragraph("<b>Tenant / Manager Acceptance:</b><br/><br/>Work completed satisfactorily.<br/>Signature: __________________________ Date: ___________", normal)]
    ]
    t_sig = Table(sig_data, colWidths=[270, 270])
    story.append(t_sig)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 10. Property Occupancy Report
# ─────────────────────────────────────────────────────────────────────────────
def generate_property_occupancy_report_pdf(property_obj):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    meta = _get_org_meta(property_obj)
    bold, normal, sub, title = _get_styles()
    story = []

    from app.models.property import RentalUnit
    units = property_obj.rental_units.order_by(RentalUnit.unit_number.asc()).all()
    total_units = len(units)
    occupied_units = sum(1 for u in units if u.occupancy_status == 'OCCUPIED')
    vacant_units = sum(1 for u in units if u.occupancy_status == 'VACANT')
    maint_units = sum(1 for u in units if u.occupancy_status in ('MAINTENANCE', 'RESERVED'))
    occupancy_rate = round((occupied_units / total_units * 100), 1) if total_units > 0 else 0
    total_potential_rent = sum(u.rent_amount_cents for u in units)

    ref_no = f"OCC-{property_obj.ref_number}-{datetime.utcnow().strftime('%Y%m%d')}"

    # Header
    header_data = [
        [
            Paragraph(f"<b>{meta['biz_name']}</b><br/>{meta['biz_code']}{meta['biz_addr']}<br/>Tel: {meta['biz_phone']} | Email: {meta['biz_email']}", sub),
            Paragraph(f"<font color='#1a56db'><b>PROPERTY OCCUPANCY ROLL REPORT</b></font><br/><b>Report Ref:</b> {ref_no}<br/><b>Date:</b> {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}", sub)
        ]
    ]
    t = Table(header_data, colWidths=[320, 220])
    t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('ALIGN', (1,0), (1,-1), 'RIGHT')]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1a56db'), spaceAfter=10))

    # Property Summary Cards
    kpis = [
        [Paragraph("<b>Property Name</b>", bold), Paragraph("<b>Location</b>", bold), Paragraph("<b>Units Total</b>", bold), Paragraph("<b>Occupancy %</b>", bold)],
        [Paragraph(property_obj.name, normal), Paragraph(property_obj.location, normal), Paragraph(f"<b>{total_units}</b> Units", normal), Paragraph(f"<font color='#0e9f6e'><b>{occupancy_rate}%</b></font>", bold)],
        [Paragraph("<b>Occupied Units</b>", bold), Paragraph("<b>Vacant Units</b>", bold), Paragraph("<b>Under Maintenance</b>", bold), Paragraph("<b>Monthly Rent Roll</b>", bold)],
        [Paragraph(f"{occupied_units} Occupied", normal), Paragraph(f"{vacant_units} Vacant", normal), Paragraph(f"{maint_units} Units", normal), Paragraph(f"<b>{format_currency(total_potential_rent)}</b>", bold)],
    ]
    t_k = Table(kpis, colWidths=[135, 135, 135, 135])
    t_k.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_k)
    story.append(Spacer(1, 12))

    # Unit Roll Table
    story.append(Paragraph("<b>UNIT-BY-UNIT OCCUPANCY &amp; RESIDENT ROSTER</b>", bold))
    story.append(Spacer(1, 4))

    u_rows = [[Paragraph("<b>Unit No</b>", bold), Paragraph("<b>Type</b>", bold), Paragraph("<b>Status</b>", bold), Paragraph("<b>Current Resident</b>", bold), Paragraph("<b>Resident Phone</b>", bold), Paragraph("<b>Monthly Rent</b>", bold)]]
    for u in units:
        t_name = u.current_tenant.full_name if u.current_tenant else '—'
        t_phone = u.current_tenant.phone if u.current_tenant else '—'
        u_rows.append([
            Paragraph(f"<b>{u.unit_number}</b>", normal),
            Paragraph(u.unit_type, normal),
            Paragraph(u.occupancy_status, bold if u.occupancy_status == 'OCCUPIED' else normal),
            Paragraph(t_name, normal),
            Paragraph(t_phone, normal),
            Paragraph(format_currency(u.rent_amount_cents), normal),
        ])

    t_u = Table(u_rows, colWidths=[65, 80, 80, 140, 95, 80])
    t_u.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e293b')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_u)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
