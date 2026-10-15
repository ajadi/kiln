# Kiln

Version 0.8.0. Kiln turns your AI coding agent into a small game studio.

You talk to one producer: your normal agent session. It plans the work and hands each piece to a
specialist (modeler, animator, level designer, sound designer, ...). Other specialists check the
result with real measurements, and you get a short report. Kiln works with Godot 4, Unity 6 or
Unreal 5, plus Blender, and drives the editors through MCP, in 3D and 2D.

You don't have to make a whole game. Kiln can also make one thing:

- a **3D model** from one to three photos or sketches;
- a **sprite sheet** or a **2D map** from a picture;
- a **music track** from a description;
- a **short video clip**, or a cutscene for your game.

New to it? [GUIDE.md](GUIDE.md) explains everything in plain words.

## Get started

### 1. Install Kiln for your agent and turn it on in your project

Each block installs Kiln once per computer and turns it on in **one project folder only**, so
your other projects stay untouched.

<details open>
<summary><b>Claude Code</b> (the full framework)</summary>

```bash
claude plugin marketplace add ajadi/kiln
claude plugin install kiln-start@kiln --scope user
```

Then, in your project folder: `/kiln-start:here`, and restart Claude Code there.
You get everything: the commands, 31 specialist roles, the safety hooks and the checks.
</details>

<details>
<summary><b>OpenAI Codex</b> (the full framework)</summary>

```bash
codex plugin marketplace add ajadi/kiln
codex plugin add kiln@kiln
```

