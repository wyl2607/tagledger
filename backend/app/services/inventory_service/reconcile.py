from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlmodel import Session, select

from backend.app.models import (
    AuditLog,
    InventoryLocation,
    InventoryMovement,
    InventoryReconcileSnapshot,
    InventoryReconcileSnapshotItem,
    User,
)

from .normalize import (
    apply_location_visibility_rules,
    movement_payload,
    normalize_factory_id,
    normalize_location_code,
    normalize_part_key,
    normalize_reason,
)

RECONCILE_CATEGORIES = ("matched", "quantity_mismatch", "excel_missing", "excel_new")


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


def inventory_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _snapshot_payload(
    snapshot: InventoryReconcileSnapshot,
    *,
    recorded: bool,
    duplicate: bool,
) -> dict[str, object]:
    return {
        "id": snapshot.id,
        "recorded": recorded,
        "duplicate": duplicate,
        "filename": snapshot.filename,
        "file_hash": snapshot.file_hash,
        "uploaded_by": snapshot.uploaded_by,
        "parsed_row_count": snapshot.parsed_row_count,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "summary": json.loads(snapshot.summary_json or "{}"),
    }


def _snapshot_item_payload(
    item: InventoryReconcileSnapshotItem,
    snapshot: InventoryReconcileSnapshot,
) -> dict[str, object]:
    return {
        "found": True,
        "snapshot_id": snapshot.id,
        "filename": snapshot.filename,
        "file_hash": snapshot.file_hash,
        "uploaded_by": snapshot.uploaded_by,
        "parsed_row_count": snapshot.parsed_row_count,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        "factory_id": item.factory_id,
        "part_key": item.part_key,
        "location_code": item.location_code,
        "system_quantity": item.system_quantity,
        "excel_quantity": item.excel_quantity,
        "category": item.category,
        "processing_status": item.processing_status,
    }


def _iter_reconcile_snapshot_items(
    preview_result: dict[str, object],
) -> list[tuple[str, dict[str, object]]]:
    items: list[tuple[str, dict[str, object]]] = []
    for category in RECONCILE_CATEGORIES:
        for row in preview_result.get(category) or []:
            if isinstance(row, dict):
                items.append((category, row))
    return items


def record_inventory_reconcile_snapshot(
    *,
    session: Session,
    filename: str,
    file_hash: str,
    parsed_row_count: int,
    preview_result: dict[str, object],
    operator: User,
) -> dict[str, object]:
    existing = session.exec(
        select(InventoryReconcileSnapshot).where(InventoryReconcileSnapshot.file_hash == file_hash)
    ).first()
    if existing is not None:
        return _snapshot_payload(existing, recorded=False, duplicate=True)

    source_filename = (filename or "inventory-snapshot").strip()[:240] or "inventory-snapshot"
    now = datetime.now(UTC)
    summary = (
        preview_result.get("summary") if isinstance(preview_result.get("summary"), dict) else {}
    )
    snapshot = InventoryReconcileSnapshot(
        filename=source_filename,
        file_hash=file_hash,
        uploaded_by=operator.username,
        uploaded_by_user_id=operator.id,
        parsed_row_count=int(parsed_row_count),
        summary_json=json.dumps(summary, ensure_ascii=False, sort_keys=True),
        created_at=now,
    )
    session.add(snapshot)
    session.flush()

    for category, row in _iter_reconcile_snapshot_items(preview_result):
        processing_status = "matched" if category == "matched" else "open"
        item = InventoryReconcileSnapshotItem(
            snapshot_id=snapshot.id or 0,
            factory_id=str(row.get("factory_id") or "factory_a"),
            part_key=str(row.get("part_key") or ""),
            location_code=str(row.get("location_code") or ""),
            system_quantity=(
                int(row["system_quantity"]) if row.get("system_quantity") is not None else None
            ),
            excel_quantity=(
                int(row["excel_quantity"]) if row.get("excel_quantity") is not None else None
            ),
            category=category,
            processing_status=processing_status,
            created_at=now,
        )
        session.add(item)

    session.commit()
    session.refresh(snapshot)
    return _snapshot_payload(snapshot, recorded=True, duplicate=False)


def latest_inventory_reconcile_snapshot_item(
    *,
    session: Session,
    factory_id: str | None,
    part_key: str,
    location_code: str,
) -> dict[str, object]:
    normalized_factory = normalize_factory_id(factory_id) if factory_id else "factory_a"
    normalized_part = normalize_part_key(part_key)
    normalized_location = normalize_location_code(location_code)
    item = session.exec(
        select(InventoryReconcileSnapshotItem)
        .where(
            InventoryReconcileSnapshotItem.factory_id == normalized_factory,
            InventoryReconcileSnapshotItem.part_key == normalized_part,
            InventoryReconcileSnapshotItem.location_code == normalized_location,
        )
        .order_by(InventoryReconcileSnapshotItem.id.desc())
    ).first()
    if item is None:
        return {
            "found": False,
            "factory_id": normalized_factory,
            "part_key": normalized_part,
            "location_code": normalized_location,
        }
    snapshot = session.get(InventoryReconcileSnapshot, item.snapshot_id)
    if snapshot is None:
        return {
            "found": False,
            "factory_id": normalized_factory,
            "part_key": normalized_part,
            "location_code": normalized_location,
        }
    return _snapshot_item_payload(item, snapshot)


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
    rows = session.exec(
        select(InventoryLocation).where(
            InventoryLocation.factory_id == factory_id,
            InventoryLocation.part_key == part_key,
            InventoryLocation.location_code == location_code,
        )
    ).all()
    if len(rows) > 1:
        raise RuntimeError("duplicate inventory locations for reconcile key")
    return rows[0] if rows else None


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
