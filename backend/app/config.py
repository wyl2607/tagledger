import logging
import os
import sys
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


def os_default_data_dir() -> Path:
    """Per-platform user data dir for the desktop launcher.

    Windows: %APPDATA%\\TagLedger
    macOS:   ~/Library/Application Support/TagLedger
    Linux:   $XDG_DATA_HOME/tagledger or ~/.local/share/tagledger
    """
    if sys.platform == "win32":
        base = os.getenv("APPDATA") or str(Path.home() / "AppData/Roaming")
        return Path(base) / "TagLedger"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/TagLedger"
    xdg = os.getenv("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "tagledger"
    return Path.home() / ".local/share/tagledger"


def os_default_log_dir() -> Path:
    return os_default_data_dir() / "logs"


class Settings(BaseModel):
    database_url: str = "sqlite:///data/app.db"
    upload_dir: str = "data/uploads"
    screenshot_dir: str = "data/screenshots"
    ocr_provider: str = "mock"
    enable_barcode: bool = True
    enable_saas_submit: bool = False
    dry_run: bool = True
    submission_retries: int = 3
    saas_username: str | None = None
    saas_password: str | None = None
    saas_selectors_path: str = "config/saas_selectors.yaml"
    saas_storage_state: str = "data/storage_state.json"
    playwright_log: str = "logs/playwright.log"
    metrics_manual_seconds_per_entry: int = 90
    material_mapping_path: str = "data/material_mapping.xlsx"
    outbound_workbook_path: str = "data/outbound/发货0422.xlsx"
    outbound_shipping_sheet: str = "21单830个物料发货单-多物料订单"
    outbound_cutting_sheet: str = "拣货单-多物料订单"
    outbound_cutting_text_path: str = "data/outbound/cutting.txt"
    outbound_shipping_text_path: str = "data/outbound/shipping.txt"
    cookie_secure: bool = False
    csrf_protection: bool = True
    lan_guard_enabled: bool = True
    pairing_enabled: bool = True
    pairing_rate_limit_per_min: int = 5
    pairing_block_minutes: int = 10
    data_dir: str | None = None
    log_dir: str | None = None

    @property
    def effective_data_dir(self) -> Path:
        return Path(self.data_dir) if self.data_dir else ROOT_DIR

    @property
    def effective_log_dir(self) -> Path:
        return Path(self.log_dir) if self.log_dir else ROOT_DIR

    @property
    def database_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Phase 1 only supports sqlite:/// database URLs")
        relative = self.database_url.removeprefix("sqlite:///")
        # When the desktop launcher provides a data dir AND the URL is still the
        # default `sqlite:///data/app.db`, reroute the SQLite file under it so
        # user data lives outside the install directory. An explicit, non-default
        # database_url (e.g. tests pointing at a tmp file) is honored as-is.
        if self.data_dir and relative == "data/app.db":
            return Path(self.data_dir) / "app.db"
        return ROOT_DIR / relative

    @property
    def upload_path(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir) / "uploads"
        return ROOT_DIR / self.upload_dir

    @property
    def screenshot_path(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir) / "screenshots"
        return ROOT_DIR / self.screenshot_dir

    @property
    def saas_selectors_file(self) -> Path:
        return ROOT_DIR / self.saas_selectors_path

    @property
    def saas_storage_state_path(self) -> Path:
        return ROOT_DIR / self.saas_storage_state

    @property
    def playwright_log_path(self) -> Path:
        if self.log_dir:
            return Path(self.log_dir) / "playwright.log"
        return ROOT_DIR / self.playwright_log

    @property
    def material_mapping_file(self) -> Path:
        return ROOT_DIR / self.material_mapping_path

    @property
    def outbound_workbook_file(self) -> Path:
        return ROOT_DIR / self.outbound_workbook_path

    @property
    def outbound_cutting_text_file(self) -> Path:
        return ROOT_DIR / self.outbound_cutting_text_path

    @property
    def outbound_shipping_text_file(self) -> Path:
        return ROOT_DIR / self.outbound_shipping_text_path


@lru_cache
def get_settings() -> Settings:
    config_path = ROOT_DIR / "config" / "settings.yaml"
    payload = {}
    if config_path.exists():
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    app_config = dict(payload.get("app", {}))
    metrics_config = payload.get("metrics", {}) or {}
    app_config.setdefault(
        "metrics_manual_seconds_per_entry",
        metrics_config.get(
            "manual_seconds",
            metrics_config.get("manual_seconds_per_entry", 90),
        ),
    )
    app_config["saas_username"] = os.getenv("SAAS_USERNAME") or app_config.get("saas_username")
    app_config["saas_password"] = os.getenv("SAAS_PASSWORD") or app_config.get("saas_password")
    app_config["database_url"] = os.getenv("DATABASE_URL") or app_config.get("database_url")
    if os.getenv("COOKIE_SECURE") is not None:
        app_config["cookie_secure"] = os.getenv("COOKIE_SECURE", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    if os.getenv("CSRF_PROTECTION") is not None:
        app_config["csrf_protection"] = os.getenv("CSRF_PROTECTION", "").lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
    if os.getenv("TAGLEDGER_DATA_DIR"):
        app_config["data_dir"] = os.getenv("TAGLEDGER_DATA_DIR")
    if os.getenv("TAGLEDGER_LOG_DIR"):
        app_config["log_dir"] = os.getenv("TAGLEDGER_LOG_DIR")
    settings = Settings(**app_config)
    if not settings.dry_run and (not settings.saas_username or not settings.saas_password):
        logger.warning("SAAS_USERNAME/SAAS_PASSWORD are not set; forcing SaaS dry_run=True")
        settings.dry_run = True
    return settings
