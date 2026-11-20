import os
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.models.property import Property, RentalUnit
from app.models.user import Landlord, User, LandlordUser
from app.models.organization import Organization
from app.models.lead import ExternalPropertyListing, HouseSeekerLead
from app.services.property_service import PropertyService
from app.utils.decorators import permission_required
from app.utils.currency import to_cents

properties_bp = Blueprint('properties', __name__, url_prefix='/properties')

PROPERTY_TYPES = [
    ('APARTMENT', 'Apartments'),
    ('RESIDENTIAL', 'Residential House / Villa'),
    ('BEDSITTER', 'Bedsitter / Studio'),
    ('SINGLE_ROOM', 'Single Room'),
    ('COMMERCIAL', 'Commercial Building'),
    ('SHOP', 'Retail Shop'),
    ('OFFICE', 'Commercial Office'),
    ('WAREHOUSE', 'Warehouse / Godown'),
    ('MIXED_USE', 'Mixed-Use Building')
]

UNIT_TYPES = [
    ('BEDSITTER', 'Bedsitter'),
    ('SINGLE_ROOM', 'Single Room'),
    ('1_BEDROOM', '1 Bedroom'),
    ('2_BEDROOM', '2 Bedroom'),
    ('3_BEDROOM', '3 Bedroom'),
    ('4_BEDROOM', '4+ Bedroom'),
    ('COMMERCIAL_SHOP', 'Retail Shop'),
    ('OFFICE_SPACE', 'Office Suite'),
    ('WAREHOUSE', 'Warehouse Space')
]

@properties_bp.route('/')
@login_required
@permission_required('properties.view')
def index():
    search = request.args.get('search', '').strip()
    property_type = request.args.get('type')
    landlord_id = request.args.get('landlord_id', type=int)

    org_id = getattr(current_user, 'organization_id', None) if not current_user.is_superadmin() else None

    # Scoping for landlord role
    if not current_user.is_superadmin() and current_user.landlords:
        assigned_ids = [l.id for l in current_user.landlords]
        if landlord_id and landlord_id not in assigned_ids:
            landlord_id = assigned_ids[0]
        elif not landlord_id and len(assigned_ids) == 1:
            landlord_id = assigned_ids[0]

    properties = PropertyService.get_properties(search, property_type, landlord_id, organization_id=org_id)
    if org_id:
        prop_landlord_ids = [row[0] for row in db.session.query(Property.landlord_id).filter(Property.organization_id == org_id).distinct().all()]
        user_landlord_ids = [row[0] for row in db.session.query(LandlordUser.landlord_id).join(User, User.id == LandlordUser.user_id).filter(User.organization_id == org_id).distinct().all()]
        direct_ids = [l.id for l in current_user.landlords] if (hasattr(current_user, 'landlords') and current_user.landlords) else []
        all_ids = list(set(prop_landlord_ids + user_landlord_ids + direct_ids))
        if all_ids:
            landlords = Landlord.query.filter(Landlord.id.in_(all_ids), Landlord.is_active == True).order_by(Landlord.name.asc()).all()
        else:
            org = db.session.get(Organization, org_id)
            if org:
                default_ll = Landlord.query.filter_by(name=org.name).first()
                if not default_ll:
                    default_ll = Landlord(
                        name=org.name,
                        contact_person=getattr(current_user, 'full_name', org.name),
                        email=getattr(current_user, 'email', None) or f"info@{org.slug}.co.ke",
                        phone=getattr(org, 'contact_phone', None) or getattr(current_user, 'phone', None) or '+254700000000',
                        is_active=True
                    )
                    db.session.add(default_ll)
                    db.session.commit()
                if hasattr(current_user, 'landlords') and default_ll not in current_user.landlords:
                    current_user.landlords.append(default_ll)
                    db.session.commit()
                landlords = [default_ll]
            else:
                landlords = Landlord.query.filter_by(is_active=True).all()
    else:
        landlords = Landlord.query.filter_by(is_active=True).order_by(Landlord.name.asc()).all()
    stats = PropertyService.get_property_occupancy_stats(organization_id=org_id)

    return render_template(
        'properties/index.html',
        properties=properties,
        landlords=landlords,
        property_types=PROPERTY_TYPES,
        stats=stats,
        search=search,
        selected_type=property_type,
        selected_landlord=landlord_id
    )

