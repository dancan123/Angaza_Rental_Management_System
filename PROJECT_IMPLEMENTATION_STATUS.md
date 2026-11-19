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

### Phase 5: Quality Assurance & Full Regression Verification (DONE)
- [x] Full test suite executed: **57 out of 57 tests passing** (48 existing regression tests + 6 Hospitality tests + 3 Multi-tenancy tests).
- [x] Zero pyflakes linter errors.
- [x] All database operations safely non-destructive.

---

## 5. Current Progress Log

- **2026-11-19 06:48**: Baseline audit completed. 37 SQLite tables, 17 blueprints, 14 service classes, and 102 routes cataloged. All 48 existing automated tests passing.
- **2026-11-19 06:55**: `PROJECT_IMPLEMENTATION_STATUS.md` published.
- **2026-11-19 07:02**: Implemented Twilio SMS integration (`SmsService`), automated payment & booking SMS, and bulk SMS broadcasting.
- **2026-11-19 07:04**: Implemented Module B (Hospitality and Short-Stay Management): `Guest`, `HospitalityReservation`, `HousekeepingTask`, `HospitalityService`, `hospitality_bp`, dashboard, ADR/RevPAR, and turnover housekeeping automation.
- **2026-11-19 07:06**: Implemented SaaS Multi-Tenancy (`Organization`) with modular subscription tiers and unit limits. Full test suite passing at **57/57 tests**.
