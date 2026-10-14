# Kiln

Version 0.7.1. A game development framework for Claude Code: Godot 4, Unity 6 or Unreal 5 plus
Blender, everything through MCP, 3D and 2D.

Kiln is a Claude Code plugin. It is active only in projects where it is installed, so its hooks do
not get in the way of other projects.

## What is inside

| Part | What it does |
|---|---|
| 31 roles (`kiln:<role>`) | 2 designers, 14 builders, 8 acceptors, 4 reviewers, 3 experts (consultants) (below) |
| 50 knowledge skills | engines (Godot / Unity / Unreal), Blender modelling, a model from 1-3 photos, assets, animation, human biomechanics, creature locomotion, rigid-body physics, destruction and effects (3D and 2D), shaders, optimisation, lighting, level design, procedural generation, 2D art and sprite sheets, UI, accessibility, localisation, controls and camera, game AI, saving, balance, narrative, cinematics and cutscenes, LLM NPCs (opt-in), procedural audio, music, release and builds, tech design, playtest, acceptance, protocol; also doors and vehicles, fields and forces, fluids and granular matter, flight, riding, hands and grips, soft bodies, elements and materials, sky and weather, traversal, the implications of a new thing; project tools (find, install, verify), rented GPU servers |
| 17 process commands | `/kiln:setup` (questionnaire), `/kiln:update` (update Kiln in a project and show what changed), `/kiln:settings`, `/kiln:doctor`, `/kiln:pipeline`, `/kiln:concept`, `/kiln:plan`, `/kiln:run`, `/kiln:autopilot`, `/kiln:stop` (finish the task and stop the autopilot), `/kiln:status`, `/kiln:gym`, `/kiln:model` (a 3D model from 1-3 images), `/kiln:sprites` (a sprite sheet or a 2D map), `/kiln:track` (a music track), `/kiln:report` (your complaint about Kiln, into `kiln-report.md`), `/kiln:retro` (session review → fixes to Kiln and the project, incl. roles never used and required roles that never ran) |
| Hooks (Python) | "MCP only", "scenes are built in the editor", write zones per role (also for shell writes), read-only acceptors in all three engines, one driver per editor with a queue and a lease, required roles per task (`touches:` + gates), git hygiene, state at session start, the engine profile in every agent, autopilot continuation, model and effort per project |
| Check scripts | meshes, contacts, back faces and gaps in Blender; silhouette measurements of characters; reference preparation and model-vs-photo silhouettes; hair card atlases; sprites (palette, mixels, silhouettes, contrast, clusters) and sprite-sheet packing; readability (contrast, colour vision, squint, saliency); UI and focus visibility; subtitles; cinematic continuity (180-degree line, 30-degree rule) and subtitle timing; 2D maps into a deduplicated tileset and Tiled map; localisation; audio (BS.1770 loudness, true peak, loop seams, stems, RT60); motion, camera and AI probes for Godot / Unity / Unreal; headless probe base, CPU skinning and autoplay for Godot; dialogue; saves; balance; procgen; performance comparison; build audit and smoke; licence registry; pipeline gates; scope contract; import options; rented GPU jobs; project tools; visual regression against baseline frames per scene; asset budgets (triangles, draw calls, bones, textures, VRAM per glb) |

## Roles

| Group | Roles | Model · effort |
|---|---|---|
| Design | game-designer, tech-designer | Opus 5.5 · medium / high |
| Art | modeler, artist-2d, animator, lighting-artist, fx-artist | Opus 5.5 · high (fx: Sonnet 5.5) |
| World and code | level-designer, gameplay-dev, ai-programmer (classic game AI) | Opus 5.5 · medium / Sonnet 5.5 · high / Opus 5.5 · high |
| UI and text | ui-designer, writer | Opus 5.5 · high / medium |
| Release | release-engineer | Sonnet 5.5 · high |
| Audio | sound-designer, composer, music-producer | Opus 5.5 · medium / high |
| Acceptance (read-only) | qa-physics, qa-locomotion, qa-feel, qa-damage, qa-ai, qa-audio, qa-performance, qa-readability | Sonnet 5.5 · high (readability: Opus) |
| Review (read-only) | playtester, autoplayer (plays the game while you are away), art-director, verifier | Sonnet 5.5 · high (playtester, autoplayer) / Opus 5.5 · high / Opus 5.5 · medium |
| Experts (write notes only) | physics-expert, anatomy-expert, creature-expert | Opus 5.5 · high |

The main session is the producer: it plans, delegates, checks and talks to the user. Model and
effort can be set per project (`agent_model` / `agent_effort` in manifest.md). A builder never
accepts its own work: acceptors measure, the verifier closes, the user decides whether it is fun.
Which consultants and acceptors a task needs follows from its `touches:` line (humanoid, creature,
physics, audio, ...) and is checked before the task closes.

Each role preloads only the core of its knowledge. Other skills are loaded with the Skill tool,
from the table in the protocol, when a task touches them. The hook adds the engine profile at agent
start, and only to roles that work with the engine.

## Installation