@properties_bp.route('/create', methods=['POST'])
@login_required
@permission_required('properties.manage')
def create_property():
    name = request.form.get('name', '').strip()
    ref_number = request.form.get('ref_number', '').strip().upper()
    property_type = request.form.get('property_type', 'APARTMENT')
    location = request.form.get('location', '').strip()
    landlord_id = request.form.get('landlord_id', type=int)
    total_floors = request.form.get('total_floors', 1, type=int)
    description = request.form.get('description', '').strip()

    if not name or not location or not landlord_id:
        flash('Property name, location, and landlord are mandatory.', 'danger')
        return redirect(url_for('properties.index'))

    # Auto-generate reference number if not provided
    if not ref_number:
        count = Property.query.count() + 1
        ref_number = f"PROP-{count:03d}"

    if Property.query.filter_by(ref_number=ref_number).first():
        flash(f"A property with reference '{ref_number}' already exists.", 'danger')
        return redirect(url_for('properties.index'))

    user_org_id = getattr(current_user, 'organization_id', None)
    prop = PropertyService.create_property(
        landlord_id=landlord_id,
        name=name,
        ref_number=ref_number,
        property_type=property_type,
        location=location,
        description=description,
        total_floors=total_floors,
        organization_id=user_org_id
    )

    # Automatically create Main Building and Ground Floor
    main_bld = PropertyService.add_building(prop.id, name=f"{name} Main", code="MAIN")
    PropertyService.add_floor(main_bld.id, floor_number=0, floor_name="Ground Floor")

    flash(f"Property '{name}' registered successfully.", 'success')
    return redirect(url_for('properties.detail', property_id=prop.id))

@properties_bp.route('/landlords/create', methods=['POST'])
@login_required
@permission_required('properties.manage')
def create_landlord():
    """Quick register a new Landlord / Property Owner."""
    name = request.form.get('name', '').strip()
    contact_person = request.form.get('contact_person', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    tax_pin = request.form.get('tax_pin', '').strip()
    address = request.form.get('address', '').strip()

    if not name or not phone:
        flash('Landlord / Owner name and phone number are required.', 'danger')
        return redirect(request.referrer or url_for('properties.index'))

    ll = Landlord(
        name=name,
        contact_person=contact_person if contact_person else None,
        phone=phone,
        email=email if email else None,
        tax_pin=tax_pin if tax_pin else None,
        address=address if address else None,
        is_active=True
    )
    db.session.add(ll)
    db.session.flush()

    if hasattr(current_user, 'landlords') and ll not in current_user.landlords:
        current_user.landlords.append(ll)

    db.session.commit()
    flash(f"Landlord / Property Owner '{ll.name}' registered successfully. You can now assign them to properties.", 'success')
    return redirect(request.referrer or url_for('properties.index'))

@properties_bp.route('/<int:property_id>')
@login_required
@permission_required('properties.view')
def detail(property_id):
    prop = Property.query.get_or_404(property_id)
    org_id = getattr(current_user, 'organization_id', None) if not current_user.is_superadmin() else None
    if org_id and prop.organization_id and prop.organization_id != org_id:
        from flask import abort
        abort(404)

    buildings = prop.buildings.all()
    units = prop.rental_units.all()
    stats = PropertyService.get_property_occupancy_stats(property_id=prop.id)
    landlords = Landlord.query.filter_by(is_active=True).all()

    from app.services.tenant_service import TenantService
    occupants_data = []
    for u in units:
        tenant = u.current_tenant
        active_lease = u.leases.filter_by(status='ACTIVE').first() if hasattr(u, 'leases') else None
        summary = TenantService.get_tenant_financial_summary(tenant.id) if tenant else None
        days_in_unit = (datetime.utcnow().date() - active_lease.start_date).days if (active_lease and active_lease.start_date) else None
        occupants_data.append({
            'unit': u,
            'tenant': tenant,
            'active_lease': active_lease,
            'summary': summary,
            'days_in_unit': days_in_unit
        })

    return render_template(
        'properties/detail.html',
        property=prop,
        buildings=buildings,
        units=units,
        stats=stats,
        landlords=landlords,
        property_types=PROPERTY_TYPES,
        unit_types=UNIT_TYPES,
        occupants_data=occupants_data
    )

@properties_bp.route('/<int:property_id>/edit', methods=['POST'])
@login_required
@permission_required('properties.manage')
def edit_property(property_id):
    prop = Property.query.get_or_404(property_id)
    if request.form.get('name'):
        prop.name = request.form.get('name').strip()
    if request.form.get('property_type'):
        prop.property_type = request.form.get('property_type')
    if request.form.get('location'):
        prop.location = request.form.get('location').strip()
    if request.form.get('description'):
        prop.description = request.form.get('description').strip()
    total_floors = request.form.get('total_floors', type=int)
    if total_floors:
        prop.total_floors = total_floors
    landlord_id = request.form.get('landlord_id', type=int)
    if landlord_id:
        prop.landlord_id = landlord_id

    # Handle image URL or direct file upload
    image_url_val = request.form.get('image_url', '').strip()
    if image_url_val:
        prop.image_url = image_url_val

    image_file = request.files.get('image_file')
    if image_file and image_file.filename:
        filename = secure_filename(image_file.filename)
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext in {'png', 'jpg', 'jpeg', 'webp'}:
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'properties')
            os.makedirs(upload_dir, exist_ok=True)
            prop_image_name = f"prop_{prop.id}_{int(datetime.utcnow().timestamp())}.{ext}"
            image_file.save(os.path.join(upload_dir, prop_image_name))
            prop.image_url = f"/static/uploads/properties/{prop_image_name}"

    db.session.commit()
    flash(f"Property '{prop.name}' profile and photo updated successfully.", 'success')
    return redirect(url_for('properties.detail', property_id=prop.id))


