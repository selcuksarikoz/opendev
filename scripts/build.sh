#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/build.sh [--major|--minor|--patch]

What it does:
1. Bumps version in pyproject.toml
2. Builds standalone binary with PyInstaller
3. Creates release commit and git tag
4. Packages macOS artifacts and updates Formula/opendev.rb
6. Pushes commit/tag and creates GitHub release with assets

Notes:
- Run from a clean git working tree.
USAGE
}

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

case "${1}" in
  --major|--minor|--patch) ;;
  *)
    usage
    exit 1
    ;;
esac

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Error: git working tree is not clean. Commit/stash changes first."
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is required."
  exit 1
fi
if ! command -v gh >/dev/null 2>&1; then
  echo "Error: gh CLI is required."
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "Error: gh is not authenticated. Run: gh auth login"
  exit 1
fi

BUMP_PART="${1#--}"

NEW_VERSION="$(
python - "$BUMP_PART" <<'PY'
from pathlib import Path
import re
import sys

part = sys.argv[1]
path = Path("pyproject.toml")
text = path.read_text()
match = re.search(r'^version\s*=\s*"(\d+)\.(\d+)\.(\d+)"\s*$', text, re.MULTILINE)
if not match:
    raise SystemExit("Could not find version in pyproject.toml")

major, minor, patch = map(int, match.groups())
if part == "major":
    major, minor, patch = major + 1, 0, 0
elif part == "minor":
    minor, patch = minor + 1, 0
elif part == "patch":
    patch += 1
else:
    raise SystemExit("Invalid bump part")

new_version = f"{major}.{minor}.{patch}"
updated = re.sub(
    r'^version\s*=\s*"\d+\.\d+\.\d+"\s*$',
    f'version = "{new_version}"',
    text,
    count=1,
    flags=re.MULTILINE,
)
path.write_text(updated)
print(new_version)
PY
)"

echo "Version bumped to: ${NEW_VERSION}"

OS_NAME="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH_NAME="$(uname -m)"
ARTIFACT_DIR="artifacts"
rm -rf "${ARTIFACT_DIR}"
mkdir -p "${ARTIFACT_DIR}"

MAC_ARCH=""
if [[ "${OS_NAME}" == "darwin" ]]; then
  case "${ARCH_NAME}" in
    arm64) MAC_ARCH="arm64" ;;
    x86_64) MAC_ARCH="x86_64" ;;
  esac
fi

rm -rf build dist

BUILD_PYTHON_VERSION="${BUILD_PYTHON_VERSION:-3.12}"
BUILD_ENV_ROOT="build/venvs"
ARM64_ENV_DIR="${BUILD_ENV_ROOT}/arm64"
X86_ENV_DIR="${BUILD_ENV_ROOT}/x86_64"
PYI_COMMON_ARGS=(
  --collect-all rich
  --add-data "${ROOT_DIR}/app/ui/style.tcss:app/ui"
)

create_uv_build_env() {
  local env_dir="$1"
  rm -rf "${env_dir}"
  env -u VIRTUAL_ENV -u PYTHONPATH -u PYTHONHOME \
    uv venv --python "${BUILD_PYTHON_VERSION}" "${env_dir}"
  env -u VIRTUAL_ENV -u PYTHONPATH -u PYTHONHOME \
    uv pip install --python "${env_dir}/bin/python" -e . pyinstaller
}

find_x86_python() {
  local candidates=()
  if [[ -n "${X86_PYTHON:-}" ]]; then
    candidates+=("${X86_PYTHON}")
  fi
  candidates+=("/usr/local/bin/python3.12" "/usr/local/bin/python3.11" "/usr/local/bin/python3")

  for candidate in "${candidates[@]}"; do
    if [[ ! -x "${candidate}" ]]; then
      continue
    fi
    if /usr/bin/arch -x86_64 "${candidate}" -c 'import platform,sys; raise SystemExit(0 if (platform.machine()=="x86_64" and sys.version_info >= (3,11)) else 1)' >/dev/null 2>&1; then
      printf "%s\n" "${candidate}"
      return 0
    fi
  done
  return 1
}

