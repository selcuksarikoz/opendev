import uuid
from app.ui.widgets import SelectionModal, ApiKeyModal
from app.utils import (
    get_provider_names,
    get_provider_models,
    set_default_provider,
    set_default_model,
)


class CommandHandler:
    def __init__(self, app):
        self.app = app
        self._model_selection_state = {
            "step": None,
            "provider": None,
            "model": None,
            "api_key": None,
        }

    async def handle(self, command: str) -> None:
        cmd = command.strip().lower()

        if cmd.startswith("/help"):
            self.app.notify(
                "Commands: /new, /clear, /model, /agents, /clean history, /help, /settings, /compact",
                severity="information",
            )

        elif cmd.startswith("/new") or cmd.startswith("/clear"):
            await self._handle_new_chat()

        elif cmd.startswith("/compact"):
            if self.app.messages:
                self.app.compact_conversation()

        elif cmd.startswith("/model"):
            await self._start_model_selection()

        elif cmd.startswith("/clean history"):
            await self.app.clean_history()

        elif cmd.startswith("/settings"):
            from app.ui.screens import SettingsScreen

            settings = await self.app.push_screen(SettingsScreen(self.app.ai_settings))
            if settings:
                for key, value in settings.items():
                    await self.app.storage.save_setting(key, value)
                self.app.ai_settings = settings
                self.app.notify("Settings saved.")

    async def _start_model_selection(self):
        from app.utils.config import get_provider

        provider_names = get_provider_names()
        if not provider_names:
            self.app.notify("No providers found.", severity="error")
            return

        self._model_selection_state = {
            "step": "provider",
            "provider": None,
            "model": None,
            "api_key": None,
        }

        def on_provider_selected(provider):
            if provider:
                self._model_selection_state["provider"] = provider
                self._continue_model_selection()

        modal = SelectionModal("Select Provider", provider_names)
        self.app.push_screen(modal, callback=on_provider_selected)

    def _continue_model_selection(self):
        from app.utils.config import get_provider, get_provider_models

        state = self._model_selection_state
        provider = state["provider"]

        if provider:
            models = get_provider_models(provider)
            if models:

                def on_model_selected(selected):
                    if selected:
                        model_id = (
                            selected.get("id")
                            if isinstance(selected, dict)
                            else selected
                        )
                        state["model"] = model_id
                        self._finish_model_selection()
                    else:
                        self._reset_model_selection()

                modal = SelectionModal(
                    "Select Model", models, display_key="name")
                self.app.push_screen(modal, callback=on_model_selected)
            else:
                self.app.notify(f"No models for {provider}", severity="error")
                self._reset_model_selection()

    def _finish_model_selection(self):
        from app.utils.config import get_provider

        state = self._model_selection_state
        provider = state["provider"]

        if not provider:
            self._reset_model_selection()
            return

        async def ask_for_optional_key():
            provider_data = get_provider(provider)
            config_key = provider_data.get("api_key", "") if provider_data else ""
            stored_key = await self.app.storage.get_api_key(provider)
            has_existing_key = bool(config_key or stored_key)

            def on_api_key_saved(key):
                # If empty, continue with existing key unchanged.
                if key:
                    state["api_key"] = key
                self._apply_model_selection()

            modal = ApiKeyModal(
                provider,
                optional=True,
                has_existing_key=has_existing_key,
            )
            self.app.push_screen(modal, callback=on_api_key_saved)

        self.app.call_later(ask_for_optional_key)

    def _apply_model_selection(self):
        from app.utils import set_default_provider, set_default_model

        state = self._model_selection_state
        provider = state["provider"]
        model = state["model"]

        if not provider or not model:
            self._reset_model_selection()
            return

        set_default_provider(provider)
        set_default_model(provider, model)

        async def do_switch():
            await self.app.switch_provider(provider, notify=False)
            if hasattr(self.app.screen, "update_status"):
                pass
                # self.app.screen.update_status()

        self.app.call_later(do_switch)
        self.app.notify(f"Switched to {provider} / {model}")
        self._reset_model_selection()

    def _reset_model_selection(self):
        self._model_selection_state = {
            "step": None,
            "provider": None,
            "model": None,
            "api_key": None,
        }

    async def _handle_new_chat(self):
        from app.ui.screens import ChatScreen

        if isinstance(self.app.screen, ChatScreen):
            self.app.screen.action_clear_chat()
            self.app.screen.query_one("#conv-title").update("# New Chat")
            self.app.screen.query_one("#context-info").update("Context: 100%")

        self.app.conversation_id = str(uuid.uuid4())
        self.app.is_new_conversation = True
        self.app.messages = []
        self.app.conversation_title = "New Chat"
        self.app.notify("New conversation started")
