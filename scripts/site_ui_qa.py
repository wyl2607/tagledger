from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "data" / "screenshots" / "site-ui-qa"
MANAGER = ("site-manager", "site-manager-pass")
OPERATOR = ("site-operator", "site-operator-pass")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(base_url: str) -> None:
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"server did not become healthy: {base_url}")


def request_json(
    base_url: str,
    path: str,
    data: dict[str, object] | None = None,
) -> dict[str, object]:
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode())


def start_server(base_url: str) -> subprocess.Popen[str]:
    port = int(base_url.rsplit(":", 1)[1])
    db_path = Path(tempfile.gettempdir()) / f"tagledger-site-ui-qa-{port}.db"
    for suffix in ("", "-shm", "-wal"):
        (Path(f"{db_path}{suffix}")).unlink(missing_ok=True)
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env.setdefault("TAGLEDGER_PAIRING_REQUIRED", "false")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    wait_for_health(base_url)
    return process


def login(page: Page, base_url: str, username: str, password: str) -> None:
    page.goto(f"{base_url}/login", wait_until="networkidle")
    page.locator("#username").fill(username)
    page.locator("#password").fill(password)
    page.locator("#loginForm button[type='submit']").click()
    page.wait_for_url("**/workbench", timeout=10_000)
    page.wait_for_load_state("networkidle")


def csrf_fetch(page: Page, path: str, data: dict[str, object]) -> dict[str, object]:
    return page.evaluate(
        """async ({ path, data }) => {
            const response = await AuthUI.fetchJson(path, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(data),
            });
            return response;
        }""",
        {"path": path, "data": data},
    )


def seed_accounts(base_url: str) -> str:
    request_json(
        base_url,
        "/api/auth/setup",
        {
            "username": MANAGER[0],
            "display_name": "Site Manager",
            "password": MANAGER[1],
        },
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        context.add_init_script("localStorage.setItem('tagledger.locale','zh')")
        page = context.new_page()
        login(page, base_url, *MANAGER)
        page.goto(f"{base_url}/outbound", wait_until="networkidle")
        order = "SO202604210093"
        choices = page.locator("[data-order-choice]")
        if choices.count():
            order = choices.first.input_value()
        page.goto(f"{base_url}/admin", wait_until="networkidle")
        page.wait_for_function("window.AuthUI !== undefined")
        csrf_fetch(
            page,
            "/api/admin/users",
            {
                "username": OPERATOR[0],
                "display_name": "Site Operator",
                "password": OPERATOR[1],
                "role": "operator",
                "assigned_order_numbers": [order],
            },
        )
        browser.close()
        return order


def capture_page(
    page: Page,
    base_url: str,
    name: str,
    path: str,
    *,
    full_page: bool = True,
) -> None:
    page.goto(f"{base_url}{path}", wait_until="networkidle")
    page.screenshot(path=ARTIFACT_DIR / f"{name}.png", full_page=full_page)


def run(base_url: str, *, start: bool) -> dict[str, object]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    process = start_server(base_url) if start else None
    console_messages: list[str] = []
    try:
        assigned_order = seed_accounts(base_url)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1366, "height": 900})
            context.add_init_script("localStorage.setItem('tagledger.locale','zh')")
            context.on(
                "page",
                lambda page: page.on(
                    "console",
                    lambda msg: console_messages.append(f"{page.url}: {msg.type}: {msg.text}")
                    if msg.type in {"error", "warning"}
                    else None,
                ),
            )
            page = context.new_page()
            login(page, base_url, *MANAGER)
            page.goto(f"{base_url}/inbound", wait_until="networkidle")
            page.locator("#partKey").fill("QA-INBOUND-001")
            page.locator("#locationCode").fill("QA-A-01")
            page.locator("#quantity").fill("3")
            page.locator("#reason").fill("site_ui_qa_inbound")
            page.locator("#submitInboundBtn").click()
            page.wait_for_function(
                "document.querySelector('#inboundStatus')?.textContent.includes('入库完成')",
                timeout=10_000,
            )
            if "入库完成" not in page.locator("#inboundStatus").inner_text():
                raise AssertionError("inbound page did not complete receiving")
            page.screenshot(path=ARTIFACT_DIR / "manager-inbound.png", full_page=True)
            page.goto(f"{base_url}/outbound", wait_until="networkidle")
            page.locator("#clearOrdersBtn").click()
            if not page.locator("#queryBtn").is_disabled():
                raise AssertionError("outbound query button should be disabled without orders")
            page.locator("#selectAllOrdersBtn").click()
            if page.locator("#queryBtn").is_disabled():
                raise AssertionError("outbound query button should enable after selecting orders")
            page.screenshot(path=ARTIFACT_DIR / "manager-outbound-query-guard.png", full_page=True)
            for name, path in (
                ("manager-workbench", "/workbench"),
                ("manager-dashboard", "/dashboard"),
                ("manager-outbound", "/outbound"),
                ("manager-transfers", "/transfers"),
                ("manager-history", "/history"),
                ("manager-admin", "/admin"),
                ("pair-missing-token", "/pair"),
            ):
                capture_page(page, base_url, name, path)
            context.clear_cookies()
            login(page, base_url, *OPERATOR)
            for name, path in (
                ("operator-workbench", "/workbench"),
                ("operator-outbound", "/outbound"),
                ("operator-transfers-denied", "/transfers"),
            ):
                capture_page(page, base_url, name, path)
            mobile = browser.new_context(viewport={"width": 390, "height": 844})
            mobile.add_init_script("localStorage.setItem('tagledger.locale','zh')")
            mobile_page = mobile.new_page()
            login(mobile_page, base_url, *OPERATOR)
            mobile_page.goto(f"{base_url}/mobile#capture", wait_until="networkidle")
            mobile_page.locator("#outboundOrderSelect").select_option("")
            if not mobile_page.locator("#manualMaterialLookupBtn").is_disabled():
                raise AssertionError(
                    "mobile outbound manual lookup should be disabled without order"
                )
            mobile_orders = mobile_page.locator("#outboundOrderSelect option:not([value=''])")
            if mobile_orders.count():
                mobile_page.locator("#outboundOrderSelect").select_option(
                    mobile_orders.first.get_attribute("value") or ""
                )
                if mobile_page.locator("#manualMaterialLookupBtn").is_disabled():
                    raise AssertionError(
                        "mobile outbound manual lookup should enable after order selection"
                    )
            capture_page(
                mobile_page,
                base_url,
                "operator-mobile",
                "/mobile#capture",
                full_page=False,
            )
            browser.close()
        errors = [message for message in console_messages if "favicon" not in message]
        if errors:
            raise AssertionError("console warnings/errors:\n" + "\n".join(errors))
        return {
            "ok": True,
            "assigned_order": assigned_order,
            "screenshots": str(ARTIFACT_DIR.relative_to(ROOT)),
        }
    finally:
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture reusable TagLedger UI QA screenshots.")
    parser.add_argument(
        "--base-url",
        default=None,
        help="Existing server base URL. Defaults to a temporary local server.",
    )
    parser.add_argument(
        "--no-start",
        action="store_true",
        help="Use --base-url without starting a temporary server.",
    )
    args = parser.parse_args()
    base_url = (args.base_url or f"http://127.0.0.1:{free_port()}").rstrip("/")
    result = run(base_url, start=not args.no_start)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
