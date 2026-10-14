---
name: setup
description: Set up Kiln in the current folder as a game project for Godot, Unity or Unreal (3D or 2D) with Blender — engine and dimension choice, project files (manifest, CLAUDE.md, GAME.md, backlog, memory), git ignores and LFS, project-scope plugin enable, MCP permissions, the engine project and its MCP server/addon, Blender Lab add-on check. Use when the user asks to set up / install Kiln or start a new Kiln game project here.
disable-model-invocation: true
argument-hint: "[project name]"
allowed-tools: Read, Glob, Grep, Bash, PowerShell, Write, Edit
---

# /kiln:setup

Templates: `${CLAUDE_SKILL_DIR}/../../templates/project/`. Machine paths cache:
`${CLAUDE_PLUGIN_DATA}/machine.json` (`godot_exe`, `unity_exe`, `unreal_exe`, `blender_exe`,
`godot_ai_addon`).

Work through the steps in order — step 4 comes before step 5: `manifest.md` switches the guard
on. Do every step yourself (protocol: "Do it yourself"): install what is missing, write the files,
start the editors and their servers. A step goes to the user only when it has no automated route,
with the reason. Report to the user in their language at the end: what was created, what you
installed and started, what is still missing.

## 1. Look before writing

- `manifest.md` with a different `framework=` value → another framework owns this project. Stop
  and ask whether to convert it; two frameworks' rules in one project conflict.
- `manifest.md` with `framework=kiln` → already set up: only fill what is missing (never
  overwrite user files), run `pipeline.py migrate` (adds `touches:` lines, gates tables and new
  manifest keys after a Kiln update; confirm its guesses), then run step 8.
- Note existing `CLAUDE.md`, `AGENTS.md`, `.gitignore`, `.claude/settings.json`,
  `project.godot`, `ref/`, task briefs (`task*.md`) — they shape the steps below.
- Project name: `$ARGUMENTS`, else the folder name.
- Detect what you can: engine (`project.godot` → godot, `Assets/` + `ProjectSettings/` → unity,
  `*.uproject` → unreal), dimension (2D/3D project settings), new vs existing project (engine
  files, game code, assets present), runtimes (`AGENTS.md`, `.codex/`), the git remote and
  whether it is public (`gh repo view --json visibility`), existing `manifest.md` values.

## 1b. Questionnaire — one round, then the user's answer

Ask everything still open in **one message**: numbered questions, each with its choices and a
`➡️ recommended` answer worded so that "yes" accepts it; the user may answer by number ("1 yes,
3 ask"). Skip a question the exploration already settled and say what you found instead. Facts
are your job (look them up); only decisions go to the user. Then show the `manifest.md` lines you
will write and write them after the answer (a plain "yes" accepts all recommendations).

1. **Project** — new or existing (detected), name.
2. **Engine** — **Godot (recommended; best for 2D, lightest MCP)** / Unity 6 / Unreal 5.8 (MCP is
   Experimental; not for 2D) → `engine=`.
3. **Dimension** — 3D / 2D → `dimension=`.
4. **Agent apps** — Claude Code (default) / OpenAI Codex / both → `runtimes=`.
5. **Kind** — `game` (recommended: every acceptance gate) or `prototype` (a demo or test of an
   idea: one acceptance role + verifier, ≤ 2 review rounds; the run skill) → `kind=`.
6. **Deciding for you** (`user_gates=`) — explain in two lines: with `proxy` (recommended) the
   agent does not stop for your decisions (scope details, the look, "is it fun"): it takes the
   recommended option, marks it PROXY and lists it in the report so you can say "redo"; with
   `ask` it asks and waits every time. Publishing, spending money, deleting your work and
   overriding a decision you made are never decided for you in either mode.
7. **Repository** — `private-solo` (recommended for a one-person private repo: Kiln's memory and
   tasks are committed) / `private-shared` / `public` (framework state stays local) → `repo_access=`.
8. **Generators** — models: `off` / `local` (open-weight, offline) / `api` (paid services; key in
   an environment variable) → `model_generators=`; sound and music the same → `audio_generators=`.
   Recommend `off` until a task needs one.
8a. **Tools folder** (once per machine; skip when machine.json has `tools_root`) — where Kiln
   installs editors, MCP servers, venvs and downloads: ➡️ an existing tools folder you already
   use (found: <path>) / `~/.local/share/kiln` → machine.json `tools_root`.

9. **Other skill packs** — list the non-Kiln plugins active here (`claude plugin list --json`:
   enabled, user or project scope; Codex: `codex plugin list`). General-purpose packs whose
   model-invoked skills overlap Kiln's process — e.g. `mattpocock-skills` (`prototype`, `tdd`,
   `code-review`, `research`, `grilling`, `domain-modeling`) — ➡️ off for this project only
   (they stay on elsewhere): `.claude/settings.json` `"enabledPlugins": {"<id>": false}`; Codex:
   `[plugins."<id>"]` / `enabled = false` in the project `.codex/config.toml`. The template
   already turns `mattpocock-skills` off. Packs that do not overlap (output style, editor
   helpers) stay on.

