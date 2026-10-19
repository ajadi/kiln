---
name: setup
description: Set up Kiln in the current folder as a game project for Godot, Unity or Unreal (3D or 2D) with Blender — engine and dimension choice, project files (manifest, CLAUDE.md, GAME.md, backlog, memory), git ignores and LFS, project-scope plugin enable, MCP permissions, the engine project and its MCP server/addon, Blender Lab add-on check. Use when the user asks to set up / install Kiln or start a new Kiln game project here.
disable-model-invocation: true
argument-hint: "[project name]"
allowed-tools: Read, Glob, Grep, Bash, PowerShell, Write, Edit
---

# /kiln:setup

Templates: `${CLAUDE_SKILL_DIR}/../../templates/project/`. Machine config (shared by both Kiln
plugins and Codex): `~/.kiln/machine.json` (`tools_root`, the tools found or installed,
`godot_ai_command`).

Work through the steps in order — step 4 comes before step 5: `manifest.md` switches the guard
on. Do every step yourself (protocol: "Do it yourself"): install what is missing, write the files,
start the editors and their servers. A step goes to the user only when it has no automated route,
with the reason. Report to the user in their language at the end: what was created, what you
installed and started, what is still missing.

## 1. Look before writing

- `python "${CLAUDE_PLUGIN_ROOT}/scripts/folder_check.py"` first: exit 1 (the home folder, a
  folder above it, a drive root) → stop and tell the user what it printed; change nothing. A
  project install there is the user's whole setup, and `git init` would take in the profile.
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
4. **Agent apps** — Claude Code (default) / OpenAI Codex / Gemini CLI / GitHub Copilot CLI / OpenCode / several (comma-separated) → `runtimes=`.
5. **Kind** — `game` (recommended: every acceptance gate) or `prototype` (a demo or test of an
   idea: one acceptance role + verifier, ≤ 2 review rounds; the run skill) or `assets` (no game:
   3D models, sprite sheets, 2D maps or music made on their own, with `/kiln:model`,
   `/kiln:sprites`, `/kiln:track`, `/kiln:cinematic`) → `kind=`. Ask it first when the folder has no engine project
   and the user's words are about an asset, not a game ("make a 3D model from this photo", "a
   track for my video"): then recommend `assets`.
   `assets` → `engine=none`; skip questions 2 and 3 (dimension is per asset), §4 (no engine
   project), the Godot `.gdignore` step and the pipeline. Generators (8) matter here: recommend
   `local` when `tools_check.py offers` finds one that fits this GPU, else `remote` or `api`,
   else `off` (models then come by hand in Blender, music from the composer's own tools).
6. **Deciding for you** (`user_gates=`) — explain in two lines: with `proxy` (recommended) the
   agent does not stop for your decisions (scope details, the look, "is it fun"): it takes the
   recommended option, marks it PROXY and lists it in the report so you can say "redo"; with
   `ask` it asks and waits every time. Publishing, spending money, deleting your work and
   overriding a decision you made are never decided for you in either mode.
7. **Repository** — `private-solo` (recommended for a one-person private repo: Kiln's memory and
   tasks are committed) / `private-shared` / `public` (framework state stays local) → `repo_access=`.
8. **Generators** — models: `off` / `local` (open-weight, offline) / `remote` (open-weight on a
   rented GPU through the gpu-server skill) / `api` (paid services; key in an environment
   variable) → `model_generators=`; sound and music the same → `audio_generators=`; video
   models (animation reference clips) the same → `video_generators=`. `api` anywhere → the user
   puts the key in on the local key page (`/kiln:settings api`), never in the chat. Free asset
   libraries → `asset_libraries=` `attribution` (default: CC0 and CC BY, credits generated) /
   `cc0` / `sharealike` / `off`.
   Recommend `off` until a task needs one.
8a. **Tools folder** (`tools_root`) — only when machine.json has none; set earlier → no
   question, skip this item. Where Kiln installs editors, MCP servers, venvs and downloads:
   ➡️ an existing tools folder you use (found: <path>) / `~/kiln-tools` →
   `tools_check.py root --set <folder>`. The user changes it later by asking (setup or
   `/kiln:settings` runs `root --set`).

9. **Other skill packs** — list the non-Kiln plugins active here (`claude plugin list --json`:
   enabled, user or project scope; Codex: `codex plugin list`). General-purpose packs whose
   model-invoked skills overlap Kiln's process — e.g. `mattpocock-skills` (`prototype`, `tdd`,
   `code-review`, `research`, `grilling`, `domain-modeling`) — ➡️ off for this project only
   (they stay on elsewhere): `.claude/settings.json` `"enabledPlugins": {"<id>": false}`; Codex:
   `codex_config.py --file .codex/config.toml --plugin <id> --off` (§6, never by hand). The template
   already turns `mattpocock-skills` off. Packs that do not overlap (output style, editor
   helpers) stay on.

