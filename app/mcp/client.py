import json
import asyncio
import subprocess
import os
from typing import Any, Optional
from pathlib import Path
from threading import Lock


class MCPProtocolError(Exception):
    pass


class MCPServer:
    def __init__(
        self,
        name: str,
        command: str,
        args: Optional[list[str]] = None,
        env: Optional[dict] = None,
    ):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.process: Optional[subprocess.Popen] = None
        self.tools: list[dict] = []
        self._request_id = 0
        self._request_lock = asyncio.Lock()
        self._id_lock = Lock()
        self.timeout_sec = 30.0

    async def start(self) -> bool:
        try:
            full_env = dict(os.environ)
            full_env.update(self.env)

            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=full_env,
                bufsize=0,
            )

            init_result = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "clientInfo": {"name": "opendev", "version": "1.0.0"},
                },
            )

            if "error" in init_result:
                return False

            await self._send_notification("notifications/initialized", {})

            tools_result = await self._send_request("tools/list", {})
            self.tools = tools_result.get("result", {}).get("tools", [])

            return True
        except Exception:
            return False

    async def stop(self) -> None:
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        return await self._send_request(
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )

    async def _send_request(self, method: str, params: dict) -> dict:
        if not self.process or not self.process.stdin or not self.process.stdout:
            return {"error": "Server not running"}

        with self._id_lock:
            self._request_id += 1
            request_id = self._request_id

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        try:
            async with self._request_lock:
                await asyncio.to_thread(self._write_message, message)
                response = await asyncio.wait_for(
                    asyncio.to_thread(self._read_message),
                    timeout=self.timeout_sec,
                )
            if response.get("id") != request_id and "method" in response:
                response = await asyncio.wait_for(
                    asyncio.to_thread(self._read_message),
                    timeout=self.timeout_sec,
                )
            return response
        except Exception as e:
            return {"error": str(e)}

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            return
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        try:
            async with self._request_lock:
                await asyncio.to_thread(self._write_message, message)
        except Exception:
            pass

    def _write_message(self, message: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise MCPProtocolError("Server stdin unavailable")
        payload = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        self.process.stdin.write(header + payload)
        self.process.stdin.flush()

    def _read_message(self) -> dict[str, Any]:
        if not self.process or not self.process.stdout:
            raise MCPProtocolError("Server stdout unavailable")
        headers: dict[str, str] = {}
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise MCPProtocolError("No response from server")
            if line in (b"\r\n", b"\n"):
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if ":" in decoded:
                key, value = decoded.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        length_str = headers.get("content-length")
        if not length_str:
            raise MCPProtocolError("Missing Content-Length")
        try:
            length = int(length_str)
        except ValueError as exc:
            raise MCPProtocolError("Invalid Content-Length") from exc
        body = self.process.stdout.read(length)
        if not body:
            raise MCPProtocolError("Empty response body")
        return json.loads(body.decode("utf-8"))

    def get_tool_schemas(self) -> list[dict]:
        schemas = []
        for tool in self.tools:
            schemas.append(
                {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("inputSchema", {}),
                }
            )
        return schemas


class MCPClient:
    def __init__(self):
        self.servers: dict[str, MCPServer] = {}

    async def connect(
        self,
        name: str,
        command: str,
        args: Optional[list[str]] = None,
        env: Optional[dict] = None,
    ) -> bool:
        if name in self.servers:
            await self.disconnect(name)

        server = MCPServer(name, command, args, env)
        success = await server.start()

        if success:
            self.servers[name] = server
            return True
        return False

    async def disconnect(self, name: str) -> bool:
        if name not in self.servers:
            return False

        await self.servers[name].stop()
        del self.servers[name]
        return True

    async def disconnect_all(self) -> None:
        for name in list(self.servers.keys()):
            await self.disconnect(name)

    def get_server(self, name: str) -> Optional[MCPServer]:
        return self.servers.get(name)

    def get_server_names(self) -> list[str]:
        return list(self.servers.keys())

    def get_all_tools(self) -> list[dict]:
        tools = []
        for server in self.servers.values():
            for tool in server.tools:
                tools.append(
                    {
                        **tool,
                        "_server": server.name,
                    }
                )
        return tools

    def get_all_tool_schemas(self) -> list[dict]:
        schemas = []
        for server in self.servers.values():
            for schema in server.get_tool_schemas():
                schemas.append({**schema, "_server": server.name})
        return schemas

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict:
        server = self.get_server(server_name)
        if not server:
            return {"error": f"Server '{server_name}' not connected"}
        return await server.call_tool(tool_name, arguments)

    async def call_tool_auto(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        for server in self.servers.values():
            for tool in server.tools:
                if tool.get("name") == tool_name:
                    return await server.call_tool(tool_name, arguments)
        return {"error": f"Tool '{tool_name}' not found in any connected server"}


async def load_mcp_from_config(config_path: Optional[str] = None) -> MCPClient:
    client = MCPClient()

    if config_path is None:
        config_path = str(get_default_mcp_config_path())

    path = Path(config_path)
    if not path.exists():
        return client

    try:
        config = load_mcp_config(path)

        servers = config.get("mcpServers", {})
        for name, server_config in servers.items():
            command = server_config.get("command", "")
            args = server_config.get("args", [])
            env = server_config.get("env", {})

            if command:
                await client.connect(name, command, args, env)
    except Exception:
        pass

    return client


def get_default_mcp_config_path() -> Path:
    return Path.home() / ".opendev" / "mcp.json"


def load_mcp_config(config_path: Optional[Path | str] = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else get_default_mcp_config_path()
    if not path.exists():
        return {"mcpServers": {}}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {"mcpServers": {}}


def save_mcp_config(config: dict[str, Any], config_path: Optional[Path | str] = None) -> None:
    path = Path(config_path) if config_path else get_default_mcp_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2))


def add_mcp_server(
    name: str,
    command: str,
    args: Optional[list[str]] = None,
    env: Optional[dict[str, str]] = None,
    config_path: Optional[Path | str] = None,
) -> None:
    config = load_mcp_config(config_path)
    servers = config.setdefault("mcpServers", {})
    servers[name] = {
        "command": command,
        "args": args or [],
        "env": env or {},
    }
    save_mcp_config(config, config_path)


def remove_mcp_server(name: str, config_path: Optional[Path | str] = None) -> bool:
    config = load_mcp_config(config_path)
    servers = config.setdefault("mcpServers", {})
    if name not in servers:
        return False
    del servers[name]
    save_mcp_config(config, config_path)
    return True