Keep `mcp_only=on` and `scene_first=on` without asking (they protect the editors and the
scene-first rule); mention them in one line.

After writing, tell the user how to change any of this later — the same text goes into the
project rules (CLAUDE.md template, "Kiln settings"): **`/kiln:settings`** shows the current values
and changes one ("/kiln:settings user_gates=ask"), or just say it in words ("ask me before
decisions", "this is a prototype now", in their own language); the agent changes `kind` and `user_gates` only when you ask.

## 2. Machine paths

Read `${CLAUDE_PLUGIN_DATA}/machine.json`. For each missing entry, find it, confirm it exists,
and save it:

- `godot_exe` (engine=godot): `where godot*`, common install folders,
  `<tools_root>/Godot/*/Godot_*_win64.exe`; if not found, install it yourself: the current
  stable win64 zip from `https://github.com/godotengine/godot-builds/releases`, unpacked into
  `<tools_root>/Godot/<version>/`.
- `unity_exe` (engine=unity): `C:/Program Files/Unity/Hub/Editor/6*/Editor/Unity.exe`.
- `unreal_exe` (engine=unreal): `C:/Program Files/Epic Games/UE_5.*/Engine/Binaries/Win64/UnrealEditor.exe`.
- `blender_exe`: the `BLENDER_PATH` of the `blender` MCP server (`claude mcp get blender`), else
  `C:/Program Files/Blender Foundation/Blender */blender.exe`.
- `godot_ai_addon`: the folder that contains `addons/godot_ai/plugin.cfg` with
  `name="Godot AI"`. Not found → download it yourself: the server is PyPI `godot-ai`
  (`uv tool install godot-ai==<version>`), which ships no addon; the addon is the GitHub release
  asset `godot-ai-v4-plugin.zip` of `hi-godot/godot-ai` tag `v<same version>` (`gh release download
  v4.3.0 -R hi-godot/godot-ai -p godot-ai-v4-plugin.zip`). The asset `godot-ai-plugin.zip` is the
  "Migration" plugin — not that one. Unpack to `<tools_root>/godot-ai/<version>/addons/godot_ai`.
- `godot_ai_command`: the exact command you registered for the `godot-ai` MCP server
  (`claude mcp get godot-ai`). The addon's client configurator can rewrite Claude Code's entry
  to its own `uvx` wrapper (seen: from `<tools_root>/uv/bin/godot-ai.exe attach` to a
  `pythonw ... uvx --from godot-ai==4.3.0` wrapper in the user profile, silently); the doctor
  compares against this value.
- `blender_mcp`: the Blender Lab MCP from `https://projects.blender.org/lab/blender_mcp` (releases
  page), never PyPI `blender_mcp` — that is a different server with the same name and version
  number. Server: `uv tool install <checkout>/mcp` (entry point `blender-mcp`); add-on (extension
  id `mcp`): `<blender_exe> --command extension install-file -r user_default -e <add-on zip>`.
  Doctor checks the tool names, not just "Connected".
- `tools_root`: the folder the user keeps tools in, if they have one (ask once in §1b; g2:
  "every tool under one tools folder"); else none. Downloads, unpacked editors, venvs and caches go
  under it (`<tools_root>/venvs/<name>`); without it, `~/.local/share/kiln/`.

Then write `production/tools.json` for this project (engine at its exact version, Blender, the
MCP servers and add-ons, uv, git-lfs, the venvs the roles need) and run the tools skill's
`tools_check.py detect` / `verify`; install what is missing as that skill says.

## 3. Repository

- Not a git repo → `git init` (tell the user).
- Python tool environments (audio, music, image tools) live outside the project in
  `<tools_root>/venvs/<name>` (machine.json; default `~/.local/share/kiln/venvs/<name>`); roles
  create them when first needed. A project with sound or music roles gets the audio venv now:
  `python -m venv <venvs>/audio` + `pip install numpy scipy soundfile pyloudnorm` (soundfile
  reads Ogg Vorbis; ffmpeg is then optional).
- Line endings: put `* text=auto eol=lf` at the top of `.gitattributes` (before the LFS block)
  and, in an existing repo, `git add --renormalize .` once. On Windows with
  `core.autocrlf=true` a repo without it showed 1045 files as modified by CRLF alone, which made
  "check git status after every agent" useless (g2 row 24).
- `repo_access` and `kind` come from the questionnaire (§1b); keep existing values.
- Append the block from `gitignore.tmpl` to `.gitignore` unless its `# --- kiln ---` marker is
  already there.
- If `git lfs version` works, append `gitattributes.tmpl` to `.gitattributes` (marker check) and
  run `git lfs install --local`; otherwise tell the user binary assets will be stored in plain
  git and how to enable LFS later.

## 4. Engine project and its MCP

### Godot

This part is bound to the project; say so to the user before doing it: the Godot AI editor
addon must sit in this project's `addons/` folder because Godot loads plugins per project.
To keep a single global copy, link it instead of copying:

- Windows: `New-Item -ItemType Junction -Path addons/godot_ai -Target <godot_ai_addon>`
- elsewhere: `ln -s <godot_ai_addon> addons/godot_ai`
- fall back to a copy only if linking fails, and say so.

A linked addon stays out of git: add `addons/godot_ai/` to `.gitignore` (git walks a Windows
junction and would commit ~270 third-party files; a Unix symlink would commit a path that exists
only on this machine). A fresh clone runs setup or doctor, which relinks it. A copied fallback
is committed like any other addon.

If there is no `project.godot`, write the minimal bootstrap yourself — do not send the user to
the Project Manager: `config_version=5`, `[application]` `config/name="<project name>"` and
`config/features=PackedStringArray("<major.minor>", "Forward Plus")` (`"Mobile"` or
`"GL Compatibility"` for those renderers), and `[editor_plugins]`
`enabled=PackedStringArray("res://addons/godot_ai/plugin.cfg")` — the editor enables the plugin
(and adds its game-helper autoload) on first open. UTF-8 without BOM, LF line ends. This is the
only time Kiln writes this file by hand — after that, project settings change only through the
editor and its MCP.

Game runs: agents start the game through the MCP (`project_run`) many times while the user may
be working in other apps. Godot 4.4+ shows it per the Game workspace mode; the floating modes pop
a window over everything on every run, and Godot 4.7 defaults to floating. Set the embedded mode
yourself in the same pass, before the editor first opens the project: write
`.godot/editor/project_metadata.cfg` with `[game_view]` `embed_on_play=true` and
`make_floating_on_play=false` (merge the two keys if the file exists). The editor reads it only at
start and rewrites it on exit, so the editor must be closed while you write it.

The guard lets the main session write a missing or empty `project.godot` and
`.godot/editor/project_metadata.cfg` (bootstrap); every other edit of `project.godot` goes
through the editor's MCP.

Then start the editor yourself if it is not running:
`Start-Process <godot_exe> -ArgumentList '--editor','--path','<project dir>'`.
2D projects: set the pixel-art or vector project settings from the art-2d skill §7 through the
MCP once the editor is connected (not by editing `project.godot`).

### Unity 6

1. Create the project yourself from the command line: `"<unity_exe>" -batchmode -quit
   -createProject "<dir>" -cloneFromTemplate "<template .tgz>"`, the template from the editor's
   `Data/Resources/PackageManager/ProjectTemplates/` (Universal 3D, or Universal 2D for
   `dimension=2d`) — UNVERIFIED on Unity 6: confirm the project opens. Unity Hub is the fallback,
   handed to the user with the reason. Kiln does not hand-write scenes, prefabs or ProjectSettings.
2. Add the package yourself, pinned to a release tag:
   `https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#<tag>` (latest tag:
   `gh api repos/CoplayDev/unity-mcp/releases/latest`) — before the first open as a
   `dependencies` entry in `Packages/manifest.json` (package name from the repo's
   `MCPForUnity/package.json`). Start its HTTP server (Window → MCP for Unity; use its auto-start
   if it has one, otherwise this is the one handed-over click, with that reason); enable only the
   core, testing, scripting_ext and profiling tool groups (asset_gen off).
3. Register once per user: `claude mcp add --scope user --transport http unity http://localhost:8080/mcp`.
4. Project settings for agents (through the MCP after connecting): Run In Background on, Play
   Mode Input Behavior "All Device Input Always Goes To Game View", Asset Serialization Force
   Text, Visible Meta Files.

### Unreal 5.8

1. Create the project yourself: copy the engine's template (`<UE>/Templates/TP_Blank` or
   `TP_FirstPerson`; C++ if gameplay code is planned) into this folder and rename the
   `.uproject` — UNVERIFIED: confirm it opens (a C++ template also needs its module renamed). The
   Epic launcher is the fallback, handed to the user with the reason.
