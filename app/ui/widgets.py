import json
import random
import re
import time
from pathlib import Path
from typing import Any, List, Optional

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll, Container
from textual.widgets import (
    Static,
    Label,
    ListView,
    ListItem,
    Markdown,
    Button,
    Input,
)
from textual.screen import ModalScreen
from textual.message import Message

from app.storage.storage import Storage


class SelectionModal(ModalScreen[Any]):
    """A generic modal for selecting an item from a list of dicts or strings."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "select", "Select"),
        ("y", "select", "Yes"),
        ("d", "delete_all", "Delete All"),
    ]

    def __init__(
        self,
        title: str,
        items: List[Any],
        display_key: str = None,
        show_delete_all: bool = False,
    ):
        super().__init__()
        self.title_text = title
        self.items = items
        self.display_key = display_key
        self.show_delete_all = show_delete_all
        self._delete_all_token = "__delete_all__"
        self._view_items: List[Any] = (
            [self._delete_all_token] + items if show_delete_all else items
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label(self.title_text, id="modal-title")
            with ListView(id="modal-list"):
                for item in self._view_items:
                    if item == self._delete_all_token:
                        display_text = "Delete All History"
                    else:
                        display_text = str(item)
                    if (
                        item != self._delete_all_token
                        and isinstance(item, dict)
                        and self.display_key
                    ):
                        display_text = item.get(self.display_key, str(item))
                    yield ListItem(Label(display_text))
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="cancel-btn")
                if self.show_delete_all:
                    yield Button("Delete All", id="delete-all-btn", variant="error")
                yield Button("Select", id="select-btn", variant="primary")

    def on_mount(self) -> None:
        list_view = self.query_one("#modal-list", ListView)
        list_view.focus()
        if self._view_items and list_view.index is None:
            list_view.index = 0

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_select(self) -> None:
        focused = self.focused
        if isinstance(focused, Button):
            if focused.id == "delete-all-btn":
                self.dismiss("__delete_all__")
                return
            if focused.id == "cancel-btn":
                self.dismiss(None)
                return

        list_view = self.query_one("#modal-list", ListView)
        if not self._view_items:
            self.dismiss(None)
            return
        if list_view.index is None:
            list_view.index = 0
        selected_item = self._view_items[list_view.index]
        if selected_item == self._delete_all_token:
            self.dismiss(self._delete_all_token)
            return
        self.dismiss(selected_item)

    def action_delete_all(self) -> None:
        if self.show_delete_all:
            self.dismiss(self._delete_all_token)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.index is not None:
            selected_item = self._view_items[event.list_view.index]
            if selected_item == self._delete_all_token:
                self.dismiss(self._delete_all_token)
                return
            self.dismiss(selected_item)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "select-btn":
            list_view = self.query_one("#modal-list", ListView)
            if self._view_items:
                if list_view.index is None:
                    list_view.index = 0
                selected_item = self._view_items[list_view.index]
                if selected_item == self._delete_all_token:
                    self.dismiss(self._delete_all_token)
                    return
                self.dismiss(selected_item)
        elif event.button.id == "delete-all-btn":
            self.dismiss(self._delete_all_token)
        elif event.button.id == "cancel-btn":
            self.dismiss(None)


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "confirm", "Confirm"),
        ("y", "confirm", "Yes"),
        ("n", "cancel", "No"),
    ]

    def __init__(self, title: str, message: str, confirm_label: str = "Confirm"):
        super().__init__()
        self.title_text = title
        self.message = message
        self.confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label(self.title_text, id="modal-title")
            yield Label(self.message, classes="modal-subtitle")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="cancel-btn")
                yield Button(self.confirm_label, id="confirm-btn", variant="error")

    def on_mount(self) -> None:
        self.query_one("#cancel-btn").focus()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.dismiss(True)
        elif event.button.id == "cancel-btn":
            self.dismiss(False)


class PermissionModal(ModalScreen[str]):
    """Specialized modal for tool execution permissions."""

    BINDINGS = [
        ("left", "focus_previous", "Focus Previous"),
        ("right", "focus_next", "Focus Next"),
        ("enter", "press_focused", "Confirm"),
        ("space", "press_focused", "Confirm"),
        ("o", "submit('yes')", "Once"),
        ("a", "submit('always')", "Always"),
        ("escape", "submit('no')", "Cancel"),
        ("n", "submit('no')", "No"),
    ]

    def __init__(self, title: str):
        super().__init__()
        self.title_text = title

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container", classes="permission-modal"):
            yield Label(self.title_text, id="modal-title")
            with Horizontal(classes="modal-buttons permission-grid"):
                yield Button("Once", id="yes", variant="primary")
                yield Button("Always", id="always")
                yield Button("Cancel", id="no")

    def on_mount(self) -> None:
        self.query_one("#yes").focus()

    def action_press_focused(self) -> None:
        focused = self.focused
        if focused and hasattr(focused, "id"):
            self.dismiss(focused.id)

    def action_submit(self, choice: str) -> None:
        self.dismiss(choice)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id)


class ApiKeyModal(ModalScreen[str]):
    """Modal to request an API key from the user."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("enter", "submit", "Submit"),
        ("left", "focus_previous", "Focus Previous"),
        ("right", "focus_next", "Focus Next"),
    ]

    def __init__(
        self,
        provider_name: str,
        optional: bool = False,
        has_existing_key: bool = False,
    ):
        super().__init__()
        self.provider_name = provider_name
        self.optional = optional
        self.has_existing_key = has_existing_key

    def compose(self) -> ComposeResult:
        subtitle = "Your key will be saved securely in SQLite (encrypted)."
        placeholder = "Paste key and press Enter..."
        action_label = "Save Key"
        if self.optional:
            if self.has_existing_key:
                subtitle = (
                    "Enter a new API key to replace the current one. "
                    "Leave empty and press Enter to continue with the current key."
                )
            else:
                subtitle = (
                    "Enter a new API key. "
                    "Leave empty and press Enter to continue without changing key settings."
                )
            placeholder = "New key (optional)..."
            action_label = "Continue"

        with Vertical(id="modal-container", classes="api-key-modal"):
            yield Label(f"Enter API Key for {self.provider_name}", id="modal-title")
            yield Label(subtitle, classes="modal-subtitle")
            yield Input(
                placeholder=placeholder,
                id="api-key-input",
                password=True,
            )
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="cancel-btn")
                yield Button(action_label, id="save-btn", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#api-key-input").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self._do_save()
        elif event.button.id == "cancel-btn":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._do_save()

    @work
    async def _do_save(self) -> None:
        input_widget = self.query_one("#api-key-input", Input)
        api_key = input_widget.value.strip()
        if api_key:
            storage = Storage()
            await storage.save_api_key(self.provider_name, api_key)
            self.dismiss(api_key)
        else:
            # Empty input - just close without saving (skip update)
            self.dismiss(None)


class ChatMessage(Static):
    """A widget to display a single chat message."""

    def __init__(self, role: str, message_content: str):
        super().__init__()
        self.role = role
        self.message_content = message_content

    def compose(self) -> ComposeResult:
        # Check if assistant content has special sections
        is_special = self.role in ("thinking", "reasoning", "thought", "todo", "diff")

        # Determine class based on role
        base_class = "message-container"
        role_class = self.role
        if is_special:
            role_class = f"assistant {self.role}-special"

        with Horizontal(classes=f"{base_class} {role_class}-wrapper"):
            with Container(classes=f"message-bubble {self.role}-bubble"):
                if self.role == "user":
                    yield Label(self.message_content, classes="content-label")
                elif is_special:
                    prefix = f"[{self.role.upper()}] "
                    yield Label(
                        f"{prefix}{self.message_content}",
                        classes=f"content-label muted special-{self.role}",
                    )
                else:
                    yield Markdown(self.message_content, classes="content-md")


class LoadingMessage(Static):
    """A simple 'AI is thinking' status with an elapsed timer."""

    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message: str = "AI is thinking..."):
        super().__init__()
        self._message = message
        self._frame = 0
        self._start_time = time.time()
        self._timer = None
        self._cancelled = False

    def compose(self) -> ComposeResult:
        yield Label(
            f"{self.SPINNER_FRAMES[0]} {self._message} (0s)",
            classes="status-muted",
            id="loading-label",
        )

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.1, self._spin)

    def _spin(self) -> None:
        if self._cancelled:
            return
        self._frame = (self._frame + 1) % len(self.SPINNER_FRAMES)
        elapsed = int(time.time() - self._start_time)
        try:
            label = self.query_one("#loading-label", Label)
            label.update(
                f"{self.SPINNER_FRAMES[self._frame]} {self._message} ({elapsed}s)"
            )
        except:
            pass

    def update_message(self, new_message: str) -> None:
        self._cancelled = True
        self._message = new_message
        if self._timer:
            self._timer.stop()
        try:
            label = self.query_one("#loading-label", Label)
            label.update(f"❌ {new_message}")
        except:
            pass