@properties_bp.route('/<int:property_id>/buildings/create', methods=['POST'])
@login_required
@permission_required('properties.manage')
def create_building(property_id):
    name = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip().upper()
    total_floors = request.form.get('total_floors', 1, type=int)
    description = request.form.get('description', '').strip()

    if not name:
        flash('Building name is required.', 'danger')
        return redirect(url_for('properties.detail', property_id=property_id))

    bld = PropertyService.add_building(property_id, name, code, total_floors, description)
    # Automatically add Ground floor
    PropertyService.add_floor(bld.id, floor_number=0, floor_name="Ground Floor")

    flash(f"Building '{name}' added to property.", 'success')
    return redirect(url_for('properties.detail', property_id=property_id))

@properties_bp.route('/<int:property_id>/floors/create', methods=['POST'])
@login_required
@permission_required('properties.manage')
def create_floor(property_id):
    building_id = request.form.get('building_id', type=int)
    floor_number = request.form.get('floor_number', type=int)
    floor_name = request.form.get('floor_name', '').strip()

    if not building_id or floor_number is None or not floor_name:
        flash('Building, floor number, and name are required.', 'danger')
        return redirect(url_for('properties.detail', property_id=property_id))

    PropertyService.add_floor(building_id, floor_number, floor_name)
    flash(f"Floor '{floor_name}' registered.", 'success')
    return redirect(url_for('properties.detail', property_id=property_id))

@properties_bp.route('/<int:property_id>/units/create', methods=['POST'])
@login_required
@permission_required('properties.manage')
def create_unit(property_id):
    unit_number = request.form.get('unit_number', '').strip().upper()
    unit_type = request.form.get('unit_type', 'APARTMENT')
    rent_amount = request.form.get('rent_amount', 0, type=float)
    deposit_amount = request.form.get('deposit_amount', 0, type=float)
    building_id = request.form.get('building_id', type=int)
    floor_id = request.form.get('floor_id', type=int)
    bedrooms = request.form.get('bedrooms', 1, type=int)
    bathrooms = request.form.get('bathrooms', 1, type=int)
    amenities = request.form.get('amenities', '').strip()
    description = request.form.get('description', '').strip()

    if not unit_number or rent_amount <= 0:
        flash('Unit number and a valid monthly rent are required.', 'danger')
        return redirect(url_for('properties.detail', property_id=property_id))

    if RentalUnit.query.filter_by(property_id=property_id, unit_number=unit_number).first():
        flash(f"A unit with number '{unit_number}' already exists in this property.", 'danger')
        return redirect(url_for('properties.detail', property_id=property_id))

    unit = PropertyService.create_unit(
        property_id=property_id,
        unit_number=unit_number,
        unit_type=unit_type,
        rent_amount=rent_amount,
        deposit_amount=deposit_amount,
        building_id=building_id,
        floor_id=floor_id,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        amenities=amenities,
        description=description
    )

    flash(f"Rental unit '{unit.unit_number}' created successfully.", 'success')
    return redirect(url_for('properties.detail', property_id=property_id))

