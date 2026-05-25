"""Transfer service package.

Replaces the single-file ``transfer_service.py``. External callers import
the same public names from the package as before::

    from backend.app.services.transfer_service import (
        FACTORIES,
        create_transfer,
        factory_summary_report,
        list_transfers,
    )
"""

from __future__ import annotations

from .normalize import FACTORIES
from .transfers import (
    create_transfer,
    factory_summary_report,
    list_transfers,
)

__all__ = [
    "FACTORIES",
    "create_transfer",
    "factory_summary_report",
    "list_transfers",
]
