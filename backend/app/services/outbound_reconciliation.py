import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from openpyxl import load_workbook

from backend.app.config import get_settings
from backend.app.services.material_mapping import (
    find_material_matches,
    normalize_material_code,
)

ORDER_RE = re.compile(r"[S5]\s*[O0](?:\D*\d){10,12}", re.IGNORECASE)
PART_CODE_RE = re.compile(
    r"(?:[A-Z]\s*\.\s*){1,3}[A-Z0-9]{1,4}\s*\.\s*\d{4,9}[A-Z]?",
    re.IGNORECASE,
)
QTY_RE = re.compile(r"\d{1,5}")


@dataclass(frozen=True)
class OutboundItem:
    order_no: str
    part_code: str
    quantity: int | None
    source: str
    raw_line: str
    name: str = ""


@dataclass(frozen=True)
class ReconciledItem:
    order_no: str
    part_code: str
    cutting_qty: int
    shipping_qty: int
    difference: int
    status: str
    cutting_lines: list[str]
    shipping_lines: list[str]


def normalize_order_no(value: str) -> str:
    cleaned = "".join(ch for ch in value.upper() if ch.isalnum())
    if cleaned.startswith("5"):
        cleaned = "S" + cleaned[1:]
    return cleaned


def normalize_order_set(values: list[str] | None) -> set[str]:
    return {normalize_order_no(value) for value in values or [] if normalize_order_no(value)}


def normalize_part_code(value: str) -> str:
    compact = re.sub(r"\s+", "", value.upper())
    compact = re.sub(r"\.+", ".", compact)
    return compact.strip(".,;:|[](){}")


def compact_part_code(value: str) -> str:
    return normalize_material_code(normalize_part_code(value))


def _quantity_before(line: str, code_start: int) -> int | None:
    prefix = ORDER_RE.sub(" ", line[:code_start])
    candidates = [int(match.group(0)) for match in QTY_RE.finditer(prefix)]
    return candidates[-1] if candidates else None


def parse_outbound_text(text: str, source: str) -> list[OutboundItem]:
    items: list[OutboundItem] = []
    current_order = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        order_match = ORDER_RE.search(line)
        if order_match:
            current_order = normalize_order_no(order_match.group(0))
        if not current_order:
            continue
        for code_match in PART_CODE_RE.finditer(line):
            part_code = normalize_part_code(code_match.group(0))
            if part_code.count(".") < 2:
                continue
            items.append(
                OutboundItem(
                    order_no=current_order,
                    part_code=part_code,
                    quantity=_quantity_before(line, code_match.start()),
                    source=source,
                    raw_line=line,
                )
            )
    return items


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _cell_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _cell_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = _cell_text(value)
    return int(text) if text.isdigit() else None


def _has_visible_mark(value: object) -> bool:
    text = _cell_text(value).upper()
    return text in {"X", "×", "√", "Y", "YES", "OK", "DONE", "已剪"}


def _load_shipping_sheet(path: Path, sheet_name: str) -> list[OutboundItem]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            return []
        sheet = workbook[sheet_name]
        items: list[OutboundItem] = []
        current_order_no = ""
        for row in sheet.iter_rows(min_row=2, values_only=True):
            order_no = normalize_order_no(_cell_text(row[0] if len(row) > 0 else ""))
            if order_no:
                current_order_no = order_no
            else:
                order_no = current_order_no
            quantity = _cell_int(row[1] if len(row) > 1 else None)
            part_code = normalize_part_code(_cell_text(row[2] if len(row) > 2 else ""))
            name = _cell_text(row[3] if len(row) > 3 else "")
            if order_no and part_code:
                items.append(
                    OutboundItem(
                        order_no=order_no,
                        part_code=part_code,
                        quantity=quantity,
                        source="shipping",
                        raw_line=f"{order_no} {quantity or ''} {part_code} {name}".strip(),
                        name=name,
                    )
                )
        return items
    finally:
        workbook.close()


def _load_cutting_sheet(path: Path, sheet_name: str) -> list[OutboundItem]:
    workbook = load_workbook(path, data_only=True, read_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            return []
        sheet = workbook[sheet_name]
        items: list[OutboundItem] = []
        for row in sheet.iter_rows(min_row=2, values_only=True):
            quantity = _cell_int(row[0] if len(row) > 0 else None)
            part_code = normalize_part_code(_cell_text(row[1] if len(row) > 1 else ""))
            name = _cell_text(row[2] if len(row) > 2 else "")
            checked = any(_has_visible_mark(cell) for cell in row[3:])
            if part_code and ((quantity is not None and quantity > 0) or checked):
                items.append(
                    OutboundItem(
                        order_no="PICKING_TOTAL",
                        part_code=part_code,
                        quantity=quantity,
                        source="cutting",
                        raw_line=f"{quantity or ''} {part_code} {name}".strip(),
                        name=name,
                    )
                )
        return items
    finally:
        workbook.close()


def _fail_outbound_config(message: str) -> NoReturn:
    raise RuntimeError(message)


def load_outbound_items() -> tuple[list[OutboundItem], list[OutboundItem]]:
    settings = get_settings()
    if not settings.outbound_workbook_file.exists():
        _fail_outbound_config(f"outbound workbook not found: {settings.outbound_workbook_file}")
    cutting = _load_cutting_sheet(settings.outbound_workbook_file, settings.outbound_cutting_sheet)
    shipping = _load_shipping_sheet(
        settings.outbound_workbook_file, settings.outbound_shipping_sheet
    )
    if not cutting or not shipping:
        _fail_outbound_config(
            f"outbound workbook missing required rows or sheets: {settings.outbound_workbook_file}"
        )
    return cutting, shipping


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
                "unknown_quantity": False,
            }
        if item.quantity is not None:
            grouped[key]["quantity"] = int(grouped[key]["quantity"]) + item.quantity
        else:
            grouped[key]["unknown_quantity"] = True
        grouped[key]["lines"].append(item.raw_line)
        if item.name:
            grouped[key]["names"].append(item.name)
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
            }
        )
    return rows


def outbound_summary() -> dict[str, object]:
    cutting_items, shipping_items = load_outbound_items()
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


def query_outbound(code: str, selected_orders: list[str] | None = None) -> dict[str, object]:
    candidates = {compact_part_code(code)}
    material_matches = []
    for match in find_material_matches(code):
        material_matches.append(match.__dict__)
        candidates.add(compact_part_code(match.ruiyun_part_number))
        candidates.add(compact_part_code(match.sku))
    cutting_items, shipping_items = load_outbound_items()
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
