import asyncio
import time
import re
from typing import Any, Callable

from app.models import ToolDefinition
from app.tools.file_tools import FILE_TOOLS
from app.tools.code_tools import CODE_TOOLS
from app.tools.exec_tools import EXEC_TOOLS
from app.tools.agent_tools import AGENT_TOOLS
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

    @staticmethod
    def _schema_type_matches(value: Any, expected: str) -> bool:
        if expected == "string":
            return isinstance(value, str)
        if expected == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected == "number":
            return (isinstance(value, int) and not isinstance(value, bool)) or isinstance(
                value, float
            )
        if expected == "boolean":
            return isinstance(value, bool)
        if expected == "array":
            return isinstance(value, list)
        if expected == "object":
            return isinstance(value, dict)
        return True

    def _validate_arguments(
        self, name: str, schema: dict, arguments: Any
    ) -> tuple[dict[str, Any] | None, str | None]:
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return None, (
                f"Error: Invalid arguments for '{name}': expected object, got "
                f"{type(arguments).__name__}"
            )

        params = schema.get("parameters", {})
        properties = params.get("properties", {}) if isinstance(params, dict) else {}
        required = params.get("required", []) if isinstance(params, dict) else []

        missing = [key for key in required if key not in arguments]
        if missing:
            return None, (
                f"Error: Invalid arguments for '{name}': missing required "
                f"{', '.join(missing)}"
            )

        unknown = [key for key in arguments if properties and key not in properties]
        if unknown:
            return None, (
                f"Error: Invalid arguments for '{name}': unknown argument(s) "
                f"{', '.join(unknown)}"
            )

        for key, value in arguments.items():
            if key not in properties:
                continue
            prop_schema = properties[key]
            expected_type = prop_schema.get("type")
            if expected_type and not self._schema_type_matches(value, expected_type):
                return None, (
                    f"Error: Invalid arguments for '{name}': '{key}' must be "
                    f"{expected_type}, got {type(value).__name__}"
                )
            if "enum" in prop_schema and value not in prop_schema.get("enum", []):
                return None, (
                    f"Error: Invalid arguments for '{name}': '{key}' must be one of "
                    f"{', '.join(map(str, prop_schema.get('enum', [])))}"
                )
            if isinstance(value, (int, float)):
                minimum = prop_schema.get("minimum")
                maximum = prop_schema.get("maximum")
                if minimum is not None and value < minimum:
                    return None, (
                        f"Error: Invalid arguments for '{name}': '{key}' must be >= {minimum}"
                    )
                if maximum is not None and value > maximum:
                    return None, (
                        f"Error: Invalid arguments for '{name}': '{key}' must be <= {maximum}"
                    )
            if isinstance(value, str):
                min_len = prop_schema.get("minLength")
                max_len = prop_schema.get("maxLength")
                if min_len is not None and len(value) < min_len:
                    return None, (
                        f"Error: Invalid arguments for '{name}': '{key}' length must be >= {min_len}"
                    )
                if max_len is not None and len(value) > max_len:
                    return None, (
                        f"Error: Invalid arguments for '{name}': '{key}' length must be <= {max_len}"
                    )
                pattern = prop_schema.get("pattern")
                if pattern:
                    try:
                        if re.search(pattern, value) is None:
                            return None, (
                                f"Error: Invalid arguments for '{name}': '{key}' does not match required pattern"
                            )
                    except re.error:
                        pass
            if isinstance(value, list):
                item_schema = prop_schema.get("items", {})
                item_type = item_schema.get("type")
                if item_type:
                    for item in value:
                        if not self._schema_type_matches(item, item_type):
                            return None, (
                                f"Error: Invalid arguments for '{name}': all '{key}' items must be {item_type}"
                            )

        return arguments, None

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        log_debug(f"Executing tool: {name} with args: {arguments}")
        if name not in self._tools:
            log_error(f"Tool '{name}' not found")
            session_tracker.record_tool_call(success=False)
            return f"Error: Tool '{name}' not found. Available: {', '.join(self._tools.keys())}"

        schema = self._schemas.get(name, {})
        validated_args, validation_error = self._validate_arguments(
            name, schema, arguments
        )
        if validation_error:
            log_error(validation_error)
            session_tracker.record_tool_call(success=False)
            return validation_error

        start_time = time.time()
        try:
            result = self._tools[name](**validated_args)
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

    for tool in AGENT_TOOLS:
        tm.register(tool["name"], tool, tool["handler"])

    return tm
