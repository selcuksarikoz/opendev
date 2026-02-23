import uuid
from app.ui.widgets import SelectionModal, ApiKeyModal
from app.core.runtime_config import COMMANDS_HELP_TEXT
from app.utils import (
    get_provider_names,
    get_provider_models,
    set_default_provider,
    set_default_model,
)
from app.prompts import get_agent_names, get_agent_description


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
                COMMANDS_HELP_TEXT,
                severity="information",
            )

        elif cmd.startswith("/new"):
            await self._handle_new_chat()

        elif cmd.startswith("/compact"):
            if self.app.messages:
                self.app.compact_conversation()
            else:
                self.app.notify("Nothing to compact.", severity="information")

        elif cmd.startswith("/conversations"):
            await self._show_conversations()

        elif cmd.startswith("/model"):
            await self._start_model_selection()

        elif cmd.startswith("/agents"):
            await self._start_agent_selection()

        elif cmd.startswith("/clean history"):
            await self.app.clean_history()

        elif cmd.startswith("/update"):
            self.app.run_update()

        elif cmd.startswith("/settings"):
            await self.app.open_settings()

    async def _show_conversations(self) -> None:
        conversations = await self.app.storage.list_conversations()
        if not conversations:
            self.app.notify("No saved conversations found.", severity="information")
            return

        items = []
        for c in conversations:
            updated = (c.get("updated_at", "") or "").replace("T", " ")
            if len(updated) > 19:
                updated = updated[:19]
            title = c.get("title", "Untitled")
            items.append(
                {
                    "id": c.get("id"),
                    "label": f"{title}  [{updated}]",
                }
            )

        selected = await self.app.push_screen(
            SelectionModal("Select Conversation", items, display_key="label")
        )
        if not selected:
            return

        conv_id = selected.get("id") if isinstance(selected, dict) else None
        if not conv_id:
            return

        loaded = await self.app.load_conversation(conv_id)
        if not loaded:
            self.app.notify("Could not open selected conversation.", severity="error")

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

        self.app.run_worker(ask_for_optional_key(), exclusive=False)

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

        self.app.run_worker(do_switch(), exclusive=False)
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
        self.app.plan_tracker = None
        self.app.notify("New conversation started")

    async def _start_agent_selection(self) -> None:
        agent_names = get_agent_names()
        if not agent_names:
            self.app.notify("No agents configured.", severity="error")
            return

        items = [
            {
                "id": name,
                "label": f"{name} - {get_agent_description(name)}",
            }
            for name in agent_names
        ]
        selected = await self.app.push_screen(
            SelectionModal("Select Agent", items, display_key="label")
        )
        if not selected:
            return

        agent_name = selected.get("id") if isinstance(selected, dict) else str(selected)
        if not agent_name:
            return
        self.app.set_active_agent(agent_name)
