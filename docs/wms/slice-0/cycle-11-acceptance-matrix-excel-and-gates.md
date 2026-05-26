## Topic

Slice 0 acceptance criteria for Excel coexistence and Local gates: preview-first import, traceable snapshots, explicit privileged apply, manual backfill export, and local validation before push/PR.

## Inputs read

- Charter: `WMS charter`
- Repo docs: `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, `docs/SYNC_RULES.md`
- Code/tests: inventory route, reconcile service, models, related tests
- Read-only evidence: `git status --short`, `git ls-files`, `ai-trace`

## Findings

Excel coexistence acceptance criteria:

1. `POST /api/inventory/reconcile/preview` accepts `factory_id`, `part_key`, `location_code`, and non-negative integer `quantity`; returns `matched`, `quantity_mismatch`, `excel_missing`, `excel_new`, plus summary counts; and never writes `InventoryLocation`, `InventoryMovement`, or `AuditLog`.
2. `POST /api/inventory/reconcile/preview-file` parses CSV/XLSX through the same preview logic. Anonymous access fails with 401. It is read-only unless `record_snapshot=true`.
3. Snapshot recording is supervisor-only and stores filename, hash, actor, row count, timestamp, and item category/status. Duplicate hashes return the existing snapshot.
4. `POST /api/inventory/reconcile/apply` requires supervisor auth, `idempotency_key`, source filename, human reason, and explicit decisions. `quantity_mismatch/use_excel` updates stock only if current quantity still matches preview, then writes `reconcile_adjust` movement and `inventory.reconcile.apply` audit. Other decisions are audit-only unless a later packet expands them. Duplicate apply keys fail.
5. `POST /api/inventory/reconcile/export-file` is supervisor-only, returns XLSX for manual Excel backfill, and remains read-only.

Local gates acceptance criteria:

1. Focused tests must pass:
   `PATH=.venv/bin:$PATH python -m pytest backend/tests/test_inventory.py backend/tests/test_inventory_reconcile_export.py backend/tests/test_api.py -q -k "inventory_reconcile or reconcile_export or inventory_page_exposes_reconcile"`
2. Grouped commit policy must be checked before commit:
   `python3 ~/tools/automation/workspace-guides/skill-chains/chain-gates/grouped_commit_cycle.py --repo "$PWD" --project tagledger --dry-run`
3. Before push/PR, run `./scripts/review_push_guard.sh origin/main`. Cross-boundary behavior also needs `ruff check backend scripts`, preflight, security check, and full `pytest`.
4. Docs-only planning is Group 3: `git diff --check -- AGENTS.md CLAUDE.md README.md docs`.

## Evidence / citations (path:line list)

- `WMS charter:19`, `:248`, `:249` require Excel coexistence and gates.
- `REQUIREMENTS.md:77`-`:90` require preview-first coexistence, four classes, read-only preview, human apply, and snapshots.
- `backend/app/routes/inventory.py:185`, `:200`, `:220`, `:245` expose preview, apply, export-file, and preview-file.
- `backend/app/services/inventory_service/reconcile.py:30`, `:203`, `:377`, `:482`, `:495` cover classify, snapshot, apply, movement, audit.
- `backend/app/models.py:213`, `:233`, `:246`, `:301` define movements, snapshots, snapshot items, audits.
- `backend/tests/test_inventory.py:230`, `:310`, `:344`, `:452` verify preview read-only, auth, audit, duplicate apply.
- `backend/tests/test_api.py:246`, `:296`, `:307`, `:318` verify UI hooks, login, file-preview read-only behavior.
- `backend/tests/test_inventory_reconcile_export.py:239`, `:260` verify supervisor XLSX export and read-only behavior.
- `AGENTS.md:24`-`:32`, `:96`-`:117`, `:142`-`:149` define grouped commit, docs gate, default validation.
- `docs/SYNC_RULES.md:143`-`:150` requires tests, security check, and review-push guard before push.

## Open questions

- Should snapshot recording be mandatory, or remain a supervisor option?
- Should `count_review` create a first-class cycle-count task in Slice 1, or remain audit-only until cycle count is designed?
