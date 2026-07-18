from app.models import LoadStatus

NEXT_STATUS = {
    LoadStatus.POSTED.value: LoadStatus.CARRIER_ASSIGNED.value,
    LoadStatus.CARRIER_ASSIGNED.value: LoadStatus.RATE_CONFIRMED.value,
    LoadStatus.RATE_CONFIRMED.value: LoadStatus.DISPATCHED.value,
    LoadStatus.DISPATCHED.value: LoadStatus.IN_TRANSIT.value,
    LoadStatus.IN_TRANSIT.value: LoadStatus.DELIVERED.value,
    LoadStatus.DELIVERED.value: LoadStatus.POD_VERIFIED.value,
    LoadStatus.POD_VERIFIED.value: LoadStatus.CLOSED.value,
}


def next_status(current: str) -> str | None:
    return NEXT_STATUS.get(current)
