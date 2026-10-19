---
name: here
description: Connect the current folder to Kiln (the game-development framework) — register its marketplace if needed, enable the kiln plugin for this project only, then hand over to /kiln:setup.
disable-model-invocation: true
allowed-tools: Bash, PowerShell, Read
---

# /kiln-start:here

Kiln is installed per project: its hooks and rules must not reach other projects. This command is
the one piece installed for the whole user, so it exists in every folder.

0. **A project folder?** `python "${CLAUDE_SKILL_DIR}/scripts/folder_check.py"`: exit 1 (the
   home folder, a folder above it, a drive root) → stop, tell the user what it printed and change
   nothing; there a project install is the user's whole setup and `git init` takes in the profile.
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
   `~/kiln-tools`. Create the folder and store it with `python
   "${CLAUDE_SKILL_DIR}/scripts/json_config.py" merge --file ~/.kiln/machine.json --json
   '{"tools_root": "<path with forward slashes>"}'` (keeps the other keys; never write the file
   by hand). It can be changed later in
   `/kiln:setup`. Kiln installs nothing without a further yes; this only says where.
3. **Enable for this project only.** In the project root:
   `claude plugin install kiln@kiln --scope project`; if it reports the plugin is already installed,
   `claude plugin enable kiln@kiln --scope project`. Check with `claude plugin list` that
   `kiln@kiln` shows `Scope: project`, `enabled`. OpenAI Codex as well (if the user works with it):
   `codex plugin add kiln@kiln` once per machine, then only through Kiln's script, never by hand
   (a line glued to the next block stops Codex from starting): `python
   <kiln>/scripts/codex_config.py --off` (user config: Kiln off in folders that are not connected)
   and here `python <kiln>/scripts/codex_config.py --file .codex/config.toml --on` (Codex reads it
   for trusted projects). `<kiln>` is the installed kiln plugin folder, the newest version under
   `~/.codex/plugins/cache/kiln/kiln/` (Windows: `%USERPROFILE%\.codex\plugins\cache\kiln\kiln\`);
   quote it. The script needs Python 3.11+; if it fails, stop and tell the user - never fall back
   to a hand edit.
   Gemini CLI as well (if the user works with it): the extension once per machine
   (`gemini extensions install https://github.com/ajadi/kiln --ref gemini-extension --consent`),
   then `gemini extensions disable kiln --scope user` and, here,
   `gemini extensions enable kiln --scope workspace` (setup §6). GitHub Copilot CLI as well:
   `copilot plugin marketplace add ajadi/kiln`, `copilot plugin install kiln@kiln` and
   `copilot plugin disable kiln@kiln` once per machine, then here `python
   "${CLAUDE_SKILL_DIR}/scripts/json_config.py" merge --file .github/copilot/settings.json --json
   '{"enabledPlugins": {"kiln@kiln": true}}'` (keeps what is there; setup §6). OpenCode: nothing per machine;
   setup §6 writes the project's `.opencode/` Kiln parts.
4. **Hand over.** Plugin commands load when a session starts. Tell the user, in their language and
   in two lines: restart Claude Code in this folder, then run **`/kiln:setup`** — it explores the
   folder and asks one round of questions (engine, 2D/3D, kind, how much it may decide for them, …),
   with recommended answers. `/kiln:settings` changes those choices later.