Once per machine:

```bash
claude plugin marketplace add ajadi/kiln             # or a path to a local copy of the repo
claude plugin install kiln-start@kiln --scope user   # the installer: one command in any folder
```

In the game folder:

1. `/kiln-start:here` connects Kiln **to this folder only** (`--scope project`): Kiln's hooks and
   rules do not reach other projects. In other projects the installer costs almost nothing
   (~70 tokens: one command, invoked only by hand).
2. Restart Claude Code in this folder: plugin commands load at session start.
3. `/kiln:setup`: a one-round questionnaire (engine, 2D/3D, game or prototype, whether to decide
   for you, repository access, generators, tools folder) with recommended answers, then the project
   files, the engine project and its MCP, the Blender check. Change the answers later with
   `/kiln:settings`.
4. `/kiln:doctor`: real calls to Blender and the engine editor.
5. `/kiln:pipeline`: production by phases: concept → style → tech plan → look-dev → mechanics →
   vertical slice → content → polish → release.

### Assets without a game

Kiln also makes single assets for people who are not making a game. `/kiln-start:here`, then
`/kiln:setup` with kind **assets** (it offers it when the folder has no engine project and you ask
for an asset): no engine, no game pipeline, Blender only.

| Command | Makes | How |
|---|---|---|
| `/kiln:model <images>` | a 3D model from 1-3 photos, concept art or sketches | modelled by hand in Blender, generated (TRELLIS.2, Pixal3D, SPAR3D, TripoSG ... when `model_generators` allows), or both; checked against every view (silhouette IoU), mesh and budget checks; `.blend` + `.glb` + previews |
| `/kiln:sprites <image>` | a sprite sheet with animations and directions, or a 2D map | pre-rendered from a Blender model with orthographic cameras, or drawn; maps cut from a reference into a deduplicated tileset + Tiled `.tmj` (`tiles.py`); PNG + Aseprite-compatible JSON |
| `/kiln:track <description>` | a song, an instrumental or a game loop | composed (MIDI + synthesis) or generated (ACE-Step 1.5, DiffRhythm when `audio_generators` allows; paid services with their terms named first); loudness, true peak, tempo, key and loop seams measured; WAV 48 kHz/24-bit + OGG or MP3 |

Everything lands in `out/<asset>/` with a README of its numbers and how it was made, and a
licence row. The same commands work inside a game project and deliver into its folders.

Problems with Kiln itself land in `kiln-report.md` in the project root: every role and the main
session add a row when the framework gets in the way (a wrong denial, a misfiring hook, a wrong or
missing instruction, a tool that fails to install), and `/kiln:report <what went wrong>` adds
yours. It can also become a GitHub issue for the Kiln authors, with your yes.

Where things stand: `production/STATUS.html` (`pipeline.py page`, regenerated after every closed task): phases, tasks and the roles they still owe, running agents and the editor queue, decisions taken for you (say "redo #N"), the last autoplay night, checks waiting for your screen.

After pulling a new Kiln: `/kiln:update` in each connected project (refreshes the installed copy,
migrates task files and the manifest, lists what changed).

The "the agent does it" principle: Kiln installs, starts and uses the tools itself (editors, MCP
servers, add-ons, the engine project and its settings, the embedded game run) and hands the user
only what cannot be automated (signing in, a licence, payment, a GUI button with no file or API
behind it), with the reason. Decisions stay the user's per `user_gates`.

Requirements: Python 3 on PATH (hooks and scripts run on it), Pillow and numpy for the check
scripts, the `blender` MCP server (Blender Lab MCP) and the engine's server: `godot-ai` (Godot AI),
`unity` (MCP for Unity) or `unreal` (Epic Unreal MCP, UE 5.8). Heavy Python environments (audio,
music, ML) live outside the project, under the machine's tools folder (`tools_root` in
`~/.kiln/machine.json`, asked once at `/kiln-start:here` and never again; change it by asking).

Tools: `/kiln:setup` looks for every tool the project needs first (registry, PATH, the tools
folder, the usual install folders) and asks once to install what is missing. Blender, uv,
git-lfs, Ollama (`llm_npc=local`), the MCP servers and their add-ons install into the tools folder
from official sources with checksums; Unity and Unreal get a short instruction; AI generators are
offered with a comparison (VRAM, licence, what they make) when `model_generators` is `local` or
`remote`. Nothing installs without your yes. Every setup run ends with a table of what Kiln
installed (version, place, size, checksum, MCP registrations, add-ons).

## Project rules (manifest.md)

