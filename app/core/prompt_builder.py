from typing import Optional
from app.prompts import SYSTEM_PROMPT, get_agent_prompt
from app.utils import get_project_instructions
import json
from app.core.runtime_config import DEFAULT_AGENT_NAME, DEFAULT_MODE

class PromptBuilder:
    def __init__(self, project_path: str = ".", agent_name: str = DEFAULT_AGENT_NAME):
        self.project_path = project_path
        self.agent_name = agent_name
        self.current_mode = DEFAULT_MODE
        self._project_instructions = None

    def get_system_prompt(self, model: str) -> str:
        parts = [SYSTEM_PROMPT]
        
        opt = self._get_model_optimizations(model)
        if opt: 
            parts.append(opt)
        
        agent_p = get_agent_prompt(self.agent_name)
        if agent_p: 
            parts.append(f"\n\n## ACTIVE AGENT\n{agent_p}")

        mode_rules = (
            "## CURRENT MODE\n"
            f"- Mode: {self.current_mode}\n"
            "- Build: execute directly and produce results.\n"
            "- Plan: for complex tasks create/execute plan; for simple tasks act directly."
        )
        parts.append(f"\n\n{mode_rules}")
        
        if self._project_instructions is None:
            self._project_instructions = get_project_instructions(self.project_path)
        if self._project_instructions:
            parts.append(f"\n\n{self._project_instructions}")
            
        return "\n".join(parts)

    def _get_model_optimizations(self, model: str) -> str:
        m = model.lower()
        if "claude" in m:
            return "## MODEL NOTES\n- Prefer concise, structured reasoning."
        if "gemini" in m:
            return "## MODEL NOTES\n- Keep tool arguments explicit and schema-compliant."
        if any(x in m for x in ["o1", "o3", "o4"]):
            return "## MODEL NOTES\n- Prefer fewer, higher-signal tool calls."
        return ""

    def build_messages(self, messages: list[dict], model: str) -> list[dict]:
        openai_msgs = [{"role": "system", "content": self.get_system_prompt(model)}]
        for msg in messages:
            m = {"role": msg["role"], "content": msg.get("content", "")}
            for key in ["tool_calls", "tool_call_id", "name"]:
                if key in msg: m[key] = msg[key]
            openai_msgs.append(m)
        return openai_msgs

    def set_mode(self, mode: str) -> None:
        self.current_mode = (mode or DEFAULT_MODE).strip()
