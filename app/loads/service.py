from datetime import date

from sqlalchemy.orm import Session

from app.models import CarrierCompliance, Load, LoadAuditEvent, LoadStatus, RateConfirmation, User


def audit(db: Session, load: Load, actor: User, event_type: str, note: str | None = None, from_status: str | None = None, to_status: str | None = None) -> None:
    db.add(
        LoadAuditEvent(
            load_id=load.id,
            actor_user_id=actor.id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            note=note,
        )
    )


def evaluate_compliance(load: Load, compliance: CarrierCompliance | None) -> tuple[bool, str | None]:
    if not compliance:
        return True, "Carrier has no compliance record"
    reasons = []
    if compliance.insurance_expiry < date.today():
        reasons.append("insurance expired")
    if not compliance.authority_active:
        reasons.append("authority inactive")
    equipment = {item.strip().lower() for item in compliance.approved_equipment.split(",") if item.strip()}
    commodities = {item.strip().lower() for item in compliance.approved_commodities.split(",") if item.strip()}
    if load.equipment_type.lower() not in equipment:
        reasons.append("equipment not approved")
    if load.commodity_type.lower() not in commodities:
        reasons.append("commodity not approved")
    return bool(reasons), ", ".join(reasons) if reasons else None


def assign_carrier(db: Session, load: Load, carrier_org_id: int, actor: User) -> None:
    load.carrier_org_id = carrier_org_id
    load.status = LoadStatus.CARRIER_ASSIGNED.value
    compliance = db.query(CarrierCompliance).filter(CarrierCompliance.carrier_org_id == carrier_org_id).first()
    flagged, reason = evaluate_compliance(load, compliance)
    load.compliance_flag = flagged
    load.compliance_reason = reason
    load.compliance_overridden = False
    audit(db, load, actor, "carrier_assigned", reason or "Carrier assigned and compliance passed", LoadStatus.POSTED.value, LoadStatus.CARRIER_ASSIGNED.value)


def confirm_rate(db: Session, load: Load, actor: User, base_rate_cents: int, accessorials_cents: int, notes: str | None) -> RateConfirmation:
    version = len(load.rates) + 1
    rate = RateConfirmation(
        load_id=load.id,
        version=version,
        base_rate_cents=base_rate_cents,
        accessorials_cents=accessorials_cents,
        notes=notes,
        confirmed_by_user_id=actor.id,
    )
    db.add(rate)
    old_status = load.status
    load.status = LoadStatus.RATE_CONFIRMED.value
    audit(db, load, actor, "rate_confirmed", f"Rate v{version} confirmed", old_status, load.status)
    return rate
