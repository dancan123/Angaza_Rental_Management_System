# Angaza Commercial Property & Hospitality Management Platform
## Project Implementation Status & Architecture Blueprint

**Document Version:** 1.0.0  
**Updated:** 2026-11-19  
**Platform Scope:** Multi-Tenant Commercial Property Management & Hospitality SaaS Platform (Kenya & Pan-African Market)  

---

## 1. Executive Summary & Audit Overview

Angaza Rental Management System is being transformed from a single-business housing management tool into an enterprise-grade, commercial, multi-tenant Property Management SaaS platform. 

The unified platform operates with two distinct modules built on top of shared core services:
- **Module A: Rental Property Management** (Commercial & Residential long-term leases, multi-unit estates, shops, warehouses, student hostels).
- **Module B: Hospitality & Short-Stay Management** (Airbnb, serviced apartments, vacation homes, lodges, boutique guest houses).

---

## 2. Existing System Audit & Implementation Inventory

Each component in the codebase has been audited and classified according to the master development standards:

| Module / Subsystem | Location | Current Database Models | Status | Assessment & Required Enhancement |
| :--- | :--- | :--- | :--- | :--- |
| **Authentication & RBAC** | `app/routes/auth_bp.py`, `app/routes/users_bp.py`, `app/models/user.py` | `User`, `Role`, `Permission`, `RolePermission` | **Complete** | Full hierarchical RBAC (SuperAdmin L100 to Tenant L10), permission matrix in Settings, password resets. |
| **Properties & Units** | `app/routes/properties_bp.py`, `app/models/property.py` | `Property`, `Building`, `Floor`, `RentalUnit` | **Needs Improvement** | Comprehensive physical hierarchy exists. Needs dual operational classification: `RENTAL` vs `HOSPITALITY` / `SHORT_STAY` per unit, and nightly rates. |
| **Tenants & Leases** | `app/routes/tenants_bp.py`, `app/routes/leases_bp.py`, `app/models/tenant.py`, `app/models/lease.py` | `Tenant`, `TenantDocument`, `NextOfKin`, `Lease`, `TenancyRecord` | **Complete** | Full tenant lifecycle, Kenyan ID/phone validation, dynamic PDF lease agreement generation, notice periods, and move-out tracking. |
| **Invoicing & Billing** | `app/routes/billing_bp.py`, `app/models/finance.py` | `RentCharge`, `Payment`, `PaymentAllocation`, `PaymentReversal` | **Complete** | Auto-invoicing, chronological FIFO payment allocation, partial payments, advance overpayments, late fees, and PDF receipt generation. |
| **Utilities & Meters** | `app/routes/utilities_bp.py`, `app/models/utility.py` | `Meter`, `MeterReading` | **Complete** | Water/electricity meter tracking, consumption calculations, and automated rent charge additions. |
| **Maintenance & Expenses** | `app/routes/maintenance_bp.py`, `app/models/maintenance.py` | `MaintenanceRequest`, `MaintenanceRecord`, `Expense` | **Complete** | Ticket logging, contractor assignment, cost approval, automatic expense generation, and resolution tracking. |
| **Financial Reports** | `app/routes/reports_bp.py`, `app/services/report_service.py` | `Payment`, `RentCharge`, `Expense` | **Complete** | Rent collection, arrears aging, income statements, landlord remittance statements, and Excel/PDF exports. |
| **Banking Reconciliation** | `app/routes/banking_bp.py`, `app/services/bank_service.py` | `BankAccount`, `BankTransaction` | **Complete** | Bank CSV statement import, automated reference matching, and transaction reconciliation. |
| **Safaricom Daraja M-Pesa** | `app/routes/mpesa_bp.py`, `app/services/mpesa_service.py` | `PaymentGatewayConfig`, `PaymentCallback` | **Needs Improvement** | STK Push and C2B webhooks work with duplicate idempotency. Needs encrypted credential storage and direct trigger of SMS receipts on confirmed callback. |
| **Communication & Notifications** | `app/routes/communication_bp.py`, `app/services/notification_service.py`, `app/models/communication.py` | `Notification`, `NotificationSetting`, `InternalMessage` | **Partially Implemented** | In-app notifications and message dispatch structure exist. Missing: Twilio / Africa's Talking live SMS gateway client, automated SMS delivery on rent/booking, and bulk SMS UI. |
| **Hospitality & Short-Stay** | Missing dedicated routes/models | Partial `Booking` model used only for rental inquiries | **Missing** | Dedicated Module B required: Guest profiles, nightly/seasonal rates, reservation calendar, check-in/out, housekeeping board (clean/dirty/inspected), ADR, and RevPAR reporting. |
| **Multi-Tenancy & SaaS Plans** | `Landlord` table used as pseudo-tenant | `Landlord`, `LandlordUser` | **Missing** | Proper `Organization` model required for multi-tenant commercial SaaS: company isolation, modular subscriptions (`RENTAL`, `HOSPITALITY`, `COMBINED`), and plan quotas. |
| **Tenant Self-Service Portal** | `app/routes/tenant_portal_bp.py` | Direct query on `Tenant` & `RentalUnit` | **Complete** | Authenticated tenant dashboard, balance inspection, payment history, PDF receipts, and maintenance ticket logging. |
| **Public Marketplace & Leads** | `app/routes/public_bp.py`, `app/models/lead.py` | `HouseSeekerLead`, `ExternalPropertyListing` | **Complete** | Public vacant unit search, landlord self-listing intake, and lead-to-tenancy conversion workflow. |

