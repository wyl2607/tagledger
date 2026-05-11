from fastapi.testclient import TestClient
from sqlmodel import Session, select

from backend.app.models import OutboundScan, User
from backend.app.services.auth_service import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    create_session,
    create_user,
)
from backend.app.services.outbound_reconciliation import OutboundItem


def test_auth_pages_are_served(client: TestClient) -> None:
    for path, expected in [
        ("/login", "auth.login.title"),
        ("/setup", "auth.setup.title"),
        ("/admin", "admin.title"),
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert expected in response.text


def test_root_routes_to_setup_or_portal(
    client: TestClient,
    session: Session,
) -> None:
    first_visit = client.get("/", follow_redirects=False)
    assert first_visit.status_code == 303
    assert first_visit.headers["location"] == "/setup"

    manager = create_user(
        session,
        username="entry-manager",
        display_name="Entry Manager",
        password="entry-manager-pass",
        role="manager",
    )

    initialized_visit = client.get("/", follow_redirects=False)
    assert initialized_visit.status_code == 200
    assert "先选岗位，再开工" in initialized_visit.text
    assert "/workbench" in initialized_visit.text

    _login_as(client, session, manager)
    authenticated_visit = client.get("/", follow_redirects=False)
    assert authenticated_visit.status_code == 200
    assert "现场总入口" in authenticated_visit.text
    assert "/mobile" in authenticated_visit.text


def test_root_serves_portal_with_invalid_session_cookie(
    client: TestClient,
    session: Session,
) -> None:
    create_user(
        session,
        username="entry-invalid-cookie",
        display_name="Entry Invalid Cookie",
        password="entry-invalid-cookie-pass",
        role="manager",
    )
    client.cookies.set(SESSION_COOKIE, "stale-session-token")

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert "先选岗位，再开工" in response.text
    assert "/login" in response.text


def test_capture_preserves_legacy_ocr_demo(client: TestClient) -> None:
    response = client.get("/capture")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "demo.title" in response.text


def test_setup_creates_first_manager_and_blocks_second(
    client: TestClient,
    session: Session,
) -> None:
    setup_page = client.get("/setup")
    assert setup_page.status_code == 200
    assert "auth.setup.title" in setup_page.text

    status = client.get("/api/auth/setup-status")
    assert status.status_code == 200
    assert status.json() == {"initialized": False}

    response = client.post(
        "/api/auth/setup",
        json={
            "username": "Boss",
            "display_name": "Site Boss",
            "password": "manager-pass-123",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["username"] == "boss"
    assert payload["user"]["role"] == "manager"
    assert SESSION_COOKIE in response.cookies
    assert CSRF_COOKIE in response.cookies
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Secure" not in set_cookie
    user = session.exec(select(User).where(User.username == "boss")).one()
    assert user.display_name == "Site Boss"

    second = client.post(
        "/api/auth/setup",
        json={
            "username": "other",
            "display_name": "Other",
            "password": "manager-pass-456",
        },
    )
    assert second.status_code == 409

    blocked_setup_page = client.get("/setup", follow_redirects=False)
    assert blocked_setup_page.status_code == 303
    assert blocked_setup_page.headers["location"] == "/login"


def test_login_me_logout_and_protected_transfers(
    client: TestClient,
    session: Session,
) -> None:
    manager = create_user(
        session,
        username="auth-manager",
        display_name="Auth Manager",
        password="auth-manager-pass",
        role="manager",
    )

    assert client.get("/api/transfers").status_code == 401
    login = client.post(
        "/api/auth/login",
        json={"username": "auth-manager", "password": "auth-manager-pass"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == manager.id
    assert "mlocr_session" in login.cookies

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "auth-manager"
    current_user = client.get("/api/auth/current-user")
    assert current_user.status_code == 200
    assert current_user.json()["user"]["username"] == "auth-manager"

    transfers = client.get("/api/transfers")
    assert transfers.status_code == 200
    assert transfers.json()["transfers"] == []

    client.headers.update({CSRF_HEADER: client.cookies.get(CSRF_COOKIE)})
    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert client.get("/api/auth/me").json()["user"] is None
    assert client.get("/api/transfers").status_code == 401


def test_cookie_session_write_requests_require_csrf(
    client: TestClient,
    session: Session,
) -> None:
    manager = create_user(
        session,
        username="csrf-manager",
        display_name="CSRF Manager",
        password="csrf-manager-pass",
        role="manager",
    )
    token, _ = create_session(session, manager, ip_address="testclient", user_agent="pytest")

    client.cookies.set(SESSION_COOKIE, token)
    missing = client.post("/api/auth/logout")
    assert missing.status_code == 403
    assert missing.json()["detail"] == "CSRF validation failed"

    client.cookies.set(CSRF_COOKIE, "cookie-token")
    client.headers.update({CSRF_HEADER: "wrong-token"})
    mismatch = client.post("/api/auth/logout")
    assert mismatch.status_code == 403
    assert mismatch.json()["detail"] == "CSRF validation failed"

    client.headers.update({CSRF_HEADER: "cookie-token"})
    allowed = client.post("/api/auth/logout")
    assert allowed.status_code == 200


def test_admin_user_management_requires_manager(
    client: TestClient,
    session: Session,
) -> None:
    operator = create_user(
        session,
        username="plain-operator",
        display_name="Plain Operator",
        password="operator-pass-123",
        role="operator",
    )
    token, _ = create_session(session, operator, ip_address="testclient", user_agent="pytest")
    _set_auth_cookies(client, token)

    assert client.get("/api/admin/users").status_code == 403

    client.cookies.clear()
    manager = create_user(
        session,
        username="admin-manager",
        display_name="Admin Manager",
        password="admin-manager-pass",
        role="manager",
    )
    token, _ = create_session(session, manager, ip_address="testclient", user_agent="pytest")
    _set_auth_cookies(client, token)

    created = client.post(
        "/api/admin/users",
        json={
            "username": "worker-one",
            "display_name": "Worker One",
            "password": "worker-one-pass",
            "role": "supervisor",
            "outbound_last_order_no": "SO202605060088",
        },
    )
    assert created.status_code == 201
    user_id = created.json()["user"]["id"]
    assert created.json()["user"]["outbound_last_order_no"] == "SO202605060088"

    listed = client.get("/api/admin/users")
    assert listed.status_code == 200
    assert any(user["username"] == "worker-one" for user in listed.json()["users"])

    updated = client.patch(
        f"/api/admin/users/{user_id}",
        json={
            "status": "disabled",
            "must_change_password": True,
            "outbound_last_order_no": "SO202605060099",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["user"]["status"] == "disabled"
    assert updated.json()["user"]["outbound_last_order_no"] == "SO202605060099"


def test_protected_pages_preserve_next_redirects(client: TestClient) -> None:
    outbound = client.get("/outbound")
    assert outbound.status_code == 200
    assert "login?next=" in outbound.text
    assert "window.location.pathname" in outbound.text

    transfers = client.get("/transfers")
    assert transfers.status_code == 200
    assert "AuthUI.redirectToLogin" in transfers.text
    assert "window.location.pathname" in transfers.text


def _fake_outbound_items() -> tuple[list[OutboundItem], list[OutboundItem]]:
    return (
        [
            OutboundItem("PICKING_TOTAL", "C.P.XS.000122001", 6, "cutting", "", "RTK"),
            OutboundItem("PICKING_TOTAL", "C.P.XS.000143004", 3, "cutting", "", "Camera"),
        ],
        [
            OutboundItem("SO202605060001", "C.P.XS.000122001", 6, "shipping", "", "RTK"),
            OutboundItem("SO202605060002", "C.P.XS.000143004", 3, "shipping", "", "Camera"),
        ],
    )


def _login_as(client: TestClient, session: Session, user: User) -> None:
    token, _ = create_session(session, user, ip_address="testclient", user_agent="pytest")
    client.cookies.clear()
    _set_auth_cookies(client, token)


def _set_auth_cookies(
    client: TestClient, token: str, csrf_token: str = "pytest-csrf-token"
) -> None:
    client.cookies.set(SESSION_COOKIE, token)
    client.cookies.set(CSRF_COOKIE, csrf_token)
    client.headers.update({CSRF_HEADER: csrf_token})


def test_operator_workbench_and_outbound_scope_are_order_limited(
    client: TestClient,
    session: Session,
    monkeypatch,
) -> None:
    from backend.app.services import outbound_reconciliation

    monkeypatch.setattr(outbound_reconciliation, "load_outbound_items", _fake_outbound_items)
    operator = create_user(
        session,
        username="shipper-one",
        display_name="Shipper One",
        password="shipper-one-pass",
        role="operator",
    )
    operator.outbound_last_order_no = "SO202605060001"
    session.add(operator)
    session.add(
        OutboundScan(
            order_no="SO202605060001",
            part_code="CPXS000122001",
            source_code="C.P.XS.000122001",
            matched_code="C.P.XS.000122001",
            quantity=2,
            operator_id="shipper-one",
        )
    )
    session.add(
        OutboundScan(
            order_no="SO202605060002",
            part_code="CPXS000143004",
            source_code="C.P.XS.000143004",
            matched_code="C.P.XS.000143004",
            quantity=1,
            operator_id="other-worker",
        )
    )
    session.commit()
    _login_as(client, session, operator)

    workbench = client.get("/api/workbench")
    assert workbench.status_code == 200
    workbench_payload = workbench.json()
    assert workbench_payload["user"]["role"] == "operator"
    assert workbench_payload["scope"]["allowed_order_numbers"] == ["SO202605060001"]
    assert {module["id"] for module in workbench_payload["modules"]} == {
        "mobile",
        "outbound",
        "my_stats",
    }
    assert workbench_payload["my_stats"]["scan_quantity"] == 2
    assert workbench_payload["global_stats"] is None

    choices = client.get("/api/outbound/orders")
    assert choices.status_code == 200
    assert choices.json()["order_numbers"]["shipping"] == ["SO202605060001"]

    summary = client.get("/api/outbound/summary")
    assert summary.status_code == 200
    assert summary.json()["order_numbers"]["shipping"] == ["SO202605060001"]
    assert {row["part_code"] for row in summary.json()["part_rows"]} == {"C.P.XS.000122001"}

    leaked_query = client.get("/api/outbound/query", params={"code": "C.P.XS.000143004"})
    assert leaked_query.status_code == 200
    assert leaked_query.json()["shipping_orders"] == []
    assert leaked_query.json()["matching_other_orders"] == []

    forbidden_status = client.get("/api/outbound/orders/SO202605060002/status")
    assert forbidden_status.status_code == 403
    assert client.get("/api/transfers").status_code == 403
    assert client.get("/api/reports/factory-summary").status_code == 403


def test_operator_scope_accepts_multiple_assigned_orders(
    client: TestClient,
    session: Session,
    monkeypatch,
) -> None:
    from backend.app.services import outbound_reconciliation

    cutting_items, shipping_items = _fake_outbound_items()
    shipping_items.append(
        OutboundItem("SO202605060003", "C.P.XS.000199999", 1, "shipping", "", "Other")
    )
    monkeypatch.setattr(
        outbound_reconciliation,
        "load_outbound_items",
        lambda: (cutting_items, shipping_items),
    )
    operator = create_user(
        session,
        username="shipper-multi",
        display_name="Shipper Multi",
        password="shipper-multi-pass",
        role="operator",
        outbound_last_order_no="SO202605060001, SO202605060002",
    )
    _login_as(client, session, operator)

    workbench = client.get("/api/workbench")
    assert workbench.status_code == 200
    assert workbench.json()["scope"]["allowed_order_numbers"] == [
        "SO202605060001",
        "SO202605060002",
    ]

    choices = client.get("/api/outbound/orders")
    assert choices.status_code == 200
    assert choices.json()["order_numbers"]["shipping"] == [
        "SO202605060001",
        "SO202605060002",
    ]

    allowed_status = client.get("/api/outbound/orders/SO202605060002/status")
    assert allowed_status.status_code == 200
    forbidden_status = client.get("/api/outbound/orders/SO202605060003/status")
    assert forbidden_status.status_code == 403


def test_unassigned_operator_workbench_has_empty_scope(
    client: TestClient,
    session: Session,
    monkeypatch,
) -> None:
    from backend.app.services import outbound_reconciliation

    monkeypatch.setattr(outbound_reconciliation, "load_outbound_items", _fake_outbound_items)
    operator = create_user(
        session,
        username="unassigned-shipper",
        display_name="Unassigned Shipper",
        password="shipper-one-pass",
        role="operator",
    )
    _login_as(client, session, operator)

    workbench = client.get("/api/workbench")
    assert workbench.status_code == 200
    payload = workbench.json()
    assert payload["scope"]["allowed_order_numbers"] == []
    assert payload["global_stats"] is None

    choices = client.get("/api/outbound/orders")
    assert choices.status_code == 200
    assert choices.json()["order_numbers"]["shipping"] == []
    preference = client.get("/api/outbound/preferences/current-order")
    assert preference.status_code == 200
    assert preference.json() == {
        "selected_order_no": None,
        "saved_order_no": None,
        "fallback": False,
        "reason": "no_orders_available",
    }
    snapshots = client.get("/api/outbound/progress-snapshots")
    assert snapshots.status_code == 200
    assert snapshots.json() == {"order_no": None, "snapshots": []}
    assert (
        client.post(
            "/api/outbound/preferences/current-order",
            json={"order_no": "SO202605060001"},
        ).status_code
        == 403
    )


def test_manager_workbench_keeps_global_visibility(
    client: TestClient,
    session: Session,
    monkeypatch,
) -> None:
    from backend.app.services import outbound_reconciliation

    monkeypatch.setattr(outbound_reconciliation, "load_outbound_items", _fake_outbound_items)
    summary_calls = 0

    def fail_if_summary_is_used(*args, **kwargs):
        nonlocal summary_calls
        summary_calls += 1
        raise AssertionError("workbench must not run full outbound summary")

    monkeypatch.setattr(outbound_reconciliation, "outbound_summary", fail_if_summary_is_used)
    manager = create_user(
        session,
        username="role-manager",
        display_name="Role Manager",
        password="role-manager-pass",
        role="manager",
    )
    _login_as(client, session, manager)

    workbench = client.get("/api/workbench")
    assert workbench.status_code == 200
    payload = workbench.json()
    assert payload["scope"]["allowed_order_numbers"] is None
    assert {"admin", "dashboard", "inventory", "transfers"}.issubset(
        {module["id"] for module in payload["modules"]}
    )
    assert payload["global_stats"]["order_count"] == 2
    assert payload["global_stats"]["scan_count"] == 0
    assert "remaining_total" not in payload["global_stats"]
    assert summary_calls == 0

    summary = client.get("/api/outbound/summary")
    assert summary.status_code == 200
    assert summary.json()["order_numbers"]["shipping"] == [
        "SO202605060001",
        "SO202605060002",
    ]
    assert client.get("/api/transfers").status_code == 200
    assert client.get("/api/reports/factory-summary").status_code == 200


def test_workbench_modules_include_signoff_for_supervisor(
    client: TestClient,
    session: Session,
) -> None:
    supervisor = create_user(
        session,
        username="bridge-supervisor",
        display_name="Bridge Supervisor",
        password="bridge-supervisor-pass",
        role="supervisor",
    )
    token, _ = create_session(session, supervisor, ip_address="testclient", user_agent="pytest")
    from backend.tests.conftest import set_authenticated_session

    set_authenticated_session(client, token)

    response = client.get("/api/workbench")
    assert response.status_code == 200
    payload = response.json()
    module_ids = [m["id"] for m in payload["modules"]]
    assert "inbound" in module_ids
    assert "signoff" in module_ids
    assert payload["user"]["capabilities"]["can_manage_signoff"] is True


def test_workbench_modules_include_signoff_for_manager(
    client: TestClient,
    session: Session,
) -> None:
    manager = create_user(
        session,
        username="bridge-manager",
        display_name="Bridge Manager",
        password="bridge-manager-pass",
        role="manager",
    )
    token, _ = create_session(session, manager, ip_address="testclient", user_agent="pytest")
    from backend.tests.conftest import set_authenticated_session

    set_authenticated_session(client, token)

    response = client.get("/api/workbench")
    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["capabilities"]["can_manage_signoff"] is True
    assert "inbound" in [m["id"] for m in payload["modules"]]
    assert "signoff" in [m["id"] for m in payload["modules"]]


def test_workbench_modules_hide_signoff_for_operator(
    client: TestClient,
    session: Session,
) -> None:
    operator = create_user(
        session,
        username="bridge-operator-wb",
        display_name="Bridge Operator WB",
        password="bridge-operator-wb-pass",
        role="operator",
    )
    token, _ = create_session(session, operator, ip_address="testclient", user_agent="pytest")
    from backend.tests.conftest import set_authenticated_session

    set_authenticated_session(client, token)

    response = client.get("/api/workbench")
    assert response.status_code == 200
    payload = response.json()
    module_ids = [m["id"] for m in payload["modules"]]
    assert "inbound" not in module_ids
    assert "signoff" not in module_ids
    assert payload["user"]["capabilities"]["can_manage_signoff"] is False
