from datetime import datetime, date, timedelta
import urllib.parse
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.extensions import db
from app.models.property import Property, RentalUnit
from app.models.booking import Booking
from app.models.lead import HouseSeekerLead, ExternalPropertyListing
from app.models.communication import Notification
from app.utils.currency import to_cents, from_cents, format_currency
from app.services.personalization_service import PersonalizationService

public_bp = Blueprint('public', __name__)

@public_bp.route('/vacancies')
def vacancies():
    """
    Public Vacant Houses & Rooms Portal:
    Accessible by external website visitors and prospective tenants without login.
    """
    property_id = request.args.get('property_id', type=int)
    unit_type = request.args.get('type')
    max_rent = request.args.get('max_rent', type=float)

    query = RentalUnit.query.filter_by(occupancy_status='VACANT')
    if property_id:
        query = query.filter_by(property_id=property_id)
    if unit_type:
        query = query.filter_by(unit_type=unit_type)
    if max_rent:
        query = query.filter(RentalUnit.rent_amount_cents <= to_cents(max_rent))

    vacant_units = query.order_by(RentalUnit.rent_amount_cents.asc()).all()
    properties = Property.query.filter_by(management_status='ACTIVE').all()

    # Query published external / partner landlord apartments
    ext_query = ExternalPropertyListing.query.filter_by(status='PUBLISHED')
    if unit_type:
        ext_query = ext_query.filter_by(unit_type=unit_type)
    if max_rent:
        ext_query = ext_query.filter(ExternalPropertyListing.monthly_rent_cents <= to_cents(max_rent))
    external_listings = ext_query.order_by(ExternalPropertyListing.created_at.desc()).all()

    currency = PersonalizationService.get_setting('currency', 'KES')
    business_phone = PersonalizationService.get_setting('business_phone', '+254700000000')
    business_email = PersonalizationService.get_setting('business_email', 'info@rentalsystem.co.ke')
    clean_phone = ''.join(c for c in business_phone if c.isdigit())
    if clean_phone.startswith('0'):
        clean_phone = '254' + clean_phone[1:]
    elif not clean_phone.startswith('254') and len(clean_phone) == 9:
        clean_phone = '254' + clean_phone

    # Default WhatsApp pre-filled inquiry text
    wa_default_msg = urllib.parse.quote("Hello, I am interested in renting a house/apartment with your management. Please share details.")

    return render_template(
        'public/vacancies.html',
        units=vacant_units,
        external_listings=external_listings,
        properties=properties,
        selected_property=property_id,
        selected_type=unit_type,
        max_rent=max_rent,
        currency=currency,
        business_phone=business_phone,
        business_email=business_email,
        clean_phone=clean_phone,
        wa_default_msg=wa_default_msg
    )

@public_bp.route('/vacancies/inquire', methods=['POST'])
def inquire():
    """
    Public booking inquiry submitted by prospective tenant from external site.
    """
    unit_id = request.form.get('unit_id', type=int)
    name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    id_num = request.form.get('id_number', '').strip()
    move_in_str = request.form.get('expected_move_in')
    notes = request.form.get('notes', '').strip()

    if not unit_id or not name or not phone:
        flash('Name, telephone number, and rental unit are required.', 'danger')
        return redirect(url_for('public.vacancies'))

    unit = RentalUnit.query.get_or_404(unit_id)
    expected_date = datetime.strptime(move_in_str, '%Y-%m-%d').date() if move_in_str else date.today() + timedelta(days=7)

    ref = f"INQ-{date.today().strftime('%Y%m')}-{unit.id}-{int(datetime.utcnow().timestamp()) % 10000}"

    booking = Booking(
        rental_unit_id=unit.id,
        booking_reference=ref,
        prospective_name=name,
        prospective_phone=phone,
        prospective_email=email,
        prospective_id_number=id_num,
        booking_date=date.today(),
        expected_move_in_date=expected_date,
        booking_deposit_cents=0,
        expiry_date=date.today() + timedelta(days=14),
        status="PENDING",
        notes=f"External web inquiry: {notes}" if notes else "Inquiry from public vacancies portal."
    )
    db.session.add(booking)

    # Dispatch alerts to Property Managers and Caretakers
    prop_name = unit.property.name if unit.property else 'Property'
    landlord_id = unit.property.landlord_id if unit.property else None

    alert_msg = (
        f"NEW PROSPECTIVE TENANT INQUIRY!\n"
        f"Unit: {unit.unit_number} ({prop_name})\n"
        f"Prospective Tenant: {name}\n"
        f"Phone: {phone}\n"
        f"Email: {email or 'N/A'}\n"
        f"Expected Move-In: {expected_date.strftime('%d/%m/%Y')}\n"
        f"Ref: {ref}"
    )

    notif = Notification(
        landlord_id=landlord_id,
        title=f"New Web Inquiry: {unit.unit_number} ({prop_name})",
        message=alert_msg,
        channel='IN_APP',
        notification_type='BOOKING_CREATED',
        sent_status='SENT',
        sent_at=datetime.utcnow()
    )
    db.session.add(notif)
    db.session.commit()

    flash(f"Thank you, {name}! Your inquiry for Unit {unit.unit_number} has been received (Ref: {ref}). Our property management team will contact you shortly.", 'success')
    return redirect(url_for('public.vacancies'))

