"""Outbound reconciliation package.

This package replaces the former single-file ``outbound_reconciliation.py``.
Public names that existed on the old module are re-exported here so that
external imports remain backward compatible::

    from backend.app.services.outbound_reconciliation import outbound_summary
    from backend.app.services import outbound_reconciliation

A monkeypatch-propagation hook keeps the existing test pattern working::

    monkeypatch.setattr(outbound_reconciliation, "get_settings", fake)

so that submodules which captured the original symbol at import time pick up
the patched version.
"""

from __future__ import annotations

# ---- external symbols re-exported for monkeypatch compatibility -------------
#
# The legacy monolith imported these at module top, which made them attributes
# of the ``outbound_reconciliation`` module. Tests rely on that by calling
# ``monkeypatch.setattr(outbound_reconciliation, "get_settings", fake)``.
from backend.app.config import get_settings  # noqa: F401
from backend.app.models import (  # noqa: F401
    OutboundProgressSnapshot,
    OutboundScan,
)
from backend.app.services.material_mapping import (  # noqa: F401
    find_material_matches,
    normalize_material_code,
)

from .excel_loader import (
    _load_cutting_sheet,
    _load_shipping_sheet,
    load_outbound_items,
)
from .inventory import (
    _record_inventory_movement,
    get_inventory_locations,
    get_inventory_movements,
    inbound_inventory,
    list_alternative_locations,
    outbound_inventory,
    reactivate_inventory_location,
    set_inventory_location_status,
    transfer_inventory,
)

# ---- public re-exports (organised by submodule) -----------------------------
from .normalize import (
    ORDER_RE,
    PART_CODE_RE,
    QTY_RE,
    OutboundCompletionMark,
    OutboundItem,
    OutboundVerificationRequiredError,
    ReconciledItem,
    compact_part_code,
    normalize_order_no,
    normalize_order_set,
    normalize_part_code,
    parse_outbound_completion_marks,
    parse_outbound_text,
)
from .orders import (
    complete_outbound_order,
    outbound_batch_detail,
    outbound_ops_health,
    outbound_order_status,
    outbound_orders_overview,
    outbound_orders_status,
    outbound_progress_snapshots,
    outbound_remaining_csv,
    rollback_outbound_order,
    save_outbound_progress_snapshot,
    set_outbound_part_quantity,
    sync_outbound_completion_marks,
    void_outbound_batch,
    void_outbound_scan,
)
from .query import (
    candidate_part_codes,
    outbound_order_choices,
    outbound_summary,
    query_outbound,
)
from .reconcile import reconcile_outbound_items
from .scans import (
    outbound_order_scans,
    preview_outbound_scan,
    register_outbound_scan,
)

__all__ = [
    # types
    "OutboundCompletionMark",
    "OutboundItem",
    "OutboundVerificationRequiredError",
    "ReconciledItem",
    # regex constants
    "ORDER_RE",
    "PART_CODE_RE",
    "QTY_RE",
    # normalize
    "compact_part_code",
    "normalize_order_no",
    "normalize_order_set",
    "normalize_part_code",
    "parse_outbound_completion_marks",
    "parse_outbound_text",
    # excel_loader
    "_load_cutting_sheet",
    "_load_shipping_sheet",
    "load_outbound_items",
    # reconcile
    "reconcile_outbound_items",
    # query
    "candidate_part_codes",
    "outbound_order_choices",
    "outbound_summary",
    "query_outbound",
    # inventory
    "_record_inventory_movement",
    "get_inventory_locations",
    "get_inventory_movements",
    "inbound_inventory",
    "list_alternative_locations",
    "outbound_inventory",
    "reactivate_inventory_location",
    "set_inventory_location_status",
    "transfer_inventory",
    # orders
    "complete_outbound_order",
    "outbound_batch_detail",
    "outbound_ops_health",
    "outbound_order_status",
    "outbound_orders_overview",
    "outbound_orders_status",
    "outbound_progress_snapshots",
    "outbound_remaining_csv",
    "rollback_outbound_order",
    "save_outbound_progress_snapshot",
    "set_outbound_part_quantity",
    "sync_outbound_completion_marks",
    "void_outbound_batch",
    "void_outbound_scan",
    # scans
    "outbound_order_scans",
    "preview_outbound_scan",
    "register_outbound_scan",
]


# ---- monkeypatch propagation -------------------------------------------------
#
# Tests do `monkeypatch.setattr(outbound_reconciliation, NAME, fake)`. Each
# submodule captured the original by `from backend.app.config import
# get_settings` (etc.) at import time, so a setattr on the package alone does
# not reach those bindings. We propagate the assignment to every submodule
# that imported the symbol.

import sys as _sys
import types as _types

from . import _helpers as _helpers
from . import excel_loader as _excel_loader
from . import inventory as _inventory
from . import orders as _orders
from . import query as _query
from . import scans as _scans

_PATCH_TARGETS = {
    # get_settings is imported (and used) in every business module.
    "get_settings": (
        _excel_loader,
        _query,
        _helpers,
        _inventory,
        _orders,
        _scans,
    ),
    "load_outbound_items": (_query,),
    "find_material_matches": (_query,),
    "query_outbound": (_helpers, _inventory, _orders, _scans),
    "candidate_part_codes": (_scans,),
    "_record_inventory_movement": (_inventory, _orders, _scans),
}


class _OutboundReconciliationModule(_types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        for module in _PATCH_TARGETS.get(name, ()):
            setattr(module, name, value)


_sys.modules[__name__].__class__ = _OutboundReconciliationModule
