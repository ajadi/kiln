---
name: protocol
description: Shared working protocol for every Kiln role — task files, handoff contract, open questions, MCP-only tool policy, exclusive editor access, evidence, cleanup and language rules. Preloaded into all Kiln agents; read it when coordinating Kiln work.
user-invocable: false
---

# Kiln protocol

## Project files you will meet

| File | What it is | Who writes |
|---|---|---|
| `GAME.md` | The game: pitch, pillars, scope, non-goals, budgets, open questions | game-designer, user |
| `backlog.md` | Index of tasks by phase | orchestrator (main session) |
| `tasks/TASK-NNN.md` | One task or batch: spec, checklist, handoffs, playtests | orchestrator + every agent appends |
| `memory/pipeline.md` | Asset/animation numbers and deviations from the contracts | modeler, animator |
| `memory/registries.md` | Physics layers, input actions, groups, audio buses | whoever changes them |
| `memory/decisions.md` | Decisions with a one-line reason | anyone, append-only |
| `memory/known-issues.md` | Problems and workarounds, `[recurring]` tag when seen twice | anyone, append-only |
| `kiln-report.md` | Problems with Kiln itself (wrong denial, misfiring hook, wrong or missing instruction, failed install, script error), one row each via `pipeline.py row kiln-report.md "<date> \| <role> \| <area> \| <what happened> \| <suggestion> \| open"`; game bugs go to known-issues | anyone, append-only, the moment it happens |
| `notes_files` in `manifest.md` (default `memory/kiln_reports.md`) | Shared notes the user asked for, e.g. ideas for Kiln | anyone, append-only, next free row number |
| `memory/out-of-scope/*.md` | Ideas the user rejected, one file per concept — check before proposing; match by meaning | orchestrator, when the user rejects with a reason |
| `manifest.md` | `framework=kiln`, repo access mode, policy switches | user / setup |
| `ref/` | Reference images and sheets — read-only inputs; `ref/manifest.csv` lists source and licence of every fetched image | user; agents add fetched images with a manifest row |

Read the task file first. Read the memory files before deciding something they may
already decide. Pass file paths to other agents, not file contents.

## Task file

```markdown
# TASK-NNN: <name>
## spec
type: design | tech | art | animation | level | lighting | gameplay | ai | ui | fx | audio | music |
      narrative | cinematic | release | integration
role: <kiln agent>[, <kiln agent> ...]   (every role named here may write the task's paths)
batch: <what this worker owns in this task, e.g. "all parts of the enemy walker">
complexity: normal | high   (high: the orchestrator may raise the role's model/effort)
effort: low | medium | high | xhigh | max   (optional; the producer passes it to this task's roles)
paths: <files/dirs this task may change>
touches: humanoid, creature, mech, physics, movement, npc, damage, audio, scene-growth | none
      (what the task builds or changes; decides the consultants and acceptors in ## gates)
depends_on: TASK-NNN | none
refs: <ref/... files> | none
acceptance:
  - <observable check, in player or measurement terms>
## gates
| role | why | verdict |
|---|---|---|
| <role> | <route table or trigger> | <verdict line, or SKIP: reason (decision #)> |
## checklist
- [ ] <step> (kept current by the worker; the orchestrator reads it to know what is left)
```

Shared numbered tables (`memory/decisions.md`, the notes files) get rows through
`python <kiln>/skills/pipeline/scripts/pipeline.py row <file> "<cells after the number>"`,
which assigns the next free number.

Agents append sections; nobody rewrites another agent's section. The `role`, `paths`, `touches`
and `type` lines and the other roles' `## gates` rows are the producer's: the guard denies a role
that edits them (ask in your handoff); you fill only your own gates row.

