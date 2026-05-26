## Topic

Risk register for executing Slice 1 through mini relay, assuming the first packet is inventory event-ledger test lockdown.

## Inputs read

- Charter: `WMS charter`.
- Repo controls: `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, `docs/SYNC_RULES.md`.
- Prior packet: cycle 14 task packet.
- Sources/tests: inventory models, routes, services, and `backend/tests/test_inventory.py`.
- Read-only evidence: `git status --short`, `git diff --name-only`, `git log --oneline -5`, `rg`, `nl -ba`, and ai-trace search.

## Findings

1. Severity: High. Dirty-tree or branch overlap can invalidate mini relay output. Mitigation: start with `git status --short`, `git diff --name-only`, and `git log --oneline -5`; abort on unexpected paths.

2. Severity: High. AGENTS grouped-commit constraints are easy to violate. Slice 1 is Group 1 behavior/test work; docs, i18n, scripts, README, CLAUDE, AGENTS, and release/sync files are forbidden. Mitigation: use the cycle 14 allowlist.

3. Severity: High. Current schema is not full ledger-as-source-of-truth: `InventoryLocation.quantity` stores stock while `InventoryMovement` records deltas. Mitigation: lock down current semantics; no projection or schema redesign without a new packet.

4. Severity: Medium-high. Over-quantity manual move behavior conflicts with requirements: requirements call for `manual_adjust` plus move rows, but current service rejects insufficient inventory. Mitigation: decide before relay whether to preserve rejection or implement atomic adjustment.

5. Severity: Medium. Missing tests can let mini relay pass while changing semantics. Cycle 14 still needs stronger movement-field, atomicity, idempotency, and ordering/filter assertions. Mitigation: start test-first; touch services only for real defects.

6. Severity: Medium. Schema migration risk is latent. LPN/box identity, receiving tasks, evidence, and projections are charter goals, but current models lack LPN fields. Mitigation: forbid schema changes unless separately approved.

7. Severity: Medium. Permission regressions are plausible: operators move stock, supervisors adjust/apply/export, and inbound lives under outbound routes. Mitigation: preserve auth dependencies and consider auth/API tests.

8. Severity: Medium. Relay execution may drift into remote or PR actions. Repo rules forbid push/PR/deploy/sync without approval. Mitigation: local edits/tests only; no remote or release commands.

## Evidence / citations (path:line list)

- `WMS charter:73` defines ledger events as source of truth.
- `WMS charter:137` covers mini relay preference and bounded fallback.
- `AGENTS.md:44` through `AGENTS.md:65` define Group 1 paths and forbidden surfaces.
- `REQUIREMENTS.md:46` requires quantity/move traceability.
- `REQUIREMENTS.md:72` through `REQUIREMENTS.md:75` require over-quantity move discrepancy handling.
- `backend/app/models.py:196` and `backend/app/models.py:204` define stored current inventory quantity.
- `backend/app/models.py:213` through `backend/app/models.py:230` define movement ledger fields.
- `backend/app/services/inventory_service/movements.py:121` through `backend/app/services/inventory_service/movements.py:123` reject insufficient moves.
- `backend/app/routes/outbound.py:233` exposes inbound inventory under the outbound router.
- `docs/wms/slice-0/cycle-14-task-packet-draft-for-recommended-slice.md:21` through `docs/wms/slice-0/cycle-14-task-packet-draft-for-recommended-slice.md:42` define Slice 1 boundaries.

## Open questions

- Should Slice 1 implement over-quantity moves now, or freeze current rejection as a later behavior slice?
- Should validation expand beyond cycle 14 to include `backend/tests/test_auth.py` and `backend/tests/test_api.py`?
