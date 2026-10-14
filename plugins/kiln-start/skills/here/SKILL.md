---
name: here
description: Connect the current folder to Kiln (the game-development framework) — register its marketplace if needed, enable the kiln plugin for this project only, then hand over to /kiln:setup.
disable-model-invocation: true
allowed-tools: Bash, PowerShell, Read
---

# /kiln-start:here

Kiln is installed per project: its hooks and rules must not reach other projects. This command is
the one piece installed for the whole user, so it exists in every folder.

1. **Already Kiln here?** `manifest.md` with `framework=kiln` → only make sure the plugin is enabled
   (step 3), then go to step 4. `manifest.md` naming another framework → stop and tell the user;
   two frameworks' rules in one project conflict.
2. **Marketplace.** `claude plugin marketplace list`: `kiln` present → go on. Absent → add it from
   the Kiln repo — a local checkout (`claude plugin marketplace add <path to the kiln repo>`) or
   GitHub (`claude plugin marketplace add ajadi/kiln`).
   Ask once which, recommending the local checkout when one exists.
3. **Enable for this project only.** In the project root:
   `claude plugin install kiln@kiln --scope project`; if it reports the plugin is already installed,
   `claude plugin enable kiln@kiln --scope project`. Check with `claude plugin list` that
   `kiln@kiln` shows `Scope: project`, `enabled`. OpenAI Codex as well (if the user works with it):
   `codex plugin add kiln@kiln` once per machine, then keep `[plugins."kiln@kiln"]` / `enabled = false`
   in the user `~/.codex/config.toml` (Kiln stays off in folders that are not connected) and write
   `enabled = true` in this project's `.codex/config.toml` (Codex reads it for trusted projects).
4. **Hand over.** Plugin commands load when a session starts. Tell the user, in their language and
   in two lines: restart Claude Code in this folder, then run **`/kiln:setup`** — it explores the
   folder and asks one round of questions (engine, 2D/3D, kind, how much it may decide for them, …),
   with recommended answers. `/kiln:settings` changes those choices later.