| Key | Default | Meaning |
|---|---|---|
| `engine` | `godot` | `godot` / `unity` / `unreal` / `none` (asset mode) |
| `dimension` | `3d` | `3d` / `2d` |
| `mcp_only` | `on` | Blender and the engine editor only through MCP: no background Blender, no `bpy` from the shell, no headless engine scripts for editor work, no hand edits of scenes and assets |
| `scene_first` | `on` | scenes, prefabs and levels are built in the editor; code that builds scene content is refused (exception: a line with `kiln:runtime-node <reason>`) |
| `model_generators` | `off` | 3D and image generators: `off` / `local` / `remote` (a rented GPU through `gpu_job.py`) / `api`; only models with a commercially safe licence |
| `audio_generators` | `off` | music and sound generators: `off` / `local` / `remote` / `api` |
| `llm_npc` | `off` | LLM-driven NPC talk: `off` / `local` (Ollama, installed with your yes) / `api` |
| `godot_files_via_mcp` | `scenes,resources,scripts` | which Godot files may not be edited as text |
| `orchestrator_writes` | `state` | the main session writes only project state; `any` lifts the limit |
| `editor_lock_ttl` | `600` | seconds of inactivity after which an editor lock frees |
| `editor_lock_other_session_ttl` | `120` | the same for a lock left by another session (killed, hit a limit) |
| `editor_lease_s` | `900` | how long a role may hold an editor while another waits in the queue |
| `user_gates` | `proxy` | the agent decides for the user (the recommended option, marked PROXY, listed in the report: "say so and I will redo it"); `ask` is the strict mode: ask and wait. Publishing, money, deleting work and overriding the user's own decisions never happen without the user |
| `kind` | `game` | `assets`: no game, no engine: models, sprite sheets, maps and music on their own (`/kiln:model`, `/kiln:sprites`, `/kiln:track`). `prototype`: light checks (one acceptor + verifier, ≤ 2 rounds, no risk review or separate playtest). Set only by the user; every report starts with the mode; switching to `game` plans a full re-acceptance task |
| `autopilot_max_nudges` | `3` | how many times in a row the autopilot continues without progress |
| `runtimes` | `claude` | agent apps: `claude` / `codex` / `claude,codex` |
| `state_paths` | empty | extra paths (comma-separated globs) the main session writes itself under `orchestrator_writes=state` |
| `notes_files` | `memory/kiln_reports.md` | shared notes every role and the main session append to (`kiln-report.md` always is one) |
| `perf_gate` | `on` | whether qa-performance blocks closing a task: `informational` reports only, `off` does not run |
| `on_screen` | `anytime` | `slot`: agents do not take the screen; on-screen checks queue in `production/MEASUREMENT_SLOT.md` and run in one session when the user grants the time |
| `agent_model`, `agent_effort` | empty | model and effort of every agent (`sonnet`, `opus`, ... / `low` ... `max`): the hook fills them into Agent calls and refuses other values unless the task file asks for them (`model:` / `effort:`, `complexity: high`) |

## OpenAI Codex (GPT models)

The same plugin works in Codex. There is no separate framework: Codex reads the same plugin
manifest and skills and runs the same Python hooks through `hooks/codex-hooks.json`. Installation
is in `/kiln:setup`, step 6:

1. `codex plugin marketplace add <path to kiln>`, then `codex plugin add kiln@kiln`.
2. In the project's `.codex/config.toml`: `[plugins."kiln@kiln"]` and `enabled = true`.
3. Add the MCP servers with `codex mcp add` under the same names: `blender`, `godot-ai`, `unity`,
   `unreal`.
4. Run `python <kiln>/scripts/codex_agents.py` in the project root: it generates 31 roles
   `kiln-<role>` in `.codex/agents/`. It writes the model and effort from `agent_model` /
   `agent_effort` in manifest.md into every role (Codex has no Agent tool the hook could fill);
   re-run it after changing them.
5. Open a new session, go to `/hooks` and trust the Kiln hooks.

| Part | Claude Code | Codex 0.160 |
|---|---|---|
| Skills | `/kiln:<skill>` | `kiln:<skill>` through `$` or `/skills` |
| Roles | subagents `kiln:<role>` | agents `kiln-<role>`, made by the generator |
| Preloaded role skills | yes | no: the role's instructions say to read the skills first |
| Models | Opus / Sonnet / Haiku | `gpt-6.1-sol` / `gpt-6-luna` (`--model-map`) |
| MCP only, scenes in the editor, git hygiene | guard hook | the same guard; `apply_patch` edits are checked per file |
| Write zones and read-only roles | the agent's `tools` + guard | guard (Codex passes `agent_type` to subagent hooks) |
| The main session does not write game content | guard | only a rule in AGENTS.md: Codex does not tell the main thread apart |
| One driver per editor | guard | guard, by `agent_id` |

Project rules for Codex live in `AGENTS.md`, and `CLAUDE.md` just imports it, so both apps read
one source of rules.

## Developing Kiln

```bash
python -m unittest discover -s tests        # hooks (3 engines), scripts, Codex adapter
KILN_LIVE=1 python -m unittest tests.test_live -v   # real claude -p sessions (costs a few cents)
claude plugin validate plugins/kiln --strict
```

The repository is English only (code, comments, test data, skills, docs); `tests/test_english.py` fails on Cyrillic. Agents still talk to each user in that user's language.

What changed: [plugins/kiln/CHANGELOG.md](plugins/kiln/CHANGELOG.md).

## Licence

MIT ([LICENSE](LICENSE)).
