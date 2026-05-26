## Topic

Verifiable Slice 0 acceptance criteria for inventory/location truth and event ledger rows.

## Inputs read

- `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md`
- `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, `docs/SYNC_RULES.md`
- Current inventory models, routes, services, UI, and tests under `backend/app/**` and `backend/tests/**`
- Prior Slice 0 notes: `docs/wms/slice-0/cycle-04-capability-map-inventory-locations.md` and `cycle-06-capability-map-event-ledger-audit.md`

## Findings

Acceptance criteria:

1. Query by item: an authenticated operator can call `GET /api/inventory/locations?part_key=CPXS000122223` and receive every visible row for that normalized item, split by `factory_id` and `location_code`, with `quantity`, `status`, `location_kind`, `zero_stock`, `restock_required`, and `updated_at`. Expected verification: total visible quantity equals the sum of returned visible rows, not a collapsed single item total.
2. Query by location: an authenticated operator can call `GET /api/inventory/location-map?factory_id=factory_a` and inspect a standard cell such as `zones.A.columns.A.racks.1.levels.1.depths.1.materials`. A location with multiple parts must list each material separately. A permanent zero-quantity location remains visible with `status=zero_stock` and `restock_required=true`; an empty temporary location is hidden unless `include_hidden=true`.
3. Event range: tests can query `InventoryMovement` rows for a time window and prove every quantity-changing operation emits ledger rows. Sample SQL: `select * from inventory_movements where created_at >= :from and created_at < :to order by created_at, id;`. Required fields per row: `id`, `factory_id`, `movement_type`, `part_key`, `location_code`, `quantity_delta`, `before_qty`, `after_qty`, `operator_id`, `reason`, `created_at`.
4. Adjustment apply: supervisor `POST /api/inventory/reconcile/apply` with `quantity_mismatch/use_excel` must update `InventoryLocation.quantity`, write one `reconcile_adjust` movement, and write one `AuditLog` with `action=inventory.reconcile.apply`; duplicate idempotency is rejected.
5. Manual move: operator `POST /api/inventory/move` must write paired `manual_move_out` and `manual_move_in` rows sharing `transfer_id`; source and target quantities must match the before/after values. Current implementation rejects insufficient source stock, so the charter-required over-quantity correction-before-move remains an explicit gap.
6. Read-only preview: `POST /api/inventory/reconcile/preview` and file preview classify rows without modifying `InventoryLocation`, `InventoryMovement`, or `AuditLog`.

Sample verification queries:

- By item API: `GET /api/inventory/locations?part_key=CPXS000122223`
- By location API: `GET /api/inventory/location-map?factory_id=factory_a&include_hidden=false`
- Latest Excel snapshot for a row: `GET /api/inventory/reconcile/latest?part_key=CPXS000122223&location_code=A-A01-023&factory_id=factory_a`
- Event range SQL: `select movement_type, part_key, location_code, quantity_delta, before_qty, after_qty, operator_id, reason, created_at from inventory_movements where part_key=:part_key and created_at between :from and :to order by created_at,id;`

Expected event payload schema for API/test assertions:

```json
{
  "id": 1,
  "factory_id": "factory_a",
  "event_type": "inventory_movement",
  "movement_type": "manual_adjust|manual_move_out|manual_move_in|reconcile_adjust",
  "part_key": "CPXS000122223",
  "location_code": "A-A01-023",
  "quantity_delta": 2,
  "before_qty": 5,
  "after_qty": 7,
  "operator_id": "inventory-supervisor",
  "reason": "daily stocktake; source=stocktake.csv",
  "idempotency_key": "reconcile:...",
  "transfer_id": "mv-...",
  "scan_id": null,
  "order_no": null,
  "created_at": "2026-05-26T10:00:00+00:00",
  "audit": {
    "action": "inventory.reconcile.apply",
    "actor_username": "inventory-supervisor",
    "target_type": "inventory_reconcile",
    "target_id": "reconcile:...",
    "detail_json": {
      "category": "quantity_mismatch",
      "decision": "use_excel",
      "status": "applied",
      "system_quantity": 5,
      "excel_quantity": 7,
      "before_qty": 5,
      "after_qty": 7
    }
  }
}
```

## Evidence / citations (path:line list)

- `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md:73` requires ledger events as source of truth; `:88` requires item/location queries and permanent empty locations; `:247` requires actor, timestamp, before/after data, and audit reason.
- `REQUIREMENTS.md:39` defines inventory by material, location, and quantity; `:45` says zero is valid; `:46` requires traceability; `:72` documents correction-before-move.
- `backend/app/models.py:196` defines `InventoryLocation`; `backend/app/models.py:213` defines `InventoryMovement`; `backend/app/models.py:301` defines `AuditLog`.
- `backend/app/routes/inventory.py:74` exposes item/location listing; `:93` exposes the location map; `:162` exposes move; `:200` exposes reconcile apply; `:283` exposes latest snapshot lookup.
- `backend/app/services/inventory_service/queries.py:51` filters by factory/item; `:74` computes permanent restock rows.
- `backend/app/services/inventory_service/normalize.py:80` retires empty temporary locations; `:83` preserves permanent zero-stock locations; `:119` defines current movement payload fields.
- `backend/app/services/inventory_service/movements.py:42` emits `manual_adjust`; `:143` and `:156` emit paired move events; `:169` writes move audit.
- `backend/app/services/inventory_service/reconcile.py:30` previews read-only classifications; `:482` emits `reconcile_adjust`; `:495` writes audit detail; `:362` rejects duplicate apply.
- `backend/tests/test_inventory.py:230` proves preview is read-only; `:344` proves reconcile apply movement and audit; `:452` proves duplicate idempotency rejection.

## Open questions

- Should Slice 0 expose an event-ledger API, or keep event range verification at the database/test layer?
- Should `InventoryMovement` become the canonical event table, or should a new event table wrap movement plus audit payloads?
- Should over-quantity move behavior be fixed in Slice 0 before broader receiving/LPN work begins?
