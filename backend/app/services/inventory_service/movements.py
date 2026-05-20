from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Session, select

from backend.app.models import AuditLog, InventoryLocation, InventoryMovement, User

from .normalize import (
    HIDDEN_LOCATION_STATUSES,
    InventoryPermissionError,
    apply_location_visibility_rules,
    location_payload,
    movement_payload,
    normalize_location_code,
    normalize_location_kind,
    normalize_reason,
)


def adjust_inventory_location(
    *,
    session: Session,
    location_id: int,
    quantity: int,
    reason: str,
    operator: User,
) -> dict[str, object]:
    location = session.get(InventoryLocation, location_id)
    if location is None:
        raise RuntimeError("location not found")
    next_qty = int(quantity)
    if next_qty < 0:
        raise RuntimeError("quantity must be >= 0")
    normalized_reason = normalize_reason(reason)
    now = datetime.now(UTC)
    before_qty = int(location.quantity or 0)
    location.quantity = next_qty
    apply_location_visibility_rules(location)
    location.updated_at = now
    movement = InventoryMovement(
        factory_id=location.factory_id,
        movement_type="manual_adjust",
        part_key=location.part_key,
        location_code=location.location_code,
        quantity_delta=next_qty - before_qty,
        before_qty=before_qty,
        after_qty=next_qty,
        operator_id=operator.username,
        reason=normalized_reason,
        created_at=now,
    )
    session.add(location)
    session.add(movement)
    session.commit()
    session.refresh(location)
    session.refresh(movement)
    return {
        "location": location_payload(location),
        "movement": movement_payload(movement),
    }


def _find_or_create_target_location(
    *,
    session: Session,
    source: InventoryLocation,
    target_location_code: str,
    target_location_kind: str,
) -> InventoryLocation:
    code = normalize_location_code(target_location_code)
    kind = normalize_location_kind(target_location_kind)
    row = session.exec(
        select(InventoryLocation).where(
            InventoryLocation.factory_id == source.factory_id,
            InventoryLocation.part_key == source.part_key,
            InventoryLocation.location_code == code,
        )
    ).first()
    if row is not None:
        if row.status == "disabled":
            raise RuntimeError(f"target location disabled: {code}")
        row.location_kind = normalize_location_kind(row.location_kind)
        return row
    row = InventoryLocation(
        factory_id=source.factory_id,
        part_key=source.part_key,
        part_name=source.part_name,
        location_code=code,
        quantity=0,
        status="active",
        zero_stock=True,
        location_kind=kind,
    )
    session.add(row)
    session.flush()
    return row


def move_inventory_quantity(
    *,
    session: Session,
    source_location_id: int,
    target_location_code: str,
    quantity: int,
    target_location_kind: str,
    reason: str,
    operator: User,
) -> dict[str, object]:
    source = session.get(InventoryLocation, source_location_id)
    if source is None:
        raise RuntimeError("source location not found")
    if operator.factory_id != source.factory_id:
        raise InventoryPermissionError("source location is outside your factory")
    move_qty = int(quantity)
    if move_qty <= 0:
        raise RuntimeError("quantity must be > 0")
    if source.status in HIDDEN_LOCATION_STATUSES:
        raise RuntimeError(f"source location is not movable: {source.status}")
    source_before = int(source.quantity or 0)
    if source_before < move_qty:
        raise RuntimeError("insufficient inventory")
    target_code = normalize_location_code(target_location_code)
    if target_code == normalize_location_code(source.location_code):
        raise RuntimeError("target location must differ from source location")
    normalized_reason = normalize_reason(reason)
    now = datetime.now(UTC)
    move_id = f"mv-{uuid.uuid4().hex[:12]}"
    target = _find_or_create_target_location(
        session=session,
        source=source,
        target_location_code=target_code,
        target_location_kind=target_location_kind,
    )
    target_before = int(target.quantity or 0)
    source.quantity = source_before - move_qty
    target.quantity = target_before + move_qty
    apply_location_visibility_rules(source)
    apply_location_visibility_rules(target)
    source.updated_at = now
    target.updated_at = now
    out_movement = InventoryMovement(
        factory_id=source.factory_id,
        movement_type="manual_move_out",
        part_key=source.part_key,
        location_code=source.location_code,
        transfer_id=move_id,
        quantity_delta=-move_qty,
        before_qty=source_before,
        after_qty=int(source.quantity),
        operator_id=operator.username,
        reason=f"{normalized_reason}; to={target.location_code}"[:200],
        created_at=now,
    )
    in_movement = InventoryMovement(
        factory_id=target.factory_id,
        movement_type="manual_move_in",
        part_key=target.part_key,
        location_code=target.location_code,
        transfer_id=move_id,
        quantity_delta=move_qty,
        before_qty=target_before,
        after_qty=int(target.quantity),
        operator_id=operator.username,
        reason=f"{normalized_reason}; from={source.location_code}"[:200],
        created_at=now,
    )
    audit = AuditLog(
        factory_id=source.factory_id,
        event_type="inventory_move",
        actor_user_id=operator.id,
        actor_username=operator.username,
        target_type="inventory_move",
        target_id=move_id,
        action="inventory.move",
        reason=normalized_reason,
        success=True,
    )
    session.add(source)
    session.add(target)
    session.add(out_movement)
    session.add(in_movement)
    session.add(audit)
    session.commit()
    for row in (source, target, out_movement, in_movement):
        session.refresh(row)
    return {
        "move_id": move_id,
        "source_location": location_payload(source),
        "target_location": location_payload(target),
        "movements": [movement_payload(out_movement), movement_payload(in_movement)],
    }
