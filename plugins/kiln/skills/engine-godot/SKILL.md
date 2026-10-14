---
name: engine-godot
description: Godot 4.6/4.7 engine profile for Kiln projects (engine=godot) - editor work through the Godot AI MCP, scenes built visually, project layout, scene composition, GDScript style, FPS essentials, registries, performance, tests, playtest tools, and the Godot 3 to 4 pitfalls table. Injected into Kiln agents automatically when manifest.md says engine=godot; read it before any Godot work.
user-invocable: false
---

# Godot 4 conventions

## Editor work goes through the Godot AI MCP

Scenes, resources and project settings are edited in the running editor through the
`godot-ai` MCP tools, not by writing `.tscn`/`.tres`/`project.godot` text. The editor keeps
UIDs, import data and undo history consistent; hand-written scene text silently breaks them.
Scripts are created and patched with `script_create` / `script_patch`, which validate GDScript
in the editor before saving.

Useful tools: `editor_state`, `scene_open` / `scene_save` / `scene_manage`,
`node_create` / `node_set_property` / `node_manage`, `script_create` / `script_patch` /
`script_attach`, `resource_manage`, `signal_manage`, `autoload_manage`, `input_map_manage`,
`project_manage`, `batch_execute` (many edits in one undoable step), `api_manage` (look up
the API of the editor version actually running), `logs_read`, `editor_screenshot`.

Before relying on any engine class or method, confirm it exists in the connected editor
with `api_manage` — Godot 4.x minor versions add and rename classes.

Import options (audio loop and beats, clip loop modes, Animation Library import, material
extraction, per-node `cast_shadow`) have no MCP op: change them with `scripts/import_edit.py`
and reimport — read [references/import-settings.md](references/import-settings.md).

Before working around a refused op, a false "reload failed (error 43)", `EDITOR_PLAYING`, a
dropped editor, a screenshot that looks wrong, or IK that lags a tick, read
[references/mcp-and-editor.md](references/mcp-and-editor.md): the known gaps, their routes (the
run-once `@tool` helper), and the engine facts measured in real projects.

Do not create throwaway scenes for checks such as "does the glb import". The MCP cannot close an
editor tab, so the scene stays open, and every `project_run` (autosave on) writes it back to
disk even after it is deleted. Live: two import-check scenes kept coming back as untracked files.
Check imports in a gym that already instances the asset, from the running game's tree, the
import log, or `filesystem_manage`. If a scratch scene cannot be avoided, run with
`autosave=false` and tell the producer which tab the user must close.

## Scenes are built in the editor, not in code

The user opens scenes and edits them by hand; they do not want to read code to find out what
is in a scene. So everything that exists in a scene is a node in the `.tscn`, created and
configured through the MCP in the open editor:

- Meshes, collision shapes, bodies, areas, lights, cameras, markers, navigation regions,
  particles, decals, audio players, UI controls, AnimationPlayer/AnimationTree, IK modifiers —
  all are nodes added with `node_create` / `batch_execute`, configured with
  `node_set_property` / `material_manage` / `particle_manage` / `ui_manage` etc., and saved
  with `scene_save`.
- Open the scene you work on with `scene_open` first, so the user sees it being built in the
  editor tab, and save after each logical step.
- Reusable things are their own scenes (a mech, a weapon, a streetlight, an effect) placed as
  instances in the editor. Runtime spawning instantiates those prepared scenes
  (`preload("res://...tscn").instantiate()`), it does not assemble nodes from parts.
- Scripts add behaviour only. They reach nodes through `@onready var x: Type = $Path` or
  `@export var x: Type` (assigned in the inspector), never by constructing them.
- Every value a designer may tweak is an `@export` (visible in the inspector) or lives in a
  `.tres` resource.
- Not allowed in game scripts: `MeshInstance3D.new()`, `CollisionShape3D.new()`,
  `BoxMesh.new()`, `StandardMaterial3D.new()`, `OmniLight3D.new()`, `Label.new()` and the like
  followed by `add_child()`. The Kiln guard rejects scripts with such constructions.
- Genuine exceptions (pooled debris built from prepared pieces, a procedural mesh the design
  requires, debug drawing) carry a marker comment on the same line:
  `# kiln:runtime-node <reason>` — the verifier reviews every marker.

## Layout