---

## 3. Platform Architecture & Data Model Enhancements

```
+------------------------------------------------------------------------------------+
|                         ANGAZA COMMERCIAL PLATFORM                                 |
+------------------------------------------------------------------------------------+
                                      |
         +----------------------------+----------------------------+
         |                                                         |
         v                                                         v
+-----------------------------+                           +-----------------------------+
|   MODULE A: RENTAL MGMT     |                           | MODULE B: HOSPITALITY MGMT  |
| - Long-term leases          |                           | - Short-stay & Airbnb       |
| - Monthly/Quarterly rent    |                           | - Daily/Seasonal room rates |
| - Security deposits         |                           | - Guest reservation calendar|
| - Late payment penalties    |                           | - Check-in / Check-out      |
| - Tenant portal & arrears   |                           | - Housekeeping & Mini-bar   |
| - Utility meter charges     |                           | - ADR, RevPAR, Occupancy %  |
+-----------------------------+                           +-----------------------------+
         |                                                         |
         +----------------------------+----------------------------+
                                      |
                                      v
+------------------------------------------------------------------------------------+
|                             SHARED PLATFORM ENGINE                                 |
| - Multi-Tenant Organizations (`Organization`, `SubscriptionPlan`, `ModuleAccess`) |
| - Users, Hierarchical RBAC & Audit Trails (`AuditLog`)                             |
| - Physical Assets (`Property`, `Building`, `Floor`, `RentalUnit`)                  |
| - Unified Financial Ledger (`Payment`, `Expense`, `PaymentAllocation`)             |
| - Safaricom Daraja M-Pesa Gateway (STK Push, C2B Webhook, Idempotency)             |
| - Twilio / Africa's Talking SMS Gateway (Automated Payment & Booking SMS)          |
| - Document & PDF Engine (Leases, Invoices, Receipts, Statements)                   |
+------------------------------------------------------------------------------------+
```

---

## 4. Phased Implementation Roadmap

### Phase 1: Audit, Architecture Blueprint & Baseline Health (DONE)
- [x] Inspect complete codebase, models, services, routes, templates, and database tables.
- [x] Verify baseline regression tests (48/48 passing).
- [x] Document audit and create `PROJECT_IMPLEMENTATION_STATUS.md`.

### Phase 2: Multi-Tenancy & SaaS Subscription Foundations (DONE)
- [x] Add `Organization` model (`app/models/organization.py`) supporting modular subscriptions:
  - `RENTAL_STANDARD`
  - `HOSPITALITY_STANDARD`
  - `COMBINED_SUITE`
  - `ENTERPRISE`
- [x] Add multi-tenant isolation links (`organization_id`) to `Property` and `User`.
- [x] Auto-seed default Organization ("Angaza Premier Properties") on startup preserving all existing single-landlord records.
- [x] Automated unit test suite (`tests/test_phase16_saas_multitenancy.py` — 3/3 passing).

### Phase 3: Twilio SMS Gateway & Automated Communications Engine (DONE)
- [x] Implement `SmsService` (`app/services/sms_service.py`):
  - E.164 phone normalization for Kenya (+2547XXXXXXXX, +2541XXXXXXXX).
  - Twilio REST API integration via standard `requests` HTTP transport.
  - Safe local/sandbox fallback (`sent_status='SIMULATED'`) preventing errors when live credentials are not yet configured.
- [x] Wire automated SMS triggers:
  - On verified rent payment -> sends instant SMS receipt to tenant and revenue alert to landlord.
  - On reservation creation / inquiry approval -> sends booking confirmation SMS with reservation code and move-in/check-in dates.
