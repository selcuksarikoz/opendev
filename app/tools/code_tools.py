import re
import ast
import asyncio
from pathlib import Path
from typing import Optional


async def search_codebase(
    regex_pattern: str, directory: str = ".", include_exts: list = None
) -> str:
    try:
        return await asyncio.to_thread(_search_codebase_sync, regex_pattern, directory, include_exts)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _search_codebase_sync(regex_pattern: str, directory: str, include_exts: list) -> str:
    try:
        path = Path(directory).expanduser()
        results = []
        pattern = re.compile(regex_pattern, re.MULTILINE)
        include_exts = include_exts or []

        for f in path.rglob("*"):
            if not f.is_file():
                continue
            if include_exts and f.suffix not in include_exts:
                continue
            if any(
                skip in f.parts
                for skip in [".git", "node_modules", "__pycache__", ".venv", "venv"]
            ):
                continue
            try:
                with open(f, "r", encoding="utf-8", errors="ignore") as file:
                    for i, line in enumerate(file, 1):
                        if pattern.search(line):
                            results.append(f"{f}:{i}: {line.rstrip()}")
                            if len(results) >= 100:
                                return "\n".join(results)
            except:
                pass
        return "\n".join(results) if results else "No matches found"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def get_code_structure(filepath: str) -> str:
    try:
        path = Path(filepath).expanduser()
        if not path.exists():
            return f"Error: File not found: {filepath}"

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        ext = path.suffix.lower()

        if ext == ".py":
            return _get_python_structure(content)
        elif ext in [".ts", ".tsx", ".js", ".jsx"]:
            return _get_js_structure(content)
        else:
            return f"Error: Unsupported file type: {ext}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _get_python_structure(content: str) -> str:
    try:
        tree = ast.parse(content)
        lines = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                bases = [ast.unparse(base) for base in node.bases]
                lines.append(
                    f"class {node.name}({', '.join(bases)})"
                    if bases
                    else f"class {node.name}"
                )
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        args = [a.arg for a in item.args.args]
                        lines.append(f"  def {item.name}({', '.join(args)})")
            elif isinstance(node, ast.FunctionDef):
                args = [a.arg for a in node.args.args]
                lines.append(f"def {node.name}({', '.join(args)})")
            elif isinstance(node, ast.AsyncFunctionDef):
                args = [a.arg for a in node.args.args]
                lines.append(f"async def {node.name}({', '.join(args)})")

        return "\n".join(lines) if lines else "No classes or functions found"
    except SyntaxError:
        return "Error: Could not parse Python file"


def _get_js_structure(content: str) -> str:
    lines = []

    function_pattern = r"(export\s+)?(async\s+)?function\s+(\w+)\s*\(([^)]*)\)"
    for match in re.finditer(function_pattern, content):
        export = "export " if match.group(1) else ""
        async_kw = "async " if match.group(2) else ""
        name = match.group(3)
        args = match.group(4)
        lines.append(f"{export}{async_kw}function {name}({args})")

    arrow_pattern = (
        r"(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?\([^)]*\)\s*=>"
    )
    for match in re.finditer(arrow_pattern, content):
        export = "export " if match.group(1) else ""
        keyword = match.group(2)
        name = match.group(3)
        async_kw = "async " if match.group(4) else ""
        lines.append(f"{export}{keyword} {name} = {async_kw}() => {{}}")

    class_pattern = r"(export\s+)?class\s+(\w+)(\s+extends\s+\w+)?"
    for match in re.finditer(class_pattern, content):
        export = "export " if match.group(1) else ""
        name = match.group(2)
        extends = match.group(3) or ""
        lines.append(f"{export}class {name}{extends}")

    return "\n".join(lines) if lines else "No classes or functions found"


async def grep_search(
    pattern: str,
    directory: str = ".",
    include: str = None,
    exclude: str = None,
    case_sensitive: bool = False,
) -> str:
    try:
        return await asyncio.to_thread(_grep_search_sync, pattern, directory, include, exclude, case_sensitive)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _grep_search_sync(pattern: str, directory: str, include: str, exclude: str, case_sensitive: bool) -> str:
    import subprocess
    cmd = ["grep", "-rn" + ("" if case_sensitive else "i")]
    if include:
        cmd.extend(["--include", include])
    if exclude:
        cmd.extend(["--exclude", exclude])
    
    # Exclude common directories
    for skip in [".git", "node_modules", "__pycache__", ".venv", "venv"]:
        cmd.extend(["--exclude-dir", skip])
        
    cmd.extend([pattern, directory])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        output = result.stdout
        if not output and result.stderr:
            return f"Error: {result.stderr}"
        
        lines = output.splitlines()
        if len(lines) > 100:
            return "\n".join(lines[:100]) + f"\n... (truncated, {len(lines)} total matches)"
        return output or "No matches found"
    except Exception as e:
        return f"Error: {str(e)}"


CODE_TOOLS = [
    {
        "name": "grep_search",
        "description": "Search for text within files using grep-like functionality.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text pattern to search for"},
                "directory": {"type": "string", "description": "Directory to search (default: current)"},
                "include": {"type": "string", "description": "File pattern to include (e.g., '*.py')"},
                "exclude": {"type": "string", "description": "File pattern to exclude"},
                "case_sensitive": {"type": "boolean", "description": "Perform case-sensitive search"},
            },
            "required": ["pattern"],
        },
        "handler": grep_search,
    },
    {
        "name": "search_codebase",
        "description": "Fast recursive regex search across the codebase. Use to find code patterns, functions, classes.",
        "parameters": {
            "type": "object",
            "properties": {
                "regex_pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "directory": {
                    "type": "string",
                    "description": "Directory to search (default: current)",
                },
                "include_exts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File extensions to include (e.g., ['.ts', '.py'])",
                },
            },
            "required": ["regex_pattern"],
        },
        "handler": search_codebase,
    },
    {
        "name": "get_code_structure",
        "description": "Get class/function signatures without implementation. Use for understanding large files efficiently.",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to the file"},
            },
            "required": ["filepath"],
        },
        "handler": get_code_structure,
    },
]