```
project.godot
addons/godot_ai/          # editor plugin (project-bound)
assets/models|textures|audio|fonts/
scenes/
  actors/<actor>/<actor>.tscn + .gd
  levels/<level>.tscn
  gyms/<mechanic>_gym.tscn      # isolated test scene per mechanic
  ui/
scripts/                  # shared code without a scene (components, systems, utils)
data/                     # .tres tuning resources (weapons, mechs, damage tables)
tests/                    # GDScript test suites run with test_run
```

## Scene composition

- A scene is a prefab with one responsibility. Actors are composed from child component
  nodes (HealthComponent, Hurtbox, Weapon, Locomotion) rather than deep inheritance; components
  report up with signals. Anything specific to this game is a scene; reusable tools are
  `class_name` scripts. Instancing a PackedScene is much faster than building node trees in code.
- The parent wires its children (passes Callables or node references down); avoid `get_parent()`
  and `../` paths. Design scenes to have no outside dependencies. Signals respond to behaviour,
  they do not start it.
- Autoload budget: Save, Settings, audio/music service, optionally a signals-only event bus.
  Shared data goes in Resources or `static var`, not new autoloads. Each autoload is listed with
  its purpose in `memory/decisions.md`.
- Levels are authored in the editor (instanced scenes, GridMap/CSG blockout, placed props).
  Gameplay code may spawn prepared enemy and effect scenes at runtime, but geometry, layout and
  spawn points live in `.tscn` files a designer can open and move.

## GDScript style

- Static typing everywhere: `var speed: float = 6.0`, typed arrays `Array[Mech]`,
  `Dictionary[K, V]` (4.4+), explicit return types; `:=` only when the type is visible on the
  same line. Typed code uses faster opcodes and catches errors before running. Turn on the
  `UNTYPED_DECLARATION` warning and treat it as an error.
- Script order: `@tool` → `class_name` → `extends` → signals, enums, constants → `@export` →
  vars → `@onready` → `_init`/`_ready` → virtual callbacks → public then private methods.
  Tabs; signal names in past tense.
- `@export` for anything a designer tunes; `@onready` / `%UniqueName` for child references.
- Tuning data lives in custom Resources (`WeaponData`, `MechPartData`, …) in `data/*.tres`.
  A loaded `.tres` is shared by everyone who loaded it: `duplicate()` it (or
  `resource_local_to_scene`) for per-instance state.
- Movement and physics in `_physics_process` (the physics space is only safe there); visuals
  and UI in `_process`. Turn on physics interpolation (`physics/common/physics_interpolation`,
  3D since 4.4) for smooth visuals and call `reset_physics_interpolation()` after teleports.
- Cache node references; reuse query objects where convenient. GDScript frees by reference
  counting, so occasional allocations are not GC pauses — profile before micro-optimising.
- Keep frequently compared names as `const` StringNames (`const FIRE := &"fire"`) and compare
  StringName to StringName; do not call String methods on StringNames in hot code.
- Godot 3 habits are the most common agent mistake — check `godot4-pitfalls.md` in this skill's
  folder before writing GDScript, and confirm unfamiliar APIs with `api_manage`.

## Registries (single owner of a shared fact)

Some facts are shared by many systems. Each has exactly one place where it is defined and one
memory file that mirrors it — change both together:

| Fact | Defined in | Mirrored in |
|---|---|---|
| Physics layers / masks | Project Settings → layer names (`project_manage`) | `memory/registries.md` |
| Input actions | InputMap (`input_map_manage`) | `memory/registries.md` |
| Groups used by code | code constants | `memory/registries.md` |
| Damage zones / part names | asset contract | `memory/pipeline.md` |
| Audio buses | default_bus_layout.tres | `memory/registries.md` |

A change to any registry is a risk-zone change: it needs review (see the kiln `run` skill).

## Performance budget (defaults, override in GAME.md)

- 60 fps on the target machine in the heaviest arena; physics tick 60 Hz.
- Watch with `editor_manage` performance monitors during playtests: frame time, physics
  time, draw calls, object count, video memory.
- Debris and particles are pooled and capped; detached parts sleep and are cleaned up after
  a timeout or count limit.

## FPS essentials (Godot 4.6/4.7)

- `CharacterBody3D` in `_physics_process`; `floor_constant_speed = true`,
  `floor_stop_on_slope = true`, `floor_max_angle` 45° default; raise `floor_snap_length` above
  0.1 for stairs and down-slopes (tune); `is_on_floor()` is valid only after `move_and_slide()`.
  There is **no built-in stair stepping** — step up/down with `PhysicsServer3D.body_test_motion`.
