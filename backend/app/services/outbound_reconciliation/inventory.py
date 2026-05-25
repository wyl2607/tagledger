import json
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, func, select

from backend.app.models import (
    AuditLog,
    InventoryLocation,
    InventoryMovement,
    User,
)

from ._helpers import (
    _inventory_status_value,
    _normalize_location_code,
)
from .normalize import compact_part_code


def _normalize_location_kind(value: str | None) -> str:
    kind = (value or "").strip().lower()
    if kind not in {"permanent", "long_term", "temporary"}:
        return "permanent"
    return kind


def _get_or_create_inventory_location(
    session: Session,
    *,
    part_key: str,
    location_code: str,
    commit: bool = True,
) -> InventoryLocation:
    row = session.exec(
        select(InventoryLocation).where(
            InventoryLocation.part_key == part_key,
            InventoryLocation.location_code == location_code,
        )
    ).first()
    if row is not None:
        return row
    row = InventoryLocation(
        part_key=part_key,
        location_code=location_code,
        quantity=0,
        status="active",
        zero_stock=True,
    )
    session.add(row)
    session.flush()
    if commit:
        session.commit()
        session.refresh(row)
    return row


def _find_inventory_location(
    session: Session,
    *,
    part_key: str,
    location_code: str,
) -> InventoryLocation | None:
    return session.exec(
        select(InventoryLocation).where(
            InventoryLocation.part_key == part_key,
            InventoryLocation.location_code == location_code,
        )
    ).first()


def _bootstrap_inventory_if_missing(
    session: Session,
    *,
    part_key: str,
    location_code: str,
    operator_id: str,
    reason: str,
    seed_quantity: int,
    commit: bool = True,
) -> InventoryLocation | None:
    normalized_part = compact_part_code(part_key)
    normalized_location = _normalize_location_code(location_code)
    existing = _find_inventory_location(
        session, part_key=normalized_part, location_code=normalized_location
    )
    if existing is not None:
        return None
    quantity = max(0, int(seed_quantity))
    row = InventoryLocation(
        part_key=normalized_part,
        location_code=normalized_location,
        quantity=quantity,
        status="active",
        zero_stock=quantity == 0,
    )
    try:
        session.add(row)
        session.flush()
        movement = _record_inventory_movement(
            session,
            movement_type="bootstrap",
            part_key=normalized_part,
            location_code=normalized_location,
            order_no=None,
            scan_id=None,
            quantity_delta=quantity,
            before_qty=0,
            after_qty=quantity,
            operator_id=operator_id,
            reason=reason,
            commit=False,
        )
        if commit:
            session.commit()
            session.refresh(row)
            session.refresh(movement)
    except Exception:
        session.rollback()
        raise
    return row


def _list_order_locations(required_row: dict[str, object]) -> list[str]:
    return sorted(
        {
            _normalize_location_code(str(location))
            for location in required_row.get("locations", [])
            if str(location).strip()
        }
    )


def _select_location_for_outbound(
    *,
    location_code: str | None,
    required_row: dict[str, object],
) -> tuple[str | None, list[str], bool]:
    available_locations = _list_order_locations(required_row)
    requested = _normalize_location_code(location_code) if location_code else None
    if not available_locations:
        return requested, [], False
    if requested:
        return requested, available_locations, requested in available_locations
    if len(available_locations) == 1:
        return available_locations[0], available_locations, True
    return None, available_locations, False


def _inventory_location_payload(location: InventoryLocation) -> dict[str, object]:
    quantity = int(location.quantity)
    return {
        "id": location.id,
        "part_key": location.part_key,
        "part_name": location.part_name,
        "location_code": location.location_code,
        "quantity": quantity,
        "quantity_on_hand": quantity,
        "status": location.status,
        "zero_stock": bool(location.zero_stock),
        "location_kind": _normalize_location_kind(location.location_kind),
        "replacement_location_code": location.replacement_location_code,
        "updated_at": location.updated_at.isoformat() if location.updated_at else None,
    }


def _movement_payload(movement: InventoryMovement) -> dict[str, object]:
    return {
        "id": movement.id,
        "movement_type": movement.movement_type,
        "part_key": movement.part_key,
        "location_code": movement.location_code,
        "order_no": movement.order_no,
        "scan_id": movement.scan_id,
        "quantity_delta": movement.quantity_delta,
        "before_qty": movement.before_qty,
        "after_qty": movement.after_qty,
        "operator_id": movement.operator_id,
        "idempotency_key": movement.idempotency_key,
        "reason": movement.reason,
        "created_at": movement.created_at.isoformat() if movement.created_at else None,
    }