- [x] Add Twilio Gateway and Bulk SMS Broadcast views in `app/templates/communication/index.html`.
- [x] Add Twilio config, test ping, and bulk broadcast routes in `app/routes/communication_bp.py`.

### Phase 4: Module B — Hospitality & Short-Stay Management Engine (DONE)
- [x] Enhance `RentalUnit` with dual operational classification:
  - `operational_type` (`LONG_TERM` vs `SHORT_STAY`)
  - `daily_rate_cents` (Nightly room rate)
  - `max_guests` (Guest capacity)
  - `cleaning_status` (`CLEAN`, `DIRTY`, `INSPECTED`, `OUT_OF_SERVICE`)
- [x] Create Hospitality Models (`app/models/hospitality.py`):
  - `Guest`: Full name, phone, national ID/passport, nationality, emergency contact.
  - `HospitalityReservation`: Unique reservation code (`STAY-YYYYMM-XXXX`), unit, check-in, check-out, nights, daily rate, total stay cost, balance, source (`DIRECT`, `AIRBNB`, `BOOKING_COM`, `WALK_IN`), status (`CONFIRMED`, `CHECKED_IN`, `CHECKED_OUT`, `CANCELLED`).
  - `HousekeepingTask`: Unit, cleaner user, task type (`TURNOVER_CLEAN`, `DAILY_REFRESH`, `DEEP_CLEAN`), priority, status (`PENDING`, `IN_PROGRESS`, `COMPLETED`).
- [x] Create `HospitalityService` (`app/services/hospitality_service.py`):
  - Date-based room availability and double-booking conflict prevention.
  - Guest check-in (`actual_check_in_time`, unit becomes `OCCUPIED`).
  - Guest check-out (financial settlement, unit becomes `VACANT`, status set to `DIRTY`, automated turnover cleaning task generated).
  - Hospitality KPIs: Occupancy %, ADR (Average Daily Rate), RevPAR (Revenue Per Available Room), today's arrivals and departures.
- [x] Create `hospitality_bp` Blueprint (`app/routes/hospitality_bp.py`):
  - `/hospitality/` — Executive Hospitality Dashboard.
  - `/hospitality/reservations` — Reservation management, search, and booking modal.
  - `/hospitality/reservations/<id>/check-in` & `/check-out` — Arrival and departure workflows.
  - `/hospitality/housekeeping` — Room readiness board and task assignments.
  - `/hospitality/rooms` — Inventory pricing and short-stay classification.
- [x] Create Hospitality Templates (`app/templates/hospitality/index.html`, `reservations.html`, `housekeeping.html`, `rooms.html`).
- [x] Add Module Switcher in `base.html` allowing one-click toggle between Rental Management Suite and Hospitality Suite.
- [x] Automated test suite (`tests/test_phase15_hospitality.py` — 6/6 passing).

### Phase 5: Platform Super Admin Control Plane (DONE)
- [x] Control Plane Blueprint (`app/routes/platform_bp.py`):
  - `/platform/organizations` — Organization directory, metrics, tier filters, search.
  - `/platform/organizations/create` — Customer organization onboarding with custom property/unit/user limits.
  - `/platform/organizations/<id>/status` — Account suspension and reactivation.
  - `/platform/organizations/<id>/subscription` — Subscription tier updates (`RENTAL_STANDARD`, `HOSPITALITY_STANDARD`, `COMBINED_SUITE`, `ENTERPRISE`).
  - `/platform/organizations/<id>/users` — Personnel directory per customer organization.
  - `/platform/organizations/<id>/assign-user` — Assign unallocated users to organizations.
  - `/platform/analytics` — Platform-wide cross-tenant analytics: managed units, tier breakdown, enforcement status, MTD gross processed volume (rental + hospitality), and SMS delivery counts.
- [x] Subscription enforcement middleware in `app/__init__.py`:
  - Intercepts requests for accounts with `SUSPENDED` or `EXPIRED` status and blocks access with informative guidance.
- [x] Automated test suite (`tests/test_phase17_platform_admin.py` — 5/5 passing).

### Phase 6: Shared Services — Consolidated Commercial Executive P&L (DONE)
- [x] Consolidated Financial Summary (`ReportService.get_consolidated_financial_summary()`):
  - Aggregates long-term rental revenue (verified `Payment` records).
  - Aggregates short-stay hospitality revenue (`HospitalityReservation` records).
  - Deducts combined operating expenses (`Expense` records).
  - Computes Net Operating Income (NOI), operating profit margin %, and module revenue share.
