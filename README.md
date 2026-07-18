# LoadFlow

Freight brokerage operations suite built for the RB DesignTech take-home assessment.

## Stack

FastAPI, SQLAlchemy, SQLite, Jinja templates, HTMX-style server flows, and Tailwind via CDN.

Chosen because this project is business-logic heavy: RBAC, org scoping, compliance gating, audit trails, and state transitions are easy to review and verify in a Python backend with server-rendered workflows.

## Features

- Auth for Broker, Carrier, and Shipper users
- Broker/Carrier org admins can create staff and custom roles from a fixed permission catalog
- API-layer permission checks with org and object-level scoping
- Permission denied attempts logged to the database and console
- Load CRUD, broker load board search/filter, and role-aware dashboards
- Full load state machine with timestamped/attributed audit trail
- Carrier compliance records with insurance, authority, equipment, and commodity checks
- Compliance auto-flagging that blocks progression past Carrier Assigned unless overridden
- Rate confirmation versioning
- POD upload metadata and viewer link
- Compliance renewal alerts and audit log viewer

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed.py
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Demo Users

All passwords are `demo123`.

| Persona | Email |
| --- | --- |
| Broker Admin | `broker.admin@loadflow.test` |
| Broker Dispatcher | `dispatcher@loadflow.test` |
| Broker Ops Lead | `opslead@loadflow.test` |
| Carrier Admin | `carrier.admin@loadflow.test` |
| Carrier Driver | `driver@loadflow.test` |
| Shipper | `shipper@loadflow.test` |

## Bootstrap Assumption

The first Broker and Carrier admin accounts are created by `python seed.py`, representing an internal bootstrap/onboarding process. After that, staff users and their custom roles are created by org admins inside the app.

## Suggested Walkthrough

1. Log in as Broker Dispatcher and try to advance a flagged load. The UI and API block it.
2. Open the audit log to show the denied attempt.
3. Log in as Broker Ops Lead and override the compliance flag.
4. Confirm a rate and advance the load.
5. Log in as Carrier Driver and update shipment status/upload POD.
6. Log in as Shipper and show only that shipper's own load timeline.

## Incomplete / With More Time

- Real email invitations for staff onboarding
- Cloud object storage and virus scanning for POD uploads
- External FMCSA/insurance verification integrations
- Payment/invoicing integrations
- Automated test suite and CI pipeline
