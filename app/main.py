from datetime import date, timedelta

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
from starlette.middleware.sessions import SessionMiddleware

from app.auth.dependencies import current_user
from app.auth.security import hash_password, verify_password
from app.database import Base, SessionLocal, engine, get_db
from app.loads.service import assign_carrier, audit, confirm_rate
from app.loads.state_machine import next_status
from app.models import (
    AccountType,
    CarrierCompliance,
    Load,
    LoadAuditEvent,
    LoadStatus,
    Org,
    OrgMembership,
    Permission,
    PermissionDeniedLog,
    PODDocument,
    Role,
    RolePermission,
    ShipperProfile,
    User,
)
from app.rbac.dependencies import active_membership, ensure_can_access_load, require_permission, user_permissions
from app.rbac.permissions import PERMISSION_CATALOG
from seed import seed_demo_data

Base.metadata.create_all(bind=engine)
with SessionLocal() as startup_db:
    seed_demo_data(startup_db)
    startup_db.commit()

app = FastAPI(title="LoadFlow")
app.add_middleware(SessionMiddleware, secret_key="loadflow-dev-secret-change-me")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code in {401, 403}:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "status_code": exc.status_code, "detail": exc.detail},
            status_code=exc.status_code,
        )
    raise exc


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


templates.env.filters["money"] = money


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        users = db.query(User).order_by(User.account_type, User.email).all()
        return templates.TemplateResponse("login.html", {"request": request, "users": users})
    return redirect("/dashboard")


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        users = db.query(User).order_by(User.account_type, User.email).all()
        return templates.TemplateResponse("login.html", {"request": request, "users": users, "error": "Invalid email or password"}, status_code=400)
    request.session["user_id"] = user.id
    return redirect("/dashboard")


