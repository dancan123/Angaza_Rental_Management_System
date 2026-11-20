from datetime import datetime, date, timedelta
import urllib.parse
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import or_, func
from app.extensions import db
from app.models.organization import Organization
from app.models.property import Property, RentalUnit
from app.models.booking import Booking
from app.models.lead import HouseSeekerLead, ExternalPropertyListing
from app.models.communication import Notification
from app.utils.currency import to_cents, from_cents, format_currency
from app.services.personalization_service import PersonalizationService

public_bp = Blueprint('public', __name__)

# ---------------------------------------------------------------------------
# PLATFORM DIRECTORY — /vacancies (no org code)
# Shows a searchable directory of all active organizations.
# Never shows any property data — tenants must pick an org first.
# ---------------------------------------------------------------------------
@public_bp.route('/vacancies', endpoint='vacancies')
def vacancies_directory():
    """
    Public Platform Directory:
    - If a registered apartment / business user is logged in (non-superadmin),
      redirects them directly to their own dedicated vacancy window (/vacancies/<org_code>).
    - If a specific org_code query parameter is passed (?org_code=...), redirects to that org.
    - Superadmins and external platform visitors see the platform directory to browse
      registered organizations across all regions.
    """
    from flask_login import current_user

    # 1. Direct query param routing
    org_param = request.args.get('org_code') or request.args.get('org') or request.args.get('code')
    if org_param:
        return redirect(url_for('public.vacancies_by_org', org_code=org_param.strip()))

    # 2. Logged-in apartment / business user -> redirect to their own exclusive portal
    if current_user.is_authenticated and not current_user.is_superadmin():
        org = getattr(current_user, 'organization', None)
        if org and org.org_code and not request.args.get('directory') and not request.args.get('all'):
            return redirect(url_for('public.vacancies_by_org', org_code=org.org_code))

    search = request.args.get('search', '').strip()
    region_filter = request.args.get('region', '').strip()

    org_query = Organization.query.filter(
        Organization.is_active == True,
        Organization.subscription_status.in_(['ACTIVE', 'TRIAL']),
        Organization.org_code != None,
        Organization.org_code != 'ANG0001'   # exclude superadmin platform account
    )

    if search:
        term = f"%{search}%"
        org_query = org_query.filter(
            or_(
                Organization.name.ilike(term),
                Organization.region.ilike(term),
                Organization.county.ilike(term),
                Organization.town.ilike(term),
                Organization.org_code.ilike(term),
            )
        )
    if region_filter:
        org_query = org_query.filter(Organization.region.ilike(f"%{region_filter}%"))

    orgs = org_query.order_by(Organization.name.asc()).all()

    # Annotate each org with its live vacant unit count (for display on cards)
    org_data = []
    for org in orgs:
        prop_ids = [p.id for p in Property.query.filter_by(organization_id=org.id, management_status='ACTIVE').all()]
        vacant_count = RentalUnit.query.filter(
            RentalUnit.property_id.in_(prop_ids),
            RentalUnit.occupancy_status == 'VACANT'
        ).count() if prop_ids else 0
        partner_count = ExternalPropertyListing.query.filter_by(
            organization_id=org.id, status='PUBLISHED'
        ).count()
        org_data.append({
            'org': org,
            'vacant_count': vacant_count,
            'partner_count': partner_count,
            'total_listings': vacant_count + partner_count,
        })

    # Distinct regions for filter chips
    all_regions = sorted(list(set(
        o.region for o in Organization.query.filter(
            Organization.is_active == True,
            Organization.region != None,
            Organization.org_code != 'ANG0001'
        ).all() if o.region
    )))

    app_name = PersonalizationService.get_setting('business_name', 'Angaza Rental Management System')

    # Partner listings – published external listings (not tied to a specific org portal)
    partner_listings_q = ExternalPropertyListing.query.filter_by(status='PUBLISHED')
    if search:
        term = f"%{search}%"
        partner_listings_q = partner_listings_q.filter(
            or_(
                ExternalPropertyListing.property_title.ilike(term),
                ExternalPropertyListing.location.ilike(term),
            )
        )
    partner_listings = partner_listings_q.order_by(ExternalPropertyListing.created_at.desc()).all()

    return render_template(
        'public/vacancies_directory.html',
        org_data=org_data,
        search=search,
        region_filter=region_filter,
        all_regions=all_regions,
        app_name=app_name,
        partner_listings=partner_listings,
    )


