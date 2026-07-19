# LoadFlow

LoadFlow is a freight brokerage operations suite for managing loads from posting to delivery. It connects three account types:

- Broker organizations that create loads, assign carriers, confirm rates, and manage operations staff.
- Carrier organizations that manage assigned freight, update shipment statuses, and upload PODs.
- Shippers that can only view their own shipment status and delivery confirmation.

The project focuses on real business rules: custom RBAC, organization scoping, object-level access, compliance checks, rate confirmation versioning, load state transitions, and audit trails.

## Links

- Repository: `https://github.com/y-abhiram/loadflow`
- Deployed app: `https://loadflow-opal.vercel.app`
- Walkthrough video: `PASTE_LOOM_OR_SCREEN_RECORDING_LINK_HERE`

## Stack

FastAPI, SQLAlchemy, SQLite, Jinja templates, and Tailwind via CDN.

I chose this stack because the assessment is business-logic heavy. FastAPI makes server-side permission enforcement, compliance checks, state transitions, and audit logging easy to inspect while still delivering a usable web interface.

## How LoadFlow Works

1. A broker creates a load for a shipper.
2. The broker assigns a carrier to that load.
3. LoadFlow checks the carrier's compliance record.
4. If the carrier has expired insurance, inactive authority, or unapproved equipment/commodity types, the load is flagged.
5. Flagged loads cannot move past `Carrier Assigned` unless a user with `load.override_compliance_flag` overrides the issue.
6. The broker confirms a rate. Rate confirmations are versioned, so old loads keep the exact rate version that was confirmed.
7. Broker/carrier users move the load through the state machine.
8. Carrier users upload POD metadata after delivery.
9. Broker verifies POD and closes the load.
10. Shipper sees only their own load status and timeline.

## Core Features

- Authentication for Broker, Carrier, and Shipper users
- Broker/Carrier admins can create staff users
- Broker/Carrier admins can create custom roles from a fixed permission catalog
- API-layer RBAC enforcement, not only UI hiding
- Permission denied attempts logged to console and database
- Broker load board with search/filter
- Load creation, carrier assignment, rate confirmation, and status progression
- Carrier compliance records with insurance, authority, equipment, and commodity checks
- Compliance auto-flagging and blocking
- Compliance override only for permitted users
- Rate confirmation versioning
- Load audit trail with actor, timestamp, old status, new status, and notes
- Separate dashboards for Broker, Carrier, and Shipper
- POD upload metadata
- Compliance renewal alerts
- Audit log viewer

## Permission Catalog

Roles are not hardcoded in the code. Admins create roles by choosing permissions from this fixed catalog:

| Permission | Meaning |
| --- | --- |
| `load.create` | Create new loads |
| `load.assign_carrier` | Assign a carrier to a load |
| `load.override_compliance_flag` | Override a blocking compliance flag |
| `rate.confirm` | Confirm rate versions |
| `load.update_status` | Advance load status |
| `staff.manage` | Create staff and custom roles |
| `pod.upload` | Upload POD metadata |

The backend checks permissions like `require_permission("rate.confirm")`. It does not check role names like `Dispatcher` or `Ops Lead`.

## Demo Users

All demo passwords are:

```text
demo123
```

| User | Email | What They Can Do |
| --- | --- | --- |
| Broker Admin | `broker.admin@loadflow.test` | Full broker access: create loads, assign carriers, confirm rates, override compliance, update statuses, manage staff/roles |
| Broker Dispatcher | `dispatcher@loadflow.test` | Assign carriers and confirm rates only |
| Broker Ops Lead | `opslead@loadflow.test` | Assign carriers, confirm rates, update statuses, and override compliance |
| Carrier Admin | `carrier.admin@loadflow.test` | Manage carrier staff/roles, edit own compliance, update assigned loads, upload POD |
| Carrier Driver | `driver@loadflow.test` | View only assigned carrier loads, update status, upload POD |
| Shipper | `shipper@loadflow.test` | View only their own loads and shipment timeline |

## Who Can Do What

| Action | Broker Admin | Broker Dispatcher | Broker Ops Lead | Carrier Admin | Carrier Driver | Shipper |
| --- | --- | --- | --- | --- | --- | --- |
| Create load | Yes | No | No | No | No | No |
| Assign carrier | Yes | Yes | Yes | No | No | No |
| Confirm rate | Yes | Yes | Yes | No | No | No |
| Override compliance | Yes | No | Yes | No | No | No |
| Update load status | Yes | No | Yes | Yes, assigned carrier loads only | Yes, assigned carrier loads only | No |
| Upload POD | Yes | No | No | Yes, assigned carrier loads only | Yes, assigned carrier loads only | No |
| Manage staff/roles | Yes | No | No | Yes | No | No |
| Edit carrier compliance | Broker can view records; carrier edits own record | No | No | Yes, own carrier only | No | No |
| View loads | Broker org loads | Broker org loads | Broker org loads | Own carrier loads | Own carrier loads | Own shipper loads only |

