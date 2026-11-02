from datetime import datetime
from io import BytesIO
from flask import Blueprint, render_template, request, send_file
from flask_login import login_required
from app.models.property import Property
from app.models.user import Landlord
from app.services.report_service import ReportService
from app.utils.decorators import permission_required

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

@reports_bp.route('/')
@login_required
@permission_required('reports.view')
def index():
    properties = Property.query.all()
    landlords = Landlord.query.filter_by(is_active=True).all()
    return render_template('reports/index.html', properties=properties, landlords=landlords)

@reports_bp.route('/collection')
@login_required
@permission_required('reports.view')
def collection():
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')
    property_id = request.args.get('property_id', type=int)
    method = request.args.get('payment_method')

    start_date = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else None
    end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else None

    report = ReportService.get_collection_report(start_date, end_date, property_id, method)
    properties = Property.query.all()

    return render_template(
        'reports/collection.html',
        report=report,
        properties=properties,
        start_date=start_str,
        end_date=end_str,
        selected_property=property_id,
        selected_method=method
    )

@reports_bp.route('/arrears')
@login_required
@permission_required('reports.view')
def arrears():
    property_id = request.args.get('property_id', type=int)
    report = ReportService.get_arrears_report(property_id)
    properties = Property.query.all()

    return render_template(
        'reports/arrears.html',
        report=report,
        properties=properties,
        selected_property=property_id
    )

@reports_bp.route('/income-statement')
@login_required
@permission_required('reports.view')
def income_statement():
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')
    property_id = request.args.get('property_id', type=int)

    start_date = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else None
    end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else None

    report = ReportService.get_income_statement(start_date, end_date, property_id)
    properties = Property.query.all()

    return render_template(
        'reports/income_statement.html',
        report=report,
        properties=properties,
        start_date=start_str,
        end_date=end_str,
        selected_property=property_id
    )

@reports_bp.route('/landlord-statement')
@login_required
@permission_required('reports.view')
def landlord_statement():
    landlord_id = request.args.get('landlord_id', type=int)
    landlords = Landlord.query.filter_by(is_active=True).all()

    if not landlord_id and landlords:
        landlord_id = landlords[0].id

    report = ReportService.get_landlord_statement(landlord_id) if landlord_id else None

    return render_template(
        'reports/landlord_statement.html',
        report=report,
        landlords=landlords,
        selected_landlord=landlord_id
    )

@reports_bp.route('/export/collection.xlsx')
@login_required
@permission_required('reports.export')
def export_collection_excel():
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')
    property_id = request.args.get('property_id', type=int)
    method = request.args.get('payment_method')

    start_date = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else None
    end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else None

    report = ReportService.get_collection_report(start_date, end_date, property_id, method)
    excel_bytes = ReportService.export_collection_excel(report)

    return send_file(
        BytesIO(excel_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"Rent_Collection_Report_{datetime.utcnow().strftime('%Y%m%d')}.xlsx"
    )

@reports_bp.route('/export/arrears.xlsx')
@login_required
@permission_required('reports.export')
def export_arrears_excel():
    property_id = request.args.get('property_id', type=int)
    report = ReportService.get_arrears_report(property_id)
    excel_bytes = ReportService.export_arrears_excel(report)

    return send_file(
        BytesIO(excel_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"Tenant_Arrears_Report_{datetime.utcnow().strftime('%Y%m%d')}.xlsx"
    )

@reports_bp.route('/export/vacant-units.xlsx')
@login_required
@permission_required('reports.export')
def export_vacant_excel():
    property_id = request.args.get('property_id', type=int)
    excel_bytes = ReportService.export_vacant_houses_excel(property_id)

    return send_file(
        BytesIO(excel_bytes),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"Vacant_Houses_Report_{datetime.utcnow().strftime('%Y%m%d')}.xlsx"
    )


