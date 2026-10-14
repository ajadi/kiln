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
2b. **Tools folder, once per machine.** Read `~/.kiln/machine.json` (the machine config both Kiln
   plugins share). No `tools_root` in it → ask the user, in their language, where Kiln may install
   editors, MCP servers, Python environments and downloads: recommend a tools folder they already
   use if you can see one (a folder named `tools` / `_tools` next to their projects), else
   `~/kiln-tools`. Create the folder and write `{"tools_root": "<path with forward slashes>"}`
   into `~/.kiln/machine.json` (merge, keep other keys). It can be changed later in
   `/kiln:setup`. Kiln installs nothing without a further yes; this only says where.
3. **Enable for this project only.** In the project root:
   `claude plugin install kiln@kiln --scope project`; if it reports the plugin is already installed,
   `claude plugin enable kiln@kiln --scope project`. Check with `claude plugin list` that
   `kiln@kiln` shows `Scope: project`, `enabled`. OpenAI Codex as well (if the user works with it):
   `codex plugin add kiln@kiln` once per machine, then keep `[plugins."kiln@kiln"]` / `enabled = false`
   in the user `~/.codex/config.toml` (Kiln stays off in folders that are not connected) and write
   `enabled = true` in this project's `.codex/config.toml` (Codex reads it for trusted projects).
   Gemini CLI as well (if the user works with it): the extension once per machine
   (`gemini extensions install https://github.com/ajadi/kiln --ref gemini-extension --consent`),
   then `gemini extensions disable kiln --scope user` and, here,
   `gemini extensions enable kiln --scope workspace` (setup §6).
4. **Hand over.** Plugin commands load when a session starts. Tell the user, in their language and
   in two lines: restart Claude Code in this folder, then run **`/kiln:setup`** — it explores the
   folder and asks one round of questions (engine, 2D/3D, kind, how much it may decide for them, …),
   with recommended answers. `/kiln:settings` changes those choices later.