2. Enable **Unreal MCP**, **AllToolsets** and **Python Editor Script Plugin** yourself: `Plugins`
   entries (`{"Name": "<plugin>", "Enabled": true}`) in the `.uproject` before the first open,
   then start or restart the editor yourself. Per user: MCP auto-start on, port 8000, path `/mcp`
   (engine-unreal skill).
3. Register once per user: `claude mcp add --scope user --transport http unreal http://127.0.0.1:8000/mcp`
   (the name must be `unreal`; the guard matches `mcp__unreal__*`). UE 5.6/5.7: ChiR24/Unreal_mcp
   under the same name.
4. Optional, with the user's consent: Epic's Claude Code plugin
   `unreal-engine-skills-for-claude-code@claude-plugins-official`.
5. The Kiln probe component and toolset (engine-unreal skill, Playtest tools) are built by the
   gameplay developer in the first tech task, not by setup.

## 5. Project files

Copy from the templates without overwriting existing files: `manifest.md`, `GAME.md`,
`backlog.md`, `memory/**` (including `memory/out-of-scope/README.md`), `.claude/settings.json` (merge: add the template's allow/deny
entries to existing arrays and its `enabledPlugins` keys, keep everything else), `tasks/archive/`,
`design/`.

Godot only: an empty `.gdignore` file in every folder that holds working material, not game
content — `ref/`, `production/`, `research/`, `design/`, `tools/`, `export/`, `art/source/`
(create the folders). Every export preset's exclude filter also gets `tests/*, addons/godot_ai/*`
(the release skill's `build.py audit` checks both). Godot then neither imports nor exports them: reference images and other games'
screenshots never ship, and `.blend` sources are not handed to Godot's Blender importer (which
would run a background Blender). Never put `.gdignore` in `tests/` — probes run from there.

