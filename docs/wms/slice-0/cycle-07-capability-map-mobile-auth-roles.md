## Topic

Map TagLedger mobile UX, auth, `/workbench` routing, and role-aware guards against the WMS MVP Slice 0 target: operator, supervisor, admin, and management.

## Inputs read

Read `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, `docs/SYNC_RULES.md`, auth/workbench/mobile sources, and prior Slice 0 notes. Also ran read-only `git status --short`, `rg`, `nl`, `sed`, `ls`, and `ai-trace.sh find "tagledger mobile auth roles workbench"`; no trace hits.

## Findings

Auth is real and mostly API-enforced. Setup creates the first `manager`; login issues session and CSRF cookies; mutating methods are CSRF checked except setup/login/pairing. Shared dependencies provide login, supervisor, and manager gates. Upload, OCR reads, confirm, outbound, inventory, transfers, metrics, admin, and workbench APIs use those guards.

The current role matrix is a five-role level ladder, not the charter's four tiers. `operator` and `auditor` are level 1, `supervisor` is level 2, and `manager` plus `it_admin` are level 3. Slice 0 mapping is approximate: operator = `operator`; supervisor = `supervisor`; admin = `manager`/`it_admin`; management = missing as a distinct persona.

`/workbench` is a static shell backed by `GET /api/workbench`. The API returns user, scope, modules, personal stats, and supervisor+ global stats. Operators get mobile, outbound, personal stats, and inventory. Supervisors add inbound, materials, transfers, dashboard, and signoff. Managers add signoff and admin. The page redirects unauthenticated API calls to `/login?next=/workbench`.

Mobile UX covers safe-area layout, camera/gallery capture, compression, OCR polling, manual correction, barcode/material matches, outbound selection, lookup, location alternatives, undo, and recent records. It uses guarded APIs and redirects 401s. Gap: mobile creates a browser-local `phone-*` operator id, while non-supervisor record access is filtered by `user.username`. This can break self-read and weakens audit attribution.

Static page guards are weaker than API guards. `/mobile`, `/outbound`, `/inventory`, `/transfers`, `/dashboard`, `/admin`, and `/signoff` serve HTML without server-side role checks. Data is guarded, but unauthorized users can see shells until API calls fail.

Priority gaps: define admin vs management semantics; align mobile `operator_id` with authenticated username; document tier-to-module visibility; decide whether static routes need redirects or a shared boot guard.

## Evidence / citations (path:line list)

- `backend/app/services/auth_service.py:11` defines role levels; `backend/app/auth.py:26`, `backend/app/auth.py:46`, and `backend/app/auth.py:55` define gates.
- `backend/app/routes/auth.py:72` builds capability flags; `backend/app/routes/auth.py:114` creates setup `manager`; `backend/app/routes/auth.py:140` handles login.
- `backend/app/routes/auth.py:187` scopes assigned orders; `backend/app/routes/auth.py:193`, `backend/app/routes/auth.py:224`, and `backend/app/routes/auth.py:264` build role modules.
- `backend/app/routes/auth.py:341` returns `/api/workbench` with login required.
- `backend/app/main.py:60` enforces CSRF; `backend/app/main.py:138`, `backend/app/main.py:146`, and `backend/app/main.py:210` serve core pages.
- `backend/app/static/home.html:216` redirects unauthenticated workbench calls; `backend/app/static/home.html:274` loads `/api/workbench`.
- `backend/app/static/mobile.html:331` defines camera/gallery inputs; `backend/app/static/mobile.html:582` creates `phone-*` ids; `backend/app/static/mobile.html:798` redirects 401s.
- `backend/app/routes/upload.py:66` protects `/upload`; `backend/app/routes/jobs.py:93` filters record ownership; `backend/app/routes/confirm.py:20` protects confirmation.
- `backend/app/routes/outbound.py:112`, `backend/app/routes/inventory.py:74`, and `backend/app/routes/transfers.py:28` show outbound, inventory, and transfer guards.

## Open questions

- Should Slice 1 rename roles to four target tiers, or keep current role strings with a mapping layer?
- Is `management` read-mostly KPI/audit access, or also user administration?
- Should `/mobile` always use authenticated username for `operator_id`, with phone id only as device metadata?
- Should static page routes enforce role redirects server-side, or is API-only authorization enough for the LAN MVP?
