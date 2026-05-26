## Topic

Map current inventory/location capabilities against Phase 2 event-ledger hardening. Main question: is current stock derived from events, or stored as mutable state?

## Inputs read

- `WMS charter`
- `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, `docs/SYNC_RULES.md`
- Inventory/outbound models, routes, services, and tests

## Findings

The charter target is stricter than the current implementation. Phase 2 wants inventory ledger events as source of truth and current stock as a derived view. TagLedger has movement rows, but operational current stock is stored on `InventoryLocation.quantity` and read directly by query, map, reconcile, export, inbound, outbound, and transfer paths.

Current location truth is centered on `InventoryLocation`: part, location, quantity, status, zero-stock flag, and kind. This supports stock by item/location, permanent zero-stock bins, temporary/permanent behavior, restock flags, and mixed-location warnings. Warehouse/zone/aisle/rack/bin are inferred from `location_code`.

`InventoryMovement` is the closest existing event ledger. It records movement type, part, location, links, delta, before/after quantity, operator, idempotency key, reason, and timestamp. Services still write it as an audit companion: adjust, move, reconcile, inbound, and outbound update `InventoryLocation.quantity`, then record movements.

Read paths confirm the same design. Inventory locations, map, reconcile preview, CSV export, and outbound inventory APIs all use the stored state.

Capability summary: location visibility and Excel coexistence are relatively mature; event-ledger semantics are partial. Missing Phase 2 pieces: replayable canonical ledger, projection-vs-delta tests, LPN/box identity, and over-quantity correction-before-move.

## Evidence / citations (path:line list)

- `WMS charter:73` requires ledger events as truth and current stock as derived view.
- `REQUIREMENTS.md:39` defines inventory/location scope; `REQUIREMENTS.md:45` makes zero valid; `REQUIREMENTS.md:46` requires traceable changes.
- `REQUIREMENTS.md:72` documents correction-before-move for over-quantity moves.
- `backend/app/models.py:196` defines `InventoryLocation`; `backend/app/models.py:204` stores current `quantity`; `backend/app/models.py:213` defines `InventoryMovement`; `backend/app/models.py:224` through `backend/app/models.py:230` store delta, before/after, operator, reason, timestamp.
- `backend/app/services/inventory_service/queries.py:60` selects `InventoryLocation`; `backend/app/services/inventory_service/queries.py:88` sums stored quantities.
- `backend/app/services/inventory_service/movements.py:38` reads current quantity; `backend/app/services/inventory_service/movements.py:39` mutates it; `backend/app/services/inventory_service/movements.py:42` creates movement; `backend/app/services/inventory_service/movements.py:122` rejects insufficient source.
- `backend/app/services/inventory_service/reconcile.py:65` builds preview truth from `InventoryLocation`; `backend/app/services/inventory_service/reconcile.py:479` writes `location.quantity`.
- `backend/app/services/outbound_reconciliation/inventory.py:270` reads `location.quantity`; `backend/app/services/outbound_reconciliation/inventory.py:277` writes it; `backend/app/services/outbound_reconciliation/inventory.py:292` records movement.
- `backend/app/services/inventory_service/normalize.py:80` retires empty temporary locations; `backend/app/services/inventory_service/normalize.py:83` preserves empty permanent rows.

## Open questions

- Promote `InventoryMovement` to canonical ledger, or add `InventoryEvent`?
- Add invariants proving projected stock equals summed movement deltas?
- How should LPN/box identity join the part/location quantity model?
- Fix over-quantity moves before broader ledger migration?