create_x86_rosetta_env() {
  local env_dir="$1"
  local x86_python_bin="$2"
  rm -rf "${env_dir}"
  /usr/bin/arch -x86_64 "${x86_python_bin}" -m venv "${env_dir}"
  /usr/bin/arch -x86_64 "${env_dir}/bin/python" -m pip install --upgrade pip
  /usr/bin/arch -x86_64 "${env_dir}/bin/python" -m pip install -e . pyinstaller
}

run_pyinstaller() {
  local env_dir="$1"
  shift
  "${env_dir}/bin/python" -m PyInstaller "$@"
}

if [[ "${OS_NAME}" == "darwin" ]]; then
  echo "Preparing isolated arm64 build environment (Python ${BUILD_PYTHON_VERSION})..."
  create_uv_build_env "${ARM64_ENV_DIR}"

  echo "Building macOS arm64 binary..."
  run_pyinstaller "${ARM64_ENV_DIR}" \
    "${PYI_COMMON_ARGS[@]}" \
    --onefile \
    --name opendev \
    --target-arch arm64 \
    --distpath dist/arm64 \
    --workpath build/arm64 \
    --specpath build/spec/arm64 \
    run.py

  echo "Building macOS x86_64 binary..."
  if [[ "${ARCH_NAME}" == "arm64" ]]; then
    if ! /usr/bin/arch -x86_64 /usr/bin/true >/dev/null 2>&1; then
      echo "Error: Rosetta is required for x86_64 build on Apple Silicon."
      echo "Install Rosetta: softwareupdate --install-rosetta"
      exit 1
    fi
    X86_PYTHON_BIN="$(find_x86_python || true)"
    if [[ -z "${X86_PYTHON_BIN}" ]]; then
      echo "Error: x86_64 Python >=3.11 not found."
      echo "Install one under Rosetta (recommended: /usr/local/bin/python3.12) or set X86_PYTHON."
      exit 1
    fi
    echo "Preparing isolated x86_64 build environment under Rosetta (${X86_PYTHON_BIN})..."
    create_x86_rosetta_env "${X86_ENV_DIR}" "${X86_PYTHON_BIN}"
    /usr/bin/arch -x86_64 "${X86_ENV_DIR}/bin/python" -m PyInstaller \
      "${PYI_COMMON_ARGS[@]}" \
      --onefile \
      --name opendev \
      --target-arch x86_64 \
      --distpath dist/x86_64 \
      --workpath build/x86_64 \
      --specpath build/spec/x86_64 \
      run.py
  else
    echo "Preparing isolated x86_64 build environment (Python ${BUILD_PYTHON_VERSION})..."
    create_uv_build_env "${X86_ENV_DIR}"
    run_pyinstaller "${X86_ENV_DIR}" \
      "${PYI_COMMON_ARGS[@]}" \
      --onefile \
      --name opendev \
      --target-arch x86_64 \
      --distpath dist/x86_64 \
      --workpath build/x86_64 \
      --specpath build/spec/x86_64 \
      run.py
  fi

  cp "dist/${MAC_ARCH}/opendev" "${ARTIFACT_DIR}/opendev-${OS_NAME}-${ARCH_NAME}"
else
  echo "Preparing isolated build environment (Python ${BUILD_PYTHON_VERSION})..."
  create_uv_build_env "${ARM64_ENV_DIR}"
  run_pyinstaller "${ARM64_ENV_DIR}" "${PYI_COMMON_ARGS[@]}" --onefile --name opendev run.py
  if [[ -f "dist/opendev" ]]; then
    cp "dist/opendev" "${ARTIFACT_DIR}/opendev-${OS_NAME}-${ARCH_NAME}"
  elif [[ -f "dist/opendev.exe" ]]; then
    cp "dist/opendev.exe" "${ARTIFACT_DIR}/opendev-${OS_NAME}-${ARCH_NAME}.exe"
  else
    echo "Error: built binary not found in dist/"
    exit 1
  fi
fi

