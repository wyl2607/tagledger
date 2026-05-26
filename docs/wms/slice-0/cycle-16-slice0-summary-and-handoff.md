## Topic

Slice 0 summary and handoff for TagLedger WMS MVP: findings, chosen Slice 1 packet, unblockers, and TOP-3 follow-ups.

## Inputs read

- Charter: `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md`.
- Repo controls: `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, `docs/SYNC_RULES.md`.
- Slice 0 outputs: `cycle-01`-`02` dirty tree/merge plan, `cycle-03`-`08` capability maps, `cycle-09`-`11` acceptance matrices, `cycle-12`-`13` first-slice candidates, `cycle-14` packet, `cycle-15` risks.
- Current inventory models, routes, services, README, requirements. Checks: `git status --short`, `git ls-files`, `rg`, `nl -ba`, ai-trace.

## Findings

TagLedger already has a local-first factory workbench with auth, `/workbench`, `/mobile`, `/outbound`, `/transfers`, `/inventory`, admin, OCR, and Excel coexistence. Slice 0 found the best WMS base is inventory/location truth plus movement rows. Main gap: `InventoryLocation.quantity` is stored state, while the charter wants ledger events as source of truth.

Cycles 01-02 say not to replay raw portal/runtime commits, to drop or mine the broad snapshot manually, and to extract inventory/outbound behavior only through focused tests. Cycles 03-08 show receiving is direct inbound inventory rather than LPN task flow; putaway is manual move rather than recommendation plus scan confirmation; outbound and Excel need stronger ledger guarantees; auth roles must stay intact. Cycles 09-11 are matrices. Cycles 12-13 chose ledger tests over style consolidation because they avoid UI/i18n/docs/scripts churn. Cycles 14-15 define the packet and risks.

Chosen Slice 1 packet: `wms-slice1-event-ledger-test-lockdown` from cycle 14. Start as Group 1 test-first work. Scope is inventory tests, plus only `backend/app/services/inventory_service/movements.py` and `backend/app/services/outbound_reconciliation/inventory.py` if tests expose defects. No schemas, static HTML, i18n, docs, scripts, release/deploy/sync, remotes, or local data. Success means adjust fields, paired moves, reconcile failure atomicity, inbound/outbound idempotency or atomicity, and validation passing.

Unblock before Slice 1: confirm no unexpected dirty paths; decide whether over-quantity move preserves rejection or implements `manual_adjust` plus move; decide whether to add auth/API smoke tests; run grouped-commit dry-run. No push, PR, deploy, fetch, pull, SSH, rsync, or remote mutation.

TOP-3 follow-up slices: 1. Receiving/LPN traceability with bounded box identity and evidence. 2. Product shell/style consolidation across `/workbench`, `/inventory`, `/outbound`. 3. Excel apply/gates hardening: snapshot metadata, stale-preview rejection, export backfill, preflight coverage.

## Evidence / citations (path:line list)

- `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md:71`, `:73`, `:156`, `:213`, `:247` cover LPN identity, ledger truth, dirty-tree classification, first-slice choice, and ledger acceptance.
- `AGENTS.md:20`, `:26`, `:44`-`65` block runtime artifacts, require grouped commits, and define Group 1.
- `README.md:6`, `:15`-`18` frame the LAN workbench and surfaces.
- `REQUIREMENTS.md:46`, `:72`-`75`, `:86` require traceability, over-quantity, read-only Excel preview.
- `backend/app/models.py:196`, `:204`, `:213`-`230` define location quantity and movement fields.
- `backend/app/routes/inventory.py:142`, `:162`, `:185`, `:200` expose adjust, move, preview, apply.
- `backend/app/services/inventory_service/movements.py:42`-`53`, `:121`-`123`, `:143`-`168` show adjust rows, insufficient-move rejection, and paired moves.
- Cross-links: `docs/wms/slice-0/cycle-01-dirty-tree-by-purpose.md` through `docs/wms/slice-0/cycle-15-risk-register.md`.

## Open questions

- Should Slice 1 implement over-quantity move handling now or freeze the current rejection?
- Should Slice 1 validation include auth/API smoke tests beyond cycle 14's focused inventory commands?
- Should Slice 2 be LPN receiving or style-system consolidation?
