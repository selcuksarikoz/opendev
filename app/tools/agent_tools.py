import json

from app.prompts import get_agent_names

HANDOFF_PREFIX = "__HANDOFF__:"


async def handoff_agent(to_agent: str, task: str, context: str = "") -> str:
    agent_names = set(get_agent_names())
    if to_agent not in agent_names:
        return (
            "Error: Invalid handoff target. "
            f"Available agents: {', '.join(sorted(agent_names))}"
        )
    if not task.strip():
        return "Error: task is required for handoff_agent"

    payload = {
        "to_agent": to_agent,
        "task": task.strip(),
        "context": (context or "").strip(),
    }
    return HANDOFF_PREFIX + json.dumps(payload, ensure_ascii=True)


AGENT_TOOLS = [
    {
        "name": "handoff_agent",
        "description": (
            "Delegate the current work to another specialized agent. "
            "Use when another agent is better suited for the next step."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "to_agent": {
                    "type": "string",
                    "enum": get_agent_names(),
                    "description": "Target agent name",
                },
                "task": {
                    "type": "string",
                    "minLength": 3,
                    "description": "Clear task assignment for the next agent",
                },
                "context": {
                    "type": "string",
                    "description": "Optional handoff context or constraints",
                },
            },
            "required": ["to_agent", "task"],
        },
        "handler": handoff_agent,
    }
]
