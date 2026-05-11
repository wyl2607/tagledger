from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlmodel import Session, select

from backend.app.models import AuditLog, InventoryLocation, InventoryMovement, User
from backend.app.services.location_profile import location_profile_payload
from backend.app.services.material_mapping import normalize_material_code
from backend.app.services.transfer_service import FACTORIES

LOCATION_KIND_ALIASES = {"long_term": "permanent"}
LOCATION_KINDS = {"permanent", "temporary"}
HIDDEN_LOCATION_STATUSES = {"retired", "disabled"}
PENDING_LOCATION_STATUSES = {"pending_restock", "pending_replacement"}


def normalize_factory_id(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in FACTORIES:
        raise RuntimeError(f"unsupported factory_id: {value}")
    return normalized


def normalize_part_key(value: str) -> str:
    normalized = normalize_material_code(value or "")
    if not normalized:
        raise RuntimeError("part_key is required")
    return normalized


def normalize_location_code(value: str) -> str:
    code = (value or "").strip().upper()
    if not code:
        raise RuntimeError("location_code is required")
    return code[:80]


def normalize_location_kind(value: str | None) -> str:
    kind = (value or "permanent").strip().lower()
    kind = LOCATION_KIND_ALIASES.get(kind, kind)
    if kind not in LOCATION_KINDS:
        raise RuntimeError(f"unsupported location_kind: {value}")
    return kind


def normalize_reason(value: str | None) -> str:
    reason = (value or "").strip()
    if not reason:
        raise RuntimeError("reason is required")
    return reason[:200]


def apply_location_visibility_rules(location: InventoryLocation) -> None:
    quantity = int(location.quantity or 0)
    kind = normalize_location_kind(location.location_kind)
    location.location_kind = kind
    location.zero_stock = quantity <= 0
    if location.status == "disabled":
        return
    if location.status in PENDING_LOCATION_STATUSES:
        return
    if quantity <= 0 and kind == "temporary":
        location.status = "retired"
    elif quantity <= 0:
        location.status = "zero_stock"
    elif location.status in {"zero_stock", "retired"}:
        location.status = "active"


def location_payload(location: InventoryLocation) -> dict[str, object]:
    kind = normalize_location_kind(location.location_kind)
    quantity = int(location.quantity or 0)
    visible = location.status not in HIDDEN_LOCATION_STATUSES
    return {
        "id": location.id or 0,
        "factory_id": location.factory_id,
        "part_key": location.part_key,
        "part_name": location.part_name,
        "location_code": location.location_code,
        "location_profile": location_profile_payload(location.location_code, kind),
        "quantity": quantity,
        "status": location.status,
        "zero_stock": bool(location.zero_stock),
        "location_kind": kind,
        "replacement_location_code": location.replacement_location_code,
        "visible": visible,
        "restock_required": visible and kind == "permanent" and quantity <= 0,
        "updated_at": location.updated_at.isoformat() if location.updated_at else None,
    }


def list_inventory_locations(
    *,
    session: Session,
    factory_id: str | None = None,
    part_key: str | None = None,
    include_hidden: bool = False,
) -> dict[str, object]:
    normalized_factory = normalize_factory_id(factory_id) if factory_id else None
    normalized_part = normalize_part_key(part_key) if part_key else None
    statement = select(InventoryLocation)
    if normalized_factory:
        statement = statement.where(InventoryLocation.factory_id == normalized_factory)
    if normalized_part:
        statement = statement.where(InventoryLocation.part_key == normalized_part)
    rows = session.exec(
        statement.order_by(
            InventoryLocation.factory_id.asc(),
            InventoryLocation.location_code.asc(),
            InventoryLocation.part_key.asc(),
        )
    ).all()
    visible_rows = [row for row in rows if row.status not in HIDDEN_LOCATION_STATUSES]
    payload_rows = rows if include_hidden else visible_rows
    restock_rows = [
        row
        for row in visible_rows
        if normalize_location_kind(row.location_kind) == "permanent" and int(row.quantity or 0) <= 0
    ]
    return {
        "factory_id": normalized_factory,
        "part_key": normalized_part,
        "locations": [location_payload(row) for row in payload_rows],
        "summary": {
            "location_count": len(rows),
            "visible_location_count": len(visible_rows),
            "retired_location_count": sum(1 for row in rows if row.status == "retired"),
            "restock_required_count": len(restock_rows),
            "total_quantity": sum(int(row.quantity or 0) for row in visible_rows),
        },
    }


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
    move_qty = int(quantity)
    if move_qty <= 0:
        raise RuntimeError("quantity must be > 0")
    if source.status in HIDDEN_LOCATION_STATUSES:
        raise RuntimeError(f"source location is not movable: {source.status}")
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
    source_before = int(source.quantity or 0)
    variance_adjustment: InventoryMovement | None = None
    if source_before < move_qty:
        # Field count is ahead of system count; reconcile source first, then apply move.
        source.quantity = move_qty
        apply_location_visibility_rules(source)
        source.updated_at = now
        variance_adjustment = InventoryMovement(
            factory_id=source.factory_id,
            movement_type="manual_adjust",
            part_key=source.part_key,
            location_code=source.location_code,
            quantity_delta=move_qty - source_before,
            before_qty=source_before,
            after_qty=move_qty,
            operator_id=operator.username,
            reason=f"盘点发现差异; {normalized_reason}"[:200],
            created_at=now,
        )
        session.add(source)
        session.add(variance_adjustment)
        source_before = move_qty
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
    if variance_adjustment is not None:
        session.add(variance_adjustment)
    session.add(out_movement)
    session.add(in_movement)
    session.add(audit)
    session.commit()
    refresh_rows: list[object] = [source, target, out_movement, in_movement]
    if variance_adjustment is not None:
        refresh_rows.insert(0, variance_adjustment)
    for row in refresh_rows:
        session.refresh(row)
    movements = [out_movement, in_movement]
    if variance_adjustment is not None:
        movements.insert(0, variance_adjustment)
    return {
        "move_id": move_id,
        "source_location": location_payload(source),
        "target_location": location_payload(target),
        "movements": [movement_payload(row) for row in movements],
    }


def movement_payload(movement: InventoryMovement) -> dict[str, object]:
    return {
        "id": movement.id or 0,
        "factory_id": movement.factory_id,
        "movement_type": movement.movement_type,
        "part_key": movement.part_key,
        "location_code": movement.location_code,
        "quantity_delta": movement.quantity_delta,
        "before_qty": movement.before_qty,
        "after_qty": movement.after_qty,
        "operator_id": movement.operator_id,
        "reason": movement.reason,
        "created_at": movement.created_at.isoformat() if movement.created_at else None,
    }
