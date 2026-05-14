from __future__ import annotations

import re
from typing import Any

STANDARD_LOCATION_RE = re.compile(
    r"^(?P<zone>[AB])-(?P<column>[A-Z])(?P<rack>\d{2})-0(?P<level>[123])(?P<depth>[123])$"
)

TEMPORARY_KEYWORDS = (
    "临时",
    "TMP",
    "暂存",
    "收货口",
    "门口",
    "地上",
    "待入库",
)
UPSTAIRS_KEYWORDS = ("楼上", "UPSTAIRS", "UP")


def normalize_location_text(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", "", text.strip()).upper()


def _raw_location_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _blank_payload(raw: str, normalized: str) -> dict[str, Any]:
    return {
        "raw_location_code": raw,
        "normalized_location_code": normalized,
        "parse_status": "unresolved",
        "zone": "unresolved",
        "aisle_or_column": None,
        "rack_index": None,
        "level": None,
        "depth": None,
        "centerline_rank": None,
        "sort_key": ["unresolved", normalized],
        "display_label": f"待整理库位：{raw or '空'}",
    }


def _keyword_hit(normalized: str, raw: str, keywords: tuple[str, ...]) -> bool:
    raw_upper = raw.upper()
    for keyword in keywords:
        key = keyword.upper()
        if key == "UP":
            tokens = [token for token in re.split(r"[^A-Z0-9]+", raw_upper) if token]
            if key in tokens or normalized == key:
                return True
            continue
        if key in normalized or key in raw_upper:
            return True
    return False


def _temporary_payload(raw: str, normalized: str) -> dict[str, Any]:
    return {
        "raw_location_code": raw,
        "normalized_location_code": normalized,
        "parse_status": "temporary",
        "zone": "temporary",
        "aisle_or_column": None,
        "rack_index": None,
        "level": None,
        "depth": None,
        "centerline_rank": None,
        "sort_key": ["temporary", normalized],
        "display_label": f"临时库位：{raw}",
    }


def _upstairs_payload(raw: str, normalized: str) -> dict[str, Any]:
    return {
        "raw_location_code": raw,
        "normalized_location_code": normalized,
        "parse_status": "upstairs",
        "zone": "upstairs",
        "aisle_or_column": None,
        "rack_index": None,
        "level": None,
        "depth": None,
        "centerline_rank": None,
        "sort_key": ["upstairs", normalized],
        "display_label": "楼上区域（待精确整理）",
    }


def parse_location_code(value: object) -> dict[str, Any]:
    raw = _raw_location_text(value)
    normalized = normalize_location_text(value)
    if not normalized:
        return _blank_payload(raw, normalized)

    match = STANDARD_LOCATION_RE.match(normalized)
    if match:
        zone = match.group("zone")
        column = match.group("column")
        rack_index = int(match.group("rack"))
        level = int(match.group("level"))
        depth = int(match.group("depth"))
        return {
            "raw_location_code": raw,
            "normalized_location_code": normalized,
            "parse_status": "standard",
            "zone": zone,
            "aisle_or_column": column,
            "rack_index": rack_index,
            "level": level,
            "depth": depth,
            "centerline_rank": depth,
            "sort_key": ["standard", zone, column, rack_index, level, depth],
            "display_label": f"{zone}区 {column}列 {rack_index}号架 {level}层 近位{depth}",
        }

    if _keyword_hit(normalized, raw, UPSTAIRS_KEYWORDS):
        return _upstairs_payload(raw, normalized)
    if _keyword_hit(normalized, raw, TEMPORARY_KEYWORDS):
        return _temporary_payload(raw, normalized)

    return _blank_payload(raw, normalized)


def location_profile_payload(
    location_code: object, location_kind: str | None = None
) -> dict[str, Any]:
    profile = parse_location_code(location_code)
    kind = (location_kind or "").strip().lower()
    if kind in {"temporary", "temp"} and profile["parse_status"] == "unresolved":
        return _temporary_payload(profile["raw_location_code"], profile["normalized_location_code"])
    return profile
