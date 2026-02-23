# opendev

Terminal-first AI coding CLI focused on free/community models.

I use AI mostly for chore work.
I am not expecting lifetime value from subscriptions, but constantly hitting limits and waiting for hours (sometimes days) is frustrating.
I used OpenCode before, but that also started to hit limits.
So I built this CLI to offload chore tasks to free models.

## What is this?

`opendev` is a keyboard-first coding assistant for terminal workflows.

- Provider/model configuration is managed from `~/.opendev/providers.json`.
- Conversation data is stored locally in `~/.opendev/data.db`.
- Supports agent-based execution, tool calls, planning mode, and build mode.
- Works best with free model providers (Groq, OpenRouter, etc.), but you can add any OpenAI-compatible provider.

## Installation

### Homebrew (recommended)

```bash
brew tap selcuksarikoz/opendev https://github.com/selcuksarikoz/opendev
brew install selcuksarikoz/opendev/opendev
```

### From source

```bash
git clone https://github.com/selcuksarikoz/opendev.git
cd opendev
uv run opendev
```

Install as a global command:

```bash
uv tool install .
```

### Single-file binary (manual)

```bash
uv run --with pyinstaller pyinstaller --onefile --name opendev run.py
```

Move binary to your PATH (`~/.local/bin`, `/usr/local/bin`, etc.).

On Apple Silicon, if you need an `x86_64` build, install Rosetta first:

```bash
softwareupdate --install-rosetta --agree-to-license
```

For dual-arch release builds on Apple Silicon, `scripts/build.sh` also needs an `x86_64` Python 3.11+.
If it is not in `/usr/local/bin/python3.12` (or `/usr/local/bin/python3.11`), set it explicitly:

```bash
X86_PYTHON=/path/to/x86_64/python3.12 ./scripts/build.sh --patch
```

## Providers and config

- Providers file: `~/.opendev/providers.json`
- Bundled default providers: `providers.json` (repo root)
- Local storage root: `~/.opendev/`

`providers.json` is used to:
- Add/edit providers
- Manage model lists
- Select default provider/model

API keys are saved securely in local storage; provider selection flow also supports optional key update.

`providers.json` will be updated continuously with free model entries.
If you installed with Homebrew, run `/update` regularly to stay current.

## Commands

| Command          | Description                                            |
| ---------------- | ------------------------------------------------------ |
| `/new`           | Start new conversation                                 |
| `/conversations` | List saved conversations and continue selected one     |
| `/model`         | Select provider/model and optionally update API key    |
| `/agents`        | Switch active agent                                    |
| `/settings`      | Configure AI settings (`max_tokens`, `temperature`, `top_p`) |
| `/compact`       | Compact current conversation context                   |
| `/clean history` | Delete all conversations/messages/history              |
| `/update`        | Update via Homebrew (if brew install is used)          |
| `/help`          | Show command list                                      |

## Keyboard shortcuts

| Shortcut          | Action                                  |
| ----------------- | --------------------------------------- |
| `Tab`             | Toggle mode (`Build` / `Plan`) in chat input |
| `Up / Down`       | Input history or autocomplete navigation |
| `Enter`           | Submit input / confirm selection         |
| `Esc`             | Cancel current request                   |
| `Ctrl + C`        | Cancel request (or start new chat if idle) |
| `Ctrl + D`        | Quit                                     |
| `Ctrl + Shift + M`| Cycle mode                               |
| `Ctrl + L`        | Clear chat screen                         |

## Release workflow

Use:

```bash
./scripts/build.sh --patch
```

Supported bumps:
- `--patch`
- `--minor`
- `--major`

`scripts/build.sh` does all of this:
1. Bump version in `pyproject.toml`
2. Build macOS binaries for both `arm64` and `x86_64`
3. Create release archives and SHA256 file
4. Update `Formula/opendev.rb` in this repo
6. Create release commit and annotated tag
7. Push commit/tag to `origin`
8. Create GitHub release and upload assets from `artifacts/`

It rewrites `artifacts/` on each run (cleans old files first).

For macOS dual-arch release builds:
- `arm64` build runs natively.
- `x86_64` build runs under Rosetta on Apple Silicon with an `x86_64` Python 3.11+.
- If Rosetta is missing, `scripts/build.sh` exits with an install hint.

## Notes

- Homebrew formula currently ships macOS binaries.
- Linux/Windows users can build native binaries locally.
- The app defaults to `Plan` mode and can auto-skip plan for simple prompts.

_Built for free-model workflows and real-world coding chores._
