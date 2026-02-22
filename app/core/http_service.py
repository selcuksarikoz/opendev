import json
import time
from typing import AsyncGenerator, Optional, Any
from openai import AsyncOpenAI

from app.utils import (
    get_provider,
    get_default_provider,
)
from app.utils.session_stats import session_tracker
from app.storage.storage import Storage
from .prompt_builder import PromptBuilder


class RateLimitError(Exception):
    pass


class HttpService:
    def __init__(
        self,
        provider_name: Optional[str] = None,
        project_path: str = ".",
        agent_name: str = "coder",
    ):
        provider = (
            get_provider(
                provider_name) if provider_name else get_default_provider()
        )
        if not provider:
            raise ValueError("No provider configured.")

        self.storage = Storage()
        self.provider_name = provider["name"]
        self.model = provider.get("default_model", "gpt-4o")
        self.base_url = provider.get("base_url", "https://api.openai.com/v1")
        self.prompt_builder = PromptBuilder(project_path, agent_name)
        self._api_key = ""
        self.client = None

        config_key = provider.get("api_key", "")
        self.api_key = config_key.strip()

    async def initialize(self):
        db_key = await self.storage.get_api_key(self.provider_name)
        if db_key:
            self.api_key = db_key.strip()

    async def close(self):
        if self.client:
            await self.client.close()
            self.client = None

    @property
    def api_key(self) -> str:
        return self._api_key

    @api_key.setter
    def api_key(self, value: str):
        new_key = (value or "").strip()
        if self._api_key == new_key and self.client:
            return

        self._api_key = new_key
        self.client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self.base_url,
            timeout=120.0,
            default_headers={
                "HTTP-Referer": "https://github.com/selcuksarikoz/opendev",
                "X-Title": "OpenDev CLI",
            },
        )

    def set_agent(self, agent_name: str) -> None:
        self.prompt_builder.agent_name = agent_name

    def _build_tools(self, tools: list[dict]) -> Optional[list[dict]]:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", t.get("parameters", {})),
                },
            }
            for t in tools
        ]

    @staticmethod
    def _is_tool_calling_unsupported(error: Exception) -> bool:
        text = str(error).lower()
        return (
            "tool calling" in text and "not supported" in text
        ) or "param': 'tool calling'" in text

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        stream: bool = True,
        **kwargs,
    ) -> AsyncGenerator[tuple[str, Any], None]:
        if not self.api_key:
            raise ValueError(f"No API key for {self.provider_name}.")

        full_messages = self.prompt_builder.build_messages(
            messages, self.model)
        openai_tools = self._build_tools(tools)
        start_time = time.time()
        input_tokens, output_tokens = 0, 0

        try:
            extra_body = {}
            if "openrouter.ai" in self.base_url:
                extra_body["reasoning"] = {"enabled": True}

            input_tokens, output_tokens = 0, 0

            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=full_messages,
                    tools=openai_tools,
                    stream=stream,
                    extra_body=extra_body if extra_body else None,
                    **kwargs,
                )
            except Exception as first_error:
                if openai_tools and self._is_tool_calling_unsupported(first_error):
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=full_messages,
                        tools=None,
                        stream=stream,
                        extra_body=extra_body if extra_body else None,
                        **kwargs,
                    )
                else:
                    raise

            if not stream:
                choice = response.choices[0]
                usage = getattr(response, "usage", None)
                if usage:
                    input_tokens = getattr(usage, "prompt_tokens", 0)
                    output_tokens = getattr(usage, "completion_tokens", 0)

                reasoning = getattr(choice.message, "reasoning", None) or getattr(
                    choice.message, "reasoning_details", None
                )
                if reasoning:
                    yield "reasoning", reasoning
                if choice.message.content:
                    yield "content", choice.message.content
                if choice.message.tool_calls:
                    for tc in choice.message.tool_calls:
                        yield (
                            "tool_call",
                            {
                                "id": tc.id,
                                "name": tc.function.name,
                                "arguments": json.loads(tc.function.arguments),
                            },
                        )
            else:
                tool_calls_acc = {}
                async for chunk in response:
                    if not chunk.choices:
                        usage = getattr(chunk, "usage", None)
                        if usage:
                            input_tokens = getattr(usage, "prompt_tokens", 0)
                            output_tokens = getattr(
                                usage, "completion_tokens", 0)
                        continue

                    choice = chunk.choices[0]
                    delta = choice.delta

                    reasoning = getattr(delta, "reasoning", None) or getattr(
                        delta, "reasoning_details", None
                    )
                    if reasoning:
                        yield "reasoning", reasoning
                    if delta.content:
                        yield "content", delta.content
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = getattr(tc, "index", 0)
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {
                                    "id": tc.id,
                                    "name": "",
                                    "arguments": "",
                                }
                            if tc.id:
                                tool_calls_acc[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_acc[idx]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_calls_acc[idx]["arguments"] += (
                                        tc.function.arguments
                                    )

                for tc in tool_calls_acc.values():
                    try:
                        args = json.loads(
                            tc["arguments"]) if tc["arguments"] else {}
                        yield (
                            "tool_call",
                            {"id": tc["id"], "name": tc["name"],
                                "arguments": args},
                        )
                    except:
                        yield (
                            "tool_call",
                            {"id": tc["id"], "name": tc["name"],
                                "arguments": {}},
                        )

        except Exception as e:
            if "429" in str(e):
                raise RateLimitError("Rate limit exceeded.")
            raise e
        finally:
            duration = time.time() - start_time
            session_tracker.record_api_call(
                self.model,
                input_tokens or (len(str(full_messages)) // 4),
                output_tokens,
                duration,
            )

    async def summarize_conversation(self, messages: list[dict]) -> str:
        """Generate a concise summary of the conversation to serve as context."""
        if not messages:
            return ""

        summary_prompt = [
            {
                "role": "system",
                "content": "You are a context manager. Summarize the following technical conversation concisely. Focus on: 1) The current goal/task. 2) Key decisions made. 3) Current state of the project/files. 4) Any specific constraints. Keep it under 500 words. Do not use conversational filler.",
            },
            {
                "role": "user",
                "content": f"Please summarize this conversation history:\n\n{json.dumps(messages[-20:])}",
            },
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=summary_prompt,
                stream=False,
                max_tokens=1000,
            )
            return (
                response.choices[0].message.content
                or "Conversation summary not available."
            )
        except Exception as e:
            return f"Error generating summary: {str(e)}"