Write zones: review and advisor roles write their own zone (the guard's denial lists it), the
shared memory files above, and the `paths:` of any open task whose `role:` line names them. To
give a role a folder for one job, the producer adds the role to that task's `role:` line and the
folder to `paths:`, not a path outside both. Acceptor probes `tests/probes/probe_qa_*` belong to
the QA roles, the playtester and the verifier: builders put their own checks in other probe
files and ask for a row change in the task file.
These rules apply to files written from the shell too (`>`, `>>`, `tee`, `cp`/`mv`, `sed -i`,
`Set-Content`/`Out-File`): a shell write is checked like a Write of that file.

## Handoff contract

When you finish (or stop), append exactly one section to the task file, then reply with the
same verdict line first:

```markdown
## handoff: <your role>
status: DONE | NEEDS_WORK | BLOCKED
changed:
  - <path> — <what changed>
evidence:
  - <measurement / screenshot description / test result that shows it works>
open: none | <what is not done>
next: <role that should act next> | orchestrator
```

Put the status line first in your final reply as well — long replies get truncated and the
first line is what survives. Write handoffs in English, terse, fields only.

## Open questions

If behaviour is undefined, requirements conflict, or an art/design choice is the user's to
make: do not guess. Add a row to the `## open questions` table in `GAME.md`
(`| OQ-NNN | question | blocks: task/track/project | ⏳ open |`), finish whatever does not
depend on it, and hand off with `status: BLOCKED` naming the OQ. Technical choices that do not
change what the player experiences are yours — record them in `memory/decisions.md`.

## Engine, dimension, policies

`manifest.md` names the project's `engine` (godot | unity | unreal), `dimension` (3d | 2d) and
policies. The engine profile (skill `kiln:engine-<engine>`) is injected when you start; it lists
the engine's MCP server, tools, file rules and conventions. Read `manifest.md` if you were not given
the profile, and load the skill yourself.

## Situational skills — load with the Skill tool only when the task needs them

Your role preloads its core skills. These others exist; load one (Skill `kiln:<name>`) when the
task touches its area, instead of guessing:

| Skill | Load when |
|---|---|
| `playtest` / `acceptance` | you must prove behaviour in the running game / measure it with probes |
| `art-2d` | `dimension=2d`, sprites, tiles, pixel art, 2D animation or 2D lighting |
| `image-to-model` | a model's reference is photos or 1–3 images instead of a full model sheet |
| `asset-libraries` | a task needs an HDRI, PBR textures, a prop or kit, sprites, UI art, icons, a font or SFX a free library (Poly Haven, ambientCG, Kenney, KayKit, game-icons, Google Fonts) may have, or the user downloaded assets by hand |
| `api-generators` | a task would use a paid generator (Meshy, ...) on the user's account (`model_generators` / `audio_generators` = `api`) |
| `animation` / `human-biomechanics` / `creature-locomotion` | motion, poses, gait, reactions |
| `rigid-body-physics` / `destruction-vfx` | bodies, joints, breaking, debris, impact effects |
| `elements-materials` | heat, cold, fire, water/wetness, electricity changing objects; freeze, melt, burn, conduct |
| `fields-forces` | gravity zones and planets, orbits, drag, wind, lift, magnets, beams, worlds larger than a few km |
| `fluids-granular` | water, waves, buoyancy, boats, flowing liquids, sand, dunes, snow cover, footprints and tracks, drifts, avalanches, sandstorms, mud, smoke |
| `soft-bodies` | cloth, ropes, cables, hair, tails, jiggle, soft and deformable objects |
| `vehicles` | cars, trucks, bikes, tracked vehicles, boats driven by the player: tyres, suspension, handling |
| `flight` | jetpacks, gliders, wingsuits, aircraft, helicopters, drones, flying creatures; fuel and gadget weight |
| `traversal` | jumps, parkour, vaulting, climbing over, hanging from ledges, crawling, openings, balance, falls, carried load, sitting, mounting and driving poses |
| `hands` | a character holds, grabs, carries, climbs or operates something: grip per object, finger poses, two-handed holds, hand IK |
| `doors` | doors, gates, hatches, curtains, car doors: clear width vs capsule and navmesh, push/pull approach and hand, physics vs animated doors, locks and breaching, AI through doors, getting in and out of vehicles |
| `weather` | rain, snow cover, wind, fog, storms, lightning, clouds, wetness, weather transitions and forecasts; anything the weather changes |
| `sky` | sun, moon and stars, day/night cycle, game clock and time compression, twilight, light and exposure across the day, sun/moon shadow handover |
| `riding` | a character rides an animal or creature: mount gaits and speeds, rider seat and sync, mounting, lean in turns, stopping, load limits, camels, elephants, big mounts |
| `lighting` / `level-design` | light setup / level layout, metrics, encounters |
| `procedural-audio` / `music` | sound effects / music |
| `tech-design` | choosing how to implement a mechanic before building it |
| `grilling` | a request leaves choices the user cares about open — ask before building |
| `implications` | a new item, wearable, kit, part, consumable, prop or ability: where it lives, both sides of every attachment, empty states, transitions, what else it touches |
| `game-ai` | enemy/NPC behaviour, perception, tactics, navigation agents |
| `controls-camera` | input mapping, remapping, dead zones, aim assist, camera rigs |
| `ui` / `accessibility` / `localization` | HUD and menus / accessibility options / translated text |
| `save-system` / `balance` / `procgen` | saving and loading / numbers and progression / generated content |
| `narrative` / `llm-npc` | story, quests, dialogue, cutscenes / LLM-driven NPC dialogue (opt-in) |
| `cinematic` | a cutscene, trailer shot or standalone clip: shot list and animatic, camera grammar and lenses, Godot AnimationPlayer + Movie Maker, Unity Timeline + Cinemachine + Recorder, Unreal Sequencer + Movie Render Queue, Blender camera markers and video output, subtitles, checks |
| `shaders` / `optimization` | writing shaders and materials / making a scene meet its budget |
| `release` | builds, CI, store packaging, the release checklist |
| `engine-godot` / `engine-unity` / `engine-unreal` | the profile was not injected |

Read a skill's `references/` files only when its SKILL.md points you to them for your case.

## Tools: editors only through their MCP servers (policy `mcp_only=on`)

- Blender work goes through the Blender Lab MCP (`mcp__blender__*`) in the Blender instance the
  user has open. Do not start Blender in background mode, do not run Python scripts that import
  `bpy` outside that instance, and do not use the `*_for_cli` tools.
- Engine editor work goes through the engine's MCP server (named in the engine profile): scenes,
  prefabs/levels, resources, project settings and, where the profile says so, scripts. Do not
  hand-write the engine's scene/resource files. Godot: `.gd`, `.tscn`, `.tres` and
  `project.godot` are created and changed only with the MCP (`script_create` / `script_patch`,
  scene and resource tools) — Edit/Write on them is denied while the editor is open, so do not
  try them first (live run: three roles lost turns that way). After changing scenes or scripts,
  run engine-godot `godot_lint.py --root .` and fix what it fails before the handoff.
- Do not talk to MCP servers through the shell (no custom clients, no HTTP to their ports).
- Headless engine runs are for checking, not building: Godot `--headless -s <script>` is allowed
  for probes and tests under `tests/` or `.kiln/tmp/` (any flags such as `--fixed-fps 60`, any
  pipe), and `--check-only` parse checks of any script; scripts elsewhere that build content are
  denied. No wrapper script is needed.
- Stop only processes you started, by PID (`taskkill /PID <pid> /T /F`, `Stop-Process -Id`,
  `kill <pid>`); record the PID when you start one. Killing by image name (`taskkill /IM`,
  `pkill`, `killall`, `Stop-Process -Name`) is denied: MCP servers, editors and other agents'
  tools share those names (g2: `taskkill /IM python.exe` killed every Python process; `/IM` on
  Godot's console launcher killed the editor it had started).
- If an MCP server is not connected, say so in a BLOCKED handoff. Do not fall back to another
  route. The `kiln` guard hook enforces these rules; a denial is a signal to change approach, not
  to find a way around it.
- AI asset generators are used only when the manifest allows them — `model_generators`
  (image-to-3D, image generation) and `audio_generators` (music and sound models), each
  `off | local | remote | api` (`remote`: on a rented GPU through the gpu-server skill only) — and
  only models whose licence the skill lists as commercial-safe. Their
  output always goes through the normal pipeline (cleanup in Blender through the MCP, gates) with
  a provenance file (tool, version, licence, seed, inputs). Agents never change these policies.

Why: models and scenes made in the real editors are visible to the user while they are being made
and stay editable by hand afterwards.

## Do it yourself — install, launch, use

You install, start and use every tool the work needs: the editors (Godot, Unity, Unreal, Blender —
the GUI app, never Blender in background mode), their MCP servers and add-ons, engine projects and
their settings, Python environments, command-line tools. Never hand the user a manual step —
"create the project in the Project Manager", "tick this setting", "open Blender", "start the
server" — when a command, a config file written before the app first reads it, or an MCP call can
do it. Hand over only what has no automated route (signing in to an account, accepting a licence,
paying, a GUI-only control with no file or API behind it) and say in one line why. Decisions stay
the user's per `user_gates`; actions are yours.

## Scenes are built visually, scripts only add behaviour (policy `scene_first=on`)

Scenes, prefabs and levels are assembled in the open editor through the MCP (open the scene
first, create and configure nodes/objects, save), so the user watches them being built and can
later open and edit them by hand without reading code. Scripts reference scene objects and add
behaviour; they do not construct meshes, shapes, lights, cameras, UI or level geometry at runtime.
Reusable objects are their own scenes/prefabs, placed in the editor or instantiated at runtime as
prepared assets. The engine profile lists the forbidden constructions and the narrow exception
marker (`kiln:runtime-node <reason>`).

## One driver per editor

There is one Blender and usually one engine editor. Two agents driving the same editor at once
corrupt each other's state. The guard hook gives the editor to the first agent that uses it and
refuses others until that agent finishes. A refused agent is put in a queue and told its place;
when the editor is free it goes to the head of the queue, and a holder that has had it longer
than `editor_lease_s` (900 s) while someone waits is told to hand over at the end of its current
step. If you are refused, do work that does not need the editor and call again later, or hand off
with `open:` naming what still needs it. `pipeline.py status` shows holders and the queue.

Files the editor watches count as editor work too: exporting a `.glb` (or textures, audio) into
the engine project while another role holds the engine editor makes that editor reimport it under
the other agent's feet. Stage such exports outside the project (`.kiln/tmp/export/`) and copy them
in when the editor is free, or hand the copy to the producer (g2: a rig export was staged this
way so a running gameplay task's node paths did not break).

## Evidence

A claim about the game needs evidence from the running game or the real editor: runtime
measurements, a screenshot you looked at, a clean log, a test result. "Files exist" and
"it should work" are not evidence. See the playtest skill.

## Scope and cleanup

- Change only what the task's `paths` and `acceptance` need. Found something else broken?
  Append it to `memory/known-issues.md` instead of fixing it on the side.
- Leave no stray files: temporary renders, probes and scratch scripts go to `.kiln/tmp/`
  (git-ignored) or are deleted. Run `git status` before your handoff.

## Language

Task files, handoffs, memory and commit messages: English, terse. Anything addressed to the
user: the language the user writes in.
