from __future__ import annotations

from backend.app.models import InventoryLocation, InventoryMovement
from backend.app.services.location_profile import location_profile_payload
from backend.app.services.material_mapping import normalize_material_code
from backend.app.services.transfer_service import FACTORIES

LOCATION_KIND_ALIASES = {"long_term": "permanent"}

LOCATION_KINDS = {"permanent", "temporary"}

HIDDEN_LOCATION_STATUSES = {"retired", "disabled"}

PENDING_LOCATION_STATUSES = {"pending_restock", "pending_replacement"}

INVENTORY_CSV_FIELDS = [
    "factory_id",
    "part_key",
    "part_name",
    "location_code",
    "quantity",
    "status",
    "location_kind",
    "zero_stock",
    "updated_at",
]

DANGEROUS_CSV_PREFIXES = {"=", "+", "-", "@"}


class InventoryPermissionError(RuntimeError):
    pass


def normalize_factory_id(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized not in FACTORIES:
        raise RuntimeError(f"unsupported factory_id: {value}")
    return normalized


def normalize_part_key(value: str) -> str:
    normalized = normalize_material_code(value or "")
    if not normalized:
        raise RuntimeError("part_key is required")
    return normalized


def normalize_location_code(value: str) -> str:
    code = (value or "").strip().upper()
    if not code:
        raise RuntimeError("location_code is required")
    return code[:80]


def normalize_location_kind(value: str | None) -> str:
    kind = (value or "permanent").strip().lower()
    kind = LOCATION_KIND_ALIASES.get(kind, kind)
    if kind not in LOCATION_KINDS:
        raise RuntimeError(f"unsupported location_kind: {value}")
    return kind


def normalize_reason(value: str | None) -> str:
    reason = (value or "").strip()
    if not reason:
        raise RuntimeError("reason is required")
    return reason[:200]


def apply_location_visibility_rules(location: InventoryLocation) -> None:
    quantity = int(location.quantity or 0)
    kind = normalize_location_kind(location.location_kind)
    location.location_kind = kind
    location.zero_stock = quantity <= 0
    if location.status == "disabled":
        return
    if location.status in PENDING_LOCATION_STATUSES:
        return
    if quantity <= 0 and kind == "temporary":
        location.status = "retired"
    elif quantity <= 0:
        location.status = "zero_stock"
    elif location.status in {"zero_stock", "retired"}:
        location.status = "active"


def location_payload(location: InventoryLocation) -> dict[str, object]:
    kind = normalize_location_kind(location.location_kind)
    quantity = int(location.quantity or 0)
    visible = location.status not in HIDDEN_LOCATION_STATUSES
    return {
        "id": location.id or 0,
        "factory_id": location.factory_id,
        "part_key": location.part_key,
        "part_name": location.part_name,
        "location_code": location.location_code,
        "location_profile": location_profile_payload(location.location_code, kind),
        "quantity": quantity,
        "status": location.status,
        "zero_stock": bool(location.zero_stock),
        "location_kind": kind,
        "replacement_location_code": location.replacement_location_code,
        "visible": visible,
        "restock_required": visible and kind == "permanent" and quantity <= 0,
        "updated_at": location.updated_at.isoformat() if location.updated_at else None,
    }


def _safe_inventory_csv_cell(value: object) -> object:
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip(" \t\r\n")
    if stripped and stripped[0] in DANGEROUS_CSV_PREFIXES:
        return f"'{value}"
    return value


def movement_payload(movement: InventoryMovement) -> dict[str, object]:
    return {
        "id": movement.id or 0,
        "factory_id": movement.factory_id,
        "movement_type": movement.movement_type,
        "part_key": movement.part_key,
        "location_code": movement.location_code,
        "quantity_delta": movement.quantity_delta,
        "before_qty": movement.before_qty,
        "after_qty": movement.after_qty,
        "operator_id": movement.operator_id,
        "reason": movement.reason,
        "created_at": movement.created_at.isoformat() if movement.created_at else None,
    }
