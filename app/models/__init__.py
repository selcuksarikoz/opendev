from pydantic import BaseModel
from typing import Optional
from enum import Enum
from app.core.runtime_config import DEFAULT_AGENT_NAME


class Mode(str, Enum):
    PLAN = "Plan Mode"
    BUILD = "Build Mode"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(BaseModel):
    role: MessageRole
    content: str
    reasoning: Optional[str] = None
    tools_used: Optional[list[str]] = None
    tool_call_id: Optional[str] = None


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict


class ToolResult(BaseModel):
    tool_call_id: str
    content: str


class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict


class Provider(BaseModel):
    name: str
    api_key: str = ""
    base_url: str = ""
    models: list[dict] = []
    default_model: str = ""


class Session(BaseModel):
    session_id: str
    messages: list[Message] = []
    mode: Mode = Mode.BUILD
    provider_name: str = ""
    model: str = ""
    agent_name: str = DEFAULT_AGENT_NAME


class AppConfig(BaseModel):
    providers: list[Provider] = []
    default_provider: str = ""
