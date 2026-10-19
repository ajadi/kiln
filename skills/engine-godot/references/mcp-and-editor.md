# Godot AI MCP and the editor: gaps, traps, routes (Godot 4.7.2, Godot AI 4.3.0)

Measured in the g2 project; report rows in brackets. The MCP is third-party: Kiln documents the
route and lists the missing op as an upstream request to the MCP's authors.

## The run-once `@tool` helper (route for what no op covers)

A script under `tools/<area>/` with `@tool`, an exported `run: bool` setter and the work in it
(ConfigFile, `EditorInterface`, resource edits). Through the MCP: `script_create` it, add a scratch
node to an open scene (`node_create`), `script_attach`, `node_set_property run=true`, read the log,
delete the node, `scene_save`. Mark constructed nodes with `# kiln:runtime-node <reason>`. Keep the
script in git so the step is repeatable. Used in g2 for: theme type variations [118],
AnimationLibrary on 9 players [146], AnimationTree graphs and IK settings [135], import options
before `import_edit.py` existed [107, 145].

## Gaps (no op in 4.3.0) and the route

| Need | Route |
|---|---|
| Import options (loop, bpm, clip loop modes, Animation Library, material extraction, cast_shadow) | `scripts/import_edit.py` + `filesystem_manage reimport` — `references/import-settings.md` [4, 61, 107, 134, 145] |
| Export presets | write `export_presets.cfg` with `filesystem_manage write_text` (allowed: not a scene); the release skill's `build.py audit` checks it [5] |
| Audio bus layout, AudioStreamRandomizer stream lists | `@tool` helper that builds the resource and saves `default_bus_layout.tres` [5] |
| Editable children / overriding a node inside an instanced scene | not possible: put the choice in the import options (glb) or move the node into its own sub-scene the parent instances (lighting in a `lighting.tscn`, not inside the level) [29, 61, 132] |
| AnimationPlayer `libraries`, `autoplay` | `@tool` helper: `player.add_animation_library(name, load(path))`, `player.autoplay = ...` [146] |
| AnimationTree graph (state machine transitions, blend space points, blend tree connections, one-shot params), SkeletonModifier3D settings arrays (TwoBoneIK3D, LookAtModifier3D) | `@tool` builder script with `kiln:runtime-node` markers; `resource_manage` refuses these dynamic properties [135] |
| Edit a saved `.tres` that is in use (Environment) | `resource_manage create overwrite=true` writes the file but the editor keeps the cached instance (scan does not reload it): preview with an inline `{"__class__": ...}` override on the node, then write the file, then reopen the scene [147] |
| Array[Node] exports (Array[AudioStreamPlayer]) | `node_set_property` treats elements as resource paths and fails; set them in a `@tool` helper or `_ready` from `@export var paths: Array[NodePath]` [119] |
| LightmapGI bake, render to a file at a set resolution | no op and no script API for the bake: plan one user click (Bake Lightmaps) and say so; true-1080p captures need a windowed game run [131] |
| Close an editor tab, delete an open scene | no op: avoid scratch scenes (see SKILL.md); name leftover tabs for the user [94] |

## Traps

- **`batch_execute` rolls back every command when one fails** (undo=true): one bad
  `node_set_property` undid the earlier ones. Keep risky sets out of batches [119].
- **`script_patch` / `script_create` "GDScript reload failed with error code 43"** on a script
  with a registered `class_name` (or used by open scenes) is a false error: the validator builds a
  throw-away script with the same `class_name`, which collides with the global class. The file IS
  written and the editor reloads it. Check the real state with `godot --headless --check-only -s
  <file>` (allowed by the guard) and `logs_read`. A script using a `class_name` not yet scanned
  gives the opposite, a real "Could not find type" error: `filesystem_manage scan` first.
  Patch one file sequentially; parallel patches to one file return a wall of intermediate parse
  errors [28, 62, 116].
- **Autoloads added with `autoload_manage` are invisible to the open editor's script analysis until
  the editor restarts** ("Identifier not found: Settings"), and an autoload script with a
  `class_name` stops being patchable (error 43). Restart the editor after adding an autoload; keep
  `class_name` off autoload scripts (the autoload extends the real class) [117].
- **`EDITOR_PLAYING`**: every write tool is refused while a game runs, including one the user
  started and left idle. `editor_state` does not say who started it. If it is the agent's own
  `project_run`, stop it; if the user's, finish non-editor work and hand off with the editor work
  under `open:` — do not stop the user's run [49].
