from __future__ import annotations

import json
from typing import Any

SENSITIVE_KEYS = {
    "raw_ocr_text",
    "image_path",
    "ip_address",
    "user_agent",
    "vin_or_bin",
    "serial_number",
    "operator_id",
    "voided_by",
    "username",
    "display_name",
}


def map_operator_to_role(operator_value: str | None) -> str:
    if operator_value is None:
        return "operator"
    value = str(operator_value).strip().lower()
    if value in {"", "nan", "none", "null"}:
        return "operator"
    normalized = value
    if any(token in normalized for token in ("supervisor", "manager", "admin")):
        return "supervisor"
    return "operator"


def redact_detail_json(raw_json: str | None) -> str | None:
    if not raw_json:
        return None
    try:
        payload = json.loads(raw_json)
    except (TypeError, json.JSONDecodeError):
        return None
    redacted = _redact_value(payload)
    return json.dumps(redacted, ensure_ascii=False, separators=(",", ":"))


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in SENSITIVE_KEYS:
                continue
            lowered = key_text.lower()
            if "vin" in lowered or "serial" in lowered or "password" in lowered:
                continue
            cleaned[key_text] = _redact_value(item)
        return cleaned
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value
