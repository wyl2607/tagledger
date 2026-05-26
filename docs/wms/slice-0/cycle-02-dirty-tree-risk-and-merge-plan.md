## Topic

Merge/discard plan for the cycle 01 dirty-tree classification. The classified stack was a 30-commit `goal/l1-tagledger` history ahead of `origin/main`; this checkout is now clean and contains cycle 01 as a planning commit only. This plan treats those 30 commits as candidate inputs to main, not as permission to mutate product code in Slice 0.

## Inputs read

- `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, `docs/SYNC_RULES.md`.
- Charter: `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md`.
- Cycle 01 file: `docs/wms/slice-0/cycle-01-dirty-tree-by-purpose.md`.
- Read-only git evidence: `git status --short`, current branch/log, and `git show --name-status` for the relevant integrated main commits.
- Current source citations from `backend/app/main.py`, `backend/app/static/portal.html`, and `backend/app/routes/inventory.py`.

## Findings

Low risk, already landable / already represented on main: the portal and LAN share-link work should be accepted only as a focused UI/API/test group, not as the original many tiny commits. Cycle 01 listed `783170e`, `5e4c08f`, `7cc6767`, `2f3f694`, `ee31261`, `c5691f8`, `f474888`, `69477af`, `01ec2eb`, `2f5ff3f`, `6524e56`, `2bab0ca`, `a2bc353`, `85d49a6`, `c40af61`, plus cleanup commits `6e209db`, `6e40beb`, `bad4bf1`, `bf4b3c6`, `151cace`, `46bea6c`, and tests `fe7b5ef`. Rationale: the current main-line history already contains the equivalent product surface in `3e215ba` and current code exposes runtime LAN URLs plus portal copy buttons. Action: do not re-merge the raw commits; if rebuilding from the dirty branch, squash/rebase as one Group 1 change and require the Group 1 gate. Risk: low after squashing, medium if replayed commit-by-commit because it creates review noise without extra value.

Medium risk, needs rebase before landing: `61f8ea0` can land only if rebased into the portal/runtime URL group or proven as a narrow fix. Rationale: request-port handling is visible in `runtime_status`, but it belongs with LAN share-link behavior. Action: keep with the portal group, verify route/API tests, and do not split into docs or script commits. Risk: medium because wrong host/port output affects factory mobile entry links.

High risk, requires human review before any further landing: `1f8ecd3` inventory export and outbound scan idempotency. Rationale: it crosses database models, inventory routes/services, outbound reconciliation, static UI, and tests. This overlaps the WMS charter’s ledger hardening and Excel coexistence goals, but it is not safe as a raw dirty-stack commit. Current main already contains later inventory reconcile snapshot/export work (`71330e8`), so replaying the old commit may conflict or regress the newer reconcile semantics. Action: manually compare the behavior against current `origin/main`, extract only missing testable behavior, and land as separate Group 1 commits after focused inventory/outbound tests. Risk: high.

Medium risk, can land only as separate ops/docs groups: `9f46875` and `62df4ef` sync remote helper changes, plus `fcdd56d` sync documentation. Rationale: they are useful local workflow changes but fall outside WMS product behavior and must not be mixed with UI/API commits. Action: if not already accepted, keep scripts in Group 4 and docs in Group 3 with their required gates. Risk: medium because sync tooling can affect remotes even if it is local-only.

Drop / mine manually: `7d77a44` baseline snapshot should not land as-is. Rationale: cycle 01 identified broad UI/style churn, i18n edits, desktop edits, docs prototype material, and deletion of tracked `data/*/.gitkeep`, crossing grouped-commit boundaries and repository-boundary risk. Action: drop wholesale unless a human explicitly asks to mine one narrow artifact from it. Risk: high.

Docs-only candidate: `ff655b6` requirements checkbox updates can land only if they reflect behavior already present on current main. Action: compare against current requirements and current tests; otherwise drop or rewrite as a new Slice 0 planning doc. Risk: low if factual, medium if it overstates accepted inventory behavior.

## Evidence / citations (path:line list)

- `AGENTS.md:20` blocks local DBs/uploads/logs/screenshots and other runtime artifacts from commits.
- `AGENTS.md:26` requires grouped commits and forbids mixing behavior/API/UI, i18n, docs, and scripts.
- `AGENTS.md:44` through `AGENTS.md:55` define the Group 1 backend/static/test surface; `AGENTS.md:57` through `AGENTS.md:65` forbid docs, i18n, and scripts in that group.
- `REQUIREMENTS.md:5` defines TagLedger as a LAN factory workbench with `/`, `/mobile`, `/outbound`, and `/workbench` as core entry points.
- `REQUIREMENTS.md:77` through `REQUIREMENTS.md:90` require Excel preview, explicit apply, and snapshot traceability.
- `REQUIREMENTS.md:92` through `REQUIREMENTS.md:98` connect picking recommendation and outbound inventory effects.
- `backend/app/main.py:91` through `backend/app/main.py:113` expose runtime status, base URL, LAN URL, mobile URL, and history URL.
- `backend/app/main.py:116` through `backend/app/main.py:207` define the portal, mobile, history, outbound, inventory, inbound, and materials route surface.
- `backend/app/static/portal.html:178` through `backend/app/static/portal.html:191` show the current portal entry and copy-link controls.
- `backend/app/routes/inventory.py:185` through `backend/app/routes/inventory.py:218` expose reconcile preview/apply endpoints.
- `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md:153` through `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md:160` require dirty-tree classification before product edits and identifying the first safe slice.

## Open questions

- Is `7d77a44` officially abandoned, or should a human nominate specific artifacts to extract?
- Does current `origin/main` fully cover the intended `1f8ecd3` outbound idempotency behavior after the later inventory snapshot/export work?
- Should sync remote helper work remain in TagLedger, or move under the broader automation control-plane policy instead?
