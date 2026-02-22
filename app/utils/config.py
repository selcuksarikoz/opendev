import json
import hashlib
from pathlib import Path
from typing import Optional


def get_config_dir() -> Path:
    return Path.home() / ".opendev"


def get_config_path() -> Path:
    return get_config_dir() / "providers.json"


def get_bundled_providers_path() -> Path:
    return Path(__file__).parent.parent.parent / "providers.json"


def get_hash_file_path() -> Path:
    return get_config_dir() / "providers.json.hash"


def _get_file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def _save_hash(hash_value: str) -> None:
    get_config_dir().mkdir(exist_ok=True)
    with open(get_hash_file_path(), "w") as f:
        f.write(hash_value)


def _load_saved_hash() -> str:
    hash_path = get_hash_file_path()
    if hash_path.exists():
        return hash_path.read_text().strip()
    return ""


def init_config() -> None:
    config_dir = get_config_dir()
    config_dir.mkdir(exist_ok=True)

    config_path = get_config_path()
    bundled_path = get_bundled_providers_path()

    bundled_hash = _get_file_hash(bundled_path)
    saved_hash = _load_saved_hash()

    if not config_path.exists() or bundled_hash != saved_hash:
        if bundled_path.exists():
            import shutil

            shutil.copy(bundled_path, config_path)
            _save_hash(bundled_hash)


def load_providers() -> dict:
    init_config()
    config_path = get_config_path()
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except:
        return {"providers": [], "default_provider": ""}


def save_providers(data: dict) -> None:
    config_path = get_config_path()
    get_config_dir().mkdir(exist_ok=True)
    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)


def get_provider_names() -> list[str]:
    data = load_providers()
    return [p["name"] for p in data.get("providers", [])]


def get_provider(name: str) -> Optional[dict]:
    data = load_providers()
    for p in data.get("providers", []):
        if p["name"] == name:
            return p
    return None


def get_provider_models(provider_name: str) -> list[dict]:
    provider = get_provider(provider_name)
    return provider.get("models", []) if provider else []


def get_default_provider() -> Optional[dict]:
    data = load_providers()
    default_name = data.get("default_provider", "")
    if default_name:
        return get_provider(default_name)
    providers = data.get("providers", [])
    return providers[0] if providers else None


def set_default_provider(name: str) -> bool:
    data = load_providers()
    if any(p["name"] == name for p in data.get("providers", [])):
        data["default_provider"] = name
        save_providers(data)
        return True
    return False


def set_default_model(provider_name: str, model_id: str) -> bool:
    data = load_providers()
    for p in data.get("providers", []):
        if p["name"] == provider_name:
            if any(m["id"] == model_id for m in p.get("models", [])):
                p["default_model"] = model_id
                save_providers(data)
                return True
    return False


def update_provider_api_key(name: str, api_key: str) -> bool:
    data = load_providers()
    for p in data.get("providers", []):
        if p["name"] == name:
            p["api_key"] = api_key
            save_providers(data)
            return True
    return False


def get_permissions_path() -> Path:
    return get_config_dir() / "permissions.json"


def load_permissions() -> dict:
    path = get_permissions_path()
    if not path.exists():
        return {"allowed_tools": [], "always_allow": False}
    try:
        return json.loads(path.read_text())
    except:
        return {"allowed_tools": [], "always_allow": False}


def save_permissions(data: dict) -> None:
    get_permissions_path().write_text(json.dumps(data, indent=2))


def is_tool_allowed(tool_name: str) -> bool:
    perms = load_permissions()
    return perms.get("always_allow", False) or tool_name in perms.get(
        "allowed_tools", []
    )


def set_always_allow(allow: bool = True) -> None:
    perms = load_permissions()
    perms["always_allow"] = allow
    save_permissions(perms)


def get_project_version() -> str:
    path = Path(__file__).parent.parent.parent / "pyproject.toml"
    if path.exists():
        try:
            with open(path, "r") as f:
                content = f.read()
                import re

                match = re.search(r'version\s*=\s*"(.*?)"', content)
                if match:
                    return match.group(1)
        except:
            pass
    return "unknown"
