from app.extensions import db
from app.models.property import Property, Building, Floor, RentalUnit
from app.utils.currency import to_cents
from app.services.audit_service import AuditService

class PropertyService:
    @staticmethod
    def get_properties(search=None, property_type=None, landlord_id=None):
        query = Property.query
        if landlord_id:
            query = query.filter(Property.landlord_id == landlord_id)
        if property_type:
            query = query.filter(Property.property_type == property_type)
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (Property.name.ilike(search_term)) |
                (Property.ref_number.ilike(search_term)) |
                (Property.location.ilike(search_term))
            )
        return query.order_by(Property.created_at.desc()).all()

    @staticmethod
    def create_property(landlord_id, name, ref_number, property_type, location, description=None, total_floors=1, image_url=None):
        prop = Property(
            landlord_id=landlord_id,
            name=name,
            ref_number=ref_number,
            property_type=property_type,
            location=location,
            description=description,
            total_floors=total_floors,
            image_url=image_url,
            management_status='ACTIVE'
        )
        db.session.add(prop)
        db.session.commit()
        AuditService.log('CREATE', 'Property', prop.id, new_values={'name': name, 'ref': ref_number})
        return prop

    @staticmethod
    def add_building(property_id, name, code=None, total_floors=1, description=None):
        bld = Building(
            property_id=property_id,
            name=name,
            code=code or name[:4].upper(),
            total_floors=total_floors,
            description=description
        )
        db.session.add(bld)
        db.session.commit()
        AuditService.log('CREATE', 'Building', bld.id, new_values={'property_id': property_id, 'name': name})
        return bld

    @staticmethod
    def add_floor(building_id, floor_number, floor_name):
        flr = Floor(
            building_id=building_id,
            floor_number=floor_number,
            floor_name=floor_name
        )
        db.session.add(flr)
        db.session.commit()
        return flr

    @staticmethod
    def create_unit(property_id, unit_number, unit_type, rent_amount, deposit_amount, building_id=None, floor_id=None, bedrooms=1, bathrooms=1, amenities=None, description=None):
        unit = RentalUnit(
            property_id=property_id,
            building_id=building_id,
            floor_id=floor_id,
            unit_number=unit_number.strip().upper(),
            unit_type=unit_type,
            rent_amount_cents=to_cents(rent_amount),
            deposit_amount_cents=to_cents(deposit_amount),
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            amenities=amenities,
            description=description,
            occupancy_status='VACANT'
        )
        db.session.add(unit)
        db.session.commit()
        AuditService.log('CREATE', 'RentalUnit', unit.id, new_values={'unit_number': unit.unit_number, 'rent': unit.rent_amount_cents})
        return unit

    @staticmethod
    def update_unit_status(unit_id, new_status, reason=None):
        unit = db.session.get(RentalUnit, unit_id)
        if unit:
            old_status = unit.occupancy_status
            unit.occupancy_status = new_status
            db.session.commit()
            AuditService.log('UPDATE_STATUS', 'RentalUnit', unit.id, old_values={'status': old_status}, new_values={'status': new_status, 'reason': reason})
            return unit
        return None

    @staticmethod
    def get_property_occupancy_stats(property_id=None):
        query = RentalUnit.query
        if property_id:
            query = query.filter_by(property_id=property_id)
        
        all_units = query.all()
        total = len(all_units)
        vacant = sum(1 for u in all_units if u.occupancy_status == 'VACANT')
        occupied = sum(1 for u in all_units if u.occupancy_status == 'OCCUPIED')
        reserved = sum(1 for u in all_units if u.occupancy_status == 'RESERVED')
        maintenance = sum(1 for u in all_units if u.occupancy_status == 'MAINTENANCE')
        
        rate = round((occupied / total * 100), 1) if total > 0 else 0
        return {
            'total': total,
            'vacant': vacant,
            'occupied': occupied,
            'reserved': reserved,
            'maintenance': maintenance,
            'rate': rate
        }

