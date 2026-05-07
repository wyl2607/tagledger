from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from statistics import mean

from sqlmodel import Session, select

from backend.app.config import get_settings
from backend.app.models import (
    Category,
    InventoryLocation,
    InventoryMovement,
    OutboundScan,
    Record,
    RecordStatus,
    utc_now,
)


def _all_records(session: Session) -> list[Record]:
    return list(session.exec(select(Record)).all())


def _seconds_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return max((end - start).total_seconds(), 0.0)


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 2) if values else None


def summary(session: Session) -> dict:
    records = _all_records(session)
    status_counts = Counter(record.status.value for record in records)
    category_counts = Counter(record.category.value for record in records)
    return {
        "total_records": len(records),
        "by_status": {status.value: status_counts.get(status.value, 0) for status in RecordStatus},
        "by_category": {
            category.value: category_counts.get(category.value, 0) for category in Category
        },
        "confirmed_count": sum(
            1
            for record in records
            if record.status in (RecordStatus.confirmed, RecordStatus.submitted)
        ),
        "submitted_count": status_counts.get(RecordStatus.submitted.value, 0),
        "failed_count": status_counts.get(RecordStatus.submission_failed.value, 0),
        "duplicates_caught": status_counts.get(RecordStatus.duplicate.value, 0),
    }


def daily_throughput(session: Session, days: int = 30) -> list[dict]:
    bounded_days = max(1, min(days, 365))
    today = utc_now().date()
    start = today - timedelta(days=bounded_days - 1)
    buckets = {
        start + timedelta(days=offset): {"uploaded": 0, "confirmed": 0, "submitted": 0}
        for offset in range(bounded_days)
    }

    for record in _all_records(session):
        record_date = record.created_at.date()
        if record_date not in buckets:
            continue
        buckets[record_date]["uploaded"] += 1
        if record.status in (RecordStatus.confirmed, RecordStatus.submitted):
            buckets[record_date]["confirmed"] += 1
        if record.status == RecordStatus.submitted:
            buckets[record_date]["submitted"] += 1

    return [
        {"date": bucket_date.isoformat(), **values}
        for bucket_date, values in sorted(buckets.items())
    ]


def avg_processing_time(session: Session) -> dict:
    records = _all_records(session)
    upload_to_confirm = [
        seconds
        for record in records
        if record.status in (RecordStatus.confirmed, RecordStatus.submitted)
        for seconds in [_seconds_between(record.created_at, record.updated_at)]
        if seconds is not None
    ]
    confirm_to_submit = [
        seconds
        for record in records
        if record.status == RecordStatus.submitted
        for seconds in [_seconds_between(record.updated_at, record.submitted_at)]
        if seconds is not None
    ]
    return {
        "upload_to_confirm_seconds": _avg(upload_to_confirm),
        "confirm_to_submit_seconds": _avg(confirm_to_submit),
    }


def ocr_quality(session: Session) -> dict:
    records = _all_records(session)
    scored = [record.confidence_score for record in records if record.confidence_score is not None]
    high = [score for score in scored if score >= 0.9]
    low = [score for score in scored if score < 0.7]
    denominator = len(scored) or 1
    return {
        "avg_confidence": round(mean(scored), 4) if scored else None,
        "high_confidence_pct": round(len(high) / denominator, 4) if scored else 0,
        "low_confidence_pct": round(len(low) / denominator, 4) if scored else 0,
        "needs_review_count": sum(
            1 for record in records if record.status == RecordStatus.needs_review
        ),
    }


def error_prevention(session: Session) -> dict:
    summary_payload = summary(session)
    return {
        "duplicates_caught": summary_payload["duplicates_caught"],
        "total_attempts": summary_payload["total_records"],
        "manual_corrections": None,
        "manual_corrections_note": "TODO: add confirmed-field audit snapshots before estimating manual corrections.",
    }


def estimated_savings(session: Session) -> dict:
    summary_payload = summary(session)
    processing = avg_processing_time(session)
    confirmed_count = summary_payload["confirmed_count"]
    actual_seconds = processing["upload_to_confirm_seconds"] or 0
    manual_seconds = get_settings().metrics_manual_seconds_per_entry
    saved_minutes = max(
        confirmed_count * (manual_seconds - actual_seconds) / 60,
        0,
    )
    return {
        "assume_manual_seconds_per_entry": manual_seconds,
        "assume_avg_processing_seconds": actual_seconds,
        "total_saved_minutes": round(saved_minutes, 2),
    }


def logistics_metrics(session: Session, days: int = 7) -> dict:
    bounded_days = max(1, min(days, 365))
    since = utc_now() - timedelta(days=bounded_days)
    locations = list(session.exec(select(InventoryLocation)).all())
    recent_movements = list(
        session.exec(select(InventoryMovement).where(InventoryMovement.created_at >= since)).all()
    )
    active_scans = list(
        session.exec(select(OutboundScan).where(OutboundScan.status == "active")).all()
    )

    active_locations = [row for row in locations if row.status == "active"]
    zero_stock_locations = [
        row for row in locations if bool(row.zero_stock) or int(row.quantity or 0) <= 0
    ]
    restock_locations = [
        row for row in active_locations if bool(row.zero_stock) or int(row.quantity or 0) <= 0
    ]

    inbound_quantity = 0
    outbound_quantity = 0
    transfer_quantity = 0
    for movement in recent_movements:
        movement_type = movement.movement_type or ""
        delta = int(movement.quantity_delta or 0)
        if movement_type == "inbound":
            inbound_quantity += max(delta, 0)
        elif movement_type.startswith("transfer_"):
            transfer_quantity += abs(delta)
        elif movement_type.startswith("outbound"):
            outbound_quantity += abs(delta)

    return {
        "inventory": {
            "location_count": len(locations),
            "active_location_count": len(active_locations),
            "disabled_location_count": sum(1 for row in locations if row.status == "disabled"),
            "zero_stock_location_count": len(zero_stock_locations),
            "restock_needed_count": len(restock_locations),
            "part_count": len({row.part_key for row in locations}),
            "total_quantity": sum(int(row.quantity or 0) for row in locations),
        },
        "movements": {
            "days": bounded_days,
            "movement_count": len(recent_movements),
            "inbound_quantity": inbound_quantity,
            "outbound_quantity": outbound_quantity,
            "transfer_quantity": transfer_quantity,
        },
        "outbound": {
            "active_scan_count": len(active_scans),
            "active_scan_quantity": sum(int(row.quantity or 0) for row in active_scans),
            "active_order_count": len({row.order_no for row in active_scans}),
        },
    }


def all_metrics(session: Session, days: int = 30) -> dict:
    return {
        "summary": summary(session),
        "throughput": daily_throughput(session, days=days),
        "processing_time": avg_processing_time(session),
        "ocr_quality": ocr_quality(session),
        "error_prevention": error_prevention(session),
        "logistics": logistics_metrics(session, days=days),
        "savings": estimated_savings(session),
        "generated_at": datetime.now(UTC).isoformat(),
    }
