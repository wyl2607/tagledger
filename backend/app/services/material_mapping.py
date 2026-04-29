from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from zipfile import BadZipFile

from backend.app.config import get_settings


@dataclass(frozen=True)
class MaterialMatch:
    ruiyun_part_number: str
    sku: str
    matched_input: str
    matched_field: str


def normalize_material_code(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _cell_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _find_header_indexes(headers: list[str]) -> tuple[int, int] | None:
    normalized = [header.strip().lower() for header in headers]
    ruiyun_candidates = {"瑞云料号", "ruiyun", "ruiyun料号", "料号"}
    sku_candidates = {"sku", "松灵物料", "松灵料号", "物料", "物料号"}

    ruiyun_index = next(
        (index for index, header in enumerate(normalized) if header in ruiyun_candidates), None
    )
    sku_index = next(
        (index for index, header in enumerate(normalized) if header in sku_candidates), None
    )
    if ruiyun_index is None or sku_index is None or ruiyun_index == sku_index:
        return None
    return ruiyun_index, sku_index


def load_material_matches(path: Path) -> list[MaterialMatch]:
    if not path.exists():
        return []
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError:
        return []
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except (BadZipFile, OSError, ValueError):
        return []

    matches: list[MaterialMatch] = []
    try:
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, None)
            if header is None:
                continue
            header_indexes = _find_header_indexes([_cell_text(cell) for cell in header])
            if header_indexes is None:
                continue
            ruiyun_index, sku_index = header_indexes
            for row in rows:
                values = list(row)
                ruiyun = _cell_text(values[ruiyun_index]) if ruiyun_index < len(values) else ""
                sku = _cell_text(values[sku_index]) if sku_index < len(values) else ""
                if ruiyun and sku:
                    matches.append(
                        MaterialMatch(
                            ruiyun_part_number=ruiyun,
                            sku=sku,
                            matched_input="",
                            matched_field="",
                        )
                    )
    finally:
        workbook.close()
    return matches


@lru_cache(maxsize=4)
def _cached_material_matches(path_text: str, mtime_ns: int, size: int) -> tuple[MaterialMatch, ...]:
    return tuple(load_material_matches(Path(path_text)))


def material_catalog() -> list[MaterialMatch]:
    path = get_settings().material_mapping_file
    try:
        stat = path.stat()
    except OSError:
        return []
    return list(_cached_material_matches(str(path), stat.st_mtime_ns, stat.st_size))


def find_material_matches(text: str, limit: int = 5) -> list[MaterialMatch]:
    compact_text = normalize_material_code(text)
    if not compact_text:
        return []

    found: list[MaterialMatch] = []
    seen: set[tuple[str, str]] = set()
    for item in material_catalog():
        candidates = [
            (item.ruiyun_part_number, "ruiyun_part_number"),
            (item.sku, "sku"),
        ]
        for raw_value, field in candidates:
            normalized = normalize_material_code(raw_value)
            if normalized and normalized in compact_text:
                key = (item.ruiyun_part_number, item.sku)
                if key not in seen:
                    found.append(
                        MaterialMatch(
                            ruiyun_part_number=item.ruiyun_part_number,
                            sku=item.sku,
                            matched_input=raw_value,
                            matched_field=field,
                        )
                    )
                    seen.add(key)
                break
        if len(found) >= limit:
            break
    return found


def material_matches_to_text(matches: list[MaterialMatch]) -> str:
    if not matches:
        return ""
    lines = ["MATERIAL MATCHES:"]
    for item in matches:
        lines.append(f"RUIYUN: {item.ruiyun_part_number}")
        lines.append(f"SKU: {item.sku}")
    return "\n".join(lines)


def clear_material_mapping_cache() -> None:
    _cached_material_matches.cache_clear()
