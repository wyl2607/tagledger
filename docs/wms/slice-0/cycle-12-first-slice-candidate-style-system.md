## Topic

Assess whether style-system consolidation is feasible as the first Slice 1
candidate for TagLedger WMS. The question is not whether to redesign the UI;
it is whether a narrow consolidation can reduce duplicated layout/status
patterns while preserving the current working pages and avoiding overlap with
uncommitted work.

## Inputs read

- `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/SYNC_RULES.md`, and
  `REQUIREMENTS.md`.
- Mandatory charter:
  `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md`.
- Current static UI sources under `backend/app/static/`, including
  `ui.css`, HTML templates, `auth-ui.js`, and `i18n.js`.
- Read-only git evidence: `git status --short`, `git ls-files`, and route/file
  searches. The checkout currently reports no dirty tracked or untracked files
  before this document is added.
- `ai-trace` search for `tagledger style system`; no prior matching trace entry
  was returned.

## Findings

Style-system consolidation is feasible as the first Slice 1 candidate, but only
as a bounded extraction/refinement pass. TagLedger already has a shared stylesheet
with root tokens, shared topbar, buttons, cards/panels, alerts, pills, tables,
and responsive primitives. That makes the first code slice lower risk than
inventing a new design system from scratch.

The fragmentation is still material. Most route pages load `ui.css` and then
define page-local CSS in `<style>` blocks. The same concepts recur under
different names: `.kpi`, `.stats-panel`, `.stat-tile`, `.pick-row`,
`.pick-summary`, `.badge`, `.pill`, `.card`, `.panel`, `.table-wrap`,
`.actions`, route-specific heads, and mobile status/result cards. Some pages use
8px radii for dense WMS panels while shared `ui.css` still uses 16px for cards,
buttons, nav controls, and alerts. That inconsistency is visible across the
workbench, inventory, outbound, and mobile flows.

JS fragmentation is a secondary but relevant part of the same problem. Shared
`auth-ui.js` centralizes auth fetch, CSRF, current-user, capability, and logout
helpers; shared `i18n.js` centralizes locale detection and DOM translation.
However, each HTML page still embeds large route scripts. The first style slice
should not extract all route JS. It should only avoid adding new per-page style
logic and, where necessary, support common state classes already emitted by the
existing scripts.

Dirty-tree overlap is currently low. `git status --short` returned empty before
this planning file, and the relevant static UI files are tracked. That makes
style-system consolidation a viable first Slice 1 candidate if the allowed edit
set is narrow and excludes product behavior, API routes, i18n JSON, docs, and
tests except focused UI smoke tests if already required by the implementation.

Recommended bounded edit scope for Slice 1:

- Allow only `backend/app/static/ui.css` plus at most three representative HTML
  pages: `home.html`, `inventory.html`, and `outbound.html`.
- Consolidate shared dense WMS primitives: page shell/head, KPI grid/tile,
  table wrapper, status/badge variants, pick/reconcile rows, and compact panel
  radii.
- Keep `/mobile` out of the first pass unless a class added to `ui.css` can be
  consumed without rewriting the mobile wizard; it has a much larger inline CSS
  and script surface.
- Do not change route behavior, API calls, i18n keys, data attributes, IDs, form
  semantics, or authorization flow.
- Validate with `ruff check backend scripts` and the existing focused pytest
  gate from Group 1 if HTML/static behavior is touched; add browser smoke only
  if the slice changes visible navigation or mobile layout.

The first Slice 1 candidate should therefore be: "extract dense WMS shared
classes from workbench/inventory/outbound into `ui.css`, then remove only the
duplicated local CSS rules that become exact consumers of those classes." This
keeps the change reviewable and avoids a broad visual rewrite.

## Evidence / citations (path:line list)

- `backend/app/main.py:49` mounts `/static`; `backend/app/main.py:138`,
  `backend/app/main.py:146`, `backend/app/main.py:170`, and
  `backend/app/main.py:186` serve `/workbench`, `/mobile`, `/outbound`, and
  `/inventory` from static HTML files.
- `backend/app/static/ui.css:1` defines shared tokens; `ui.css:27` defines the
  sticky topbar; `ui.css:142` defines `.card`/`.panel`; `ui.css:159` defines
  shared form controls; `ui.css:232` defines alerts.
- `backend/app/static/home.html:8` starts page-local CSS despite loading
  `ui.css`; `home.html:48` defines `.stats-panel`; `home.html:89` defines
  `.module-grid`; `home.html:208` starts embedded route JS.
- `backend/app/static/inventory.html:8` starts page-local CSS;
  `inventory.html:15` redefines `.filters, .panel`; `inventory.html:18`
  defines a KPI grid; `inventory.html:76` defines pick form primitives;
  `inventory.html:318` starts a long embedded route script.
- `backend/app/static/outbound.html:8` starts page-local CSS;
  `outbound.html:16` defines `.kpis`; `outbound.html:26` defines pick panel
  primitives overlapping inventory; `outbound.html:115` starts embedded route JS.
- `backend/app/static/mobile.html:9` starts the largest page-local CSS block;
  `mobile.html:489` loads shared JS; `mobile.html:491` starts the largest
  embedded script, so it should not be first-pass scope.
- `backend/app/static/auth-ui.js:37` exposes shared auth helpers; `auth-ui.js:46`
  wraps authenticated JSON fetch; `backend/app/static/i18n.js:29` loads locale
  JSON and `i18n.js:52` applies DOM translations.

## Open questions

- Should the first executable slice include `/mobile` visual cleanup, or should
  mobile remain a separate operator-flow hardening slice after desktop WMS pages
  share tokens?
- Should TagLedger adopt 8px as the default dense WMS radius in `ui.css`, or
  preserve the current 16px shared defaults and add separate compact classes?
- Is a static HTML smoke check enough for this first pass, or should the slice
  include a Playwright screenshot comparison for `/workbench`, `/inventory`, and
  `/outbound` before review?
