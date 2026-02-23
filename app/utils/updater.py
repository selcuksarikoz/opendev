import asyncio
import json
import platform
import shutil
import subprocess
from typing import Any


FORMULA_NAME = "opendev"
TAP_NAME = "selcuksarikoz/opendev"
TAP_URL = "https://github.com/selcuksarikoz/opendev"
QUALIFIED_FORMULA = f"{TAP_NAME}/{FORMULA_NAME}"


def _has_brew() -> bool:
    return shutil.which("brew") is not None


def _is_supported_platform() -> bool:
    return platform.system() in {"Darwin", "Linux"}


def _run_brew(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["brew", *args],
        capture_output=True,
        text=True,
        check=False,
    )


async def check_update_available(formula: str = FORMULA_NAME) -> dict[str, Any]:
    if not _is_supported_platform():
        return {"ok": False, "reason": "unsupported_platform"}
    if not _has_brew():
        return {"ok": False, "reason": "brew_not_found"}

    proc = await asyncio.to_thread(_run_brew, ["outdated", "--json=v2", formula])
    if proc.returncode != 0:
        proc = await asyncio.to_thread(_run_brew, ["outdated", "--json=v2", QUALIFIED_FORMULA])
    if proc.returncode != 0:
        return {"ok": False, "reason": "brew_outdated_failed", "stderr": proc.stderr.strip()}

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "reason": "invalid_brew_json"}

    formulae = payload.get("formulae", [])
    for item in formulae:
        if item.get("name") == formula:
            return {
                "ok": True,
                "update_available": True,
                "latest_version": item.get("current_version"),
                "installed_versions": item.get("installed_versions", []),
            }
    return {"ok": True, "update_available": False}


async def install_or_upgrade(formula: str = FORMULA_NAME) -> dict[str, Any]:
    if not _is_supported_platform():
        return {"ok": False, "reason": "unsupported_platform"}
    if not _has_brew():
        return {"ok": False, "reason": "brew_not_found"}

    tap_proc = await asyncio.to_thread(_run_brew, ["tap", TAP_NAME, TAP_URL])
    if tap_proc.returncode != 0:
        return {"ok": False, "reason": "brew_tap_failed", "stderr": tap_proc.stderr.strip()}

    list_proc = await asyncio.to_thread(_run_brew, ["list", "--formula", formula])
    cmd = ["upgrade", QUALIFIED_FORMULA] if list_proc.returncode == 0 else ["install", QUALIFIED_FORMULA]

    proc = await asyncio.to_thread(_run_brew, cmd)
    return {
        "ok": proc.returncode == 0,
        "action": cmd[0],
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }
