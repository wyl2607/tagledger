import csv
import json
import socket
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, func, select

from backend.app.config import get_settings
from backend.app.models import (
    AuditLog,
    InventoryMovement,
    OutboundProgressSnapshot,
    OutboundScan,
    Record,
    User,
)

from ._helpers import (
    _active_scan_summary,
    _is_same_batch_scope,
    _manual_source_code,
    _normalize_location_code,
    _scan_counts,
    _scan_to_payload,
    _scan_total,
    _today_part_remaining,
)
from .inventory import (
    _bootstrap_inventory_if_missing,
    _get_or_create_inventory_location,
    _select_location_for_outbound,
    inbound_inventory,
    outbound_inventory,
)
from .normalize import (
    compact_part_code,
    normalize_order_no,
    parse_outbound_completion_marks,
)
from .query import (
    _order_numbers,
    _order_required_rows,
)


def _snapshot_to_payload(snapshot: OutboundProgressSnapshot) -> dict[str, object]:
    detail = json.loads(snapshot.detail_json) if snapshot.detail_json else {}
    detail.pop("source_code", None)
    return {
        "id": snapshot.id,
        "order_no": snapshot.order_no,
        "event": snapshot.event,
        "required_total": snapshot.required_total,
        "scanned_total": snapshot.scanned_total,
        "remaining_total": snapshot.remaining_total,
        "line_total": snapshot.line_total,
        "complete_line_total": snapshot.complete_line_total,
        "active_scan_count": snapshot.active_scan_count,
        "active_scan_quantity": snapshot.active_scan_quantity,
        "operator_id": snapshot.operator_id,
        "batch_id": snapshot.batch_id,
        "scan_id": snapshot.scan_id,
        "completed_at": snapshot.completed_at.isoformat() if snapshot.completed_at else None,
        "detail": detail,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


def save_outbound_progress_snapshot(
    *,
    order_no: str,
    event: str,
    operator_id: str,
    session: Session,
    status: dict[str, object] | None = None,
    scan_id: int | None = None,
    batch_id: str | None = None,
    detail: dict[str, object] | None = None,
    completed_at: datetime | None = None,
) -> OutboundProgressSnapshot:
    selected_order = normalize_order_no(order_no)
    status = status or outbound_order_status(selected_order, session)
    active_count, active_quantity = _active_scan_summary(session, selected_order)
    snapshot = OutboundProgressSnapshot(
        order_no=selected_order,
        event=event[:80],
        required_total=int(status.get("required_total") or 0),
        scanned_total=int(status.get("scanned_total") or 0),
        remaining_total=int(status.get("remaining_total") or 0),
        line_total=int(status.get("line_total") or 0),
        complete_line_total=int(status.get("complete_line_total") or 0),
        active_scan_count=active_count,
        active_scan_quantity=active_quantity,
        operator_id=(operator_id.strip() or "self")[:80],
        batch_id=(batch_id or "")[:120] or None,
        scan_id=scan_id,
        completed_at=completed_at,
        detail_json=json.dumps(detail or {}, ensure_ascii=False, default=str),
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def _safe_csv_cell(value: object) -> str:
    text = str(value or "")
    if text and text[0] in {"=", "+", "-", "@", "\t", "\r", "\n"}:
        return f"'{text}"
    return text


def _public_path(path: Path) -> str:
    return path.name


def outbound_order_status(
    order_no: str,
    session: Session,
    *,
    include_today_remaining: bool = True,
) -> dict[str, object]:
    selected_order = normalize_order_no(order_no)
    required_rows = _order_required_rows(selected_order)
    scan_counts = _scan_counts(session, selected_order)
    today_remaining = (
        _today_part_remaining(session) if include_today_remaining and required_rows else {}
    )
    rows = []
    for key, row in sorted(required_rows.items(), key=lambda item: str(item[1]["part_code"])):
        required_qty = int(row["required_qty"])
        scanned_qty = scan_counts.get(key, 0)
        remaining_qty = None if row["unknown_quantity"] else max(required_qty - scanned_qty, 0)
        over_scanned_qty = 0 if row["unknown_quantity"] else max(scanned_qty - required_qty, 0)
        rows.append(
            {
                **row,
                "part_key": key,
                "scanned_qty": scanned_qty,
                "remaining_qty": remaining_qty,
                "over_scanned_qty": over_scanned_qty,
                "today_remaining_qty": today_remaining.get(key, remaining_qty or 0),
                "is_complete": not row["unknown_quantity"] and scanned_qty >= required_qty,
            }
        )
    required_total = sum(int(row["required_qty"]) for row in required_rows.values())
    scanned_total = sum(scan_counts.get(key, 0) for key in required_rows)
    over_scanned_total = sum(int(row["over_scanned_qty"]) for row in rows)
    extra_scanned_total = (
        max(_scan_total(session, selected_order) - scanned_total, 0) + over_scanned_total
    )
    complete_line_total = sum(1 for row in rows if row["is_complete"])
    return {
        "order_no": selected_order,
        "required_total": required_total,
        "scanned_total": scanned_total,
        "extra_scanned_total": extra_scanned_total,
        "remaining_total": max(required_total - scanned_total, 0),
        "line_total": len(rows),
        "complete_line_total": complete_line_total,
        "is_complete": bool(rows) and complete_line_total == len(rows),
        "rows": rows,
    }


def outbound_orders_status(session: Session) -> dict[str, object]:
    orders = [
        outbound_order_status(order_no, session, include_today_remaining=False)
        for order_no in _order_numbers()
    ]
    today_remaining: dict[str, int] = defaultdict(int)
    for order in orders:
        for row in order["rows"]:
            today_remaining[str(row["part_key"])] += int(row.get("remaining_qty") or 0)
    for order in orders:
        for row in order["rows"]:
            row["today_remaining_qty"] = today_remaining.get(str(row["part_key"]), 0)
    complete_order_count = sum(1 for order in orders if order["is_complete"])
    return {
        "orders": orders,
        "totals": {
            "order_count": len(orders),
            "complete_order_count": complete_order_count,
            "open_order_count": len(orders) - complete_order_count,
            "required_total": sum(int(order["required_total"]) for order in orders),
            "scanned_total": sum(int(order["scanned_total"]) for order in orders),
            "remaining_total": sum(int(order["remaining_total"]) for order in orders),
            "extra_scanned_total": sum(int(order["extra_scanned_total"]) for order in orders),
        },
    }


def outbound_orders_overview(session: Session) -> dict[str, object]:
    status = outbound_orders_status(session)
    return {
        "orders": [
            {key: value for key, value in order.items() if key != "rows"}
            for order in status["orders"]
        ],
        "totals": status["totals"],
    }


def outbound_progress_snapshots(
    order_no: str | None,
    session: Session,
    *,
    limit: int = 100,
) -> dict[str, object]:
    statement = select(OutboundProgressSnapshot).order_by(
        OutboundProgressSnapshot.created_at.desc(),
        OutboundProgressSnapshot.id.desc(),
    )
    selected_order = normalize_order_no(order_no) if order_no else ""
    if selected_order:
        statement = statement.where(OutboundProgressSnapshot.order_no == selected_order)
    snapshots = session.exec(statement.limit(max(1, min(limit, 500)))).all()
    return {
        "order_no": selected_order or None,
        "snapshots": [_snapshot_to_payload(snapshot) for snapshot in snapshots],
    }


def outbound_remaining_csv(order_no: str, session: Session) -> str:
    status = outbound_order_status(order_no, session)
    buffer = StringIO()
    fields = [
        "order_no",
        "part_code",
        "name",
        "locations",
        "required_qty",
        "scanned_qty",
        "remaining_qty",
        "today_remaining_qty",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for row in status["rows"]:
        if int(row.get("remaining_qty") or 0) <= 0:
            continue
        writer.writerow(
            {
                "order_no": status["order_no"],
                "part_code": _safe_csv_cell(row["part_code"]),
                "name": _safe_csv_cell(row.get("name") or ""),
                "locations": _safe_csv_cell(
                    ";".join(str(location) for location in row.get("locations", []))
                ),
                "required_qty": row["required_qty"],
                "scanned_qty": row["scanned_qty"],
                "remaining_qty": row["remaining_qty"],
                "today_remaining_qty": row["today_remaining_qty"],
            }
        )
    return buffer.getvalue()


def outbound_batch_detail(order_no: str, batch_id: str, session: Session) -> dict[str, object]:
    selected_order = normalize_order_no(order_no)
    batch_id = batch_id.strip()
    if not batch_id:
        raise RuntimeError("batch_id is required")
    scans = session.exec(
        select(OutboundScan)
        .where(OutboundScan.order_no == selected_order, OutboundScan.batch_id == batch_id)
        .order_by(OutboundScan.created_at.desc(), OutboundScan.id.desc())
    ).all()
    if not scans:
        raise RuntimeError(f"outbound batch not found: {selected_order} {batch_id}")
    affected: dict[str, dict[str, object]] = {}
    for scan in scans:
        row = affected.setdefault(
            scan.part_code,
            {
                "part_key": scan.part_code,
                "matched_code": scan.matched_code,
                "active_quantity": 0,
                "voided_quantity": 0,
                "active_scan_count": 0,
                "voided_scan_count": 0,
            },
        )
        if scan.status == "active":
            row["active_quantity"] = int(row["active_quantity"]) + scan.quantity
            row["active_scan_count"] = int(row["active_scan_count"]) + 1
        else:
            row["voided_quantity"] = int(row["voided_quantity"]) + scan.quantity
            row["voided_scan_count"] = int(row["voided_scan_count"]) + 1
    active_scans = [scan for scan in scans if scan.status == "active"]
    active_quantity = sum(scan.quantity for scan in active_scans)
    status = outbound_order_status(selected_order, session)
    preview_status = {
        "scanned_total": max(int(status["scanned_total"]) - active_quantity, 0),
        "remaining_total": int(status["remaining_total"]) + active_quantity,
        "affected_quantity": active_quantity,
    }
    return {
        "order_no": selected_order,
        "batch_id": batch_id,
        "scan_count": len(scans),
        "active_scan_count": len(active_scans),
        "voided_scan_count": len(scans) - len(active_scans),
        "active_quantity": active_quantity,
        "voided_quantity": sum(scan.quantity for scan in scans if scan.status != "active"),
        "affected_parts": sorted(affected.values(), key=lambda item: str(item["part_key"])),
        "current_status": {key: value for key, value in status.items() if key != "rows"},
        "preview_status": preview_status,
    }


def outbound_ops_health(session: Session) -> dict[str, object]:
    settings = get_settings()
    is_sqlite = session.get_bind().dialect.name == "sqlite"
    if is_sqlite:
        db_quick_check_row = session.exec(text("PRAGMA quick_check")).one()
        if isinstance(db_quick_check_row, tuple):
            db_quick_check_value = db_quick_check_row[0]
        elif hasattr(db_quick_check_row, "_mapping"):
            db_quick_check_value = next(iter(db_quick_check_row._mapping.values()))
        else:
            db_quick_check_value = db_quick_check_row
        db_quick_check = str(db_quick_check_value)
    else:
        # PostgreSQL does not support PRAGMA; validate connectivity with a cheap heartbeat.
        heartbeat = session.exec(text("SELECT 1")).one()
        if isinstance(heartbeat, tuple):
            heartbeat_value = heartbeat[0]
        elif hasattr(heartbeat, "_mapping"):
            heartbeat_value = next(iter(heartbeat._mapping.values()))
        else:
            heartbeat_value = heartbeat
        db_quick_check = "ok" if int(heartbeat_value) == 1 else "degraded"

    if is_sqlite:
        database_file = _public_path(settings.database_path)
        backup_dir = settings.database_path.parent / "backups"
        backup_globs = ["*.db"]
        database_kind = "sqlite"
    else:
        database_file = "postgresql://***"
        backup_dir = Path(__file__).resolve().parents[3] / "data" / "backups"
        backup_globs = ["*.dump", "*.backup"]
        database_kind = "postgresql"
    backups: list[Path] = []
    for pattern in backup_globs:
        backups.extend(backup_dir.glob(pattern))
    backups = sorted(backups, key=lambda path: path.stat().st_mtime, reverse=True)
    latest_backup = backups[0] if backups else None
    scan_rows = session.exec(
        select(
            OutboundScan.status, func.count(OutboundScan.id), func.sum(OutboundScan.quantity)
        ).group_by(OutboundScan.status)
    ).all()
    snapshot_count = int(session.exec(select(func.count(OutboundProgressSnapshot.id))).one() or 0)
    error_records = session.exec(
        select(Record)
        .where(Record.last_error.is_not(None))
        .order_by(Record.updated_at.desc(), Record.id.desc())
        .limit(5)
    ).all()
    try:
        outbound_overview = outbound_orders_overview(session)
        default_order = outbound_order_status("SO202604210135", session)
    except RuntimeError as exc:
        outbound_overview = {"error": str(exc)}
        default_order = {"error": str(exc)}
    return {
        "status": "ok" if db_quick_check == "ok" else "degraded",
        "database": {
            "kind": database_kind,
            "file": database_file,
            "quick_check": db_quick_check,
        },
        "runtime": {
            "ocr_provider": settings.ocr_provider,
            "enable_barcode": settings.enable_barcode,
            "enable_saas_submit": settings.enable_saas_submit,
            "dry_run": settings.dry_run,
            "host_name": socket.gethostname().split(".")[0],
        },
        "backups": {
            "count": len(backups),
            "latest": None
            if latest_backup is None
            else {
                "file": _public_path(latest_backup),
                "size_bytes": latest_backup.stat().st_size,
                "modified_at": datetime.fromtimestamp(
                    latest_backup.stat().st_mtime, UTC
                ).isoformat(),
            },
        },
        "outbound": {
            "totals": outbound_overview.get("totals", {})
            if isinstance(outbound_overview, dict)
            else {},
            "default_order": {key: value for key, value in default_order.items() if key != "rows"}
            if isinstance(default_order, dict)
            else {},
            "scan_status": {
                str(status): {"count": int(count or 0), "quantity": int(quantity or 0)}
                for status, count, quantity in scan_rows
            },
            "snapshot_count": snapshot_count,
        },
        "recent_errors": [
            {
                "id": record.id,
                "status": record.status,
                "has_error": bool(record.last_error),
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            }
            for record in error_records
        ],
    }


def void_outbound_batch(
    *,
    order_no: str,
    batch_id: str,
    operator_id: str,
    session: Session,
) -> dict[str, object]:
    selected_order = normalize_order_no(order_no)
    batch_id = batch_id.strip()
    if not batch_id:
        raise RuntimeError("batch_id is required")
    scans = session.exec(
        select(OutboundScan).where(
            OutboundScan.order_no == selected_order,
            OutboundScan.batch_id == batch_id,
            OutboundScan.status == "active",
        )
    ).all()
    if not scans:
        raise RuntimeError(f"active outbound batch not found: {selected_order} {batch_id}")
    now = datetime.now(UTC)
    for scan in scans:
        if scan.location_code:
            try:
                inbound_inventory(
                    part_key=scan.part_code,
                    location_code=scan.location_code,
                    quantity=scan.quantity,
                    operator_id=operator_id,
                    reason="void_outbound_batch_revert",
                    session=session,
                )
            except RuntimeError:
                pass
        scan.status = "voided"
        scan.void_reason = "batch_void"
        scan.voided_by = (operator_id.strip() or "self")[:80]
        scan.voided_at = now
        session.add(scan)
    session.commit()
    status = outbound_order_status(selected_order, session)
    snapshot = save_outbound_progress_snapshot(
        order_no=selected_order,
        event="batch_voided",
        operator_id=operator_id,
        session=session,
        status=status,
        batch_id=batch_id,
        detail={
            "batch_id": batch_id,
            "voided_scan_ids": [scan.id for scan in scans],
            "voided_quantity": sum(scan.quantity for scan in scans),
        },
    )
    return {
        "voided": True,
        "batch_id": batch_id,
        "voided_scan_count": len(scans),
        "voided_quantity": sum(scan.quantity for scan in scans),
        "snapshot": _snapshot_to_payload(snapshot),
        "order_status": status,
    }


def void_outbound_scan(
    *,
    scan_id: int,
    operator_id: str,
    reason: str,
    session: Session,
) -> dict[str, object]:
    scan = session.get(OutboundScan, scan_id)
    if scan is None:
        raise RuntimeError(f"outbound scan not found: {scan_id}")
    if scan.status != "voided":
        scan.status = "voided"
        scan.void_reason = (reason.strip() or "operator_void")[:200]
        scan.voided_by = (operator_id.strip() or "self")[:80]
        scan.voided_at = datetime.now(UTC)
        session.add(scan)
        session.commit()
        session.refresh(scan)
        if scan.location_code:
            try:
                inbound_inventory(
                    part_key=scan.part_code,
                    location_code=scan.location_code,
                    quantity=scan.quantity,
                    operator_id=operator_id,
                    reason="void_outbound_scan_revert",
                    session=session,
                )
            except RuntimeError:
                pass
    status = outbound_order_status(scan.order_no, session)
    snapshot = save_outbound_progress_snapshot(
        order_no=scan.order_no,
        event="scan_voided",
        operator_id=operator_id,
        session=session,
        status=status,
        scan_id=scan.id,
        detail={"part_key": scan.part_code, "quantity": scan.quantity, "reason": reason},
    )
    return {
        "voided": True,
        "scan": _scan_to_payload(scan),
        "snapshot": _snapshot_to_payload(snapshot),
        "order_status": status,
    }


def set_outbound_part_quantity(
    *,
    order_no: str,
    part_key: str,
    quantity: int,
    operator_id: str,
    session: Session,
    reason: str = "manual_set",
    batch_id: str | None = None,
) -> dict[str, object]:
    selected_order = normalize_order_no(order_no)
    normalized_part = compact_part_code(part_key)
    required_rows = _order_required_rows(selected_order)
    matched_row = required_rows.get(normalized_part)
    if matched_row is None:
        raise RuntimeError(f"part not found in order: {selected_order} {part_key}")
    if matched_row["unknown_quantity"]:
        raise RuntimeError(f"part quantity unreadable: {selected_order} {part_key}")
    required_qty = int(matched_row["required_qty"])
    target_qty = max(0, min(int(quantity), required_qty))
    active_scans = session.exec(
        select(OutboundScan).where(
            OutboundScan.order_no == selected_order,
            OutboundScan.part_code == normalized_part,
            OutboundScan.status == "active",
        )
    ).all()
    if batch_id:
        existing = [scan for scan in active_scans if _is_same_batch_scope(scan.batch_id, batch_id)]
        preserved_qty = sum(
            scan.quantity
            for scan in active_scans
            if not _is_same_batch_scope(scan.batch_id, batch_id)
        )
    else:
        existing = active_scans
        preserved_qty = 0
    now = datetime.now(UTC)
    for scan in existing:
        if scan.location_code:
            try:
                inbound_inventory(
                    part_key=normalized_part,
                    location_code=scan.location_code,
                    quantity=scan.quantity,
                    operator_id=operator_id,
                    reason=f"{reason}_void_revert",
                    session=session,
                )
            except RuntimeError:
                pass
        scan.status = "voided"
        scan.void_reason = reason[:200]
        scan.voided_by = (operator_id.strip() or "self")[:80]
        scan.voided_at = now
        session.add(scan)
    scan = None
    new_qty = max(0, target_qty - preserved_qty)
    if new_qty > 0:
        selected_location, available_locations, location_matches = _select_location_for_outbound(
            location_code=None,
            required_row=matched_row,
        )
        if available_locations and not selected_location:
            selected_location = available_locations[0]
            location_matches = True
        if available_locations and not location_matches:
            raise RuntimeError(
                f"invalid location selection for manual quantity update: {normalized_part}"
            )
        if selected_location:
            _bootstrap_inventory_if_missing(
                session,
                part_key=normalized_part,
                location_code=selected_location,
                operator_id=operator_id,
                reason="legacy_bootstrap_from_manual_quantity",
                seed_quantity=max(new_qty, required_qty),
            )
            outbound_inventory(
                part_key=normalized_part,
                location_code=selected_location,
                quantity=new_qty,
                operator_id=operator_id,
                reason=reason,
                session=session,
                order_no=selected_order,
            )
        scan = OutboundScan(
            order_no=selected_order,
            part_code=normalized_part,
            location_code=selected_location,
            source_code=_manual_source_code(normalized_part),
            matched_code=str(matched_row["part_code"]),
            quantity=new_qty,
            status="active",
            operator_id=(operator_id.strip() or "self")[:80],
            batch_id=(batch_id or "")[:120] or None,
            record_id=None,
        )
        session.add(scan)
    session.commit()
    if scan is not None:
        session.refresh(scan)
    status = outbound_order_status(selected_order, session)
    snapshot = save_outbound_progress_snapshot(
        order_no=selected_order,
        event=reason,
        operator_id=operator_id,
        session=session,
        status=status,
        scan_id=scan.id if scan is not None else None,
        batch_id=batch_id,
        detail={
            "part_key": normalized_part,
            "target_quantity": target_qty,
            "new_quantity": new_qty,
            "preserved_quantity": preserved_qty,
            "batch_id": batch_id,
        },
    )
    return {
        "updated": True,
        "target_quantity": target_qty,
        "scan": _scan_to_payload(scan) if scan is not None else None,
        "snapshot": _snapshot_to_payload(snapshot),
        "matched_part": matched_row,
        "order_status": status,
    }


def complete_outbound_order(
    *,
    order_no: str,
    operator_id: str,
    session: Session,
) -> dict[str, object]:
    selected_order = normalize_order_no(order_no)
    required_rows = _order_required_rows(selected_order)
    if not required_rows:
        raise RuntimeError(f"order not found: {selected_order}")
    batch_id = f"complete-{selected_order}-{uuid.uuid4().hex[:12]}"
    for part_key, row in required_rows.items():
        if row["unknown_quantity"]:
            continue
        set_outbound_part_quantity(
            order_no=selected_order,
            part_key=part_key,
            quantity=int(row["required_qty"]),
            operator_id=operator_id,
            session=session,
            reason="complete_order",
            batch_id=batch_id,
        )
    status = outbound_order_status(selected_order, session)
    completed_at = datetime.now(UTC)
    snapshot = save_outbound_progress_snapshot(
        order_no=selected_order,
        event="complete_order_finished",
        operator_id=operator_id,
        session=session,
        status=status,
        batch_id=batch_id,
        completed_at=completed_at,
        detail={"line_total": len(required_rows), "batch_id": batch_id},
    )
    return {
        "completed": True,
        "batch_id": batch_id,
        "snapshot": _snapshot_to_payload(snapshot),
        "order_status": status,
    }


def rollback_outbound_order(
    *,
    order_no: str,
    operator: User,
    session: Session,
) -> dict[str, object]:
    selected_order = normalize_order_no(order_no)
    latest_completion = session.exec(
        select(OutboundProgressSnapshot)
        .where(
            OutboundProgressSnapshot.order_no == selected_order,
            OutboundProgressSnapshot.event == "complete_order_finished",
        )
        .order_by(OutboundProgressSnapshot.created_at.desc(), OutboundProgressSnapshot.id.desc())
    ).first()
    if latest_completion is None:
        raise RuntimeError(f"no completion snapshot found for order: {selected_order}")

    completed_at = latest_completion.completed_at or latest_completion.created_at
    if completed_at is None:
        raise RuntimeError(f"invalid completion snapshot for order: {selected_order}")
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=UTC)
    else:
        completed_at = completed_at.astimezone(UTC)

    now = datetime.now(UTC)
    rollback_window_minutes = max(1, int(get_settings().rollback_window_minutes or 30))
    rollback_deadline = completed_at + timedelta(minutes=rollback_window_minutes)
    if now > rollback_deadline:
        raise RuntimeError(
            f"rollback window expired for order {selected_order}: "
            f"completed_at={completed_at.isoformat()} deadline={rollback_deadline.isoformat()}"
        )

    active_scans = session.exec(
        select(OutboundScan)
        .where(OutboundScan.order_no == selected_order, OutboundScan.status == "active")
        .order_by(OutboundScan.id.asc())
    ).all()
    if not active_scans:
        raise RuntimeError(f"no active scans to rollback for order: {selected_order}")

    now = datetime.now(UTC)
    restored_count = 0
    restored_quantity = 0
    movement_rows: list[InventoryMovement] = []
    for scan in active_scans:
        if scan.location_code:
            normalized_location = _normalize_location_code(scan.location_code)
            location = _get_or_create_inventory_location(
                session,
                part_key=scan.part_code,
                location_code=normalized_location,
            )
            before_qty = int(location.quantity)
            after_qty = before_qty + int(scan.quantity)
            location.quantity = after_qty
            location.zero_stock = after_qty == 0
            if location.zero_stock:
                location.status = "zero_stock"
            elif location.status in {"zero_stock", "retired"}:
                location.status = "active"
            location.updated_at = now
            session.add(location)
            session.flush()

            movement = InventoryMovement(
                movement_type="inbound",
                part_key=scan.part_code,
                location_code=normalized_location,
                order_no=selected_order,
                scan_id=scan.id,
                quantity_delta=int(scan.quantity),
                before_qty=before_qty,
                after_qty=after_qty,
                operator_id=(operator.username or "self")[:80],
                reason="rollback_outbound_order_revert",
            )
            session.add(movement)
            movement_rows.append(movement)
            restored_count += 1
            restored_quantity += int(scan.quantity)

        scan.status = "voided"
        scan.void_reason = "rollback"
        scan.voided_by = (operator.username or "self")[:80]
        scan.voided_at = now
        session.add(scan)
    session.flush()

    status = outbound_order_status(selected_order, session)
    active_count, active_quantity = _active_scan_summary(session, selected_order)
    rollback_snapshot = OutboundProgressSnapshot(
        order_no=selected_order,
        event="rollback_completed",
        required_total=int(status.get("required_total") or 0),
        scanned_total=int(status.get("scanned_total") or 0),
        remaining_total=int(status.get("remaining_total") or 0),
        line_total=int(status.get("line_total") or 0),
        complete_line_total=int(status.get("complete_line_total") or 0),
        active_scan_count=active_count,
        active_scan_quantity=active_quantity,
        operator_id=(operator.username or "self")[:80],
        batch_id=latest_completion.batch_id,
        scan_id=None,
        detail_json=json.dumps(
            {
                "rollback_source_snapshot_id": latest_completion.id,
                "rollback_window_minutes": rollback_window_minutes,
                "voided_scan_ids": [scan.id for scan in active_scans],
                "voided_quantity": sum(int(scan.quantity) for scan in active_scans),
                "restored_inventory_rows": restored_count,
                "restored_inventory_quantity": restored_quantity,
            },
            ensure_ascii=False,
            default=str,
        ),
    )
    session.add(rollback_snapshot)
    session.flush()

    audit = AuditLog(
        event_type="outbound_rollback",
        actor_user_id=operator.id,
        actor_username=operator.username,
        target_type="outbound_order",
        target_id=selected_order,
        action="outbound.rollback",
        reason="supervisor rollback",
        success=True,
        detail_json=json.dumps(
            {
                "order_no": selected_order,
                "rollback_source_snapshot_id": latest_completion.id,
                "voided_scan_count": len(active_scans),
                "voided_quantity": sum(int(scan.quantity) for scan in active_scans),
                "rollback_window_minutes": rollback_window_minutes,
                "completed_at": completed_at.isoformat(),
                "rolled_back_at": now.isoformat(),
            },
            ensure_ascii=False,
            default=str,
        ),
    )
    session.add(audit)
    session.commit()
    session.refresh(rollback_snapshot)
    session.refresh(audit)

    return {
        "rolled_back": True,
        "order_no": selected_order,
        "voided_scan_count": len(active_scans),
        "voided_quantity": sum(int(scan.quantity) for scan in active_scans),
        "restored_inventory_rows": restored_count,
        "restored_inventory_quantity": restored_quantity,
        "rollback_window_minutes": rollback_window_minutes,
        "completed_at": completed_at.isoformat(),
        "rolled_back_at": now.isoformat(),
        "snapshot": _snapshot_to_payload(rollback_snapshot),
        "audit_log_id": audit.id,
        "order_status": status,
    }


def sync_outbound_completion_marks(
    *,
    text: str,
    operator_id: str,
    session: Session,
    order_no: str | None = None,
) -> dict[str, object]:
    marks = parse_outbound_completion_marks(text)
    selected_order = normalize_order_no(order_no) if order_no else ""
    applied = []
    skipped = []
    for mark in marks:
        if selected_order and mark.order_no != selected_order:
            skipped.append({**mark.__dict__, "reason": "outside_selected_order"})
            continue
        part_key = compact_part_code(mark.part_code)
        required_rows = _order_required_rows(mark.order_no)
        row = required_rows.get(part_key)
        if row is None:
            skipped.append({**mark.__dict__, "reason": "part_not_found"})
            continue
        if row["unknown_quantity"]:
            skipped.append({**mark.__dict__, "reason": "quantity_unreadable"})
            continue
        if mark.quantity is not None and mark.quantity != int(row["required_qty"]):
            skipped.append(
                {
                    **mark.__dict__,
                    "reason": "quantity_mismatch",
                    "required_qty": int(row["required_qty"]),
                }
            )
            continue
        result = set_outbound_part_quantity(
            order_no=mark.order_no,
            part_key=part_key,
            quantity=int(row["required_qty"]),
            operator_id=operator_id,
            session=session,
            reason="completion_mark_sync",
            batch_id=f"marks-{selected_order or mark.order_no}",
        )
        applied.append(
            {
                **mark.__dict__,
                "part_key": part_key,
                "target_quantity": result["target_quantity"],
            }
        )
    touched_orders = sorted({mark["order_no"] for mark in applied})
    return {
        "parsed_count": len(marks),
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "applied": applied,
        "skipped": skipped,
        "orders": [outbound_order_status(order_no, session) for order_no in touched_orders],
    }
