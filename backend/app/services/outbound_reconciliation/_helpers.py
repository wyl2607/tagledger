from collections import defaultdict

from sqlmodel import Session, func, select

from backend.app.models import (
    OutboundScan,
)

from .normalize import (
    PART_CODE_RE,
    compact_part_code,
    normalize_order_no,
    normalize_part_code,
)
from .query import _order_numbers


def _today_part_remaining(session: Session) -> dict[str, int]:
    from .orders import outbound_order_status

    orders = [
        outbound_order_status(order_no, session, include_today_remaining=False)
        for order_no in _order_numbers()
    ]
    totals: dict[str, int] = defaultdict(int)
    for order in orders:
        for row in order["rows"]:
            totals[str(row["part_key"])] += int(row.get("remaining_qty") or 0)
    return dict(totals)


def _scan_counts(session: Session, order_no: str) -> dict[str, int]:
    selected_order = normalize_order_no(order_no)
    statement = (
        select(OutboundScan.part_code, func.sum(OutboundScan.quantity))
        .where(OutboundScan.order_no == selected_order, OutboundScan.status == "active")
        .group_by(OutboundScan.part_code)
    )
    return {
        str(part_code): int(quantity or 0) for part_code, quantity in session.exec(statement).all()
    }


def _scan_total(session: Session, order_no: str) -> int:
    selected_order = normalize_order_no(order_no)
    statement = select(func.sum(OutboundScan.quantity)).where(
        OutboundScan.order_no == selected_order,
        OutboundScan.status == "active",
    )
    return int(session.exec(statement).one() or 0)


def _active_scan_summary(session: Session, order_no: str) -> tuple[int, int]:
    selected_order = normalize_order_no(order_no)
    statement = select(func.count(OutboundScan.id), func.sum(OutboundScan.quantity)).where(
        OutboundScan.order_no == selected_order,
        OutboundScan.status == "active",
    )
    count, quantity = session.exec(statement).one()
    return int(count or 0), int(quantity or 0)


def _is_same_batch_scope(scan_batch_id: str | None, batch_id: str | None) -> bool:
    current = (scan_batch_id or "").strip()
    target = (batch_id or "").strip()
    return current == target if target else current == ""


def _manual_source_code(part_key: str) -> str:
    return f"MANUAL:{part_key}"


def _scan_to_payload(scan: OutboundScan) -> dict[str, object]:
    return {
        "id": scan.id,
        "order_no": scan.order_no,
        "part_code": scan.part_code,
        "location_code": scan.location_code,
        "source_code": scan.source_code,
        "matched_code": scan.matched_code,
        "quantity": scan.quantity,
        "status": scan.status,
        "operator_id": scan.operator_id,
        "batch_id": scan.batch_id,
        "record_id": scan.record_id,
        "verification_record_id": scan.verification_record_id,
        "void_reason": scan.void_reason,
        "voided_by": scan.voided_by,
        "created_at": scan.created_at.isoformat() if scan.created_at else None,
        "voided_at": scan.voided_at.isoformat() if scan.voided_at else None,
    }


def _source_part_key_from_scan_code(code: str) -> str | None:
    match = PART_CODE_RE.search(code)
    if match is None:
        return None
    return compact_part_code(normalize_part_code(match.group(0)))


def _normalize_location_code(value: str) -> str:
    cleaned = value.strip().upper()
    if not cleaned:
        raise RuntimeError("location_code is required")
    return cleaned


def _inventory_status_value(value: str) -> str:
    status = value.strip().lower()
    aliases = {
        "replenish_needed": "pending_restock",
        "to_be_replaced": "pending_replacement",
    }
    status = aliases.get(status, status)
    if status not in {
        "active",
        "disabled",
        "pending_restock",
        "pending_replacement",
        "zero_stock",
        "retired",
    }:
        raise RuntimeError(
            "status must be active, disabled, pending_restock, pending_replacement, zero_stock, or retired"
        )
    return status