- Mouse look in `_unhandled_input` with `MOUSE_MODE_CAPTURED`, using `event.screen_relative`
  (`relative` is scaled by the stretch mode). Capture on a click in the game window, release on
  Esc and on `NOTIFICATION_APPLICATION_FOCUS_OUT`, and turn the camera only while captured —
  never capture in `_ready()`: every agent run would take the mouse from a user working in other
  apps (live run, user complaint).
- Hitscan: `PhysicsRayQueryParameters3D.create(from, to, mask, [get_rid()])` →
  `intersect_ray` inside `_physics_process`; `collide_with_areas = true` when hurtboxes are
  Area3D; under Jolt `face_index` is -1 unless enabled. Fast projectiles: ray from previous to
  current position each tick.
- Physics: Jolt is the default for **new** 3D projects since 4.6 (check the project setting).
  Jolt does not support joint softness/bias/damping; frozen kinematic bodies do not report
  contacts with static bodies unless enabled.
- Ragdolls: `PhysicalBoneSimulator3D` (4.3+) owns the PhysicalBone3D nodes;
  `physical_bones_start_simulation()` is called on it, `influence` blends partial ragdolls.
- IK and procedural bones: `SkeletonModifier3D` subclasses — `TwoBoneIK3D`, `FABRIK3D`,
  `CCDIK3D`, `JacobianIK3D`, `SplineIK3D` (4.6+), `LookAtModifier3D`, `AimModifier3D`,
  `SpringBoneSimulator3D`; custom modifiers override `_process_modification_with_delta`.
  `SkeletonIK3D` is deprecated.
- Saves: an integer `save_version` with migrations; JSON or `store_var` with
  `allow_objects = false`; never load `.tres` saves from untrusted sources (they can carry
  scripts).
- Levels: one main scene instancing a sub-scene per arena, streamed with
  `ResourceLoader.load_threaded_request`.

## 2D essentials (dimension=2d)

- Pixel art: stretch mode `viewport`, scale mode integer, default texture filter Nearest,
  `snap_2d_transforms_to_pixel` on (test with physics interpolation); imports without mipmaps.
- TileMapLayer per layer (TileMap is deprecated), Parallax2D (4.3+), Y-sort for top-down;
  `CharacterBody2D` settings in feel-numbers § 2D movement; art rules in the art-2d skill.

## Playtest tools (Godot AI MCP)

| Step | Tool |
|---|---|
| editor state / select session | `editor_state`, `session_manage`, `session_activate` |
| logs | `logs_read` (`source` editor / game) |
| run / stop | `project_run` (scene), `project_manage` (stop, settings) — runs in the editor's embedded Game view (Godot 4.4+ default `embed_on_play`), which takes the OS foreground only when the editor already has focus; do not start the game as a separate process while the user works |
| input | `game_manage` input simulation (action names) |
| runtime values, recorder, eval | `editor_manage` game eval |
| scene structure (lint) | `scene_get_hierarchy`, `node_find`, `node_get_properties`, `signal_manage` (list) |
| screenshots | `editor_screenshot` (`source` = game; `view_target`, `azimuth`, `elevation`, `fov`) |
| tests | `test_run`, `test_manage` |
| performance | `editor_manage` monitors; GPU time via `RenderingServer.viewport_get_measured_render_time_gpu` |

Recorder: copy the acceptance skill's `recorder.gd` to `res://tests/probes/recorder.gd` once.
Save a capture from game eval:
`get_viewport().get_texture().get_image().save_png(ProjectSettings.globalize_path("res://production/captures/<task>/<name>.png"))`.
Deterministic particles for captures: `use_fixed_seed`, `speed_scale = 0` +
`request_particles_process(t)`. Movie Maker mode (`--write-movie`) writes frame-perfect PNG + WAV
for sequences.

## Tests

Scene QA contracts (acceptance skill §2a): `tests/qa/<scene>_qa.gd` extends the acceptance
skill's `qa_contract.gd`, lists the scene's QA states and is run by `qa_contract.py run`
(headless Godot with `--fixed-fps 60`; windowed for frame captures). Track specs: a node path
(Node3D / Node2D global position, a Control's centre) or `Skeleton3D path:bone`.

GDScript test suites in `tests/` run inside the editor with `test_run` (GUT 9.7.x for 4.7, or
gdUnit4 6.2.x). Write them for logic that is easy to break and hard to see: damage routing and
part-detach rules, fire rate and ammo, state-machine transitions, save round-trips and
migrations, input-buffer timers. Each test must fail when its rule is broken. Feel, animation and
visuals are verified by acceptance roles in the running game, not unit tests.
