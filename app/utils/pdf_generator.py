import io
import hashlib

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
