import asyncio
import os
from pathlib import Path
from typing import Optional
from app.utils.session_stats import session_tracker


async def read_file(
    filepath: str, start_line: Optional[int] = None, end_line: Optional[int] = None
) -> str:
    try:
        return await asyncio.to_thread(_read_file_sync, filepath, start_line, end_line)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _read_file_sync(
    filepath: str, start_line: Optional[int], end_line: Optional[int]
) -> str:
    path = Path(filepath).expanduser()
    if not path.exists():
        return f"Error: File not found: {filepath}"
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    if start_line is not None:
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line or len(lines))
        return "".join(lines[start_idx:end_idx])
    return "".join(lines)


async def write_file(filepath: str, content: str) -> str:
    try:
        return await asyncio.to_thread(_write_file_sync, filepath, content)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _write_file_sync(filepath: str, content: str) -> str:
    path = Path(filepath).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Estimate changes
    lines_added = content.count("\n") + 1
    lines_removed = 0
    if path.exists():
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines_removed = f.read().count("\n") + 1

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    session_tracker.record_code_changes(lines_added, lines_removed)
    return f"Success: Written to {filepath}"


async def edit_file(filepath: str, search_block: str, replace_block: str) -> str:
    try:
        return await asyncio.to_thread(
            _edit_file_sync, filepath, search_block, replace_block
        )
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _edit_file_sync(filepath: str, search_block: str, replace_block: str) -> str:
    path = Path(filepath).expanduser()
    if not path.exists():
        return f"Error: File not found: {filepath}"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Normalizing line endings can help with matching
    if search_block not in content:
        # Try a more loose match (strip trailing whitespace from lines)
        return "Error: search_block not found in file. Please ensure exact match or use read_file to check content."

    # Estimate changes
    lines_added = replace_block.count("\n") + 1
    lines_removed = search_block.count("\n") + 1

    new_content = content.replace(search_block, replace_block, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    session_tracker.record_code_changes(lines_added, lines_removed)
    return f"Success: Edited {filepath}"


async def delete_file(filepath: str) -> str:
    try:
        return await asyncio.to_thread(_delete_file_sync, filepath)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _delete_file_sync(filepath: str) -> str:
    import shutil

    path = Path(filepath).expanduser()
    if not path.exists():
        return f"Error: File not found: {filepath}"

    # Estimate changes
    lines_removed = 0
    if path.is_file():
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines_removed = f.read().count("\n") + 1

    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()

    session_tracker.record_code_changes(0, lines_removed)
    return f"Success: Deleted {filepath}"


async def list_directory(path: str) -> str:
    try:
        return await asyncio.to_thread(_list_directory_sync, path)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _list_directory_sync(path: str) -> str:
    dir_path = Path(path).expanduser()
    if not dir_path.exists():
        return f"Error: Directory not found: {path}"
    items = []
    for item in sorted(dir_path.iterdir()):
        suffix = "/" if item.is_dir() else ""
        items.append(f"{item.name}{suffix}")
    return "\n".join(items)


async def find_files(pattern: str, directory: str = ".") -> str:
    try:
        return await asyncio.to_thread(_find_files_sync, pattern, directory)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _find_files_sync(pattern: str, directory: str) -> str:
    path = Path(directory).expanduser()
    if not path.exists():
        return f"Error: Directory not found: {directory}"

    results = []
    for f in path.rglob(pattern):
        # Skip if any part of the file's path is an exact match for a skip directory
        if any(
            part in [".git", "node_modules", "__pycache__", ".venv", "venv"]
            for part in f.parts
        ):
            continue
        results.append(str(f))
        if len(results) >= 100:
            break

    return "\n".join(results) if results else "No files found matching pattern"


async def get_file_tree(path: str = ".") -> str:
    try:
        return await asyncio.to_thread(_get_file_tree_sync, path)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _get_file_tree_sync(path: str) -> str:
    import os

    dir_path = Path(path).expanduser()
    if not dir_path.exists():
        return f"Error: Directory not found: {path}"

    tree = []
    skip_dirs = [
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".ruff_cache",
        ".vscode",
    ]

    for root, dirs, files in os.walk(dir_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        rel_root = Path(root).relative_to(dir_path)
        depth = len(rel_root.parts)
        indent = "  " * depth

        if rel_root.name:
            tree.append(f"{indent}[{rel_root.name}/]")

        file_indent = "  " * (depth + 1)
        for f in sorted(files):
            tree.append(f"{file_indent}{f}")

        if len(tree) > 500:
            tree.append(f"{file_indent}... (truncated)")
            break

    return "\n".join(tree) if tree else "No files found"


async def create_directory(path: str) -> str:
    try:
        return await asyncio.to_thread(_create_directory_sync, path)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _create_directory_sync(path: str) -> str:
    dir_path = Path(path).expanduser()
    if dir_path.exists():
        return f"Error: Directory already exists: {path}"
    dir_path.mkdir(parents=True, exist_ok=True)
    return f"Success: Created directory {path}"


async def move_file(source: str, destination: str) -> str:
    try:
        return await asyncio.to_thread(_move_file_sync, source, destination)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _move_file_sync(source: str, destination: str) -> str:
    import shutil

    src = Path(source).expanduser()
    dst = Path(destination).expanduser()

    if not src.exists():
        return f"Error: Source not found: {source}"

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return f"Success: Moved {source} -> {destination}"


async def copy_file(source: str, destination: str) -> str:
    try:
        return await asyncio.to_thread(_copy_file_sync, source, destination)
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _copy_file_sync(source: str, destination: str) -> str:
    import shutil

    src = Path(source).expanduser()
    dst = Path(destination).expanduser()

    if not src.exists():
        return f"Error: Source not found: {source}"

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    return f"Success: Copied {source} -> {destination}"


async def read_files_batch(
    filepaths: list[str],
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    max_chars_per_file: int = 20000,
) -> str:
    try:
        return await asyncio.to_thread(
            _read_files_batch_sync,
            filepaths,
            start_line,
            end_line,
            max_chars_per_file,
        )
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _read_files_batch_sync(
    filepaths: list[str],
    start_line: Optional[int],
    end_line: Optional[int],
    max_chars_per_file: int,
) -> str:
    if not filepaths:
        return "Error: filepaths is required"

    max_chars = max(500, min(int(max_chars_per_file), 100000))
    chunks: list[str] = []
    for filepath in filepaths[:50]:
        content = _read_file_sync(filepath, start_line, end_line)
        if content.startswith("Error:"):
            chunks.append(f"## {filepath}\n{content}")
            continue
        if len(content) > max_chars:
            content = content[:max_chars] + "\n... (truncated)"
        chunks.append(f"## {filepath}\n{content}")
    return "\n\n".join(chunks)


async def replace_regex(
    filepath: str,
    pattern: str,
    replacement: str,
    max_replacements: int = 0,
) -> str:
    try:
        return await asyncio.to_thread(
            _replace_regex_sync, filepath, pattern, replacement, max_replacements
        )
    except Exception as e:
        return f"Error: {type(e).__name__}: {str(e)}"


def _replace_regex_sync(
    filepath: str,
    pattern: str,
    replacement: str,
    max_replacements: int,
) -> str:
    import re

    path = Path(filepath).expanduser()
    if not path.exists():
        return f"Error: File not found: {filepath}"

    content = path.read_text(encoding="utf-8", errors="ignore")
    try:
        regex = re.compile(pattern, re.MULTILINE)
    except re.error as e:
        return f"Error: Invalid regex pattern: {str(e)}"

    replacement_limit = max(0, int(max_replacements))
    new_content, count = regex.subn(
        replacement,
        content,
        count=replacement_limit if replacement_limit > 0 else 0,
    )
    if count == 0:
        return "Error: No regex matches found"

    path.write_text(new_content, encoding="utf-8")
    return f"Success: Replaced {count} occurrence(s) in {filepath}"


FILE_TOOLS = [
    {
        "name": "get_file_tree",
        "description": "Show the project's directory structure in a tree-like format.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Starting directory (default: current)",
                },
            },
        },
        "handler": get_file_tree,
    },
    {
        "name": "read_file",
        "description": "Read file content, optionally by line range. Use for understanding existing code before editing.",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to the file"},
                "start_line": {
                    "type": "integer",
                    "description": "Start line number (1-indexed)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line number (1-indexed)",
                },
            },
            "required": ["filepath"],
        },
        "handler": read_file,
    },
    {
        "name": "write_file",
        "description": "Create new file or overwrite existing. Use ONLY for new files, prefer edit_file for modifications.",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to the file"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["filepath", "content"],
        },
        "handler": write_file,
    },
    {
        "name": "edit_file",
        "description": "Replace exact text block in existing file. MUST read file first. search_block must match exactly.",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to the file"},
                "search_block": {
                    "type": "string",
                    "description": "Exact text to find and replace",
                },
                "replace_block": {
                    "type": "string",
                    "description": "New text to insert",
                },
            },
            "required": ["filepath", "search_block", "replace_block"],
        },
        "handler": edit_file,
    },
    {
        "name": "delete_file",
        "description": "Delete a file or directory. Use with caution.",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to delete"},
            },
            "required": ["filepath"],
        },
        "handler": delete_file,
    },
    {
        "name": "list_directory",
        "description": "List files and folders in a directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"},
            },
            "required": ["path"],
        },
        "handler": list_directory,
    },
    {
        "name": "find_files",
        "description": "Find files by name pattern (e.g., '*.py', 'config.json').",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern to match"},
                "directory": {
                    "type": "string",
                    "description": "Starting directory (default: current)",
                },
            },
            "required": ["pattern"],
        },
        "handler": find_files,
    },
    {
        "name": "create_directory",
        "description": "Create a new directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to create"},
            },
            "required": ["path"],
        },
        "handler": create_directory,
    },
    {
        "name": "move_file",
        "description": "Move or rename a file or directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source path"},
                "destination": {"type": "string", "description": "Destination path"},
            },
            "required": ["source", "destination"],
        },
        "handler": move_file,
    },
    {
        "name": "copy_file",
        "description": "Copy a file or directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source path"},
                "destination": {"type": "string", "description": "Destination path"},
            },
            "required": ["source", "destination"],
        },
        "handler": copy_file,
    },
    {
        "name": "read_files_batch",
        "description": "Read multiple files in one tool call. Useful for comparing related files quickly.",
        "parameters": {
            "type": "object",
            "properties": {
                "filepaths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths to read",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Start line number (1-indexed)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "End line number (1-indexed)",
                },
                "max_chars_per_file": {
                    "type": "integer",
                    "description": "Maximum output characters per file",
                    "minimum": 500,
                    "maximum": 100000,
                },
            },
            "required": ["filepaths"],
        },
        "handler": read_files_batch,
    },
    {
        "name": "replace_regex",
        "description": "Replace text by regex pattern in a file. Use after read_file/search confirmation.",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to the file"},
                "pattern": {"type": "string", "description": "Regex pattern"},
                "replacement": {"type": "string", "description": "Replacement text"},
                "max_replacements": {
                    "type": "integer",
                    "description": "Max replacement count, 0 means replace all",
                    "minimum": 0,
                },
            },
            "required": ["filepath", "pattern", "replacement"],
        },
        "handler": replace_regex,
    },
]
