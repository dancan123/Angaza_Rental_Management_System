import io
import hashlib
from datetime import datetime

# Python 3.8 compatibility patch for ReportLab md5 usedforsecurity kwarg
_orig_md5 = hashlib.md5
def _safe_md5(*args, **kwargs):
    kwargs.pop('usedforsecurity', None)
    return _orig_md5(*args, **kwargs)
hashlib.md5 = _safe_md5

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
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

    settings = PersonalizationService.get_all_settings()
    biz_name = settings.get('business_name', 'Property Management System')
    biz_addr = settings.get('business_address', 'Nairobi, Kenya')
    biz_phone = settings.get('business_phone', '+254 700 000 000')
    biz_email = settings.get('business_email', 'info@primerent.co.ke')
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

    story = []

    # 1. Header: Company Info and Receipt Badge
    header_data = [
        [
            Paragraph(f"<b>{biz_name}</b><br/>{biz_addr}<br/>Tel: {biz_phone} | Email: {biz_email}", subtitle_style),
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
        [Paragraph("<b>#</b>", bold_style), Paragraph("<b>Description / Period</b>", bold_style), Paragraph("<b>Charge Type</b>", bold_style), Paragraph("<b>Allocated Amount</b>", bold_style)]
    ]

    if allocations:
        for idx, a in enumerate(allocations, start=1):
            c = a.rent_charge
            period_str = f"Period: {c.period_month}/{c.period_year}" if c else "General Credit"
            items_data.append([
                Paragraph(str(idx), normal_style),
                Paragraph(f"{c.description or 'Rent Payment'} ({period_str})", normal_style),
                Paragraph(c.charge_type if c else "RENT", normal_style),
                Paragraph(a.amount_display, bold_style)
            ])
    else:
        items_data.append([
            Paragraph("1", normal_style),
            Paragraph(payment.description or "Rent Account Payment", normal_style),
            Paragraph(payment.payment_method, normal_style),
            Paragraph(payment.amount_display, bold_style)
        ])

    items_data.append([
        Paragraph("<b>TOTAL RECEIVED</b>", bold_style),
        Paragraph("", normal_style),
        Paragraph("", normal_style),
        Paragraph(f"<b>{payment.amount_display}</b>", bold_style)
    ])

    items_table = Table(items_data, colWidths=[30, 290, 100, 120])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a56db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 30))

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

    # 3. Particulars
    items_data = [
        [Paragraph("<b>#</b>", bold_style), Paragraph("<b>Item Description</b>", bold_style), Paragraph("<b>Category</b>", bold_style), Paragraph("<b>Amount (KES)</b>", bold_style)],
        [
            Paragraph("1", normal_style),
            Paragraph(charge.description or f"Monthly Rental Charge ({charge.period_month:02d}/{charge.period_year})", normal_style),
            Paragraph(charge.charge_type, normal_style),
            Paragraph(charge.amount_display, bold_style)
        ],
        [
            Paragraph("<b>TOTAL DUE</b>", bold_style),
            Paragraph("", normal_style),
            Paragraph("", normal_style),
            Paragraph(f"<b>{charge.amount_display}</b>", bold_style)
        ]
    ]
    if charge.amount_paid_cents > 0:
        items_data.append([
            Paragraph("<b>LESS: AMOUNT PAID</b>", bold_style),
            Paragraph("", normal_style),
            Paragraph("", normal_style),
            Paragraph(f"<font color='#0e9f6e'><b>- {charge.paid_display}</b></font>", bold_style)
        ])
        items_data.append([
            Paragraph("<b>OUTSTANDING BALANCE</b>", bold_style),
            Paragraph("", normal_style),
            Paragraph("", normal_style),
            Paragraph(f"<font color='#dc2626'><b>{charge.balance_display}</b></font>", bold_style)
        ])

    items_table = Table(items_data, colWidths=[30, 290, 100, 120])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dc2626')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (3, 0), (3, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fef2f2')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 25))

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


