from datetime import date, timedelta

from app.auth.security import hash_password
from app.database import Base, SessionLocal, engine
from app.loads.service import audit
from app.models import (
    AccountType,
    CarrierCompliance,
    Load,
    LoadStatus,
    Org,
    OrgMembership,
    Permission,
    Role,
    RolePermission,
    ShipperProfile,
    User,
)
from app.rbac.permissions import PERMISSION_CATALOG


def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def user(db, name: str, email: str, account_type: str) -> User:
    item = User(name=name, email=email, account_type=account_type, password_hash=hash_password("demo123"))
    db.add(item)
    db.flush()
    return item


def role(db, org: Org, name: str, codes: list[str]) -> Role:
    item = Role(org_id=org.id, name=name)
    db.add(item)
    db.flush()
    permissions = db.query(Permission).filter(Permission.code.in_(codes)).all()
    for permission in permissions:
        db.add(RolePermission(role_id=item.id, permission_id=permission.id))
    db.flush()
    return item


def main():
    reset_database()
    db = SessionLocal()
    try:
        for code, label in PERMISSION_CATALOG.items():
            db.add(Permission(code=code, label=label))
        db.flush()

        broker = Org(name="Northstar Brokerage", type="broker")
        carrier = Org(name="Atlas Freight Lines", type="carrier")
        second_carrier = Org(name="Prairie Express", type="carrier")
        db.add_all([broker, carrier, second_carrier])
        db.flush()

        broker_admin = user(db, "Broker Admin", "broker.admin@loadflow.test", AccountType.BROKER.value)
        dispatcher = user(db, "Broker Dispatcher", "dispatcher@loadflow.test", AccountType.BROKER.value)
        ops_lead = user(db, "Broker Ops Lead", "opslead@loadflow.test", AccountType.BROKER.value)
        carrier_admin = user(db, "Carrier Admin", "carrier.admin@loadflow.test", AccountType.CARRIER.value)
        driver = user(db, "Carrier Driver", "driver@loadflow.test", AccountType.CARRIER.value)
        shipper_user = user(db, "Shipper User", "shipper@loadflow.test", AccountType.SHIPPER.value)

        shipper = ShipperProfile(user_id=shipper_user.id, company_name="Bluebird Retail Co.")
        db.add(shipper)
        db.flush()

        dispatcher_role = role(db, broker, "Dispatcher", ["load.assign_carrier", "rate.confirm"])
        ops_role = role(db, broker, "Ops Lead", ["load.assign_carrier", "rate.confirm", "load.update_status", "load.override_compliance_flag"])
        driver_role = role(db, carrier, "Driver", ["load.update_status", "pod.upload"])

        db.add_all(
            [
                OrgMembership(user_id=broker_admin.id, org_id=broker.id, is_admin=True),
                OrgMembership(user_id=dispatcher.id, org_id=broker.id, role_id=dispatcher_role.id),
                OrgMembership(user_id=ops_lead.id, org_id=broker.id, role_id=ops_role.id),
                OrgMembership(user_id=carrier_admin.id, org_id=carrier.id, is_admin=True),
                OrgMembership(user_id=driver.id, org_id=carrier.id, role_id=driver_role.id),
            ]
        )

        db.add_all(
            [
                CarrierCompliance(
                    carrier_org_id=carrier.id,
                    insurance_expiry=date.today() + timedelta(days=90),
                    authority_active=True,
                    approved_equipment="Dry Van, Reefer",
                    approved_commodities="Retail Goods, Food",
                ),
                CarrierCompliance(
                    carrier_org_id=second_carrier.id,
                    insurance_expiry=date.today() - timedelta(days=5),
                    authority_active=False,
                    approved_equipment="Flatbed",
                    approved_commodities="Steel",
                ),
            ]
        )
        db.flush()

        load_one = Load(
            reference="LF-00001",
            broker_org_id=broker.id,
            carrier_org_id=carrier.id,
            shipper_id=shipper.id,
            origin="Dallas, TX",
            destination="Atlanta, GA",
            equipment_type="Dry Van",
            commodity_type="Retail Goods",
            status=LoadStatus.RATE_CONFIRMED.value,
        )
        load_two = Load(
            reference="LF-00002",
            broker_org_id=broker.id,
            carrier_org_id=second_carrier.id,
            shipper_id=shipper.id,
            origin="Phoenix, AZ",
            destination="Denver, CO",
            equipment_type="Dry Van",
            commodity_type="Retail Goods",
            status=LoadStatus.CARRIER_ASSIGNED.value,
            compliance_flag=True,
            compliance_reason="insurance expired, authority inactive, equipment not approved, commodity not approved",
        )
        load_three = Load(
            reference="LF-00003",
            broker_org_id=broker.id,
            shipper_id=shipper.id,
            origin="Chicago, IL",
            destination="Nashville, TN",
            equipment_type="Reefer",
            commodity_type="Food",
            status=LoadStatus.POSTED.value,
        )
        db.add_all([load_one, load_two, load_three])
        db.flush()

        audit(db, load_one, broker_admin, "load_created", "Seeded posted load", None, LoadStatus.POSTED.value)
        audit(db, load_one, broker_admin, "carrier_assigned", "Carrier compliance passed", LoadStatus.POSTED.value, LoadStatus.CARRIER_ASSIGNED.value)
        audit(db, load_one, ops_lead, "rate_confirmed", "Rate v1 confirmed", LoadStatus.CARRIER_ASSIGNED.value, LoadStatus.RATE_CONFIRMED.value)
        audit(db, load_two, broker_admin, "load_created", "Seeded posted load", None, LoadStatus.POSTED.value)
        audit(db, load_two, dispatcher, "carrier_assigned", load_two.compliance_reason, LoadStatus.POSTED.value, LoadStatus.CARRIER_ASSIGNED.value)
        audit(db, load_three, broker_admin, "load_created", "Seeded posted load", None, LoadStatus.POSTED.value)

        db.commit()
        print("Seeded LoadFlow demo database. All demo passwords are demo123.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
