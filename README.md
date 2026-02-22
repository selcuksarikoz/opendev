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
brew tap selcuksarikoz/open-dev
brew install opendev
```

### From Source
If you want to run it in your dev environment:
1. Clone the repository:
   ```bash
   git clone https://github.com/selcuksarikoz/open-dev.git
   cd open-dev
   ```
2. Run using `uv`:
   ```bash
   uv run opendev
   ```

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
The executable will be generated in the `dist/` folder. Note that you must build on the target OS (e.g., build on Windows to get a `.exe`).

## How to use
Everything is controlled by the `providers.json` file.

- **Providers + Free Models:** `~/.opendev/providers.json` is used for provider setup and free LLM model lists (OpenRouter/Groq/etc.).
- **Custom Keys:** Put your API keys in `~/.opendev/providers.json`.
- **Auto-updates:** If you're using the brew version, the bundled `providers.json` is updated with new free models.
- **Fun Fact:** This tool was made for free-model workflows, so it is happiest when your budget is zero.

## Commands

| Command | Description |
|---------|-------------|
| `/model` | Select provider and model |
| `/settings` | Configure AI settings (max tokens, temperature, top_p) |
| `/new` or `/clear` | Start new conversation |
| `/compact` | Compact conversation context |
| `/help` | Show available commands |

### Quick Actions
- Type `@filename` to attach a file to your message
- Use `/` for command autocomplete
- Press **Enter** to send message

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Tab` | Cycle between **Build** / **Agent** / **Plan** modes |
| `Up/Down` | Navigate history or dropdown |
| `Ctrl + C` | Cancel current request |
| `Ctrl + D` | Quit |
| `Ctrl + L` | Clear chat (in conversation) |
| `Esc` | Cancel request (in conversation) |

---

*Built because paid limits are annoying.*
