## Topic

Map TagLedger outbound, pick, pack, and dispatch capabilities against the WMS charter Phase 4 target: convert orders into pick tasks, verify packages, stage by carrier, reconcile expected vs scanned packages before dispatch, and keep carrier integrations behind adapter boundaries.

## Inputs read

Read `WMS charter`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, `docs/SYNC_RULES.md`, current route/template sources for `/outbound`, `/mobile`, `/transfers`, inventory pick recommendations, and existing Slice 0 docs. Also ran read-only `git status --short`, `git ls-files`, and `ai-trace.sh find "tagledger outbound mobile transfers WMS Phase 4"`; the trace search returned no matching entries.

## Findings

Current outbound is an order reconciliation and scan-confirmation workflow, not a complete Phase 4 pick-pack-dispatch workflow. `GET /outbound` serves `outbound.html`; `/api/outbound/*` exposes authenticated order summaries, order choices, scoped order access, query, status, scan history, remaining CSV, progress snapshots, scan preview, scan registration, scan void, supervisor completion, rollback, batch detail, and manual quantity set. This covers "expected order line vs scanned item" and some completion control.

Pick capability exists as read-only recommendation, not executable pick tasks. The outbound page can generate recommendations per part/quantity and calls `/api/inventory/pick-recommendations`; the inventory route requires login and returns `recommend_inventory_picks`. The UI displays temporary/permanent location, available quantity, suggested pick quantity, and shortages. It does not create durable `PickTask` rows, assign operators, require source-location scan confirmation, reserve inventory, or track task states such as open, picked, short, substituted, or cancelled.

Mobile outbound support is stronger than desktop picking. `GET /mobile` serves a phone workflow with photo/OCR/barcode capture, current outbound order selection, manual SKU/barcode lookup, order preview, scan preview/registration, scan history, undo for active scans, alternative location switching, and inventory impact display. This can support floor scanning against a selected order, but it still records scans against order/part/location rather than package/LPN/task objects.

Packing is mostly absent. There are OCR record fields and a legacy demo `packageCode` field, but the outbound route/template set does not model packages, carton contents, package photos, pack verification, label printing/storage, carrier label reference, tracking number, dimensional weight, or package close/reopen states. The existing `OutboundScan`/batch concepts help group scans, but they are not package manifests.

Dispatch and carrier staging are absent. `/transfers` is cross-factory stock movement for supervisors and writes transfer records; it is not dispatch staging. No current route or template found for carrier lanes, DHL/DPD/UPS staging areas, expected-vs-scanned package reconciliation, truck handoff, dispatch close, manifest generation, manifest export, or carrier adapter boundaries. The only "manifest" hits are unrelated sustainability export tests.

Phase 4 gap summary: keep existing outbound scan/order reconciliation as a useful base, add explicit domain objects before code changes: `PickTask`, `Package`, `PackageLine`, `Shipment`, `CarrierLane`, `DispatchManifest`, and package scan events. Carrier integrations should remain optional adapters after local package/manifest truth exists.

## Evidence / citations (path:line list)

- `WMS charter:151` defines Phase 4 outbound pick, pack, stage, dispatch goals.
- `backend/app/main.py:146` serves `/mobile`; `backend/app/main.py:170` serves `/outbound`; `backend/app/main.py:178` serves `/transfers`.
- `backend/app/routes/outbound.py:44` defines `/api/outbound`; `backend/app/routes/outbound.py:112` scopes non-supervisors to assigned orders.
- `backend/app/routes/outbound.py:149` returns outbound summary; `backend/app/routes/outbound.py:168` returns order choices; `backend/app/routes/outbound.py:305` queries part/SKU/order membership.
- `backend/app/routes/outbound.py:323` returns order status; `backend/app/routes/outbound.py:336` returns scans; `backend/app/routes/outbound.py:349` exports remaining CSV; `backend/app/routes/outbound.py:503` registers scans; `backend/app/routes/outbound.py:527` previews scans.
- `backend/app/routes/outbound.py:389` voids batches; `backend/app/routes/outbound.py:422` sets part quantity; `backend/app/routes/outbound.py:443` completes orders; `backend/app/routes/outbound.py:460` rolls back orders; these are supervisor controls, not package dispatch controls.
- `backend/app/routes/inventory.py:110` exposes `/api/inventory/pick-recommendations` as a login-required read API.
- `backend/app/static/outbound.html:71` renders order selection; `backend/app/static/outbound.html:81` renders scan/query; `backend/app/static/outbound.html:96` renders part quantity reconciliation.
- `backend/app/static/outbound.html:99` renders outbound pick recommendations; `backend/app/static/outbound.html:202` lets a reconciliation row seed a recommendation; `backend/app/static/outbound.html:269` calls `/api/inventory/pick-recommendations`.
- `backend/app/static/mobile.html:346` renders the mobile outbound scan panel; `backend/app/static/mobile.html:432` embeds outbound check results in the edit step.
- `backend/app/static/mobile.html:743` renders scan history; `backend/app/static/mobile.html:679` renders alternative locations; `backend/app/static/mobile.html:646` renders inventory impact for outbound scans.
- `backend/app/routes/transfers.py:28` creates transfer records; `backend/app/routes/transfers.py:49` lists transfer history; `backend/app/static/transfers.html:47` states transfers write source-out and target-in movements.

## Open questions

- Should the first Phase 4 slice create durable `PickTask` records from current order lines, or first wrap existing scan rows with task-state semantics?
- Is an LPN/package code mandatory before packing, or can MVP start with order plus package number and add LPN later?
- Which carrier lanes are required on day one: named carriers only, warehouse staging zones only, or both?
- Should dispatch manifest completion be supervisor-only, and should it block when expected packages are missing or merely record an exception?
