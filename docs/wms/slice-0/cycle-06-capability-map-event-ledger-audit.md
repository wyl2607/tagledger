## Topic

Map current event-ledger and audit coverage against the charter goal that inventory ledger events are the source of truth and current stock is derived.

## Inputs read

- `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md`
- `AGENTS.md`, `CLAUDE.md`, `README.md`, `REQUIREMENTS.md`, `docs/SYNC_RULES.md`
- `backend/app/models.py`
- `backend/app/routes/inventory.py`, `backend/app/routes/outbound.py`
- Relevant inventory, outbound, transfer, and auth services.

## Findings

TagLedger has a real quantity ledger, but current stock is not yet derived only from it. `InventoryLocation` persists mutable `quantity` and `status`; `InventoryMovement` records type, part, location, order/transfer/scan links, delta, before/after, operator string, reason, idempotency key, and timestamp. `AuditLog` is separate and richer for actor identity, but not every movement writes one.

Ledger movement types emitted: `bootstrap`, `inbound`, `outbound`, `transfer_out`, `transfer_in`, `manual_adjust`, `manual_move_out`, `manual_move_in`, `location_status`, `location_reactivate`, and `reconcile_adjust`.

Inventory-relevant audit types emitted: `inventory_inbound`, `inventory_move`, `inventory_transfer`, `inventory_reconcile`, `inventory_location_reactivate`, and `outbound_rollback`. Account/security audit events also exist, but are not inventory source-of-truth events.

Gaps:

- Missing WMS vocabulary: no explicit receive/LPN-created, putaway-confirmed, cycle-count-observed/applied, pick reserved, pack verified, shipment staged, dispatch confirmed, hold/release, return, scrap, damage, exception opened/resolved, or RMA events.
- Actor coverage is split. Movements store `operator_id` as free text; audits store `actor_user_id` and `actor_username`.
- Timestamp coverage is mostly present through `created_at`, but there is no immutable event sequence.
- Before/after coverage is strong for quantities, including reconciliation. It is weak for state-only changes: `location_status` and `location_reactivate` do not encode previous/new status in the movement row.
- Reason coverage exists, but system paths use fixed reasons such as `outbound_scan`, bootstrap, or rollback.
- Audit pairing is incomplete. `manual_adjust`, outbound scan consumption, `location_status`, and reconcile snapshot recording are not consistently paired with `AuditLog`.
- Excel coexistence is partly aligned: preview is read-only, snapshots store filename/hash/uploader/row count/summary, and apply is explicit. Apply decisions are not linked to snapshot item IDs.

## Evidence / citations (path:line list)

- `/Users/yilinwang/tagledger-slice0-loop/wms-charter.md:73` sets ledger events as source of truth; `:75` requires audit trails; `:247` requires actor, timestamp, before/after, and audit reason.
- `REQUIREMENTS.md:73` requires `manual_adjust`, `manual_move_out`, and `manual_move_in`; `:86` requires read-only preview; `:90` requires snapshot metadata.
- `backend/app/models.py:196` defines mutable inventory rows; `:213` defines `InventoryMovement`; `:233` defines reconcile snapshots; `:301` defines `AuditLog`.
- `backend/app/services/inventory_service/movements.py:42` emits `manual_adjust`; `:143` and `:156` emit move pairs; `:169` emits move audit.
- `backend/app/services/inventory_service/reconcile.py:203` records snapshots; `:482` emits `reconcile_adjust`; `:495` emits audit detail.
- `backend/app/services/outbound_reconciliation/scans.py:172` emits outbound movement during scan save.
- `backend/app/services/transfer_service/transfers.py:108` and `:125` emit transfer pairs; `:146` emits transfer audit.
- `backend/app/routes/inventory.py:200` exposes supervisor reconcile apply.

## Open questions

- Should the first code slice derive stock views from `InventoryMovement`, or first add tests proving every quantity-changing path emits complete movements?
- Should every movement require an `AuditLog`, or should system events have a documented exemption?
- What canonical event names should be reserved now for LPN, receiving, cycle count, hold, return, scrap, and exceptions?
