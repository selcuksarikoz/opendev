import os
from pathlib import Path
from typing import List, Any

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, Container
from textual.widgets import Static, Label, Input, Button
from textual.screen import Screen, ModalScreen
from textual.binding import Binding
from textual import on

from app.ui.widgets import ChatArea, CustomInput, TipsWidget, AutocompleteDropdown
from app.utils import get_project_version

ASCII_LOGO = r"""                             _            
                            | |           
   ___  _ __   ___ _ __   __| | _____   __
  / _ \| '_ \ / _ \ '_ \ / _` |/ _ \ \ / /
 | (_) | |_) |  __/ | | | (_| |  __/\ V / 
  \___/| .__/ \___|_| |_|\__,_|\___| \_/  
       | |                                
       |_|                                """


class BaseScreen(Screen):
    """Base class for screens with a shared footer."""

    def compose_footer(self) -> ComposeResult:
        with Horizontal(id="status-bar"):
            yield Label("", id="status-left")
            yield Label("", id="status-center")
            yield Label(get_project_version(), id="status-right")

    def update_status(self) -> None:
        try:
            app = self.app
            path = os.getcwd().replace(os.path.expanduser("~"), "~")
            status_center = f"{app.get_current_mode()} {app.get_status_text()}"

            self.query_one("#status-left", Label).update(f"{path} |")
            self.query_one("#status-center", Label).update(f"{status_center} |")
        except:
            pass


class WelcomeScreen(BaseScreen):
    """The initial screen with the logo and first input."""

    def compose(self) -> ComposeResult:
        with Vertical(id="screen-container"):
            with Vertical(id="main-container"):
                yield Static(ASCII_LOGO, id="logo")
                with Vertical(id="input-wrapper"):
                    yield CustomInput(
                        placeholder='Ask anything... "Fix a TODO in the codebase"',
                        id="initial-input",
                    )
                    with Horizontal(id="input-meta"):
                        yield Label("", id="chat-status")
            yield TipsWidget(id="tips-area")
        yield from self.compose_footer()
        yield AutocompleteDropdown(id="autocomplete-list")

    def on_mount(self) -> None:
        self.query_one("#initial-input").focus()
        self.update_status()


