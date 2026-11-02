from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models.property import Property, RentalUnit
from app.models.user import Landlord
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

    # Scoping for landlord role
    if not current_user.is_superadmin() and current_user.landlords:
        assigned_ids = [l.id for l in current_user.landlords]
        if landlord_id and landlord_id not in assigned_ids:
            landlord_id = assigned_ids[0]
        elif not landlord_id and len(assigned_ids) == 1:
            landlord_id = assigned_ids[0]

    properties = PropertyService.get_properties(search, property_type, landlord_id)
    landlords = Landlord.query.filter_by(is_active=True).all()
    stats = PropertyService.get_property_occupancy_stats()

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

    prop = PropertyService.create_property(
        landlord_id=landlord_id,
        name=name,
        ref_number=ref_number,
        property_type=property_type,
        location=location,
        description=description,
        total_floors=total_floors
    )

    # Automatically create Main Building and Ground Floor
    main_bld = PropertyService.add_building(prop.id, name=f"{name} Main", code="MAIN")
    PropertyService.add_floor(main_bld.id, floor_number=0, floor_name="Ground Floor")

    flash(f"Property '{name}' registered successfully.", 'success')
    return redirect(url_for('properties.detail', property_id=prop.id))

@properties_bp.route('/<int:property_id>')
@login_required
@permission_required('properties.view')
def detail(property_id):
    prop = Property.query.get_or_404(property_id)
    buildings = prop.buildings.all()
    units = prop.rental_units.all()
    stats = PropertyService.get_property_occupancy_stats(property_id=prop.id)
    landlords = Landlord.query.filter_by(is_active=True).all()

    return render_template(
        'properties/detail.html',
        property=prop,
        buildings=buildings,
        units=units,
        stats=stats,
        landlords=landlords,
        property_types=PROPERTY_TYPES,
        unit_types=UNIT_TYPES
    )

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
@permission_required('units.manage')
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
@permission_required('units.manage')
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
@permission_required('units.manage')
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

    db.session.commit()
    flash(f"Unit '{unit.unit_number}' details updated successfully.", 'success')
    return redirect(url_for('properties.detail', property_id=unit.property_id))

@properties_bp.route('/units/<int:unit_id>/delete', methods=['POST'])
@login_required
@permission_required('units.manage')
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

    listing_query = ExternalPropertyListing.query
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
    leads = HouseSeekerLead.query.order_by(HouseSeekerLead.created_at.desc()).limit(50).all()

    total_published = ExternalPropertyListing.query.filter_by(status='PUBLISHED').count()
    total_pending = ExternalPropertyListing.query.filter_by(status='PENDING').count()
    total_leads = HouseSeekerLead.query.count()

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

    listing = ExternalPropertyListing(
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
        return redirect(url_for('properties.marketplace'))

    new_status = request.form.get('status')
    if new_status in ['PUBLISHED', 'PENDING', 'RENTED', 'ARCHIVED']:
        listing.status = new_status
        db.session.commit()
        flash(f"Listing '{listing.property_title}' status updated to {new_status}.", 'info')
    return redirect(url_for('properties.marketplace'))

@properties_bp.route('/external-listings/<int:listing_id>/delete', methods=['POST'])
@login_required
@permission_required('properties.manage')
def delete_external_listing(listing_id):
    listing = db.session.get(ExternalPropertyListing, listing_id)
    if listing:
        title = listing.property_title
        db.session.delete(listing)
        db.session.commit()
        flash(f"Listing '{title}' deleted successfully.", 'success')
    return redirect(url_for('properties.marketplace'))

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
    prop = PropertyService.create_property(
        landlord_id=landlord.id,
        name=listing.property_title,
        ref_number=ref,
        property_type=listing.property_type or 'APARTMENT',
        location=listing.location,
        description=listing.description,
        total_floors=1
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
@permission_required('units.view')
def occupancy_grid():
    """
    Visual Property Occupancy Interface:
    Allows property managers and caretakers to see all rental units visually distinguished
    by status (Vacant, Occupied, Reserved, Maintenance) with live search and multi-criteria filters.
    """
    status_filter = request.args.get('status')
    property_filter = request.args.get('property_id', type=int)
    search = request.args.get('search', '').strip()

    query = RentalUnit.query
    if property_filter:
        query = query.filter(RentalUnit.property_id == property_filter)
    if status_filter:
        query = query.filter(RentalUnit.occupancy_status == status_filter)
    if search:
        query = query.filter(RentalUnit.unit_number.ilike(f"%{search}%"))

    units = query.order_by(RentalUnit.unit_number.asc()).all()
    properties = Property.query.all()
    stats = PropertyService.get_property_occupancy_stats(property_filter)

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
@permission_required('units.view')
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


