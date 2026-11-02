# ANGAZA RENTALS SYSTEM (RPMS)
## Premium Enterprise Rental Property Management System

A modern, secure, and production-grade full-stack Flask application tailored for property managers, landlords, and real estate management agencies in Kenya and beyond.

---

### 🌟 Key Features

1. **System Personalization & White-Label Branding**
   - Dynamic business name, custom logo, contact info, and tax/registration PINs across all views, invoices, receipts, and reports.
   - Configurable theme colors, dark mode support, custom currency (default: **KES**), and payment receipt footer notes.
   - Configurable billing rules: default rent payment due day, grace period days, and late fee penalties.

2. **Executive Dashboard & Real-Time Analytics**
   - KPI metrics: Properties, Buildings, Units (Vacant, Occupied, Reserved, Maintenance), Active Tenants.
   - Financial summaries: Expected Monthly Income, Collected Rent, Outstanding Arrears, Collection Rate, Expenses, and Net Operating Income.
   - Interactive Chart.js visualizations: Rent collection vs arrears, occupancy breakdown, monthly income trends, and payment methods.

3. **Multi-Property & Unit Management**
   - Multi-property support: Apartments, Residential Villas, Bedsitters, Single Rooms, Commercial Buildings, Retail Shops, Office Suites, Warehouses, and Mixed-Use Buildings.
   - Multi-building and multi-floor hierarchy with unit-level amenities, bedrooms, bathrooms, base monthly rent, and security deposit requirements.
   - **Interactive Visual Occupancy Grid** color-coding vacant, occupied, reserved, and maintenance units with instant filters.

4. **Tenant CRM & Tenancy Lifecycle**
   - Complete KYC profile: Full Name, National ID/Passport number, phone, email, physical address, occupation, next-of-kin contacts, and emergency information.
   - Move-in onboarding, unit-to-unit transfer history, and lease termination with automated status updates.

5. **House Bookings & Reservation System**
   - Reserve vacant units with prospective tenant registration, booking deposits, and expiry dates.
   - Overlap validation to prevent double-booking.
   - One-click conversion of active reservations into full tenancies.

6. **Rent Billing, Invoicing & Chronological Allocation**
   - Automated monthly rent charge generation with strict idempotency (no duplicate monthly bills).
   - Chronological payment allocation: incoming payments first settle the oldest unpaid arrears before current rent.
   - Security deposit handling, overpayment balance tracking, and partial payments.
   - Reversible payments with full audit trails.
   - Professional PDF Rent Receipts generated using ReportLab.

7. **Safaricom M-Pesa Daraja Integration**
   - Supports **Paybill** and **Till (Buy Goods)** via Safaricom Daraja REST APIs.
   - STK Push simulation and live transaction initiation.
   - Automated C2B callback confirmation webhook (`/mpesa/c2b-callback`).
   - Smart tenant matching by rental unit number in `BillRefNumber` or fallback by phone number.
   - Idempotency guards preventing duplicate receipt processing.

8. **Bank Statement Import & Automated Reconciliation**
   - Upload CSV or Excel bank statements.
   - Intelligent fuzzy column detection (dates, references, credit amounts, narrations).
   - Automatic matching of bank deposits against tenant accounts with a manual review queue for unmatched entries.

9. **Maintenance Management & Operating Expenses**
   - Maintenance ticket logging with priority levels (Low, Medium, High, Emergency).
   - Technician assignment, resolution tracking, and automatic generation of linked property operating expenses.
   - Direct operating expense tracking across properties.

10. **Lease Agreements & Legal Contract PDF Generation**
    - Digital lease agreements with commencement, expiry, rent due day, notice period, and custom terms.
    - Automated query for upcoming expiring leases within 45 days.
    - One-click legal PDF Tenancy Agreement generation.

11. **Financial Reports & Excel Export**
    - Monthly Rent Collection Report.
    - Tenant Arrears Aging & Outstanding Balances Report.
    - Property Income vs Expense Statement (P&L).
    - Landlord Statement (Net payout after management fees).
    - One-click Excel spreadsheet export (`.xlsx`) via openpyxl.

12. **Role-Based Access Control (RBAC) & Security**
    - Granular permissions with built-in roles: `SUPERADMIN`, `PROPERTY_MANAGER`, `LANDLORD`, `ACCOUNTANT`, `CARETAKER`, and `VIEWER`.
    - Landlord-scoped access control restricting managers/landlords to only their designated properties.
    - Comprehensive Audit Trail logging all security, financial, and administrative operations.

---

### 🚀 Quick Start Guide

#### 1. Requirements
- Python 3.8 or newer
- Virtual environment (`venv`)

#### 2. Initialize Database & Seed Roles / Admin User
Run the automated initialization script:
```bash
python init_db.py
```

This will:
- Create all database tables in SQLite (`instance/rental_management.db`).
- Seed system roles and granular permissions.
- Create the default administrator account.

#### 3. Default Login Credentials
- **URL**: `http://localhost:5000/auth/login`
- **Username**: `admin`
- **Password**: `AdminPassword2026!`

*(Remember to change the administrator password after first login in **My Profile**)*

#### 4. Start the Application
```bash
python run.py
```
Then open `http://localhost:5000` in your web browser.

---

### 🧪 Running the Test Suite

The project includes automated pytest test coverage:
```bash
python -m pytest tests/ -v
```
All tests run against an in-memory SQLite database without modifying production data.

---

### 📁 Project Structure

```text
├── app/
│   ├── models/            # SQLAlchemy database models
│   │   ├── user.py        # User, Role, Permission, Landlord
│   │   ├── property.py    # Property, Building, Floor, RentalUnit
│   │   ├── tenant.py      # Tenant, NextOfKin, TenantDocument
│   │   ├── booking.py     # Booking/Reservation
│   │   ├── lease.py       # Lease, TenancyRecord
│   │   ├── finance.py     # RentCharge, Payment, PaymentAllocation
│   │   ├── maintenance.py # MaintenanceRequest, Expense
│   │   ├── system.py      # SystemSetting, DatabaseBackup, AuditLog
│   │   ├── communication.py # Notification, NotificationSetting
│   │   └── gateway.py     # PaymentGatewayConfig, BankAccount, BankTransaction
│   ├── routes/            # Modular Flask Blueprints (13 blueprints)
│   ├── services/          # Business logic & integrations
│   ├── templates/         # Bootstrap 5 responsive Jinja2 templates
│   ├── utils/             # Currency, decorators, PDF generators
│   ├── config.py          # Development, Testing, Production configurations
│   ├── extensions.py      # db, migrate, login_manager, csrf
│   └── __init__.py        # App factory, context processors, jinja filters
├── tests/                 # Full automated test suite (33 tests)
├── init_db.py             # Single-command database setup & seeding
├── run.py                 # Development web server entrypoint
└── README.md              # Project documentation
```

