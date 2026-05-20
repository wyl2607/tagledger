from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from backend.app.models import AuditLog, InventoryMovement, User

from .idempotency import (
    _find_existing_transfer_id,
    _transfer_payload_from_existing,
    _transfer_request_signature,
)
from .locations import (
    _apply_target_inbound,
    _pick_source_location,
    _resolve_target_location,
    _update_location_after_change,
)
from .normalize import (
    FACTORIES,
    _normalize_factory_id,
    _normalize_idempotency_key,
    _normalize_part_key,
    _normalize_reason,
    _to_utc,
)


def create_transfer(
    *,
    source_factory: str,
    target_factory: str,
    part_key: str,
    quantity: int,
    reason: str,
    idempotency_key: str | None = None,
    operator: User,
    session: Session,
) -> dict[str, object]:
    source_factory_id = _normalize_factory_id(source_factory)
    target_factory_id = _normalize_factory_id(target_factory)
    if source_factory_id == target_factory_id:
        raise RuntimeError("source_factory and target_factory must be different")
    normalized_part = _normalize_part_key(part_key)
    normalized_reason = _normalize_reason(reason)
    transfer_qty = int(quantity)
    if transfer_qty <= 0:
        raise RuntimeError("quantity must be > 0")
    request_signature = _transfer_request_signature(
        source_factory=source_factory_id,
        target_factory=target_factory_id,
        part_key=normalized_part,
        quantity=transfer_qty,
        reason=normalized_reason,
    )
    normalized_idempotency_key = _normalize_idempotency_key(idempotency_key)
    if normalized_idempotency_key:
        existing_transfer_id = _find_existing_transfer_id(
            session,
            operator=operator,
            idempotency_key=normalized_idempotency_key,
            request_signature=request_signature,
        )
        if existing_transfer_id:
            existing_payload = _transfer_payload_from_existing(
                session=session,
                transfer_id=existing_transfer_id,
            )
            if existing_payload is not None:
                return existing_payload

    transfer_id = f"tf-{uuid.uuid4().hex[:12]}"
    now = datetime.now(UTC)
    source_location = _pick_source_location(
        session,
        factory_id=source_factory_id,
        part_key=normalized_part,
        quantity=transfer_qty,
    )
    target_location = _resolve_target_location(
        session,
        factory_id=target_factory_id,
        part_key=normalized_part,
        fallback_location_code=source_location.location_code,
    )
    if target_location.status == "disabled":
        raise RuntimeError(f"target location disabled: {target_location.location_code}")

    source_before = int(source_location.quantity)
    source_location.quantity = source_before - transfer_qty
    _update_location_after_change(source_location)
    source_location.updated_at = now
    session.add(source_location)
    session.flush()

    try:
        target_before, target_after = _apply_target_inbound(
            target_location=target_location,
            quantity=transfer_qty,
        )
        session.add(target_location)
        session.flush()

        out_movement = InventoryMovement(
            factory_id=source_factory_id,
            movement_type="transfer_out",
            part_key=normalized_part,
            location_code=source_location.location_code,
            order_no=None,
            transfer_id=transfer_id,
            scan_id=None,
            quantity_delta=-transfer_qty,
            before_qty=source_before,
            after_qty=int(source_location.quantity),
            operator_id=operator.username,
            reason=f"{normalized_reason}; to={target_factory_id}:{target_location.location_code}"[
                :200
            ],
            created_at=now,
        )
        in_movement = InventoryMovement(
            factory_id=target_factory_id,
            movement_type="transfer_in",
            part_key=normalized_part,
            location_code=target_location.location_code,
            order_no=None,
            transfer_id=transfer_id,
            scan_id=None,
            quantity_delta=transfer_qty,
            before_qty=target_before,
            after_qty=target_after,
            operator_id=operator.username,
            reason=f"{normalized_reason}; from={source_factory_id}:{source_location.location_code}"[
                :200
            ],
            created_at=now,
        )
        session.add(out_movement)
        session.add(in_movement)
        session.flush()

        audit = AuditLog(
            factory_id=source_factory_id,
            event_type="inventory_transfer",
            actor_user_id=operator.id,
            actor_username=operator.username,
            target_type="inventory_transfer",
            target_id=transfer_id,
            action="inventory.transfer",
            reason=normalized_reason,
            success=True,
            detail_json=json.dumps(
                {
                    "transfer_id": transfer_id,
                    "source_factory": source_factory_id,
                    "target_factory": target_factory_id,
                    "part_key": normalized_part,
                    "quantity": transfer_qty,
                    "source_location_code": source_location.location_code,
                    "target_location_code": target_location.location_code,
                    "idempotency_key": normalized_idempotency_key,
                    "request_signature": request_signature,
                },
                ensure_ascii=False,
            ),
        )
        session.add(audit)
        session.commit()
        session.refresh(out_movement)
        session.refresh(in_movement)
        session.refresh(source_location)
        session.refresh(target_location)
        session.refresh(audit)
    except Exception:
        session.rollback()
        raise

    return {
        "created": True,
        "transfer_id": transfer_id,
        "source_factory": source_factory_id,
        "target_factory": target_factory_id,
        "part_key": normalized_part,
        "quantity": transfer_qty,
        "source_location": {
            "factory_id": source_location.factory_id,
            "location_code": source_location.location_code,
            "quantity": int(source_location.quantity),
            "status": source_location.status,
        },
        "target_location": {
            "factory_id": target_location.factory_id,
            "location_code": target_location.location_code,
            "quantity": int(target_location.quantity),
            "status": target_location.status,
        },
        "movements": [
            {
                "id": out_movement.id,
                "factory_id": out_movement.factory_id,
                "movement_type": out_movement.movement_type,
                "part_key": out_movement.part_key,
                "location_code": out_movement.location_code,
                "transfer_id": out_movement.transfer_id,
                "quantity_delta": out_movement.quantity_delta,
                "before_qty": out_movement.before_qty,
                "after_qty": out_movement.after_qty,
                "created_at": out_movement.created_at.isoformat()
                if out_movement.created_at
                else None,
            },
            {
                "id": in_movement.id,
                "factory_id": in_movement.factory_id,
                "movement_type": in_movement.movement_type,
                "part_key": in_movement.part_key,
                "location_code": in_movement.location_code,
                "transfer_id": in_movement.transfer_id,
                "quantity_delta": in_movement.quantity_delta,
                "before_qty": in_movement.before_qty,
                "after_qty": in_movement.after_qty,
                "created_at": in_movement.created_at.isoformat()
                if in_movement.created_at
                else None,
            },
        ],
        "audit_log_id": audit.id,
    }