@public_bp.route('/vacancies/house-alert', methods=['POST'])
def register_house_alert():
    """
    Prospective Tenant Waitlist & House Alerts Registration:
    Captures house seeker details (budget, preferred unit type, preferred locations, contact method: WhatsApp, SMS, Email, Call).
    """
    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    unit_type = request.form.get('unit_type', '').strip()
    locations = request.form.get('locations', '').strip()
    budget_raw = request.form.get('max_budget', type=float)
    move_in_str = request.form.get('expected_move_in')
    contact_method = request.form.get('contact_method', 'WHATSAPP')
    notes = request.form.get('notes', '').strip()

    if not full_name or not phone:
        flash('Full Name and Phone number are required to register for house notifications.', 'danger')
        return redirect(url_for('public.vacancies'))

    budget_cents = to_cents(budget_raw) if budget_raw and budget_raw > 0 else 0
    move_in_date = None
    if move_in_str:
        try:
            move_in_date = datetime.strptime(move_in_str, '%Y-%m-%d').date()
        except Exception:
            move_in_date = None

    lead = HouseSeekerLead(
        full_name=full_name,
        phone=phone,
        email=email if email else None,
        preferred_unit_type=unit_type if unit_type else 'ANY',
        preferred_locations=locations if locations else 'Any Area',
        max_budget_cents=budget_cents,
        expected_move_in_date=move_in_date,
        preferred_contact_method=contact_method,
        notes=notes,
        status='NEW'
    )
    db.session.add(lead)

    # In-App notification to Property Managers
    budget_label = format_currency(budget_cents) if budget_cents > 0 else "Flexible"
    notif_msg = (
        f"NEW HOUSE SEEKER ALERT REQUEST!\n"
        f"Name: {full_name}\n"
        f"Phone: {phone}\n"
        f"Email: {email or 'N/A'}\n"
        f"Preferred House: {unit_type or 'Any'}\n"
        f"Target Locations: {locations or 'Any'}\n"
        f"Max Budget: {budget_label}\n"
        f"Preferred Channel: {contact_method}\n"
        f"Expected Move-In: {move_in_date.strftime('%d/%m/%Y') if move_in_date else 'Flexible'}\n"
        f"Notes: {notes or 'None'}"
    )

    notif = Notification(
        title=f"New House Alert Lead: {full_name} ({unit_type})",
        message=notif_msg,
        channel='IN_APP',
        notification_type='NEW_TENANT',
        sent_status='SENT',
        sent_at=datetime.utcnow()
    )
    db.session.add(notif)
    db.session.commit()

    flash(
        f"Awesome, {full_name}! We have saved your house preferences for {unit_type or 'rentals'} in {locations or 'your preferred areas'}. "
        f"We will notify you via {contact_method} the moment a matching vacant unit becomes available!",
        'success'
    )
    return redirect(url_for('public.vacancies'))

