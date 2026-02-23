from typing import TYPE_CHECKING

from app.core.runtime_config import APP_MODES, DEFAULT_MODE

if TYPE_CHECKING:
    from app.ui.app import OpenDevApp


class ModeManager:
    def __init__(self, app: "OpenDevApp"):
        self.app = app
        self.modes = list(APP_MODES)

    def get_current_mode(self) -> str:
        idx = int(getattr(self.app, "current_mode_index", 0))
        if idx < 0 or idx >= len(self.modes):
            idx = 0
        return self.modes[idx]

    def load_from_settings(self, settings: dict[str, str]) -> None:
        stored_mode = str(settings.get("current_mode", "")).strip()
        if stored_mode in self.modes:
            self.app.current_mode_index = self.modes.index(stored_mode)
        else:
            self.app.current_mode_index = (
                self.modes.index(DEFAULT_MODE) if DEFAULT_MODE in self.modes else 0
            )
            self.persist_current_mode(self.get_current_mode())
        self.apply_to_http_service()

    def cycle(self) -> str:
        self.app.current_mode_index = (self.app.current_mode_index + 1) % len(self.modes)
        mode = self.get_current_mode()
        self.apply_to_http_service()
        self.persist_current_mode(mode)
        return mode

    def apply_to_http_service(self) -> None:
        if self.app.http_service:
            self.app.http_service.set_mode(self.get_current_mode())

    def persist_current_mode(self, mode: str) -> None:
        async def save_mode():
            await self.app.storage.save_setting("current_mode", mode)
            self.app.ai_settings["current_mode"] = mode

        self.app.run_worker(save_mode(), exclusive=False)