Keep `mcp_only=on` and `scene_first=on` without asking (they protect the editors and the
scene-first rule); mention them in one line.

After writing, tell the user how to change any of this later — the same text goes into the
project rules (CLAUDE.md template, "Kiln settings"): **`/kiln:settings`** shows the current values
and changes one ("/kiln:settings user_gates=ask"), or just say it in words ("ask me before
decisions", "this is a prototype now", in their own language); the agent changes `kind` and `user_gates` only when you ask.

## 2. Tools (the tools skill)

1. `python "${CLAUDE_SKILL_DIR}/../tools/scripts/tools_check.py" root`: the machine's tools folder
   (`~/.kiln/machine.json`). Not set (kiln-start normally asks) → ask now, §1b item 8a, then
   `root --set <folder>`. Set → use it, no question.
2. `tools_check.py plan --project .`: every tool this project needs is searched for first (the
   machine registry, PATH, the tools root, the usual install folders). Ask the user once, with the
   plan's `confirm` line and a table: what will be installed (size, licence, into tools_root), what
   needs them (Unity, Unreal: give the row's short instruction and wait), and, when
   `model_generators` is `local` or `remote`, the generator comparison from `tools_check.py offers`
   with your recommendation and why (tools skill §4).
3. On the yes: `tools_check.py install <tool> --yes` for each (uv first); register every MCP server
   with the `register` command it prints (Claude Code, and Codex, Gemini CLI, Copilot CLI or OpenCode when `runtimes` includes them),
   then its `after` step: the Blender add-on with `<blender> --command extension install-file -r
   user_default -e <add-on zip>`, the Godot addon linked into the project in step 4, Ollama's
   model pull. After each: `tools_check.py mark <tool> --mcp claude|codex` per registration and
   `--addon "<what, where>"` per add-on, so §9 can show it. Record the exact command you
   registered for `godot-ai` as machine.json
   `godot_ai_command`: the addon's client configurator can rewrite Claude Code's entry to its own
   `uvx` wrapper (seen: from `<tools_root>/bin/godot-ai.exe attach` to a `pythonw ... uvx --from
   godot-ai==4.3.0` wrapper in the user profile, silently); the doctor compares against it.
4. Traps the catalog already avoids, keep them in mind when fixing by hand: the Godot AI addon is
   the release asset `godot-ai-v4-plugin.zip` (`godot-ai-plugin.zip` is the Migration plugin);
   the Blender Lab MCP comes from projects.blender.org, never PyPI `blender_mcp` (a different
   server with the same name and version number); Blender's add-on needs `--online-mode`.
5. Registering MCP servers changes what the session loads: tell the user to restart the session
   and run setup again; step 1 skips what exists and comes back to step 8.

## 3. Repository

- Not a git repo → `git init` (tell the user).
- Python tool environments (audio, music, image tools) live outside the project in
  `<tools_root>/venvs/<name>` (machine.json `tools_root`); roles
  create them when first needed. A project with sound or music roles gets the audio venv now:
  `python -m venv <venvs>/audio` + `pip install numpy scipy soundfile pyloudnorm` (soundfile
  reads Ogg Vorbis; ffmpeg is then optional).
- Line endings: `python "${CLAUDE_PLUGIN_ROOT}/scripts/text_block.py" include --file
  .gitattributes --line "* text=auto eol=lf"` (first line, the user's lines kept) and, in an
  existing repo, `git add --renormalize .` once. On Windows with
  `core.autocrlf=true` a repo without it showed 1045 files as modified by CRLF alone, which made
  "check git status after every agent" useless (g2 row 24).
- `repo_access` and `kind` come from the questionnaire (§1b); keep existing values.
- `.gitignore`: `python "${CLAUDE_PLUGIN_ROOT}/scripts/text_block.py" block --file .gitignore
  --source "${CLAUDE_PLUGIN_ROOT}/templates/project/gitignore.tmpl" --marker kiln` - never append
  with a text tool (a file without a final newline turned `.env` + the block into
  `.env# --- kiln ---`, and that pattern stopped working).
- If `git lfs version` works, the same for `.gitattributes` with `gitattributes.tmpl`, then
  `git lfs install --local`; otherwise tell the user binary assets will be stored in plain
  git and how to enable LFS later.

## 4. Engine project and its MCP

`engine=none` (`kind=assets`) → skip this step; Blender is the only editor (step 7).

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
is committed like any other addon. To remove the link, remove only the link:
`cmd /c rmdir addons\godot_ai` (or `[IO.Directory]::Delete("addons\godot_ai")`), elsewhere `rm
addons/godot_ai`; never `Remove-Item -Recurse` on a folder that holds a junction - Windows
PowerShell 5.1 follows it and deletes the shared addon for every project (the guard refuses it).

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
   `MCPForUnity/package.json`), only with `python "${CLAUDE_PLUGIN_ROOT}/scripts/json_config.py"
   merge --file Packages/manifest.json --json '{"dependencies": {"<name>": "<git url>"}}'` (a
   broken manifest stops Unity at package resolution). Start its HTTP server (Window → MCP for Unity; use its auto-start
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
   with `json_config.py merge --file <name>.uproject --json '{"Plugins": [...]}'` (lists are
   joined; a broken `.uproject` does not open),
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
`backlog.md`, `memory/**` (including `memory/out-of-scope/README.md`), `.claude/settings.json` (merge with
`python "${CLAUDE_PLUGIN_ROOT}/scripts/json_config.py" merge --file .claude/settings.json --json
'<the template's object>'`: lists joined, keys added, everything else kept; an invalid file would
turn Kiln and the user's permissions off), `tasks/archive/`,
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
  `CLAUDE.md` (Claude Code too) imports it: `python "${CLAUDE_PLUGIN_ROOT}/scripts/text_block.py"
  include --file CLAUDE.md --line "@AGENTS.md"` (adds the line first, keeps the user's text; if
  `CLAUDE.md` holds an older Kiln block between the markers, remove only that block) — one copy
  of the rules, read by both.
  Keep the combined `AGENTS.md` under Codex's 32 KiB `project_doc_max_bytes`.
- Gemini CLI in `runtimes`: the block goes to `AGENTS.md` the same way, and `GEMINI.md` (the
  context file Gemini reads) imports it the same way: `text_block.py include --file GEMINI.md
  --line "@AGENTS.md"` (Gemini's import syntax; the user's text in `GEMINI.md` stays).

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
2. Enable it for this project only, only with `python "${CLAUDE_PLUGIN_ROOT}/scripts/codex_config.py"` (Python 3.11+; if it fails, stop and say so, never hand-edit)
   (never edit a Codex `config.toml` by hand or with a text tool: a value glued to the next
   table header stops Codex from starting): `--file .codex/config.toml --on`, then
   `--file .codex/config.toml --plugin mattpocock-skills@mattpocock --off` and the same for any
   other overlapping pack from §1b item 9; `--off` without `--file` for the user config if Kiln
   should stay off elsewhere. `--check` / `--repair` when Codex reports a broken config. Codex loads project config only for trusted projects — trust the
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

Gemini CLI (when `runtimes` includes gemini; gemini-cli 0.64.0 docs "Extensions", "Hooks",
"Subagents", "MCP servers"):

1. The extension, once per machine: `gemini extensions install https://github.com/ajadi/kiln
   --ref gemini-extension --consent` (the built extension: roles as subagents `kiln-<role>`,
   commands `/kiln:<name>`, the same Python hooks; `python` must be on PATH). From a local Kiln
   checkout: `python <kiln>/plugins/kiln/scripts/gemini_extension.py --out <folder>`, then
   `gemini extensions install <folder>`.
2. This project only: `gemini extensions disable kiln --scope user`, then in the project root
   `gemini extensions enable kiln --scope workspace`. On Windows the user-scope rule covers only
   folders under the user profile: a project on another drive stays enabled everywhere on that
   drive unless it is disabled there too; say so.
3. Trust the project folder when Gemini asks (an untrusted folder ignores the project's
   settings, agents and commands).
4. MCP servers, once per machine, with the same names: the `gemini` command in each tool's
   `register` (`gemini mcp add -s user godot-ai <path> attach`, `gemini mcp add -s user -t http
   unity http://localhost:8080/mcp`, ...).
5. Kiln's user policy, once per machine, with the user's yes: copy `user-policy/kiln.toml` from
   the extension folder (`~/.gemini/extensions/kiln/`) to `~/.gemini/policies/kiln.toml`. It
   lets Kiln's skills activate without a question each time (headless runs otherwise hide
   `activate_skill`) and lets Plan Mode start Kiln's read-only roles (art-director, QA,
   verifier, playtester, autoplayer). Extensions may not ship allow rules, hence the copy.
6. Restart Gemini CLI in the project; `/kiln:doctor`.

In Gemini CLI Kiln runs one role at a time: a second role started while one runs is refused
until the first returns (Gemini's hook payloads do not name the role, so two at once would be
mixed up). Headless runs (`gemini -p`, autopilot) need `--approval-mode yolo`, because headless
Gemini denies file writes and shell commands; the Kiln guard still checks every call.

GitHub Copilot CLI (when `runtimes` includes copilot; checked with Copilot CLI 1.0.97). Copilot
reads the plugin through `plugins/kiln/.github/plugin/plugin.json`: the roles as agents
`kiln:<role>` (from `copilot/agents/`, generated by `scripts/copilot_agents.py`), the skills, and
the same Python hooks (`hooks/copilot-hooks.json`, `--runtime copilot`). It also reads
`CLAUDE.md` / `AGENTS.md`, so the project rules need no extra file; the roles get them too
(`include-custom-instructions: true` in each generated agent).

1. Once per machine: `copilot plugin marketplace add ajadi/kiln`, then
   `copilot plugin install kiln@kiln`, then `copilot plugin disable kiln@kiln` (off elsewhere).
2. This project only: `python "${CLAUDE_PLUGIN_ROOT}/scripts/json_config.py" merge --file
   .github/copilot/settings.json --json '{"enabledPlugins": {"kiln@kiln": true}}'`.
3. MCP servers, once per machine, with the same names: the `copilot` command in each tool's
   `register` (`copilot mcp add godot-ai -- <path> attach`, `copilot mcp add --transport http
   unity http://localhost:8080/mcp`, ...).
4. Trust the folder when Copilot asks; restart Copilot CLI; `/kiln:doctor`.

`/kiln:autopilot` in Copilot runs in Copilot's own autopilot mode (`copilot --autopilot`, or
Shift+Tab to autopilot): without it Copilot ends the turn after 8 continuations in a row
(checked live with 1.0.98: 9 of 12 items done, then it stopped; in autopilot mode all 12).

OpenCode (when `runtimes` includes opencode; checked with OpenCode 1.19.0). Kiln runs as a
project plugin, so it is on in this project only:

1. `python <kiln>/plugins/kiln/scripts/opencode_setup.py --project .` writes
   `.opencode/plugins/kiln.js` (the same Python hooks around OpenCode's tool calls),
   `.opencode/agents/kiln-<role>.md` (the roles as subagents) and `.opencode/skills/<name>`
   (links to Kiln's skills). Re-run it after updating Kiln.
2. Project rules: the block goes to `AGENTS.md` (OpenCode reads it, and `CLAUDE.md`).
3. MCP servers: merge each server's `register` entry (`mcp_check.py required --runtime
   opencode`) into the project's `opencode.json` with `json_config.py merge --file opencode.json
   --json '{"mcp": {...}}'` (it reads JSONC; comments are not kept, the original stays as
   `opencode.json.kiln-backup` - tell the user if it had comments).
4. The autopilot continues only in a running OpenCode (TUI or `opencode serve`): a one-shot
   `opencode run` exits after its first answer.

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

## 9. What Kiln installed

End every setup run (also a re-run that installed nothing) with one table from
`tools_check.py installed`: tool, version, where (under tools_root), size, how it was checked
(sha256 / via uv), MCP registrations (Claude Code, Codex), add-ons; generators as their own rows;
the total size. Then the project-level installs of this run (the Godot AI addon linked into
`addons/`, a package added to `Packages/manifest.json`, a plugin enabled in the `.uproject`).
Tools that were found already installed are not Kiln's: list them in one line as "found". Say
how to remove a Kiln install (tools skill, "Update and remove").

`kind=assets` → no pipeline: tell the user the three commands with one example each and stop.
If task briefs exist (`task*.md`), suggest `/kiln:concept` next to turn them into `GAME.md` and
design specs.