# ---------------------------------------------------------------------------
# PER-ORG ISOLATED VACANCY PORTAL — /vacancies/<org_code>  &  /v/<org_code>
# ---------------------------------------------------------------------------
@public_bp.route('/vacancies/<org_code>', endpoint='vacancies_by_org')
@public_bp.route('/v/<org_code>', endpoint='vacancies_short')
def vacancies(org_code=None):
    """
    Per-Organization Isolated Public Vacancy Portal.
    Each landlord/organization has their own branded page — ZERO cross-org data.
    URL: /vacancies/ANG0002  or  /v/ANG0002
    """
    # Support legacy ?org_code= query param for backward compat
    if not org_code:
        org_code = request.args.get('org_code') or request.args.get('org') or request.args.get('code')

    # No org_code at all → redirect to directory
    if not org_code:
        return redirect(url_for('public.vacancies'))

    code_str = org_code.strip()
    target_org = Organization.query.filter(
        or_(
            func.upper(Organization.org_code) == code_str.upper(),
            Organization.slug == code_str.lower()
        )
    ).first()

    if not target_org:
        flash(f"Organization '{org_code}' was not found. Please check the link or search for your landlord below.", 'warning')
        return redirect(url_for('public.vacancies'))

    property_id = request.args.get('property_id', type=int)
    unit_type = request.args.get('type')
    max_rent = request.args.get('max_rent', type=float)
    location_filter = request.args.get('location', '').strip()

    # Active section tab: 'rental' | 'airbnb' | 'partner'
    active_section = request.args.get('section', 'rental')

    # Always scoped to this org — no global fallback
    base_q = RentalUnit.query.join(
        Property, RentalUnit.property_id == Property.id
    ).filter(Property.organization_id == target_org.id)

    # Long-term vacant rental units
    rental_q = base_q.filter(
        RentalUnit.occupancy_status == 'VACANT',
        RentalUnit.operational_type == 'LONG_TERM'
    )
    # Short-stay (Airbnb) rooms – all, regardless of occupancy (they can be booked for future dates)
    airbnb_q = base_q.filter(
        RentalUnit.operational_type == 'SHORT_STAY'
    )
    ext_query = ExternalPropertyListing.query.filter_by(organization_id=target_org.id, status='PUBLISHED')

    properties = Property.query.filter_by(organization_id=target_org.id, management_status='ACTIVE').all()

    if property_id:
        rental_q = rental_q.filter(RentalUnit.property_id == property_id)
        airbnb_q = airbnb_q.filter(RentalUnit.property_id == property_id)
    if unit_type:
        rental_q = rental_q.filter(RentalUnit.unit_type == unit_type)
        airbnb_q = airbnb_q.filter(RentalUnit.unit_type == unit_type)
        ext_query = ext_query.filter(ExternalPropertyListing.unit_type == unit_type)
    if max_rent:
        rental_q = rental_q.filter(RentalUnit.rent_amount_cents <= to_cents(max_rent))
        ext_query = ext_query.filter(ExternalPropertyListing.monthly_rent_cents <= to_cents(max_rent))
    if location_filter:
        loc_term = f"%{location_filter}%"
        rental_q = rental_q.filter(Property.location.ilike(loc_term))
        airbnb_q = airbnb_q.filter(Property.location.ilike(loc_term))
        ext_query = ext_query.filter(ExternalPropertyListing.location.ilike(loc_term))

    vacant_units = rental_q.order_by(RentalUnit.rent_amount_cents.asc()).all()
    airbnb_rooms = airbnb_q.order_by(RentalUnit.daily_rate_cents.asc()).all()
    external_listings = ext_query.order_by(ExternalPropertyListing.created_at.desc()).all()

    # Split partner/neighbour listings from own published listings
    partner_listings = [e for e in external_listings if getattr(e, 'is_partner_neighbour', True)]
    own_ext_listings  = [e for e in external_listings if not getattr(e, 'is_partner_neighbour', True)]

    currency = PersonalizationService.get_setting('currency', 'KES')

    business_name = target_org.name
    business_phone = target_org.contact_phone or PersonalizationService.get_setting('business_phone', '+254700000000')
    business_email = target_org.contact_email or PersonalizationService.get_setting('business_email', 'info@rentalsystem.co.ke')
    region_name = target_org.region or 'Kenya'
    county_name = target_org.county or ''
    town_name = target_org.town or ''

    clean_phone = ''.join(c for c in business_phone if c.isdigit())
    if clean_phone.startswith('0'):
        clean_phone = '254' + clean_phone[1:]
    elif not clean_phone.startswith('254') and len(clean_phone) == 9:
        clean_phone = '254' + clean_phone

    # Default WhatsApp pre-filled inquiry text
    wa_msg = f"Hello {business_name}, I saw your available properties in {region_name} on your public portal. Please share more details."
    wa_default_msg = urllib.parse.quote(wa_msg)

    # Extract distinct locations for quick filtering
    available_locations = sorted(list(set(
        [p.location.strip() for p in properties if p.location] +
        [e.location.strip() for e in external_listings if e.location]
    )))

    return render_template(
        'public/vacancies.html',
        units=vacant_units,
        airbnb_rooms=airbnb_rooms,
        external_listings=external_listings,
        partner_listings=partner_listings,
        own_ext_listings=own_ext_listings,
        properties=properties,
        selected_property=property_id,
        selected_type=unit_type,
        max_rent=max_rent,
        selected_location=location_filter,
        available_locations=available_locations,
        active_section=active_section,
        currency=currency,
        business_name=business_name,
        business_phone=business_phone,
        business_email=business_email,
        clean_phone=clean_phone,
        wa_default_msg=wa_default_msg,
        target_org=target_org,
        region_name=region_name,
        county_name=county_name,
        town_name=town_name
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
    org_code = request.form.get('org_code', '').strip()

    if not unit_id or not name or not phone:
        flash('Name, telephone number, and rental unit are required.', 'danger')
        if org_code:
            return redirect(url_for('public.vacancies_by_org', org_code=org_code))
        return redirect(url_for('public.vacancies'))

    unit = db.session.get(RentalUnit, unit_id)
    if not unit:
        from flask import abort
        abort(404)
    expected_date = datetime.strptime(move_in_str, '%Y-%m-%d').date() if move_in_str else date.today() + timedelta(days=7)

    # Security guard: if org_code provided, unit must belong to that org
    if org_code and unit.property:
        claimed_org = Organization.query.filter(
            or_(func.upper(Organization.org_code) == org_code.upper(),
                Organization.slug == org_code.lower())
        ).first()
        if claimed_org and unit.property.organization_id != claimed_org.id:
            flash('This unit does not belong to the selected organization.', 'danger')
            return redirect(url_for('public.vacancies_by_org', org_code=org_code))

    ref = f"INQ-{date.today().strftime('%Y%m')}-{unit.id}-{int(datetime.utcnow().timestamp()) % 10000}"

    # Always derive org_id from the unit's actual property — cannot be spoofed
    org_id = unit.property.organization_id if unit.property else None

    booking = Booking(
        organization_id=org_id,
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
    if org_code:
        return redirect(url_for('public.vacancies_by_org', org_code=org_code))
    return redirect(url_for('public.vacancies'))


@public_bp.route('/vacancies/airbnb-book', methods=['POST'])
def vacancies_airbnb_book():
    """
    Public Airbnb / Short-Stay Online Booking from /vacancies/<org_code> portal.
    Creates a HospitalityReservation with PENDING status and notifies the team.
    Data is strictly scoped to the unit's owning organization.
    """
    from app.models.hospitality import Guest, HospitalityReservation
    unit_id = request.form.get('unit_id', type=int)
    guest_name = request.form.get('guest_name', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    check_in_str = request.form.get('check_in_date', '').strip()
    check_out_str = request.form.get('check_out_date', '').strip()
    num_guests = request.form.get('num_guests', 1, type=int)
    special_requests = request.form.get('special_requests', '').strip()
    org_code = request.form.get('org_code', '').strip()

    if not unit_id or not guest_name or not phone or not check_in_str or not check_out_str:
        flash('Full name, phone, check-in and check-out dates are required to book.', 'danger')
        if org_code:
            return redirect(url_for('public.vacancies_by_org', org_code=org_code))
        return redirect(url_for('public.vacancies'))

    unit = db.session.get(RentalUnit, unit_id)
    if not unit or unit.operational_type != 'SHORT_STAY':
        flash('Requested Airbnb room could not be found or is not available for short-stay booking.', 'danger')
        if org_code:
            return redirect(url_for('public.vacancies_by_org', org_code=org_code))
        return redirect(url_for('public.vacancies'))

    # Security: unit must belong to the declared org
    if org_code and unit.property:
        claimed_org = Organization.query.filter(
            or_(func.upper(Organization.org_code) == org_code.upper(),
                Organization.slug == org_code.lower())
        ).first()
        if claimed_org and unit.property.organization_id != claimed_org.id:
            flash('This room does not belong to the selected organization.', 'danger')
            return redirect(url_for('public.vacancies_by_org', org_code=org_code))

    try:
        check_in = datetime.strptime(check_in_str, '%Y-%m-%d').date()
        check_out = datetime.strptime(check_out_str, '%Y-%m-%d').date()
    except Exception:
        flash('Invalid check-in or check-out date format.', 'danger')
        if org_code:
            return redirect(url_for('public.vacancies_by_org', org_code=org_code))
        return redirect(url_for('public.vacancies'))

    if check_out <= check_in:
        flash('Check-out date must be after check-in date.', 'danger')
        if org_code:
            return redirect(url_for('public.vacancies_by_org', org_code=org_code))
        return redirect(url_for('public.vacancies'))

    num_nights = (check_out - check_in).days
    total_cents = num_nights * unit.daily_rate_cents

    org = unit.property.organization if unit.property else None
    names = guest_name.strip().split(' ', 1)
    first_name = names[0]
    last_name = names[1] if len(names) > 1 else 'Guest'

    guest = Guest.query.filter_by(phone=phone).first()
    if not guest:
        guest = Guest(first_name=first_name, last_name=last_name, phone=phone, email=email or None, organization_id=org.id if org else None)
        db.session.add(guest)
        db.session.flush()
    elif org and not guest.organization_id:
        guest.organization_id = org.id

    res_code = f"STAY-{org.org_code if org else 'VIS'}-{int(datetime.utcnow().timestamp()) % 100000}"

    reservation = HospitalityReservation(
        organization_id=org.id if org else None,
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
        status='PENDING',
        special_requests=f"Online Portal Booking. {special_requests}".strip()
    )
    db.session.add(reservation)
    db.session.flush()

    # Dispatch multi-channel notifications (SMS, Email, WhatsApp, In-App) to Manager/Staff
    try:
        from app.services.notification_service import NotificationService
        NotificationService.notify_airbnb_booking(reservation)
    except Exception:
        pass

    # Auto-SMS to guest confirming the pending booking
    try:
        from app.services.sms_service import SmsService
        sms_msg = (
            f"Dear {first_name}, your Airbnb booking for {unit.unit_number} is PENDING confirmation! "
            f"Ref: {res_code}. Check-In: {check_in.strftime('%d/%m/%Y')}. "
            f"Total: {format_currency(total_cents)}. "
            f"Our team will contact you on {phone} to confirm and arrange payment."
        )
        SmsService.send_sms(
            to_phone=phone,
            message=sms_msg,
            notification_type='HOSPITALITY_RESERVATION',
            organization_id=org.id if org else None
        )
    except Exception:
        pass  # SMS failure should not block reservation creation

    db.session.commit()

    flash(
        f"Thank you, {guest_name}! Your Airbnb booking for {unit.unit_number} is registered (Ref: {res_code}). "
        f"Our hospitality team will confirm and contact you shortly on {phone}.",
        'success'
    )
    if org_code:
        return redirect(url_for('public.vacancies_by_org', org_code=org_code, section='airbnb'))
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
    org_code = request.form.get('org_code', '').strip()

    if not full_name or not phone:
        flash('Full Name and Phone number are required to register for house notifications.', 'danger')
        if org_code:
            return redirect(url_for('public.vacancies_by_org', org_code=org_code))
        return redirect(url_for('public.vacancies'))

    target_org = None
    if org_code:
        target_org = Organization.query.filter(
            or_(func.upper(Organization.org_code) == org_code.upper(), Organization.slug == org_code.lower())
        ).first()

    budget_cents = to_cents(budget_raw) if budget_raw and budget_raw > 0 else 0
    move_in_date = None
    if move_in_str:
        try:
            move_in_date = datetime.strptime(move_in_str, '%Y-%m-%d').date()
        except Exception:
            move_in_date = None

    lead = HouseSeekerLead(
        organization_id=target_org.id if target_org else None,
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
    if org_code:
        return redirect(url_for('public.vacancies_by_org', org_code=org_code))
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
    org_code = request.form.get('org_code', '').strip()

    if not owner_name or not owner_phone or not property_title or not location:
        flash('Owner Name, Telephone, Property Name, and Location are mandatory to submit a listing.', 'danger')
        if org_code:
            return redirect(url_for('public.vacancies_by_org', org_code=org_code))
        return redirect(url_for('public.vacancies'))

    target_org = None
    if org_code:
        target_org = Organization.query.filter(
            or_(func.upper(Organization.org_code) == org_code.upper(), Organization.slug == org_code.lower())
        ).first()

    # Parse approximate rent if numeric
    rent_cents = 0
    clean_digits = ''.join(c for c in rent_range if c.isdigit())
    if clean_digits:
        try:
            rent_cents = int(clean_digits) * 100
        except Exception:
            rent_cents = 0

    new_listing = ExternalPropertyListing(
        organization_id=target_org.id if target_org else None,
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
    if org_code:
        return redirect(url_for('public.vacancies_by_org', org_code=org_code))
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
    org_code = request.form.get('org_code', '').strip()

    if not listing_id or not full_name or not phone:
        flash('Full Name and Phone Number are required to submit an application/inquiry.', 'danger')
        if org_code:
            return redirect(url_for('public.vacancies_by_org', org_code=org_code))
        return redirect(url_for('public.vacancies'))

    listing = db.session.get(ExternalPropertyListing, listing_id)
    if not listing:
        flash('Requested property listing could not be found.', 'danger')
        if org_code:
            return redirect(url_for('public.vacancies_by_org', org_code=org_code))
        return redirect(url_for('public.vacancies'))

    move_in_date = None
    if move_in_str:
        try:
            move_in_date = datetime.strptime(move_in_str, '%Y-%m-%d').date()
        except Exception:
            move_in_date = None

    lead = HouseSeekerLead(
        organization_id=listing.organization_id if listing else None,
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
        f"Thank you, {full_name}! Your application for '{listing.property_title}' has been received. "
        f"Our property management team will contact you on {phone} to arrange physical viewing and allocate the unit!",
        'success'
    )
    if org_code:
        return redirect(url_for('public.vacancies_by_org', org_code=org_code))
    return redirect(url_for('public.vacancies'))




@public_bp.route('/api/v1/vacant-units')
def api_vacant_units():
    """
    Public JSON REST API endpoint:
    Allows any external website (WordPress, Next.js, mobile app) to query available vacant units.
    Optionally scoped to organization via ?org_code=ANGxxxx.
    """
    org_code = request.args.get('org_code') or request.args.get('org')
    property_id = request.args.get('property_id', type=int)
    op_type = request.args.get('type')
    query = RentalUnit.query.filter_by(occupancy_status='VACANT')

    if op_type:
        query = query.filter(RentalUnit.operational_type == op_type.strip().upper())

    if org_code:
        target_org = Organization.query.filter(
            or_(func.upper(Organization.org_code) == org_code.strip().upper(), Organization.slug == org_code.strip().lower())
        ).first()
        if target_org:
            query = query.join(Property).filter(Property.organization_id == target_org.id)

    if property_id:
        query = query.filter_by(property_id=property_id)

    units = query.order_by(RentalUnit.rent_amount_cents.asc()).all()
    currency = PersonalizationService.get_setting('currency', 'KES')

    result = []
    for u in units:
        result.append({
            'id': u.id,
            'unit_number': u.unit_number,
            'operational_type': u.operational_type,
            'daily_rate': float(from_cents(u.daily_rate_cents)) if u.daily_rate_cents else 0.0,
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
            'image_url': u.image_url,
            'youtube_url': u.youtube_url,
            'youtube_embed_url': u.youtube_embed_url,
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

    unit = db.session.get(RentalUnit, unit_id)
    if not unit:
        from flask import abort
        abort(404)
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

    unit = db.session.get(RentalUnit, unit_id)
    if not unit:
        from flask import abort
        abort(404)
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
            phone=phone,
            organization_id=org.id
        )
        db.session.add(guest)
        db.session.flush()
    elif not guest.organization_id:
        guest.organization_id = org.id

    res_code = f"RES-{org.business_code}-{int(datetime.utcnow().timestamp()) % 100000}"

    reservation = HospitalityReservation(
        organization_id=org.id,
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
    db.session.flush()

    # Dispatch multi-channel notifications (SMS, Email, WhatsApp, In-App) to Manager/Staff
    try:
        from app.services.notification_service import NotificationService
        NotificationService.notify_airbnb_booking(reservation)
    except Exception:
        pass

    db.session.commit()

    flash(
        f"Thank you, {guest_name}! Your reservation request for Room {unit.unit_number} has been registered (Code: {res_code}). "
        f"Our hospitality desk at {org.name} will contact you on {phone} with check-in instructions.",
        'success'
    )
    return redirect(url_for('public.tenant_site', slug=slug))

