---
name: doctor
description: Check that a Kiln project can really work — Blender Lab MCP and the engine's MCP (Godot AI, MCP for Unity or Unreal MCP) connected to live editors with real tool calls, not config inspection; the right project open, addon and plugin versions, Kiln hooks active, git/LFS state. Use before starting production work, after setup, or when an MCP call fails.
allowed-tools: Read, Glob, Grep, Bash, PowerShell
---

# /kiln:doctor

A configured server is not a working connection. Every check below makes a real call and
reports what came back. Report in the user's language as a table: check · result · fix.

## Checks

Checks 1–4 are the MCP check of `/kiln:setup` step 8 (`scripts/mcp_check.py required` →
visible tool names + probe calls → `verify`): run it again and report its problems; the rows
below say what each failure usually means.

1. **MCP servers registered** — the agent's list (Claude Code `claude mcp list`, Codex `codex mcp
   list`, Gemini CLI `gemini mcp list`, OpenCode `opencode mcp list`; Copilot CLI: the tool
   names this session sees, from `mcp_check.py`): `blender` plus the engine's server (`godot-ai`,
   `unity` or `unreal` per `engine=` in `manifest.md`) present and connected. Confirm their
   origin: `blender` → the Blender Lab `blender-mcp` executable; `godot-ai` → `godot-ai attach`;
   `unity` → `http://localhost:8080/mcp`; `unreal` → `http://127.0.0.1:8000/mcp`. Any other Blender
   or engine MCP server configured → warn (the project allows only these). `godot-ai` command
   differs from machine.json `godot_ai_command` → the addon's client configurator rewrote it;
   re-register setup's command and say so. Blender tools listed but not the Blender Lab names
   (`execute_blender_code`, `get_blendfile_summary_path_info`) → the PyPI `blender_mcp` of the
   same name is installed; replace it (setup §2).
2. **Blender live** — call `mcp__blender__get_blendfile_summary_path_info`. Success shows the
   open file; an error means Blender is closed or its add-on server is not started (fix: start
   Blender yourself — the GUI, `blender_exe` from the machine cache, with `--online-mode`; its
   add-on auto-starts the server, setup §7). Blender running but nothing listens on port 9876 →
   online access is off (the add-on preferences show "Online access must be enabled"): restart it
   with `--online-mode`. Then prove the Kiln review scripts work in this
   Blender version: send `mesh_qa.py` from the blender-modeling skill (read-only, starts with
   `# Kiln mesh QA`) through `execute_blender_code`; it must return its result dict (an empty
   scene reports zero objects). An exception here means a Blender API change — report it as a
   Kiln bug with the traceback.
3. **Engine live** — Godot: `mcp__godot-ai__session_manage` (list) + `editor_state`; project
   path is this folder; several sessions → name the one to use (`session_activate`). No session
   (PLUGIN_DISCONNECTED) → the editor process exited (seen after `settings_set` of
   `physics/3d/physics_engine`, and during a headless probe on the same project): start it again
   yourself (`Start-Process <godot_exe> -ArgumentList '--editor','--path','<project>'`) and repeat
   the call; engine-switching settings may restart the editor. Unity:
   `mcp__unity__manage_scene` {action: get_active} + `read_console`; project path matches. Unreal:
   `mcp__unreal__list_toolsets` (AllToolsets present?) + `call_tool` SceneTools.get_current_level.
4. **Engine addon** — Godot: `addons/godot_ai/plugin.cfg`, name "Godot AI", version, link or copy.
   Unity: MCP for Unity package pinned to a tag; asset_gen group off. Unreal: engine 5.8 (or the
   fallback server on 5.6/5.7).
   Godot game runs: `.godot/editor/project_metadata.cfg` `[game_view]` without
   `make_floating_on_play=false` (4.7 defaults to floating) or with `embed_on_play=false` → warn:
   every agent run will pop a window over the user's apps; set the embedded mode yourself while
   the editor is closed (setup §4).
   The file is written when the editor saves, so a fresh change may not show yet.