class ToolCallMessage(Static):
    """A compact tool call block under the assistant message."""

    def __init__(self, tool_name: str, arguments: dict):
        super().__init__()
        self.tool_name = tool_name
        self.arguments = arguments

    def compose(self) -> ComposeResult:
        if isinstance(self.arguments, dict):
            arg_str = ", ".join(f"{k}={v}" for k, v in self.arguments.items())
        elif self.arguments is None:
            arg_str = ""
        else:
            arg_str = str(self.arguments)
        # Truncate long arguments
        if len(arg_str) > 60:
            arg_str = arg_str[:57] + "..."

        with Horizontal(classes="message-container assistant-wrapper"):
            with Horizontal(classes="tool-call-container"):
                yield Label("🛠", classes="tool-icon")
                yield Label(self.tool_name, classes="tool-name")
                if arg_str:
                    yield Label(f"({arg_str})", classes="tool-args")


class ChatArea(VerticalScroll):
    """A scrollable area for chat messages."""

    def add_message(
        self, role: str, content: str, is_first_chunk: bool = False
    ) -> None:
        # If it's the first chunk of a streamed assistant message, and there's a LoadingMessage, remove it first.
        if role == "assistant" and is_first_chunk:
            self.query(LoadingMessage).remove()

        # Group assistant tags visually but maintain them in fewer widgets
        if role == "assistant":
            # Just mount the whole content as one assistant message to prevent block fragmentation
            # We'll rely on CSS and internal Markdown/Label to keep it tight
            self.mount(ChatMessage("assistant", content))
        else:
            msg_widget = ChatMessage(role, content)
            self.mount(msg_widget)

        self.scroll_end()

    def add_tool_call(self, tool_name: str, arguments: dict) -> None:
        # If there's a LoadingMessage, remove it before adding a tool call
        if self.children and isinstance(self.children[-1], LoadingMessage):
            self.children[-1].remove()

        self.mount(ToolCallMessage(tool_name, arguments))
        self.scroll_end()

    def update_last_assistant_message(self, content: str) -> None:
        self.query(LoadingMessage).remove()

        messages = self.query(ChatMessage)
        if messages:
            last_message = messages.last()

            if last_message.role in ("assistant", "thinking"):
                last_message.message_content = content
                if last_message.role == "assistant":
                    try:
                        md_widget = last_message.query_one(".content-md", Markdown)
                        md_widget.update(content)
                    except Exception:
                        last_message.remove()
                        self.mount(ChatMessage("assistant", content))
                else:
                    label_widget = last_message.query_one(".content-label", Label)
                    label_widget.update(f"[{last_message.role.upper()}] {content}")
                self.scroll_end()
            else:
                self.add_message("assistant", content)
        else:
            self.add_message("assistant", content)

    def clear(self) -> None:
        self.query(ChatMessage).remove()
        # Ensure any lingering loading message is also removed
        self.query(LoadingMessage).remove()


