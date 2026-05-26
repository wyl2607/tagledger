## Topic

Capability map for TagLedger receiving and putaway against the Industrial WMS Development Program Phase 3 target: receiving tasks, LPN creation/scan, photo capture, condition flags, putaway recommendations, permanent vs temporary location rules, empty permanent-location visibility, and movement-event evidence.

## Inputs read

Read the mandatory charter at `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md`, plus `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, `docs/SYNC_RULES.md`, and current TagLedger source/tests under `backend/app`, `backend/tests`, and `docs/wms/slice-0`. Also ran read-only `git status --short`, `git ls-files`, and `ai-trace.sh find "tagledger receiving putaway wms"`; the trace search returned no matching entries.

## Findings

Exists: TagLedger has a minimal stock-receiving path, but it is modeled as direct inventory inbound rather than WMS receiving tasks. `/inbound` serves `backend/app/static/inbound.html`, a supervisor-gated "purchase inbound" form with part/SKU, location, quantity, reason, and generated idempotency key. It posts to `POST /api/outbound/inventory/inbound`, which requires `require_supervisor`, writes an `inbound` `InventoryMovement`, creates/updates `InventoryLocation`, and records an `AuditLog` with movement id, location id, part, location, quantity, idempotency key, and request signature. Tests verify movement creation, authenticated operator attribution, rollback on movement failure, and idempotency behavior.

Exists: Putaway-adjacent inventory movement exists. `POST /api/inventory/move` moves quantity from a source `InventoryLocation` to a target code, creates target locations when needed, and writes paired `manual_move_out` / `manual_move_in` events. Operators can move stock, while manual quantity adjustment is supervisor-only. Permanent vs temporary location behavior is implemented: temporary locations retire and become hidden at zero quantity, while permanent zero-stock locations stay visible and set `restock_required`.

Exists: Location truth is stronger than receiving workflow. `InventoryLocation` stores factory, part, location code, quantity, status, zero-stock flag, and `location_kind`; `InventoryMovement` stores movement type, part, location, quantity delta, before/after quantities, operator, reason, idempotency key, and timestamps. `/api/inventory/locations`, `/api/inventory/location-map`, and `/inventory` expose stock lists, a computed 2D map, restock warnings, mixed-location warnings, temporary/upstairs/unresolved buckets, Excel reconciliation, and read-only pick recommendations. Location parsing supports standard A/B rack codes and temporary keywords such as TMP, receiving door, staged, and pending putaway.

Partial: Receiving does not yet match the Phase 3 operator workflow. It accepts part/location/quantity directly and can be used to place goods into a receiving or QA location, but there is no `ReceivingTask`, ASN/purchase-order intake, expected-vs-received line state, receiving staging status, or task queue. The endpoint lives under `/api/outbound/inventory/inbound`, which is historically practical but not a clean inbound domain boundary.

Partial: Putaway is manual movement, not recommendation-driven putaway. TagLedger can classify permanent vs temporary locations, preserve empty permanent bins, and sort locations for pick recommendations, but no API recommends a putaway destination based on SKU, zone, empty permanent bin, temporary overflow, mixed-location risk, or operator scan confirmation. `/api/inventory/move` confirms movement by source location id and typed target location, not by scanning both LPN and destination.

Missing: LPN/box identity is absent from receiving and movement models. `Record` captures OCR label fields and image path; `OutboundScan` captures outbound part scans; inventory rows are keyed by `part_key` plus `location_code`. There is no LPN table, box code, parent/child package identity, per-LPN quantity, or LPN-level movement ledger.

Missing: Phase 3 receiving evidence is not represented. Current OCR/mobile flows capture photos for label records, and return signoff has evidence-photo models, but inbound stock receiving has no photo upload, receiving-condition flags, damage/hold markers, lot/batch/serial capture, or evidence attachment linked to the inbound movement.

## Evidence / citations (path:line list)

- `backend/app/main.py:194` serves `/inbound`; `backend/app/main.py:186` serves `/inventory`.
- `backend/app/static/inbound.html:61` defines the inbound form; `backend/app/static/inbound.html:145` posts to `/api/outbound/inventory/inbound`; `backend/app/static/inbound.html:171` gates on `can_manage_inventory`.
- `backend/app/routes/outbound.py:57` defines `InboundInventoryRequest`; `backend/app/routes/outbound.py:233` defines `POST /api/outbound/inventory/inbound`.
- `backend/app/services/outbound_reconciliation/inventory.py:397` implements `inbound_inventory`; `backend/app/services/outbound_reconciliation/inventory.py:439` applies the stock delta; `backend/app/services/outbound_reconciliation/inventory.py:451` writes the inbound audit log.
- `backend/app/models.py:196` defines `InventoryLocation`; `backend/app/models.py:213` defines `InventoryMovement`; neither includes LPN, receiving task, condition, or evidence fields.
- `backend/app/routes/inventory.py:74` lists locations; `backend/app/routes/inventory.py:93` returns the location map; `backend/app/routes/inventory.py:162` moves inventory.
- `backend/app/services/inventory_service/movements.py:101` implements manual location movement; `backend/app/services/inventory_service/normalize.py:71` applies temporary/permanent visibility rules.
- `backend/app/services/location_profile.py:6` parses standard location codes; `backend/app/services/location_profile.py:10` lists temporary-location keywords.
- `backend/app/services/location_map.py:154` builds the inventory map and buckets temporary/upstairs/unresolved locations.
- `backend/tests/test_inventory.py:1521` verifies inbound movement and quantity-on-hand; `backend/tests/test_inventory.py:1612` verifies inbound idempotency; `backend/tests/test_inventory.py:1291` verifies paired movement records; `backend/tests/test_inventory.py:1326` verifies temporary retirement and permanent zero-stock visibility.
- `backend/tests/test_api.py:459` verifies `/inbound` serves HTML and references the inbound API; `backend/tests/test_api.py:625` checks inventory/inbound UI capability gates.

## Open questions

- Should Slice 1 introduce clean `/api/inbound/*` routes while keeping the current outbound-namespaced endpoint as a compatibility wrapper?
- Is LPN the first-class receiving object for all inbound goods, or only for cartons/pallets where SKU quantity may be unknown at arrival?
- Which receiving evidence is mandatory for MVP: photo, condition, lot/batch/serial, supplier/order reference, or all of them?
