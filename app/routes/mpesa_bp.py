from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required
from app.extensions import db, csrf
from app.models.gateway import PaymentGatewayConfig, PaymentCallback
from app.models.property import Property, RentalUnit
from app.models.tenant import Tenant
from app.services.mpesa_service import DarajaClient, MpesaCallbackHandler
from app.utils.decorators import permission_required

mpesa_bp = Blueprint('mpesa', __name__, url_prefix='/mpesa')

@mpesa_bp.route('/')
@login_required
@permission_required('mpesa.manage')
def index():
    configs = PaymentGatewayConfig.query.all()
    callbacks = PaymentCallback.query.order_by(PaymentCallback.created_at.desc()).limit(50).all()
    properties = Property.query.all()
    vacant_or_all_units = RentalUnit.query.all()
    active_tenants = Tenant.query.filter_by(is_active=True).all()

    return render_template(
        'mpesa/index.html',
        configs=configs,
        callbacks=callbacks,
        properties=properties,
        units=vacant_or_all_units,
        tenants=active_tenants
    )

@mpesa_bp.route('/config/save', methods=['POST'])
@login_required
@permission_required('mpesa.manage')
def save_config():
    gateway_id = request.form.get('config_id', type=int)
    name = request.form.get('name', '').strip()
    gateway_type = request.form.get('gateway_type', 'MPESA_PAYBILL')
    shortcode = request.form.get('shortcode', '').strip()
    till_number = request.form.get('till_number', '').strip()
    consumer_key = request.form.get('consumer_key', '').strip()
    consumer_secret = request.form.get('consumer_secret', '').strip()
    passkey = request.form.get('passkey', '').strip()
    callback_url = request.form.get('callback_url', '').strip()
    property_id = request.form.get('property_id', type=int)
    is_sandbox = bool(request.form.get('is_sandbox'))

    if gateway_id:
        cfg = db.session.get(PaymentGatewayConfig, gateway_id)
        if not cfg:
            from flask import abort; abort(404)
    else:
        cfg = PaymentGatewayConfig()
        db.session.add(cfg)

    cfg.name = name
    cfg.gateway_type = gateway_type
    cfg.shortcode = shortcode
    cfg.till_number = till_number
    cfg.consumer_key = consumer_key
    cfg.consumer_secret = consumer_secret
    cfg.passkey = passkey
    cfg.callback_url = callback_url
    cfg.property_id = property_id if property_id else None
    cfg.is_sandbox = is_sandbox

    db.session.commit()
    flash(f"M-Pesa Gateway configuration '{name}' saved successfully.", 'success')
    return redirect(url_for('mpesa.index'))

# ----------------- PUBLIC SAFARICOM DARAJA WEBHOOKS -----------------

@mpesa_bp.route('/c2b/confirmation', methods=['POST'])
@csrf.exempt
def c2b_confirmation():
    payload = request.get_json(force=True, silent=True) or request.form.to_dict()
    res, status_code = MpesaCallbackHandler.process_c2b_callback(payload)
    return jsonify(res), status_code

@mpesa_bp.route('/c2b/validation', methods=['POST'])
@csrf.exempt
def c2b_validation():
    # Safaricom validation hook: accepts or rejects transaction before debiting customer
    payload = request.get_json(force=True, silent=True) or request.form.to_dict()
    bill_ref = payload.get('BillRefNumber', '').strip().upper()

    # Validate if unit exists
    unit = RentalUnit.query.filter_by(unit_number=bill_ref).first()
    if unit:
        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"}), 200
    
    # Alternatively accept to reconciliation queue
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted to holding"}), 200

@mpesa_bp.route('/stk/callback', methods=['POST'])
@csrf.exempt
def stk_callback():
    payload = request.get_json(force=True, silent=True) or {}
    res, status_code = MpesaCallbackHandler.process_stk_callback(payload)
    return jsonify(res), status_code

# ----------------- STK PUSH TRIGGER & SANDBOX SIMULATOR -----------------

@mpesa_bp.route('/stk/initiate', methods=['POST'])
@login_required
@permission_required('mpesa.manage')
def initiate_stk():
    config_id = request.form.get('config_id', type=int)
    phone = request.form.get('phone', '').strip()
    amount = request.form.get('amount', type=int)
    unit_ref = request.form.get('account_reference', 'RENT').strip()

    config = db.session.get(PaymentGatewayConfig, config_id)
    if not config:
        from flask import abort; abort(404)
    client = DarajaClient(config)

    try:
        response = client.initiate_stk_push(phone, amount, unit_ref)
        if response.get('ResponseCode') == '0':
            flash(f"STK Push prompt sent to {phone}. Customer Prompt: {response.get('CustomerMessage')}", 'success')
        else:
            flash(f"STK Push rejected by Daraja: {response.get('errorMessage') or response.get('ResponseDescription')}", 'danger')
    except Exception as e:
        flash(f"STK Push error: {str(e)}", 'danger')

    return redirect(url_for('mpesa.index'))

@mpesa_bp.route('/simulate', methods=['POST'])
@login_required
@permission_required('mpesa.manage')
def simulate_c2b():
    trans_id = request.form.get('trans_id', '').strip().upper()
    amount = request.form.get('amount', 0)
    bill_ref = request.form.get('bill_ref', '').strip().upper()
    phone = request.form.get('phone', '254712345678').strip()
    first_name = request.form.get('first_name', 'John')
    last_name = request.form.get('last_name', 'Kamau')

    mock_payload = {
        "TransactionType": "Pay Bill",
        "TransID": trans_id,
        "TransTime": datetime.now().strftime('%Y%m%d%H%M%S'),
        "TransAmount": str(amount),
        "BusinessShortCode": "247247",
        "BillRefNumber": bill_ref,
        "InvoiceNumber": "",
        "OrgAccountBalance": "150000.00",
        "ThirdPartyTransID": "",
        "MSISDN": phone,
        "FirstName": first_name,
        "MiddleName": "",
        "LastName": last_name
    }

    res, status_code = MpesaCallbackHandler.process_c2b_callback(mock_payload)
    if status_code == 200 and res.get('ResultCode') == 0:
        flash(f"Simulated C2B callback processed successfully for Ref '{trans_id}'. Rent settled and landlord alerted!", 'success')
    else:
        flash(f"Simulation result [{status_code}]: {res.get('ResultDesc')}", 'warning')

    return redirect(url_for('mpesa.index'))