def _is_outbound_record_idempotency_conflict(exc: IntegrityError) -> bool:
    original = getattr(exc, "orig", None)
    diag = getattr(original, "diag", None)
    constraint_name = str(getattr(diag, "constraint_name", "") or "")
    if constraint_name == "ux_outbound_scans_record":
        return True
    message = f"{original} {exc}"
    return "ux_outbound_scans_record" in message or (
        "outbound_scans.order_no" in message
        and "outbound_scans.part_code" in message
        and "outbound_scans.record_id" in message
    )


def _record_inventory_movement(
    session: Session,
    *,
    movement_type: str,
    part_key: str,
    location_code: str,
    order_no: str | None,
    scan_id: int | None,
    quantity_delta: int,
    before_qty: int,
    after_qty: int,
    operator_id: str,
    reason: str | None,
    idempotency_key: str | None = None,
    commit: bool = True,
) -> InventoryMovement:
    row = InventoryMovement(
        movement_type=movement_type,
        part_key=part_key,
        location_code=location_code,
        order_no=order_no,
        scan_id=scan_id,
        quantity_delta=quantity_delta,
        before_qty=before_qty,
        after_qty=after_qty,
        operator_id=(operator_id.strip() or "self")[:80],
        idempotency_key=_normalize_idempotency_key(idempotency_key),
        reason=reason,
    )
    session.add(row)
    session.flush()
    if commit:
        session.commit()
        session.refresh(row)
    return row


def _apply_inventory_delta(
    session: Session,
    *,
    movement_type: str,
    part_key: str,
    location_code: str,
    quantity_delta: int,
    operator_id: str,
    reason: str,
    order_no: str | None = None,
    scan_id: int | None = None,
    allow_new_location: bool = False,
    commit: bool = True,
    idempotency_key: str | None = None,
) -> tuple[InventoryLocation, InventoryMovement]:
    normalized_part = compact_part_code(part_key)
    normalized_location = _normalize_location_code(location_code)
    location = _get_or_create_inventory_location(
        session,
        part_key=normalized_part,
        location_code=normalized_location,
        commit=False,
    )
    if (
        not allow_new_location
        and location.id is not None
        and location.quantity == 0
        and quantity_delta < 0
    ):
        raise RuntimeError(
            f"insufficient inventory at location {normalized_location} for part {normalized_part}"
        )
    if location.status == "disabled":
        raise RuntimeError(f"location {normalized_location} for part {normalized_part} is disabled")
    before_qty = int(location.quantity)
    after_qty = before_qty + quantity_delta
    if after_qty < 0:
        raise RuntimeError(
            f"insufficient inventory at location {normalized_location} for part {normalized_part}"
        )
    now = datetime.now(UTC)
    location.quantity = after_qty
    location.zero_stock = after_qty == 0
    location_kind = _normalize_location_kind(location.location_kind)
    if location.zero_stock and location_kind == "temporary":
        location.status = "retired"
    elif location.zero_stock:
        location.status = "zero_stock"
    elif location.status == "zero_stock":
        location.status = "active"
    elif location.status == "retired":
        location.status = "active"
    location.updated_at = now
    try:
        session.add(location)
        session.flush()
        movement = _record_inventory_movement(
            session,
            movement_type=movement_type,
            part_key=normalized_part,
            location_code=normalized_location,
            order_no=order_no,
            scan_id=scan_id,
            quantity_delta=quantity_delta,
            before_qty=before_qty,
            after_qty=after_qty,
            operator_id=operator_id,
            reason=reason,
            idempotency_key=idempotency_key,
            commit=False,
        )
        if commit:
            session.commit()
            session.refresh(location)
            session.refresh(movement)
    except Exception:
        session.rollback()
        raise
    return location, movement


def _normalize_idempotency_key(value: str | None) -> str | None:
    key = (value or "").strip()
    if not key:
        return None
    if len(key) > 120:
        raise RuntimeError("idempotency_key must be <= 120 characters")
    return key


