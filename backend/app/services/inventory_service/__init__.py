"""Inventory service package.

Replaces the single-file ``inventory_service.py``. All public names that
existed on the old module are re-exported here, so external imports continue
to work::

    from backend.app.services.inventory_service import recommend_inventory_picks
    from backend.app.services.inventory_service import (
        InventoryPermissionError,
        list_inventory_locations,
        ...
    )
"""

from __future__ import annotations

from .movements import (
    adjust_inventory_location,
    move_inventory_quantity,
)
from .normalize import (
    DANGEROUS_CSV_PREFIXES,
    HIDDEN_LOCATION_STATUSES,
    INVENTORY_CSV_FIELDS,
    LOCATION_KIND_ALIASES,
    LOCATION_KINDS,
    PENDING_LOCATION_STATUSES,
    InventoryPermissionError,
    apply_location_visibility_rules,
    location_payload,
    movement_payload,
    normalize_factory_id,
    normalize_location_code,
    normalize_location_kind,
    normalize_part_key,
    normalize_reason,
)
from .queries import (
    export_inventory_locations_csv,
    list_inventory_locations,
    recommend_inventory_picks,
)
from .reconcile import (
    apply_inventory_reconcile,
    preview_inventory_reconcile,
)

__all__ = [
    # constants
    "DANGEROUS_CSV_PREFIXES",
    "HIDDEN_LOCATION_STATUSES",
    "INVENTORY_CSV_FIELDS",
    "LOCATION_KIND_ALIASES",
    "LOCATION_KINDS",
    "PENDING_LOCATION_STATUSES",
    # exception
    "InventoryPermissionError",
    # normalizers
    "normalize_factory_id",
    "normalize_location_code",
    "normalize_location_kind",
    "normalize_part_key",
    "normalize_reason",
    # payload helpers
    "apply_location_visibility_rules",
    "location_payload",
    "movement_payload",
    # queries
    "export_inventory_locations_csv",
    "list_inventory_locations",
    "recommend_inventory_picks",
    # movements
    "adjust_inventory_location",
    "move_inventory_quantity",
    # reconcile
    "apply_inventory_reconcile",
    "preview_inventory_reconcile",
]