- [x] Route & Executive Template:
  - `/reports/consolidated` (`app/routes/reports_bp.py`).
  - `app/templates/reports/consolidated.html` — Full audit-grade P&L statement with metric cards, revenue breakdown chart, and printable ledger.
- [x] Automated test suite (`tests/test_phase18_consolidated_reports.py` — 2/2 passing).

### Phase 7: Dynamic & Seasonal Pricing Engine (DONE)
- [x] Dynamic Pricing Model (`app/models/pricing.py` — `RoomPricingRule`):
  - Rule categories: `PEAK_SEASON`, `LOW_SEASON`, `WEEKEND_PREMIUM`, `HOLIDAY`, `EVENT`, `DISCOUNT`, `CUSTOM`.
  - Adjustment types: Percentage multiplier (e.g. `1.5` = +50%) or fixed flat rate daily override.
  - Day-of-week mask (e.g. `FRI,SAT,SUN` for weekend premiums).
  - Unit-specific vs global application priority.
- [x] Pricing Routes & Views:
  - `/hospitality/pricing` — Rules directory, add rule modal, toggle activation, deletion.
  - Integration with `HospitalityService.create_reservation()` to automatically calculate multi-day rates based on active pricing rules.
- [x] Automated test suite (`tests/test_phase19_pricing_and_calendar.py` — 4/4 passing).

### Phase 8: Multi-Room Availability Calendar (DONE)
- [x] Interactive Booking Calendar (`/hospitality/calendar`):
  - 30-day rolling grid showing all rooms/units.
  - Real-time status indicators: Available (green), Checked In (red), Confirmed (yellow), Leased (gray).
  - Quick navigation by start date.

### Phase 9: SMS Delivery Logs & Gateway History (DONE)
- [x] SMS Delivery History Dashboard (`/communication/sms-history`):
  - Paginated audit log of all transactional SMS transmissions.
  - Status tracking: `SENT`, `FAILED`, `PENDING`, and `SIMULATED`.
  - Type filters: rent payment receipts, booking confirmations, guest check-in SMS, and bulk broadcasts.

### Phase 10: Quality Assurance & Full Regression Verification (DONE)
- [x] Full test suite executed: **72 out of 72 tests passing** across 20 comprehensive test phases.
- [x] Zero pyflakes linter errors across all models, services, blueprints, and utilities.
- [x] All database operations safely backward-compatible and non-destructive.

### Phase 11 / Phase 20: Commercial Self-Onboarding, Impersonation & SMS Credit Sales (DONE)
- [x] **Public Self-Onboarding (`/auth/register`)**:
  - Open customer registration portal requiring organization name, manager name, contact email/phone, and chosen subscription tier.
  - Automatically provisions `Organization` with `TRIAL` status, 14-day expiry date, and complimentary 50 SMS credits.
  - Provisions primary `User` with `PROPERTY_MANAGER` role, default `Landlord` profile, and links them to the new organization.
  - Automatically signs in the user and routes them directly to their operational dashboard.
- [x] **Superadmin User Impersonation (`/auth/impersonate/<user_id>`)**:
  - Platform Superadmin can impersonate any organization manager or landlord directly from the UI (`/platform/organizations/<id>/users` or `/users`).
  - Seamlessly switches session context to view properties, billing, and reservations as that user.
  - Yellow sticky alert bar displayed across all pages with an instant "Exit Impersonation" action (`/auth/stop-impersonation`) restoring the superadmin session safely.
- [x] **SMS Credit Wallet & Billing System**:
  - `Organization.sms_credits` balance tracked per organization.
  - `SmsService.send_sms()` verifies and deducts 1 credit per dispatched SMS.
  - Automatic out-of-credit blocking with clear user feedback prompting top-up.
  - Platform Superadmin has unlimited SMS bypass for system administration.
  - Superadmin can sell / top-up SMS credits for any organization (`POST /platform/organizations/<id>/add-sms`).
  - Real-time SMS credit balance badge shown in the top navigation bar.
- [x] **Subscription Timeline Management**:
  - Superadmin can extend or adjust trial / subscription duration (`POST /platform/organizations/<id>/update-timeline`).
  - Real-time trial countdown badge ("X days trial left") displayed in navigation.
  - Subscription suspension middleware automatically handles expired organizations.
- [x] Automated test suite (`tests/test_phase20_commercial_onboarding_and_sms.py` — 4/4 passing).