if [[ -n "${MAC_ARCH}" ]]; then
  ARM64_STAGE_DIR="${ARTIFACT_DIR}/opendev-macos-arm64"
  X86_64_STAGE_DIR="${ARTIFACT_DIR}/opendev-macos-x86_64"
  ARM64_TAR="${ARTIFACT_DIR}/opendev-macos-arm64.tar.gz"
  X86_64_TAR="${ARTIFACT_DIR}/opendev-macos-x86_64.tar.gz"

  mkdir -p "${ARM64_STAGE_DIR}" "${X86_64_STAGE_DIR}"
  cp "dist/arm64/opendev" "${ARM64_STAGE_DIR}/opendev"
  cp "dist/x86_64/opendev" "${X86_64_STAGE_DIR}/opendev"
  tar -C "${ARM64_STAGE_DIR}" -czf "${ARM64_TAR}" "opendev"
  tar -C "${X86_64_STAGE_DIR}" -czf "${X86_64_TAR}" "opendev"

  ARM64_SHA="$(shasum -a 256 "${ARM64_TAR}" | awk '{print $1}')"
  X86_64_SHA="$(shasum -a 256 "${X86_64_TAR}" | awk '{print $1}')"

  if [[ -z "${ARM64_SHA}" || -z "${X86_64_SHA}" ]]; then
    echo "Error: both macOS SHA256 values are required to update Formula/opendev.rb."
    exit 1
  fi
  {
    printf "%s  %s\n" "${ARM64_SHA}" "opendev-macos-arm64.tar.gz"
    printf "%s  %s\n" "${X86_64_SHA}" "opendev-macos-x86_64.tar.gz"
  } > "${ARTIFACT_DIR}/sha256.txt"

  FORMULA_PATH="${ROOT_DIR}/Formula/opendev.rb"
  mkdir -p "$(dirname "${FORMULA_PATH}")"
  ARM64_URL="https://github.com/selcuksarikoz/opendev/releases/download/v${NEW_VERSION}/opendev-macos-arm64.tar.gz"
  X86_64_URL="https://github.com/selcuksarikoz/opendev/releases/download/v${NEW_VERSION}/opendev-macos-x86_64.tar.gz"
  FORMULA_CONTENT="$(cat <<RUBY
class Opendev < Formula
  desc "Terminal-first AI coding assistant focused on free/community models"
  homepage "https://github.com/selcuksarikoz/opendev"
  version "${NEW_VERSION}"

  if OS.mac?
    if Hardware::CPU.arm?
      url "${ARM64_URL}"
      sha256 "${ARM64_SHA}"
    elsif Hardware::CPU.intel?
      url "${X86_64_URL}"
      sha256 "${X86_64_SHA}"
    else
      odie "Unsupported macOS CPU."
    end
  else
    odie "Homebrew formula currently ships macOS binaries only."
  end

  def install
    bin.install "opendev"
  end

  test do
    assert_match "usage", shell_output("#{bin}/opendev --help 2>&1").downcase
  end
end
RUBY
)"
  printf "%s\n" "${FORMULA_CONTENT}" > "${FORMULA_PATH}"
fi

git add pyproject.toml Formula/opendev.rb
git commit -m "release: v${NEW_VERSION}"
git tag -a "v${NEW_VERSION}" -m "Release v${NEW_VERSION}"

echo
echo "Done."
echo "Created commit + tag: v${NEW_VERSION}"
echo "Built artifact(s): ${ARTIFACT_DIR}"
if [[ -n "${MAC_ARCH}" ]]; then
  echo "macOS archive: ${ARTIFACT_DIR}/opendev-macos-${MAC_ARCH}.tar.gz"
  echo "SHA256 arm64: ${ARM64_SHA}"
  echo "SHA256 x86_64: ${X86_64_SHA}"
fi

echo "Pushing commit and tag to origin..."
git push origin HEAD
git push origin "v${NEW_VERSION}"

if [[ -n "${MAC_ARCH}" ]]; then
  echo "Creating GitHub release v${NEW_VERSION}..."
  RELEASE_NOTES="Release v${NEW_VERSION}"
  gh release create \
    "v${NEW_VERSION}" \
    "${ARTIFACT_DIR}/opendev-macos-arm64.tar.gz" \
    "${ARTIFACT_DIR}/opendev-macos-x86_64.tar.gz" \
    "${ARTIFACT_DIR}/sha256.txt" \
    --title "v${NEW_VERSION}" \
    --notes "${RELEASE_NOTES}"
fi

echo "GitHub release published: v${NEW_VERSION}"
