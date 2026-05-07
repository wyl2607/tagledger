from __future__ import annotations

import json
import os
import statistics
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

BASE_URL = os.getenv("TAGLEDGER_BROWSER_BASE_URL", "http://127.0.0.1:8031").rstrip("/")
ARTIFACT_DIR = Path("data/screenshots/browser-role-flow")


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


def login(page: Page, username: str, password: str) -> None:
    page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    page.locator("#username").fill(username)
    page.locator("#password").fill(password)
    page.locator("#loginForm button[type='submit']").click()
    page.wait_for_url("**/workbench", timeout=10_000)
    expect(page.locator("#moduleGrid")).to_be_visible(timeout=10_000)
    expect(page.locator("#userBadge")).not_to_contain_text("加载中", timeout=10_000)


def assert_no_console_errors(messages: list[str]) -> None:
    errors = [message for message in messages if message]
    if errors:
        raise AssertionError("console errors:\n" + "\n".join(errors))


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
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()
        console_errors: list[str] = []
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text)
            if msg.type in {"error", "warning"}
            else None,
        )
        login(page, "browser-manager", "browser-manager-pass")
        expect(page.get_by_text("全局录入和调拨状态，一屏看清")).to_be_visible()
        expect(page.get_by_text("账号与权限")).to_be_visible()

        page.goto(f"{BASE_URL}/outbound", wait_until="networkidle")
        first_order = page.locator("[data-order-choice]").first.input_value()
        if not first_order:
            raise AssertionError("no outbound order found in workbook")

        page.goto(f"{BASE_URL}/admin", wait_until="networkidle")
        expect(page.locator("#createUserForm")).to_be_visible()
        page.locator("#username").fill("shipper-one")
        page.locator("#displayName").fill("Shipper One")
        page.locator("#role").select_option("operator")
        page.locator("#assignedOrder").fill(first_order)
        page.locator("#password").fill("shipper-one-pass")
        page.locator("#createUserForm button[type='submit']").click()
        expect(page.locator("#createStatus")).not_to_be_empty(timeout=10_000)
        expect(page.locator("#userRows")).to_contain_text("shipper-one")
        page.screenshot(path=ARTIFACT_DIR / "admin-users.png", full_page=True)

        page.locator("#logoutBtn").click()
        page.wait_for_url("**/login", timeout=10_000)
        login(page, "shipper-one", "shipper-one-pass")
        expect(page.get_by_text("只看你的发货单，先把当前单做完")).to_be_visible()
        expect(page.get_by_text(f"分配单号 {first_order}")).to_be_visible()
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
        if choice_count != 1:
            raise AssertionError(f"operator saw {choice_count} orders, expected 1")
        if order_choices.first.input_value() != first_order:
            raise AssertionError("operator outbound order scope changed unexpectedly")
        page.screenshot(path=ARTIFACT_DIR / "operator-outbound.png", full_page=True)

        context.clear_cookies()
        login(page, "browser-manager", "browser-manager-pass")
        page.goto(f"{BASE_URL}/admin", wait_until="networkidle")
        assigned_value = page.locator("input[data-assigned-order]").first.input_value()
        if assigned_value != first_order:
            raise AssertionError(
                f"assigned order value mismatch: {assigned_value} != {first_order}"
            )

        mobile = browser.new_context(viewport={"width": 390, "height": 844})
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