Then, in your project: turn it on in `.codex/config.toml` and generate the roles
([Codex details](#openai-codex)).
</details>

<details>
<summary><b>Gemini CLI</b> (the full framework)</summary>

```bash
gemini extensions install https://github.com/ajadi/kiln --ref gemini-extension --consent
gemini extensions disable kiln --scope user        # off everywhere ...
gemini extensions enable kiln --scope workspace    # ... on in this project (run it there)
```

The roles become Gemini subagents (`kiln-<role>`), the commands are `/kiln:<name>`, and the same
safety hooks run. Python must be on PATH. Update with `gemini extensions update kiln`.
Checked with gemini-cli 0.64.0 against a local test server. A session with a real Gemini model
has not been run yet.
</details>

<details>
<summary><b>GitHub Copilot CLI</b> (the full framework)</summary>

```bash
copilot plugin marketplace add ajadi/kiln
copilot plugin install kiln@kiln
copilot plugin disable kiln@kiln                    # off everywhere ...
```

... and on in your project: `.github/copilot/settings.json` with
`{"enabledPlugins": {"kiln@kiln": true}}`. The roles are Copilot agents
`kiln:<role>`, and the same safety hooks run. Python must be on PATH. Checked with Copilot CLI
1.0.97 against a local test model. A session with a real Copilot model has not been run yet.
</details>

<details>
<summary><b>OpenCode</b> (the full framework)</summary>

```bash
git clone https://github.com/ajadi/kiln ~/kiln                   # once per computer
python ~/kiln/plugins/kiln/scripts/opencode_setup.py --project .  # in your project
```

Kiln runs as a plugin of this project only: the roles are subagents `kiln-<role>`, the skills are
linked in, and the same safety hooks run (Python must be on PATH). The autopilot keeps going in
a running OpenCode; a one-shot `opencode run` stops after its answer. Checked with OpenCode
1.19.0 against a local test model. A session with a real model has not been run yet.
</details>

<details>
<summary><b>Any other agent</b> (Windsurf, Amp, ...: the skills only)</summary>

```bash
npx skills@latest add ajadi/kiln -a <agent>      # windsurf, amp, cursor, ...; omit -a to choose
```

You get the knowledge and the commands as skills. There are no safety hooks and no specialist
roles, so the agent does the work itself. Update with `npx skills@latest update`. Cursor is
here too: its CLI needs a Cursor account and routes every call through Cursor's servers, so
Kiln's hooks could not be checked against a test model, and Kiln does not ship them for it.
</details>

### 2. Set up the project

Ask your agent to set up Kiln in the project: say **"set up Kiln here"**, or call the setup
command the way your agent calls commands:

| Agent | Command |
|---|---|
| Claude Code, Gemini CLI | `/kiln:setup` |
| OpenAI Codex | `$kiln:setup` (or pick it in `/skills`) |
| GitHub Copilot CLI, OpenCode | say it: "set up Kiln here" (the skill loads by its description) |

It asks one round of questions, each with a recommended answer you can accept with "yes":

- a game, a prototype or just assets;
- which engine;
- 2D or 3D;
- whether it may decide small things for you.

Then it finds the programs the project needs, offers to install what is missing (nothing is
installed without your yes), and shows what it installed.

### 3. Start

- Making a game: the **pipeline** ("make a game: ...", or `pipeline` as a command), or
  **concept** with your idea.
- One asset: **model**, **sprites**, **track** or **cinematic** with a picture or a
  description.

Say it in your own words, in any language, or use the commands below.

## Commands

Written as Claude Code and Gemini CLI call them (`/kiln:<name>`); in Codex `$kiln:<name>`; in
Copilot CLI and OpenCode name the command in words ("run the Kiln pipeline").

| You want to ... | Command |
|---|---|
| set up or check a project | `/kiln:setup`, `/kiln:doctor`, `/kiln:settings`, `/kiln:status` |
| make a game | `/kiln:pipeline` (the whole way), `/kiln:concept`, `/kiln:plan`, `/kiln:run` (next task), `/kiln:gym` (test one mechanic) |
| let it work while you are away | `/kiln:autopilot`, and `/kiln:stop` to finish the current task and stop |
| make one asset | `/kiln:model`, `/kiln:sprites`, `/kiln:track`, `/kiln:cinematic` |
| update Kiln | `/kiln:update` (this project) or `/kiln:update all` (every project on this computer) |
| complain or improve Kiln | `/kiln:report` (your complaint), `/kiln:retro` (review the session and fix what went wrong) |

## How it works

- **A studio, not one agent.** The producer plans and delegates. Builders make things; separate
  checkers measure them; a verifier closes each task. Nobody grades their own work, and whether
  it is fun is your call.
- **Real editors.** Scenes are built in the open editor through MCP, so you can watch and change
  them by hand later. Blender likewise.
- **Safety hooks.** Small Python scripts check every action:
  - editors only through MCP;
  - each role writes only its own files;
  - one agent per editor at a time;
  - no secrets in commits;
  - no task closes while a required check is missing.
- **Decides for you, openly.** By default small decisions are taken for you, marked and listed, so
  you can say "redo #3". Publishing, spending money and deleting your work always wait for you.
- **Reports its own problems.** When Kiln gets in the way, the agents write it into
  `kiln-report.md`. Your own complaints go there with `/kiln:report`.
- **Keeps itself current.** It tells you when a new version is out, and updates every project with
  `/kiln:update all`.

Where things stand: `production/STATUS.html` shows the phases, the tasks, what each still needs,
and the decisions taken for you.

<details>
<summary><b>What is inside</b></summary>

| Part | What it does |
|---|---|
| 31 roles (`kiln:<role>`) | 2 designers, 14 builders, 8 acceptors, 4 reviewers, 3 experts (consultants) (below) |
| 49 knowledge skills | engines (Godot / Unity / Unreal), Blender modelling, a model from 1-3 photos, assets, animation, human biomechanics, creature locomotion, rigid-body physics, destruction and effects (3D and 2D), shaders, optimisation, lighting, level design, procedural generation, 2D art and sprite sheets, UI, accessibility, localisation, controls and camera, game AI, saving, balance, narrative, LLM NPCs (opt-in), procedural audio, music, release and builds, tech design, playtest, acceptance, protocol; also doors and vehicles, fields and forces, fluids and granular matter, flight, riding, hands and grips, soft bodies, elements and materials, sky and weather, traversal, the implications of a new thing; project tools (find, install, verify), rented GPU servers |
| 18 process commands | `/kiln:setup`, `/kiln:update`, `/kiln:settings`, `/kiln:doctor`, `/kiln:pipeline`, `/kiln:concept`, `/kiln:plan`, `/kiln:run`, `/kiln:autopilot`, `/kiln:stop`, `/kiln:status`, `/kiln:gym`, `/kiln:model`, `/kiln:sprites`, `/kiln:track`, `/kiln:cinematic`, `/kiln:report`, `/kiln:retro` |
| Hooks (Python) | "MCP only", "scenes are built in the editor", write zones per role (also for shell writes), read-only acceptors in all three engines, one driver per editor with a queue and a lease, required roles per task (`touches:` + gates), git hygiene, state at session start, the engine profile in every agent, autopilot continuation, model and effort per project, new-version notice, problem reports |
| Check scripts | meshes, contacts, back faces and gaps in Blender; silhouettes; model-vs-photo silhouettes; hair card atlases; sprites and sprite-sheet packing; 2D maps into a deduplicated tileset and Tiled map; readability; UI and focus; subtitles; cinematic continuity (180-degree line, 30-degree rule); localisation; audio (loudness, true peak, loop seams, stems, RT60); motion, camera and AI probes for Godot / Unity / Unreal; animation that is only the whole character moved (a similarity fit per frame); pops on transitions; attacks that miss their targets; a scene QA contract (named states re-checked by one command into one report); dialogue; saves; balance; procgen; performance; build audit and smoke; licences; pipeline gates; rented GPU jobs; project tools; visual regression; frozen effects and sweeps on a state change; fidelity to a reference image in numbers (values, light pools, tones, palette, per region); asset budgets |
</details>

<details>
<summary><b>The roles and their models</b></summary>

| Group | Roles | Model tier · effort |
|---|---|---|
| Design | game-designer, tech-designer | strong · medium / high |
| Art | modeler, artist-2d, animator, lighting-artist, fx-artist | strong · high (fx: balanced) |
| World and code | level-designer, gameplay-dev, ai-programmer (classic game AI) | strong · medium / balanced · high / strong · high |
| UI and text | ui-designer, writer | strong · high / medium |
| Release | release-engineer | balanced · high |
| Audio | sound-designer, composer, music-producer | strong · medium / high |
| Acceptance (read-only) | qa-physics, qa-locomotion, qa-feel, qa-damage, qa-ai, qa-audio, qa-performance, qa-readability | balanced · high (readability: strong) |
| Review (read-only) | playtester, autoplayer (plays the game while you are away), art-director, verifier | balanced · high / strong · high / strong · medium |
| Experts (write notes only) | physics-expert, anatomy-expert, creature-expert | strong · high |

Each role file names a tier, and the app running Kiln picks the model:

| Tier | Claude Code | OpenAI Codex (`codex_agents.py --model-map`) | Gemini CLI |
|---|---|---|---|
| strong | Opus | `gpt-6.1-sol` | the session's model |
| balanced | Sonnet | `gpt-6.1-sol` | the session's model |
| fast | Haiku | `gpt-6-luna` | the session's model |

`agent_model` / `agent_effort` in manifest.md set every role at once: a tier alias (`opus`,
`sonnet`, `haiku`) works everywhere; a Codex model name applies only in Codex. Which experts and
checkers a task needs follows from its `touches:` line (humanoid, creature, physics, audio, ...).
</details>

<details>
<summary><b>Settings</b> (<code>manifest.md</code>; change them with <code>/kiln:settings</code> or in words)</summary>

| Key | Default | Meaning |
|---|---|---|
| `kind` | `game` | `game`; `prototype` (light checks: one acceptor + verifier, ≤ 2 rounds); `assets` (no game, no engine: single assets). Set only by you |
| `user_gates` | `proxy` | `proxy`: small decisions are taken for you, marked and listed; `ask`: it asks and waits |
| `engine` | `godot` | `godot` / `unity` / `unreal` / `none` (asset mode) |
| `dimension` | `3d` | `3d` / `2d` |
| `runtimes` | `claude` | the agent apps: `claude`, `codex`, `gemini`, `copilot`, `opencode`, comma-separated |
| `model_generators` | `off` | 3D and image generators: `off` / `local` / `remote` (a rented GPU) / `api`; only commercially safe licences |
| `audio_generators` | `off` | music and sound generators: `off` / `local` / `remote` / `api` |
| `llm_npc` | `off` | NPCs that talk through a language model: `off` / `local` (Ollama) / `api` |
| `problem_reports` | `on` | Kiln's own problems into `kiln-report.md` (agents, and crashed hooks by themselves); `off` stops both |
| `mcp_only` | `on` | Blender and the engine editor only through MCP |
| `scene_first` | `on` | scenes are built in the editor; code that builds scene content is refused (unless marked `kiln:runtime-node <reason>`) |
| `godot_files_via_mcp` | `scenes,resources,scripts` | which Godot files may not be edited as text |
| `orchestrator_writes` | `state` | the producer writes only project state; `any` lifts the limit |
| `state_paths` | empty | extra paths the producer may write itself |
| `notes_files` | `memory/kiln_reports.md` | shared notes everyone may append to (`kiln-report.md` always is one) |
| `perf_gate` | `on` | whether the performance check blocks a task: `informational` / `off` |
| `on_screen` | `anytime` | `slot`: agents do not take your screen; on-screen checks wait for a time you give |
| `editor_lock_ttl` | `600` | seconds of inactivity after which an editor lock frees |
| `editor_lock_other_session_ttl` | `120` | the same for a lock left by another session |
| `editor_lease_s` | `900` | how long a role may hold an editor while another waits |
| `autopilot_max_nudges` | `3` | how often in a row the autopilot continues without progress |
| `agent_model`, `agent_effort` | empty | model and effort of every role (see the roles table) |

On this computer, `~/.kiln/machine.json` holds the tools folder (`tools_root`, asked once) and
`"update_check": "off"` turns off the new-version notice.
</details>

## OpenAI Codex

The same plugin works in Codex; `/kiln:setup` step 6 does this for you:

1. `codex plugin marketplace add ajadi/kiln`, then `codex plugin add kiln@kiln`.
2. In the project's `.codex/config.toml`: `[plugins."kiln@kiln"]` and `enabled = true` (and
   `enabled = false` in your user config, so Kiln stays off elsewhere).
3. Add the MCP servers with `codex mcp add` under the same names: `blender`, `godot-ai`, `unity`,
   `unreal`.
4. Run `python <kiln>/scripts/codex_agents.py` in the project root: it generates 31 roles
   `kiln-<role>` in `.codex/agents/`; re-run it after updating Kiln or changing `agent_model`.
5. Open a new session, go to `/hooks` and trust the Kiln hooks.

<details>
<summary>What differs from Claude Code</summary>

| Part | Claude Code | Codex 0.160 | Gemini CLI 0.64 | Copilot CLI 1.0.97 |
|---|---|---|---|---|
| Commands | `/kiln:<name>` | `kiln:<skill>` through `$` or `/skills` | `/kiln:<name>` | `/<skill>` |
| Roles | subagents `kiln:<role>` | agents `kiln-<role>`, made by the generator | subagents `kiln-<role>`, built into the extension | agents `kiln:<role>` (`copilot/agents/`, generated) |
| Preloaded role skills | yes | no: the role's instructions say to read them first | no: the role activates them first | yes |
| Safety hooks | guard hook | the same guard; `apply_patch` checked per file | the same guard (`run_shell_command`, `write_file`, `replace`, MCP tools) | the same guard (`powershell`/`bash`, `create`, `edit`, `task`, MCP tools) |
| Write zones per role | the agent's `tools` + guard | guard (Codex passes `agent_type`) | guard; the role is known from the `invoke_agent` call that runs it | guard; a subagent runs in its own session, which its start names |
| The producer does not write game content | guard | a rule in AGENTS.md (Codex does not tell the main thread apart) | guard | guard |

Project rules for Codex and Gemini live in `AGENTS.md`; `CLAUDE.md` and `GEMINI.md` just import it. Copilot reads `CLAUDE.md` and `AGENTS.md` itself.
</details>

## Developing Kiln

```bash
python -m unittest discover -s tests        # hooks (3 engines), scripts, Codex, Gemini, Copilot and OpenCode adapters
KILN_LIVE=1 python -m unittest tests.test_live -v   # real claude -p sessions (costs a few cents)
claude plugin validate plugins/kiln --strict
python plugins/kiln/scripts/gemini_extension.py --out dist/gemini/kiln   # the Gemini extension
python plugins/kiln/scripts/copilot_agents.py   # after changing a role: the Copilot agents
```

What changed: [plugins/kiln/CHANGELOG.md](plugins/kiln/CHANGELOG.md).

## Licence

MIT ([LICENSE](LICENSE)).
