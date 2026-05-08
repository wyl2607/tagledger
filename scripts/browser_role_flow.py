from __future__ import annotations

import json
import os
import statistics
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, expect, sync_playwright

BASE_URL = os.getenv("TAGLEDGER_BROWSER_BASE_URL", "http://127.0.0.1:8031").rstrip("/")
ARTIFACT_DIR = Path("data/screenshots/browser-role-flow")
LOCALE_STORAGE_KEY = "tagledger.locale"
TRANSFER_PART = "CPXS000122001"


def request_json(path: str, *, data: dict[str, object] | None = None) -> dict[str, object]:
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())


def login(
    page: Page,
    username: str,
    password: str,
    *,
    expected_path: str = "/workbench",
) -> None:
    if "/login" not in page.url:
        page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    page.locator("#username").fill(username)
    page.locator("#password").fill(password)
    page.locator("#loginForm button[type='submit']").click()
    page.wait_for_url(f"**{expected_path}", timeout=10_000)
    if expected_path == "/workbench":
        expect(page.locator("#moduleGrid")).to_be_visible(timeout=10_000)
        expect(page.locator("#userBadge")).not_to_contain_text("加载中", timeout=10_000)


def assert_no_console_errors(messages: list[str]) -> None:
    errors = [message for message in messages if message]
    if errors:
        raise AssertionError("console errors:\n" + "\n".join(errors))


def attach_console_capture(context: BrowserContext, messages: list[str]) -> None:
    context.on(
        "page",
        lambda page: page.on(
            "console",
            lambda msg: (
                messages.append(f"{page.url}: {msg.text}")
                if msg.type in {"error", "warning"}
                else None
            ),
        ),
    )