@public_bp.route('/vacancies/list-property', methods=['POST'])
def list_property_lead():
    """
    Landlord / Property Owner Onboarding Lead:
    Allows outside apartment owners, landlords, or agents to submit their vacant building/apartments
    for marketing, tenant matching, and listing on the public platform.
    """
    owner_name = request.form.get('owner_name', '').strip()
    owner_phone = request.form.get('owner_phone', '').strip()
    owner_email = request.form.get('owner_email', '').strip()
    property_title = request.form.get('property_title', '').strip()
    location = request.form.get('location', '').strip()
    property_type = request.form.get('property_type', 'APARTMENT').strip()
    num_vacant = request.form.get('num_vacant_units', 1, type=int)
    rent_range = request.form.get('rent_range', '').strip()
    description = request.form.get('description', '').strip()

    if not owner_name or not owner_phone or not property_title or not location:
        flash('Owner Name, Telephone, Property Name, and Location are mandatory to submit a listing.', 'danger')
        return redirect(url_for('public.vacancies'))

    # Parse approximate rent if numeric
    rent_cents = 0
    clean_digits = ''.join(c for c in rent_range if c.isdigit())
    if clean_digits:
        try:
            rent_cents = int(clean_digits) * 100
        except Exception:
            rent_cents = 0

    new_listing = ExternalPropertyListing(
        owner_name=owner_name,
        owner_phone=owner_phone,
        owner_email=owner_email,
        property_title=property_title,
        location=location,
        property_type=property_type,
        unit_type='APARTMENT',
        monthly_rent_cents=rent_cents,
        description=f"{num_vacant} vacant unit(s). {description}".strip(),
        status='PENDING'
    )
    db.session.add(new_listing)

    alert_msg = (
        f"NEW EXTERNAL LANDLORD LISTING SUBMISSION!\n"
        f"Owner/Agent: {owner_name}\n"
        f"Phone: {owner_phone}\n"
        f"Email: {owner_email or 'N/A'}\n"
        f"Property: {property_title} ({property_type})\n"
        f"Location: {location}\n"
        f"Vacant Units to Fill: {num_vacant}\n"
        f"Expected Rent: {rent_range or 'Negotiable'}\n"
        f"Details: {description or 'None'}"
    )

    notif = Notification(
        title=f"New Property Listing Lead: {property_title} by {owner_name}",
        message=alert_msg,
        channel='IN_APP',
        notification_type='NEW_TENANT',
        sent_status='SENT',
        sent_at=datetime.utcnow()
    )
    db.session.add(notif)
    db.session.commit()

    flash(
        f"Thank you, {owner_name}! Your property '{property_title}' ({location}) has been submitted for review. "
        f"Our management and marketing team will contact you on {owner_phone} to verify and publish your vacant units!",
        'success'
    )
    return redirect(url_for('public.vacancies'))

@public_bp.route('/vacancies/inquire-external', methods=['POST'])
def inquire_external_lead():
    """
    Prospective Tenant Inquiry for an External / Partner Listing:
    Routes directly to Angaza Tenacity management desk, keeping landlord identity private.
    """
    listing_id = request.form.get('listing_id', type=int)
    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    move_in_str = request.form.get('expected_move_in')
    notes = request.form.get('notes', '').strip()

    if not listing_id or not full_name or not phone:
        flash('Full Name and Phone Number are required to submit an application/inquiry.', 'danger')
        return redirect(url_for('public.vacancies'))

    listing = db.session.get(ExternalPropertyListing, listing_id)
    if not listing:
        flash('Requested property listing could not be found.', 'danger')
        return redirect(url_for('public.vacancies'))

    move_in_date = None
    if move_in_str:
        try:
            move_in_date = datetime.strptime(move_in_str, '%Y-%m-%d').date()
        except Exception:
            move_in_date = None

    lead = HouseSeekerLead(
        full_name=full_name,
        phone=phone,
        email=email,
        preferred_unit_type=listing.unit_type,
        preferred_locations=listing.location,
        max_budget_cents=listing.monthly_rent_cents,
        expected_move_in_date=move_in_date,
        preferred_contact_method='WHATSAPP',
        notes=f"Inquired specifically for partner listing: '{listing.property_title}' (Ref ID: #{listing.id}). Notes: {notes}".strip(),
        status='NEW'
    )
    db.session.add(lead)

    alert_msg = (
        f"NEW TENANT INQUIRY FOR PARTNER LISTING!\n"
        f"Listing: {listing.property_title} (#{listing.id})\n"
        f"Location: {listing.location}\n"
        f"Rent: {listing.rent_display}\n"
        f"Applicant: {full_name}\n"
        f"Phone: {phone}\n"
        f"Email: {email or 'N/A'}\n"
        f"Move-In Target: {move_in_date.strftime('%d/%m/%Y') if move_in_date else 'Immediate'}\n"
        f"Landlord on File: {listing.owner_name} ({listing.owner_phone})\n"
        f"Action: Contact tenant or allocate unit via Marketplace Hub."
    )

    notif = Notification(
        title=f"New Seeker Application: {listing.property_title} by {full_name}",
        message=alert_msg,
        channel='IN_APP',
        notification_type='NEW_TENANT',
        sent_status='SENT',
        sent_at=datetime.utcnow()
    )
    db.session.add(notif)
    db.session.commit()

    flash(
        f"Thank you, {full_name}! Your application for '{listing.property_title}' has been received by Angaza Tenacity. "
        f"Our property management team will contact you on {phone} to arrange physical viewing and allocate the unit!",
        'success'
    )
    return redirect(url_for('public.vacancies'))

