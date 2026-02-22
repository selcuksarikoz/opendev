#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/build.sh [--major|--minor|--patch]

What it does:
1. Bumps version in pyproject.toml
2. Builds standalone binary with PyInstaller
3. Creates release commit and git tag
4. Packages macOS artifact for Homebrew tap
5. Updates local tap repo formula commit (no push)

Notes:
- Push is NOT performed.
- Run from a clean git working tree.
- Homebrew tap update is performed locally in ../homebrew-opendev (or TAP_DIR env).
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

rm -rf build dist
uv tool run pyinstaller --onefile --name opendev app/__main__.py

OS_NAME="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH_NAME="$(uname -m)"
ARTIFACT_DIR="artifacts/v${NEW_VERSION}"
mkdir -p "${ARTIFACT_DIR}"

if [[ -f "dist/opendev" ]]; then
  cp "dist/opendev" "${ARTIFACT_DIR}/opendev-${OS_NAME}-${ARCH_NAME}"
elif [[ -f "dist/opendev.exe" ]]; then
  cp "dist/opendev.exe" "${ARTIFACT_DIR}/opendev-${OS_NAME}-${ARCH_NAME}.exe"
else
  echo "Error: built binary not found in dist/"
  exit 1
fi

MAC_ARCH=""
if [[ "${OS_NAME}" == "darwin" ]]; then
  case "${ARCH_NAME}" in
    arm64) MAC_ARCH="arm64" ;;
    x86_64) MAC_ARCH="x86_64" ;;
  esac
fi

if [[ -n "${MAC_ARCH}" ]]; then
  MAC_STAGE_DIR="${ARTIFACT_DIR}/opendev-macos-${MAC_ARCH}"
  mkdir -p "${MAC_STAGE_DIR}"
  cp "dist/opendev" "${MAC_STAGE_DIR}/opendev"
  TAR_PATH="${ARTIFACT_DIR}/opendev-macos-${MAC_ARCH}.tar.gz"
  tar -C "${MAC_STAGE_DIR}" -czf "${TAR_PATH}" "opendev"
  SHA256="$(shasum -a 256 "${TAR_PATH}" | awk '{print $1}')"
  printf "%s  %s\n" "${SHA256}" "$(basename "${TAR_PATH}")" > "${ARTIFACT_DIR}/sha256.txt"

  # Update Homebrew tap formula locally (commit, no push)
  TAP_REPO_URL="${TAP_REPO_URL:-https://github.com/selcuksarikoz/homebrew-opendev.git}"
  TAP_DIR="${TAP_DIR:-../homebrew-opendev}"
  if [[ ! -d "${TAP_DIR}/.git" ]]; then
    git clone "${TAP_REPO_URL}" "${TAP_DIR}"
  fi
  FORMULA_DIR="${TAP_DIR}/Formula"
  FORMULA_PATH="${FORMULA_DIR}/opendev.rb"
  mkdir -p "${FORMULA_DIR}"
  ASSET_URL="https://github.com/selcuksarikoz/opendev/releases/download/v${NEW_VERSION}/opendev-macos-${MAC_ARCH}.tar.gz"
  if [[ "${MAC_ARCH}" == "arm64" ]]; then
    CPU_CHECK="arm?"
  else
    CPU_CHECK="intel?"
  fi
  cat > "${FORMULA_PATH}" <<RUBY
class Opendev < Formula
  desc "Terminal-first AI coding assistant focused on free/community models"
  homepage "https://github.com/selcuksarikoz/opendev"
  version "${NEW_VERSION}"

  if OS.mac?
    if Hardware::CPU.${CPU_CHECK}
      url "${ASSET_URL}"
      sha256 "${SHA256}"
    else
      odie "No published binary for this macOS CPU in v${NEW_VERSION}."
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
  pushd "${TAP_DIR}" >/dev/null
  if ! git diff --quiet -- "${FORMULA_PATH}"; then
    git add "${FORMULA_PATH}"
    git commit -m "opendev ${NEW_VERSION}"
    echo "Tap formula updated and committed at: ${TAP_DIR}"
  else
    echo "No tap formula changes detected."
  fi
  popd >/dev/null
fi

git add pyproject.toml
git commit -m "release: v${NEW_VERSION}"
git tag -a "v${NEW_VERSION}" -m "Release v${NEW_VERSION}"

echo
echo "Done."
echo "Created commit + tag: v${NEW_VERSION}"
echo "Built artifact(s): ${ARTIFACT_DIR}"
if [[ -n "${MAC_ARCH}" ]]; then
  echo "macOS archive: ${ARTIFACT_DIR}/opendev-macos-${MAC_ARCH}.tar.gz"
  echo "SHA256: ${SHA256}"
  echo "Tap repo: ${TAP_DIR}"
fi
echo "Push manually when ready:"
echo "  git push origin HEAD"
echo "  git push origin v${NEW_VERSION}"
if [[ -n "${MAC_ARCH}" ]]; then
  echo
  echo "After pushing tag, create GitHub release and upload tar.gz:"
  echo "  gh release create v${NEW_VERSION} ${ARTIFACT_DIR}/opendev-macos-${MAC_ARCH}.tar.gz --title \"v${NEW_VERSION}\" --notes \"Release v${NEW_VERSION}\""
fi
