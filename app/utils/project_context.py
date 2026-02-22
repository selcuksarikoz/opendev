import os
import re
from pathlib import Path
from typing import Optional


AI_RULES_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    ".claude.md",
    "CURSOR.md",
    ".cursorrules",
    "AI.md",
    ".ai",
    "README.md",
]


def find_ai_rules_files(project_path: str = ".") -> list[str]:
    found = []
    path = Path(project_path)

    for filename in AI_RULES_FILES:
        file_path = path / filename
        if file_path.exists() and file_path.is_file():
            found.append(str(file_path))

    rules_dir = path / ".cursor" / "rules"
    if rules_dir.exists() and rules_dir.is_dir():
        for f in rules_dir.glob("*.md"):
            found.append(str(f))

    return found


def find_agent_instructions(project_path: str = ".") -> str:
    found = []
    path = Path(project_path)
    
    # Common directories to ignore
    ignore_dirs = {".venv", "node_modules", ".git", "__pycache__", ".ruff_cache"}
    
    # Search for files like AGENT_*.md or agent_*.md and files in agents/ folders
    # We'll do a manual walk to respect ignore_dirs
    for root, dirs, files in os.walk(path):
        # Filter out ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        root_path = Path(root)
        
        # Check files in current root
        for file in files:
            if file.lower().endswith(".md"):
                if "agent" in file.lower():
                    found.append(root_path / file)
        
        # Check if current directory is an "agents" directory
        if root_path.name.lower() == "agents":
            for file in files:
                if file.lower().endswith(".md"):
                    file_path = root_path / file
                    if file_path not in found:
                        found.append(file_path)

    if not found:
        return ""

    parts = ["## CUSTOM AGENT DEFINITIONS (from project files)\n"]
    for file_path in found:
        try:
            content = file_path.read_text(encoding="utf-8")
            parts.append(f"### From {file_path.name}\n")
            parts.append(content)
            parts.append("\n")
        except:
            continue
    return "\n".join(parts)


def read_ai_rules(file_path: str) -> Optional[str]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return None


def build_project_context(project_path: str = ".") -> str:
    rules_files = find_ai_rules_files(project_path)
    agent_instructions = find_agent_instructions(project_path)

    if not rules_files and not agent_instructions:
        return ""

    context_parts = []
    
    if rules_files:
        context_parts.append("## PROJECT RULES (from project files)\n")
        for file_path in rules_files:
            content = read_ai_rules(file_path)
            if content:
                filename = Path(file_path).name
                context_parts.append(f"### From {filename}\n")
                context_parts.append(content)
                context_parts.append("\n")

    if agent_instructions:
        context_parts.append(agent_instructions)

    return "\n".join(context_parts)


def get_project_instructions(project_path: str = ".") -> str:
    context = build_project_context(project_path)
    if not context:
        return ""

    return f"""
{context}

NOTE: Follow the project rules above when working on this codebase.
"""
