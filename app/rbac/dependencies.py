from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.models import AccountType, Load, OrgMembership, PermissionDeniedLog, User


def active_membership(user: User) -> OrgMembership | None:
    return user.memberships[0] if user.memberships else None


def user_permissions(user: User) -> set[str]:
    membership = active_membership(user)
    if not membership:
        return set()
    if membership.is_admin:
        return {
            "load.create",
            "load.assign_carrier",
            "load.override_compliance_flag",
            "rate.confirm",
            "load.update_status",
            "staff.manage",
            "pod.upload",
        }
    if not membership.role:
        return set()
    return {rp.permission.code for rp in membership.role.permissions}


def log_denied(db: Session, request: Request, user: User | None, reason: str) -> None:
    db.add(PermissionDeniedLog(user_id=user.id if user else None, path=str(request.url.path), reason=reason))
    db.commit()
    who = user.email if user else "anonymous"
    print(f"[permission-denied] user={who} path={request.url.path} reason={reason}")


def require_permission(db: Session, request: Request, user: User, permission: str) -> None:
    if permission not in user_permissions(user):
        log_denied(db, request, user, f"missing permission {permission}")
        raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")


def ensure_can_access_load(db: Session, request: Request, user: User, load: Load) -> None:
    membership = active_membership(user)
    if user.account_type == AccountType.SHIPPER.value:
        if not user.shipper_profile or load.shipper_id != user.shipper_profile.id:
            log_denied(db, request, user, "shipper attempted to access another shipper load")
            raise HTTPException(status_code=403, detail="You cannot access this load")
        return
    if not membership:
        log_denied(db, request, user, "org user has no membership")
        raise HTTPException(status_code=403, detail="No org membership")
    if user.account_type == AccountType.BROKER.value and load.broker_org_id == membership.org_id:
        return
    if user.account_type == AccountType.CARRIER.value and load.carrier_org_id == membership.org_id:
        return
    log_denied(db, request, user, "org scope violation")
    raise HTTPException(status_code=403, detail="You cannot access this load")
