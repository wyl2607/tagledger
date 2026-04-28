from pathlib import Path
from unittest.mock import Mock
import importlib.util

import pytest
import yaml

from backend.app.config import Settings
from backend.app.models import Category, Record, RecordStatus
from backend.app.saas.client import SaaSClient, SaaSLoginError


PLAYWRIGHT_AVAILABLE = importlib.util.find_spec("playwright") is not None


def write_selectors(path: Path, form_url: str = "file:///fake_saas.html") -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "saas": {
                    "login_url": "file:///fake_saas.html",
                    "form_url": form_url,
                    "selectors": {
                        "login": {
                            "username": "#username",
                            "password": "#password",
                            "submit": "button[type=submit]",
                        },
                        "form": {
                            "model": "#model",
                            "vin_or_bin": "#vin",
                            "serial_number": "#sn",
                            "category_a": "input[value=A]",
                            "category_b": "input[value=B]",
                            "category_c": "input[value=C]",
                            "image_upload": "input[type=file][name=label]",
                            "submit": "button.submit-record",
                        },
                        "success_indicator": ".alert-success",
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def make_settings(tmp_path: Path, selectors: Path) -> Settings:
    return Settings(
        screenshot_dir=str(tmp_path / "screenshots"),
        saas_selectors_path=str(selectors),
        saas_storage_state=str(tmp_path / "storage_state.json"),
        playwright_log=str(tmp_path / "playwright.log"),
        saas_username="demo",
        saas_password="secret",
    )


def make_record() -> Record:
    return Record(
        id=123,
        image_path="label.jpg",
        category=Category.A,
        model="MODEL-X",
        vin_or_bin="VIN123",
        serial_number="SN123",
        status=RecordStatus.confirmed,
    )


def test_saas_client_raises_clear_error_for_missing_selector(tmp_path: Path) -> None:
    selectors = tmp_path / "bad_selectors.yaml"
    selectors.write_text(
        yaml.safe_dump({"saas": {"login_url": "x", "form_url": "y", "selectors": {}}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing SaaS selector config"):
        SaaSClient(make_settings(tmp_path, selectors), dry_run=True)


def test_dry_run_submit_never_clicks_submit_with_mock_page(tmp_path: Path) -> None:
    selectors = tmp_path / "selectors.yaml"
    write_selectors(selectors)
    image_path = tmp_path / "label.jpg"
    image_path.write_bytes(b"fake image")
    client = SaaSClient(make_settings(tmp_path, selectors), dry_run=True)
    page = Mock()
    page.screenshot.side_effect = lambda path, full_page: Path(path).write_bytes(b"png")

    result = client.submit_record_on_page(page, make_record(), image_path)

    assert result.dry_run is True
    assert result.screenshot_path is not None
    assert Path(result.screenshot_path).exists()
    page.click.assert_not_called()


def test_login_failure_raises_clear_error(tmp_path: Path) -> None:
    selectors = tmp_path / "selectors.yaml"
    write_selectors(selectors)
    client = SaaSClient(make_settings(tmp_path, selectors), dry_run=True)
    page = Mock()
    page.click.side_effect = RuntimeError("bad credentials")

    with pytest.raises(SaaSLoginError, match="SaaS login failed"):
        client.login(page)


@pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="playwright optional dependency not installed")
def test_dry_run_submit_never_clicks_submit_with_file_page(tmp_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    fixture = Path(__file__).parent / "fixtures" / "fake_saas.html"
    selectors = tmp_path / "selectors.yaml"
    write_selectors(selectors, form_url=fixture.as_uri())
    image_path = tmp_path / "label.jpg"
    image_path.write_bytes(b"fake image")
    client = SaaSClient(make_settings(tmp_path, selectors), dry_run=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            result = client.submit_record_on_page(page, make_record(), image_path)
            submitted = page.evaluate("window.realSubmitted")
        finally:
            browser.close()

    assert result.dry_run is True
    assert submitted is False
    assert result.screenshot_path is not None
    assert Path(result.screenshot_path).exists()
