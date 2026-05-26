## Topic

Assess whether inventory event-ledger tests should be the first Slice 1 candidate after WMS MVP Slice 0. Recommendation: yes, as a test-first Group 1 slice, because it can lock down existing inventory semantics without touching UI, i18n, docs, scripts, deployment, or remote sync surfaces. It has zero current dirty-tree overlap in this checkout: `git status --short`, `git diff --stat`, `git diff --name-only`, and `git status --short -- docs/wms/slice-0 backend/tests backend/app/services backend/app/routes backend/app/models.py` returned no dirty paths before this planning file was created.

## Inputs read

Read required control documents: `WMS charter`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, and `docs/SYNC_RULES.md`. Also inspected current Slice 0 notes, inventory models, inventory routes, inventory service movement/reconcile code, outbound inventory helpers, and tests in `backend/tests/test_inventory.py`, `backend/tests/test_inventory_reconcile_export.py`, `backend/tests/test_transfers.py`, and `backend/tests/test_outbound_reconciliation.py`. Ran read-only `git status`, `git diff`, `git ls-files`, and `ai-trace.sh find "tagledger inventory event ledger tests"`; the trace search returned no matching entries.

## Findings

Event-ledger tests are feasible as the first Slice 1 candidate because the schema and partial behavior already exist. `InventoryMovement` stores movement type, part/location, links, quantity delta, before/after quantities, operator, idempotency key, reason, and timestamp. Current stock is still stored on `InventoryLocation.quantity`, so Slice 1 should not claim full ledger-as-source-of-truth yet. The first value is semantic lock-down: prove every supported stock-changing route creates the right movement and audit companion, and prove preview/export paths remain read-only.

Existing coverage is useful but uneven. `test_inventory_reconcile_preview_classifies_rows_and_is_read_only` already proves Excel preview does not mutate locations, movements, or audit logs. Reconcile apply tests cover supervisor-only apply, `reconcile_adjust` movement fields, duplicate idempotency rejection, non-destructive audit-only decisions, and CSV export reflecting applied stock. Transfer tests cover linked `transfer_out` / `transfer_in`, idempotency, insufficient inventory, and disabled-target atomicity. Missing direct lock-down: manual quantity adjustment route, manual move route, movement listing filters/order/limit, inbound idempotency behavior in `outbound_reconciliation.inventory`, outbound stock decrement movement fields, over-quantity move semantics versus the requirement, and cross-checking `sum(quantity_delta)` against before/after movement chains for a single part/location.

Recommended new tests:

- Manual adjust: `PATCH /api/inventory/locations/{id}` writes one `manual_adjust` movement with actor, reason, before/after, delta, and zero-stock/permanent visibility behavior.
- Manual move: `POST /api/inventory/move` writes paired `manual_move_out` and `manual_move_in` with one transfer id, normalized target, source/target before/after, and no partial mutation on invalid target or insufficient stock.
- Reconcile guard: existing apply coverage should add explicit stale-preview rejection and assert no new movement/audit on failure.
- Inbound/outbound helper tests: inbound with the same idempotency key returns the same movement without duplicate stock change; changed payload with same key is rejected or non-reused; outbound writes `outbound` movement with order number and fails atomically on insufficient stock.
- Ledger query: `/api/outbound/inventory/movements` filters by part/location and clamps limit, returning newest movements first.

Allowed files for the first implementation packet: `backend/tests/test_inventory.py`, optionally a new `backend/tests/test_inventory_event_ledger.py`, `backend/tests/test_transfers.py`, `backend/app/services/inventory_service/movements.py`, `backend/app/services/inventory_service/reconcile.py`, `backend/app/services/outbound_reconciliation/inventory.py`, `backend/app/routes/inventory.py`, `backend/app/routes/outbound.py`, and only if a defect requires it, `backend/app/models.py` or `backend/app/database.py`. Forbidden files: `backend/app/static/**`, `backend/app/static/i18n/*.json`, `docs/**` except the task packet itself, `README.md`, `CLAUDE.md`, `AGENTS.md`, `scripts/**`, release/deploy/sync files, remote configuration, local data, uploads, logs, screenshots, `.omx/`, and `.automation/`.

Validation for this slice should be: `ruff check backend scripts`; `PATH=.venv/bin:$PATH python -m pytest backend/tests/test_inventory.py backend/tests/test_transfers.py backend/tests/test_inventory_reconcile_export.py -q`; add any new event-ledger test file to the same command. Because this is Group 1 behavior/test work, do not mix i18n, docs, UI, or scripts in the same commit.

## Evidence / citations (path:line list)

- `WMS charter:73` says inventory ledger events are the source of truth and current stock is derived.
- `WMS charter:247` requires receiving, move, adjustment, and reconciliation events with actor, timestamp, before/after data, and reason.
- `AGENTS.md:44` and `AGENTS.md:55` allow Group 1 feature/API/service/test files; `AGENTS.md:57` through `AGENTS.md:65` forbid mixing i18n, docs, scripts, and release/deploy changes.
- `REQUIREMENTS.md:46` requires all quantity changes, moves, and count differences to be traceable; `REQUIREMENTS.md:73` defines correction-before-move for over-quantity moves.
- `backend/app/models.py:196` defines `InventoryLocation`; `backend/app/models.py:204` stores current quantity.
- `backend/app/models.py:213` defines `InventoryMovement`; `backend/app/models.py:224` through `backend/app/models.py:230` store delta, before/after, operator, idempotency, reason, and timestamp.
- `backend/app/services/inventory_service/movements.py:42` through `backend/app/services/inventory_service/movements.py:53` create `manual_adjust` movement rows.
- `backend/app/services/inventory_service/movements.py:143` through `backend/app/services/inventory_service/movements.py:168` create paired manual move movements.
- `backend/app/services/inventory_service/reconcile.py:482` through `backend/app/services/inventory_service/reconcile.py:493` create `reconcile_adjust` movement rows.
- `backend/app/services/outbound_reconciliation/inventory.py:236` through `backend/app/services/outbound_reconciliation/inventory.py:314` applies inventory deltas and records movement rows atomically.
- `backend/tests/test_inventory.py:230` through `backend/tests/test_inventory.py:307` proves reconcile preview is read-only.
- `backend/tests/test_inventory.py:344` through `backend/tests/test_inventory.py:397` verifies reconcile apply movement semantics.
- `backend/tests/test_transfers.py:62` through `backend/tests/test_transfers.py:97` verifies linked transfer movements.

## Open questions

Should Slice 1 preserve current "stored current stock plus audit movements" semantics while testing them, or start the larger redesign toward replayed projections? Should the requirement for over-quantity manual moves be implemented now, since current manual move rejects insufficient stock? Should inbound receiving be modeled through current helper functions first, or wait for explicit LPN/box domain objects?