- **Editor exits** after `settings_set physics/3d/physics_engine` (Jolt switch) and once during a
  headless probe on the same project: `PLUGIN_DISCONNECTED`. Start it again yourself (minimized)
  and repeat the call [27].
- **Killing the console launcher kills the editor**: `Godot_*_console.exe` starts the editor as a
  child with the same image name. Start the editor from the plain exe and keep its PID [50].
- PowerShell: `Start-Process` of the windowed exe returns an empty ExitCode unless the Process
  object is kept (`$p = Start-Process -PassThru ...; $p.WaitForExit(); $p.ExitCode`) [65].
- `reimport` of a `.csv` translation does nothing; use `scan` [120].

## Screenshots

- `editor_screenshot source=cinematic` renders the current Camera3D even with the editor
  minimized (3D scene with a Camera3D, a light and a WorldEnvironment). Toggle `current` per camera
  with `node_set_property`. An ORTHOGONAL camera with `size = frame_px / px_per_m` gives an exact
  px/m. The image lands under the session's tool-results folder; copy it to
  `production/captures/<task>/` [124].
- It ignores frustum cameras (projection 2 with `frustum_offset`: cropped and shifted), is capped at
  the editor viewport size (1204x623 in g2) and fails in transport above ~960 px for busy images:
  reference frames and 1080p captures need a windowed game run [94, 131].
- `view_target` counts OmniLight ranges in the AABB (a stall with lights framed 10 m wide); a Player
  node as `view_target` dropped the transport twice [94].
- `source=viewport_2d` with the editor minimized returns a 2x2 black image: UI checks run headless
  (ui skill) [121].

## Engine facts that cost a round

- **glTF extensions**: 4.7.2 reads only `KHR_materials_emissive_strength`,
  `KHR_materials_pbrSpecularGlossiness` and `KHR_materials_unlit`; `KHR_materials_specular` / `ior`
  that Blender writes for a low Specular IOR Level are ignored, so hair cards keep 4 % specular and
  a grey sheen. Set `metallic_specular` on the extracted material (import options) [58].
- **IK lag**: SkeletonModifier3D in the default IDLE callback solves before an AnimationTree that
  runs in the physics callback applies the new pose — feet and hands lag one tick (2-10 cm slip).
  Set `Skeleton3D.modifier_callback_mode_process = MANUAL` and call `skeleton.advance(delta)` from
  `AnimationTree.mixer_applied`; probes read bones in `modification_processed` [136].
- **Per-instance material copies** (duplicated surface override materials) freed with the scene
  print `ERROR: Parameter "material" is null` on `reload_current_scene` (dummy renderer,
  `material_get_instance_shader_parameters`), never on `queue_free`. Drop the copies on
  `tree_exiting` (or keep them alive); scene lint: reload the scene twice headless and grep the
  log [144].
- **NavigationServer3D** answers (0,0,0) and prints an error when queried before the first async
  map sync: wait until `NavigationServer3D.map_get_iteration_id(map) > 0` [65].
- **Jolt worker pool**: "job system exceeded the maximum number of jobs" in headless runs on a
  many-core machine under load — set `threading/worker_pool/max_threads = 8` [51].
- Editor-held assets: exporting a glb into `assets/` while another role holds the editor makes that
  editor reimport it under the other agent (its node paths break mid-run). Stage engine-bound
  exports outside the project (`.kiln/tmp/export/`) and copy them in when the editor is free [129].

## Upstream requests (filed 2026-10-19 against Godot AI 4.3.0)

When a newer Godot AI closes one of these, use its op and drop the route above.

| Gap | Issue |
|---|---|
| Import options | hi-godot/godot-ai#1166 |
| Editable children (edits under an instance are dropped on save) | #1167 |
| False "reload failed, error code 43" on `class_name` scripts | #1168 |
| New autoload not seen until an editor restart | #1169 |
| `editor_screenshot` cinematic: frustum offset, size, `save_to`, light ranges in framing | #1170 |
| Close a scene tab | #1171 |
| Overwritten `.tres` stays cached; edit a saved resource | #1172 |
| Indexed properties (randomizer streams, IK settings), AnimationTree ops | #1173 |
| Attach an AnimationLibrary, read `autoplay` | #1174 |
| `Array[Node]` exports | #1175 |
| Who started a play session, idle time | #1176 |
| LightmapGI bake | #1177 |
| Audio bus layout | #1178 |
| `reimport` of a `.glb` whose `.import` changed, CSV translations | #1147 (fix in #1153) |
