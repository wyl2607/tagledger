import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from backend.app.config import Settings
from backend.app.models import Record
from backend.app.saas.session import SaaSSession

logger = logging.getLogger(__name__)


class PlaywrightNotInstalledError(RuntimeError):
    pass


class SaaSLoginError(RuntimeError):
    pass


class SaaSSubmissionError(RuntimeError):
    def __init__(self, message: str, screenshot_path: str | None = None) -> None:
        super().__init__(message)
        self.screenshot_path = screenshot_path


@dataclass(frozen=True)
class SubmissionResult:
    dry_run: bool
    screenshot_path: str | None = None


def _get_nested(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"missing SaaS selector config: {'.'.join(path)}")
        current = current[key]
    if current is None or current == "":
        raise ValueError(f"empty SaaS selector config: {'.'.join(path)}")
    return current


class SaaSClient:
    def __init__(self, settings: Settings, dry_run: bool) -> None:
        self.settings = settings
        self.dry_run = dry_run
        self.config = self._load_config(settings.saas_selectors_file)
        self.saas_config = _get_nested(self.config, ("saas",))
        self.selectors = _get_nested(self.saas_config, ("selectors",))
        self.login_url = _get_nested(self.saas_config, ("login_url",))
        self.form_url = _get_nested(self.saas_config, ("form_url",))
        self.session = SaaSSession(settings.saas_storage_state_path)

    def login(self, page) -> None:
        if not self.settings.saas_username or not self.settings.saas_password:
            raise ValueError("SAAS_USERNAME and SAAS_PASSWORD are required for SaaS login")
        login_selectors = _get_nested(self.selectors, ("login",))
        try:
            page.fill(_get_nested(login_selectors, ("username",)), self.settings.saas_username)
            page.fill(_get_nested(login_selectors, ("password",)), self.settings.saas_password)
            page.click(_get_nested(login_selectors, ("submit",)))
            page.wait_for_load_state("networkidle")
        except Exception as exc:
            raise SaaSLoginError(f"SaaS login failed: {exc}") from exc

    def submit_record(self, record: Record, image_path: Path) -> SubmissionResult:
        self.settings.screenshot_path.mkdir(parents=True, exist_ok=True)
        self.settings.playwright_log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise PlaywrightNotInstalledError(
                'Playwright is not installed. Run: pip install -e ".[submit]"'
            ) from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(**self.session.context_options())
                try:
                    self.session.ensure_login(context, self.login, self.login_url)
                    page = context.new_page()
                    try:
                        return self._submit_on_page(page, record, image_path)
                    except Exception:
                        if self.settings.saas_username and self.settings.saas_password:
                            self.session.refresh_login(context, self.login, self.login_url)
                            page = context.new_page()
                            return self._submit_on_page(page, record, image_path)
                        raise
                    finally:
                        if not page.is_closed():
                            page.close()
                finally:
                    context.close()
            finally:
                browser.close()

    def submit_record_on_page(
        self,
        page,
        record: Record,
        image_path: Path,
    ) -> SubmissionResult:
        return self._submit_on_page(page, record, image_path)

    def _submit_on_page(self, page, record: Record, image_path: Path) -> SubmissionResult:
        form_selectors = _get_nested(self.selectors, ("form",))
        page.goto(self.form_url)
        self._fill_if_present(page, _get_nested(form_selectors, ("model",)), record.model)
        self._fill_if_present(
            page,
            _get_nested(form_selectors, ("vin_or_bin",)),
            record.vin_or_bin,
        )
        self._fill_if_present(
            page,
            _get_nested(form_selectors, ("serial_number",)),
            record.serial_number,
        )
        category_selector = _get_nested(
            form_selectors,
            (f"category_{record.category.value.lower()}",),
        )
        page.check(category_selector)
        page.set_input_files(_get_nested(form_selectors, ("image_upload",)), str(image_path))

        if self.dry_run:
            screenshot = self._dry_run_screenshot_path(record)
            page.screenshot(path=str(screenshot), full_page=True)
            self._log_playwright(f"Dry-run SaaS submission screenshot saved: {screenshot}")
            return SubmissionResult(dry_run=True, screenshot_path=str(screenshot))

        try:
            page.click(_get_nested(form_selectors, ("submit",)))
            page.wait_for_selector(
                _get_nested(self.selectors, ("success_indicator",)),
                timeout=15000,
            )
            screenshot = self._submitted_screenshot_path(record)
            page.screenshot(path=str(screenshot), full_page=True)
            return SubmissionResult(dry_run=False, screenshot_path=str(screenshot))
        except Exception as exc:
            screenshot = self._error_screenshot_path(record)
            try:
                page.screenshot(path=str(screenshot), full_page=True)
            except Exception:
                screenshot = None
            raise SaaSSubmissionError(str(exc), str(screenshot) if screenshot else None) from exc

    def _dry_run_screenshot_path(self, record: Record) -> Path:
        self.settings.screenshot_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return self.settings.screenshot_path / f"dryrun_{record.id}_{ts}.png"

    def _submitted_screenshot_path(self, record: Record) -> Path:
        self.settings.screenshot_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return self.settings.screenshot_path / f"submitted_{record.id}_{ts}.png"

    def _error_screenshot_path(self, record: Record) -> Path:
        self.settings.screenshot_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return self.settings.screenshot_path / f"error_{record.id}_{ts}.png"

    def _log_playwright(self, message: str) -> None:
        logger.info(message)
        self.settings.playwright_log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).isoformat()
        with self.settings.playwright_log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")

    @staticmethod
    def _fill_if_present(page, selector: str, value: str | None) -> None:
        if value is not None:
            page.fill(selector, value)

    @staticmethod
    def _load_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise ValueError(f"SaaS selector config not found: {path}")
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError("SaaS selector config must be a YAML mapping")
        required = (
            ("saas", "login_url"),
            ("saas", "form_url"),
            ("saas", "selectors", "login", "username"),
            ("saas", "selectors", "login", "password"),
            ("saas", "selectors", "login", "submit"),
            ("saas", "selectors", "form", "model"),
            ("saas", "selectors", "form", "vin_or_bin"),
            ("saas", "selectors", "form", "serial_number"),
            ("saas", "selectors", "form", "category_a"),
            ("saas", "selectors", "form", "category_b"),
            ("saas", "selectors", "form", "category_c"),
            ("saas", "selectors", "form", "image_upload"),
            ("saas", "selectors", "form", "submit"),
            ("saas", "selectors", "success_indicator"),
        )
        for item in required:
            _get_nested(payload, item)
        return payload
