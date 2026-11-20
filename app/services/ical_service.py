"""
iCal Calendar Synchronization Service (RFC 5545)
================================================
Handles two-way synchronization between the Angaza short-stay/Airbnb platform
and external OTAs (Airbnb.com, Booking.com, VRBO, etc.).

1. Generates RFC 5545 .ics export feeds for any accommodation listing.
2. Imports external .ics feeds to automatically block calendar dates and prevent double bookings.
"""
import re
import requests
from datetime import datetime, date, timedelta
from app.extensions import db
from app.models.property import RentalUnit
from app.models.hospitality import HospitalityReservation, Guest


class ICalService:
    @staticmethod
    def generate_unit_ical(unit: RentalUnit) -> str:
        """
        Generates a valid RFC 5545 VCALENDAR feed containing all active and upcoming
        confirmed reservations for the specified unit.
        """
        unit.ensure_ical_token()
        db.session.commit()

        # Query confirmed reservations from 60 days ago onwards
        cutoff = date.today() - timedelta(days=60)
        reservations = HospitalityReservation.query.filter(
            HospitalityReservation.rental_unit_id == unit.id,
            HospitalityReservation.status.in_(['CONFIRMED', 'CHECKED_IN']),
            HospitalityReservation.check_out_date >= cutoff
        ).order_by(HospitalityReservation.check_in_date.asc()).all()

        prop_name = unit.property.name if unit.property else "Angaza Premises"
        cal_name = f"{unit.unit_number} - {prop_name}"

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Angaza Property Manager//Hospitality iCal 1.0//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            f"X-WR-CALNAME:{cal_name}",
            "X-WR-TIMEZONE:Africa/Nairobi"
        ]

        now_stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

        for res in reservations:
            guest_name = res.guest.full_name if res.guest else "Short-Stay Guest"
            # Format dates (DTEND in iCal is non-inclusive day of departure)
            dtstart = res.check_in_date.strftime("%Y%m%d")
            dtend = res.check_out_date.strftime("%Y%m%d")
            uid = f"{res.reservation_code}@angaza.co.ke"

            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART;VALUE=DATE:{dtstart}",
                f"DTEND;VALUE=DATE:{dtend}",
                f"SUMMARY:Reserved - {guest_name}",
                f"DESCRIPTION:Angaza Hospitality Reservation ({res.reservation_code})",
                "STATUS:CONFIRMED",
                "TRANSP:OPAQUE",
                "END:VEVENT"
            ])

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    @staticmethod
    def parse_ical_content(content: str) -> list:
        """
        Parses raw .ics text content and extracts VEVENT items with start/end dates and UIDs.
        """
        events = []
        vevent_pattern = re.compile(r"BEGIN:VEVENT(.*?)END:VEVENT", re.DOTALL | re.IGNORECASE)

        for match in vevent_pattern.finditer(content):
            event_block = match.group(1)

            uid_m = re.search(r"^UID:(.*?)$", event_block, re.MULTILINE | re.IGNORECASE)
            summary_m = re.search(r"^SUMMARY:(.*?)$", event_block, re.MULTILINE | re.IGNORECASE)

            # Support DTSTART with or without parameters (e.g. DTSTART;VALUE=DATE:20261125 or DTSTART:20261125T140000Z)
            dtstart_m = re.search(r"^DTSTART[^:]*:(.*?)$", event_block, re.MULTILINE | re.IGNORECASE)
            dtend_m = re.search(r"^DTEND[^:]*:(.*?)$", event_block, re.MULTILINE | re.IGNORECASE)

            if not dtstart_m or not dtend_m:
                continue

            raw_start = dtstart_m.group(1).strip()
            raw_end = dtend_m.group(1).strip()
            uid = uid_m.group(1).strip() if uid_m else f"EXT-{datetime.utcnow().timestamp()}"
            summary = summary_m.group(1).strip() if summary_m else "External Reservation"

            # Parse date strings (extract first 8 digits YYYYMMDD)
            s_digits = re.search(r"(\d{8})", raw_start)
            e_digits = re.search(r"(\d{8})", raw_end)
            if not s_digits or not e_digits:
                continue

            try:
                start_date = datetime.strptime(s_digits.group(1), "%Y%m%d").date()
                end_date = datetime.strptime(e_digits.group(1), "%Y%m%d").date()
            except Exception:
                continue

            # Ensure end_date is at least 1 day after start_date
            if end_date <= start_date:
                end_date = start_date + timedelta(days=1)

            events.append({
                'uid': uid,
                'summary': summary,
                'start_date': start_date,
                'end_date': end_date
            })

        return events

    @staticmethod
    def sync_unit_external_ical(unit_id: int, feed_url: str = None, ics_content: str = None) -> dict:
        """
        Synchronizes an external calendar feed into local reservations for a unit.
        Fetches feed_url if provided, otherwise parses ics_content.
        Creates/updates reservations tagged with booking_source='AIRBNB_ICAL' so they
        block local availability without duplicate collisions.
        """
        unit = db.session.get(RentalUnit, unit_id)
        if not unit:
            return {'success': False, 'error': 'Unit not found', 'imported': 0}

        target_url = feed_url or unit.ical_import_url
        if not target_url and not ics_content:
            return {'success': False, 'error': 'No iCal feed URL or content provided', 'imported': 0}

        content = ics_content
        if not content and target_url:
            try:
                resp = requests.get(target_url, timeout=12, headers={'User-Agent': 'Angaza-Hospitality-iCal/1.0'})
                if resp.status_code != 200:
                    return {'success': False, 'error': f'Failed to fetch feed: HTTP {resp.status_code}', 'imported': 0}
                content = resp.text
            except Exception as e:
                return {'success': False, 'error': f'Network error fetching feed: {str(e)}', 'imported': 0}

        events = ICalService.parse_ical_content(content)
        if not events:
            # Still update last synced timestamp
            unit.ical_last_synced_at = datetime.utcnow()
            if target_url:
                unit.ical_import_url = target_url
            db.session.commit()
            return {'success': True, 'imported': 0, 'message': 'iCal feed parsed successfully; no active events found.'}

        # Resolve or create an external OTA system guest for this organization
        org_id = unit.property.organization_id if unit.property else None
        ota_guest = Guest.query.filter_by(
            organization_id=org_id,
            phone='ICAL-EXTERNAL'
        ).first()

        if not ota_guest:
            ota_guest = Guest(
                organization_id=org_id,
                first_name='External',
                last_name='Airbnb/OTA Guest',
                phone='ICAL-EXTERNAL',
                email='ical-sync@angaza.co.ke',
                special_notes='Automated placeholder guest for external synchronized calendar reservations.'
            )
            db.session.add(ota_guest)
            db.session.flush()

        imported_count = 0
        updated_count = 0
        cutoff = date.today() - timedelta(days=7)

        for ev in events:
            if ev['end_date'] < cutoff:
                continue

            # Clean UID to form standardized reservation_code
            clean_uid = re.sub(r'[^A-Za-z0-9_-]', '', ev['uid'])[:32]
            res_code = f"ICAL-{clean_uid}"

            existing = HospitalityReservation.query.filter_by(
                reservation_code=res_code,
                rental_unit_id=unit.id
            ).first()

            num_nights = (ev['end_date'] - ev['start_date']).days or 1

            if existing:
                existing.check_in_date = ev['start_date']
                existing.check_out_date = ev['end_date']
                existing.num_nights = num_nights
                existing.status = 'CONFIRMED'
                existing.special_requests = ev['summary']
                updated_count += 1
            else:
                new_res = HospitalityReservation(
                    organization_id=org_id,
                    reservation_code=res_code,
                    guest_id=ota_guest.id,
                    rental_unit_id=unit.id,
                    check_in_date=ev['start_date'],
                    check_out_date=ev['end_date'],
                    num_guests=unit.max_guests or 2,
                    num_nights=num_nights,
                    daily_rate_cents=unit.daily_rate_cents or 0,
                    total_stay_cents=(unit.daily_rate_cents or 0) * num_nights,
                    paid_amount_cents=(unit.daily_rate_cents or 0) * num_nights,
                    booking_source='AIRBNB_ICAL',
                    status='CONFIRMED',
                    special_requests=f"Imported from external iCal: {ev['summary']}"
                )
                db.session.add(new_res)
                imported_count += 1

        unit.ical_last_synced_at = datetime.utcnow()
        if target_url:
            unit.ical_import_url = target_url
        db.session.commit()

        return {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'total_events': len(events),
            'last_synced_at': unit.ical_last_synced_at.strftime('%d/%m/%Y %H:%M')
        }
