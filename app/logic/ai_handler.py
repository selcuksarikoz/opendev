import json
import time
from typing import Any
from app.utils.session_stats import session_tracker
from app.utils.logger import log_error


class AIHandler:
    def __init__(self, app):
        self.app = app
        self.max_tool_rounds = 8

    async def get_response(self, user_input: str):
        if not self.app.http_service:
            return
        self.app.is_streaming = True
        pending_writes = []
        response_text, reasoning_text = "", ""
        tool_round = 0
        last_tool_calls: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()

        try:
            while self.app.is_streaming:
                response_text = ""
                reasoning_text = ""
                tool_calls = []
                tools = self.app.tool_manager.get_tools_for_api()
                ui_update_interval, last_update = 0.3, 0

                if hasattr(self.app.screen, "query_one"):
                    from app.ui.widgets import LoadingMessage, ChatArea

                    area = self.app.screen.query_one(ChatArea)
                    area.mount(LoadingMessage("AI is thinking..."))
                    area.scroll_end()

                async for chunk_type, data in self.app.http_service.chat(
                    self.app.messages,
                    tools,
                    stream=True,
                    max_tokens=int(self.app.ai_settings.get("max_tokens", 4096)),
                    temperature=float(self.app.ai_settings.get("temperature", 0.5)),
                    top_p=float(self.app.ai_settings.get("top_p", 1.0)),
                ):
                    if not self.app.is_streaming:
                        break
                    now = time.time()

                    if chunk_type == "reasoning":
                        reasoning_text += data
                        if now - last_update > ui_update_interval:
                            self._update_ui_status(
                                f"Thinking: {reasoning_text[:60]}..."
                            )
                            last_update = now
                    elif chunk_type == "content":
                        if not response_text:
                            self._update_ui_status("AI is responding...")
                        is_first = not response_text
                        response_text += data
                        if now - last_update > ui_update_interval:
                            self._update_ui_content(response_text, is_first)
                            last_update = now
                    elif chunk_type == "tool_call":
                        self._update_ui_status(f"Running tool: {data['name']}...")
                        tool_calls.append(data)

                if tool_calls:
                    self._process_tool_calls(tool_calls)
                last_tool_calls = tool_calls

                # Message building and saving
                msg = {"role": "assistant", "content": response_text or ""}
                if reasoning_text:
                    msg["reasoning"] = reasoning_text
                if tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"]),
                            },
                        }
                        for tc in tool_calls
                    ]

                self.app.messages.append(msg)
                pending_writes.append(
                    {"conversation_id": self.app.conversation_id, **msg}
                )

                if not tool_calls:
                    break

                tool_round += 1
                if tool_round > self.max_tool_rounds:
                    self.app.notify(
                        "Stopped tool loop: reached max tool rounds.",
                        severity="warning",
                    )
                    break

                signatures = self._tool_signatures(tool_calls)
                if signatures and all(sig in seen_signatures for sig in signatures):
                    self.app.notify(
                        "Stopped tool loop: repeated tool call detected.",
                        severity="warning",
                    )
                    break
                seen_signatures.update(signatures)

                if not await self._execute_tools(tool_calls, pending_writes):
                    break

            await self._finalize_stats()

            if response_text or reasoning_text:
                self._finalize_message(response_text, reasoning_text, last_tool_calls)

        except Exception as e:
            log_error("AI Loop Error", e)
            self.app.notify(f"Error: {str(e)}", severity="error")
        finally:
            self.app.is_streaming = False
            if not getattr(self.app, "is_shutting_down", False):
                for w in pending_writes:
                    try:
                        await self.app.storage.save_message(
                            w["conversation_id"],
                            w["role"],
                            w["content"],
                            w.get("tool_calls"),
                            w.get("reasoning"),
                        )
                    except Exception as exc:
                        if "closed" in str(exc).lower():
                            break
                        raise

    def _tool_signatures(self, tool_calls: list[dict[str, Any]]) -> list[str]:
        signatures: list[str] = []
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("arguments", {})
            try:
                args_str = json.dumps(args, sort_keys=True, ensure_ascii=True)
            except Exception:
                args_str = str(args)
            signatures.append(f"{name}:{args_str}")
        return signatures

    def _finalize_message(
        self, response_text: str, reasoning_text: str, tool_calls: list
    ):
        try:
            from app.ui.screens import ChatScreen
            from app.ui.widgets import LoadingMessage, ChatArea

            area = self.app.screen.query_one(ChatArea)
            for child in list(area.children):
                if isinstance(child, LoadingMessage):
                    child.remove()

            # Force a final UI sync so the tail of streamed content is never lost.
            if isinstance(self.app.screen, ChatScreen) and response_text:
                self.app.screen.update_last_assistant_message(response_text)
        except Exception:
            pass

    def _clear_loading(self):
        try:
            from app.ui.widgets import LoadingMessage, ChatArea

            area = self.app.screen.query_one(ChatArea)
            for child in area.children:
                if isinstance(child, LoadingMessage):
                    child.remove()
            if (
                area.children
                and hasattr(area.children[-1], "role")
                and area.children[-1].role == "assistant"
            ):
                area.children[-1].remove()
        except:
            pass

    def _update_ui_status(self, text: str):
        try:
            from app.ui.widgets import LoadingMessage, ChatArea

            area = self.app.screen.query_one(ChatArea)
            if area.children and isinstance(area.children[-1], LoadingMessage):
                area.children[-1].update_message(text)
                area.scroll_end()
        except:
            pass

    def _update_ui_content(self, text: str, is_first: bool):
        try:
            from app.ui.screens import ChatScreen

            if isinstance(self.app.screen, ChatScreen):
                if is_first:
                    self.app.screen.add_message("assistant", text, is_first_chunk=True)
                else:
                    self.app.screen.update_last_assistant_message(text)
        except:
            pass

    def _process_tool_calls(self, tool_calls):
        try:
            from app.ui.screens import ChatScreen

            if isinstance(self.app.screen, ChatScreen):
                for tc in tool_calls:
                    self.app.screen.add_tool_call(tc["name"], tc["arguments"])
        except:
            pass

    async def _execute_tools(self, tool_calls, pending_writes) -> bool:
        # Simplified for brevity, would include permission checks from app.py
        seen_in_round: set[str] = set()
        for tc in tool_calls:
            sig = self._tool_signatures([tc])[0]
            if sig in seen_in_round:
                continue
            seen_in_round.add(sig)
            result = await self.app.tool_manager.execute(tc["name"], tc["arguments"])
            tool_msg = {
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tc["name"],
                "content": str(result),
            }
            self.app.messages.append(tool_msg)
            pending_writes.append(
                {"conversation_id": self.app.conversation_id, **tool_msg}
            )
            session_tracker.record_tool_call(
                success=not str(result).startswith("Error:")
            )
        return True

    async def _finalize_stats(self):
        stats = session_tracker.get_total_stats()
        total, limit = stats.get("total_tokens", 0), 128_000
        self.app.context_remaining = max(0, 100 - int((total / limit) * 100))
        if self.app.context_remaining < 20 and len(self.app.messages) > 10:
            self.app.compact_conversation()
