from __future__ import annotations

import hashlib
import json
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


class InventoryPermissionError(RuntimeError):
    pass


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


def recommend_inventory_picks(
    *,
    session: Session,
    part_key: str,
    quantity: int,
    factory_id: str | None = None,
) -> dict[str, object]:
    normalized_part = normalize_part_key(part_key)
    normalized_factory = normalize_factory_id(factory_id) if factory_id else None
    requested_quantity = int(quantity)
    if requested_quantity <= 0:
        raise RuntimeError("quantity must be > 0")

    statement = select(InventoryLocation).where(InventoryLocation.part_key == normalized_part)
    if normalized_factory:
        statement = statement.where(InventoryLocation.factory_id == normalized_factory)
    rows = [
        row
        for row in session.exec(statement).all()
        if row.status not in HIDDEN_LOCATION_STATUSES and int(row.quantity or 0) > 0
    ]

    def recommendation_sort_key(location: InventoryLocation) -> tuple[object, ...]:
        kind = normalize_location_kind(location.location_kind)
        profile = location_profile_payload(location.location_code, kind)
        return (
            0 if kind == "temporary" else 1,
            int(location.quantity or 0),
            tuple(profile["sort_key"]),
            location.factory_id,
            location.location_code,
            location.id or 0,
        )

    ordered_rows = sorted(rows, key=recommendation_sort_key)
    total_available = sum(int(row.quantity or 0) for row in ordered_rows)
    remaining = requested_quantity
    recommendations: list[dict[str, object]] = []
    for row in ordered_rows:
        if remaining <= 0:
            break
        available = int(row.quantity or 0)
        pick_quantity = min(available, remaining)
        remaining -= pick_quantity
        payload = location_payload(row)
        recommendations.append(
            {
                **payload,
                "available_quantity": available,
                "pick_quantity": pick_quantity,
            }
        )

    return {
        "factory_id": normalized_factory,
        "part_key": normalized_part,
        "requested_quantity": requested_quantity,
        "total_available": total_available,
        "shortage_quantity": max(remaining, 0),
        "insufficient": remaining > 0,
        "recommendations": recommendations,
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


def preview_inventory_reconcile(
    *,
    session: Session,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    def _normalized_row(raw: dict[str, object]) -> dict[str, object]:
        factory_value = raw.get("factory_id")
        factory_id = normalize_factory_id(str(factory_value)) if factory_value else "factory_a"
        part_key = normalize_part_key(str(raw.get("part_key") or ""))
        location_code = normalize_location_code(str(raw.get("location_code") or ""))
        quantity = int(raw.get("quantity") or 0)
        if quantity < 0:
            raise RuntimeError("quantity must be >= 0")
        return {
            "factory_id": factory_id,
            "part_key": part_key,
            "location_code": location_code,
            "quantity": quantity,
        }

    excel_rows = [_normalized_row(item) for item in rows]
    excel_map: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in excel_rows:
        key = (row["factory_id"], row["part_key"], row["location_code"])
        current = excel_map.get(key)
        if current is None:
            excel_map[key] = {
                "factory_id": row["factory_id"],
                "part_key": row["part_key"],
                "location_code": row["location_code"],
                "excel_quantity": int(row["quantity"]),
            }
        else:
            current["excel_quantity"] = int(current["excel_quantity"]) + int(row["quantity"])

    system_map: dict[tuple[str, str, str], dict[str, object]] = {}
    for location in session.exec(select(InventoryLocation)).all():
        key = (
            str(location.factory_id or "factory_a").strip().lower() or "factory_a",
            normalize_part_key(str(location.part_key or "")),
            normalize_location_code(str(location.location_code or "")),
        )
        current = system_map.get(key)
        if current is None:
            system_map[key] = {
                "factory_id": key[0],
                "part_key": key[1],
                "location_code": key[2],
                "system_quantity": int(location.quantity or 0),
            }
        else:
            current["system_quantity"] = int(current["system_quantity"]) + int(
                location.quantity or 0
            )

    matched: list[dict[str, object]] = []
    quantity_mismatch: list[dict[str, object]] = []
    excel_missing: list[dict[str, object]] = []
    excel_new: list[dict[str, object]] = []

    all_keys = sorted(set(system_map) | set(excel_map))
    for key in all_keys:
        system_item = system_map.get(key)
        excel_item = excel_map.get(key)
        if system_item and excel_item:
            system_quantity = int(system_item["system_quantity"])
            excel_quantity = int(excel_item["excel_quantity"])
            base = {
                "factory_id": key[0],
                "part_key": key[1],
                "location_code": key[2],
                "system_quantity": system_quantity,
                "excel_quantity": excel_quantity,
            }
            if system_quantity == excel_quantity:
                matched.append(base)
            else:
                quantity_mismatch.append(
                    {
                        **base,
                        "delta": excel_quantity - system_quantity,
                    }
                )
            continue
        if system_item:
            excel_missing.append(
                {
                    "factory_id": key[0],
                    "part_key": key[1],
                    "location_code": key[2],
                    "system_quantity": int(system_item["system_quantity"]),
                }
            )
            continue
        excel_new.append(
            {
                "factory_id": key[0],
                "part_key": key[1],
                "location_code": key[2],
                "excel_quantity": int(excel_item["excel_quantity"]),
            }
        )

    return {
        "matched": matched,
        "quantity_mismatch": quantity_mismatch,
        "excel_missing": excel_missing,
        "excel_new": excel_new,
        "summary": {
            "matched_count": len(matched),
            "quantity_mismatch_count": len(quantity_mismatch),
            "excel_missing_count": len(excel_missing),
            "excel_new_count": len(excel_new),
        },
    }


def _reconcile_audit_detail(
    *,
    category: str,
    decision: str,
    idempotency_key: str,
    source_filename: str | None,
    part_key: str,
    location_code: str,
    status: str,
    system_quantity: int | None = None,
    excel_quantity: int | None = None,
    before_qty: int | None = None,
    after_qty: int | None = None,
) -> str:
    return json.dumps(
        {
            "category": category,
            "decision": decision,
            "idempotency_key": idempotency_key,
            "source_filename": source_filename,
            "part_key": part_key,
            "location_code": location_code,
            "status": status,
            "system_quantity": system_quantity,
            "excel_quantity": excel_quantity,
            "before_qty": before_qty,
            "after_qty": after_qty,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _find_reconcile_location(
    *,
    session: Session,
    factory_id: str,
    part_key: str,
    location_code: str,
) -> InventoryLocation | None:
    return session.exec(
        select(InventoryLocation).where(
            InventoryLocation.factory_id == factory_id,
            InventoryLocation.part_key == part_key,
            InventoryLocation.location_code == location_code,
        )
    ).first()


def _reconcile_item_key(
    *,
    idempotency_key: str,
    category: str,
    decision: str,
    factory_id: str,
    part_key: str,
    location_code: str,
) -> str:
    raw_key = "|".join([idempotency_key, category, decision, factory_id, part_key, location_code])
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
    return f"reconcile:{digest}"


def _reject_duplicate_reconcile_apply(
    *,
    session: Session,
    item_key: str,
) -> None:
    existing_audit = session.exec(
        select(AuditLog).where(
            AuditLog.action == "inventory.reconcile.apply",
            AuditLog.target_id == item_key,
        )
    ).first()
    if existing_audit is not None:
        raise RuntimeError("duplicate reconcile apply request")


def apply_inventory_reconcile(
    *,
    session: Session,
    decisions: list[dict[str, object]],
    idempotency_key: str,
    source_filename: str | None,
    reason: str,
    operator: User,
) -> dict[str, object]:
    normalized_reason = normalize_reason(reason)
    normalized_idempotency_key = normalize_reason(idempotency_key)
    source_label = (source_filename or "manual").strip()[:120] or "manual"
    now = datetime.now(UTC)
    results: list[dict[str, object]] = []
    applied_count = 0
    audit_only_count = 0
    skipped_count = 0

    for raw in decisions:
        category = str(raw.get("category") or "").strip()
        decision = str(raw.get("decision") or "").strip()
        factory_value = raw.get("factory_id")
        factory_id = normalize_factory_id(str(factory_value)) if factory_value else "factory_a"
        part_key = normalize_part_key(str(raw.get("part_key") or ""))
        location_code = normalize_location_code(str(raw.get("location_code") or ""))
        system_quantity = (
            int(raw["system_quantity"]) if raw.get("system_quantity") is not None else None
        )
        excel_quantity = (
            int(raw["excel_quantity"]) if raw.get("excel_quantity") is not None else None
        )

        result_base = {
            "category": category,
            "decision": decision,
            "factory_id": factory_id,
            "part_key": part_key,
            "location_code": location_code,
            "system_quantity": system_quantity,
            "excel_quantity": excel_quantity,
        }
        item_key = _reconcile_item_key(
            idempotency_key=normalized_idempotency_key,
            category=category,
            decision=decision,
            factory_id=factory_id,
            part_key=part_key,
            location_code=location_code,
        )
        _reject_duplicate_reconcile_apply(session=session, item_key=item_key)

        if category == "matched":
            if decision not in {"noop", "keep_system"}:
                raise RuntimeError(f"unsupported matched decision: {decision}")
            skipped_count += 1
            status = "skipped"
            audit = AuditLog(
                factory_id=factory_id,
                event_type="inventory_reconcile",
                actor_user_id=operator.id,
                actor_username=operator.username,
                target_type="inventory_reconcile",
                target_id=item_key,
                action="inventory.reconcile.apply",
                reason=normalized_reason,
                success=True,
                detail_json=_reconcile_audit_detail(
                    category=category,
                    decision=decision,
                    idempotency_key=normalized_idempotency_key,
                    source_filename=source_label,
                    part_key=part_key,
                    location_code=location_code,
                    status=status,
                    system_quantity=system_quantity,
                    excel_quantity=excel_quantity,
                ),
                created_at=now,
            )
            session.add(audit)
            results.append({**result_base, "status": status})
            continue

        if category == "quantity_mismatch":
            if decision == "use_excel":
                if excel_quantity is None:
                    raise RuntimeError("excel_quantity is required for use_excel")
                if system_quantity is None:
                    raise RuntimeError("system_quantity is required for use_excel")
                if excel_quantity < 0:
                    raise RuntimeError("excel_quantity must be >= 0")
                location = _find_reconcile_location(
                    session=session,
                    factory_id=factory_id,
                    part_key=part_key,
                    location_code=location_code,
                )
                if location is None:
                    raise RuntimeError("inventory location not found")
                before_qty = int(location.quantity or 0)
                if system_quantity is not None and before_qty != system_quantity:
                    raise RuntimeError("system quantity changed since preview")
                location.quantity = excel_quantity
                apply_location_visibility_rules(location)
                location.updated_at = now
                movement = InventoryMovement(
                    factory_id=factory_id,
                    movement_type="reconcile_adjust",
                    part_key=part_key,
                    location_code=location_code,
                    quantity_delta=excel_quantity - before_qty,
                    before_qty=before_qty,
                    after_qty=excel_quantity,
                    operator_id=operator.username,
                    idempotency_key=item_key,
                    reason=f"{normalized_reason}; source={source_label}"[:200],
                    created_at=now,
                )
                audit = AuditLog(
                    factory_id=factory_id,
                    event_type="inventory_reconcile",
                    actor_user_id=operator.id,
                    actor_username=operator.username,
                    target_type="inventory_reconcile",
                    target_id=item_key,
                    action="inventory.reconcile.apply",
                    reason=normalized_reason,
                    success=True,
                    detail_json=_reconcile_audit_detail(
                        category=category,
                        decision=decision,
                        idempotency_key=normalized_idempotency_key,
                        source_filename=source_label,
                        part_key=part_key,
                        location_code=location_code,
                        status="applied",
                        system_quantity=system_quantity,
                        excel_quantity=excel_quantity,
                        before_qty=before_qty,
                        after_qty=excel_quantity,
                    ),
                    created_at=now,
                )
                session.add(location)
                session.add(movement)
                session.add(audit)
                session.flush()
                applied_count += 1
                results.append(
                    {
                        **result_base,
                        "status": "applied",
                        "before_qty": before_qty,
                        "after_qty": excel_quantity,
                        "movement": movement_payload(movement),
                    }
                )
                continue
            if decision not in {"keep_system", "count_review"}:
                raise RuntimeError(f"unsupported quantity_mismatch decision: {decision}")
        elif category == "excel_missing":
            if decision != "mark_excel_missing":
                raise RuntimeError(f"unsupported excel_missing decision: {decision}")
        elif category == "excel_new":
            if decision != "mark_excel_new":
                raise RuntimeError(f"unsupported excel_new decision: {decision}")
        else:
            raise RuntimeError(f"unsupported reconcile category: {category}")

        audit_only_count += 1
        audit = AuditLog(
            factory_id=factory_id,
            event_type="inventory_reconcile",
            actor_user_id=operator.id,
            actor_username=operator.username,
            target_type="inventory_reconcile",
            target_id=item_key,
            action="inventory.reconcile.apply",
            reason=normalized_reason,
            success=True,
            detail_json=_reconcile_audit_detail(
                category=category,
                decision=decision,
                idempotency_key=normalized_idempotency_key,
                source_filename=source_label,
                part_key=part_key,
                location_code=location_code,
                status="audit_only",
                system_quantity=system_quantity,
                excel_quantity=excel_quantity,
            ),
            created_at=now,
        )
        session.add(audit)
        results.append({**result_base, "status": "audit_only"})

    session.commit()
    return {
        "source_filename": source_label,
        "results": results,
        "summary": {
            "applied_count": applied_count,
            "audit_only_count": audit_only_count,
            "skipped_count": skipped_count,
        },
    }
