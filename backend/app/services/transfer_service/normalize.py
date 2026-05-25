from __future__ import annotations

from datetime import UTC, datetime

from backend.app.services.material_mapping import normalize_material_code

FACTORIES = ("factory_a", "factory_b", "factory_c")


def _to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_factory_id(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in FACTORIES:
        raise RuntimeError(f"unsupported factory_id: {value}")
    return normalized


def _normalize_part_key(value: str) -> str:
    normalized = normalize_material_code(value or "")
    if not normalized:
        raise RuntimeError("part_key is required")
    return normalized


def _normalize_reason(value: str) -> str:
    reason = (value or "").strip()
    if not reason:
        raise RuntimeError("reason is required")
    return reason[:200]


def _normalize_idempotency_key(value: str | None) -> str | None:
    key = (value or "").strip()
    return key[:120] if key else None
