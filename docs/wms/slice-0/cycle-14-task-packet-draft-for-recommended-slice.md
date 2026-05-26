## Topic

Recommend one first Slice 1 task from cycle 12 or cycle 13, then draft a bounded task packet for implementation. Recommendation: choose cycle 13, inventory event-ledger tests, before cycle 12 style-system consolidation.

## Inputs read

- `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, and `docs/SYNC_RULES.md`.
- Mandatory charter: `WMS charter`.
- Prior Slice 0 notes: `docs/wms/slice-0/cycle-12-first-slice-candidate-style-system.md` and `docs/wms/slice-0/cycle-13-first-slice-candidate-event-ledger-tests.md`.
- Current inventory and outbound surfaces: `backend/app/models.py`, `backend/app/routes/inventory.py`, `backend/app/routes/outbound.py`, `backend/app/services/inventory_service/movements.py`, `backend/app/services/outbound_reconciliation/inventory.py`, `backend/tests/test_inventory.py`, and `backend/tests/test_transfers.py`.
- Read-only evidence commands: `git status --short`, `git log --oneline -5`, `rg --files`, `nl -ba`, and `ai-trace.sh find "tagledger wms slice 0 cycle"`.

## Findings

Cycle 13 should be the first Slice 1 task. It is narrower and safer than cycle 12 because it can start as test-only Group 1 work and lock down existing ledger semantics without changing user-facing layout, i18n JSON, docs, scripts, or release operations. Cycle 12 is useful, but shared style cleanup would touch multiple static pages and can easily drift into visual redesign. The WMS charter makes event ledger hardening a core domain requirement, while the current checkout already has `InventoryMovement` fields and stock-changing routes that can be verified before any larger ledger redesign.

```json
{
  "task_id": "wms-slice1-event-ledger-test-lockdown",
  "recommended_source_cycle": "cycle-13",
  "allowed_files": [
    "backend/tests/test_inventory.py",
    "backend/tests/test_transfers.py",
    "backend/tests/test_inventory_reconcile_export.py",
    "backend/app/services/inventory_service/movements.py",
    "backend/app/services/outbound_reconciliation/inventory.py"
  ],
  "forbidden_files": [
    "backend/app/static/**",
    "backend/app/static/i18n/*.json",
    "docs/**",
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
    "scripts/**",
    "config/**",
    "data/**",
    ".env*",
    ".omx/**",
    ".automation/**"
  ],
  "diff_hint": "Start by adding focused tests for manual adjustment movement fields, manual move paired movements, reconcile failure atomicity, inbound idempotency, outbound insufficient-stock atomicity, and movement ordering/filter behavior if already exposed. Prefer assertions against InventoryMovement rows and InventoryLocation quantities. Only touch the two allowed service files if the new tests expose a real defect; do not alter schemas, routes, UI, i18n, docs, scripts, deployment, or sync files.",
  "validation_commands": [
    "ruff check backend scripts",
    "PATH=.venv/bin:$PATH python -m pytest backend/tests/test_inventory.py backend/tests/test_transfers.py backend/tests/test_inventory_reconcile_export.py -q"
  ],
  "success_criteria": [
    "Manual adjust writes one manual_adjust movement with operator, reason, before_qty, after_qty, and quantity_delta matching the location change.",
    "Manual move writes linked manual_move_out and manual_move_in rows with one transfer_id and no partial mutation on invalid or insufficient moves.",
    "Reconcile preview and failed apply paths remain read-only for InventoryLocation, InventoryMovement, and AuditLog.",
    "Inbound/outbound inventory deltas are idempotent or atomic according to current helper contracts and never duplicate stock changes for the same idempotency key.",
    "All validation commands pass locally with no UI, i18n, docs, scripts, release, deploy, remote, or local data changes."
  ],
  "rollback_plan": [
    "If only tests were added, remove the new assertions or test blocks from the allowed test files.",
    "If a service fix was required, revert only the hunks in the allowed service files and rerun the validation commands.",
    "Confirm rollback with git diff --name-only showing no paths outside the allowed_files list."
  ]
}
```

## Evidence / citations (path:line list)

- `WMS charter:73` defines inventory ledger events as source of truth and current stock as a derived view.
- `WMS charter:171` starts Phase 2 event-ledger hardening and requires explicit receive, move, adjust, count, pick, pack, ship, hold, return, and scrap semantics.
- `WMS charter:213` says the first TagLedger code slice should be either style-system consolidation or inventory event-ledger tests, whichever has least dirty-tree overlap.
- `WMS charter:247` requires event-ledger acceptance evidence for receiving, move, adjustment, and reconciliation events with actor, timestamp, before/after data, and reason.
- `AGENTS.md:44` through `AGENTS.md:65` define Group 1 allowed files and forbid mixing i18n, docs, scripts, or release/deploy changes into feature/API/UI/test work.
- `README.md:6` describes TagLedger as a local factory LAN web workbench; `README.md:17` and `README.md:18` identify `/mobile` and `/outbound` as active workflow surfaces.
- `REQUIREMENTS.md:46` requires all quantity changes, location moves, and count differences to be traceable through movements or audit records.
- `REQUIREMENTS.md:72` through `REQUIREMENTS.md:75` require over-quantity moves to expose inventory differences through `manual_adjust` plus move events instead of hiding the discrepancy.
- `backend/app/models.py:196` defines `InventoryLocation`; `backend/app/models.py:213` through `backend/app/models.py:230` define movement type, part, location, order/transfer/scan links, delta, before/after quantities, operator, idempotency key, reason, and timestamp.
- `backend/app/routes/inventory.py:142` exposes `PATCH /api/inventory/locations/{location_id}`; `backend/app/routes/inventory.py:162` exposes `POST /api/inventory/move`; `backend/app/routes/inventory.py:185` and `backend/app/routes/inventory.py:200` expose reconcile preview and apply.
- `backend/app/services/inventory_service/movements.py:42` through `backend/app/services/inventory_service/movements.py:53` create `manual_adjust` movements.
- `backend/app/services/inventory_service/movements.py:143` through `backend/app/services/inventory_service/movements.py:168` create paired manual move movements.
- `backend/app/services/outbound_reconciliation/inventory.py:236` through `backend/app/services/outbound_reconciliation/inventory.py:314` applies inventory deltas and records movement rows with rollback on exceptions.
- `backend/tests/test_inventory.py:230` starts existing read-only reconcile preview coverage; `backend/tests/test_transfers.py:62` starts linked transfer movement coverage.

## Open questions

- Should over-quantity manual moves be implemented in Slice 1 if tests expose the current insufficient-inventory rejection, or should Slice 1 only document that gap and preserve current behavior?
- Should inbound receiving remain covered through existing outbound reconciliation helpers for this first packet, or wait for explicit LPN/box models in a later receiving slice?