Placeholders: `{{PROJECT_NAME}}`, `{{DATE}}` (today), `{{ENGINE}}`, `{{DIMENSION}}`,
`{{RUNTIMES}}`, `{{AGENTS_IMPORT}}` → if `AGENTS.md` exists and the Kiln rules go to `CLAUDE.md`:
`Mandatory requirements from the user (shared with other agent tools): @AGENTS.md`, otherwise
remove the line.

Project rules (the `CLAUDE.md` template is the Kiln rules block for both runtimes):
- `runtimes=claude`: the block goes to `CLAUDE.md` — create it if absent, else append it between
  `<!-- kiln:begin -->` and `<!-- kiln:end -->` markers (replace that block on re-runs).
- Codex in `runtimes`: Codex reads `AGENTS.md`, not `CLAUDE.md`, so the block goes to `AGENTS.md`
  between the same markers (after any requirements the user already wrote there), and
  `CLAUDE.md` (Claude Code too) contains only `@AGENTS.md` — one copy of the rules, read by both.
  Keep the combined `AGENTS.md` under Codex's 32 KiB `project_doc_max_bytes`.

Show the user the added section.

Write the questionnaire answers (§1b) into `manifest.md`.

## 6. Enable the plugin for this project only

Claude Code: `claude plugin install kiln@kiln --scope project` — Kiln's hooks then run only in
this project. (If the user prefers not to commit `.claude/settings.json`, use `--scope local`.)
If the marketplace is unknown, `claude plugin marketplace add <kiln repo>`.

