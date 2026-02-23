import json
import time
from typing import Any
from app.utils.session_stats import session_tracker
from app.utils.logger import log_error
from app.logic.tool_orchestrator import ToolOrchestrator
from app.core.runtime_config import (
    PLAN_PROMPT_TEMPLATE,
    PLAN_SKIP_TOKEN,
    AI_DEFAULT_MAX_TOKENS,
    AI_DEFAULT_TEMPERATURE,
    AI_DEFAULT_TOP_P,
    TOOL_MAX_PARALLEL,
)


class AIHandler:
    def __init__(self, app):
        self.app = app
        self.max_parallel_tools = TOOL_MAX_PARALLEL
        self.tool_orchestrator = ToolOrchestrator(app, self.max_parallel_tools)

    async def generate_plan(self, user_input: str) -> str:
        if not self.app.http_service:
            return ""
        self._show_loading("AI is planning...")
        planning_prompt = PLAN_PROMPT_TEMPLATE.format(user_input=user_input)
        planning_messages = list(self.app.messages) + [
            {"role": "user", "content": planning_prompt}
        ]
        chunks: list[str] = []
        try:
            async for chunk_type, data in self.app.http_service.chat(
                planning_messages,
                tools=[],
                stream=False,
                max_tokens=600,
                temperature=0.2,
            ):
                if chunk_type == "content" and data:
                    chunks.append(str(data))
        except Exception as e:
            log_error("Plan generation failed", e)
            self.app.notify(f"Plan generation failed: {str(e)}", severity="error")
            return ""
        finally:
            self._clear_loading()
        result = "\n".join(chunks).strip()
        if result.upper() == PLAN_SKIP_TOKEN:
            return PLAN_SKIP_TOKEN
        return result

    def _show_loading(self, text: str) -> None:
        try:
            from app.ui.widgets import LoadingMessage

            area = self._get_chat_area()
            if area is None:
                return
            for child in list(area.children):
                if isinstance(child, LoadingMessage):
                    child.remove()
            area.mount(LoadingMessage(text))
            area.scroll_end()
        except Exception:
            pass

    def _get_chat_area(self):
        try:
            from app.ui.screens import ChatScreen
            from app.ui.widgets import ChatArea

            if not isinstance(self.app.screen, ChatScreen):
                return None
            return self.app.screen.query_one(ChatArea)
        except Exception:
            return None

    async def get_response(self, user_input: str):
        if not self.app.http_service:
            return
        self.app.is_streaming = True
        pending_writes = []
        response_text, reasoning_text = "", ""
        accumulated_response_text = ""
        assistant_stream_started = False
        last_tool_calls: list[dict[str, Any]] = []

        try:
            while self.app.is_streaming:
                response_text = ""
                reasoning_text = ""
                tool_calls = []
                streamed_assistant_preview = False
                tools = self.app.tool_manager.get_tools_for_api()
                ui_update_interval, last_update = 0.3, 0

                area = self._get_chat_area()
                if area is not None:
                    from app.ui.widgets import LoadingMessage

                    area.mount(LoadingMessage("AI is thinking..."))
                    area.scroll_end()

                async for chunk_type, data in self.app.http_service.chat(
                    self.app.messages,
                    tools,
                    stream=True,
                    max_tokens=int(
                        self.app.ai_settings.get("max_tokens", AI_DEFAULT_MAX_TOKENS)
                    ),
                    temperature=float(
                        self.app.ai_settings.get("temperature", AI_DEFAULT_TEMPERATURE)
                    ),
                    top_p=float(self.app.ai_settings.get("top_p", AI_DEFAULT_TOP_P)),
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
                        response_text += data
                        accumulated_response_text += data
                        is_first = not assistant_stream_started
                        if is_first or (now - last_update > ui_update_interval):
                            self._update_ui_content(accumulated_response_text, is_first)
                            if is_first:
                                assistant_stream_started = True
                            streamed_assistant_preview = True
                            last_update = now
                    elif chunk_type == "tool_call":
                        self._update_ui_status(f"Running tool: {data['name']}...")
                        tool_calls.append(data)

                if tool_calls:
                    self._process_tool_calls(tool_calls)
                last_tool_calls = tool_calls

                # Message building and saving
                assistant_content = response_text or ""
                msg = {"role": "assistant", "content": assistant_content}
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

                if assistant_content.strip() or reasoning_text or tool_calls:
                    self.app.messages.append(msg)
                    pending_writes.append(
                        {"conversation_id": self.app.conversation_id, **msg}
                    )

                if not tool_calls:
                    break

                (
                    should_continue,
                    _round_exec_count,
                    _round_failures,
                    _round_handoffs,
                    round_success_count,
                ) = await self._execute_tools(
                    tool_calls, pending_writes
                )
                if round_success_count > 0:
                    self.app.advance_plan_progress(1)

                if not should_continue:
                    break

            await self._finalize_stats()
            if self.app.is_streaming:
                self.app.finalize_plan_progress()

            if accumulated_response_text or reasoning_text:
                self._finalize_message(
                    accumulated_response_text, reasoning_text, last_tool_calls
                )

        except Exception as e:
            log_error("AI Loop Error", e)
            self._clear_loading()
            self.app.notify(f"Error: {str(e)}", severity="error")
        finally:
            self.app.is_streaming = False
            self._clear_loading()
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
            from app.ui.widgets import LoadingMessage

            area = self._get_chat_area()
            if area is None:
                return
            for child in area.children:
                if isinstance(child, LoadingMessage):
                    child.remove()
        except Exception:
            pass

    def _update_ui_status(self, text: str):
        try:
            from app.ui.widgets import LoadingMessage

            area = self._get_chat_area()
            if area is None:
                return
            if area.children and isinstance(area.children[-1], LoadingMessage):
                area.children[-1].update_message(text)
                area.scroll_end()
        except Exception:
            pass

    def _update_ui_content(self, text: str, is_first: bool):
        try:
            from app.ui.screens import ChatScreen

            if isinstance(self.app.screen, ChatScreen):
                if is_first:
                    self.app.screen.add_message("assistant", text, is_first_chunk=True)
                else:
                    self.app.screen.update_last_assistant_message(text)
        except Exception:
            pass

    def _remove_last_assistant_preview(self) -> None:
        try:
            from app.ui.widgets import ChatMessage

            area = self._get_chat_area()
            if area is None:
                return
            messages = area.query(ChatMessage)
            if messages:
                last_message = messages.last()
                if getattr(last_message, "role", None) == "assistant":
                    last_message.remove()
        except Exception:
            pass

    def _process_tool_calls(self, tool_calls):
        try:
            from app.ui.screens import ChatScreen

            if isinstance(self.app.screen, ChatScreen):
                for tc in tool_calls:
                    self.app.screen.add_tool_call(
                        tc.get("id", ""),
                        tc["name"],
                        tc.get("arguments", {}),
                    )
        except Exception:
            pass

    async def _execute_tools(
        self, tool_calls, pending_writes
    ) -> tuple[bool, int, set[str], int, int]:
        return await self.tool_orchestrator.execute_tools(
            tool_calls=tool_calls,
            pending_writes=pending_writes,
            signature_fn=self._tool_signatures,
        )

    async def _finalize_stats(self):
        stats = session_tracker.get_total_stats()
        self.app.refresh_context_info()
        if self.app.context_remaining < 20 and len(self.app.messages) > 10:
            self.app.compact_conversation()
