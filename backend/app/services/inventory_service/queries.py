from __future__ import annotations

import csv
from io import StringIO

from sqlmodel import Session, select

from backend.app.models import InventoryLocation
from backend.app.services.location_profile import location_profile_payload

from .normalize import (
    HIDDEN_LOCATION_STATUSES,
    INVENTORY_CSV_FIELDS,
    _safe_inventory_csv_cell,
    location_payload,
    normalize_factory_id,
    normalize_location_kind,
    normalize_part_key,
)


def export_inventory_locations_csv(*, session: Session) -> str:
    statement = select(InventoryLocation).order_by(
        InventoryLocation.factory_id.asc(),
        InventoryLocation.part_key.asc(),
        InventoryLocation.location_code.asc(),
        InventoryLocation.id.asc(),
    )
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=INVENTORY_CSV_FIELDS)
    writer.writeheader()
    for location in session.exec(statement).all():
        quantity = int(location.quantity or 0)
        row = {
            "factory_id": location.factory_id,
            "part_key": location.part_key,
            "part_name": location.part_name or "",
            "location_code": location.location_code,
            "quantity": quantity,
            "status": location.status,
            "location_kind": normalize_location_kind(location.location_kind),
            "zero_stock": "TRUE" if quantity <= 0 else "FALSE",
            "updated_at": location.updated_at.isoformat() if location.updated_at else "",
        }
        writer.writerow(
            {field: _safe_inventory_csv_cell(row[field]) for field in INVENTORY_CSV_FIELDS}
        )
    return buffer.getvalue()


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
