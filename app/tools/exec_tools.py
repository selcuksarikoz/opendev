import asyncio
import os
import subprocess
from pathlib import Path
from typing import Optional


def _find_test_root(file_path: Path) -> str:
    current = file_path.parent
    for _ in range(10):
        for f in [
            "package.json",
            "pyproject.toml",
            "setup.py",
            "requirements.txt",
            "pytest.ini",
        ]:
            if (current / f).exists():
                return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return str(file_path.parent)


def _detect_framework(project_root: str, file_path: Path) -> tuple:
    root = Path(project_root)

    if (root / "package.json").exists():
        try:
            import json

            pkg = json.loads((root / "package.json").read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "vitest" in deps:
                return str(root / "tests" / f"{file_path.stem}.test.ts"), "vitest"
            if "jest" in deps:
                return str(root / "tests" / f"{file_path.stem}.test.js"), "jest"
        except:
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

        with open(test_path, "a", encoding="utf-8") as f:
            f.write("\n" + test_content)

        if run_coverage and framework:
            if framework == "pytest":
                result = subprocess.run(
                    f"cd {project_root} && pytest --cov=. --cov-report=term-missing -q",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            elif framework in ["jest", "vitest"]:
                result = subprocess.run(
                    f"cd {project_root} && {framework} --coverage",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            else:
                return f"Test written to: {test_path}"

            output = result.stdout + result.stderr
            if len(output) > 3000:
                output = output[:1500] + "\n\n--- COVERAGE ---\n\n" + output[-1500:]
            return f"Test: {test_path}\n\n{output}"

        return f"Test written to: {test_path}"
    except subprocess.TimeoutExpired:
        return "Error: Test timed out"
    except Exception as e:
        return f"Error: {str(e)}"


async def execute_command(
    command: str, background: bool = False, timeout: int = 60
) -> str:
    try:
        if background:
            # For background tasks, we start the process but don't wait for it
            # We use asyncio.create_subprocess_shell but don't await communicate() immediately
            # In a real background task manager, we'd track this task.
            # For now, we'll let it run detached.
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=os.getcwd(),
                start_new_session=True,
            )
            return f"Command started in background with PID {process.pid}"

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd(),
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
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

        return "\n".join(output) if output else "Command completed with no output"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


async def git_action(action: str) -> str:
    try:
        command = f"git {action}"
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd(),
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            return "Error: Git command timed out"

        if process.returncode != 0 and stderr:
            return f"Error: {stderr.decode().strip()}"

        return stdout.decode().strip() or f"git {action} completed"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


async def run_tests(command: str) -> str:
    try:
        return await asyncio.to_thread(_run_tests_sync, command)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _run_tests_sync(command: str) -> str:
    import subprocess

    try:
        # Run with a reasonable timeout for tests
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.getcwd(),
        )

        output = []
        if result.stdout:
            output.append(result.stdout)
        if result.stderr:
            output.append(result.stderr)

        full_output = "\n".join(output)

        # Heuristic: If output is massive, try to return the failures part (tail)
        # or just truncate.
        if len(full_output) > 5000:
            return (
                full_output[:1000]
                + f"\n\n... ({len(full_output) - 2000} chars truncated) ...\n\n"
                + full_output[-1000:]
            )

        return full_output or "Tests ran with no output."

    except subprocess.TimeoutExpired:
        return "Error: Tests timed out after 120 seconds."
    except Exception as e:
        return f"Error running tests: {str(e)}"


async def read_webpage(url: str) -> str:
    try:
        import httpx
        import re

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text

            # Basic HTML stripping
            # 1. Remove scripts and styles
            html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL)
            # 2. Remove comments
            html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
            # 3. Remove tags
            text = re.sub(r"<[^>]+>", " ", html)
            # 4. Collapse whitespace
            text = re.sub(r"\s+", " ", text).strip()

            # Truncate if too long
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
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "background": {
                    "type": "boolean",
                    "description": "Run in background (non-blocking)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 60)",
                },
            },
            "required": ["command"],
        },
        "handler": execute_command,
    },
    {
        "name": "run_tests",
        "description": "Run tests and capture output intelligently. Use for verification.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Test command (e.g., 'pytest', 'npm test')",
                },
            },
            "required": ["command"],
        },
        "handler": run_tests,
    },
    {
        "name": "git_action",
        "description": "Execute git commands: status, diff, log, branch, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Git action (e.g., 'status', 'diff', 'log --oneline -10')",
                },
            },
            "required": ["action"],
        },
        "handler": git_action,
    },
    {
        "name": "read_webpage",
        "description": "Fetch and extract text from a URL. Useful for documentation.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
            },
            "required": ["url"],
        },
        "handler": read_webpage,
    },
    {
        "name": "write_test",
        "description": "Generate and run tests. Auto-detects pytest/jest/vitest/unittest.",
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
