## Topic

Slice 0 acceptance criteria for the charter's first two matrix rows: Receiving and Box/SKU traceability. This page defines the minimum verifiable endpoint contracts, test evidence, and schema shape needed before product implementation starts.

## Inputs read

Read `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, `docs/SYNC_RULES.md`, the mandatory charter at `WMS charter`, current backend routes/models/services/tests, `git status --short`, and `ai-trace` search for `tagledger receiving traceability` (no matching trace output).

## Findings

Current TagLedger already has authenticated OCR upload/confirmation, inventory location rows, movement rows, and an existing supervisor-only inbound inventory endpoint under `/api/outbound/inventory/inbound`. Slice 0 should not treat that endpoint as the final WMS receiving contract because it receives abstract part quantities, not a physical box/LPN. The first executable product slice needs a narrow Receiving API that creates or scans a physical box and links it to SKU/part metadata, evidence, current location, state, actor, and events.

Minimum receiving contract:

- `POST /api/wms/receipts` requires login and CSRF, accepts `lpn_code` optional for scan-or-create, `part_key` required, `quantity` positive integer, `location_code` defaulting to receiving staging, `condition` enum such as `ok|damaged|needs_review`, `source_record_id` optional for existing OCR/photo evidence, `idempotency_key` required for retry safety, and `reason` required.
- Success returns `201` or idempotent `200` with `box`, `sku`, `location`, `state`, and first `events[]`. The event must include `event_type=receive`, actor username, timestamp, quantity delta, before/after quantity where a stock row is updated, reason, and linked evidence IDs when present.
- Anonymous requests must return `401`; logged-in operator may receive; receiving must not use the current supervisor-only manual adjustment permission path. Duplicate idempotency key with same signature returns the original payload; same key with changed LPN/SKU/location/quantity returns `409`.

Minimum traceability lookup contract:

- `GET /api/wms/boxes/{lpn_code}` requires login and returns one physical box/LPN view. Payload includes `lpn_code`, `part_key`, `part_name`, `quantity`, `current_location_code`, `state`, `condition`, `created_at`, `updated_at`, `evidence[]`, and chronologically ordered `events[]`.
- `events[]` must expose at least receive and movement-style rows with `event_id`, `event_type`, `operator_id`, `created_at`, `from_location_code`, `to_location_code`, `quantity_delta`, `before_qty`, `after_qty`, `reason`, and source links such as `record_id` or `movement_id`.
- Missing LPN returns `404`; anonymous lookup returns `401`; lookup must not expose raw image paths beyond the existing authenticated image/evidence route model.

Minimum schema shape:

- New physical-box table or equivalent model keyed by normalized `lpn_code`, with `factory_id`, `part_key`, `quantity`, `current_location_code`, `state`, `condition`, optional `source_record_id`, timestamps, and creator/operator fields.
- Event storage can either extend `InventoryMovement` with LPN fields or add a WMS event table, but it must preserve actor, timestamp, event type, reason, quantity delta, before/after data when relevant, and evidence/source links. Current `InventoryMovement` lacks LPN identity, so box traceability cannot be satisfied by existing rows alone.
- Evidence links should reuse existing `Record` photo/OCR fields where possible: `Record.image_path`, `model`, `vin_or_bin`, `serial_number`, `barcodes_json`, and status already represent label evidence, but the WMS lookup must expose only authenticated, stable references.

Required test evidence:

- API tests prove unauthenticated receive and lookup return `401`, operator receive succeeds, created/idempotent receive writes one physical box and one receive event, mismatched idempotency returns `409`, and lookup returns SKU/part, current location, state, evidence reference, and linked events.
- Schema/service tests prove quantity is integer and positive, part/location codes normalize consistently with inventory services, movement/receive events include actor and before/after quantities, and existing inventory location totals update or remain explicitly decoupled by documented design.
- Regression tests should cite the existing inventory auth pattern and should not mutate current OCR, outbound, Excel, or i18n behavior.

## Evidence / citations (path:line list)

- `backend/app/auth.py:26` defines `require_login`; `backend/app/auth.py:46` defines supervisor-only dependency.
- `backend/app/main.py:194` serves `/inbound`; `backend/app/main.py:260` includes current API routers.
- `backend/app/routes/upload.py:66` defines authenticated `POST /upload` for photo/OCR records.
- `backend/app/routes/confirm.py:20` confirms OCR records under authenticated `POST /confirm/{record_id}`.
- `backend/app/routes/outbound.py:57` defines current `InboundInventoryRequest` as part/location/quantity, not LPN.
- `backend/app/routes/outbound.py:233` exposes `POST /api/outbound/inventory/inbound` and requires supervisor.
- `backend/app/routes/inventory.py:74` exposes authenticated inventory location listing.
- `backend/app/models.py:52` defines `Record` evidence fields; `backend/app/models.py:196` defines `InventoryLocation`; `backend/app/models.py:213` defines `InventoryMovement`.
- `backend/app/services/outbound_reconciliation/inventory.py:167` shows movement payload shape with before/after, actor, reason, and timestamp.
- `backend/app/services/outbound_reconciliation/inventory.py:397` implements inbound inventory without LPN identity.
- `backend/tests/test_inventory.py:150` verifies inventory map requires login; `backend/tests/test_inventory.py:185` verifies location listing requires login and allows operators.
- `backend/tests/test_inventory.py:1124` verifies move events preserve the logged-in operator; `backend/tests/test_inventory.py:1152` verifies operators cannot use manual adjustment.

## Open questions

- Should the first LPN be globally unique per factory, or reusable after a terminal shipped/scrapped state?
- Should receiving immediately update `InventoryLocation` quantity, or stay in a WMS box ledger until putaway confirms the destination?
- Which existing evidence route should become the stable public contract for box photos: `Record` image retrieval, `EvidencePhoto`, or a new WMS evidence wrapper?
