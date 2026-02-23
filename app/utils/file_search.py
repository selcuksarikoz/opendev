from pathlib import Path

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
}


def search_files_for_query(
    query: str = "",
    limit: int = 20,
    include_git_branches: bool = False,
) -> list[str]:
    items: list[str] = []
    safe_limit = max(1, min(int(limit), 200))

    try:
        root = Path(".")
        search_path = root
        search_name = query.lower()

        if "/" in query:
            p_query = Path(query)
            if query.endswith("/"):
                search_path = p_query
                search_name = ""
            else:
                search_path = p_query.parent
                search_name = p_query.name.lower()

        if search_path.exists() and search_path.is_dir():
            for item in search_path.iterdir():
                if item.name in SKIP_DIRS or item.name.startswith("."):
                    continue
                if search_name and search_name not in item.name.lower():
                    continue
                full_str = str(item)
                if full_str.startswith("./"):
                    full_str = full_str[2:]
                items.append(full_str + ("/" if item.is_dir() else ""))
                if len(items) >= safe_limit:
                    break

        if include_git_branches and len(query) > 1 and len(items) < safe_limit:
            git_heads = root / ".git" / "refs" / "heads"
            if git_heads.exists():
                for branch in git_heads.iterdir():
                    if branch.is_file() and query.lower() in branch.name.lower():
                        items.append(f"branch:{branch.name}")
                        if len(items) >= safe_limit:
                            break
    except Exception:
        return []

    return items[:safe_limit]