@properties_bp.route('/units/<int:unit_id>/status', methods=['POST'])
@login_required
@permission_required('properties.manage')
def update_unit_status(unit_id):
    new_status = request.form.get('status')
    reason = request.form.get('reason')
    unit = PropertyService.update_unit_status(unit_id, new_status, reason)
    if unit:
        flash(f"Unit {unit.unit_number} status updated to {new_status}.", 'info')
        return redirect(url_for('properties.detail', property_id=unit.property_id))
    flash('Unit not found.', 'danger')
    return redirect(url_for('properties.index'))

@properties_bp.route('/units/<int:unit_id>/edit', methods=['POST'])
@login_required
@permission_required('properties.manage')
def edit_unit(unit_id):
    unit = RentalUnit.query.get_or_404(unit_id)
    unit_number = request.form.get('unit_number', '').strip().upper()
    unit_type = request.form.get('unit_type', unit.unit_type)
    rent_amount = request.form.get('rent_amount', type=float)
    deposit_amount = request.form.get('deposit_amount', type=float)
    bedrooms = request.form.get('bedrooms', unit.bedrooms, type=int)
    bathrooms = request.form.get('bathrooms', unit.bathrooms, type=int)
    amenities = request.form.get('amenities', '').strip()
    description = request.form.get('description', '').strip()
    status = request.form.get('occupancy_status', unit.occupancy_status)

    if not unit_number or rent_amount is None or rent_amount <= 0:
        flash('Unit number and valid rent amount are required.', 'danger')
        return redirect(url_for('properties.detail', property_id=unit.property_id))

    # Check unique unit_number within same property
    existing = RentalUnit.query.filter(
        RentalUnit.property_id == unit.property_id,
        RentalUnit.unit_number == unit_number,
        RentalUnit.id != unit.id
    ).first()
    if existing:
        flash(f"A unit with number '{unit_number}' already exists in this property.", 'danger')
        return redirect(url_for('properties.detail', property_id=unit.property_id))

    unit.unit_number = unit_number
    unit.unit_type = unit_type
    unit.rent_amount_cents = to_cents(rent_amount)
    if deposit_amount is not None:
        unit.deposit_amount_cents = to_cents(deposit_amount)
    unit.bedrooms = bedrooms
    unit.bathrooms = bathrooms
    unit.amenities = amenities
    unit.description = description
    if status in ['VACANT', 'OCCUPIED', 'RESERVED', 'MAINTENANCE', 'INACTIVE']:
        unit.occupancy_status = status

    # Handle Unit / Airbnb Room Photo upload or URL
    image_url_val = request.form.get('image_url', '').strip()
    if image_url_val:
        unit.image_url = image_url_val

    image_file = request.files.get('image_file')
    if image_file and image_file.filename:
        filename = secure_filename(image_file.filename)
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext in {'png', 'jpg', 'jpeg', 'webp'}:
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'units')
            os.makedirs(upload_dir, exist_ok=True)
            unit_image_name = f"unit_{unit.id}_{int(datetime.utcnow().timestamp())}.{ext}"
            image_file.save(os.path.join(upload_dir, unit_image_name))
            unit.image_url = f"/static/uploads/units/{unit_image_name}"

    db.session.commit()
    flash(f"Unit '{unit.unit_number}' details updated successfully.", 'success')
    return redirect(url_for('properties.detail', property_id=unit.property_id))

@properties_bp.route('/units/<int:unit_id>/delete', methods=['POST'])
@login_required
@permission_required('properties.manage')
def delete_unit(unit_id):
    unit = RentalUnit.query.get_or_404(unit_id)
    prop_id = unit.property_id

    if unit.occupancy_status == 'OCCUPIED' or unit.current_tenant_id:
        flash(f"Cannot delete unit '{unit.unit_number}' because it is currently occupied by an active tenant.", 'danger')
        return redirect(url_for('properties.detail', property_id=prop_id))

    active_leases = unit.leases.filter_by(status='ACTIVE').count()
    if active_leases > 0:
        flash(f"Cannot delete unit '{unit.unit_number}' with active lease contracts. Terminate or transfer first.", 'danger')
        return redirect(url_for('properties.detail', property_id=prop_id))

    unit_name = unit.unit_number
    db.session.delete(unit)
    db.session.commit()
    flash(f"Rental unit '{unit_name}' deleted successfully.", 'success')
    return redirect(url_for('properties.detail', property_id=prop_id))