class ChatScreen(BaseScreen):
    """The main chat conversation screen."""

    BINDINGS = [
        Binding("ctrl+l", "clear_chat", "Clear Chat"),
        Binding("escape", "cancel_or_back", "Back/Cancel", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="screen-container"):
            with Horizontal(id="chat-header"):
                yield Label("# Conversation Title", id="conv-title")
                yield Label("Context: 100%", id="context-info")

            yield ChatArea(id="message-area")

            with Vertical(id="chat-footer"):
                with Horizontal(id="queue-overlay"):
                    pass
                with Vertical(id="input-wrapper"):
                    yield CustomInput(placeholder="Send a message...", id="chat-input")

                with Horizontal(id="chat-meta"):
                    yield Label("", id="chat-status")
        yield AutocompleteDropdown(id="autocomplete-list")

    def on_mount(self) -> None:
        self.query_one("#chat-input").focus()

    def add_message(
        self, role: str, content: str, is_first_chunk: bool = False
    ) -> None:
        area = self.query_one("#message-area", ChatArea)
        area.add_message(role, content, is_first_chunk=is_first_chunk)

    def add_tool_call(self, tool_name: str, arguments: dict) -> None:
        area = self.query_one("#message-area", ChatArea)
        area.add_tool_call(tool_name, arguments)

    def update_last_assistant_message(self, content: str) -> None:
        area = self.query_one("#message-area", ChatArea)
        area.update_last_assistant_message(content)

    def update_status_text(self, text: str) -> None:
        try:
            self.query_one("#chat-status", Label).update(text)
        except:
            pass

    def update_queue_overlay(self, queued_messages: list[str]) -> None:
        try:
            overlay = self.query_one("#queue-overlay")
            if not queued_messages:
                overlay.display = False
                for child in list(overlay.children):
                    child.remove()
                return

            for child in list(overlay.children):
                child.remove()

            for message in queued_messages[:3]:
                text = message.replace("\n", " ").strip()
                if len(text) > 36:
                    text = text[:33] + "..."
                overlay.mount(Label(" QUEUED ", classes="queue-chip"))
                overlay.mount(Label(text, classes="queue-msg"))

            extra = len(queued_messages) - min(3, len(queued_messages))
            if extra > 0:
                overlay.mount(Label(f" +{extra} more ", classes="queue-chip"))

            overlay.display = True
        except Exception:
            pass

    def action_cancel_or_back(self) -> None:
        if self.app.is_streaming:
            self.app.is_streaming = False
            self._show_cancelled()
        else:
            self.app.pop_screen()

    def _show_cancelled(self):
        try:
            from app.ui.widgets import LoadingMessage, ChatArea

            area = self.query_one("#message-area", ChatArea)
            for child in area.children:
                if isinstance(child, LoadingMessage):
                    child.update_message("❌ Request cancelled")
        except:
            pass

    def action_clear_chat(self) -> None:
        area = self.query_one("#message-area", ChatArea)
        area.clear()
        self.app.messages = []
        self.query_one("#tips-area", TipsWidget).update_tip()


class SettingsScreen(ModalScreen[dict]):
    """Settings modal for AI configuration."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Save"),
    ]

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self._input_ids = ["max-tokens", "temperature", "top-p"]
        self._focus_index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-container"):
            yield Label("⚙️ AI Settings", id="settings-title")

            yield Input(
                value=f"Max Tokens: {self.settings.get('max_tokens', '4096')}",
                id="max-tokens",
            )

            yield Input(
                value=f"Temperature: {self.settings.get('temperature', '0.5')}",
                id="temperature",
            )

            yield Input(
                value=f"Top P: {self.settings.get('top_p', '1.0')}",
                id="top-p",
            )

            yield Label(
                "Tab/Arrows: Navigate  •  Ctrl+S: Save  •  Esc: Cancel",
                classes="settings-hint",
            )

            with Horizontal(classes="settings-buttons"):
                yield Button("Cancel", id="cancel-btn", variant="error")
                yield Button("Save", id="save-btn", variant="primary")

    def on_mount(self) -> None:
        self._focus_index = 0
        self.query_one("#max-tokens").focus()

    def on_key(self, event) -> None:
        if event.key == "tab":
            self._focus_next()
            event.prevent_default()
        elif event.key == "shift+tab":
            self._focus_previous()
            event.prevent_default()
        elif event.key == "down":
            self._focus_next()
            event.prevent_default()
        elif event.key == "up":
            self._focus_previous()
            event.prevent_default()
        elif event.key == "enter":
            self._save_settings()
            event.prevent_default()

    def _focus_next(self):
        self._focus_index = (self._focus_index + 1) % len(self._input_ids)
        self.query_one(f"#{self._input_ids[self._focus_index]}").focus()

    def _focus_previous(self):
        self._focus_index = (self._focus_index - 1) % len(self._input_ids)
        self.query_one(f"#{self._input_ids[self._focus_index]}").focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_save(self) -> None:
        self._save_settings()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self._save_settings()
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def _save_settings(self) -> None:
        def extract_value(text: str, key: str) -> str:
            prefix = f"{key}: "
            if text.startswith(prefix):
                return text[len(prefix) :].strip()
            return text.strip()

        settings = {
            "max_tokens": extract_value(
                self.query_one("#max-tokens").value, "Max Tokens"
            )
            or "4096",
            "temperature": extract_value(
                self.query_one("#temperature").value, "Temperature"
            )
            or "0.5",
            "top_p": extract_value(self.query_one("#top-p").value, "Top P") or "1.0",
        }
        self.dismiss(settings)


class PlanConfirmModal(ModalScreen[bool]):
    """Modal to confirm plan execution in Plan mode."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Execute"),
        Binding("space", "confirm", "Execute"),
        Binding("y", "confirm", "Yes"),
        Binding("n", "cancel", "No"),
        Binding("left", "focus_previous", "Previous"),
        Binding("right", "focus_next", "Next"),
    ]

    def __init__(self, plan_summary: str):
        super().__init__()
        self.plan_summary = plan_summary

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label("📋 Plan Review", id="modal-title")
            yield Label(self.plan_summary, classes="plan-summary")
            yield Label(
                "Enter/Space/Y: Execute  •  N/Esc: Cancel  •  Arrows: Navigate",
                classes="plan-hint",
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="cancel-btn", variant="error")
                yield Button("Execute", id="execute-btn", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#execute-btn").focus()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "execute-btn":
            self.dismiss(True)
        elif event.button.id == "cancel-btn":
            self.dismiss(False)
