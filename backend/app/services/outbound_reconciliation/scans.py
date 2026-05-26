from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.app.models import (
    OutboundScan,
    OutboundScanEventLedger,
)

from ._helpers import (
    _scan_counts,
    _scan_to_payload,
    _source_part_key_from_scan_code,
)
from .inventory import (
    _apply_inventory_delta,
    _bootstrap_inventory_if_missing,
    _inventory_location_payload,
    _is_outbound_record_idempotency_conflict,
    _movement_payload,
    _select_location_for_outbound,
    list_alternative_locations,
)
from .normalize import (
    OutboundVerificationRequiredError,
    normalize_order_no,
)
from .orders import (
    _snapshot_to_payload,
    outbound_order_status,
    save_outbound_progress_snapshot,
)
from .query import (
    _order_required_rows,
    candidate_part_codes,
    query_outbound,
)


def _record_scan_event_ledger(
    *,
    order_no: str,
    part_code: str,
    location_code: str | None,
    source_code: str,
    matched_code: str,
    quantity: int,
    outcome: str,
    operator_id: str,
    record_id: int | None,
    scan_id: int | None,
    verification_record_id: int | None,
    session: Session,
    commit: bool = True,
) -> OutboundScanEventLedger:
    row = OutboundScanEventLedger(
        order_no=order_no,
        part_code=part_code,
        location_code=location_code,
        source_code=source_code.strip(),
        matched_code=matched_code,
        quantity=quantity,
        outcome=outcome,
        operator_id=(operator_id.strip() or "self")[:80],
        record_id=record_id,
        scan_id=scan_id,
        verification_record_id=verification_record_id,
    )
    session.add(row)
    if commit:
        session.commit()
        session.refresh(row)
    return row