@properties_bp.route('/marketplace')
@login_required
@permission_required('properties.view')
def marketplace():
    """
    Marketplace & External Listings Hub:
    Enables System Admin to manage and publish third-party / external landlord vacant apartments,
    and monitor incoming House Seeker waitlist leads and inquiries.
    """
    status_filter = request.args.get('status', 'ALL')
    search = request.args.get('search', '').strip()

    org_id = getattr(current_user, 'organization_id', None) if not current_user.is_superadmin() else None

    listing_query = ExternalPropertyListing.query
    if org_id:
        listing_query = listing_query.filter(ExternalPropertyListing.organization_id == org_id)

    if status_filter != 'ALL':
        listing_query = listing_query.filter_by(status=status_filter)
    if search:
        term = f"%{search}%"
        listing_query = listing_query.filter(
            (ExternalPropertyListing.property_title.ilike(term)) |
            (ExternalPropertyListing.location.ilike(term)) |
            (ExternalPropertyListing.owner_name.ilike(term)) |
            (ExternalPropertyListing.owner_phone.ilike(term))
        )

    listings = listing_query.order_by(ExternalPropertyListing.created_at.desc()).all()

    leads_query = HouseSeekerLead.query
    if org_id:
        leads_query = leads_query.filter(HouseSeekerLead.organization_id == org_id)
    leads = leads_query.order_by(HouseSeekerLead.created_at.desc()).limit(50).all()

    pub_query = ExternalPropertyListing.query.filter_by(status='PUBLISHED')
    pend_query = ExternalPropertyListing.query.filter_by(status='PENDING')
    lead_count_query = HouseSeekerLead.query
    if org_id:
        pub_query = pub_query.filter(ExternalPropertyListing.organization_id == org_id)
        pend_query = pend_query.filter(ExternalPropertyListing.organization_id == org_id)
        lead_count_query = lead_count_query.filter(HouseSeekerLead.organization_id == org_id)

    total_published = pub_query.count()
    total_pending = pend_query.count()
    total_leads = lead_count_query.count()

    return render_template(
        'properties/marketplace.html',
        listings=listings,
        leads=leads,
        total_published=total_published,
        total_pending=total_pending,
        total_leads=total_leads,
        status_filter=status_filter,
        search=search,
        unit_types=UNIT_TYPES
    )

@properties_bp.route('/external-listings/create', methods=['POST'])
@login_required
@permission_required('properties.manage')
def create_external_listing():
    owner_name = request.form.get('owner_name', '').strip()
    owner_phone = request.form.get('owner_phone', '').strip()
    owner_email = request.form.get('owner_email', '').strip()
    property_title = request.form.get('property_title', '').strip()
    location = request.form.get('location', '').strip()
    unit_type = request.form.get('unit_type', '2_BEDROOM')
    rent_raw = request.form.get('monthly_rent', 0, type=float)
    deposit_raw = request.form.get('deposit', 0, type=float)
    bedrooms = request.form.get('bedrooms', 1, type=int)
    bathrooms = request.form.get('bathrooms', 1, type=int)
    features = request.form.get('features', '').strip()
    description = request.form.get('description', '').strip()
    status = request.form.get('status', 'PUBLISHED')

    if not owner_name or not owner_phone or not property_title or not location or rent_raw <= 0:
        flash('Owner Name, Telephone, Property Title, Location, and Monthly Rent are required.', 'danger')
        return redirect(url_for('properties.marketplace'))

    org_id = getattr(current_user, 'organization_id', None) if not current_user.is_superadmin() else None

    listing = ExternalPropertyListing(
        organization_id=org_id,
        owner_name=owner_name,
        owner_phone=owner_phone,
        owner_email=owner_email,
        property_title=property_title,
        location=location,
        property_type='APARTMENT',
        unit_type=unit_type,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        monthly_rent_cents=to_cents(rent_raw),
        deposit_cents=to_cents(deposit_raw),
        features=features,
        description=description,
        status=status
    )
    db.session.add(listing)
    db.session.commit()
    flash(f"External apartment '{property_title}' published to public vacancies website successfully!", 'success')
    return redirect(url_for('properties.marketplace'))

