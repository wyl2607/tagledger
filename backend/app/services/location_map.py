from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from backend.app.models import InventoryLocation
from backend.app.services.inventory_service import (
    HIDDEN_LOCATION_STATUSES,
    location_payload,
    normalize_factory_id,
)

MIXED_MATERIAL_THRESHOLD = 5


def _empty_summary() -> dict[str, int]:
    return {
        "total_quantity": 0,
        "standard_location_count": 0,
        "temporary_location_count": 0,
        "upstairs_location_count": 0,
        "unresolved_location_count": 0,
        "mixed_location_count": 0,
        "restock_required_count": 0,
    }


def _empty_payload(factory_id: str | None) -> dict[str, Any]:
    return {
        "factory_id": factory_id,
        "summary": _empty_summary(),
        "zones": {"A": {"columns": {}}, "B": {"columns": {}}},
        "buckets": {"temporary": [], "upstairs": [], "unresolved": []},
    }


def _material_payload(row: dict[str, object]) -> dict[str, object]:
    return {
        "part_key": row["part_key"],
        "part_name": row["part_name"],
        "quantity": int(row["quantity"] or 0),
    }


def _new_cell(row: dict[str, object]) -> dict[str, Any]:
    return {
        "location_code": row["location_code"],
        "location_profile": row["location_profile"],
        "total_quantity": 0,
        "material_count": 0,
        "materials": [],
        "mixed_material_warning": False,
        "restock_required": False,
        "sort_key": row["location_profile"]["sort_key"],
    }


def _merge_location_row(target: dict[str, Any], row: dict[str, object]) -> None:
    target["total_quantity"] += int(row["quantity"] or 0)
    target["restock_required"] = bool(target["restock_required"] or row["restock_required"])
    material_by_key = {item["part_key"]: item for item in target["materials"]}
    part_key = row["part_key"]
    if part_key in material_by_key:
        material_by_key[part_key]["quantity"] += int(row["quantity"] or 0)
        if not material_by_key[part_key].get("part_name") and row.get("part_name"):
            material_by_key[part_key]["part_name"] = row["part_name"]
    else:
        target["materials"].append(_material_payload(row))
    target["materials"].sort(key=lambda item: str(item["part_key"]))
    target["material_count"] = len(target["materials"])
    target["mixed_material_warning"] = target["material_count"] >= MIXED_MATERIAL_THRESHOLD


def _bucket_item(row: dict[str, object]) -> dict[str, Any]:
    item = _new_cell(row)
    _merge_location_row(item, row)
    return item


def _bucket_index(bucket: list[dict[str, Any]], location_code: str) -> dict[str, Any] | None:
    return next((item for item in bucket if item["location_code"] == location_code), None)


def _standard_cell(payload: dict[str, Any], profile: dict[str, object], row: dict[str, object]):
    zone = str(profile["zone"])
    column = str(profile["aisle_or_column"])
    rack = str(profile["rack_index"])
    level = str(profile["level"])
    depth = str(profile["depth"])
    columns = payload["zones"].setdefault(zone, {"columns": {}})["columns"]
    column_payload = columns.setdefault(column, {"racks": {}})
    rack_payload = column_payload["racks"].setdefault(
        rack,
        {
            "rack_index": profile["rack_index"],
            "rack_warning": False,
            "rack_warning_message": None,
            "levels": {},
        },
    )
    level_payload = rack_payload["levels"].setdefault(level, {"depths": {}})
    depths = level_payload["depths"]
    return rack_payload, depths.setdefault(depth, _new_cell(row))


def _apply_rack_warnings(payload: dict[str, Any]) -> None:
    for zone_payload in payload["zones"].values():
        for column_payload in zone_payload["columns"].values():
            for rack_payload in column_payload["racks"].values():
                mixed_cells = [
                    cell
                    for level_payload in rack_payload["levels"].values()
                    for cell in level_payload["depths"].values()
                    if cell["mixed_material_warning"]
                ]
                if len(mixed_cells) >= 2:
                    rack_payload["rack_warning"] = True
                    rack_payload["rack_warning_message"] = (
                        "同一货架多个深度位混放物料较多，建议整理到 B区或待整理区。"
                    )


def _standard_cells(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        cell
        for zone_payload in payload["zones"].values()
        for column_payload in zone_payload["columns"].values()
        for rack_payload in column_payload["racks"].values()
        for level_payload in rack_payload["levels"].values()
        for cell in level_payload["depths"].values()
    ]


def _refresh_summary_counts(payload: dict[str, Any]) -> None:
    cells = _standard_cells(payload)
    bucket_items = [item for bucket in payload["buckets"].values() for item in bucket]
    payload["summary"].update(
        {
            "standard_location_count": len(cells),
            "temporary_location_count": len(payload["buckets"]["temporary"]),
            "upstairs_location_count": len(payload["buckets"]["upstairs"]),
            "unresolved_location_count": len(payload["buckets"]["unresolved"]),
            "mixed_location_count": sum(
                1 for item in [*cells, *bucket_items] if item["mixed_material_warning"]
            ),
            "restock_required_count": sum(
                1 for item in [*cells, *bucket_items] if item["restock_required"]
            ),
        }
    )


def build_inventory_location_map(
    *,
    session: Session,
    factory_id: str | None = None,
    include_hidden: bool = False,
) -> dict[str, Any]:
    normalized_factory = normalize_factory_id(factory_id) if factory_id else None
    statement = select(InventoryLocation)
    if normalized_factory:
        statement = statement.where(InventoryLocation.factory_id == normalized_factory)
    rows = session.exec(
        statement.order_by(
            InventoryLocation.factory_id.asc(),
            InventoryLocation.location_code.asc(),
            InventoryLocation.part_key.asc(),
        )
    ).all()
    payload = _empty_payload(normalized_factory)
    visible_rows = [
        row for row in rows if include_hidden or row.status not in HIDDEN_LOCATION_STATUSES
    ]

    for location in visible_rows:
        row = location_payload(location)
        profile = row["location_profile"]
        quantity = int(row["quantity"] or 0)
        payload["summary"]["total_quantity"] += quantity

        status = profile["parse_status"]
        if status == "standard":
            rack_payload, cell = _standard_cell(payload, profile, row)
            _merge_location_row(cell, row)
            continue

        bucket_name = status if status in {"temporary", "upstairs"} else "unresolved"
        bucket = payload["buckets"][bucket_name]
        item = _bucket_index(bucket, str(row["location_code"]))
        if item is None:
            item = _bucket_item(row)
            bucket.append(item)
        else:
            _merge_location_row(item, row)

    _apply_rack_warnings(payload)
    _refresh_summary_counts(payload)
    for bucket in payload["buckets"].values():
        bucket.sort(key=lambda item: item["sort_key"])
    return payload
