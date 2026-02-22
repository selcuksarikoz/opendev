import uuid
import time
from typing import Any, Optional

from textual.app import App, ComposeResult
from textual.widgets import Input
from textual.binding import Binding
from textual import on, work

from app.core.http_service import HttpService
from app.utils import (
    get_provider_names,
    get_default_provider,
    set_default_provider,
    load_permissions,
    get_provider,
)
from app.utils.session_stats import session_tracker
from app.prompts import get_agent_names
from app.tools.tool_manager import create_tool_manager
from app.storage.storage import Storage
from app.ui.widgets import (
    SelectionModal,
    ApiKeyModal,
    ChatArea,
)
from app.ui.screens import WelcomeScreen, ChatScreen
from app.utils.logger import log_error
from app.logic.ai_handler import AIHandler
from app.logic.command_handler import CommandHandler


class OpenDevApp(App):
    """Main OpenDev application with decoupled logic."""

    CSS_PATH = "style.tcss"
    BINDINGS = [
        Binding("ctrl+c", "cancel_request",
                "Cancel Request", show=True, priority=True),
        Binding("ctrl+d", "quit", "Quit", show=True, priority=True),
        Binding("ctrl+shift+m", "cycle_mode", "Switch Mode", show=True),
    ]

    def __init__(self, yolo: bool = False):
        super().__init__()
        self.storage = Storage()
        self.session_id = session_tracker.session_id
        self.messages = []
        self._last_processed_input = None
        self._last_processed_time = 0
        self.is_streaming = False
        self.current_provider_info = get_default_provider()
        self.http_service = None
        self.tool_manager = create_tool_manager()
        self.conversation_title = "New Chat"
        self.context_remaining = 100
        self.modes = ["Build", "Plan"]
        self.current_mode_index = 0
        self.conversation_id = str(uuid.uuid4())
        self.is_new_conversation = True
        self.pending_user_queue: list[str] = []
        self.is_shutting_down = False

        self.yolo_mode = yolo
        self.always_allow_session = False
        self.persistent_permissions = {}
        self.ai_settings = {}
        self.ai_handler = AIHandler(self)
        self.command_handler = CommandHandler(self)

    async def on_mount(self) -> None:
        self.ai_settings = await self.storage.get_all_settings()
        self.persistent_permissions = load_permissions()
        if self.current_provider_info:
            self.http_service = HttpService()
            await self.http_service.initialize()
        self.push_screen(WelcomeScreen())

    async def on_unmount(self) -> None:
        self.is_shutting_down = True
        self.is_streaming = False
        if self.http_service:
            await self.http_service.close()
        await self.storage.shutdown()

    async def switch_provider(self, provider_name: str, notify: bool = True):
        if self.http_service:
            await self.http_service.close()
        self.http_service = HttpService(provider_name=provider_name)
        await self.http_service.initialize()
        self.current_provider_info = get_default_provider()
        if notify:
            self.notify(f"Provider switched to {provider_name}")

    def action_cancel_request(self) -> None:
        if self.is_streaming:
            self.is_streaming = False
            self.notify("Request cancelled", severity="warning")

    def get_status_text(self) -> str:
        if not self.current_provider_info:
            return "No provider configured"
        p = self.current_provider_info.get("name", "none")
        m = self.current_provider_info.get("default_model", "unknown")
        return f"{p} • {m}"

    def get_current_mode(self) -> str:
        return self.modes[self.current_mode_index]

    async def ensure_api_key(self, provider_name: str) -> Optional[str]:
        api_key = await self.storage.get_api_key(provider_name)
        if not api_key:
            provider = get_provider(provider_name)
            if provider:
                api_key = provider.get("api_key")
        if not api_key:
            api_key = await self.push_screen(ApiKeyModal(provider_name))
        if not self.http_service or self.http_service.provider_name != provider_name:
            await self.switch_provider(provider_name)
        if self.http_service:
            self.http_service.api_key = api_key
        return api_key

    @on(Input.Submitted, "#initial-input")
    async def handle_initial_input(self, event: Input.Submitted) -> None:
        await self.handle_input(event)

    @on(Input.Submitted, "#chat-input")
    async def handle_chat_input(self, event: Input.Submitted) -> None:
        await self.handle_input(event)

    async def handle_input(self, event: Input.Submitted) -> None:
        event.stop()
        user_input = getattr(event.input, "_real_value",
                             "") or event.value.strip()
        if not user_input:
            return

        now = time.time()
        if (
            user_input == self._last_processed_input
            and (now - self._last_processed_time) < 0.2
        ):
            return
        self._last_processed_input, self._last_processed_time = user_input, now

        event.input.value = ""
        if hasattr(event.input, "_real_value"):
            event.input._real_value = ""
        if hasattr(event.input, "add_to_history"):
            event.input.add_to_history(user_input)

        if user_input.startswith("/"):
            await self.handle_command(user_input)
            return

        if not self.current_provider_info:
            self.notify("Configure a provider first with /model",
                        severity="error")
            return

        api_key = await self.ensure_api_key(self.current_provider_info.get("name"))
        if not api_key:
            return

        if self.is_streaming:
            self.pending_user_queue.append(user_input)
            self._refresh_queue_overlay()
            self.notify(
                f"Message queued ({len(self.pending_user_queue)} pending).",
                severity="information",
            )
            return

        await self._submit_user_message(user_input, skip_render=False)

    @work(exclusive=True)
    async def run_ai(self, user_input: str) -> None:
        """Run AI response generation as an exclusive worker."""
        await self.ai_handler.get_response(user_input)
        if self.pending_user_queue and not self.is_streaming:
            next_input = self.pending_user_queue.pop(0)
            self._refresh_queue_overlay()
            await self._submit_user_message(next_input, skip_render=True)
        else:
            self._refresh_queue_overlay()

    async def _submit_user_message(self, user_input: str, skip_render: bool = False) -> None:
        if self.is_new_conversation:
            self.conversation_title = f"Chat: {user_input[:30]}..."
            await self.storage.create_conversation(
                self.conversation_id, self.conversation_title
            )
            self.is_new_conversation = False
            if isinstance(self.screen, WelcomeScreen):
                chat_screen = ChatScreen()
                await self.push_screen(chat_screen)
                chat_screen.query_one(
                    "#conv-title").update(self.conversation_title)

        self.messages.append({"role": "user", "content": user_input})
        await self.storage.save_message(self.conversation_id, "user", user_input)
        if isinstance(self.screen, ChatScreen) and not skip_render:
            self.screen.add_message("user", user_input)

        self.is_streaming = True
        self.run_ai(user_input)

    def _refresh_queue_overlay(self) -> None:
        try:
            if isinstance(self.screen, ChatScreen):
                self.screen.update_queue_overlay(self.pending_user_queue)
        except Exception:
            pass

    async def handle_command(self, command: str) -> None:
        if command == "/model":
            from app.logic.command_handler import CommandHandler

            handler = CommandHandler(self)
            await handler._start_model_selection()
            return
        elif command == "/settings":
            from app.ui.screens import SettingsScreen

            settings = await self.push_screen(SettingsScreen(self.ai_settings))
            if settings:
                for key, value in settings.items():
                    await self.storage.save_setting(key, value)
                self.ai_settings = settings
                self.notify("Settings saved.")
            return
        elif command.startswith("@"):
            from app.ui.widgets import SelectionModal

            query = command[1:]
            files = self._search_files(query)
            selected = await self.push_screen(SelectionModal("Select File", files))
            if selected:
                self.messages.append(
                    {"role": "user", "content": f"@{selected}"})
                await self.storage.save_message(
                    self.conversation_id, "user", f"@{selected}"
                )
                if isinstance(self.screen, ChatScreen):
                    self.screen.add_message("user", f"@{selected}")
                await self.ai_handler.get_response(f"@{selected}")
            return

        await self.command_handler.handle(command)

    def _search_files(self, query: str = "") -> list[str]:
        from pathlib import Path

        items = []
        skip_dirs = {
            ".git",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            "dist",
            "build",
        }

        try:
            root = Path(".")
            search_path = root
            search_name = query.lower()

            if "/" in query:
                p_query = Path(query)
                if query.endswith("/"):
                    search_path = p_query
                    search_name = ""
                else:
                    search_path = p_query.parent
                    search_name = p_query.name.lower()

            if search_path.exists() and search_path.is_dir():
                for item in search_path.iterdir():
                    if item.name in skip_dirs or item.name.startswith("."):
                        continue
                    if search_name and search_name not in item.name.lower():
                        continue
                    full_str = str(item)
                    if full_str.startswith("./"):
                        full_str = full_str[2:]
                    items.append(full_str + ("/" if item.is_dir() else ""))
                    if len(items) >= 20:
                        break
        except:
            pass

        return items

    @work(exclusive=True)
    async def compact_conversation(self) -> None:
        if not self.http_service or not self.messages:
            return
        self.notify("Compacting context...")
        try:
            summary = await self.http_service.summarize_conversation(self.messages)
            self.messages = []
            context_msg = {"role": "assistant",
                           "content": f"[COMPACTED]\n{summary}"}
            self.messages.append(context_msg)
            await self.storage.save_message(
                self.conversation_id, "assistant", context_msg["content"]
            )
            if isinstance(self.screen, ChatScreen):
                self.screen.action_clear_chat()
                self.screen.add_message("assistant", context_msg["content"])
        except Exception as e:
            self.notify(f"Compaction failed: {e}", severity="error")

    async def clean_history(self) -> None:
        keep_id = self.conversation_id if not self.is_new_conversation else None
        before = await self.storage.list_conversations()
        before_count = len(before)

        await self.storage.delete_conversations_except(keep_id)

        after = await self.storage.list_conversations()
        after_count = len(after)
        deleted = before_count - after_count
        self.notify(f"History cleaned. Deleted {deleted} message(s).")

    def _format_short(self, num: float, is_currency: bool = False) -> str:
        if is_currency:
            return f"${num:.4f}" if num < 0.01 else f"${num:.2f}"
        return f"{num / 1000:.1f}K" if num >= 1000 else str(int(num))


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--yolo", action="store_true")
    args = parser.parse_args()
    app = OpenDevApp(yolo=args.yolo)
    try:
        app.run()
    finally:
        session_tracker.print_summary()


if __name__ == "__main__":
    main()
