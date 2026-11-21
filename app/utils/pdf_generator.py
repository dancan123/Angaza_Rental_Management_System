import io
import hashlib
from datetime import datetime

# Python 3.8 compatibility patch for ReportLab md5 usedforsecurity kwarg
_orig_md5 = hashlib.md5
def _safe_md5(*args, **kwargs):
    kwargs.pop('usedforsecurity', None)
    return _orig_md5(*args, **kwargs)
hashlib.md5 = _safe_md5

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from app.services.personalization_service import PersonalizationService

def generate_receipt_pdf(payment):
    """
    Generates a professional PDF payment receipt using ReportLab.
    Returns bytes buffer.
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

    # Personalize branding to the organization that owns this payment/property
    org = None
    if hasattr(payment, 'organization') and payment.organization:
        org = payment.organization
    elif payment.property and getattr(payment.property, 'organization', None):
        org = payment.property.organization
    elif payment.rental_unit and payment.rental_unit.property and getattr(payment.rental_unit.property, 'organization', None):
        org = payment.rental_unit.property.organization

    org_id = org.id if org else None
    settings = PersonalizationService.get_all_settings(organization_id=org_id)

    biz_name = (org.name if org else None) or settings.get('business_name', 'Property Management System')
    biz_addr = (f"{org.town}, {org.county}" if org and (org.town or org.county) else None) or settings.get('business_address', 'Nairobi, Kenya')
    biz_phone = (org.contact_phone if org else None) or settings.get('business_phone', '+254 700 000 000')
    biz_email = (org.contact_email if org else None) or settings.get('business_email', 'info@primerent.co.ke')
    biz_code = f"Business Code: {org.org_code} | " if org and org.org_code else ""
    receipt_footer = settings.get('receipt_footer', 'Thank you for your prompt payment.')

    styles = getSampleStyleSheet()
    subtitle_style = ParagraphStyle(
        'ReceiptSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#64748b')
    )
    bold_style = ParagraphStyle(
        'BoldSmall',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.HexColor('#1e293b')
    )
    normal_style = ParagraphStyle(
        'NormalSmall',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        textColor=colors.HexColor('#334155')
    )
    center_bold = ParagraphStyle('RcptCenterBold', parent=bold_style, alignment=TA_CENTER)
    center_normal = ParagraphStyle('RcptCenterNorm', parent=normal_style, alignment=TA_CENTER)
    right_bold = ParagraphStyle('RcptRightBold', parent=bold_style, alignment=TA_RIGHT)
    header_white_center = ParagraphStyle('RcptHdrCenter', parent=bold_style, alignment=TA_CENTER, textColor=colors.white)
    header_white_left = ParagraphStyle('RcptHdrLeft', parent=bold_style, alignment=TA_LEFT, textColor=colors.white)
    header_white_right = ParagraphStyle('RcptHdrRight', parent=bold_style, alignment=TA_RIGHT, textColor=colors.white)

    story = []

    # 1. Header: Company Info and Receipt Badge
    header_data = [
        [
            Paragraph(f"<b>{biz_name}</b><br/>{biz_code}{biz_addr}<br/>Tel: {biz_phone} | Email: {biz_email}", subtitle_style),
            Paragraph(f"<font color='#1a56db'><b>OFFICIAL PAYMENT RECEIPT</b></font><br/><b>Receipt No:</b> {payment.receipt_number}<br/><b>Date:</b> {payment.payment_date.strftime('%d/%m/%Y')}", subtitle_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[320, 220])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1a56db'), spaceAfter=15))

    # 2. Tenant and Property Information Block
    tenant = payment.tenant
    unit = payment.rental_unit
    info_data = [
        [
            Paragraph("<b>RECEIVED FROM:</b>", bold_style),
            Paragraph(f"{tenant.full_name}", normal_style),
            Paragraph("<b>PROPERTY:</b>", bold_style),
            Paragraph(f"{unit.property.name}", normal_style)
        ],
        [
            Paragraph("<b>NATIONAL ID:</b>", bold_style),
            Paragraph(f"{tenant.id_passport_number}", normal_style),
            Paragraph("<b>RENTAL UNIT:</b>", bold_style),
            Paragraph(f"{unit.unit_number} ({unit.unit_type})", normal_style)
        ],
        [
            Paragraph("<b>PHONE:</b>", bold_style),
            Paragraph(f"{tenant.phone}", normal_style),
            Paragraph("<b>PAYMENT METHOD:</b>", bold_style),
            Paragraph(f"{payment.payment_method}", normal_style)
        ],
        [
            Paragraph("<b>TRANSACTION REF:</b>", bold_style),
            Paragraph(f"{payment.transaction_reference or 'N/A'}", normal_style),
            Paragraph("<b>PAYMENT STATUS:</b>", bold_style),
            Paragraph(f"<font color='#0e9f6e'><b>{payment.payment_status}</b></font>", normal_style)
        ]
    ]
    info_table = Table(info_data, colWidths=[110, 160, 110, 160])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))

    # 3. Allocations / Particulars Table
    allocations = payment.allocations.all()
    items_data = [
        [
            Paragraph("<b>#</b>", header_white_center),
            Paragraph("<b>Description / Period</b>", header_white_left),
            Paragraph("<b>Charge Type</b>", header_white_center),
            Paragraph("<b>Allocated Amount</b>", header_white_right)
        ]
    ]

    if allocations:
        for idx, a in enumerate(allocations, start=1):
            c = a.rent_charge
            period_str = f"Period: {c.period_month}/{c.period_year}" if c else "General Credit"
            items_data.append([
                Paragraph(str(idx), center_normal),
                Paragraph(f"{c.description or 'Rent Payment'} ({period_str})", normal_style),
                Paragraph(c.charge_type if c else "RENT", center_normal),
                Paragraph(a.amount_display, right_bold)
            ])
    else:
        items_data.append([
            Paragraph("1", center_normal),
            Paragraph(payment.description or "Rent Account Payment", normal_style),
            Paragraph(payment.payment_method, center_normal),
            Paragraph(payment.amount_display, right_bold)
        ])

    total_row = len(items_data)
    items_data.append([
        Paragraph("<b>TOTAL RECEIVED:</b>", right_bold),
        "",
        "",
        Paragraph(f"<b>{payment.amount_display}</b>", right_bold)
    ])

    items_table = Table(items_data, colWidths=[36, 284, 100, 120])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a56db')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('SPAN', (0, total_row), (2, total_row)),
        ('BACKGROUND', (0, total_row), (-1, total_row), colors.HexColor('#f1f5f9')),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 25))

    # 4. Sign-off and Verification Stamp Box
    stamp_data = [
        [
            Paragraph("<b>Official Stamp / Authorization:</b><br/><br/>_______________________________<br/>Authorized Accounts Officer", subtitle_style),
            Paragraph(f"<b>System Verification:</b><br/>Status: <b>VERIFIED & CONFIRMED</b><br/>Printed: {payment.verified_at.strftime('%Y-%m-%d %H:%M') if payment.verified_at else 'System Record'}", subtitle_style)
        ]
    ]
    stamp_table = Table(stamp_data, colWidths=[270, 270])
    story.append(stamp_table)
    story.append(Spacer(1, 20))

    # 5. Footer Notice
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cbd5e1'), spaceAfter=10))
    story.append(Paragraph(f"<i>{receipt_footer}</i>", subtitle_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# Re-export advanced tenancy and property management PDF generators
from app.utils.advanced_pdf_generator import (
    generate_tenant_registration_form_pdf,
    generate_rent_demand_letter_pdf,
    generate_rent_arrears_statement_pdf,
    generate_deposit_receipt_pdf,
    generate_deposit_refund_statement_pdf,
    generate_move_in_inspection_pdf,
    generate_move_out_inspection_pdf,
    generate_tenancy_renewal_agreement_pdf,
    generate_maintenance_work_order_pdf,
    generate_property_occupancy_report_pdf,
)



def generate_invoice_pdf(charge):
    """
    Generates a professional PDF Monthly Rent Invoice / Demand Note using ReportLab.
    Returns bytes buffer.
    """
    from app.utils.currency import format_currency
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
    biz_name = settings.get('business_name', 'Property Management System')
    biz_addr = settings.get('business_address', 'Nairobi, Kenya')
    biz_phone = settings.get('business_phone', '+254 700 000 000')
    biz_email = settings.get('business_email', 'info@primerent.co.ke')
    mpesa_paybill = settings.get('mpesa_paybill', '522522')
    bank_name = settings.get('bank_name', 'KCB Bank Kenya')
    bank_acc = settings.get('bank_account_number', '1234567890')

    styles = getSampleStyleSheet()
    subtitle_style = ParagraphStyle('InvSub', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#64748b'))
    bold_style = ParagraphStyle('InvBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#1e293b'))
    normal_style = ParagraphStyle('InvNorm', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#334155'))
    
    center_bold = ParagraphStyle('InvCenterBold', parent=bold_style, alignment=TA_CENTER)
    center_normal = ParagraphStyle('InvCenterNorm', parent=normal_style, alignment=TA_CENTER)
    right_bold = ParagraphStyle('InvRightBold', parent=bold_style, alignment=TA_RIGHT)
    right_normal = ParagraphStyle('InvRightNorm', parent=normal_style, alignment=TA_RIGHT)

    header_white_center = ParagraphStyle('InvHdrCenter', parent=bold_style, alignment=TA_CENTER, textColor=colors.white)
    header_white_left = ParagraphStyle('InvHdrLeft', parent=bold_style, alignment=TA_LEFT, textColor=colors.white)
    header_white_right = ParagraphStyle('InvHdrRight', parent=bold_style, alignment=TA_RIGHT, textColor=colors.white)

    story = []

    # 1. Header
    header_data = [
        [
            Paragraph(f"<b>{biz_name}</b><br/>{biz_addr}<br/>Tel: {biz_phone} | Email: {biz_email}", subtitle_style),
            Paragraph(f"<font color='#dc2626'><b>RENT INVOICE & DEMAND NOTE</b></font><br/><b>Invoice No:</b> {charge.invoice_number}<br/><b>Due Date:</b> <font color='#dc2626'><b>{charge.due_date.strftime('%d/%m/%Y')}</b></font>", subtitle_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[320, 220])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#dc2626'), spaceAfter=15))

    # 2. Tenant Info
    tenant = charge.tenant
    unit = charge.rental_unit
    info_data = [
        [
            Paragraph("<b>BILLED TO:</b>", bold_style),
            Paragraph(f"{tenant.full_name}", normal_style),
            Paragraph("<b>PROPERTY:</b>", bold_style),
            Paragraph(f"{unit.property.name if unit.property else 'N/A'}", normal_style)
        ],
        [
            Paragraph("<b>PHONE:</b>", bold_style),
            Paragraph(f"{tenant.phone}", normal_style),
            Paragraph("<b>UNIT NUMBER:</b>", bold_style),
            Paragraph(f"{unit.unit_number} ({unit.unit_type})", normal_style)
        ],
        [
            Paragraph("<b>NATIONAL ID:</b>", bold_style),
            Paragraph(f"{tenant.id_passport_number}", normal_style),
            Paragraph("<b>BILLING PERIOD:</b>", bold_style),
            Paragraph(f"{charge.period_month:02d}/{charge.period_year}", normal_style)
        ]
    ]
    info_table = Table(info_data, colWidths=[110, 160, 110, 160])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff5f5')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#fecaca')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#fecaca')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))

    # 3. Particulars Table (Col widths: # = 36, Description = 284, Category = 100, Amount = 120 -> Total 540 pt)
    items_data = [
        [
            Paragraph("<b>#</b>", header_white_center),
            Paragraph("<b>Item Description</b>", header_white_left),
            Paragraph("<b>Category</b>", header_white_center),
            Paragraph("<b>Amount (KES)</b>", header_white_right)
        ],
        [
            Paragraph("1", center_normal),
            Paragraph(charge.description or f"Monthly Rental Charge ({charge.period_month:02d}/{charge.period_year}) - Unit {unit.unit_number}", normal_style),
            Paragraph(charge.charge_type, center_normal),
            Paragraph(charge.amount_display, right_bold)
        ],
        [
            Paragraph("<b>TOTAL DUE:</b>", right_bold),
            "",
            "",
            Paragraph(f"<b>{charge.amount_display}</b>", right_bold)
        ]
    ]

    table_styles = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('SPAN', (0, 2), (2, 2)),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#f8fafc')),
    ]

    curr_row = 3
    if charge.amount_paid_cents > 0:
        items_data.append([
            Paragraph("<b>LESS: AMOUNT PAID:</b>", right_bold),
            "",
            "",
            Paragraph(f"<font color='#059669'><b>- {charge.paid_display}</b></font>", right_bold)
        ])
        table_styles.append(('SPAN', (0, curr_row), (2, curr_row)))
        table_styles.append(('BACKGROUND', (0, curr_row), (-1, curr_row), colors.HexColor('#f0fdf4')))
        curr_row += 1

    bal_color = '#dc2626' if charge.balance_cents > 0 else '#059669'
    bal_text = charge.balance_display if charge.balance_cents > 0 else 'KES 0.00 (PAID IN FULL)'
    items_data.append([
        Paragraph("<b>OUTSTANDING BALANCE:</b>", right_bold),
        "",
        "",
        Paragraph(f"<font color='{bal_color}'><b>{bal_text}</b></font>", right_bold)
    ])
    table_styles.append(('SPAN', (0, curr_row), (2, curr_row)))
    table_styles.append(('BACKGROUND', (0, curr_row), (-1, curr_row), colors.HexColor('#fef2f2') if charge.balance_cents > 0 else colors.HexColor('#ecfdf5')))

    items_table = Table(items_data, colWidths=[36, 284, 100, 120])
    items_table.setStyle(TableStyle(table_styles))
    story.append(items_table)
    story.append(Spacer(1, 15))

    # Official Status Banner
    if charge.status == 'PAID' or charge.balance_cents <= 0:
        status_box = [
            [
                Paragraph("<font color='#059669'><b>INVOICE STATUS: PAID IN FULL &bull; SETTLED</b></font><br/><font color='#475569'>This invoice has been cleared and settled in full. Thank you for your prompt payment.</font>", subtitle_style)
            ]
        ]
        status_table = Table(status_box, colWidths=[540])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ecfdf5')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#10b981')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(status_table)
        story.append(Spacer(1, 12))
    elif charge.status == 'PARTIALLY_PAID':
        status_box = [
            [
                Paragraph(f"<font color='#d97706'><b>INVOICE STATUS: PARTIALLY PAID</b></font><br/><font color='#475569'>Paid: {charge.paid_display} &bull; Outstanding Balance: <font color='#dc2626'><b>{charge.balance_display}</b></font> due by {charge.due_date.strftime('%d/%m/%Y')}.</font>", subtitle_style)
            ]
        ]
        status_table = Table(status_box, colWidths=[540])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fffbeb')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#f59e0b')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(status_table)
        story.append(Spacer(1, 12))

    # 4. Payment Instructions Box
    pay_data = [
        [
            Paragraph(f"<b>HOW TO PAY VIA M-PESA:</b><br/>1. Go to M-Pesa Menu &gt; Lipa na M-Pesa<br/>2. Paybill Number: <b>{mpesa_paybill}</b><br/>3. Account: <b>{unit.unit_number}</b><br/>4. Enter Amount and M-Pesa PIN", subtitle_style),
            Paragraph(f"<b>BANK TRANSFER DETAILS:</b><br/>Bank: <b>{bank_name}</b><br/>Account Name: <b>{biz_name}</b><br/>Account No: <b>{bank_acc}</b><br/>Ref: <b>{charge.invoice_number}</b>", subtitle_style)
        ]
    ]
    pay_table = Table(pay_data, colWidths=[270, 270])
    pay_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(pay_table)
    story.append(Spacer(1, 15))
    story.append(Paragraph("<i>Payment is due on or before the 5th of each calendar month. Late payments may attract standard penalty fees.</i>", subtitle_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# Re-export advanced tenancy and property management PDF generators
from app.utils.advanced_pdf_generator import (
    generate_tenant_registration_form_pdf,
    generate_rent_demand_letter_pdf,
    generate_rent_arrears_statement_pdf,
    generate_deposit_receipt_pdf,
    generate_deposit_refund_statement_pdf,
    generate_move_in_inspection_pdf,
    generate_move_out_inspection_pdf,
    generate_tenancy_renewal_agreement_pdf,
    generate_maintenance_work_order_pdf,
    generate_property_occupancy_report_pdf,
)



def generate_guest_folio_pdf(reservation):
    """
    Generates an official Executive PDF Guest Folio & Booking Receipt for Airbnb / Short-Stay Management.
    Calibrated to fit on EXACTLY ONE (1) A4 PAGE with zero overflow.
    Returns bytes buffer.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=28,
        leftMargin=28,
        topMargin=22,
        bottomMargin=22
    )

    settings = PersonalizationService.get_all_settings()
    biz_name = settings.get('business_name', 'Angaza Hospitality & Short-Stay Suites')
    biz_phone = settings.get('business_phone', '+254 700 000 000')
    biz_email = settings.get('business_email', 'hospitality@primerent.co.ke')

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('FolioTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14, leading=16, textColor=colors.HexColor('#0f172a'))
    subtitle_style = ParagraphStyle('FolioSub', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor('#475569'))
    header_right = ParagraphStyle('FolioHRight', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=11, alignment=2, textColor=colors.HexColor('#334155'))
    bold_style = ParagraphStyle('FolioBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=11, textColor=colors.HexColor('#0f172a'))
    normal_style = ParagraphStyle('FolioNorm', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor('#334155'))
    right_bold = ParagraphStyle('FolioRBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=11, alignment=2, textColor=colors.HexColor('#0f172a'))
    center_norm = ParagraphStyle('FolioCNorm', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10, alignment=1, textColor=colors.HexColor('#334155'))
    table_head = ParagraphStyle('FolioTHead', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=10.5, textColor=colors.white)

    story = []

    # 1. Header with Property / Brand Styling
    prop = reservation.rental_unit.property if reservation.rental_unit else None
    prop_name = prop.name if prop else biz_name
    prop_loc = prop.location if prop and prop.location else 'Prime Location, Kenya'

    method_name = (reservation.payment_method or 'MPESA').upper()
    pay_badge_text = "CASH PAYMENT RECEIVED" if method_name == 'CASH' else f"{method_name} CONFIRMED"

    header_data = [
        [
            Paragraph(f"<b>{prop_name.upper()}</b><br/><font color='#e11d48'><b>OFFICIAL SHORT-STAY GUEST FOLIO &amp; RECEIPT</b></font><br/>{prop_loc} &bull; Hotline: {biz_phone} &bull; Email: {biz_email}", subtitle_style),
            Paragraph(f"<b>Folio #: REC-{reservation.reservation_code}</b><br/><b>Date Issued:</b> {datetime.utcnow().strftime('%d %b %Y %H:%M')}<br/><b>Channel:</b> {reservation.booking_source} &bull; <b>Status:</b> <font color=\"{'#15803d' if reservation.status in ('CHECKED_IN','CHECKED_OUT') else '#1d4ed8'}\"><b>{reservation.status}</b></font>", header_right)
        ]
    ]
    header_table = Table(header_data, colWidths=[330, 209])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#e11d48'), spaceBefore=2, spaceAfter=8))

    # 2. Guest & Reservation Summary Block (Compact 2x4 Grid = 539 pt wide)
    guest = reservation.guest
    unit = reservation.rental_unit
    info_data = [
        [
            Paragraph("<b>Guest Name:</b>", bold_style),
            Paragraph(f"<b>{guest.full_name}</b>", bold_style),
            Paragraph("<b>Room / Suite:</b>", bold_style),
            Paragraph(f"<b>Unit {unit.unit_number}</b> ({unit.unit_type})", bold_style)
        ],
        [
            Paragraph("<b>Phone / WhatsApp:</b>", bold_style),
            Paragraph(f"{guest.phone}", normal_style),
            Paragraph("<b>Check-In Date:</b>", bold_style),
            Paragraph(f"{reservation.check_in_date.strftime('%d %b %Y')} (After 2:00 PM)", normal_style)
        ],
        [
            Paragraph("<b>National ID / Passport:</b>", bold_style),
            Paragraph(f"{guest.id_passport_number or 'On File'} ({guest.nationality or 'Kenyan'})", normal_style),
            Paragraph("<b>Check-Out Date:</b>", bold_style),
            Paragraph(f"{reservation.check_out_date.strftime('%d %b %Y')} (By 10:00 AM)", normal_style)
        ],
        [
            Paragraph("<b>Email Address:</b>", bold_style),
            Paragraph(f"{guest.email or 'N/A'}", normal_style),
            Paragraph("<b>Duration of Stay:</b>", bold_style),
            Paragraph(f"<b>{reservation.num_nights} Night(s)</b> &bull; {reservation.num_guests} Guest(s)", bold_style)
        ]
    ]
    info_table = Table(info_data, colWidths=[105, 164, 105, 165])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#f1f5f9')),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8))

    # 3. Itemized Charges Table (539 pt wide)
    items_data = [
        [
            Paragraph("<b>#</b>", table_head),
            Paragraph("<b>Particulars / Service Description</b>", table_head),
            Paragraph("<b>Daily Rate</b>", table_head),
            Paragraph("<b>Nights</b>", table_head),
            Paragraph("<b>Total (KES)</b>", table_head)
        ],
        [
            Paragraph("1", center_norm),
            Paragraph(f"<b>Accommodation: Room {unit.unit_number}</b><br/><font color='#64748b' size=7>Dates: {reservation.check_in_date.strftime('%d/%m/%Y')} &rarr; {reservation.check_out_date.strftime('%d/%m/%Y')} &bull; Source: {reservation.booking_source}</font>", normal_style),
            Paragraph(reservation.daily_rate_display, center_norm),
            Paragraph(f"{reservation.num_nights}", center_norm),
            Paragraph(f"<b>{reservation.total_stay_display}</b>", right_bold)
        ],
        [
            Paragraph("<b>TOTAL CHARGES:</b>", right_bold),
            "",
            "",
            "",
            Paragraph(f"<b>{reservation.total_stay_display}</b>", right_bold)
        ],
        [
            Paragraph("<b>PAYMENTS RECORDED:</b>", bold_style),
            Paragraph(f"<b>Mode:</b> {method_name} &bull; <b>Ref:</b> {reservation.payment_reference or 'SETTLED'}", normal_style),
            "",
            "",
            Paragraph(f"<font color='#0e9f6e'><b>- {reservation.paid_amount_display}</b></font>", right_bold)
        ],
        [
            Paragraph("<b>OUTSTANDING BALANCE:</b>", right_bold),
            "",
            "",
            "",
            Paragraph(f"<font color=\"{'#dc2626' if reservation.balance_cents > 0 else '#0e9f6e'}\"><b>{reservation.balance_display if reservation.balance_cents > 0 else 'KES 0.00 (SETTLED IN FULL)'}</b></font>", right_bold)
        ]
    ]
    items_table = Table(items_data, colWidths=[30, 229, 95, 55, 130])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e11d48')),
        ('ALIGN', (0, 0), (0, 1), 'CENTER'),
        ('ALIGN', (2, 0), (3, 1), 'CENTER'),
        ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('SPAN', (0, 2), (3, 2)),
        ('SPAN', (1, 3), (3, 3)),
        ('SPAN', (0, 4), (3, 4)),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f0fdf4')),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#fef2f2') if reservation.balance_cents > 0 else colors.HexColor('#f0fdf4')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 8))

    # 4. Payment Authentication & Settlement Banner (539 pt wide)
    if method_name == 'CASH':
        badge_bg = '#fefce8'
        badge_border = '#ca8a04'
        badge_title = "OFFICIAL CASH PAYMENT VERIFIED"
        badge_desc = f"Cash received and counted at Front Desk / Cashier. Official receipt issued under Ref: {reservation.payment_reference or ('CASH-' + reservation.reservation_code)}."
    elif 'MPESA' in method_name:
        badge_bg = '#f0fdf4'
        badge_border = '#16a34a'
        badge_title = "SAFARICOM M-PESA CONFIRMED & SETTLED"
        badge_desc = f"Direct mobile settlement verified on Daraja Gateway. Reference: {reservation.payment_reference or 'QZ99FATUMA'}."
    else:
        badge_bg = '#eff6ff'
        badge_border = '#2563eb'
        badge_title = f"{method_name} PAYMENT CONFIRMED"
        badge_desc = f"Electronic payment verified. Transaction Reference: {reservation.payment_reference or 'N/A'}."

    pay_box = [
        [
            Paragraph(f"<b><font color='{badge_border}'>&#10004; {badge_title}</font></b><br/><font size=7.5 color='#334155'>{badge_desc}</font>", normal_style),
            Paragraph(f"<b>Status:</b> {'SETTLED' if reservation.balance_cents <= 0 else 'PARTIAL'}<br/><b>Amount:</b> {reservation.paid_amount_display}", right_bold)
        ]
    ]
    pay_table = Table(pay_box, colWidths=[380, 159])
    pay_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(badge_bg)),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor(badge_border)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(pay_table)
    story.append(Spacer(1, 8))

    # 5. House Rules, Policies & Authorized Signatures (539 pt wide)
    rules_and_sign = [
        [
            Paragraph(
                "<b>HOUSE RULES &amp; KEY POLICIES:</b><br/>"
                "&bull; <b>Check-out:</b> Strictly by 10:00 AM on departure date.<br/>"
                "&bull; <b>Smoking &amp; Parties:</b> Strictly prohibited inside suites.<br/>"
                "&bull; <b>Quiet Hours:</b> 10:00 PM to 7:00 AM. Respect neighbor privacy.<br/>"
                "&bull; <b>Energy &amp; Water:</b> Kindly switch off lighting and AC when vacating.",
                subtitle_style
            ),
            Paragraph(
                "<b>OFFICIAL ISSUANCE &amp; VERIFICATION:</b><br/>"
                f"Generated by: Front Desk Management<br/>"
                f"Date &amp; Time: {datetime.utcnow().strftime('%d/%m/%Y %H:%M UTC')}<br/>"
                f"Support / Emergency: {biz_phone}<br/>"
                "<b>Status:</b> Official Computer-Generated Document &bull; Valid without physical seal.",
                subtitle_style
            )
        ]
    ]
    footer_table = Table(rules_and_sign, colWidths=[270, 269])
    footer_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(footer_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_thermal_receipt_pdf(reservation):
    """
    Generates a true 80mm POS Thermal Slip Payment Receipt for Airbnb / Short-Stay Management.
    Accommodates both Cash and M-Pesa payments authentically.
    Standard Kenyan 80mm roll width POS receipt.
    Returns bytes buffer.
    """
    from reportlab.lib.units import mm
    buffer = io.BytesIO()
    # 80mm width standard thermal roll. Height around 205mm.
    doc = SimpleDocTemplate(
        buffer,
        pagesize=(80 * mm, 205 * mm),
        rightMargin=3 * mm,
        leftMargin=3 * mm,
        topMargin=4 * mm,
        bottomMargin=4 * mm
    )

    settings = PersonalizationService.get_all_settings()
    biz_name = settings.get('business_name', 'Angaza Hospitality Suites')
    biz_phone = settings.get('business_phone', '+254 700 000 000')
    biz_email = settings.get('business_email', 'hospitality@primerent.co.ke')

    prop = reservation.rental_unit.property if reservation.rental_unit else None
    prop_name = prop.name if prop else biz_name
    prop_loc = prop.location if prop and prop.location else 'Prime Location, Kenya'

    styles = getSampleStyleSheet()
    t_center_bold = ParagraphStyle('TCBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=10.5, alignment=1, textColor=colors.HexColor('#0f172a'))
    t_center_title = ParagraphStyle('TCTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10.5, leading=12.5, alignment=1, textColor=colors.HexColor('#0f172a'))
    t_center_norm = ParagraphStyle('TCNorm', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=9, alignment=1, textColor=colors.HexColor('#475569'))
    t_left_bold = ParagraphStyle('TLBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=9.5, textColor=colors.HexColor('#0f172a'))
    t_left_norm = ParagraphStyle('TLNorm', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9.5, textColor=colors.HexColor('#334155'))
    t_right_bold = ParagraphStyle('TRBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=9.5, alignment=2, textColor=colors.HexColor('#0f172a'))
    t_right_norm = ParagraphStyle('TRNorm', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9.5, alignment=2, textColor=colors.HexColor('#334155'))
    t_mono = ParagraphStyle('TMono', parent=styles['Normal'], fontName='Courier-Bold', fontSize=7.5, leading=9.5, alignment=1, textColor=colors.HexColor('#0f172a'))

    story = []

    # Store / Property Header
    story.append(Paragraph(f"<b>{prop_name.upper()}</b>", t_center_title))
    story.append(Spacer(1, 2))
    story.append(Paragraph(f"{prop_loc} &bull; Tel: {biz_phone}", t_center_norm))
    story.append(Paragraph("SHORT-STAY / AIRBNB OFFICIAL RECEIPT", t_center_bold))
    story.append(Spacer(1, 2))
    story.append(Paragraph("------------------------------------------------------------", t_center_norm))

    # Meta
    dt_str = reservation.created_at.strftime('%d/%m/%Y %H:%M') if reservation.created_at else datetime.now().strftime('%d/%m/%Y %H:%M')
    meta_table = Table([
        [Paragraph("<b>Receipt #:</b>", t_left_norm), Paragraph(f"<b>REC-{reservation.reservation_code}</b>", t_right_bold)],
        [Paragraph("<b>Date / Time:</b>", t_left_norm), Paragraph(dt_str, t_right_norm)],
        [Paragraph("<b>Guest Name:</b>", t_left_norm), Paragraph(reservation.guest.full_name if reservation.guest else "Guest", t_right_bold)],
        [Paragraph("<b>Phone:</b>", t_left_norm), Paragraph(reservation.guest.phone if reservation.guest else "N/A", t_right_norm)],
        [Paragraph("<b>Room / Unit:</b>", t_left_norm), Paragraph(reservation.rental_unit.unit_number if reservation.rental_unit else "Room", t_right_bold)],
        [Paragraph("<b>Check-In:</b>", t_left_norm), Paragraph(reservation.check_in_date.strftime('%d/%m/%Y'), t_right_norm)],
        [Paragraph("<b>Check-Out:</b>", t_left_norm), Paragraph(reservation.check_out_date.strftime('%d/%m/%Y'), t_right_norm)],
        [Paragraph("<b>Duration:</b>", t_left_norm), Paragraph(f"{reservation.num_nights} Night(s)", t_right_norm)],
    ], colWidths=[28 * mm, 46 * mm])
    meta_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(meta_table)
    story.append(Paragraph("------------------------------------------------------------", t_center_norm))

    # Line Item
    item_table = Table([
        [Paragraph("<b>Item / Description</b>", t_left_bold), Paragraph("<b>Qty</b>", t_center_bold), Paragraph("<b>Amount (KES)</b>", t_right_bold)],
        [
            Paragraph(f"Stay: {reservation.rental_unit.unit_number if reservation.rental_unit else 'Room'}<br/>@{reservation.daily_rate_display}/night", t_left_norm),
            Paragraph(f"{reservation.num_nights}n", t_center_norm),
            Paragraph(reservation.total_stay_display, t_right_bold)
        ]
    ], colWidths=[42 * mm, 10 * mm, 22 * mm])
    item_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(item_table)
    story.append(Paragraph("------------------------------------------------------------", t_center_norm))

    # Settlement Totals
    status_label = "Checked In (Active)" if reservation.status == 'CHECKED_IN' else reservation.status
    method_name = (reservation.payment_method or 'MPESA').upper()
    ref_display = reservation.payment_reference or ('CASH-COUNTER' if method_name == 'CASH' else 'N/A')

    fin_table = Table([
        [Paragraph("<b>TOTAL CHARGE:</b>", t_left_bold), Paragraph(f"<b>{reservation.total_stay_display}</b>", t_right_bold)],
        [Paragraph("<b>AMOUNT PAID:</b>", t_left_bold), Paragraph(f"<b>{reservation.paid_amount_display}</b>", t_right_bold)],
        [Paragraph("<b>BALANCE DUE:</b>", t_left_bold), Paragraph(f"<b>{'KES 0.00 (SETTLED)' if reservation.balance_cents <= 0 else reservation.balance_display}</b>", t_right_bold)],
        [Paragraph("<b>PAYMENT METHOD:</b>", t_left_norm), Paragraph(f"<b>{method_name}</b>", t_right_bold)],
        [Paragraph("<b>TRANSACTION REF:</b>", t_left_norm), Paragraph(f"<b>{ref_display}</b>", t_right_bold)],
        [Paragraph("<b>RESERVATION STATUS:</b>", t_left_norm), Paragraph(f"<b>{status_label}</b>", t_right_bold)],
    ], colWidths=[36 * mm, 38 * mm])
    fin_table.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(fin_table)
    story.append(Spacer(1, 2))
    story.append(Paragraph("============================================", t_center_norm))
    story.append(Spacer(1, 1))

    # Barcode representation & Footer
    barcode_text = f"*{ref_display}*"
    story.append(Paragraph(barcode_text, t_mono))
    story.append(Spacer(1, 2))

    if method_name == 'CASH':
        story.append(Paragraph("<b>OFFICIAL CASH PAYMENT VERIFIED &amp; RECEIPTED</b>", t_center_bold))
    elif 'MPESA' in method_name:
        story.append(Paragraph("<b>SAFARICOM M-PESA CONFIRMED &amp; SETTLED</b>", t_center_bold))
    else:
        story.append(Paragraph(f"<b>{method_name} PAYMENT CONFIRMED &amp; SETTLED</b>", t_center_bold))

    story.append(Paragraph("Thank you for staying with us! Karibu tena.", t_center_norm))
    story.append(Paragraph("Angaza Rentals &amp; Short-Stay Hospitality Management", t_center_norm))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# Re-export advanced tenancy and property management PDF generators
from app.utils.advanced_pdf_generator import (
    generate_tenant_registration_form_pdf,
    generate_rent_demand_letter_pdf,
    generate_rent_arrears_statement_pdf,
    generate_deposit_receipt_pdf,
    generate_deposit_refund_statement_pdf,
    generate_move_in_inspection_pdf,
    generate_move_out_inspection_pdf,
    generate_tenancy_renewal_agreement_pdf,
    generate_maintenance_work_order_pdf,
    generate_property_occupancy_report_pdf,
)



def generate_tenant_statement_pdf(tenant):
    """
    Generates a full PDF Tenant Statement of Account / Financial Ledger.
    Returns bytes buffer.
    """
    from app.utils.currency import format_currency
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
    biz_name = settings.get('business_name', 'Property Management System')
    biz_phone = settings.get('business_phone', '+254 700 000 000')
    biz_email = settings.get('business_email', 'info@primerent.co.ke')

    styles = getSampleStyleSheet()
    subtitle_style = ParagraphStyle('StmtSub', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#64748b'))
    bold_style = ParagraphStyle('StmtBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#1e293b'))
    normal_style = ParagraphStyle('StmtNorm', parent=styles['Normal'], fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#334155'))

    story = []

    # 1. Header
    header_data = [
        [
            Paragraph(f"<b>{biz_name}</b><br/>Tel: {biz_phone} | Email: {biz_email}", subtitle_style),
            Paragraph(f"<font color='#0284c7'><b>TENANT STATEMENT OF ACCOUNT</b></font><br/><b>Statement Date:</b> {datetime.utcnow().strftime('%d/%m/%Y')}<br/><b>Tenant ID:</b> {tenant.id_passport_number}", subtitle_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[320, 220])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284c7'), spaceAfter=15))

    # 2. Tenant Summary Block
    unit = tenant.current_unit
    summary_data = [
        [
            Paragraph("<b>TENANT NAME:</b>", bold_style),
            Paragraph(f"{tenant.full_name}", normal_style),
            Paragraph("<b>PROPERTY:</b>", bold_style),
            Paragraph(f"{unit.property.name if unit and unit.property else 'N/A'}", normal_style)
        ],
        [
            Paragraph("<b>PHONE NUMBER:</b>", bold_style),
            Paragraph(f"{tenant.phone}", normal_style),
            Paragraph("<b>CURRENT UNIT:</b>", bold_style),
            Paragraph(f"{unit.unit_number if unit else 'N/A'}", normal_style)
        ]
    ]
    summary_table = Table(summary_data, colWidths=[110, 160, 110, 160])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f9ff')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#bae6fd')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bae6fd')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))

    # 3. Chronological Transactions Ledger
    from sqlalchemy import asc
    charges = tenant.rent_charges.order_by(asc('due_date')).all()
    payments = tenant.payments.order_by(asc('payment_date')).all()

    events = []
    for c in charges:
        events.append({
            'date': c.due_date,
            'ref': c.invoice_number,
            'desc': f"{c.charge_type}: {c.description or 'Monthly Charge'}",
            'debit': c.amount_cents,
            'credit': 0
        })
    for p in payments:
        events.append({
            'date': p.payment_date,
            'ref': p.receipt_number,
            'desc': f"Payment ({p.payment_method}) - {p.transaction_reference or ''}",
            'debit': 0,
            'credit': p.amount_cents
        })

    events.sort(key=lambda x: x['date'])

    running_bal = 0
    total_debits = 0
    total_credits = 0

    ledger_data = [
        [Paragraph("<b>Date</b>", bold_style), Paragraph("<b>Reference</b>", bold_style), Paragraph("<b>Description</b>", bold_style), Paragraph("<b>Charge (Dr)</b>", bold_style), Paragraph("<b>Paid (Cr)</b>", bold_style), Paragraph("<b>Balance</b>", bold_style)]
    ]

    for ev in events:
        running_bal += (ev['debit'] - ev['credit'])
        total_debits += ev['debit']
        total_credits += ev['credit']
        ledger_data.append([
            Paragraph(ev['date'].strftime('%d/%m/%Y'), normal_style),
            Paragraph(ev['ref'], normal_style),
            Paragraph(ev['desc'][:38], normal_style),
            Paragraph(format_currency(ev['debit']) if ev['debit'] > 0 else "-", normal_style),
            Paragraph(format_currency(ev['credit']) if ev['credit'] > 0 else "-", normal_style),
            Paragraph(format_currency(running_bal), bold_style)
        ])

    right_bold = ParagraphStyle('StatRightBold', parent=bold_style, alignment=TA_RIGHT)

    ledger_data.append([
        Paragraph("<b>TOTALS:</b>", right_bold),
        "",
        "",
        Paragraph(f"<b>{format_currency(total_debits)}</b>", right_bold),
        Paragraph(f"<b>{format_currency(total_credits)}</b>", right_bold),
        Paragraph(f"<b>{format_currency(running_bal)}</b>", right_bold)
    ])

    ledger_table = Table(ledger_data, colWidths=[65, 80, 165, 75, 75, 80])
    ledger_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0284c7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('SPAN', (0, -1), (2, -1)),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(ledger_table)
    story.append(Spacer(1, 25))

    story.append(Paragraph(f"<b>Net Outstanding Balance:</b> <font color=\"{'#dc2626' if running_bal > 0 else '#0e9f6e'}\"><b>{format_currency(running_bal)}</b></font>", bold_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# Re-export advanced tenancy and property management PDF generators
from app.utils.advanced_pdf_generator import (
    generate_tenant_registration_form_pdf,
    generate_rent_demand_letter_pdf,
    generate_rent_arrears_statement_pdf,
    generate_deposit_receipt_pdf,
    generate_deposit_refund_statement_pdf,
    generate_move_in_inspection_pdf,
    generate_move_out_inspection_pdf,
    generate_tenancy_renewal_agreement_pdf,
    generate_maintenance_work_order_pdf,
    generate_property_occupancy_report_pdf,
)



def generate_landlord_remittance_pdf(landlord, report_dict):
    """
    Generates a formal Landlord Remittance & Monthly Disbursement Statement PDF.
    Returns bytes buffer.
    """
    from app.utils.currency import format_currency
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
    biz_name = settings.get('business_name', 'Property Management System')
    biz_phone = settings.get('business_phone', '+254 700 000 000')
    biz_email = settings.get('business_email', 'info@primerent.co.ke')

    styles = getSampleStyleSheet()
    subtitle_style = ParagraphStyle('RemSub', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#64748b'))
    bold_style = ParagraphStyle('RemBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#1e293b'))
    normal_style = ParagraphStyle('RemNorm', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#334155'))

    story = []

    # 1. Header
    header_data = [
        [
            Paragraph(f"<b>{biz_name}</b><br/>Property Agency &amp; Management<br/>Tel: {biz_phone} | Email: {biz_email}", subtitle_style),
            Paragraph(f"<font color='#047857'><b>LANDLORD REMITTANCE STATEMENT</b></font><br/><b>Date:</b> {datetime.utcnow().strftime('%d/%m/%Y')}<br/><b>Statement Ref:</b> REM-{landlord.id}-{datetime.utcnow().strftime('%Y%m')}", subtitle_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[320, 220])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#047857'), spaceAfter=15))

    # 2. Landlord Profile
    info_data = [
        [
            Paragraph("<b>PROPERTY OWNER:</b>", bold_style),
            Paragraph(f"{landlord.name}", normal_style),
            Paragraph("<b>TAX PIN:</b>", bold_style),
            Paragraph(f"{landlord.tax_pin or 'N/A'}", normal_style)
        ],
        [
            Paragraph("<b>CONTACT PHONE:</b>", bold_style),
            Paragraph(f"{landlord.phone}", normal_style),
            Paragraph("<b>BANK DETAILS:</b>", bold_style),
            Paragraph(f"{landlord.bank_account_info or 'On File'}", normal_style)
        ]
    ]
    info_table = Table(info_data, colWidths=[110, 160, 110, 160])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0fdf4')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#bbf7d0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bbf7d0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))

    # 3. Financial Summary Table
    gross = report_dict.get('gross_income_cents', 0)
    exp = report_dict.get('total_expenses_cents', 0)
    net = report_dict.get('net_payout_cents', 0)

    summary_data = [
        [Paragraph("<b>Financial Metric</b>", bold_style), Paragraph("<b>Amount (KES)</b>", bold_style)],
        [Paragraph("Gross Rent Collections Received", normal_style), Paragraph(format_currency(gross), bold_style)],
        [Paragraph("Less: Maintenance Expenses &amp; Direct Deductions", normal_style), Paragraph(f"<font color='#dc2626'>- {format_currency(exp)}</font>", bold_style)],
        [Paragraph("<b>NET DISBURSEMENT PAYABLE TO LANDLORD</b>", bold_style), Paragraph(f"<font color='#047857'><b>{format_currency(net)}</b></font>", bold_style)]
    ]
    summary_table = Table(summary_data, colWidths=[360, 180])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#047857')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0fdf4')),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 30))

    # 4. Signatures
    sign_data = [
        [
            Paragraph("Prepared By:<br/><br/>________________________<br/>Accountant / Property Manager", subtitle_style),
            Paragraph("Approved For Payment:<br/><br/>________________________<br/>Managing Director", subtitle_style)
        ]
    ]
    sign_table = Table(sign_data, colWidths=[270, 270])
    story.append(sign_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# Re-export advanced tenancy and property management PDF generators
from app.utils.advanced_pdf_generator import (
    generate_tenant_registration_form_pdf,
    generate_rent_demand_letter_pdf,
    generate_rent_arrears_statement_pdf,
    generate_deposit_receipt_pdf,
    generate_deposit_refund_statement_pdf,
    generate_move_in_inspection_pdf,
    generate_move_out_inspection_pdf,
    generate_tenancy_renewal_agreement_pdf,
    generate_maintenance_work_order_pdf,
    generate_property_occupancy_report_pdf,
)


# Re-export advanced tenancy and property management PDF generators
from app.utils.advanced_pdf_generator import (
    generate_tenant_registration_form_pdf,
    generate_rent_demand_letter_pdf,
    generate_rent_arrears_statement_pdf,
    generate_deposit_receipt_pdf,
    generate_deposit_refund_statement_pdf,
    generate_move_in_inspection_pdf,
    generate_move_out_inspection_pdf,
    generate_tenancy_renewal_agreement_pdf,
    generate_maintenance_work_order_pdf,
    generate_property_occupancy_report_pdf,
)




def generate_collection_sales_report_pdf(report_data, org=None, start_date=None, end_date=None):
    """
    Generates a formal Daily/Periodic Sales & Rent Collection PDF report
    personalized to the organization.
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

    org_id = org.id if org else None
    settings = PersonalizationService.get_all_settings(organization_id=org_id)

    biz_name = (org.name if org else None) or settings.get('business_name', 'Property Management System')
    biz_addr = (f"{org.town}, {org.county}" if org and (org.town or org.county) else None) or settings.get('business_address', 'Nairobi, Kenya')
    biz_phone = (org.contact_phone if org else None) or settings.get('business_phone', '+254 700 000 000')
    biz_code = f"Business Code: {org.org_code} | " if org and org.org_code else ""

    styles = getSampleStyleSheet()
    header_style = ParagraphStyle('ReportHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=14, textColor=colors.HexColor('#0f172a'))
    subtitle_style = ParagraphStyle('ReportSub', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#64748b'))
    bold_style = ParagraphStyle('ReportBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, textColor=colors.HexColor('#1e293b'))
    normal_style = ParagraphStyle('ReportNormal', parent=styles['Normal'], fontName='Helvetica', fontSize=8, textColor=colors.HexColor('#334155'))

    story = []

    # 1. Header Banner
    date_range_str = f"From: {start_date or 'Earliest'} To: {end_date or 'Today'}"
    header_data = [
        [
            Paragraph(f"<b>{biz_name}</b><br/>{biz_code}{biz_addr}<br/>Tel: {biz_phone}", subtitle_style),
            Paragraph(f"<font color='#1a56db'><b>COLLECTIONS &amp; SALES REPORT</b></font><br/>{date_range_str}<br/><b>Printed:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", subtitle_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[320, 220])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1a56db'), spaceAfter=12))

    # 2. Executive KPI Summary Cards
    from app.utils.currency import format_currency
    total_col = report_data.get('total_collected_cents', 0)
    tx_count = report_data.get('transactions_count', 0)
    by_method = report_data.get('by_method', {})
    mpesa_total = by_method.get('MPESA_PAYBILL', 0) + by_method.get('MPESA_TILL', 0)
    bank_total = by_method.get('BANK_TRANSFER', 0)
    cash_total = by_method.get('CASH', 0)

    kpi_data = [
        [
            Paragraph("<b>Total Collections</b>", bold_style),
            Paragraph("<b>Transactions</b>", bold_style),
            Paragraph("<b>M-Pesa Collections</b>", bold_style),
            Paragraph("<b>Bank / Cash</b>", bold_style),
        ],
        [
            Paragraph(f"<font color='#0e9f6e'><b>{format_currency(total_col)}</b></font>", bold_style),
            Paragraph(f"<b>{tx_count}</b> receipts", normal_style),
            Paragraph(f"{format_currency(mpesa_total)}", normal_style),
            Paragraph(f"{format_currency(bank_total + cash_total)}", normal_style),
        ]
    ]
    kpi_table = Table(kpi_data, colWidths=[135, 135, 135, 135])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 15))

    # 3. Itemized Transaction / Sales Log
    tx_rows = [
        [
            Paragraph("<b>Receipt No</b>", bold_style),
            Paragraph("<b>Date</b>", bold_style),
            Paragraph("<b>Tenant &amp; Unit</b>", bold_style),
            Paragraph("<b>Property</b>", bold_style),
            Paragraph("<b>Method &amp; Ref</b>", bold_style),
            Paragraph("<b>Amount</b>", bold_style),
        ]
    ]

    payments = report_data.get('payments', [])
    for p in payments[:200]:  # Cap at 200 items per PDF page limit
        t_name = p.tenant.full_name if p.tenant else 'N/A'
        u_num = p.rental_unit.unit_number if p.rental_unit else 'N/A'
        prop_name = p.property.name if p.property else 'N/A'
        p_date = p.payment_date.strftime('%d/%m/%Y') if p.payment_date else ''
        p_ref = p.transaction_reference or 'N/A'
        p_amount = format_currency(p.amount_cents)

        tx_rows.append([
            Paragraph(f"{p.receipt_number}", normal_style),
            Paragraph(f"{p_date}", normal_style),
            Paragraph(f"{t_name} ({u_num})", normal_style),
            Paragraph(f"{prop_name}", normal_style),
            Paragraph(f"{p.payment_method}<br/><font color='#64748b'>{p_ref}</font>", normal_style),
            Paragraph(f"<b>{p_amount}</b>", normal_style),
        ])

    if len(payments) == 0:
        tx_rows.append([Paragraph("No transactions recorded for this period.", normal_style), "", "", "", "", ""])

    tx_table = Table(tx_rows, colWidths=[80, 55, 125, 110, 95, 75])
    tx_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(tx_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# Re-export advanced tenancy and property management PDF generators
from app.utils.advanced_pdf_generator import (
    generate_tenant_registration_form_pdf,
    generate_rent_demand_letter_pdf,
    generate_rent_arrears_statement_pdf,
    generate_deposit_receipt_pdf,
    generate_deposit_refund_statement_pdf,
    generate_move_in_inspection_pdf,
    generate_move_out_inspection_pdf,
    generate_tenancy_renewal_agreement_pdf,
    generate_maintenance_work_order_pdf,
    generate_property_occupancy_report_pdf,
)