@public_bp.route('/api/v1/vacant-units')
def api_vacant_units():
    """
    Public JSON REST API endpoint:
    Allows any external website (WordPress, Next.js, mobile app) to query available vacant units.
    """
    property_id = request.args.get('property_id', type=int)
    query = RentalUnit.query.filter_by(occupancy_status='VACANT')
    if property_id:
        query = query.filter_by(property_id=property_id)

    units = query.order_by(RentalUnit.rent_amount_cents.asc()).all()
    currency = PersonalizationService.get_setting('currency', 'KES')

    result = []
    for u in units:
        result.append({
            'id': u.id,
            'unit_number': u.unit_number,
            'property_id': u.property_id,
            'property_name': u.property.name if u.property else None,
            'property_location': u.property.location if u.property else None,
            'building': u.building.name if u.building else None,
            'floor': u.floor.floor_name if u.floor else None,
            'unit_type': u.unit_type,
            'monthly_rent': float(from_cents(u.rent_amount_cents)),
            'deposit_required': float(from_cents(u.deposit_amount_cents)),
            'currency': currency,
            'bedrooms': u.bedrooms,
            'bathrooms': u.bathrooms,
            'amenities': u.amenities,
            'description': u.description,
            'availability_date': u.availability_date.strftime('%Y-%m-%d') if u.availability_date else 'Immediate',
            'inquiry_url': url_for('public.vacancies', property_id=u.property_id, _external=True)
        })

    return jsonify({
        'status': 'success',
        'count': len(result),
        'currency': currency,
        'vacant_units': result
    })


# ============================================================================
# MULTI-TENANT SUBDOMAIN & EXTERNAL BRANDED WEBSITES FOR LANDLORDS & BUSINESSES
# ============================================================================

def _clean_phone_for_wa(raw_phone):
    """Formats phone number to international WhatsApp format (254XXXXXXXXX)."""
    if not raw_phone:
        return None
    clean = ''.join(c for c in raw_phone if c.isdigit())
    if clean.startswith('0'):
        clean = '254' + clean[1:]
    elif not clean.startswith('254') and len(clean) == 9:
        clean = '254' + clean
    return clean if len(clean) >= 10 else None


def _find_organization_by_slug_or_code(identifier):
    """Resolves an Organization by its slug or business/org code."""
    from app.models.organization import Organization
    if not identifier:
        return None
    ident = identifier.strip().lower()
    return Organization.query.filter(
        (db.func.lower(Organization.slug) == ident) |
        (db.func.lower(Organization.org_code) == ident)
    ).first()


