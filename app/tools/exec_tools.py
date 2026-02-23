import asyncio
import json
import os
from pathlib import Path
from typing import Optional


def _find_test_root(file_path: Path) -> str:
    current = file_path.parent
    for _ in range(10):
        for marker in [
            "package.json",
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            "pytest.ini",
        ]:
            if (current / marker).exists():
                return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return str(file_path.parent)


def _detect_framework(project_root: str, file_path: Path) -> tuple[Optional[str], Optional[str]]:
    root = Path(project_root)
    if (root / "package.json").exists():
        try:
            pkg = json.loads((root / "package.json").read_text(encoding="utf-8"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "vitest" in deps:
                return str(root / "tests" / f"{file_path.stem}.test.ts"), "vitest"
            if "jest" in deps:
                return str(root / "tests" / f"{file_path.stem}.test.js"), "jest"
        except Exception:
            pass

    if (
        (root / "pyproject.toml").exists()
        or (root / "pytest.ini").exists()
        or (root / "tests").exists()
    ):
        test_file = root / "tests" / f"test_{file_path.stem}.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        return str(test_file), "pytest"

    return None, None


def _resolve_cwd(working_dir: Optional[str] = None) -> str:
    if not working_dir:
        return os.getcwd()
    return str(Path(working_dir).expanduser())


def _truncate_output(output: str, max_len: int = 5000) -> str:
    if len(output) <= max_len:
        return output
    return (
        output[:1000]
        + f"\n\n... ({len(output) - 2000} chars truncated) ...\n\n"
        + output[-1000:]
    )


async def _run_shell_command(
    command: str,
    timeout: int = 60,
    working_dir: Optional[str] = None,
) -> str:
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=_resolve_cwd(working_dir),
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        return f"Error: Command timed out after {timeout} seconds"

    output = []
    if stdout:
        output.append(stdout.decode().strip())
    if stderr:
        output.append(f"stderr: {stderr.decode().strip()}")
    if process.returncode != 0:
        output.append(f"Exit code: {process.returncode}")
    result = "\n".join(output) if output else "Command completed with no output"
    return _truncate_output(result)


async def _run_exec_command(
    argv: list[str],
    timeout: int = 120,
    working_dir: Optional[str] = None,
) -> str:
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=_resolve_cwd(working_dir),
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        return f"Error: Command timed out after {timeout} seconds"

    output = []
    if stdout:
        output.append(stdout.decode().strip())
    if stderr:
        output.append(f"stderr: {stderr.decode().strip()}")
    if process.returncode != 0:
        output.append(f"Exit code: {process.returncode}")
    result = "\n".join(output) if output else "Command completed with no output"
    return _truncate_output(result)


async def write_test(
    filepath: str, test_content: str, run_coverage: bool = True
) -> str:
    try:
        file_path = Path(filepath).expanduser()
        if not file_path.exists():
            return f"Error: File not found: {filepath}"

        project_root = _find_test_root(file_path)
        test_path, framework = _detect_framework(project_root, file_path)
        if not test_path:
            return "Error: No test framework found. Use pytest, jest, or vitest"

        test_file = Path(test_path)
        test_file.parent.mkdir(parents=True, exist_ok=True)
        existing = test_file.read_text(encoding="utf-8") if test_file.exists() else ""
        test_file.write_text(existing + "\n" + test_content, encoding="utf-8")

        if not run_coverage or not framework:
            return f"Test written to: {test_path}"

        if framework == "pytest":
            result = await _run_exec_command(
                ["pytest", "--cov=.", "--cov-report=term-missing", "-q"],
                timeout=120,
                working_dir=project_root,
            )
        elif framework in {"jest", "vitest"}:
            result = await _run_exec_command(
                ["npx", framework, "--coverage"],
                timeout=120,
                working_dir=project_root,
            )
        else:
            return f"Test written to: {test_path}"

        return f"Test: {test_path}\n\n{_truncate_output(result, max_len=3000)}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


async def execute_command(
    command: str,
    background: bool = False,
    timeout: int = 60,
    working_dir: Optional[str] = None,
) -> str:
    try:
        cwd = _resolve_cwd(working_dir)
        if background:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=cwd,
                start_new_session=True,
            )
            return f"Command started in background with PID {process.pid}"

        return await _run_shell_command(command, timeout=timeout, working_dir=cwd)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


async def git_action(action: str) -> str:
    try:
        # Keep shell semantics for flexible git subcommands.
        return await _run_shell_command(f"git {action}", timeout=30)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


async def run_tests(command: str, working_dir: Optional[str] = None) -> str:
    try:
        return await _run_shell_command(command, timeout=120, working_dir=working_dir)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _mask_env_value(key: str, value: str) -> str:
    sensitive = ["KEY", "TOKEN", "SECRET", "PASSWORD", "PASS", "PRIVATE", "AUTH"]
    if any(flag in key.upper() for flag in sensitive):
        if len(value) <= 4:
            return "***"
        return value[:4] + "***"
    return value


async def get_working_dir() -> str:
    return os.getcwd()


async def get_env_variables(pattern: Optional[str] = None) -> str:
    try:
        q = (pattern or "").lower()
        lines = []
        for key in sorted(os.environ.keys()):
            if q and q not in key.lower():
                continue
            value = os.environ.get(key, "")
            lines.append(f"{key}={_mask_env_value(key, value)}")
        if not lines:
            return "No environment variables matched"
        return _truncate_output("\n".join(lines), max_len=8000)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


async def install_package(package: str, package_manager: str = "auto") -> str:
    try:
        if not package.strip():
            return "Error: package is required"

        root = Path(os.getcwd())
        pm = package_manager.lower().strip()
        if pm == "auto":
            if (root / "package.json").exists():
                pm = "npm"
            elif (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
                pm = "pip"
            else:
                pm = "pip"

        if pm == "npm":
            return await _run_exec_command(["npm", "install", package], timeout=180)
        if pm == "pnpm":
            return await _run_exec_command(["pnpm", "add", package], timeout=180)
        if pm == "yarn":
            return await _run_exec_command(["yarn", "add", package], timeout=180)
        if pm == "pip":
            return await _run_exec_command(
                [os.environ.get("PYTHON", "python"), "-m", "pip", "install", package],
                timeout=180,
            )

        return f"Error: Unsupported package manager '{package_manager}'"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


async def format_code(path: str = ".", formatter: str = "auto") -> str:
    try:
        target = Path(path).expanduser()
        if not target.exists():
            return f"Error: Path not found: {path}"

        fmt = formatter.lower().strip()
        if fmt == "auto":
            if target.is_file():
                ext = target.suffix.lower()
                if ext == ".py":
                    fmt = "ruff"
                elif ext in {".js", ".jsx", ".ts", ".tsx", ".json", ".css", ".md"}:
                    fmt = "prettier"
                elif ext == ".go":
                    fmt = "gofmt"
                elif ext == ".rs":
                    fmt = "rustfmt"
                else:
                    return f"Error: Could not auto-detect formatter for {path}"
            else:
                if (target / "pyproject.toml").exists():
                    fmt = "ruff"
                elif (target / "package.json").exists():
                    fmt = "prettier"
                else:
                    return f"Error: Could not auto-detect formatter for {path}"

        if fmt == "ruff":
            return await _run_exec_command(["ruff", "format", str(target)], timeout=120)
        if fmt == "black":
            return await _run_exec_command(["black", str(target)], timeout=120)
        if fmt == "prettier":
            return await _run_exec_command(["npx", "prettier", "-w", str(target)], timeout=180)
        if fmt == "gofmt":
            return await _run_exec_command(["gofmt", "-w", str(target)], timeout=120)
        if fmt == "rustfmt":
            return await _run_exec_command(["rustfmt", str(target)], timeout=120)

        return f"Error: Unsupported formatter '{formatter}'"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


async def read_webpage(url: str) -> str:
    try:
        import httpx
        import re

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
            html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL)
            html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 8000:
                text = text[:8000] + f"... (truncated, {len(text)} total chars)"
            return text
    except Exception as e:
        return f"Error fetching {url}: {str(e)}"


EXEC_TOOLS = [
    {
        "name": "execute_command",
        "description": "Run shell/bash commands. Use for builds, package managers, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "background": {"type": "boolean", "description": "Run in background"},
                "timeout": {"type": "integer", "description": "Timeout in seconds"},
                "working_dir": {"type": "string", "description": "Working directory"},
            },
            "required": ["command"],
        },
        "handler": execute_command,
    },
    {
        "name": "run_tests",
        "description": "Run tests and capture output. Use for verification.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Test command (e.g., pytest)"},
                "working_dir": {"type": "string", "description": "Working directory"},
            },
            "required": ["command"],
        },
        "handler": run_tests,
    },
    {
        "name": "format_code",
        "description": "Format file or directory with common formatters.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or directory path"},
                "formatter": {
                    "type": "string",
                    "enum": ["auto", "ruff", "black", "prettier", "gofmt", "rustfmt"],
                    "description": "Formatter name",
                },
            },
        },
        "handler": format_code,
    },
    {
        "name": "install_package",
        "description": "Install dependencies with pip/npm/pnpm/yarn.",
        "parameters": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Package name"},
                "package_manager": {
                    "type": "string",
                    "enum": ["auto", "pip", "npm", "pnpm", "yarn"],
                    "description": "Package manager",
                },
            },
            "required": ["package"],
        },
        "handler": install_package,
    },
    {
        "name": "get_working_dir",
        "description": "Return current working directory.",
        "parameters": {"type": "object", "properties": {}},
        "handler": get_working_dir,
    },
    {
        "name": "get_env_variables",
        "description": "List environment variables (sensitive values are masked).",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Filter by key substring"}
            },
        },
        "handler": get_env_variables,
    },
    {
        "name": "git_action",
        "description": "Execute git commands: status, diff, log, branch, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Git action arguments"},
            },
            "required": ["action"],
        },
        "handler": git_action,
    },
    {
        "name": "read_webpage",
        "description": "Fetch and extract text from a URL.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to fetch"}},
            "required": ["url"],
        },
        "handler": read_webpage,
    },
    {
        "name": "write_test",
        "description": "Generate and run tests. Auto-detects pytest/jest/vitest.",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "File to test"},
                "test_content": {"type": "string", "description": "Test code"},
                "run_coverage": {"type": "boolean", "description": "Run with coverage"},
            },
            "required": ["filepath", "test_content"],
        },
        "handler": write_test,
    },
]
