COMMANDS: tuple[str, ...] = (
    "/new",
    "/conversations",
    "/model",
    "/agents",
    "/settings",
    "/compact",
    "/clean history",
    "/update",
    "/help",
)

COMMANDS_HELP_TEXT = "Commands: " + ", ".join(COMMANDS)

BUILD_MODE = "Build"
PLAN_MODE = "Plan"
APP_MODES: tuple[str, ...] = (BUILD_MODE, PLAN_MODE)
DEFAULT_MODE = PLAN_MODE
DEFAULT_AGENT_NAME = "coder"

CONTEXT_LIMIT_TOKENS = 128_000

PLAN_PROMPT_TEMPLATE = (
    "Decide whether a plan is needed for this request.\n"
    "If the request is simple/single-step/small-talk, return exactly [NO_PLAN].\n"
    "If the request is complex/multi-step/high-risk, return only a concise markdown checklist with 3-7 steps.\n"
    "Do not add any extra text.\n\n"
    "Request:\n{user_input}"
)
PLAN_MESSAGE_PREFIX = "[PLAN]\n"
PLAN_SKIP_TOKEN = "[NO_PLAN]"

AI_DEFAULT_MAX_TOKENS = 4096
AI_DEFAULT_TEMPERATURE = 0.5
AI_DEFAULT_TOP_P = 1.0

TOOL_MAX_ROUNDS = 24
TOOL_MAX_PER_ROUND = 6
TOOL_MAX_TOTAL = 24
TOOL_MAX_PARALLEL = 3
TOOL_MAX_HANDOFFS = 3
