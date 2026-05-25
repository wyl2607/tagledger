from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlmodel import Session, select

from backend.app.models import AuditLog, InventoryLocation, InventoryMovement, User

from .normalize import (
    apply_location_visibility_rules,
    movement_payload,
    normalize_factory_id,
    normalize_location_code,
    normalize_part_key,
    normalize_reason,
)


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