@public_bp.route('/site/<slug>')
@public_bp.route('/site/<slug>/')
def tenant_site(slug):
    """
    Public External Website for an Individual Landlord / Management Company:
    Provides branded property discovery, rental vacancy applications, and Airbnb short-stay bookings.
    Zero cross-tenant data bleed.
    """
    from app.models.organization import Organization
    org = _find_organization_by_slug_or_code(slug)
    if not org:
        from flask import abort
        abort(404, description=f"Organization website '{slug}' not found.")

    if org.is_suspended:
        return render_template('public/suspended_site.html', org=org), 503

    # 1. Properties belonging exclusively to this organization
    properties = Property.query.filter_by(organization_id=org.id, management_status='ACTIVE').all()
    property_ids = [p.id for p in properties]

    # 2. Long-term vacant units
    vacant_units = []
    if property_ids and org.enable_rentals:
        vacant_units = RentalUnit.query.filter(
            RentalUnit.property_id.in_(property_ids),
            RentalUnit.occupancy_status == 'VACANT',
            RentalUnit.operational_type == 'LONG_TERM'
        ).order_by(RentalUnit.rent_amount_cents.asc()).all()

    # 3. Airbnb / Short-Stay executive rooms
    airbnb_rooms = []
    if property_ids and org.enable_hospitality:
        airbnb_rooms = RentalUnit.query.filter(
            RentalUnit.property_id.in_(property_ids),
            RentalUnit.operational_type == 'SHORT_STAY'
        ).order_by(RentalUnit.daily_rate_cents.asc()).all()

    # Contact & WhatsApp details
    contact_phone = org.contact_phone or PersonalizationService.get_setting('business_phone', '+254700000000')
    clean_phone = _clean_phone_for_wa(contact_phone)
    wa_msg = urllib.parse.quote(f"Hello {org.name}, I am interested in inquiring about your available properties and short-stay suites.")

    return render_template(
        'public/tenant_website.html',
        org=org,
        properties=properties,
        vacant_units=vacant_units,
        airbnb_rooms=airbnb_rooms,
        clean_phone=clean_phone,
        wa_default_msg=wa_msg
    )


@public_bp.route('/site/<slug>/inquire', methods=['POST'])
def tenant_inquire(slug):
    """
    Submits a prospective tenant rental inquiry / application to a specific organization.
    Saves a PENDING Booking and alerts the organization's property manager.
    """
    org = _find_organization_by_slug_or_code(slug)
    if not org:
        flash('Invalid property management organization.', 'danger')
        return redirect(url_for('public.vacancies'))

    if org.is_suspended:
        flash('Inquiries for this organization are temporarily paused due to administrative maintenance.', 'warning')
        return redirect(url_for('public.tenant_site', slug=slug))

    unit_id = request.form.get('unit_id', type=int)
    full_name = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    move_in_str = request.form.get('expected_move_in')
    notes = request.form.get('notes', '').strip()

    if not unit_id or not full_name or not phone:
        flash('Full Name, phone number, and rental unit are required.', 'danger')
        return redirect(url_for('public.tenant_site', slug=slug))

    unit = RentalUnit.query.get_or_404(unit_id)
    # Security checkpoint: Ensure unit belongs to this organization
    if not unit.property or unit.property.organization_id != org.id:
        flash('Requested unit does not belong to this organization.', 'danger')
        return redirect(url_for('public.tenant_site', slug=slug))

    expected_date = date.today() + timedelta(days=7)
    if move_in_str:
        try:
            expected_date = datetime.strptime(move_in_str, '%Y-%m-%d').date()
        except Exception:
            pass

    ref = f"INQ-{org.business_code}-{unit.id}-{int(datetime.utcnow().timestamp()) % 10000}"

    booking = Booking(
        rental_unit_id=unit.id,
        booking_reference=ref,
        prospective_name=full_name,
        prospective_phone=phone,
        prospective_email=email or None,
        booking_date=date.today(),
        expected_move_in_date=expected_date,
        expiry_date=date.today() + timedelta(days=14),
        status='PENDING',
        notes=f"External Web Lead for {org.name}: {notes}".strip()
    )
    db.session.add(booking)

    # In-app notification for the landlord / manager
    notif = Notification(
        landlord_id=unit.property.landlord_id,
        title=f"New Web Inquiry: Unit {unit.unit_number} ({unit.property.name})",
        message=(
            f"NEW PROSPECTIVE TENANT LEAD!\n"
            f"Business: {org.name} ({org.business_code})\n"
            f"Unit: {unit.unit_number} ({unit.property.name})\n"
            f"Applicant: {full_name}\n"
            f"Phone: {phone}\n"
            f"Target Move-In: {expected_date.strftime('%d/%m/%Y')}\n"
            f"Ref: {ref}"
        ),
        channel='IN_APP',
        notification_type='BOOKING_CREATED',
        sent_status='SENT',
        sent_at=datetime.utcnow()
    )
    db.session.add(notif)
    db.session.commit()

    flash(f"Thank you, {full_name}! Your inquiry for Unit {unit.unit_number} has been submitted to {org.name} (Ref: {ref}). We will reach out shortly on {phone}.", 'success')
    return redirect(url_for('public.tenant_site', slug=slug))


