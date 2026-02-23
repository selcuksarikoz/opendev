import asyncio
import re
from typing import TYPE_CHECKING, Any

from app.core.runtime_config import PLAN_MODE, PLAN_MESSAGE_PREFIX, PLAN_SKIP_TOKEN
from app.ui.screens import ChatScreen, PlanConfirmModal

if TYPE_CHECKING:
    from app.ui.app import OpenDevApp


class TurnOrchestrator:
    def __init__(self, app: "OpenDevApp"):
        self.app = app

    async def handle_user_turn(self, user_input: str) -> None:
        if self.app.get_current_mode() == PLAN_MODE:
            await self._run_plan_turn(user_input)
            return
        self.app._start_ai_run(user_input)

    async def _run_plan_turn(self, user_input: str) -> bool:
        if not self.app.http_service:
            return False

        plan_summary = await self.app.ai_handler.generate_plan(user_input)
        if not plan_summary or plan_summary.strip() == PLAN_SKIP_TOKEN:
            self.app._start_ai_run(user_input)
            return True

        plan_items = self._extract_plan_items(plan_summary)
        plan_body = self._format_plan_items(plan_items, completed=0)
        plan_msg = f"{PLAN_MESSAGE_PREFIX}{plan_body}"
        self.app.messages.append({"role": "assistant", "content": plan_msg})
        plan_message_index = len(self.app.messages) - 1
        await self.app.storage.save_message(
            self.app.conversation_id,
            "assistant",
            plan_msg,
        )
        if isinstance(self.app.screen, ChatScreen):
            self.app.screen.add_message("assistant", plan_msg)
        self.app.plan_tracker = {
            "active": False,
            "items": plan_items,
            "completed": 0,
            "message_index": plan_message_index,
        }

        approved = await self._confirm_plan_execution(plan_summary)
        if not approved:
            self.app.notify("Plan execution cancelled.", severity="warning")
            return False

        self.app.messages.append(
            {
                "role": "system",
                "content": (
                    "Execution plan approved by user. Execute the approved plan now. "
                    "Do not generate a new plan. Apply this plan step by step and deliver outcomes.\n\n"
                    f"Approved plan:\n{plan_summary}"
                ),
            }
        )
        await self.app.storage.save_message(
            self.app.conversation_id,
            "system",
            f"Execution plan approved by user.\n\nApproved plan:\n{plan_summary}",
        )
        if self.app.plan_tracker:
            self.app.plan_tracker["active"] = True
        approved_msg = "Plan approved. Executing..."
        self.app.messages.append({"role": "assistant", "content": approved_msg})
        if isinstance(self.app.screen, ChatScreen):
            self.app.screen.add_message("assistant", approved_msg)
        try:
            await self.app.storage.save_message(
                self.app.conversation_id,
                "assistant",
                approved_msg,
            )
        except Exception:
            pass
        self.app.call_after_refresh(lambda: self.app._start_ai_run(user_input))
        return True

    async def _confirm_plan_execution(self, plan_summary: str) -> bool:
        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[bool] = loop.create_future()

        def on_decision(result: Any) -> None:
            if not result_future.done():
                result_future.set_result(bool(result))

        self.app.push_screen(PlanConfirmModal(plan_summary), callback=on_decision)
        return await result_future

    @staticmethod
    def _extract_plan_items(plan_summary: str) -> list[str]:
        items: list[str] = []
        for raw in (plan_summary or "").splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith(("- ", "* ")):
                line = line[2:].strip()
            else:
                line = re.sub(r"^\d+\.\s+", "", line)
            if line.startswith("[ ]"):
                line = line[3:].strip()
            elif line.startswith("[x]") or line.startswith("[X]"):
                line = line[3:].strip()
            if line:
                items.append(line)
        if not items and plan_summary.strip():
            items = [x.strip() for x in plan_summary.splitlines() if x.strip()]
        return items

    @staticmethod
    def _format_plan_items(items: list[str], completed: int) -> str:
        if not items:
            return ""
        lines = []
        done = max(0, min(completed, len(items)))
        for idx, item in enumerate(items):
            mark = "x" if idx < done else " "
            lines.append(f"- [{mark}] {item}")
        return "\n".join(lines)
