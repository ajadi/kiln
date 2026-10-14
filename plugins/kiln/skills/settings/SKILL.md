---
name: settings
description: Show or change this project's Kiln settings (manifest.md) — kind game/prototype/assets, user_gates proxy/ask, repo_access, generators, engine policies. Use when the user runs /kiln:settings, asks what Kiln is set to here, or asks to change how Kiln works in this project ("ask me before deciding", "decide for me", "this is a prototype now", "turn on model generators").
argument-hint: "[key=value]"
---

# /kiln:settings

The settings live in `manifest.md` at the project root, one `key=value` per line; defaults are in
the hook library (`DEFAULT_POLICY`).

## Show

No arguments, or the user asks what is set: print one table — setting, current value, what it
does in one line, how to change it. Mark values that differ from the default.

| Setting | Values | What it does |
|---|---|---|
| `kind` | `game` (default) / `prototype` / `assets` | prototype: one acceptance role + verifier, ≤ 2 review rounds, every report starts with the mode; assets: no game and no engine (`engine=none`), models, sprite sheets, maps and music with `/kiln:model`, `/kiln:sprites`, `/kiln:track`, `/kiln:cinematic` |
| `user_gates` | `proxy` (default) / `ask` | proxy: the agent decides your open decisions with the recommended option, marks them PROXY and lists them for redo; ask: it asks and waits |
| `repo_access` | `private-solo` / `private-shared` / `public` | whether Kiln's memory and tasks are committed |
| `model_generators`, `audio_generators` | `off` / `local` / `remote` / `api` | which asset generators roles may run (`remote`: open-weight models on a rented GPU through the gpu-server skill only) |
| tools folder (machine, not the manifest) | a path | only when the user asks to change it: `tools_check.py root --set <folder>` (tools skill); tools already installed stay where they are |
| `llm_npc` | `off` / `local` / `api` | LLM-driven NPC talk: `local` installs Ollama (with your yes) and a model; `api` needs a key in an environment variable |
| `mcp_only`, `scene_first` | `on` / `off` | editor work only through MCP; scenes built in the editor |
| `orchestrator_writes` | `state` / `any` | what the main session may write itself |
| `state_paths` | comma-separated globs (`tools/infra/**`) | extra paths the main session counts as state under `orchestrator_writes=state` |
| `notes_files` | comma-separated paths (default `memory/kiln_reports.md`) | shared notes every role and the main session may append to; `kiln-report.md` always is one |
| `editor_lock_ttl`, `editor_lock_other_session_ttl` | seconds | when an idle editor lock frees |
| `editor_lease_s` | seconds (900) | how long a role may hold an editor while another waits in the queue before it must hand over |
| `perf_gate` | `on` (default) / `informational` / `off` | whether qa-performance blocks a task's gates (`informational`: it runs and reports, the gate is advisory) |
| `on_screen` | `anytime` (default) / `slot` | `slot`: agents never take the screen; on-screen checks queue in `production/MEASUREMENT_SLOT.md` for one batched session (playtest skill) |
| `agent_model`, `agent_effort` | empty (default) / `sonnet`, `opus`, `haiku`, `fable` (both apps), or a Codex model name such as `gpt-6.1-sol` (Codex only; Claude Code keeps each role's model) / `low` … `max` | model and effort of every delegated agent: the guard fills them into Agent calls and denies other values unless the task file names them (`model:` / `effort:`, or `complexity: high` for a stronger model). Seen working live in 0.7.0 (`tests/test_live.py`). `agent_effort` needs a Claude Code whose Agent tool has `effort` (2.1.296 has it, 2.1.281 lacked it; doctor 8a checks the headless CLI) |

## Change

`key=value` in the arguments, or the user asked in words — change exactly what they asked, in
this conversation, nothing more:

1. Edit that line of `manifest.md` (add it if missing). `kind` and `user_gates` change only on the
   user's explicit request, never on your own initiative.
2. Say what changed and what it means from now on, in one or two lines. The new value applies
   to the next session start and to every new delegation now (the session context shows it).
3. Follow-ups:
   - `kind` prototype → game: plan the promotion task (plan skill step 6) — a full re-acceptance
     of the prototype's closed work.
   - `repo_access` towards shared/public: framework state (`.claude/`, `memory/`, `tasks/`,
     `CLAUDE.md`) must leave git — show the user the `git rm --cached` list and `.gitignore`
     lines before running them.
   - `mcp_only=off` or `scene_first=off`: warn once what the guard stops protecting.
   - generators to `api`: the key goes in an environment variable, never in the project.
4. Record it in `memory/decisions.md` (date, setting, old → new, the user's words).
