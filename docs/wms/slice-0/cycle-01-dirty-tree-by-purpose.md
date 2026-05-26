## Topic

Classify the `goal/l1-tagledger` dirty tree for WMS MVP Slice 0 before any product edits. The active slice worktree is clean at `origin/main`, while the referenced goal worktree has 30 commits ahead of `origin/main` and no uncommitted working-tree files by `git status --short --branch`.

## Inputs read

- `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, `docs/SYNC_RULES.md`.
- WMS charter: `WMS charter`.
- Read-only git evidence from `/Volumes/Mac扩容/workspace-sync/dev-roots/tagledger`: `status`, `log origin/main..HEAD`, `diff --stat`, `diff --name-status`, and per-commit `--name-status`.

## Findings

WIP feature work, mostly mergeable after squashing into focused feature commits:
- `783170e` copy center entry link; `5e4c08f` copy mobile picking link; `7cc6767` copy outbound check link; `2f3f694` copy workbench link; `ee31261` copy all common entry links; `c5691f8` show current entry host; `f474888` refresh runtime status; `69477af` show refresh time; `01ec2eb` copy current entry address; `2f5ff3f` link material catalog; `6524e56` copy material catalog link; `2bab0ca` copy inbound entry link; `a2bc353` copy history entry link; `85d49a6` expose LAN share links; `c40af61` copy LAN-ready entry links. Suggested write group: squash/mergeable as one portal/runtime share-link group, because all touch `backend/app/static/portal.html`, `backend/app/main.py`, and API tests around the same UX surface.
- `1f8ecd3` harden inventory export and outbound scan idempotency. Suggested write group: hold then split/mergeable. It touches database/models/routes/services/UI/tests and overlaps the WMS ledger and outbound scope; it should not be buried with portal link UX.
- `61f8ea0` build LAN URLs with actual request port. Suggested write group: mergeable with `85d49a6` runtime URL work, or squash into the share-link group if tests prove the behavior is only runtime URL correctness.

Cleanup/refactor:
- `6e209db`, `6e40beb`, `bad4bf1`, `bf4b3c6`, `151cace`, `46bea6c` are portal UI fixes around copy labels, action grouping, runtime guards, responsive tiles, and markup preservation. Suggested write group: squash with the portal feature group rather than standalone commits.
- `7d77a44` baseline snapshot is high-risk cleanup/refactor noise: large UI/style churn, i18n edits, desktop edits, docs prototype, and deletion of tracked `data/*/.gitkeep`. Suggested write group: hold or split; do not merge as-is because it crosses AGENTS groups.

Config/fixture changes:
- `9f46875` add coco sync remote helper, and `62df4ef` reject `COCO_REMOTE_NAME=origin`. Suggested write group: mergeable only as scripts/ops group after release-packaging validation; keep separate from product code.
- `fcdd56d` document coco git sync remote. Suggested write group: mergeable docs group, separate from scripts.

Dependency bumps:
- None detected in the 30-commit stack. No lockfile, pyproject, package, or requirements dependency bump appears in the per-commit touched paths.

Test additions:
- `fe7b5ef` guard portal copy links. Suggested write group: squash with portal share-link work.
- `58c65ec` adds `backend/tests/test_ocr_worker.py` and `backend/tests/test_outbound_ops_health.py`. Suggested write group: hold or mergeable as tests-only if they pass against current `origin/main`; do not squash with unrelated portal UI.

Debug noise / drop candidates:
- `7d77a44` contains the clearest debug/noise risk because it is an environment snapshot with broad unrelated edits and deleted tracked placeholders. Suggested write group: hold/drop pending manual extraction of useful UI tokens.
- No untracked files or unstaged working-tree modifications were reported in the goal worktree, so there is no separate dirty working-copy group to classify.
- The stack also includes `ff655b6` ticking completed inventory items in `REQUIREMENTS.md`; suggested write group: docs-only mergeable, but only if it matches the final accepted inventory behavior.

## Evidence / citations (path:line list)

- `AGENTS.md:20` forbids committing local databases, uploaded images, logs, screenshots, `.omx`, `.automation`, and build/test byproducts.
- `AGENTS.md:26` requires grouped commits and forbids mixing behavior/API/UI, i18n, docs, and scripts in one commit.
- `AGENTS.md:44` defines the feature/API/UI/refactor group; `AGENTS.md:74` defines i18n-only handling.
- `README.md:6` frames TagLedger as a LAN factory workbench; `README.md:16` lists `/` as the initialized center entry; `README.md:17` and `README.md:18` identify `/mobile` and `/outbound` as core flows.
- `REQUIREMENTS.md:27` through `REQUIREMENTS.md:37` list the existing page surface that portal link commits modify or expose.
- `REQUIREMENTS.md:77` through `REQUIREMENTS.md:90` define Excel coexistence and explicit apply, which makes `1f8ecd3` strategically relevant but high-blast-radius.
- `REQUIREMENTS.md:92` through `REQUIREMENTS.md:98` define picking recommendation and outbound inventory coupling, also touched by `1f8ecd3`.
- `backend/app/main.py:91` through `backend/app/main.py:113` expose runtime status and LAN/mobile/history URLs.
- `backend/app/main.py:116` through `backend/app/main.py:207` define the static route surface for portal, mobile, history, outbound, inventory, inbound, and materials.
- `backend/app/static/portal.html:178` through `backend/app/static/portal.html:191` show the copy-link buttons targeted by most portal commits.
- `backend/app/routes/inventory.py:185` through `backend/app/routes/inventory.py:218` expose reconcile preview/apply endpoints, matching the WMS charter’s Excel coexistence constraint.
- `WMS charter:153` through `WMS charter:160` requires dirty-tree classification before product edits.

## Open questions

- Should `7d77a44` be treated as a local snapshot to mine manually, or as an abandoned baseline commit to drop wholesale?
- Should portal share-link UX be preserved as its own Slice 0 cleanup PR, or deferred until the WMS shell/style slice?
- Should `1f8ecd3` be rebased onto current `origin/main` as a ledger hardening candidate, given current `origin/main` already includes later inventory reconcile snapshot work?
