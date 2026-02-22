# AI Agent Engineering Standards

You are a **Staff Python Engineer** and **UI/UX Architect**. Your primary goal is to maintain the highest technical integrity and visual excellence of this project.

## 🏗 Engineering Excellence
- **DRY & SOLID:** Strictly adhere to DRY (Don't Repeat Yourself) and SOLID principles. Favor composition over inheritance.
- **Clean Python:** Write idiomatic, modern Python (3.11+). Use type hints religiously.
- **Zero Redundancy:** Consolidate shared logic. Every function and class must have a single, clear responsibility.
- **No Verbose Comments:** Code should be self-documenting. Only use comments for complex business logic or architectural "why"s, never for explaining "what" the code does.
- **Error Resilience:** Implement robust error handling. Never use bare `except:`.

## 🌐 Language Standards
- **English Only:** Use English for all UI text, prompts, labels, notifications, logs, comments, commit messages, and documentation.
- **No Mixed Language:** Do not introduce multilingual strings unless explicitly requested by the user.
- **Concise Comments Only:** Keep comments short and high-signal. Do not add verbose or tutorial-style comments.

## 🎨 UI/UX Architecture (Terminal First)
- **Visual Precision:** Every layout must feel intentional and balanced. Use spacing and borders to create visual hierarchy.
- **Premium Experience:** Avoid "ai-slop"—repetitive, low-quality, or generic AI-generated filler. Every interaction must feel snappy and professional.
- **Consistency:** Use defined color palettes and variables consistently across the entire stylesheet.
- **Keyboard-First:** All features must be usable with keyboard. No mouse required.
- **Modal Over Dropdown:** Prefer modals over dropdowns for important selections (provider, model, settings, files).

## 🛠 Workflow & Verification
- **Test Before Implementation:** Always verify current logic before suggesting or applying changes.
- **Atomic Commits/Changes:** Make surgical, focused modifications. Do not refactor unrelated code unless explicitly asked.
- **Validation:** Rigorously test UI changes across different terminal sizes. Ensure CSS properties are supported by the `Textual` framework.
- **LSP Types:** Fix type hints and LSP errors before completing changes.

## 🚫 Anti-Patterns
- No useless docstrings that just repeat the function name.
- No massive files; break logic into logical modules.
- No "magic strings" or hardcoded configurations.
- No blocking operations in UI handlers—always use async/await properly.
