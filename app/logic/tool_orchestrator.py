import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from app.tools.agent_tools import HANDOFF_PREFIX

if TYPE_CHECKING:
    from app.ui.app import OpenDevApp


class ToolOrchestrator:
    def __init__(self, app: "OpenDevApp", max_parallel_tools: int):
        self.app = app
        self.max_parallel_tools = max(1, int(max_parallel_tools))

    async def execute_tools(
        self,
        tool_calls: list[dict[str, Any]],
        pending_writes: list[dict[str, Any]],
        signature_fn,
    ) -> tuple[bool, int, set[str], int, int]:
        failed_in_round: set[str] = set()
        handoff_in_round = 0
        success_in_round = 0

        runnable: list[tuple[int, dict[str, Any], str]] = []
        for tc in tool_calls:
            sig = signature_fn([tc])[0]
            runnable.append((len(runnable), tc, sig))

        semaphore = asyncio.Semaphore(self.max_parallel_tools)

        async def run_one(
            idx: int, tool_call: dict[str, Any], sig: str
        ) -> tuple[int, dict[str, Any], str, str, int]:
            async with semaphore:
                start = time.perf_counter()
                result = await self.app.tool_manager.execute(
                    tool_call["name"], tool_call["arguments"]
                )
                duration_ms = int((time.perf_counter() - start) * 1000)
                return idx, tool_call, sig, str(result), duration_ms

        tasks = [run_one(idx, tc, sig) for idx, tc, sig in runnable]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        ordered_results: list[tuple[int, dict[str, Any], str, str, int]] = []
        for item in raw_results:
            if isinstance(item, Exception):
                continue
            ordered_results.append(item)
        ordered_results.sort(key=lambda x: x[0])

        for _, tc, sig, result, duration_ms in ordered_results:
            self._push_tool_result_ui(
                tool_call_id=tc.get("id", ""),
                tool_name=tc.get("name", "tool"),
                result=result,
                duration_ms=duration_ms,
            )
            if tc["name"] == "handoff_agent":
                applied, handoff_result = self._apply_handoff_result(result)
                result = handoff_result
                if applied:
                    handoff_in_round += 1
                    pending_writes.append(
                        {
                            "conversation_id": self.app.conversation_id,
                            "role": "system",
                            "content": handoff_result,
                        }
                    )
            if result.startswith("Error:"):
                failed_in_round.add(sig)
            else:
                success_in_round += 1
            tool_msg = {
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tc["name"],
                "content": result,
            }
            self.app.messages.append(tool_msg)
            pending_writes.append(
                {"conversation_id": self.app.conversation_id, **tool_msg}
            )

        exec_count = len(ordered_results)
        continue_loop = exec_count > 0
        return (
            continue_loop,
            exec_count,
            failed_in_round,
            handoff_in_round,
            success_in_round,
        )

    def _push_tool_result_ui(
        self,
        tool_call_id: str,
        tool_name: str,
        result: str,
        duration_ms: int | None = None,
    ) -> None:
        try:
            from app.ui.screens import ChatScreen

            if isinstance(self.app.screen, ChatScreen):
                self.app.screen.add_tool_result(
                    tool_call_id,
                    tool_name,
                    result,
                    duration_ms=duration_ms,
                )
        except Exception:
            pass

    def _apply_handoff_result(self, result: str) -> tuple[bool, str]:
        if not result.startswith(HANDOFF_PREFIX):
            return False, result
        raw = result[len(HANDOFF_PREFIX) :].strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return False, "Error: Invalid handoff payload."

        to_agent = str(payload.get("to_agent", "")).strip()
        task = str(payload.get("task", "")).strip()
        context = str(payload.get("context", "")).strip()
        applied, message = self.app.apply_agent_handoff(
            to_agent=to_agent,
            task=task,
            context=context,
        )
        if not applied:
            return False, message
        return True, f"Handoff applied. {message}"