5. **Kiln hooks active** — pipe-test the guard:
   `echo '{"tool_name":"Write","tool_input":{"file_path":"<scene file>"}}' | CLAUDE_PROJECT_DIR="$PWD" python "${extensionPath}/hooks/guard.py"`
   with `scenes/x.tscn` (Godot), `Assets/x.unity` (Unity) or `Content/x.umap` (Unreal) must
   print a JSON deny. No output → manifest missing `framework=kiln` or Python not found.
   Also confirm the plugin is enabled for this project: `claude plugin list`. The other
   runtimes, each with its own payload (all checked to deny):
   - Gemini CLI: `{"tool_name":"write_file","tool_input":{"file_path":"<scene file>","content":"x"},"hook_event_name":"BeforeTool","session_id":"s","cwd":"<project>"}`
     into `guard.py --runtime gemini`; `gemini extensions list` shows kiln enabled for this
     workspace.
   - Copilot CLI: `{"toolName":"create","toolArgs":{"path":"<scene file>","file_text":"x"},"sessionId":"s","cwd":"<project>"}`
     into `guard.py --runtime copilot`; `.github/copilot/settings.json` enables `kiln@kiln`.
   - OpenCode: the Claude Code payload into `guard.py --runtime opencode` (the project's
     `.opencode/plugins/kiln.js` converts OpenCode's calls to it); that file names this Kiln
     clone (`KILN_ROOT`), and `.opencode/agents/` holds a `kiln-<role>.md` per role - otherwise
     re-run `scripts/opencode_setup.py --project .`.
   - Codex: item 9.
6. **Manifest** — `framework=kiln`, `engine`, `dimension`, `repo_access`, `mcp_only=on` (warn if
   off), `model_generators` / `audio_generators` / `video_generators` (report; `api` needs a key in
   the environment: `gen_api.py services` says which keys are set, never their values, and
   `gen_api.py balance <service>` the credit left - both free calls; a missing key → `/kiln:settings
   api`), `asset_libraries` (not `off` → `assets_api.py search polyhaven wood --kind texture
   --limit 1` answers: the libraries are reachable),
   `kind` (report `prototype` prominently: reviews are light), `user_gates`.
   Other skill packs: `claude plugin list --json` (Codex `codex plugin list`, Gemini CLI
   `gemini extensions list`) — a
   general-purpose pack enabled in this project whose model-invoked skills overlap Kiln (e.g.
   `mattpocock-skills`) → warn and offer `enabledPlugins` `false` at project scope (setup §1b item 9).
7. **Repo** — git present; LFS installed if `.gitattributes` uses it; engine caches ignored
   (`.godot/`, Unity `Library/`, Unreal `Intermediate/` `Saved/` `DerivedDataCache/`).
   `git status` lists files whose diff is line endings only (`git diff --ignore-cr-at-eol
   --name-only` shorter than `git diff --name-only`) → add `* text=auto eol=lf` to
   `.gitattributes` and `git add --renormalize .` (setup §3). Engine folders in `.gitignore`
   are anchored (`/export/`, `/Saved/`): an unanchored `Saved/` also hides a code folder of that
   name - offer the anchored line. `manifest.md` is UTF-8 (kiln-report.md lists it otherwise).
   Junctions in the project (Windows: `Get-ChildItem -Recurse -Attributes ReparsePoint
   -Directory`) → name each with its target and say how to remove one: `cmd /c rmdir <link>`,
   never `Remove-Item -Recurse` over it.
7b. **Tools** — `tools_check.py plan --project .` (tools skill): every tool the project needs is
   found (or listed for install / as a manual step); `production/tools.json` pins pass
   `tools_check.py verify`. Missing tools go to the user as one install question, never installed
   silently.
7a. **Tool environments** — sound or music roles in the backlog: `<venvs>/audio` exists and
   imports numpy, soundfile, pyloudnorm (create it yourself, setup §3). Venvs live under
   machine.json `tools_root` when it is set.
8. **Editor locks** — `.kiln/locks.json` entries older than the TTL → offer to clear.
8a. **Claude Code CLI for headless runs** — `claude --version` of the binary that launches
   autopilot runs (often the npm global, older than the IDE extension's bundled binary). Warn when
   it is older than the version whose Agent tool has `effort` (2.1.281 lacked it, 2.1.296 has it):
   per-task effort then needs `scripts/effort_agents.py`, and a manifest `agent_effort` must be
   left empty (the guard would pass an `effort` the old Agent tool does not know); recommend updating the CLI
   (`npm i -g @anthropic-ai/claude-code`, not while a run uses it) or launching with the newer
   bundled binary. Older than 2.1.182: `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` does not exist,
   and a headless run may drop background roles after 10 idle minutes - say so.
9. **Codex** (when `runtimes` includes codex) —
   - `codex plugin list` shows `kiln@kiln  installed, enabled`; `codex mcp list` has `blender`
     and the engine server; project `.codex/config.toml` enables `kiln@kiln`.
   - `.codex/agents/` holds one `kiln-<role>.toml` per Kiln role, generated by the installed
     Kiln version (header comment); otherwise re-run `${extensionPath}${/}skills${/}doctor/../../scripts/codex_agents.py`.
   - Hooks really run: ask the user to start Codex once with `KILN_HOOK_TRACE=1` in the
     environment; `.kiln/hooks.log` must then show `trace codex SessionStart`. Nothing logged →
     the hooks are not trusted yet (`/hooks`) or Python is not on PATH for `cmd.exe`/`sh`.
   - Pipe-test the Codex guard with an `apply_patch` payload:
     `{"tool_name":"apply_patch","tool_input":{"command":"*** Begin Patch\n*** Add File: <scene file>\n+x\n*** End Patch\n"}}`
     into `python guard.py --runtime codex` must print a JSON deny.
10. **Gemini CLI, Copilot CLI, OpenCode** (when `runtimes` includes them) — the pipe tests in
    item 5; Python on PATH for the hook command (`node .../py.cjs` finds python, python3 or py -3
    for Gemini; Copilot calls `python` on Windows, `python3` elsewhere; OpenCode's plugin calls
    the same). Versions Kiln was checked with: gemini-cli 0.64, Copilot CLI 1.0.97, OpenCode
    1.19.0 - an older one → say so. Gemini: Kiln's policy file in `~/.gemini/policies/kiln.toml`
    (setup offers it) or skills ask before loading. OpenCode: the `.opencode/skills/<name>` links
    point at the clone (`opencode_setup.py` re-made them after a move).

End with the single most important fix if anything failed, or "ready" if all passed.
