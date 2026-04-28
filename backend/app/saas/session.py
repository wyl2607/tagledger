from collections.abc import Callable
from pathlib import Path


class SaaSSession:
    def __init__(self, storage_state_path: Path) -> None:
        self.storage_state_path = storage_state_path

    def context_options(self) -> dict[str, str]:
        if self.storage_state_path.exists():
            return {"storage_state": str(self.storage_state_path)}
        return {}

    def save(self, context) -> None:
        self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(self.storage_state_path))

    def ensure_login(self, context, login: Callable[[object], None], login_url: str) -> None:
        if self.storage_state_path.exists():
            return
        page = context.new_page()
        try:
            page.goto(login_url)
            login(page)
            self.save(context)
        finally:
            page.close()

    def refresh_login(self, context, login: Callable[[object], None], login_url: str) -> None:
        page = context.new_page()
        try:
            page.goto(login_url)
            login(page)
            self.save(context)
        finally:
            page.close()
