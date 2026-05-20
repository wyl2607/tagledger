from __future__ import annotations

import json

from sqlmodel import Session, select

from backend.app.models import AuditLog, InventoryMovement, User


def _transfer_request_signature(
    *,
    source_factory: str,
    target_factory: str,
    part_key: str,
    quantity: int,
    reason: str,
) -> str:
    return json.dumps(
        {
            "source_factory": source_factory,
            "target_factory": target_factory,
            "part_key": part_key,
            "quantity": quantity,
            "reason": reason,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _find_existing_transfer_id(
    session: Session,
    *,
    operator: User,
    idempotency_key: str,
    request_signature: str,
) -> str | None:
    rows = session.exec(
        select(AuditLog)
        .where(
            AuditLog.action == "inventory.transfer",
            AuditLog.actor_username == operator.username,
            AuditLog.success == True,  # noqa: E712
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(200)
    ).all()
    for row in rows:
        try:
            detail = json.loads(row.detail_json or "{}")
        except json.JSONDecodeError:
            continue
        if detail.get("idempotency_key") == idempotency_key:
            if detail.get("request_signature") != request_signature:
                raise RuntimeError("idempotency_key reused with different transfer payload")
            transfer_id = str(detail.get("transfer_id") or row.target_id or "")
            return transfer_id or None
    return None


def _transfer_payload_from_existing(
    *,
    session: Session,
    transfer_id: str,
) -> dict[str, object] | None:
    movements = session.exec(
        select(InventoryMovement)
        .where(InventoryMovement.transfer_id == transfer_id)
        .order_by(InventoryMovement.movement_type.desc(), InventoryMovement.id.asc())
    ).all()
    if len(movements) < 2:
        return None
    out_movement = next((row for row in movements if row.movement_type == "transfer_out"), None)
    in_movement = next((row for row in movements if row.movement_type == "transfer_in"), None)
    if out_movement is None or in_movement is None:
        return None
    return {
        "created": False,
        "transfer_id": transfer_id,
        "source_factory": out_movement.factory_id,
        "target_factory": in_movement.factory_id,
        "part_key": out_movement.part_key,
        "quantity": abs(int(out_movement.quantity_delta)),
        "source_location": {
            "factory_id": out_movement.factory_id,
            "location_code": out_movement.location_code,
            "quantity": int(out_movement.after_qty),
            "status": None,
        },
        "target_location": {
            "factory_id": in_movement.factory_id,
            "location_code": in_movement.location_code,
            "quantity": int(in_movement.after_qty),
            "status": None,
        },
        "movements": [
            {
                "id": row.id,
                "factory_id": row.factory_id,
                "movement_type": row.movement_type,
                "part_key": row.part_key,
                "location_code": row.location_code,
                "transfer_id": row.transfer_id,
                "quantity_delta": row.quantity_delta,
                "before_qty": row.before_qty,
                "after_qty": row.after_qty,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in (out_movement, in_movement)
        ],
        "audit_log_id": None,
    }
