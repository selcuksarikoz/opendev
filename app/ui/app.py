import uuid
import time
from typing import Any, Optional

from textual.app import App, ComposeResult
from textual.widgets import Input, Label
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
    CustomInput,
)
from app.ui.screens import WelcomeScreen, ChatScreen
from app.utils.logger import log_error
from app.logic.ai_handler import AIHandler
from app.logic.command_handler import CommandHandler
from app.logic.turn_orchestrator import TurnOrchestrator
from app.logic.mode_manager import ModeManager
from app.utils.updater import check_update_available, install_or_upgrade
from app.utils.file_search import search_files_for_query
from app.core.runtime_config import (
    DEFAULT_AGENT_NAME,
    CONTEXT_LIMIT_TOKENS,
    PLAN_MESSAGE_PREFIX,
)


class OpenDevApp(App):
    """Main OpenDev application with decoupled logic."""

    CSS_PATH = "style.tcss"
    BINDINGS = [
        Binding("ctrl+c", "cancel_request",
                "Cancel Request", show=True, priority=True),
        Binding("escape", "escape_request_only", "Cancel Request", show=False, priority=True),
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
        self.mode_manager = ModeManager(self)
        self.modes = self.mode_manager.modes
        self.current_mode_index = 0
        self.active_agent = DEFAULT_AGENT_NAME
        self.conversation_id = str(uuid.uuid4())
        self.is_new_conversation = True
        self.pending_user_queue: list[str] = []
        self.is_shutting_down = False
        self.plan_tracker: Optional[dict[str, Any]] = None

        self.yolo_mode = yolo
        self.always_allow_session = False
        self.persistent_permissions = {}
        self.ai_settings = {}
        self.ai_handler = AIHandler(self)
        self.command_handler = CommandHandler(self)
        self.turn_orchestrator = TurnOrchestrator(self)

    def notify(self, *args, **kwargs):
        kwargs.setdefault("timeout", 1.5)
        return super().notify(*args, **kwargs)

    async def on_mount(self) -> None:
        self.ai_settings = await self.storage.get_all_settings()
        self.mode_manager.load_from_settings(self.ai_settings)
        try:
            CustomInput._shared_history = await self.storage.get_recent_user_history()
            CustomInput._history_index = -1
        except Exception:
            pass
        self.persistent_permissions = load_permissions()
        if self.current_provider_info:
            self.http_service = HttpService(agent_name=self.active_agent)
            await self.http_service.initialize()
            self.mode_manager.apply_to_http_service()
        self.push_screen(WelcomeScreen())
        self.check_updates_on_startup()
        self.refresh_context_info()

    async def on_unmount(self) -> None:
        self.is_shutting_down = True
        self.is_streaming = False
        if self.http_service:
            await self.http_service.close()
        await self.storage.shutdown()

    async def switch_provider(self, provider_name: str, notify: bool = True):
        if self.http_service:
            await self.http_service.close()
        self.http_service = HttpService(
            provider_name=provider_name,
            agent_name=self.active_agent,
        )
        await self.http_service.initialize()
        self.mode_manager.apply_to_http_service()
        self.current_provider_info = get_default_provider()
        if notify:
            self.notify(f"Provider switched to {provider_name}")

    def set_active_agent(self, agent_name: str) -> None:
        valid_agents = set(get_agent_names())
        if agent_name not in valid_agents:
            self.notify(f"Unknown agent: {agent_name}", severity="error")
            return
        self.active_agent = agent_name
        if self.http_service:
            self.http_service.set_agent(agent_name)
        if hasattr(self.screen, "update_mode_indicator"):
            try:
                self.screen.update_mode_indicator(self.get_current_mode())
            except Exception:
                pass
        self.notify(f"Switched agent to {agent_name}")

    def apply_agent_handoff(
        self,
        to_agent: str,
        task: str,
        context: str = "",
    ) -> tuple[bool, str]:
        valid_agents = set(get_agent_names())
        if to_agent not in valid_agents:
            return False, f"Error: Unknown handoff target '{to_agent}'."
        if not task.strip():
            return False, "Error: Handoff task cannot be empty."

        from_agent = self.active_agent
        if to_agent == from_agent:
            return False, "Error: Handoff target is already the active agent."

        self.set_active_agent(to_agent)
        handoff_msg = (
            f"Agent handoff from '{from_agent}' to '{to_agent}'. "
            f"Assigned task: {task.strip()}."
        )
        if context.strip():
            handoff_msg += f" Context: {context.strip()}."

        self.messages.append({"role": "system", "content": handoff_msg})
        return True, handoff_msg

    def action_cancel_request(self) -> None:
        if self.is_streaming:
            self.is_streaming = False
            self.notify("Request cancelled", severity="warning")
            return

        self.run_worker(self.command_handler._handle_new_chat(), exclusive=False)

    def action_escape_request_only(self) -> None:
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
        return self.mode_manager.get_current_mode()

    def action_cycle_mode(self) -> None:
        mode = self.mode_manager.cycle()
        if hasattr(self.screen, "update_mode_indicator"):
            try:
                self.screen.update_mode_indicator(mode)
            except Exception:
                pass
        if hasattr(self.screen, "update_status"):
            try:
                self.screen.update_status()
            except Exception:
                pass

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
            await self._submit_user_message(next_input, skip_render=False)
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

        await self.turn_orchestrator.handle_user_turn(user_input)

    def _start_ai_run(self, user_input: str) -> None:
        self.is_streaming = True
        self.run_ai(user_input)

    def advance_plan_progress(self, step_count: int = 1) -> None:
        tracker = self.plan_tracker
        if not tracker or not tracker.get("active"):
            return
        items = tracker.get("items", [])
        if not items:
            return
        tracker["completed"] = max(
            0, min(int(tracker.get("completed", 0)) + max(1, step_count), len(items))
        )
        updated = (
            f"{PLAN_MESSAGE_PREFIX}"
            f"{TurnOrchestrator._format_plan_items(items, tracker['completed'])}"
        )
        msg_index = int(tracker.get("message_index", -1))
        if 0 <= msg_index < len(self.messages):
            self.messages[msg_index]["content"] = updated
        if isinstance(self.screen, ChatScreen):
            self.screen.update_plan_message(updated)

    def finalize_plan_progress(self) -> None:
        tracker = self.plan_tracker
        if not tracker or not tracker.get("active"):
            return
        items = tracker.get("items", [])
        tracker["completed"] = len(items)
        updated = (
            f"{PLAN_MESSAGE_PREFIX}"
            f"{TurnOrchestrator._format_plan_items(items, len(items))}"
        )
        msg_index = int(tracker.get("message_index", -1))
        if 0 <= msg_index < len(self.messages):
            self.messages[msg_index]["content"] = updated
        if isinstance(self.screen, ChatScreen):
            self.screen.update_plan_message(updated)
        tracker["active"] = False

    def _refresh_queue_overlay(self) -> None:
        try:
            if isinstance(self.screen, ChatScreen):
                self.screen.update_queue_overlay(self.pending_user_queue)
        except Exception:
            pass

    async def handle_command(self, command: str) -> None:
        if command == "/model":
            await self.command_handler._start_model_selection()
            return
        elif command == "/settings":
            await self.open_settings()
            return
        elif command.startswith("@"):
            from app.ui.widgets import SelectionModal

            query = command[1:]
            files = search_files_for_query(query=query, limit=20, include_git_branches=False)
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

    async def open_settings(self) -> None:
        from app.ui.screens import SettingsScreen

        settings = await self.push_screen(SettingsScreen(self.ai_settings))
        if settings:
            for key, value in settings.items():
                await self.storage.save_setting(key, value)
            self.ai_settings = settings
            self.mode_manager.load_from_settings(self.ai_settings)
            self.notify("Settings saved.")

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
        finally:
            self.refresh_context_info()

    async def clean_history(self) -> None:
        before = await self.storage.list_conversations()
        before_count = len(before)
        await self.storage.delete_all_conversations()

        self.messages = []
        self.pending_user_queue = []
        self.is_new_conversation = True
        self.conversation_id = str(uuid.uuid4())
        self.conversation_title = "New Chat"
        self.plan_tracker = None

        if isinstance(self.screen, ChatScreen):
            self.screen.action_clear_chat()
            self.screen.query_one("#conv-title").update("# New Chat")
            self.screen.query_one("#context-info").update("Context: 100%")
            self.screen.update_queue_overlay([])
        self.refresh_context_info()

        self.notify(f"History cleaned. Deleted {before_count} conversation(s).")

    async def load_conversation(self, conversation_id: str) -> bool:
        conversations = await self.storage.list_conversations()
        conversation = next((c for c in conversations if c.get("id") == conversation_id), None)
        if not conversation:
            self.notify("Conversation not found.", severity="error")
            return False

        messages = await self.storage.get_messages(conversation_id)
        self.conversation_id = conversation_id
        self.conversation_title = conversation.get("title", "Conversation")
        self.is_new_conversation = False
        self.messages = list(messages)
        self.pending_user_queue = []
        self.plan_tracker = None

        chat_screen: ChatScreen
        if isinstance(self.screen, ChatScreen):
            chat_screen = self.screen
        else:
            chat_screen = ChatScreen()
            await self.push_screen(chat_screen)

        if isinstance(chat_screen, ChatScreen):
            area = chat_screen.query_one("#message-area", ChatArea)
            area.clear()
            chat_screen.update_queue_overlay([])
            chat_screen.query_one("#conv-title").update(self.conversation_title)
            for msg in messages:
                role = msg.get("role", "assistant")
                content = msg.get("content", "")
                if role in {"system"}:
                    continue
                if role == "assistant" and not content.strip():
                    continue
                if role == "tool":
                    tool_name = msg.get("name", "tool")
                    tool_call_id = msg.get("tool_call_id", f"history-{len(content)}-{tool_name}")
                    chat_screen.add_tool_call(tool_call_id, tool_name, {})
                    chat_screen.add_tool_result(tool_call_id, tool_name, content)
                else:
                    chat_screen.add_message(role, content)
            chat_screen.query_one("#chat-input", Input).focus()
            self.refresh_context_info()
            return True

        return False

    def refresh_context_info(self) -> None:
        stats = session_tracker.get_total_stats()
        input_tokens = int(stats.get("input_tokens", 0))
        output_tokens = int(stats.get("output_tokens", 0))
        total_tokens = int(stats.get("total_tokens", 0))
        context_limit = CONTEXT_LIMIT_TOKENS
        self.context_remaining = max(0, 100 - int((total_tokens / context_limit) * 100))
        if isinstance(self.screen, ChatScreen):
            try:
                self.screen.query_one("#context-info", Label).update(
                    f"Context: {self.context_remaining}% • in {self._format_short(input_tokens)} out {self._format_short(output_tokens)}"
                )
            except Exception:
                pass

    @work(exclusive=True)
    async def check_updates_on_startup(self) -> None:
        result = await check_update_available()
        if not result.get("ok"):
            return
        if result.get("update_available"):
            latest = result.get("latest_version", "latest")
            self.notify(f"Update available: {latest}. Run /update.")

    @work(exclusive=True)
    async def run_update(self) -> None:
        self.notify("Running update via Homebrew...")
        result = await install_or_upgrade()
        if result.get("ok"):
            action = result.get("action", "upgrade")
            self.notify(f"Homebrew {action} completed. Restart opendev.")
            return

        reason = result.get("reason", "")
        if reason == "brew_not_found":
            self.notify("Homebrew not found. Install brew first.", severity="error")
        elif reason == "unsupported_platform":
            self.notify(
                "Auto update is supported on macOS/Linux with Homebrew.",
                severity="warning",
            )
        else:
            stderr = result.get("stderr", "")
            self.notify(
                f"Update failed. {stderr or 'Check brew/tap configuration.'}",
                severity="error",
            )

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
