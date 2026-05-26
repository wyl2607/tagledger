## Topic

Assess current Excel import preview, snapshot, apply, and reconciled export coverage for WMS MVP Slice 0. The charter requirement is Excel coexistence during rollout: import preview must be read-only, snapshots must be traceable, apply must be explicit, and export must support manual backfill.

## Inputs read

Read repository guidance and product inputs before writing: `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/SYNC_RULES.md`, `REQUIREMENTS.md`, and `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md`. Also checked `ai-trace` for TagLedger Excel/reconcile notes. Source inspection covered inventory routes, inventory services, Excel parser/export helpers, inventory UI, models, and focused tests.

## Findings

TagLedger already has a meaningful Excel coexistence slice under `/inventory`, centered on `/api/inventory/reconcile/*`. It covers CSV and XLSX parsing, read-only preview, optional snapshot recording, explicit supervisor apply, current inventory CSV export, and reconciled XLSX export.

Preview is read-only in the normal charter sense. JSON preview is exposed at `POST /api/inventory/reconcile/preview` for logged-in users. File preview is exposed at `POST /api/inventory/reconcile/preview-file` and parses `.csv` or `.xlsx` through shared parser logic. The classifier normalizes factory, part, location, and quantity, then buckets rows into `matched`, `quantity_mismatch`, `excel_missing`, and `excel_new`. Tests assert preview leaves `InventoryLocation`, `InventoryMovement`, and `AuditLog` counts unchanged and preserves stored quantities.

Snapshot traceability is present but intentionally gated. File preview can take `record_snapshot=true`; only supervisors may record a snapshot. Snapshot metadata stores filename, SHA-256 file hash, uploader, parsed row count, summary JSON, and timestamp. Snapshot items persist per-row classification, system quantity, Excel quantity, and processing status. Duplicate file hashes return the existing snapshot instead of recording a second copy. A latest-lookup API can retrieve the most recent snapshot item for a factory/part/location key. Gap: snapshots are not required for every preview or apply, and apply decisions do not currently link to `snapshot_id`; traceability is therefore available but not yet a closed provenance chain.

Apply is explicit. The UI renders per-row decision controls only for inventory managers, requires a reason and idempotency key, and posts selected decisions to `/api/inventory/reconcile/apply`. The backend requires supervisor auth. Only `quantity_mismatch` plus `use_excel` mutates inventory, and it checks that current system quantity still matches the previewed quantity before writing. Other decisions (`keep_system`, `count_review`, `mark_excel_missing`, `mark_excel_new`) are audit-only. Every apply decision writes an `inventory.reconcile.apply` audit record; applied mismatches also write `InventoryMovement` rows with `movement_type="reconcile_adjust"`.

Export coverage exists in two forms. `/api/inventory/export.csv` exports current system inventory for supervisor/manual backfill and escapes formula-risk cells. `/api/inventory/reconcile/export-file` accepts an uploaded CSV/XLSX, reuses preview classification, and returns a `tagledger-reconcile-export-YYYYMMDD.xlsx` workbook with `factory_id`, `part_key`, `location_code`, `quantity`, `excel_quantity`, `delta`, `category`, and note columns. This is useful for human reconciliation because it keeps system-vs-Excel differences visible without mutating inventory. Gap: there is no committed sample template file; the live UI placeholder and generated workbook headers are the current templates.

Overall Slice 0 status: substantially covered for planning acceptance. Remaining product hardening should require linking apply actions to snapshot IDs, deciding whether snapshot recording is mandatory for file apply/export workflows, and adding an explicit documented template/sample if operations need a stable Excel handoff contract.

## Evidence / citations (path:line list)

- `REQUIREMENTS.md:77` defines Excel coexistence and fact-source boundaries; `REQUIREMENTS.md:80` requires preview before import; `REQUIREMENTS.md:86` requires preview to avoid writes; `REQUIREMENTS.md:88` requires human apply; `REQUIREMENTS.md:90` requires snapshot metadata.
- `backend/app/routes/inventory.py:185` exposes JSON preview; `backend/app/routes/inventory.py:200` exposes supervisor apply; `backend/app/routes/inventory.py:220` exposes reconciled XLSX export; `backend/app/routes/inventory.py:245` exposes file preview with optional snapshot; `backend/app/routes/inventory.py:283` exposes latest snapshot lookup.
- `backend/app/services/inventory_excel.py:9` defines required columns; `backend/app/services/inventory_excel.py:11` allows `.csv` and `.xlsx`; `backend/app/services/inventory_excel.py:26` rejects fractional/negative quantities; `backend/app/services/inventory_excel.py:117` defines reconciled export headers; `backend/app/services/inventory_excel.py:160` renders the XLSX export.
- `backend/app/services/inventory_service/reconcile.py:30` classifies preview buckets; `backend/app/services/inventory_service/reconcile.py:147` hashes uploaded files; `backend/app/services/inventory_service/reconcile.py:203` records snapshots; `backend/app/services/inventory_service/reconcile.py:377` applies explicit decisions.
- `backend/app/models.py:233` stores snapshot metadata; `backend/app/models.py:246` stores snapshot item classifications.
- `backend/app/static/inventory.html:202` labels preview as non-writing; `backend/app/static/inventory.html:212` adds snapshot recording control; `backend/app/static/inventory.html:234` renders the apply panel; `backend/app/static/inventory.html:525` posts explicit apply decisions; `backend/app/static/inventory.html:694` exports the reconciled file.
- `backend/tests/test_inventory.py:230` proves preview classification and read-only behavior; `backend/tests/test_inventory.py:344` proves applied mismatch movement and audit; `backend/tests/test_inventory.py:588` proves audit-only non-destructive decisions; `backend/tests/test_inventory.py:858` proves snapshot metadata/latest lookup; `backend/tests/test_inventory.py:941` proves duplicate snapshot hash handling.
- `backend/tests/test_inventory_reconcile_export.py:85` proves export workbook shape; `backend/tests/test_inventory_reconcile_export.py:239` proves export requires supervisor; `backend/tests/test_inventory_reconcile_export.py:260` proves reconciled export is read-only.

## Open questions

- Should every file-based apply require a recorded `snapshot_id`, or is filename plus idempotency key enough for Slice 1?
- Should the reconciled XLSX become the official operational template, with a checked-in sample or generated download endpoint?
- Should snapshot item `processing_status` be updated after apply so unresolved Excel differences can be tracked across days?