def register_outbound_scan(
    *,
    order_no: str,
    code: str,
    operator_id: str,
    session: Session,
    record_id: int | None = None,
    verification_record_id: int | None = None,
    quantity: int = 1,
    location_code: str | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    selected_order = normalize_order_no(order_no)
    required_rows = _order_required_rows(selected_order)
    query_payload = query_outbound(code, selected_orders=[selected_order])
    quantity = max(1, int(quantity))
    if not required_rows:
        return {
            **query_payload,
            "scan_saved": False,
            "order_not_found": True,
            "order_status": outbound_order_status(selected_order, session),
        }
    candidates = candidate_part_codes(code)
    matched_key = next((candidate for candidate in candidates if candidate in required_rows), None)
    if matched_key is None:
        return {
            **query_payload,
            "scan_saved": False,
            "order_status": outbound_order_status(selected_order, session),
        }

    matched_row = required_rows[matched_key]
    source_part_key = _source_part_key_from_scan_code(code)
    requires_verification = bool(source_part_key and source_part_key != matched_key)
    if requires_verification and verification_record_id is None and not dry_run:
        raise OutboundVerificationRequiredError("verification_record_id is required")
    selected_location, available_locations, location_matches = _select_location_for_outbound(
        location_code=location_code,
        required_row=matched_row,
    )
    if available_locations and not selected_location:
        return {
            **query_payload,
            "scan_saved": False,
            "location_required": True,
            "available_locations": available_locations,
            "matched_part": matched_row,
            "order_status": outbound_order_status(selected_order, session),
        }
    if available_locations and not location_matches:
        return {
            **query_payload,
            "scan_saved": False,
            "location_invalid": True,
            "available_locations": available_locations,
            "requested_location_code": location_code,
            "matched_part": matched_row,
            "order_status": outbound_order_status(selected_order, session),
        }
    if record_id is not None:
        existing_statement = select(OutboundScan).where(
            OutboundScan.order_no == selected_order,
            OutboundScan.part_code == matched_key,
            OutboundScan.record_id == record_id,
            OutboundScan.status == "active",
        )
        existing_scan = session.exec(existing_statement).first()
        if existing_scan is not None:
            _record_scan_event_ledger(
                order_no=selected_order,
                part_code=matched_key,
                location_code=selected_location,
                source_code=code,
                matched_code=str(matched_row["part_code"]),
                quantity=quantity,
                outcome="idempotent_duplicate",
                operator_id=operator_id,
                record_id=record_id,
                scan_id=existing_scan.id,
                verification_record_id=verification_record_id,
                session=session,
            )
            return {
                **query_payload,
                "scan_saved": False,
                "already_recorded": True,
                "matched_part": matched_row,
                "order_status": outbound_order_status(selected_order, session),
            }
    before_counts = _scan_counts(session, selected_order)
    before_scanned = before_counts.get(matched_key, 0)
    required_qty = int(matched_row["required_qty"])
    unknown_quantity = bool(matched_row["unknown_quantity"])
    if unknown_quantity:
        return {
            **query_payload,
            "scan_saved": False,
            "quantity_unreadable": True,
            "matched_part": matched_row,
            "order_status": outbound_order_status(selected_order, session),
        }
    if not unknown_quantity and before_scanned >= required_qty:
        return {
            **query_payload,
            "scan_saved": False,
            "already_complete": True,
            "matched_part": matched_row,
            "order_status": outbound_order_status(selected_order, session),
        }
    remaining_qty = required_qty - before_scanned
    if quantity > remaining_qty:
        return {
            **query_payload,
            "scan_saved": False,
            "quantity_too_large": True,
            "requested_quantity": quantity,
            "remaining_qty": remaining_qty,
            "matched_part": matched_row,
            "order_status": outbound_order_status(selected_order, session),
        }
    if dry_run:
        return {
            **query_payload,
            "scan_saved": False,
            "preview": True,
            "location_code": selected_location,
            "requested_quantity": quantity,
            "remaining_qty": remaining_qty,
            "matched_part": matched_row,
            "requires_verification": requires_verification,
            "verification_reason": "part_mismatch" if requires_verification else None,
            "source_part_key": source_part_key,
            "order_status": outbound_order_status(selected_order, session),
        }
    inventory_location = None
    inventory_movement = None
    try:
        if selected_location:
            _bootstrap_inventory_if_missing(
                session,
                part_key=matched_key,
                location_code=selected_location,
                operator_id=operator_id,
                reason="legacy_bootstrap_from_order_requirement",
                seed_quantity=max(required_qty - before_scanned, quantity),
                commit=False,
            )
            inventory_location, inventory_movement = _apply_inventory_delta(
                session,
                movement_type="outbound",
                part_key=matched_key,
                location_code=selected_location,
                quantity_delta=-quantity,
                operator_id=operator_id,
                reason="outbound_scan",
                order_no=selected_order,
                commit=False,
            )

        scan = OutboundScan(
            order_no=selected_order,
            part_code=matched_key,
            location_code=selected_location,
            source_code=code.strip(),
            matched_code=str(matched_row["part_code"]),
            quantity=quantity,
            status="active",
            operator_id=(operator_id.strip() or "self")[:80],
            record_id=record_id,
            verification_record_id=verification_record_id,
        )
        session.add(scan)
        session.flush()
        if inventory_movement is not None:
            inventory_movement.scan_id = scan.id
            session.add(inventory_movement)
        ledger_row = _record_scan_event_ledger(
            order_no=selected_order,
            part_code=matched_key,
            location_code=selected_location,
            source_code=code,
            matched_code=str(matched_row["part_code"]),
            quantity=quantity,
            outcome="accepted",
            operator_id=operator_id,
            record_id=record_id,
            scan_id=scan.id,
            verification_record_id=verification_record_id,
            session=session,
            commit=False,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if not _is_outbound_record_idempotency_conflict(exc):
            raise RuntimeError("outbound scan integrity error") from exc
        existing_scan = session.exec(
            select(OutboundScan).where(
                OutboundScan.order_no == selected_order,
                OutboundScan.part_code == matched_key,
                OutboundScan.record_id == record_id,
                OutboundScan.status == "active",
            )
        ).first()
        _record_scan_event_ledger(
            order_no=selected_order,
            part_code=matched_key,
            location_code=selected_location,
            source_code=code,
            matched_code=str(matched_row["part_code"]),
            quantity=quantity,
            outcome="idempotent_duplicate",
            operator_id=operator_id,
            record_id=record_id,
            scan_id=existing_scan.id if existing_scan is not None else None,
            verification_record_id=verification_record_id,
            session=session,
        )
        return {
            **query_payload,
            "scan_saved": False,
            "already_recorded": True,
            "matched_part": matched_row,
            "order_status": outbound_order_status(selected_order, session),
        }
    except RuntimeError as exc:
        session.rollback()
        message = str(exc)
        if selected_location and "disabled" in message:
            return {
                **query_payload,
                "scan_saved": False,
                "location_disabled": True,
                "location_code": selected_location,
                "matched_part": matched_row,
                "order_status": outbound_order_status(selected_order, session),
            }
        raise
    except Exception:
        session.rollback()
        raise
    session.refresh(scan)
    if inventory_movement is not None:
        session.refresh(inventory_movement)
    if inventory_location is not None:
        session.refresh(inventory_location)
    session.refresh(ledger_row)
    status = outbound_order_status(selected_order, session)
    snapshot = save_outbound_progress_snapshot(
        order_no=selected_order,
        event="scan_confirmed",
        operator_id=operator_id,
        session=session,
        status=status,
        scan_id=scan.id,
        detail={"part_key": matched_key, "quantity": quantity, "source_code": code.strip()},
    )
    return {
        **query_payload,
        "scan_saved": True,
        "already_complete": False,
        "location_code": selected_location,
        "quantity": quantity,
        "requires_verification": requires_verification,
        "verification_reason": "part_mismatch" if requires_verification else None,
        "source_part_key": source_part_key,
        "matched_part": matched_row,
        "scan_id": scan.id,
        "scan": _scan_to_payload(scan),
        "ledger_event_id": ledger_row.id,
        "inventory_location": _inventory_location_payload(inventory_location)
        if inventory_location is not None
        else None,
        "inventory_movement": _movement_payload(inventory_movement)
        if inventory_movement is not None
        else None,
        "snapshot": _snapshot_to_payload(snapshot),
        "order_status": status,
    }


def preview_outbound_scan(
    *,
    order_no: str,
    code: str,
    operator_id: str,
    session: Session,
    record_id: int | None = None,
    verification_record_id: int | None = None,
    quantity: int = 1,
    location_code: str | None = None,
) -> dict[str, object]:
    payload = register_outbound_scan(
        order_no=order_no,
        code=code,
        operator_id=operator_id,
        record_id=record_id,
        verification_record_id=verification_record_id,
        quantity=quantity,
        location_code=location_code,
        session=session,
        dry_run=True,
    )
    matched_part = payload.get("matched_part")
    matched_code = ""
    if isinstance(matched_part, dict):
        matched_code = str(matched_part.get("part_code") or "")
    selected_location = str(payload.get("location_code") or "").strip() or None
    if matched_code:
        payload["alternative_locations"] = list_alternative_locations(
            session=session,
            part_key=matched_code,
            exclude_location=selected_location,
        )
    else:
        payload["alternative_locations"] = []
    return payload


def outbound_order_scans(order_no: str, session: Session) -> dict[str, object]:
    selected_order = normalize_order_no(order_no)
    statement = (
        select(OutboundScan)
        .where(OutboundScan.order_no == selected_order)
        .order_by(OutboundScan.created_at.desc(), OutboundScan.id.desc())
    )
    return {
        "order_no": selected_order,
        "scans": [_scan_to_payload(scan) for scan in session.exec(statement).all()],
        "order_status": outbound_order_status(selected_order, session),
    }
