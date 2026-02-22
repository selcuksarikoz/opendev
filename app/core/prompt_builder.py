from typing import Optional
from app.prompts import SYSTEM_PROMPT, get_agent_prompt
from app.utils import get_project_instructions
import json

class PromptBuilder:
    def __init__(self, project_path: str = ".", agent_name: str = "coder"):
        self.project_path = project_path
        self.agent_name = agent_name
        self._project_instructions = None

    def get_system_prompt(self, model: str) -> str:
        parts = [SYSTEM_PROMPT]
        
        opt = self._get_model_optimizations(model)
        if opt: 
            parts.append(opt)
        
        agent_p = get_agent_prompt(self.agent_name)
        if agent_p: 
            parts.append(f"\n\n## ACTIVE AGENT\n{agent_p}")
        
        if self._project_instructions is None:
            self._project_instructions = get_project_instructions(self.project_path)
        if self._project_instructions:
            parts.append(f"\n\n{self._project_instructions}")
            
        return "\n".join(parts)

    def _get_model_optimizations(self, model: str) -> str:
        m = model.lower()
        if "claude" in m:
            return "## CLAUDE OPTIMIZATION\n- Use <thinking> tags\n- Be concise"
        if "gemini" in m:
            return "## GEMINI OPTIMIZATION\n- Use thinking blocks\n- Parallel tool calls"
        if any(x in m for x in ["o1", "o3", "o4"]):
            return "## REASONING MODEL OPTIMIZATION\n- Less tool use\n- Complex logic"
        return ""

    def build_messages(self, messages: list[dict], model: str) -> list[dict]:
        openai_msgs = [{"role": "system", "content": self.get_system_prompt(model)}]
        for msg in messages:
            m = {"role": msg["role"], "content": msg.get("content", "")}
            for key in ["tool_calls", "tool_call_id", "name"]:
                if key in msg: m[key] = msg[key]
            openai_msgs.append(m)
        return openai_msgs
