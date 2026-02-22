# opendev

A simple AI CLI for those who just want things to work.

I got tired of paying for LLM plans and still hitting limits, especially for repetitive chore work.
So I built a CLI tool focused on free models, where I can offload "worker" tasks and keep moving.

## What is this?

It's a terminal-first AI coding assistant focused on free/community models.
You manage providers and model lists from `providers.json`, then use it to handle coding chores from the command line.

## Installation

### Via Homebrew (Recommended)

The easiest way. No python management, no hassle:

```bash
brew tap selcuksarikoz/opendev
brew install opendev
```

If your tap repo name is different (for example `homebrew-ssrok`), use that tap path instead.

How Homebrew finds it:
- The tap repo (`homebrew-opendev`) contains `Formula/opendev.rb`.
- That formula points to GitHub release assets for `opendev`.
- This repo also includes `Formula/opendev.rb` as a synced reference template.

### From Source

If you want to run it in your dev environment:

1. Clone the repository:
   ```bash
   git clone https://github.com/selcuksarikoz/opendev.git
   cd open-dev
   ```
2. Run using `uv`:
   ```bash
   uv run opendev
   ```

3. Install command globally (so you can run `opendev` directly):
   ```bash
   uv tool install .
   ```

### Standalone Binary Install (Linux/macOS)

Build:
```bash
uv tool run pyinstaller --onefile --name opendev app/__main__.py
```

Install to PATH:
```bash
install -m 755 dist/opendev ~/.local/bin/opendev
```

Or system-wide:
```bash
sudo install -m 755 dist/opendev /usr/local/bin/opendev
```

### Windows

Build:
```powershell
uv tool run pyinstaller --onefile --name opendev app/__main__.py
```

Add `dist\` to PATH or move `dist\opendev.exe` to a directory already in PATH.

### Creating Standalone Executables

If you want to build a single binary for your specific OS (macOS, Linux, or Windows):

1. Install `PyInstaller`:
   ```bash
   pip install pyinstaller
   ```
2. Generate the build:
   ```bash
   pyinstaller --onefile --name opendev app/__main__.py
   ```
   The executable will be generated in the `dist/` folder. Build on each target OS for native binaries.

## Release Workflow

Use the release script:

```bash
./scripts/build.sh --patch
```

Supported version bumps:
- `--patch`
- `--minor`
- `--major`

The script will:
1. Bump version in `pyproject.toml`
2. Build macOS binaries for both Apple Silicon (`arm64`) and Intel (`x86_64`) with PyInstaller
3. Package both macOS archives (`opendev-macos-arm64.tar.gz` and `opendev-macos-x86_64.tar.gz`)
4. Generate SHA256
5. Update local Homebrew tap formula commit (`homebrew-opendev`)
6. Create release commit
7. Create annotated git tag

It does **not** push. You push manually.

Then publish release asset (after pushing tag):

```bash
gh release create vX.Y.Z artifacts/vX.Y.Z/opendev-macos-arm64.tar.gz artifacts/vX.Y.Z/opendev-macos-x86_64.tar.gz --title "vX.Y.Z" --notes "Release vX.Y.Z"
```

## How to use

Everything is controlled by the `providers.json` file.

- **Providers + Free Models:** `~/.opendev/providers.json` is used for provider setup and free LLM model lists (OpenRouter/Groq/etc.).
- **Custom Keys:** Put your API keys in `~/.opendev/providers.json`.
- **Auto-updates:** If you're using the brew version, the bundled `providers.json` is updated with new free models.
- **Fun Fact:** This tool was made for free-model workflows, so it is happiest when your budget is zero.

## Commands

| Command            | Description                                            |
| ------------------ | ------------------------------------------------------ |
| `/model`           | Select provider and model                              |
| `/settings`        | Configure AI settings (max tokens, temperature, top_p) |
| `/new` or `/clear` | Start new conversation                                 |
| `/compact`         | Compact conversation context                           |
| `/update`          | Check/install updates via Homebrew                     |
| `/help`            | Show available commands                                |

### Quick Actions

- Type `@filename` to attach a file to your message
- Use `/` for command autocomplete
- Press **Enter** to send message

## Keyboard Shortcuts

| Shortcut   | Action                                               |
| ---------- | ---------------------------------------------------- |
| `Tab`      | Cycle between **Build** / **Agent** / **Plan** modes |
| `Up/Down`  | Navigate history or dropdown                         |
| `Ctrl + C` | Cancel current request                               |
| `Ctrl + D` | Quit                                                 |
| `Ctrl + L` | Clear chat (in conversation)                         |
| `Esc`      | Cancel request (in conversation)                     |

---

_Built because paid limits are annoying._