@properties_bp.route('/external-listings/<int:listing_id>/toggle-status', methods=['POST'])
@login_required
@permission_required('properties.manage')
def toggle_external_listing_status(listing_id):
    listing = db.session.get(ExternalPropertyListing, listing_id)
    if not listing:
        flash('Listing not found.', 'danger')
        return redirect(request.form.get('next') or request.referrer or url_for('properties.marketplace'))

    # Security check: multi-tenant isolation
    org_id = getattr(current_user, 'organization_id', None) if not current_user.is_superadmin() else None
    if org_id and listing.organization_id and listing.organization_id != org_id:
        from flask import abort
        abort(403)

    new_status = request.form.get('status')
    if new_status in ['PUBLISHED', 'PENDING', 'RENTED', 'ARCHIVED']:
        listing.status = new_status
        db.session.commit()
        flash(f"Listing '{listing.property_title}' status updated to {new_status}.", 'info')
    return redirect(request.form.get('next') or request.referrer or url_for('properties.marketplace'))

@properties_bp.route('/external-listings/<int:listing_id>/delete', methods=['POST'])
@login_required
@permission_required('properties.manage')
def delete_external_listing(listing_id):
    listing = db.session.get(ExternalPropertyListing, listing_id)
    if listing:
        org_id = getattr(current_user, 'organization_id', None) if not current_user.is_superadmin() else None
        if org_id and listing.organization_id and listing.organization_id != org_id:
            from flask import abort
            abort(403)
        title = listing.property_title
        db.session.delete(listing)
        db.session.commit()
        flash(f"Listing '{title}' deleted successfully.", 'success')
    return redirect(request.form.get('next') or request.referrer or url_for('properties.marketplace'))

@properties_bp.route('/external-listings/<int:listing_id>/allocate', methods=['POST'])
@login_required
@permission_required('properties.manage')
def allocate_external_listing(listing_id):
    """
    Allocate / Link House to Tenant:
    Angaza staff links a prospective tenant/applicant with the landlord's vacant house.
    """
    listing = db.session.get(ExternalPropertyListing, listing_id)
    if not listing:
        flash('Listing not found.', 'danger')
        return redirect(url_for('properties.marketplace'))

    tenant_name = request.form.get('tenant_name', '').strip()
    tenant_phone = request.form.get('tenant_phone', '').strip()
    notes = request.form.get('allocation_notes', '').strip()
    lead_id = request.form.get('lead_id', type=int)

    if not tenant_name or not tenant_phone:
        flash('Applicant / Tenant Name and Phone Number are required to allocate.', 'danger')
        return redirect(url_for('properties.marketplace'))

    listing.allocated_tenant_name = tenant_name
    listing.allocated_tenant_phone = tenant_phone
    listing.allocated_at = datetime.utcnow()
    listing.allocation_notes = notes
    listing.status = 'ALLOCATED'

    if lead_id:
        lead = db.session.get(HouseSeekerLead, lead_id)
        if lead:
            lead.status = 'MATCHED'
            lead.notes = f"{lead.notes or ''} [Allocated to partner listing: {listing.property_title}]".strip()

    db.session.commit()
    flash(f"Successfully linked & allocated '{listing.property_title}' to tenant {tenant_name} ({tenant_phone})! Landlord: {listing.owner_name} ({listing.owner_phone}).", 'success')
    return redirect(url_for('properties.marketplace'))