@public_bp.route('/site/<slug>/airbnb-inquire', methods=['POST'])
def tenant_airbnb_inquire(slug):
    """
    Submits an executive short-stay / Airbnb reservation request to a specific organization.
    Saves Guest record and HospitalityReservation with status PENDING.
    """
    from app.models.hospitality import Guest, HospitalityReservation
    org = _find_organization_by_slug_or_code(slug)
    if not org:
        flash('Invalid property management organization.', 'danger')
        return redirect(url_for('public.vacancies'))

    if org.is_suspended:
        flash('Inquiries for this organization are temporarily paused due to administrative maintenance.', 'warning')
        return redirect(url_for('public.tenant_site', slug=slug))

    unit_id = request.form.get('unit_id', type=int)
    guest_name = request.form.get('guest_name', '').strip()
    phone = request.form.get('phone', '').strip()
    check_in_str = request.form.get('check_in_date')
    check_out_str = request.form.get('check_out_date')
    num_guests = request.form.get('num_guests', 1, type=int)
    special_requests = request.form.get('special_requests', '').strip()

    if not unit_id or not guest_name or not phone or not check_in_str or not check_out_str:
        flash('Name, telephone, check-in, and check-out dates are mandatory.', 'danger')
        return redirect(url_for('public.tenant_site', slug=slug))

    unit = RentalUnit.query.get_or_404(unit_id)
    if not unit.property or unit.property.organization_id != org.id:
        flash('Requested short-stay suite does not belong to this organization.', 'danger')
        return redirect(url_for('public.tenant_site', slug=slug))

    try:
        check_in = datetime.strptime(check_in_str, '%Y-%m-%d').date()
        check_out = datetime.strptime(check_out_str, '%Y-%m-%d').date()
    except Exception:
        flash('Invalid date format provided.', 'danger')
        return redirect(url_for('public.tenant_site', slug=slug))

    if check_out <= check_in:
        flash('Check-out date must be after check-in date.', 'danger')
        return redirect(url_for('public.tenant_site', slug=slug))

    num_nights = (check_out - check_in).days
    total_cents = num_nights * unit.daily_rate_cents

    # Find or create guest
    names = guest_name.split(' ', 1)
    first_name = names[0]
    last_name = names[1] if len(names) > 1 else 'Guest'
    
    guest = Guest.query.filter_by(phone=phone).first()
    if not guest:
        guest = Guest(
            first_name=first_name,
            last_name=last_name,
            phone=phone
        )
        db.session.add(guest)
        db.session.flush()

    res_code = f"RES-{org.business_code}-{int(datetime.utcnow().timestamp()) % 100000}"

    reservation = HospitalityReservation(
        reservation_code=res_code,
        guest_id=guest.id,
        rental_unit_id=unit.id,
        check_in_date=check_in,
        check_out_date=check_out,
        num_guests=num_guests,
        num_nights=num_nights,
        daily_rate_cents=unit.daily_rate_cents,
        total_stay_cents=total_cents,
        paid_amount_cents=0,
        booking_source='WEBSITE',
        status='CONFIRMED',
        special_requests=f"Website Booking via {org.name}: {special_requests}".strip()
    )
    db.session.add(reservation)

    # In-app notification to Hospitality Desk
    notif = Notification(
        landlord_id=unit.property.landlord_id,
        title=f"New Airbnb Booking: Room {unit.unit_number} ({res_code})",
        message=(
            f"NEW SHORT-STAY RESERVATION!\n"
            f"Business: {org.name} ({org.business_code})\n"
            f"Room: {unit.unit_number} ({unit.property.name})\n"
            f"Guest: {guest_name} ({phone})\n"
            f"Dates: {check_in.strftime('%d/%m/%Y')} to {check_out.strftime('%d/%m/%Y')} ({num_nights} nights)\n"
            f"Total: {format_currency(total_cents)}\n"
            f"Booking Code: {res_code}"
        ),
        channel='IN_APP',
        notification_type='BOOKING_CREATED',
        sent_status='SENT',
        sent_at=datetime.utcnow()
    )
    db.session.add(notif)
    db.session.commit()

    flash(
        f"Thank you, {guest_name}! Your reservation request for Room {unit.unit_number} has been registered (Code: {res_code}). "
        f"Our hospitality desk at {org.name} will contact you on {phone} with check-in instructions.",
        'success'
    )
    return redirect(url_for('public.tenant_site', slug=slug))

