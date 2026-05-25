from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, select

from backend.app.models import InventoryLocation


def _pick_source_location(
    session: Session,
    *,
    factory_id: str,
    part_key: str,
    quantity: int,
) -> InventoryLocation:
    rows = session.exec(
        select(InventoryLocation)
        .where(
            InventoryLocation.factory_id == factory_id,
            InventoryLocation.part_key == part_key,
        )
        .order_by(InventoryLocation.quantity.desc(), InventoryLocation.location_code.asc())
    ).all()
    for row in rows:
        if row.status == "disabled":
            continue
        if int(row.quantity) >= quantity:
            return row
    raise RuntimeError(f"insufficient inventory for transfer: {factory_id} {part_key}")


def _resolve_target_location(
    session: Session,
    *,
    factory_id: str,
    part_key: str,
    fallback_location_code: str,
) -> InventoryLocation:
    row = session.exec(
        select(InventoryLocation)
        .where(
            InventoryLocation.factory_id == factory_id,
            InventoryLocation.part_key == part_key,
        )
        .order_by(InventoryLocation.quantity.desc(), InventoryLocation.location_code.asc())
    ).first()
    if row is not None:
        return row

    existing_codes = {
        str(code)
        for code in session.exec(
            select(InventoryLocation.location_code).where(InventoryLocation.part_key == part_key)
        ).all()
        if code
    }
    fallback = (fallback_location_code or "").strip() or "LOC"
    base = f"{fallback}-{factory_id}"
    candidate = base
    suffix = 2
    while candidate in existing_codes:
        candidate = f"{base}-{suffix}"
        suffix += 1
        if suffix > 1000:
            raise RuntimeError(f"failed to allocate target location code for {part_key}")

    row = InventoryLocation(
        factory_id=factory_id,
        part_key=part_key,
        location_code=candidate,
        quantity=0,
        status="active",
        zero_stock=True,
    )
    session.add(row)
    session.flush()
    return row


def _update_location_after_change(location: InventoryLocation) -> None:
    quantity = int(location.quantity)
    kind = (location.location_kind or "permanent").strip().lower()
    location.zero_stock = quantity <= 0
    if location.status == "disabled":
        return
    if quantity <= 0 and kind == "temporary":
        location.status = "retired"
    elif quantity <= 0:
        location.status = "zero_stock"
    elif location.status in {"zero_stock", "retired"}:
        location.status = "active"


def _apply_target_inbound(
    *,
    target_location: InventoryLocation,
    quantity: int,
) -> tuple[int, int]:
    before_qty = int(target_location.quantity)
    target_location.quantity = before_qty + quantity
    _update_location_after_change(target_location)
    target_location.updated_at = datetime.now(UTC)
    return before_qty, int(target_location.quantity)
