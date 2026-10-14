# {{PROJECT_NAME}} — Kiln game project

A game made with {{ENGINE}} ({{DIMENSION}}) and Blender, run as a small studio of AI agents (the
Kiln plugin). The main session is the producer: it plans, delegates to Kiln roles, checks results
and talks to the user. Roles do the hands-on work; acceptance roles judge it.

{{AGENTS_IMPORT}}

## How work flows

- The kiln `pipeline` skill runs the production pipeline phase by phase (setup → concept → style
  → tech plan → look-dev → mechanics → vertical slice → content → polish → release);
  `production/PIPELINE.md` holds the gates. `status` shows where things stand, `run` runs the next
  task, `doctor` checks that the editors are really connected. Claude Code: `/kiln:<skill>`;
  Codex: mention the skill with `$` or pick it in `/skills`.
- Kiln roles: Claude Code subagents `kiln:<role>`; Codex custom agents `kiln-<role>` (generated
  into `.codex/agents/` by the kiln plugin's `scripts/codex_agents.py`). In Kiln skill files
  `${CLAUDE_SKILL_DIR}` is the folder of that SKILL.md and `${CLAUDE_PLUGIN_ROOT}` the kiln plugin
  folder (Codex shows each skill's path).
- Before any game work, `.kiln/mcp-check.json` must say `"ready": true` (setup step 8): every
  MCP server, tool and probe the project needs is really available.
- `GAME.md` says what the game is; `backlog.md` lists tasks; each task lives in
  `tasks/TASK-NNN.md` with acceptance checks and a checklist.
- The main session writes project state (tasks, backlog, GAME.md, memory, production files) and
  delegates game content to the role that owns it (`orchestrator_writes` in `manifest.md`).

## Rules that matter most

- Editors only through their MCP servers (`mcp_only`): Blender Lab MCP for Blender, the engine's
  MCP for the engine. No background Blender, no `bpy` from the shell, no hand-written scene files.
  If a server is not connected, stop and say so.
- Scenes are built visually in the open editor (`scene_first`) so the user can watch and later
  edit them by hand. Scripts only add behaviour and reference scene objects; tunable values are
  exposed in the inspector or in data assets.
- Do it yourself: install, start and use every tool (editors, MCP servers, add-ons, engine
  projects and their settings). The user gets a manual step only when no command, config file or
  MCP call can do it, with the reason.
- One agent drives an editor at a time (the guard keeps an editor lock).
- The builder never grades its own work: acceptance roles measure, the verifier closes tasks,
  and fun is the user's call.
- A task is done when it was seen working in the running game or the real editor, with
  measurements and captures — not when files exist.

## Kiln settings

Settings live in `manifest.md`. `/kiln:settings` shows them and changes one
(`/kiln:settings user_gates=ask`); the user may also just say it in words ("ask me before deciding",
"decide for me", "this is a prototype now"). `user_gates=proxy` (default): decide the user's open
decisions with the recommended option, mark them PROXY and list them in the report for redo;
`ask`: ask and wait. `kind` and `user_gates` change only when the user asks.

## Language

Talk to the user in the language they write in. Task files, handoffs, memory and commits are in
English, short and structured.

## Commits

Commit per finished task with specific paths (`git add <paths>`, never `-A`). Framework state is
committed according to `repo_access` in `manifest.md`.
