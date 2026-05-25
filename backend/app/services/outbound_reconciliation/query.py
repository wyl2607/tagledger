from collections import defaultdict

from backend.app.config import get_settings
from backend.app.services.material_mapping import (
    find_material_matches,
)

from .excel_loader import load_outbound_items
from .normalize import (
    OutboundItem,
    compact_part_code,
    normalize_order_no,
    normalize_order_set,
)
from .reconcile import (
    _aggregate_by_part,
    _part_rows,
    _scope_items_for_orders,
)


def outbound_summary(allowed_orders: list[str] | None = None) -> dict[str, object]:
    cutting_items, shipping_items = load_outbound_items()
    cutting_items, shipping_items = _scope_items_for_orders(
        cutting_items,
        shipping_items,
        allowed_orders,
    )
    part_rows = _part_rows(cutting_items, shipping_items)
    part_status_counts: dict[str, int] = defaultdict(int)
    for row in part_rows:
        part_status_counts[str(row["status"])] += 1
    order_numbers = {
        "cutting": sorted({item.order_no for item in cutting_items}),
        "shipping": sorted({item.order_no for item in shipping_items}),
    }
    return {
        "data_source": "workbook" if get_settings().outbound_workbook_file.exists() else "text_ocr",
        "order_numbers": {
            "shipping": order_numbers["shipping"],
            "note": "拣货单没有出库单号，单号只来自发货单；数量按备件编码总量核对。",
        },
        "counts": {
            "cutting_items": len(cutting_items),
            "shipping_items": len(shipping_items),
            "cutting_part_rows": len(_aggregate_by_part(cutting_items)),
            "shipping_part_rows": len(_aggregate_by_part(shipping_items)),
            "part_status": dict(sorted(part_status_counts.items())),
        },
        "part_rows": part_rows,
    }


def outbound_order_choices(allowed_orders: list[str] | None = None) -> dict[str, object]:
    cutting_items, shipping_items = load_outbound_items()
    _, shipping_items = _scope_items_for_orders(cutting_items, shipping_items, allowed_orders)
    return {
        "data_source": "workbook" if get_settings().outbound_workbook_file.exists() else "text_ocr",
        "order_numbers": {
            "shipping": sorted(
                {normalize_order_no(item.order_no) for item in shipping_items if item.order_no}
            ),
            "note": "拣货单没有出库单号，单号只来自发货单；数量按备件编码总量核对。",
        },
    }


def query_outbound(
    code: str,
    selected_orders: list[str] | None = None,
    allowed_orders: list[str] | None = None,
) -> dict[str, object]:
    candidates = {compact_part_code(code)}
    material_matches = []
    for match in find_material_matches(code):
        material_matches.append(match.__dict__)
        candidates.add(compact_part_code(match.ruiyun_part_number))
        candidates.add(compact_part_code(match.sku))
    cutting_items, shipping_items = load_outbound_items()
    cutting_items, shipping_items = _scope_items_for_orders(
        cutting_items,
        shipping_items,
        allowed_orders,
    )
    rows = [
        row
        for row in _part_rows(cutting_items, shipping_items)
        if compact_part_code(str(row["part_code"])) in candidates
    ]
    shipping_orders = [
        item.__dict__ for item in shipping_items if compact_part_code(item.part_code) in candidates
    ]
    cutting_totals = [
        item.__dict__ for item in cutting_items if compact_part_code(item.part_code) in candidates
    ]
    selected = normalize_order_set(selected_orders)
    matching_selected_orders = [
        item for item in shipping_orders if normalize_order_no(str(item["order_no"])) in selected
    ]
    matching_other_orders = [
        item
        for item in shipping_orders
        if selected and normalize_order_no(str(item["order_no"])) not in selected
    ]
    return {
        "query": code,
        "candidate_codes": sorted(candidates),
        "material_matches": material_matches,
        "selected_order_numbers": sorted(selected),
        "belongs_to_selected": bool(selected and matching_selected_orders),
        "rows": rows,
        "shipping_orders": shipping_orders,
        "matching_selected_orders": matching_selected_orders,
        "matching_other_orders": matching_other_orders,
        "cutting_totals": cutting_totals,
    }


def candidate_part_codes(code: str) -> list[str]:
    candidates = {compact_part_code(code)}
    for match in find_material_matches(code):
        candidates.add(compact_part_code(match.ruiyun_part_number))
        candidates.add(compact_part_code(match.sku))
    return sorted(candidate for candidate in candidates if candidate)


def _order_required_rows(order_no: str) -> dict[str, dict[str, object]]:
    selected_order = normalize_order_no(order_no)
    cutting_items, shipping_items = load_outbound_items()
    location_map = _part_location_map(cutting_items)
    rows: dict[str, dict[str, object]] = {}
    for item in shipping_items:
        if normalize_order_no(item.order_no) != selected_order:
            continue
        key = compact_part_code(item.part_code)
        if key not in rows:
            rows[key] = {
                "order_no": selected_order,
                "part_code": item.part_code,
                "name": item.name,
                "locations": location_map.get(key, []),
                "required_qty": 0,
                "unknown_quantity": False,
                "shipping_lines": [],
            }
        if item.quantity is None:
            rows[key]["unknown_quantity"] = True
        else:
            rows[key]["required_qty"] = int(rows[key]["required_qty"]) + item.quantity
        rows[key]["shipping_lines"].append(item.raw_line)
    return rows


def _order_numbers() -> list[str]:
    _, shipping_items = load_outbound_items()
    return sorted({normalize_order_no(item.order_no) for item in shipping_items if item.order_no})


def _part_location_map(cutting_items: list[OutboundItem]) -> dict[str, list[str]]:
    locations: dict[str, list[str]] = defaultdict(list)
    for item in cutting_items:
        key = compact_part_code(item.part_code)
        for location in item.locations:
            if location not in locations[key]:
                locations[key].append(location)
    return dict(locations)
