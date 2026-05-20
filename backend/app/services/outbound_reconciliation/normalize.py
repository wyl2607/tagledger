import re
from dataclasses import dataclass

from backend.app.services.material_mapping import (
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
    locations: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class OutboundCompletionMark:
    order_no: str
    part_code: str
    quantity: int | None
    raw_line: str


class OutboundVerificationRequiredError(RuntimeError):
    pass


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


def _has_quantity_completion_mark(
    line: str, order_end: int, code_start: int
) -> tuple[bool, int | None]:
    between = line[order_end:code_start]
    quantity_matches = list(QTY_RE.finditer(between))
    if not quantity_matches:
        return False, None
    quantity_match = quantity_matches[-1]
    after_quantity = between[quantity_match.end() :]
    tokens = [
        token for token in re.split(r"[\s|_\-.:;,'\[\](){}]+", after_quantity.strip()) if token
    ]
    if not tokens:
        return False, int(quantity_match.group(0))
    # OCR commonly reads handwritten crosses/checks as K, V, ¥ or stray percent-like marks.
    return len(tokens[0]) == 1 and tokens[0].upper() in {
        "X",
        "×",
        "✕",
        "✖",
        "√",
        "✓",
        "V",
        "K",
        "¥",
        "%",
    }, int(quantity_match.group(0))


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


def parse_outbound_completion_marks(text: str) -> list[OutboundCompletionMark]:
    marks: list[OutboundCompletionMark] = []
    current_order = ""
    seen: set[tuple[str, str, str]] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        order_match = ORDER_RE.search(line)
        if order_match:
            current_order = normalize_order_no(order_match.group(0))
            order_end = order_match.end()
        else:
            order_end = 0
        if not current_order:
            continue
        for code_match in PART_CODE_RE.finditer(line):
            part_code = normalize_part_code(code_match.group(0))
            if part_code.count(".") < 2:
                continue
            marked, quantity = _has_quantity_completion_mark(line, order_end, code_match.start())
            if not marked:
                continue
            key = (current_order, compact_part_code(part_code), line)
            if key in seen:
                continue
            seen.add(key)
            marks.append(
                OutboundCompletionMark(
                    order_no=current_order,
                    part_code=part_code,
                    quantity=quantity,
                    raw_line=line,
                )
            )
    return marks