### Phase 12 / Phase 21: Tabular Airbnb Room Management, Custom Renaming & Financial Totals (DONE)
- [x] **Comprehensive Tabular Airbnb Inventory View (`/hospitality/rooms`)**:
  - Re-architected room inventory into an interactive administrative table with executive summary KPI cards.
  - Cards: Total Inventory, Live Occupancy %, Daily Rate Capacity, Estimated Monthly Capacity (30-day projected potential), and Total Historical Collected Revenue.
  - Interactive search bar (search by room name, property, or guest) and filter pills (All, Short-Stay Only, Vacant & Ready, Occupied/Booked, Needs Cleaning).
- [x] **Open Custom Room Renaming (`POST /hospitality/rooms/<id>/update`)**:
  - Each landlord/user can freely rename rooms according to their branding needs (e.g., "Sunset Suite 101", "Deluxe Ocean Penthouse", "Studio B-4").
  - Configures daily/nightly rates, monthly equivalent rent, room type, max guest capacity, cleaning status, and room notes/keypad codes.
- [x] **Financial Transparency per Room**:
  - **Rate / Day**: Nightly charge clearly formatted (e.g. `KES 4,500 / night`).
  - **Rate / Month**: 30-day projected capacity or monthly rent (e.g. `KES 135,000 / mo`).
  - **Total Collected**: All-time actual revenue received and paid for that specific room from bookings.
- [x] **Live Occupancy Status & Timelines**:
  - Displays whether room is Booked/Occupied, Reserved, or Vacant & Ready.
  - For booked rooms: displays active guest name, contact phone, check-in date ➜ check-out date, nights count, and paid status.
- [x] **1-Click Operational Controls & Guest Communication**:
  - **Book Room**: Instant booking modal pre-populated with room identifier and daily rate.
  - **Check-In / Check-Out**: Direct actions to check in arriving guests or complete departures.
  - **1-Click Cleaning Toggle (`POST /hospitality/rooms/<id>/toggle-cleaning`)**: Instant toggle between Clean & Ready and Dirty turnover.
  - **Direct Room SMS (`POST /hospitality/rooms/<id>/send-sms`)**: Dispatches SMS messages with one-click templates (Check-in directions & keybox code, WiFi credentials & house rules, Checkout reminder).
- [x] Automated test suite (`tests/test_phase21_hospitality_rooms_tabular.py` — 4/4 passing).

---

## 5. Current Progress Log

- **2026-11-19 06:48**: Baseline audit completed. 37 SQLite tables, 17 blueprints, 14 service classes, and 102 routes cataloged. All 48 existing automated tests passing.
- **2026-11-19 06:55**: `PROJECT_IMPLEMENTATION_STATUS.md` published.
- **2026-11-19 07:02**: Implemented Twilio SMS integration (`SmsService`), automated payment & booking SMS, and bulk SMS broadcasting.
- **2026-11-19 07:04**: Implemented Module B (Hospitality and Short-Stay Management): `Guest`, `HospitalityReservation`, `HousekeepingTask`, `HospitalityService`, `hospitality_bp`, dashboard, ADR/RevPAR, and turnover housekeeping automation.
- **2026-11-19 07:06**: Implemented SaaS Multi-Tenancy (`Organization`) with modular subscription tiers and unit limits. Full test suite passing at **57/57 tests**.
- **2026-11-19 07:45**: Implemented Platform Super Admin Control Plane (`platform_bp`), account suspension enforcement middleware, user organization assignments, and cross-tenant platform usage analytics.
- **2026-11-19 07:48**: Implemented Consolidated Commercial P&L Report (`reports.consolidated`), Dynamic Seasonal Pricing (`RoomPricingRule`), Multi-Room Booking Calendar (`hospitality.calendar`), and SMS Delivery History (`communication.sms_history`).
- **2026-11-19 07:54**: Full test suite verified at **68 out of 68 passing tests** (zero regressions across all 19 test phases). All changes staged and committed.
- **2026-11-19 08:35**: Phase 20 completed: Commercial self-onboarding portal, 14-day free trial engine, user impersonation for superadmin, SMS credits wallet and billing, subscription timeline management. Full test suite verified at **72 out of 72 passing tests** (zero regressions across all 20 test phases).
- **2026-11-19 08:57**: Phase 21 completed: Tabular Airbnb room inventory, custom room renaming by landlords, daily/monthly/total collected financial columns, live occupancy timelines, 1-click booking, 1-click cleaning status toggle, and direct guest SMS communication. Full test suite verified at **76 out of 76 passing tests** (zero regressions across all 21 test phases).
