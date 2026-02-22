import asyncio
import time
from typing import Any, Callable

from app.models import ToolDefinition
from app.tools.file_tools import FILE_TOOLS
from app.tools.code_tools import CODE_TOOLS
from app.tools.exec_tools import EXEC_TOOLS
from app.utils.session_stats import session_tracker
from app.utils.logger import log_error, log_debug


class ToolManager:
    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._schemas: dict[str, dict] = {}

    def register(self, name: str, schema: dict, handler: Callable) -> None:
        self._tools[name] = handler
        self._schemas[name] = schema

    def unregister(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            del self._schemas[name]
            return True
        return False

    def get_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=name,
                description=schema.get("description", ""),
                input_schema=schema.get("parameters", {}),
            )
            for name, schema in self._schemas.items()
        ]

    def get_tools_for_api(self) -> list[dict]:
        return [
            {
                "name": name,
                "description": schema.get("description", ""),
                "input_schema": schema.get("parameters", {}),
            }
            for name, schema in self._schemas.items()
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        log_debug(f"Executing tool: {name} with args: {arguments}")
        if name not in self._tools:
            log_error(f"Tool '{name}' not found")
            session_tracker.record_tool_call(success=False)
            return f"Error: Tool '{name}' not found. Available: {', '.join(self._tools.keys())}"

        start_time = time.time()
        try:
            result = self._tools[name](**arguments)
            if asyncio.iscoroutine(result):
                result = await result
            
            duration = time.time() - start_time
            session_tracker.record_tool_execution(duration)
            
            result_str = str(result)
            success = not result_str.startswith("Error:")
            if not success:
                log_error(f"Tool '{name}' returned error: {result_str}")
            
            session_tracker.record_tool_call(success=success)
            return result_str
        except TypeError as e:
            log_error(f"Invalid arguments for tool '{name}'", e)
            duration = time.time() - start_time
            session_tracker.record_tool_execution(duration)
            session_tracker.record_tool_call(success=False)
            return f"Error: Invalid arguments for '{name}': {str(e)}"
        except Exception as e:
            log_error(f"Tool execution failed: {name}", e)
            duration = time.time() - start_time
            session_tracker.record_tool_execution(duration)
            session_tracker.record_tool_call(success=False)
            return f"Error: {type(e).__name__}: {str(e)}"

    def has_tool(self, name: str) -> bool:
        return name in self._tools


def create_tool_manager() -> ToolManager:
    tm = ToolManager()

    for tool in FILE_TOOLS:
        tm.register(tool["name"], tool, tool["handler"])

    for tool in CODE_TOOLS:
        tm.register(tool["name"], tool, tool["handler"])

    for tool in EXEC_TOOLS:
        tm.register(tool["name"], tool, tool["handler"])

    return tm
