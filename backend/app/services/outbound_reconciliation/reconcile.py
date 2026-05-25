from .normalize import (
    OutboundItem,
    ReconciledItem,
    compact_part_code,
    normalize_order_no,
    normalize_order_set,
)


def _aggregate(items: list[OutboundItem]) -> dict[tuple[str, str], dict[str, object]]:
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for item in items:
        key = (item.order_no, compact_part_code(item.part_code))
        if key not in grouped:
            grouped[key] = {
                "order_no": item.order_no,
                "part_code": item.part_code,
                "quantity": 0,
                "lines": [],
                "names": [],
                "unknown_quantity": False,
            }
        if item.quantity is None:
            grouped[key]["unknown_quantity"] = True
        else:
            grouped[key]["quantity"] = int(grouped[key]["quantity"]) + item.quantity
        grouped[key]["lines"].append(item.raw_line)
        if item.name:
            grouped[key]["names"].append(item.name)
        if item.locations:
            grouped[key].setdefault("locations", [])
            grouped[key]["locations"].extend(item.locations)
    return grouped


def _aggregate_by_part(items: list[OutboundItem]) -> dict[str, dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for item in items:
        key = compact_part_code(item.part_code)
        if key not in grouped:
            grouped[key] = {
                "part_code": item.part_code,
                "quantity": 0,
                "lines": [],
                "names": [],
                "locations": [],
                "unknown_quantity": False,
            }
        if item.quantity is not None:
            grouped[key]["quantity"] = int(grouped[key]["quantity"]) + item.quantity
        else:
            grouped[key]["unknown_quantity"] = True
        grouped[key]["lines"].append(item.raw_line)
        if item.name:
            grouped[key]["names"].append(item.name)
        grouped[key]["locations"].extend(item.locations)
    return grouped


def reconcile_outbound_items(
    cutting_items: list[OutboundItem],
    shipping_items: list[OutboundItem],
) -> list[ReconciledItem]:
    cutting = _aggregate(cutting_items)
    shipping = _aggregate(shipping_items)
    rows: list[ReconciledItem] = []
    for key in sorted(set(cutting) | set(shipping)):
        cut = cutting.get(key)
        ship = shipping.get(key)
        cutting_qty = int(cut["quantity"]) if cut else 0
        shipping_qty = int(ship["quantity"]) if ship else 0
        if cut is None:
            status = "shipping_extra"
        elif ship is None:
            status = "cutting_missing_shipping"
        elif cut.get("unknown_quantity") or ship.get("unknown_quantity"):
            status = "quantity_unreadable"
        elif cutting_qty == shipping_qty:
            status = "matched"
        elif shipping_qty > cutting_qty:
            status = "over_shipped"
        else:
            status = "under_shipped"
        rows.append(
            ReconciledItem(
                order_no=(cut or ship)["order_no"],
                part_code=(cut or ship)["part_code"],
                cutting_qty=cutting_qty,
                shipping_qty=shipping_qty,
                difference=shipping_qty - cutting_qty,
                status=status,
                cutting_lines=list(cut["lines"]) if cut else [],
                shipping_lines=list(ship["lines"]) if ship else [],
            )
        )
    return rows


def _part_rows(
    cutting_items: list[OutboundItem], shipping_items: list[OutboundItem]
) -> list[dict[str, object]]:
    cutting_parts = _aggregate_by_part(cutting_items)
    shipping_parts = _aggregate_by_part(shipping_items)
    rows = []
    for key in sorted(set(cutting_parts) | set(shipping_parts)):
        cut = cutting_parts.get(key)
        ship = shipping_parts.get(key)
        cutting_qty = int(cut["quantity"]) if cut else 0
        shipping_qty = int(ship["quantity"]) if ship else 0
        if cut is None:
            status = "shipping_extra"
        elif ship is None:
            status = "cutting_missing_shipping"
        elif cut.get("unknown_quantity") or ship.get("unknown_quantity"):
            status = "quantity_unreadable"
        elif cutting_qty == shipping_qty:
            status = "matched"
        elif shipping_qty > cutting_qty:
            status = "over_shipped"
        else:
            status = "under_shipped"
        rows.append(
            {
                "part_code": (cut or ship)["part_code"],
                "name": next(iter((cut or ship).get("names", [])), ""),
                "cutting_qty": cutting_qty,
                "shipping_qty": shipping_qty,
                "difference": shipping_qty - cutting_qty,
                "status": status,
                "cutting_lines": list(cut["lines"]) if cut else [],
                "shipping_lines": list(ship["lines"]) if ship else [],
                "locations": sorted(set(cut.get("locations", []))) if cut else [],
            }
        )
    return rows


def _scope_items_for_orders(
    cutting_items: list[OutboundItem],
    shipping_items: list[OutboundItem],
    allowed_orders: list[str] | None,
) -> tuple[list[OutboundItem], list[OutboundItem]]:
    if allowed_orders is None:
        return cutting_items, shipping_items
    selected = normalize_order_set(allowed_orders)
    if not selected:
        return [], []
    scoped_shipping = [
        item for item in shipping_items if normalize_order_no(item.order_no) in selected
    ]
    scoped_part_keys = {compact_part_code(item.part_code) for item in scoped_shipping}
    scoped_cutting = [
        item for item in cutting_items if compact_part_code(item.part_code) in scoped_part_keys
    ]
    return scoped_cutting, scoped_shipping
