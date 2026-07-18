from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class OrgType(str, Enum):
    BROKER = "broker"
    CARRIER = "carrier"


class AccountType(str, Enum):
    BROKER = "broker"
    CARRIER = "carrier"
    SHIPPER = "shipper"


class LoadStatus(str, Enum):
    POSTED = "Posted"
    CARRIER_ASSIGNED = "Carrier Assigned"
    RATE_CONFIRMED = "Rate Confirmed"
    DISPATCHED = "Dispatched"
    IN_TRANSIT = "In Transit"
    DELIVERED = "Delivered"
    POD_VERIFIED = "POD Verified"
    CLOSED = "Invoiced/Closed"


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(20))

    memberships = relationship("OrgMembership", back_populates="org")
    roles = relationship("Role", back_populates="org")
    compliance = relationship("CarrierCompliance", back_populates="carrier_org", uselist=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    account_type: Mapped[str] = mapped_column(String(20))

    memberships = relationship("OrgMembership", back_populates="user")
    shipper_profile = relationship("ShipperProfile", back_populates="user", uselist=False)


class ShipperProfile(Base):
    __tablename__ = "shipper_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    company_name: Mapped[str] = mapped_column(String(160))

    user = relationship("User", back_populates="shipper_profile")
    loads = relationship("Load", back_populates="shipper")


class OrgMembership(Base):
    __tablename__ = "org_memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)

    user = relationship("User", back_populates="memberships")
    org = relationship("Org", back_populates="memberships")
    role = relationship("Role", back_populates="memberships")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    label: Mapped[str] = mapped_column(String(140))

    roles = relationship("RolePermission", back_populates="permission")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"))
    name: Mapped[str] = mapped_column(String(100))

    org = relationship("Org", back_populates="roles")
    permissions = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")
    memberships = relationship("OrgMembership", back_populates="role")


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"))

    role = relationship("Role", back_populates="permissions")
    permission = relationship("Permission", back_populates="roles")


class CarrierCompliance(Base):
    __tablename__ = "carrier_compliance"

    id: Mapped[int] = mapped_column(primary_key=True)
    carrier_org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"), unique=True)
    insurance_expiry: Mapped[datetime] = mapped_column(Date)
    authority_active: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_equipment: Mapped[str] = mapped_column(String(255))
    approved_commodities: Mapped[str] = mapped_column(String(255))

    carrier_org = relationship("Org", back_populates="compliance")


class Load(Base):
    __tablename__ = "loads"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    broker_org_id: Mapped[int] = mapped_column(ForeignKey("orgs.id"))
    carrier_org_id: Mapped[int | None] = mapped_column(ForeignKey("orgs.id"), nullable=True)
    shipper_id: Mapped[int] = mapped_column(ForeignKey("shipper_profiles.id"))
    origin: Mapped[str] = mapped_column(String(160))
    destination: Mapped[str] = mapped_column(String(160))
    equipment_type: Mapped[str] = mapped_column(String(80))
    commodity_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default=LoadStatus.POSTED.value)
    compliance_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    compliance_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    compliance_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    broker_org = relationship("Org", foreign_keys=[broker_org_id])
    carrier_org = relationship("Org", foreign_keys=[carrier_org_id])
    shipper = relationship("ShipperProfile", back_populates="loads")
    rates = relationship("RateConfirmation", back_populates="load", order_by="RateConfirmation.version")
    audits = relationship("LoadAuditEvent", back_populates="load", order_by="LoadAuditEvent.created_at")
    pods = relationship("PODDocument", back_populates="load")


class RateConfirmation(Base):
    __tablename__ = "rate_confirmations"
    __table_args__ = (UniqueConstraint("load_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    load_id: Mapped[int] = mapped_column(ForeignKey("loads.id"))
    version: Mapped[int] = mapped_column(Integer)
    base_rate_cents: Mapped[int] = mapped_column(Integer)
    accessorials_cents: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    load = relationship("Load", back_populates="rates")
    confirmed_by = relationship("User")


class LoadAuditEvent(Base):
    __tablename__ = "load_audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    load_id: Mapped[int] = mapped_column(ForeignKey("loads.id"))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_type: Mapped[str] = mapped_column(String(80))
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    load = relationship("Load", back_populates="audits")
    actor = relationship("User")


class PermissionDeniedLog(Base):
    __tablename__ = "permission_denied_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    path: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class PODDocument(Base):
    __tablename__ = "pod_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    load_id: Mapped[int] = mapped_column(ForeignKey("loads.id"))
    uploaded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(String(180))
    storage_note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    load = relationship("Load", back_populates="pods")
    uploaded_by = relationship("User")
