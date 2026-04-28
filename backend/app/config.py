from functools import lru_cache
import logging
import os
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


@lru_cache
def get_settings() -> Settings:
    config_path = ROOT_DIR / "config" / "settings.yaml"
    payload = {}
    if config_path.exists():
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    app_config = payload.get("app", {})
    settings = Settings(
        **app_config,
        saas_username=os.getenv("SAAS_USERNAME") or app_config.get("saas_username"),
        saas_password=os.getenv("SAAS_PASSWORD") or app_config.get("saas_password"),
    )
    if not settings.dry_run and (not settings.saas_username or not settings.saas_password):
        logger.warning(
            "SAAS_USERNAME/SAAS_PASSWORD are not set; forcing SaaS dry_run=True"
        )
        settings.dry_run = True
    return settings