## End-To-End Demo Flow

Use this flow for the screen recording.

1. Login as Broker Admin:

```text
broker.admin@loadflow.test
demo123
```

2. Go to `Loads` and click `Create Load`.

Use:

```text
Shipper: Bluebird Retail Co.
Origin: Dallas, TX
Destination: Atlanta, GA
Equipment: Dry Van
Commodity: Retail Goods
```

The load starts in:

```text
Posted
```

3. Open the new load and assign carrier:

```text
Atlas Freight Lines
```

This carrier passes compliance because it has active authority, valid insurance, and approval for `Dry Van` and `Retail Goods`.

The load moves to:

```text
Carrier Assigned
```

4. Confirm a rate:

```text
Base rate: 2400
Accessorials: 150
Notes: Fuel surcharge included
```

The app creates rate confirmation version `v1` and moves the load to:

```text
Rate Confirmed
```

5. Click `Advance to Dispatched`.

The audit trail records the status change and actor.

6. Logout and login as Carrier Driver:

```text
driver@loadflow.test
demo123
```

The driver only sees loads assigned to `Atlas Freight Lines`.

7. Open the same load and advance:

```text
Dispatched -> In Transit -> Delivered
```

8. Upload a POD file from the POD panel.

The app stores POD metadata and records the upload in the audit trail.

9. Logout and login as Broker Admin again.

Open the same load and advance:

```text
Delivered -> POD Verified -> Invoiced/Closed
```

10. Logout and login as Shipper:

```text
shipper@loadflow.test
demo123
```

The shipper sees only their own loads, including the completed shipment timeline.

## Compliance/RBAC Demo Flow

This second short flow proves the strongest security requirement.

1. Login as Broker Dispatcher:

```text
dispatcher@loadflow.test
demo123
```

2. Open seeded load:

```text
LF-00002
```

This load is assigned to `Prairie Express`, which is non-compliant:

```text
Insurance expired
Authority inactive
Equipment not approved
Commodity not approved
```

The Dispatcher does not have:

```text
load.override_compliance_flag
```

So the backend blocks restricted progression/override attempts.

3. Open the Audit Log and show the permission-denied record.

4. Logout and login as Broker Ops Lead:

```text
opslead@loadflow.test
demo123
```

5. Open `LF-00002` and click `Override Flag`.

The Ops Lead can do this because their role includes:

```text
load.override_compliance_flag
```

The audit trail records the override.

## Creating New Staff And Roles

Broker and Carrier admins can create users from the app.

1. Login as an admin:

```text
broker.admin@loadflow.test
```

or:

```text
carrier.admin@loadflow.test
```

2. Open `Staff & Roles`.
3. Create a role by selecting permissions.
4. Create a staff user and assign that role.
5. New staff users use password:

```text
demo123
```

Example broker role:

```text
Role: Junior Dispatcher
Permissions:
- load.assign_carrier
```

Example staff:

```text
Name: Ravi Dispatcher
Email: ravi@loadflow.test
Role: Junior Dispatcher
```

When Ravi logs in, the backend only allows actions included in the assigned role.

## Scoping Rules

- Broker staff can only see loads for their broker organization.
- Carrier staff can only see loads assigned to their carrier organization.
- Shippers can only see loads connected to their own shipper profile.
- Permissions do not bypass object-level scoping.
- Restricted endpoint attempts are blocked server-side and logged.

## Bootstrap Assumption

The first Broker Admin and Carrier Admin are created by the seed/bootstrap process:

```bash
python seed.py
```

After that, org admins create invited staff and custom roles inside the application.

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed.py
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

## Vercel Notes

The deployed demo uses SQLite in `/tmp/loadflow.db` because Vercel's app directory is read-only. The app auto-seeds demo data when the database is empty.

For production, I would replace SQLite with Postgres, Turso, or another managed database so data persists reliably across serverless cold starts.

## Incomplete / With More Time

- Real email invitations for staff onboarding
- Persistent cloud storage and virus scanning for POD uploads
- External FMCSA/insurance verification integrations
- Payment and invoicing integrations
- Automated test suite and CI pipeline
