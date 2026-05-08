import logging
import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


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
    def database_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Phase 1 only supports sqlite:/// database URLs")
        return ROOT_DIR / self.database_url.removeprefix("sqlite:///")

    @property
    def upload_path(self) -> Path:
        return ROOT_DIR / self.upload_dir

    @property
    def screenshot_path(self) -> Path:
        return ROOT_DIR / self.screenshot_dir

    @property
    def saas_selectors_file(self) -> Path:
        return ROOT_DIR / self.saas_selectors_path

    @property
    def saas_storage_state_path(self) -> Path:
        return ROOT_DIR / self.saas_storage_state

    @property
    def playwright_log_path(self) -> Path:
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
    settings = Settings(**app_config)
    if not settings.dry_run and (not settings.saas_username or not settings.saas_password):
        logger.warning("SAAS_USERNAME/SAAS_PASSWORD are not set; forcing SaaS dry_run=True")
        settings.dry_run = True
    return settings