@app.post("/demo-login")
def demo_login(request: Request, user_id: int = Form(...), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Demo user not found")
    request.session["user_id"] = user.id
    return redirect("/dashboard")


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = active_membership(user)
    permissions = user_permissions(user)
    if user.account_type == AccountType.BROKER.value:
        loads = db.query(Load).filter(Load.broker_org_id == membership.org_id).order_by(Load.created_at.desc()).all()
        alerts = [load for load in loads if load.compliance_flag and not load.compliance_overridden]
        return templates.TemplateResponse("broker_dashboard.html", {"request": request, "user": user, "membership": membership, "permissions": permissions, "loads": loads, "alerts": alerts})
    if user.account_type == AccountType.CARRIER.value:
        loads = db.query(Load).filter(Load.carrier_org_id == membership.org_id).order_by(Load.created_at.desc()).all()
        return templates.TemplateResponse("carrier_dashboard.html", {"request": request, "user": user, "membership": membership, "permissions": permissions, "loads": loads})
    loads = db.query(Load).filter(Load.shipper_id == user.shipper_profile.id).order_by(Load.created_at.desc()).all()
    return templates.TemplateResponse("shipper_dashboard.html", {"request": request, "user": user, "permissions": permissions, "loads": loads})


@app.get("/loads", response_class=HTMLResponse)
def loads_board(request: Request, q: str = "", status: str = "", db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = active_membership(user)
    query = db.query(Load)
    if user.account_type == AccountType.BROKER.value:
        query = query.filter(Load.broker_org_id == membership.org_id)
    elif user.account_type == AccountType.CARRIER.value:
        query = query.filter(Load.carrier_org_id == membership.org_id)
    else:
        query = query.filter(Load.shipper_id == user.shipper_profile.id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Load.reference.ilike(like), Load.origin.ilike(like), Load.destination.ilike(like), Load.commodity_type.ilike(like)))
    if status:
        query = query.filter(Load.status == status)
    loads = query.order_by(Load.created_at.desc()).all()
    return templates.TemplateResponse("loads.html", {"request": request, "user": user, "membership": membership, "permissions": user_permissions(user), "loads": loads, "q": q, "status": status, "statuses": [s.value for s in LoadStatus]})


@app.post("/loads")
def create_load(request: Request, shipper_id: int = Form(...), origin: str = Form(...), destination: str = Form(...), equipment_type: str = Form(...), commodity_type: str = Form(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_permission(db, request, user, "load.create")
    membership = active_membership(user)
    count = db.query(Load).count() + 1
    load = Load(reference=f"LF-{count:05d}", broker_org_id=membership.org_id, shipper_id=shipper_id, origin=origin, destination=destination, equipment_type=equipment_type, commodity_type=commodity_type)
    db.add(load)
    db.flush()
    audit(db, load, user, "load_created", "Load posted", None, LoadStatus.POSTED.value)
    db.commit()
    return redirect(f"/loads/{load.id}")


@app.get("/loads/new", response_class=HTMLResponse)
def new_load(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_permission(db, request, user, "load.create")
    shippers = db.query(ShipperProfile).order_by(ShipperProfile.company_name).all()
    return templates.TemplateResponse("new_load.html", {"request": request, "user": user, "membership": active_membership(user), "permissions": user_permissions(user), "shippers": shippers})


@app.get("/loads/{load_id}", response_class=HTMLResponse)
def load_detail(request: Request, load_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    load = db.query(Load).options(joinedload(Load.rates), joinedload(Load.audits)).filter(Load.id == load_id).first()
    if not load:
        raise HTTPException(404, "Load not found")
    ensure_can_access_load(db, request, user, load)
    carriers = db.query(Org).filter(Org.type == "carrier").order_by(Org.name).all()
    return templates.TemplateResponse("load_detail.html", {"request": request, "user": user, "membership": active_membership(user), "permissions": user_permissions(user), "load": load, "carriers": carriers, "next_status": next_status(load.status)})


@app.post("/loads/{load_id}/assign")
def assign_load_carrier(request: Request, load_id: int, carrier_org_id: int = Form(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_permission(db, request, user, "load.assign_carrier")
    load = db.get(Load, load_id)
    if not load:
        raise HTTPException(404, "Load not found")
    ensure_can_access_load(db, request, user, load)
    assign_carrier(db, load, carrier_org_id, user)
    db.commit()
    return redirect(f"/loads/{load.id}")


@app.post("/loads/{load_id}/override")
def override_compliance(request: Request, load_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_permission(db, request, user, "load.override_compliance_flag")
    load = db.get(Load, load_id)
    if not load:
        raise HTTPException(404, "Load not found")
    ensure_can_access_load(db, request, user, load)
    load.compliance_overridden = True
    audit(db, load, user, "compliance_overridden", load.compliance_reason)
    db.commit()
    return redirect(f"/loads/{load.id}")


@app.post("/loads/{load_id}/rate")
def rate_load(request: Request, load_id: int, base_rate: int = Form(...), accessorials: int = Form(0), notes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_permission(db, request, user, "rate.confirm")
    load = db.get(Load, load_id)
    if not load:
        raise HTTPException(404, "Load not found")
    ensure_can_access_load(db, request, user, load)
    if load.compliance_flag and not load.compliance_overridden:
        raise HTTPException(403, "Compliance flag blocks rate confirmation until resolved or overridden")
    confirm_rate(db, load, user, base_rate * 100, accessorials * 100, notes)
    db.commit()
    return redirect(f"/loads/{load.id}")


@app.post("/loads/{load_id}/advance")
def advance_load(request: Request, load_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_permission(db, request, user, "load.update_status")
    load = db.get(Load, load_id)
    if not load:
        raise HTTPException(404, "Load not found")
    ensure_can_access_load(db, request, user, load)
    if load.status == LoadStatus.CARRIER_ASSIGNED.value and load.compliance_flag and not load.compliance_overridden:
        raise HTTPException(403, "Compliance flag blocks progression past Carrier Assigned")
    target = next_status(load.status)
    if not target:
        raise HTTPException(400, "Load is already closed")
    old = load.status
    load.status = target
    audit(db, load, user, "status_changed", f"{old} -> {target}", old, target)
    db.commit()
    return redirect(f"/loads/{load.id}")


@app.post("/loads/{load_id}/pod")
async def pod_upload(request: Request, load_id: int, file: UploadFile, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_permission(db, request, user, "pod.upload")
    load = db.get(Load, load_id)
    if not load:
        raise HTTPException(404, "Load not found")
    ensure_can_access_load(db, request, user, load)
    pod = PODDocument(load_id=load.id, uploaded_by_user_id=user.id, filename=file.filename or "pod.pdf", storage_note="Demo stores POD metadata only; production would use object storage.")
    db.add(pod)
    audit(db, load, user, "pod_uploaded", pod.filename)
    db.commit()
    return redirect(f"/loads/{load.id}")


@app.get("/staff", response_class=HTMLResponse)
def staff_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_permission(db, request, user, "staff.manage")
    membership = active_membership(user)
    roles = db.query(Role).filter(Role.org_id == membership.org_id).order_by(Role.name).all()
    staff = db.query(OrgMembership).filter(OrgMembership.org_id == membership.org_id).all()
    permissions = db.query(Permission).order_by(Permission.code).all()
    return templates.TemplateResponse("staff.html", {"request": request, "user": user, "membership": membership, "permissions": user_permissions(user), "roles": roles, "staff": staff, "catalog": permissions})


@app.post("/roles")
def create_role(request: Request, name: str = Form(...), permission_codes: list[str] = Form([]), db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_permission(db, request, user, "staff.manage")
    membership = active_membership(user)
    role = Role(org_id=membership.org_id, name=name)
    db.add(role)
    db.flush()
    permissions = db.query(Permission).filter(Permission.code.in_(permission_codes)).all()
    for permission in permissions:
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    db.commit()
    return redirect("/staff")


@app.post("/staff")
def create_staff(request: Request, name: str = Form(...), email: str = Form(...), role_id: int = Form(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_permission(db, request, user, "staff.manage")
    membership = active_membership(user)
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(400, "Email already exists")
    staff_user = User(name=name, email=email, password_hash=hash_password("demo123"), account_type=user.account_type)
    db.add(staff_user)
    db.flush()
    db.add(OrgMembership(user_id=staff_user.id, org_id=membership.org_id, role_id=role_id, is_admin=False))
    db.commit()
    return redirect("/staff")


@app.get("/compliance", response_class=HTMLResponse)
def compliance_page(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = active_membership(user)
    if user.account_type == AccountType.CARRIER.value:
        records = db.query(CarrierCompliance).filter(CarrierCompliance.carrier_org_id == membership.org_id).all()
    else:
        records = db.query(CarrierCompliance).all()
    expiring = [record for record in records if record.insurance_expiry <= date.today() + timedelta(days=30)]
    return templates.TemplateResponse("compliance.html", {"request": request, "user": user, "membership": membership, "permissions": user_permissions(user), "records": records, "expiring": expiring})


@app.post("/compliance/{record_id}")
def update_compliance(request: Request, record_id: int, insurance_expiry: str = Form(...), authority_active: str = Form("off"), approved_equipment: str = Form(...), approved_commodities: str = Form(...), db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = active_membership(user)
    record = db.get(CarrierCompliance, record_id)
    if not record:
        raise HTTPException(404, "Compliance record not found")
    if user.account_type == AccountType.CARRIER.value and record.carrier_org_id != membership.org_id:
        raise HTTPException(403, "Cannot edit another carrier compliance record")
    record.insurance_expiry = date.fromisoformat(insurance_expiry)
    record.authority_active = authority_active == "on"
    record.approved_equipment = approved_equipment
    record.approved_commodities = approved_commodities
    db.commit()
    return redirect("/compliance")


@app.get("/audit", response_class=HTMLResponse)
def audit_log(request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)):
    events = db.query(LoadAuditEvent).order_by(LoadAuditEvent.created_at.desc()).limit(100).all()
    denied = db.query(PermissionDeniedLog).order_by(PermissionDeniedLog.created_at.desc()).limit(50).all()
    return templates.TemplateResponse("audit.html", {"request": request, "user": user, "membership": active_membership(user), "permissions": user_permissions(user), "events": events, "denied": denied})