def list_transfers(
    *,
    session: Session,
    factory_id: str | None = None,
    days: int = 30,
    limit: int = 200,
) -> dict[str, object]:
    normalized_factory = _normalize_factory_id(factory_id) if factory_id else None
    now = datetime.now(UTC)
    since = now - timedelta(days=max(1, min(days, 365)))
    rows = session.exec(
        select(InventoryMovement)
        .where(
            InventoryMovement.transfer_id.is_not(None),
            InventoryMovement.created_at >= since,
            InventoryMovement.movement_type.in_(("transfer_out", "transfer_in")),
        )
        .order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc())
        .limit(max(1, min(limit, 500)))
    ).all()
    grouped: dict[str, dict[str, object]] = defaultdict(dict)
    for row in rows:
        transfer_id = str(row.transfer_id or "")
        if not transfer_id:
            continue
        entry = grouped[transfer_id]
        entry["transfer_id"] = transfer_id
        entry["part_key"] = row.part_key
        entry["quantity"] = abs(int(row.quantity_delta))
        entry["created_at"] = _to_utc(row.created_at).isoformat() if row.created_at else None
        entry["reason"] = row.reason
        if row.movement_type == "transfer_out":
            entry["source_factory"] = row.factory_id
            entry["source_location_code"] = row.location_code
        elif row.movement_type == "transfer_in":
            entry["target_factory"] = row.factory_id
            entry["target_location_code"] = row.location_code
    transfers = sorted(
        grouped.values(),
        key=lambda item: str(item.get("created_at") or ""),
        reverse=True,
    )
    if normalized_factory:
        transfers = [
            row
            for row in transfers
            if row.get("source_factory") == normalized_factory
            or row.get("target_factory") == normalized_factory
        ]
    return {
        "factory_id": normalized_factory,
        "days": max(1, min(days, 365)),
        "count": len(transfers),
        "transfers": transfers,
    }


def factory_summary_report(
    *,
    session: Session,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
) -> dict[str, object]:
    start = _to_utc(from_at) or (datetime.now(UTC) - timedelta(days=30))
    end = _to_utc(to_at) or datetime.now(UTC)
    if end < start:
        raise RuntimeError("to must be >= from")
    rows = session.exec(
        select(InventoryMovement).where(
            InventoryMovement.created_at >= start,
            InventoryMovement.created_at <= end,
        )
    ).all()
    summary: dict[str, dict[str, int]] = {
        factory: {
            "inbound": 0,
            "outbound": 0,
            "transfer_in": 0,
            "transfer_out": 0,
            "net_change": 0,
        }
        for factory in FACTORIES
    }
    transfer_ids: set[str] = set()
    for row in rows:
        factory = (row.factory_id or "").strip().lower()
        if factory not in summary:
            continue
        delta = int(row.quantity_delta)
        movement_type = (row.movement_type or "").strip().lower()
        if movement_type == "inbound":
            summary[factory]["inbound"] += max(delta, 0)
        elif movement_type == "outbound":
            summary[factory]["outbound"] += abs(min(delta, 0))
        elif movement_type == "transfer_in":
            summary[factory]["transfer_in"] += max(delta, 0)
        elif movement_type == "transfer_out":
            summary[factory]["transfer_out"] += abs(min(delta, 0))
        summary[factory]["net_change"] += delta
        if row.transfer_id:
            transfer_ids.add(row.transfer_id)
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "factories": [{"factory_id": factory, **summary[factory]} for factory in FACTORIES],
        "transfers": {
            "count": len(transfer_ids),
        },
    }