@properties_bp.route('/external-listings/<int:listing_id>/onboard-managed', methods=['POST'])
@login_required
@permission_required('properties.manage')
def onboard_external_to_managed(listing_id):
    """
    Convert an external listing into a full internal managed property in the core system.
    Creates Landlord, Property, Building, Floor, and RentalUnit records.
    """
    listing = db.session.get(ExternalPropertyListing, listing_id)
    if not listing:
        flash('Listing not found.', 'danger')
        return redirect(url_for('properties.marketplace'))

    # 1. Find or create Landlord
    landlord = Landlord.query.filter_by(phone=listing.owner_phone).first()
    if not landlord:
        landlord = Landlord(
            name=listing.owner_name,
            phone=listing.owner_phone,
            email=listing.owner_email,
            is_active=True
        )
        db.session.add(landlord)
        db.session.flush()

    # 2. Create Property
    prop_count = Property.query.count() + 1
    ref = f"PROP-EXT-{prop_count:03d}"
    org_id = listing.organization_id or (getattr(current_user, 'organization_id', None) if not current_user.is_superadmin() else None)
    prop = PropertyService.create_property(
        landlord_id=landlord.id,
        name=listing.property_title,
        ref_number=ref,
        property_type=listing.property_type or 'APARTMENT',
        location=listing.location,
        description=listing.description,
        total_floors=1,
        organization_id=org_id
    )

    # 3. Create Main Building & Floor
    bld = PropertyService.add_building(prop.id, name=f"{listing.property_title} Block", code="MAIN")
    PropertyService.add_floor(bld.id, floor_number=0, floor_name="Ground Floor")

    # 4. Create Rental Unit
    PropertyService.create_unit(
        property_id=prop.id,
        unit_number="UNIT-01",
        unit_type=listing.unit_type or '2_BEDROOM',
        rent_amount=listing.monthly_rent_cents / 100,
        deposit_amount=listing.deposit_cents / 100,
        building_id=bld.id,
        bedrooms=listing.bedrooms or 1,
        bathrooms=listing.bathrooms or 1,
        amenities=listing.features,
        description=listing.description
    )

    # 5. Mark listing as onboarded/rented
    listing.status = 'RENTED'
    db.session.commit()

    flash(f"Property '{listing.property_title}' successfully onboarded into core database for Landlord {landlord.name}! You can now manage leases, billing, and occupancy directly.", 'success')
    return redirect(url_for('properties.detail', property_id=prop.id))

@properties_bp.route('/occupancy')
@login_required
@permission_required('properties.view')
def occupancy_grid():
    """
    Visual Property Occupancy Interface:
    Allows property managers and caretakers to see all rental units visually distinguished
    by status (Vacant, Occupied, Reserved, Maintenance) with live search and multi-criteria filters.
    """
    from app.utils.decorators import multi_tenant_scoped
    status_filter = request.args.get('status')
    property_filter = request.args.get('property_id', type=int)
    search = request.args.get('search', '').strip()

    org_id = getattr(current_user, 'organization_id', None) if not current_user.is_superadmin() else None

    query = multi_tenant_scoped(RentalUnit.query, RentalUnit)
    if property_filter:
        query = query.filter(RentalUnit.property_id == property_filter)
    if status_filter:
        query = query.filter(RentalUnit.occupancy_status == status_filter)
    if search:
        query = query.filter(RentalUnit.unit_number.ilike(f"%{search}%"))

    units = query.order_by(RentalUnit.unit_number.asc()).all()
    properties = multi_tenant_scoped(Property.query, Property).all()
    stats = PropertyService.get_property_occupancy_stats(property_filter, organization_id=org_id)

    return render_template(
        'properties/occupancy.html',
        units=units,
        properties=properties,
        stats=stats,
        selected_status=status_filter,
        selected_property=property_filter,
        search=search
    )

@properties_bp.route('/export-vacant-excel')
@login_required
@permission_required('properties.view')
def export_vacant_excel():
    property_id = request.args.get('property_id', type=int)
    from app.services.report_service import ReportService
    from flask import Response
    from datetime import datetime
    excel_data = ReportService.export_vacant_houses_excel(property_id=property_id)
    filename = f"Vacant_Houses_Report_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.xlsx"
    return Response(
        excel_data,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@properties_bp.route('/<int:property_id>/occupancy/pdf')
@login_required
@permission_required('properties.view')
def download_occupancy_pdf(property_id):
    from io import BytesIO
    from flask import send_file, abort
    from app.models.property import Property
    from app.utils.pdf_generator import generate_property_occupancy_report_pdf
    prop = db.session.get(Property, property_id)
    if not prop:
        abort(404)
    if not current_user.is_superadmin() and prop.organization_id != current_user.organization_id:
        abort(404)
    pdf_bytes = generate_property_occupancy_report_pdf(prop)
    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Occupancy_Report_{prop.ref_number}.pdf"
    )