def generate_guest_folio_pdf(reservation):
    """
    Generates an official PDF Guest Folio & Booking Receipt for Airbnb / Short-Stay Management.
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

    settings = PersonalizationService.get_all_settings()
    biz_name = settings.get('business_name', 'Angaza Hospitality & Short-Stay Suites')
    biz_phone = settings.get('business_phone', '+254 700 000 000')
    biz_email = settings.get('business_email', 'hospitality@primerent.co.ke')

    styles = getSampleStyleSheet()
    subtitle_style = ParagraphStyle('FolioSub', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#64748b'))
    bold_style = ParagraphStyle('FolioBold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#1e293b'))
    normal_style = ParagraphStyle('FolioNorm', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=colors.HexColor('#334155'))

    story = []

    # 1. Header with Airbnb brand red styling
    prop = reservation.rental_unit.property if reservation.rental_unit else None
    prop_name = prop.name if prop else biz_name
    prop_loc = prop.location if prop and prop.location else 'Prime Location, Kenya'

    header_data = [
        [
            Paragraph(f"<font color='#e11d48'><b>{biz_name}</b></font><br/><b>Property:</b> {prop_name}<br/>Location: {prop_loc}<br/>Guest Support: {biz_phone}", subtitle_style),
            Paragraph(f"<font color='#e11d48'><b>OFFICIAL GUEST FOLIO &amp; RECEIPT</b></font><br/><b>Reservation Ref:</b> <b>{reservation.reservation_code}</b><br/><b>Booking Source:</b> {reservation.booking_source}<br/><b>Status:</b> <b>{reservation.status}</b>", subtitle_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[310, 230])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#e11d48'), spaceAfter=15))

    # 2. Guest & Reservation Details Block
    guest = reservation.guest
    unit = reservation.rental_unit
    info_data = [
        [
            Paragraph("<b>PRIMARY GUEST:</b>", bold_style),
            Paragraph(f"{guest.full_name}", normal_style),
            Paragraph("<b>ROOM / SUITE:</b>", bold_style),
            Paragraph(f"{unit.unit_number}", bold_style)
        ],
        [
            Paragraph("<b>CONTACT PHONE:</b>", bold_style),
            Paragraph(f"{guest.phone}", normal_style),
            Paragraph("<b>ROOM CATEGORY:</b>", bold_style),
            Paragraph(f"{unit.unit_type} (Max {unit.max_guests} Guests)", normal_style)
        ],
        [
            Paragraph("<b>EMAIL ADDRESS:</b>", bold_style),
            Paragraph(f"{guest.email or 'N/A'}", normal_style),
            Paragraph("<b>CHECK-IN DATE:</b>", bold_style),
            Paragraph(f"{reservation.check_in_date.strftime('%d %b %Y')} (After 2:00 PM)", normal_style)
        ],
        [
            Paragraph("<b>NATIONALITY / ID:</b>", bold_style),
            Paragraph(f"{guest.nationality} | {guest.id_passport_number or 'N/A'}", normal_style),
            Paragraph("<b>CHECK-OUT DATE:</b>", bold_style),
            Paragraph(f"{reservation.check_out_date.strftime('%d %b %Y')} (By 10:00 AM)", normal_style)
        ]
    ]
    info_table = Table(info_data, colWidths=[110, 160, 110, 160])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff1f2')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#fecdd3')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#fecdd3')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 20))

    # 3. Itemized Charges Table
    items_data = [
        [Paragraph("<b>#</b>", bold_style), Paragraph("<b>Particulars</b>", bold_style), Paragraph("<b>Rate / Night</b>", bold_style), Paragraph("<b>Nights</b>", bold_style), Paragraph("<b>Total (KES)</b>", bold_style)],
        [
            Paragraph("1", normal_style),
            Paragraph(f"Short-Stay Accommodation: {unit.unit_number}", normal_style),
            Paragraph(reservation.daily_rate_display, normal_style),
            Paragraph(f"{reservation.num_nights} Night(s)", normal_style),
            Paragraph(reservation.total_stay_display, bold_style)
        ],
        [
            Paragraph("<b>TOTAL STAY CHARGES</b>", bold_style),
            Paragraph("", normal_style),
            Paragraph("", normal_style),
            Paragraph("", normal_style),
            Paragraph(f"<b>{reservation.total_stay_display}</b>", bold_style)
        ],
        [
            Paragraph("<b>TOTAL PAYMENTS RECORDED</b>", bold_style),
            Paragraph(f"Method: {reservation.payment_method} | Ref: {reservation.payment_reference or 'N/A'}", subtitle_style),
            Paragraph("", normal_style),
            Paragraph("", normal_style),
            Paragraph(f"<font color='#0e9f6e'><b>- {reservation.paid_amount_display}</b></font>", bold_style)
        ],
        [
            Paragraph("<b>OUTSTANDING FOLIO BALANCE</b>", bold_style),
            Paragraph("", normal_style),
            Paragraph("", normal_style),
            Paragraph("", normal_style),
            Paragraph(f"<font color=\"{'#dc2626' if reservation.balance_cents > 0 else '#0e9f6e'}\"><b>{reservation.balance_display if reservation.balance_cents > 0 else 'SETTLED IN FULL ✅'}</b></font>", bold_style)
        ]
    ]
    items_table = Table(items_data, colWidths=[25, 235, 100, 60, 120])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e11d48')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fff1f2')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 25))

    # 4. House Rules and Guest Sign-off
    house_rules_data = [
        [
            Paragraph("<b>HOUSE RULES &amp; POLICIES:</b><br/>&bull; Strict check-out by 10:00 AM on departure date.<br/>&bull; No smoking inside suites. Please dispose of waste responsibly.<br/>&bull; Quiet hours observed between 10:00 PM and 7:00 AM.", subtitle_style),
            Paragraph(f"<b>GUEST VERIFICATION:</b><br/>Folio generated on: {datetime.utcnow().strftime('%d %b %Y %H:%M')}<br/>We wish you a wonderful stay with us!<br/>Support Hotline: {biz_phone}", subtitle_style)
        ]
    ]
    rules_table = Table(house_rules_data, colWidths=[270, 270])
    rules_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(rules_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


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

    ledger_data.append([
        Paragraph("<b>TOTALS</b>", bold_style),
        Paragraph("", normal_style),
        Paragraph("", normal_style),
        Paragraph(f"<b>{format_currency(total_debits)}</b>", bold_style),
        Paragraph(f"<b>{format_currency(total_credits)}</b>", bold_style),
        Paragraph(f"<b>{format_currency(running_bal)}</b>", bold_style)
    ])

    ledger_table = Table(ledger_data, colWidths=[65, 80, 165, 75, 75, 80])
    ledger_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0284c7')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
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