class AutocompleteDropdown(ListView):
    """Dropdown list for autocompletion."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def update_items(self, items: List[str]):
        self.clear()
        for item in items:
            li = ListItem(Label(item))
            # Store the original text value on the ListItem for easy access
            li._item_value = item
            self.append(li)

        if items:
            self.add_class("visible")
            self.index = 0
        else:
            self.remove_class("visible")

    @property
    def is_visible(self) -> bool:
        return self.has_class("visible")


class CustomInput(Input):
    """A custom input field that handles autocompletion, history, and pastes."""

    _shared_history: List[str] = []
    _history_index: int = -1

    class Selected(Message):
        def __init__(self, value: str):
            super().__init__()
            self.value = value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._real_value = ""
        self._autocomplete_timer = None
        self._commands = [
            "/new",
            "/model",
            "/agents",
            "/clear",
            "/clean history",
            "/update",
            "/help",
            "/settings",
            "/compact",
        ]

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        val = event.value

        # Paste/Image logic - only match actual file paths, not placeholder text
        image_pattern = r"^[a-zA-Z0-9_/.-]+\.(png|jpg|jpeg|gif|webp)$"
        if re.search(image_pattern, val) and len(val.split()) == 1:
            self._real_value = val
            self.value = "[image1]"
            return

        if len(val) > 100 and not val.startswith("[pasted text"):
            line_count = val.count("\n") + 1
            if line_count == 1 and len(val) > 500:
                line_count = len(val) // 80
            self._real_value = val
            self.value = f"[pasted text: {line_count} lines]"
            return

        # Autocomplete Logic with Debounce
        if self._autocomplete_timer:
            self._autocomplete_timer.stop()

        # Fast command autocomplete (doesn't need worker)
        if val.startswith("/") and not "@" in val:
            self._handle_autocomplete_sync(val)
        else:
            self._autocomplete_timer = self.set_timer(
                0.15, lambda: self._handle_autocomplete_worker(val)
            )

    def _handle_autocomplete_sync(self, val: str):
        try:
            dropdown = self.screen.query_one("#autocomplete-list", AutocompleteDropdown)
            matches = [c for c in self._commands if c.startswith(val)]
            dropdown.update_items(matches)
            self._position_dropdown(dropdown, len(matches))
        except Exception:
            pass

    @work(thread=True)
    def _handle_autocomplete_worker(self, val: str):
        if not val or (not val.startswith("/") and "@" not in val):
            self.app.call_from_thread(self._update_dropdown, [])
            return

        items = []
        if "@" in val:
            parts = val.rsplit("@", 1)
            query = parts[-1].lower()

            try:
                root = Path(".")
                count = 0
                skip_dirs = {
                    ".git",
                    "node_modules",
                    "__pycache__",
                    ".venv",
                    "venv",
                    "dist",
                    "build",
                }

                search_path = root
                search_name = query

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

                        full_str = str(item)
                        if full_str.startswith("./"):
                            full_str = full_str[2:]

                        if search_name in item.name.lower():
                            items.append(full_str + ("/" if item.is_dir() else ""))
                            count += 1
                        if count > 15:
                            break

                # Git branches - more cautious
                if len(query) > 1 and len(items) < 10 and (root / ".git").exists():
                    git_heads = root / ".git" / "refs" / "heads"
                    if git_heads.exists():
                        # Only search heads, no rglob if query is short
                        for branch in git_heads.iterdir():
                            if branch.is_file() and query in branch.name.lower():
                                items.append(f"branch:{branch.name}")

            except Exception:
                pass

        self.app.call_from_thread(self._update_dropdown, items[:15])

    def _update_dropdown(self, items: List[str]):
        try:
            dropdown = self.screen.query_one("#autocomplete-list", AutocompleteDropdown)
            dropdown.update_items(items)
            self._position_dropdown(dropdown, len(items))
        except Exception:
            pass

    def _position_dropdown(
        self, dropdown: AutocompleteDropdown, item_count: int
    ) -> None:
        if item_count <= 0:
            return

        input_region = self.region
        screen_size = self.screen.size
        dropdown_height = min(max(item_count + 2, 4), 14)
        dropdown_width = max(42, min(input_region.width, 110))

        x = input_region.x
        y_above_input = input_region.y - dropdown_height - 1
        y = y_above_input if y_above_input >= 1 else input_region.y + input_region.height

        max_x = max(1, screen_size.width - dropdown_width - 1)
        x = min(x, max_x)

        dropdown.styles.width = dropdown_width
        dropdown.styles.max_height = dropdown_height
        dropdown.styles.offset = (x, y)

    def add_to_history(self, text: str):
        if text and (
            not CustomInput._shared_history or text != CustomInput._shared_history[-1]
        ):
            CustomInput._shared_history.append(text)
        CustomInput._history_index = -1

    async def handle_key(self, event) -> None:
        dropdown = None
        try:
            dropdown = self.screen.query_one("#autocomplete-list", AutocompleteDropdown)
        except Exception:
            pass

        if dropdown and dropdown.is_visible:
            num_children = len(dropdown.children) if dropdown.children else 0
            if num_children > 0:
                if event.key == "up":
                    event.prevent_default()
                    event.stop()
                    dropdown.index = (
                        dropdown.index - 1
                        if dropdown.index is not None and dropdown.index > 0
                        else num_children - 1
                    )
                    return
                if event.key == "down":
                    event.prevent_default()
                    event.stop()
                    dropdown.index = (
                        dropdown.index + 1
                        if dropdown.index is not None and dropdown.index < num_children - 1
                        else 0
                    )
                    return
                if event.key in ("enter", "tab"):
                    event.prevent_default()
                    event.stop()
                    if dropdown.index is not None and dropdown.index < num_children:
                        selected_item = dropdown.children[dropdown.index]
                        selected_text = getattr(selected_item, "_item_value", "")
                        if not selected_text:
                            try:
                                label = selected_item.query_one(Label)
                                selected_text = str(label.renderable)
                            except Exception:
                                selected_text = ""
                        if self.value.startswith("/"):
                            self.value = selected_text
                        elif "@" in self.value:
                            self.value = self.value.split("@")[0] + "@" + selected_text
                        dropdown.remove_class("visible")
                        self.cursor_position = len(self.value)
                    return
                if event.key == "escape":
                    event.prevent_default()
                    event.stop()
                    dropdown.remove_class("visible")
                    return

        if event.key == "up" and not (dropdown and dropdown.is_visible):
            if CustomInput._shared_history:
                if CustomInput._history_index == -1:
                    CustomInput._history_index = len(CustomInput._shared_history) - 1
                elif CustomInput._history_index > 0:
                    CustomInput._history_index -= 1
                self.value = CustomInput._shared_history[CustomInput._history_index]
                self.cursor_position = len(self.value)
            return

        if event.key == "down" and not (dropdown and dropdown.is_visible):
            if CustomInput._shared_history:
                if CustomInput._history_index != -1:
                    if CustomInput._history_index < len(CustomInput._shared_history) - 1:
                        CustomInput._history_index += 1
                        self.value = CustomInput._shared_history[
                            CustomInput._history_index
                        ]
                    else:
                        CustomInput._history_index = -1
                        self.value = ""
                else:
                    CustomInput._history_index = 0
                    self.value = CustomInput._shared_history[0]
                self.cursor_position = len(self.value)
            return

        await super().handle_key(event)


class TipsWidget(Static):
    """A widget to display a random tip."""

    def on_mount(self) -> None:
        self.update_tip()

    def update_tip(self) -> None:
        try:
            tips_path = Path("tips.json")
            if tips_path.exists():
                tips = json.loads(tips_path.read_text())
                if tips:
                    self.update(f"💡 Tip: {random.choice(tips)}")
                else:
                    self.update("💡 Tip: Try /model to switch models.")
            else:
                self.update("💡 Tip: Use /help for assistance.")
        except Exception:
            self.update("💡 Tip: Use /help for assistance.")