def _inbound_request_signature(
    *,
    part_key: str,
    location_code: str,
    quantity: int,
    reason: str,
) -> str:
    return json.dumps(
        {
            "part_key": part_key,
            "location_code": location_code,
            "quantity": quantity,
            "reason": reason,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _find_existing_inbound_movement(
    session: Session,
    *,
    operator_id: str,
    idempotency_key: str,
    part_key: str,
    location_code: str,
    quantity: int,
    reason: str,
) -> InventoryMovement | None:
    movement = session.exec(
        select(InventoryMovement)
        .where(
            InventoryMovement.movement_type == "inbound",
            InventoryMovement.operator_id == (operator_id.strip() or "self")[:80],
            InventoryMovement.idempotency_key == idempotency_key,
        )
        .order_by(InventoryMovement.id.desc())
    ).first()
    if movement is None:
        return None
    if (
        movement.part_key != part_key
        or movement.location_code != location_code
        or int(movement.quantity_delta) != quantity
        or (movement.reason or "") != reason
    ):
        raise RuntimeError("idempotency_key reused with different inbound payload")
    return movement


def _inbound_payload_from_existing(
    *,
    session: Session,
    movement: InventoryMovement,
) -> dict[str, object] | None:
    location = _find_inventory_location(
        session,
        part_key=movement.part_key,
        location_code=movement.location_code,
    )
    if location is None:
        return None
    return {
        "updated": True,
        "created": False,
        "location": _inventory_location_payload(location),
        "movement": _movement_payload(movement),
    }


def inbound_inventory(
    *,
    part_key: str,
    location_code: str,
    quantity: int,
    operator_id: str,
    reason: str,
    idempotency_key: str | None = None,
    session: Session,
) -> dict[str, object]:
    qty = int(quantity)
    if qty <= 0:
        raise RuntimeError("quantity must be > 0")
    normalized_part = compact_part_code(part_key)
    normalized_location = _normalize_location_code(location_code)
    normalized_reason = reason[:200] or "inbound"
    normalized_idempotency_key = _normalize_idempotency_key(idempotency_key)
    request_signature = _inbound_request_signature(
        part_key=normalized_part,
        location_code=normalized_location,
        quantity=qty,
        reason=normalized_reason,
    )
    if normalized_idempotency_key:
        existing_movement = _find_existing_inbound_movement(
            session,
            operator_id=operator_id,
            idempotency_key=normalized_idempotency_key,
            part_key=normalized_part,
            location_code=normalized_location,
            quantity=qty,
            reason=normalized_reason,
        )
        if existing_movement is not None:
            existing_payload = _inbound_payload_from_existing(
                session=session,
                movement=existing_movement,
            )
            if existing_payload is not None:
                return existing_payload
            raise RuntimeError("idempotency_key previous inbound result is unavailable")
    try:
        location, movement = _apply_inventory_delta(
            session,
            movement_type="inbound",
            part_key=normalized_part,
            location_code=normalized_location,
            quantity_delta=qty,
            operator_id=operator_id,
            reason=normalized_reason,
            allow_new_location=True,
            commit=False,
            idempotency_key=normalized_idempotency_key,
        )
        audit = AuditLog(
            event_type="inventory_inbound",
            actor_username=(operator_id.strip() or "self")[:80],
            target_type="inventory_movement",
            target_id=str(movement.id),
            action="inventory.inbound",
            reason=normalized_reason,
            success=True,
            detail_json=json.dumps(
                {
                    "movement_id": movement.id,
                    "location_id": location.id,
                    "part_key": normalized_part,
                    "location_code": normalized_location,
                    "quantity": qty,
                    "idempotency_key": normalized_idempotency_key,
                    "request_signature": request_signature,
                },
                ensure_ascii=False,
            ),
        )
        session.add(audit)
        session.commit()
        session.refresh(location)
        session.refresh(movement)
    except IntegrityError:
        session.rollback()
        if not normalized_idempotency_key:
            raise
        existing_movement = _find_existing_inbound_movement(
            session,
            operator_id=operator_id,
            idempotency_key=normalized_idempotency_key,
            part_key=normalized_part,
            location_code=normalized_location,
            quantity=qty,
            reason=normalized_reason,
        )
        if existing_movement is None:
            raise
        existing_payload = _inbound_payload_from_existing(
            session=session,
            movement=existing_movement,
        )
        if existing_payload is None:
            raise RuntimeError("idempotency_key previous inbound result is unavailable") from None
        return existing_payload
    except Exception:
        session.rollback()
        raise
    return {
        "updated": True,
        "created": True,
        "location": _inventory_location_payload(location),
        "movement": _movement_payload(movement),
    }


def outbound_inventory(
    *,
    part_key: str,
    location_code: str,
    quantity: int,
    operator_id: str,
    reason: str,
    session: Session,
    order_no: str | None = None,
) -> dict[str, object]:
    qty = int(quantity)
    if qty <= 0:
        raise RuntimeError("quantity must be > 0")
    location, movement = _apply_inventory_delta(
        session,
        movement_type="outbound",
        part_key=part_key,
        location_code=location_code,
        quantity_delta=-qty,
        operator_id=operator_id,
        reason=reason[:200] or "outbound",
        order_no=(order_no or "").strip() or None,
    )
    return {
        "updated": True,
        "location": _inventory_location_payload(location),
        "movement": _movement_payload(movement),
    }


def transfer_inventory(
    *,
    part_key: str,
    from_location_code: str,
    to_location_code: str,
    quantity: int,
    operator_id: str,
    reason: str,
    session: Session,
) -> dict[str, object]:
    qty = int(quantity)
    if qty <= 0:
        raise RuntimeError("quantity must be > 0")
    normalized_part = compact_part_code(part_key)
    source_code = _normalize_location_code(from_location_code)
    target_code = _normalize_location_code(to_location_code)
    if source_code == target_code:
        raise RuntimeError("from_location_code and to_location_code must be different")

    source = _find_inventory_location(
        session,
        part_key=normalized_part,
        location_code=source_code,
    )
    if source is None or int(source.quantity) < qty:
        raise RuntimeError(
            f"insufficient inventory at location {source_code} for part {normalized_part}"
        )
    if source.status == "disabled":
        raise RuntimeError(f"location {source_code} for part {normalized_part} is disabled")

    target = _get_or_create_inventory_location(
        session,
        part_key=normalized_part,
        location_code=target_code,
    )
    if target.status == "disabled":
        raise RuntimeError(f"location {target_code} for part {normalized_part} is disabled")

    now = datetime.now(UTC)
    source_before = int(source.quantity)
    target_before = int(target.quantity)
    source.quantity = source_before - qty
    target.quantity = target_before + qty
    source.zero_stock = source.quantity == 0
    target.zero_stock = target.quantity == 0
    if source.zero_stock:
        source.status = "zero_stock"
    elif source.status == "zero_stock":
        source.status = "active"
    if target.status == "zero_stock":
        target.status = "active"
    source.updated_at = now
    target.updated_at = now
    session.add(source)
    session.add(target)
    session.commit()
    session.refresh(source)
    session.refresh(target)

    note = reason[:200] or "transfer"
    movement_out = _record_inventory_movement(
        session,
        movement_type="transfer_out",
        part_key=normalized_part,
        location_code=source_code,
        order_no=None,
        scan_id=None,
        quantity_delta=-qty,
        before_qty=source_before,
        after_qty=source_before - qty,
        operator_id=operator_id,
        reason=f"{note}; to={target_code}",
    )
    movement_in = _record_inventory_movement(
        session,
        movement_type="transfer_in",
        part_key=normalized_part,
        location_code=target_code,
        order_no=None,
        scan_id=None,
        quantity_delta=qty,
        before_qty=target_before,
        after_qty=target_before + qty,
        operator_id=operator_id,
        reason=f"{note}; from={source_code}",
    )
    return {
        "updated": True,
        "from_location": _inventory_location_payload(source),
        "to_location": _inventory_location_payload(target),
        "movements": [_movement_payload(movement_out), _movement_payload(movement_in)],
    }


def set_inventory_location_status(
    *,
    part_key: str,
    location_code: str,
    status: str,
    operator_id: str,
    reason: str,
    replacement_location_code: str | None,
    session: Session,
) -> dict[str, object]:
    normalized_part = compact_part_code(part_key)
    normalized_location = _normalize_location_code(location_code)
    target_status = _inventory_status_value(status)
    row = _get_or_create_inventory_location(
        session,
        part_key=normalized_part,
        location_code=normalized_location,
    )
    row.status = target_status
    row.replacement_location_code = (
        _normalize_location_code(replacement_location_code)
        if replacement_location_code and replacement_location_code.strip()
        else None
    )
    row.updated_at = datetime.now(UTC)
    row.zero_stock = int(row.quantity) <= 0
    session.add(row)
    session.commit()
    session.refresh(row)
    movement = _record_inventory_movement(
        session,
        movement_type="location_status",
        part_key=normalized_part,
        location_code=normalized_location,
        order_no=None,
        scan_id=None,
        quantity_delta=0,
        before_qty=int(row.quantity),
        after_qty=int(row.quantity),
        operator_id=operator_id,
        reason=(reason[:200] or "location_status"),
    )
    return {
        "updated": True,
        "location": _inventory_location_payload(row),
        "movement": _movement_payload(movement),
    }


def get_inventory_locations(
    session: Session,
    part_key: str | None = None,
    location_code: str | None = None,
    status: str | None = None,
    exclude_temporary: bool = False,
) -> dict[str, object]:
    statement = select(InventoryLocation).order_by(
        InventoryLocation.part_key.asc(),
        InventoryLocation.location_code.asc(),
    )
    normalized_part = compact_part_code(part_key) if part_key else ""
    normalized_location = _normalize_location_code(location_code) if location_code else ""
    normalized_status = _inventory_status_value(status) if status else ""
    if normalized_part:
        statement = statement.where(InventoryLocation.part_key == normalized_part)
    if normalized_location:
        statement = statement.where(InventoryLocation.location_code == normalized_location)
    if normalized_status:
        statement = statement.where(InventoryLocation.status == normalized_status)
    if exclude_temporary:
        statement = statement.where(
            func.lower(func.coalesce(InventoryLocation.location_kind, "permanent")) != "temporary"
        )
    rows = session.exec(statement).all()
    return {
        "part_key": normalized_part or None,
        "location_code": normalized_location or None,
        "status": normalized_status or None,
        "exclude_temporary": exclude_temporary,
        "locations": [_inventory_location_payload(row) for row in rows],
    }


def list_alternative_locations(
    session: Session,
    part_key: str,
    exclude_location: str | None = None,
) -> list[dict[str, object]]:
    normalized_part = compact_part_code(part_key)
    normalized_exclude = _normalize_location_code(exclude_location) if exclude_location else ""
    statement = (
        select(InventoryLocation)
        .where(InventoryLocation.part_key == normalized_part)
        .order_by(InventoryLocation.quantity.desc(), InventoryLocation.location_code.asc())
    )
    rows = session.exec(statement).all()
    alternatives: list[dict[str, object]] = []
    for row in rows:
        location_code = _normalize_location_code(row.location_code)
        quantity = int(row.quantity or 0)
        if quantity <= 0:
            continue
        if normalized_exclude and location_code == normalized_exclude:
            continue
        alternatives.append(
            {
                "location_code": location_code,
                "quantity": quantity,
                "status": row.status or "active",
                "location_kind": _normalize_location_kind(row.location_kind),
            }
        )
    return alternatives


def reactivate_inventory_location(
    *,
    inventory_location_id: int,
    reason: str,
    actor: User,
    session: Session,
) -> dict[str, object]:
    row = session.get(InventoryLocation, inventory_location_id)
    if row is None:
        raise RuntimeError(f"inventory location not found: {inventory_location_id}")
    if row.status != "retired":
        raise RuntimeError("only retired location can be reactivated")

    row.status = "active"
    row.updated_at = datetime.now(UTC)
    row.zero_stock = int(row.quantity) <= 0
    session.add(row)
    session.flush()

    movement = InventoryMovement(
        movement_type="location_reactivate",
        part_key=row.part_key,
        location_code=row.location_code,
        order_no=None,
        scan_id=None,
        quantity_delta=0,
        before_qty=int(row.quantity),
        after_qty=int(row.quantity),
        operator_id=actor.username,
        reason=(reason.strip() or "manual_reactivate")[:200],
    )
    session.add(movement)
    session.flush()

    audit = AuditLog(
        event_type="inventory_location_reactivate",
        actor_user_id=actor.id,
        actor_username=actor.username,
        target_type="inventory_location",
        target_id=str(row.id),
        action="inventory.location.reactivate",
        reason=movement.reason,
        success=True,
        detail_json=json.dumps(
            {
                "part_key": row.part_key,
                "location_code": row.location_code,
                "location_kind": _normalize_location_kind(row.location_kind),
                "from_status": "retired",
                "to_status": "active",
                "quantity": int(row.quantity),
            },
            ensure_ascii=False,
        ),
    )
    session.add(audit)
    session.commit()
    session.refresh(row)
    session.refresh(movement)
    session.refresh(audit)

    return {
        "updated": True,
        "location": _inventory_location_payload(row),
        "movement": _movement_payload(movement),
        "audit_log_id": audit.id,
    }


def get_inventory_movements(
    session: Session,
    *,
    part_key: str | None = None,
    location_code: str | None = None,
    limit: int = 100,
) -> dict[str, object]:
    statement = select(InventoryMovement).order_by(
        InventoryMovement.created_at.desc(),
        InventoryMovement.id.desc(),
    )
    normalized_part = compact_part_code(part_key) if part_key else ""
    normalized_location = _normalize_location_code(location_code) if location_code else ""
    if normalized_part:
        statement = statement.where(InventoryMovement.part_key == normalized_part)
    if normalized_location:
        statement = statement.where(InventoryMovement.location_code == normalized_location)
    rows = session.exec(statement.limit(max(1, min(limit, 500)))).all()
    return {
        "part_key": normalized_part or None,
        "location_code": normalized_location or None,
        "movements": [_movement_payload(row) for row in rows],
    }