OpenAI Codex (when `runtimes` includes codex; commands from the Codex docs "Package your plugin",
"Hooks", "Subagents" and "Model Context Protocol"). Run them from a normal terminal: inside a
Codex session the workspace `.codex/` folder is read-only to commands.

1. Marketplace and plugin, once per machine: `codex plugin marketplace add <kiln repo path or
   owner/repo>` (Codex reads the repo's `.agents/plugins/marketplace.json`), then
   `codex plugin add kiln@kiln` (or install it from `/plugins`).
2. Enable it for this project only: project `.codex/config.toml` gets
   `[plugins."kiln@kiln"]` / `enabled = true`, plus `[plugins."mattpocock-skills@mattpocock"]` /
   `enabled = false` and any other overlapping pack from §1b item 9; set `enabled = false` in the
   user config if Kiln should stay off elsewhere. Codex loads project config only for trusted projects — trust the
   folder when Codex asks.
3. MCP servers, once per machine, with the same names as in Claude Code (the guard and the role
   instructions use them): `codex mcp add blender -- <blender-mcp executable>`,
   `codex mcp add godot-ai -- godot-ai attach`, `codex mcp add unity --url
   http://localhost:8080/mcp`, `codex mcp add unreal --url http://127.0.0.1:8000/mcp` — only the
   ones this project uses. Godot AI and Epic's Unreal MCP both default to port 8000; never run
   both, or move Unreal's `ServerPortNumber`.
4. Role agents: `python "<kiln plugin>/scripts/codex_agents.py"` in the project root writes
   `.codex/agents/kiln-<role>.toml` (31 files: instructions, model, effort; see the script
   header for what Codex applies). Re-run after every Kiln update.
5. Start a new Codex session and open `/hooks`: review and trust the Kiln hooks — Codex skips
   plugin hooks until their current definition is trusted.

## 7. Blender

Check that the Blender Lab add-on is installed (Blender `extensions/user_default/mcp` in the
user's Blender config folder); install it yourself if it is missing. If Blender is not running,
start it yourself — the GUI app, `Start-Process <blender_exe> -ArgumentList '--online-mode'`,
never `-b`/background mode. The add-on refuses to start its server unless Blender's online
access is on ("Online access must be enabled in the system preferences"; off by default in a
fresh Blender, so the bridge on port 9876 silently never starts — g2 row 20). `--online-mode`
turns it on for that run; launch with it every time (store the arguments in machine.json
`blender_args`). The add-on's Auto Start preference (`use_autostart`, on by default) then starts
its MCP server a few seconds after launch; step 8's probe confirms it. Only if Auto Start was turned off does the user
get one click (add-on preferences → Start server, or tick Auto Start), with that reason.

## 8. MCP check — blocking

Kiln is not connected to a project until everything it needs from MCP is really there. MCP
tools load when a session starts: if this run registered a server or enabled the plugin, tell
the user to restart the session (Codex: new session, trust the hooks in `/hooks`) and run setup
again — step 1 skips what exists and comes back here.

1. `python "${CLAUDE_SKILL_DIR}/../../scripts/mcp_check.py" required --runtime <claude|codex>`
   lists the servers this project needs (Blender, plus the engine's server; Blender is optional
   for 2D), the tools Kiln uses from each (including every tool named in a role's tool list),
   Unreal toolsets, and one read-only probe call per server.
2. Write every MCP tool name you can see for those servers into `.kiln/mcp-tools.txt`, one per
   line as `mcp__<server>__<tool>` (Claude Code: load deferred tools first with ToolSearch
   `+<server>`). Unreal: call `list_toolsets` and add `unreal:toolset:<Name>` lines.
3. Make each probe call through the MCP and note `ok` or the error text.
4. `python ".../mcp_check.py" verify --available .kiln/mcp-tools.txt --probe <server>=<ok|error> ...`
   writes `.kiln/mcp-check.json` and closes the Phase 0 gate when `"ready": true`.
5. Not ready → fix each problem yourself (run the register command the script prints, start the
   editor or Blender, enable the addon/plugin, update a renamed tool) and re-run steps 2–4. Show
   the user only a problem with no automated fix, with its reason, and stop there: no concept,
   plan or pipeline work on a project whose MCP check fails.

Ready → run `/kiln:doctor` (Codex: the `doctor` skill) for hooks, addon versions and the repo.
If task briefs exist (`task*.md`), suggest `/kiln:concept` next to turn them into `GAME.md` and
design specs.