def post_json_from_page(page: Page, path: str, data: dict[str, object]) -> dict[str, object]:
    return page.evaluate(
        """async ({ path, data }) => {
            const csrfToken = document.cookie
                .split(';')
                .map((item) => item.trim())
                .find((item) => item.startsWith('tagledger_csrf='))
                ?.slice('tagledger_csrf='.length) || '';
            const headers = { 'Content-Type': 'application/json' };
            if (csrfToken) headers['X-CSRF-Token'] = decodeURIComponent(csrfToken);
            const response = await fetch(path, {
                method: 'POST',
                headers,
                body: JSON.stringify(data),
            });
            const text = await response.text();
            const payload = text ? JSON.parse(text) : {};
            if (!response.ok) {
                throw new Error(payload.detail || `HTTP ${response.status}`);
            }
            return payload;
        }""",
        {"path": path, "data": data},
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    setup = request_json(
        "/api/auth/setup",
        data={
            "username": "browser-manager",
            "display_name": "Browser Manager",
            "password": "browser-manager-pass",
        },
    )
    if setup["user"]["role"] != "manager":
        raise AssertionError(setup)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        anonymous = browser.new_context(viewport={"width": 1366, "height": 900})
        anonymous.add_init_script(f"window.localStorage.setItem({LOCALE_STORAGE_KEY!r}, 'zh');")
        anonymous_page = anonymous.new_page()
        anonymous_page.goto(f"{BASE_URL}/transfers", wait_until="networkidle")
        anonymous_page.wait_for_url("**/login?next=%2Ftransfers", timeout=10_000)
        login(anonymous_page, "browser-manager", "browser-manager-pass", expected_path="/transfers")
        expect(anonymous_page.locator("#createTransferCard")).to_be_visible(timeout=10_000)
        anonymous.close()

        context = browser.new_context(viewport={"width": 1366, "height": 900})
        context.add_init_script(f"window.localStorage.setItem({LOCALE_STORAGE_KEY!r}, 'zh');")
        page = context.new_page()
        console_errors: list[str] = []
        attach_console_capture(context, console_errors)
        page.on(
            "console",
            lambda msg: (
                console_errors.append(msg.text) if msg.type in {"error", "warning"} else None
            ),
        )
        login(page, "browser-manager", "browser-manager-pass")
        expect(page.get_by_text("全局录入和调拨状态，一屏看清")).to_be_visible()
        expect(page.get_by_text("账号与权限")).to_be_visible()

        page.goto(f"{BASE_URL}/outbound", wait_until="networkidle")
        first_order = page.locator("[data-order-choice]").first.input_value()
        if not first_order:
            raise AssertionError("no outbound order found in workbook")
        second_order = first_order
        if page.locator("[data-order-choice]").count() > 1:
            second_order = page.locator("[data-order-choice]").nth(1).input_value()
        assigned_orders = [first_order]
        if second_order and second_order != first_order:
            assigned_orders.append(second_order)
        assigned_order_text = ", ".join(assigned_orders)

        page.goto(f"{BASE_URL}/admin", wait_until="networkidle")
        expect(page.locator("#createUserForm")).to_be_visible()
        page.locator("#username").fill("shipper-one")
        page.locator("#displayName").fill("Shipper One")
        page.locator("#role").select_option("operator")
        page.locator("[data-testid='assigned-order-input']").fill(assigned_order_text)
        page.locator("#password").fill("shipper-one-pass")
        page.locator("#createUserForm button[type='submit']").click()
        expect(page.locator("#createStatus")).not_to_be_empty(timeout=10_000)
        expect(page.locator("#userRows")).to_contain_text("shipper-one")
        page.screenshot(path=ARTIFACT_DIR / "admin-users.png", full_page=True)

        page.locator("#logoutBtn").click()
        page.wait_for_url("**/login", timeout=10_000)
        login(page, "shipper-one", "shipper-one-pass")
        expect(page.get_by_text("只看你的发货单，先把当前单做完")).to_be_visible()
        expect(page.get_by_text(f"分配单号 {assigned_order_text}")).to_be_visible()
        expect(page.get_by_text("账号与权限")).not_to_be_visible()
        expect(page.get_by_text("跨场子调拨")).not_to_be_visible()
        page.screenshot(path=ARTIFACT_DIR / "operator-workbench-desktop.png", full_page=True)

        page.goto(f"{BASE_URL}/transfers", wait_until="networkidle")
        expect(page.locator("#transferListCard")).to_contain_text("权限不足")
        expect(page.locator("#createTransferCard")).to_be_hidden()
        page.screenshot(path=ARTIFACT_DIR / "operator-transfer-denied.png", full_page=True)

        page.goto(f"{BASE_URL}/outbound", wait_until="networkidle")
        order_choices = page.locator("[data-order-choice]")
        choice_count = order_choices.count()
        if choice_count != len(assigned_orders):
            raise AssertionError(
                f"operator saw {choice_count} orders, expected {len(assigned_orders)}"
            )
        visible_orders = [order_choices.nth(index).input_value() for index in range(choice_count)]
        if visible_orders != assigned_orders:
            raise AssertionError("operator outbound order scope changed unexpectedly")
        page.screenshot(path=ARTIFACT_DIR / "operator-outbound.png", full_page=True)

        operator_mobile = browser.new_context(viewport={"width": 390, "height": 844})
        operator_mobile.add_init_script(
            f"window.localStorage.setItem({LOCALE_STORAGE_KEY!r}, 'zh');"
        )
        attach_console_capture(operator_mobile, console_errors)
        operator_mobile_page = operator_mobile.new_page()
        login(operator_mobile_page, "shipper-one", "shipper-one-pass")
        operator_mobile_page.goto(f"{BASE_URL}/mobile#capture", wait_until="networkidle")
        mobile_order_options = operator_mobile_page.locator("#outboundOrderSelect option")
        visible_mobile_orders = [
            mobile_order_options.nth(index).get_attribute("value")
            for index in range(mobile_order_options.count())
        ]
        for order in assigned_orders:
            if order not in visible_mobile_orders:
                raise AssertionError(f"operator mobile missing assigned order {order}")
        with operator_mobile_page.expect_response(
            lambda response: (
                f"/api/outbound/orders/{first_order}/status" in response.url
                and response.status == 200
            ),
            timeout=20_000,
        ):
            operator_mobile_page.locator("#outboundOrderSelect").select_option(first_order)
        expect(operator_mobile_page.locator("#outboundOrderSelect")).to_have_value(first_order)
        expect(operator_mobile_page.locator("#outboundCaptureSummary")).to_contain_text(
            first_order,
            timeout=20_000,
        )
        expect(operator_mobile_page.locator("#manualMaterialCode")).to_be_visible(timeout=10_000)
        quick_scan_buttons = operator_mobile_page.locator("[data-manual-code]")
        expect(quick_scan_buttons.first).to_be_visible(timeout=20_000)
        quick_scan_buttons.first.click()
        expect(operator_mobile_page.locator("#outboundCaptureScanResult")).to_be_visible(
            timeout=10_000
        )
        location_switches = operator_mobile_page.locator("[data-switch-location]")
        if location_switches.count():
            location_switches.first.click()
        expect(operator_mobile_page.locator("#outboundConfirmScanBtn")).to_be_visible(
            timeout=10_000
        )
        with operator_mobile_page.expect_response(
            lambda response: "/api/outbound/scan" in response.url
            and response.request.method == "POST"
            and response.status == 200,
            timeout=20_000,
        ):
            operator_mobile_page.locator("#outboundConfirmScanBtn").click()
        expect(operator_mobile_page.locator("#outboundCaptureScanResult")).to_contain_text(
            "已出库",
            timeout=20_000,
        )
        if operator_mobile_page.locator("#outboundCompleteOrderBtn").count():
            raise AssertionError("operator mobile can see complete-order supervisor action")
        if operator_mobile_page.locator("#outboundRollbackOrderBtn").count():
            raise AssertionError("operator mobile can see rollback supervisor action")
        if operator_mobile_page.locator("#outboundSyncMarksBtn").count():
            raise AssertionError("operator mobile can see sync-marks supervisor action")
        if operator_mobile_page.locator("[data-set-complete]").count():
            raise AssertionError("operator mobile can see line-complete supervisor action")
        if operator_mobile_page.locator("[data-edit-qty]").count():
            raise AssertionError("operator mobile can see edit-quantity supervisor action")
        if operator_mobile_page.locator("[data-reset-qty]").count():
            raise AssertionError("operator mobile can see reset-quantity supervisor action")
        operator_mobile_page.screenshot(path=ARTIFACT_DIR / "operator-mobile.png", full_page=True)
        operator_mobile.close()

        context.clear_cookies()
        login(page, "browser-manager", "browser-manager-pass")
        page.goto(f"{BASE_URL}/admin", wait_until="networkidle")
        assigned_value = page.locator("input[data-assigned-order]").first.input_value()
        saved_orders = [value.strip() for value in assigned_value.split(",") if value.strip()]
        if saved_orders != assigned_orders:
            raise AssertionError(
                f"assigned order value mismatch: {saved_orders} != {assigned_orders}"
            )

        page.goto(f"{BASE_URL}/transfers", wait_until="networkidle")
        expect(page.locator("#createTransferCard")).to_be_visible(timeout=10_000)
        post_json_from_page(
            page,
            "/api/outbound/inventory/inbound",
            {
                "part_key": TRANSFER_PART,
                "location_code": "QA-A-01",
                "quantity": 5,
                "operator_id": "browser-manager",
                "reason": "browser_role_flow_seed",
            },
        )
        page.locator("#transferPart").fill(TRANSFER_PART)
        page.locator("#transferQty").fill("1")
        page.locator("#transferReason").fill("browser_role_flow")
        page.locator("#createTransferBtn").click()
        expect(page.locator("#createResult")).to_contain_text("tf-", timeout=10_000)
        expect(page.locator("#transferList")).to_contain_text("browser_role_flow")
        page.screenshot(path=ARTIFACT_DIR / "manager-transfer-created.png", full_page=True)

        mobile = browser.new_context(viewport={"width": 390, "height": 844})
        mobile.add_init_script(f"window.localStorage.setItem({LOCALE_STORAGE_KEY!r}, 'zh');")
        mobile_page = mobile.new_page()
        mobile_page.goto(f"{BASE_URL}/login", wait_until="networkidle")
        mobile_page.screenshot(path=ARTIFACT_DIR / "login-mobile.png", full_page=True)
        mobile.close()

        latencies = []
        for _ in range(40):
            start = time.perf_counter()
            page.goto(f"{BASE_URL}/workbench", wait_until="networkidle")
            expect(page.locator("#moduleGrid")).to_be_visible()
            latencies.append((time.perf_counter() - start) * 1000)
        p95 = statistics.quantiles(latencies, n=20)[18]
        if p95 > 1500:
            raise AssertionError(f"workbench browser p95 too slow: {p95:.1f}ms")

        assert_no_console_errors(console_errors)
        browser.close()

    print(
        json.dumps(
            {
                "ok": True,
                "assigned_order": first_order,
                "workbench_p95_ms": round(p95, 1),
                "screenshots": str(ARTIFACT_DIR),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
