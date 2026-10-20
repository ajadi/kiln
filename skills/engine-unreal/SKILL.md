---
name: engine-unreal
description: Unreal Engine 5.6-5.8 engine profile for Kiln projects (engine=unreal) - editor work through Epic's Unreal MCP (UE 5.8, toolsets via call_tool) or the community fallback, levels built by placing actors, content layout and asset naming, C++ vs Blueprint split, Enhanced Input, Character Movement, Chaos physics and destruction, animation (IK Rig, Control Rig, Motion Matching, Pose Warping), Niagara, MetaSounds, AI and navigation, rendering, tests and profiling, Blender to Unreal import rules, probes and the UE5 pitfalls table. Injected into Kiln agents automatically when manifest.md says engine=unreal.
user-invocable: false
---

# Unreal Engine 5 conventions

## Editor work goes through the Unreal MCP

**Default: Epic's Unreal MCP** (plugin `ModelContextProtocol`, UE 5.8, Experimental).

1. Enable the plugins **Unreal MCP**, **AllToolsets** and **Python Editor Script Plugin** (Edit →
   Plugins, or the `.uproject` `Plugins` array). Without AllToolsets the server has no tools.
2. Start the server: console `ModelContextProtocol.StartServer 8000`, or per user
   `Saved/Config/WindowsEditor/EditorPerProjectUserSettings.ini` →
   `[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]` `bAutoStartServer=True`,
   `ServerPortNumber=8000`, `ServerUrlPath=/mcp`.
3. Register it in Claude Code under the name **`unreal`** (the Kiln guard matches
   `mcp__unreal__*`): `claude mcp add --scope user --transport http unreal http://127.0.0.1:8000/mcp`.
   HTTP, loopback only, one editor per port. The stdio proxy
   `Engine/Plugins/Experimental/ModelContextProtocol/Extras/Proxy/Bin/Win64/unreal_mcp_proxy.exe`
   keeps the session across editor restarts; its installer replaces the entry with one named
   `unreal-mcp-proxy` - register the proxy under the name `unreal` yourself instead.
4. Optional: Epic's Claude Code plugin `unreal-engine-skills-for-claude-code@claude-plugins-official`
   (MIT; skills `unreal-mcp`, `create-toolset`, `unreal-skill`; its SessionStart hook needs Git Bash).
   Its `unreal-mcp` skill writes a `.mcp.json` entry named `unreal-mcp`: keep one entry, named
   `unreal`. Kiln's roles also accept `mcp__unreal-mcp` and `mcp__unreal-mcp-proxy` tools, and the
   guard applies the same rules to them, but two entries for one editor are two drivers.

With tool search on (default) the server lists only `list_toolsets`, `describe_toolset` and
`call_tool(toolset_name, tool_name, arguments)`. Call `describe_toolset` before the first use of a
toolset; calls run on the game thread, so never fire mutations in parallel.

| Area | Toolsets → tools (R read, M mutate) |
|---|---|
| Level / actors | SceneTools: get_current_level, find_actors, trace_world (R); add_to_scene_from_asset, add_to_scene_from_class, remove_from_scene, load_level, save_actor, level instances, merge_actors (M). ActorTools: get_actor_transform/bounds, get_components (R); set_actor_transform, add/remove_component, set_parent_component, set_label, add_tag (M) |
| Any property | ObjectTools: list/get_properties, get_class (R); set_properties, reset_properties (M) |
| Blueprints | BlueprintTools: get_graph, find_nodes, read_graph_dsl (R); create, add_variable, create_node, connect_pins, set_pin_value, write_graph_dsl, compile_blueprint (M); also UMG, StateTree, BehaviorTree, ControlRig, Sequencer |
| Assets | AssetTools (find, dependencies, duplicate, move, delete, save_assets), MaterialTools, MaterialInstanceTools, StaticMeshTools (import_file, generate_lods, generate_convex_collisions, set_nanite_enabled), SkeletalMeshTools (import_file, sockets, physics asset), TextureTools, PhysicsAsset, DataTable/DataAsset/CurveTable, Niagara, PCG, GAS |
| Play / evidence | EditorAppToolset: StartPIE, StopPIE, IsPIERunning, CaptureViewport, CaptureEditorImage; LogsToolset: GetLogEntries; AutomationTestToolset: DiscoverTests, RunTests, GetTestResults |
| Batch | ProgrammaticToolset.execute_tool_script (batches tool calls; builders only) |

Gaps in Epic's server: no console commands, no gameplay input, no performance tools, no general
Python. Close them with a project **Kiln toolset** (Python, `init_unreal.py` registers a
`unreal.ToolsetDefinition` subclass with `@toolset_registry.tool_call` methods; see Epic's
`create-toolset` skill): `exec_console` (on the PIE world), `inject_input`, `kiln_probe_start/stop/read`,
`highres_shot`. The guard lets read-only roles use these plus get/find/list/capture/log/PIE/test
tools and `stat`/`csvprofile`/`trace.`/`HighResShot` console commands.

**Fallback for UE 5.6/5.7:** ChiR24/Unreal_mcp (MIT, C++ McpAutomationBridge; PIE with input,
screenshots, logs, console, Python, profiling) registered as `unreal`. Its tools are one per area
(`inspect`, `control_editor`, `system_control`, `build_environment`, ...) with the operation in
`action`; the guard reads the action (get/list/find/inspect/screenshot/... are reads, PIE and
safe console commands are allowed to read-only roles, procedural `create_procedural_*` /
`generate_*` actions are refused). **Avoid:** hosted cloud
servers, stale or unlicensed servers, and any server whose tools generate towns/houses/mazes.

Levels, Blueprints, materials, data assets and config change only through these tools. Never write
`.uasset`, `.umap` or any `Config/*.ini` (project or plugin) as text (the guard blocks it). C++
under `Source/` may be written directly; build with Live Coding — `LiveCodingToolset.CompileLiveCoding`
as Epic's skills name it, UNVERIFIED: it is not in a UE 5.8.0 launcher editor's toolset dump, so
check `list_toolsets` first and fall back to the Live Coding shortcut (Ctrl+Alt+F11) or a full
build. Live Coding cannot add new UPROPERTY/UFUNCTION members; those need an editor restart and a
full build.

Tools that Kiln has only for Godot so far: import options go through the Unreal MCP or editor
Python (`unreal.AssetImportTask`); headless probes are `KilnProbeComponent` in automation tests;
there is no Kiln helper yet for CPU-skinned mesh fits (`GetSkinnedVertexPosition`) or for
autoplay (Gauntlet is the route). A check that needs a missing helper is NOT ASSESSED with that
reason until the first task builds the helper.

## Levels are built by placing actors (scene_first)

- World Partition + One File Per Actor for every map (each actor is a file under
  `__ExternalActors__`; diffs stay small). Data Layers and HLOD for large maps; Level Instances or
  Packed Level Actors for reusable blocks. Actor queries see only loaded WP regions — load the
  region first.
- Forbidden for static content: spawning geometry or buildings in BeginPlay, the GameMode or the
  Level Blueprint; `SpawnActor<AStaticMeshActor>`; `NewObject<U...MeshComponent/LightComponent>`
  at runtime; construction scripts that scatter instances nobody can edit; hard-coded transforms.
  Exceptions carry `// kiln:runtime-node <reason>` on the line.
- Acceptable: components declared with `CreateDefaultSubobject` in C++ constructors (visible in the
  editor), spawning prepared Blueprint classes (projectiles, debris, enemies from spawners placed in
  the level), pools, construction scripts that derive visuals from designer data (spline meshes),
  PCG generated in the editor and saved with Manual Editing (flag it in the handoff).

## Layout and naming

Everything under `Content/<Project>/`, grouped by feature: `Maps/`, `Characters/Hero`,
`Mechs/<Name>`, `Environment/<Area>`, `Weapons`, `Audio`, `VFX`, `UI`, `Input`, `Data`;
`Developers/` for scratch. PascalCase, no spaces, no Unicode. Name pattern
`Prefix_Name_Descriptor_Variant`:

| Prefix | Asset | Prefix | Asset |
|---|---|---|---|
| SM_ | static mesh | BP_ | Blueprint class |
| SK_ / SKEL_ | skeletal mesh / skeleton | ABP_ | Anim Blueprint |
| PHYS_ | physics asset | AS_ / AM_ / BS_ | sequence / montage / blend space |
| M_ / MI_ | material / instance | T_ | texture (+ `_D`, `_N`, `_ORM` suffix) |
| PM_ | physical material | NS_ / FXE_ | Niagara system / emitter |
| IA_ / IMC_ | input action / mapping context | DT_ / CT_ / DA_ | data table / curve table / data asset |
| BT_ / BB_ / EQS_ | behaviour tree / blackboard / query | WBP_ | widget |
| MS_ / SC_ | MetaSound source / sound cue | LS_ | level sequence |

C++: U/A/F/E/T/I/S type prefixes, `b` for bools, IWYU includes (never `Engine.h`), `virtual` +
`override`, `TObjectPtr<>` members, `TSoftObjectPtr`/`TSubclassOf` set in Blueprint instead of
`ConstructorHelpers::FObjectFinder` paths.

## Systems

- **C++ vs Blueprint:** systems in C++ (part health, damage model, probes), content in Blueprint
  subclasses. Tuning through `UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category=..., meta=(ClampMin, Units="cm"))`,
  per-type tuning in `UPrimaryDataAsset`, tables in DataTables, falloffs in CurveTables.
- **Input:** Enhanced Input only — IA_Move/IA_Look (Axis2D), IA_Jump, IA_Crouch, IA_Fire,
  IA_Aim, IA_Reload, IA_Melee; IMC_Default added through `UEnhancedInputLocalPlayerSubsystem`.
- **Character:** CharacterMovementComponent (capsule only; MaxStepHeight 45 cm and walkable floor
  ≈44.8° by default). Mover is Experimental. Mesh component offset −90° yaw and −half-height Z.
- **Physics (Chaos):** custom object channels (MechPart, Debris) and trace channels (Weapon) with
  presets in Project Settings → Collision; bullets are traces; CCD only for fast small bodies;
  sleep thresholds; Chaos Visual Debugger for recordings; physics may lag the game thread a frame.
- **Destruction:** Fracture Mode → Geometry Collection; per-level `damage_threshold`, Anchor
  Fields for foundations, removal on sleep. Damage that must stay local (mech parts) lives in
  gameplay code — part HP and joint HP — not in physics strain; on detach hide the part and spawn
  its debris Blueprint at the socket; on death disable the controller and ragdoll the physics asset
  so the body settles.
- **Animation:** IK Rig + IK Retargeter; Control Rig with Full Body IK for foot planting; Motion
  Matching (Pose Search schema/database; locomotion clips need root motion; reference: Game
  Animation Sample); **Pose Warping** (stride and orientation warping) ties stride to real speed.
  Anim Blueprints use thread-safe update + Property Access.
- **VFX / audio:** Niagara with pooling (`UNiagaraFunctionLibrary::SpawnSystemAtLocation`);
  MetaSounds (Source + Patch; drive with `SetFloatParameter`/`SetTriggerParameter`; the MetaSound
  Builder API authors graphs in the editor); Quartz for beat-quantised music.
- **AI / navigation:** StateTree or Behavior Tree + Blackboard + EQS, Smart Objects, Mass for
  crowds. Navigation: one Supported Agent entry per agent size (radius, height, step, slope), each
  gets its own RecastNavMesh; World-Partitioned navmesh for large maps.
- **Rendering:** Lumen (Lumen Lite in 5.8 is cheaper), Nanite for dense opaque static meshes
  (ignores LODs; WPO and masked cost more), Virtual Shadow Maps (moving/WPO geometry invalidates
  pages), MegaLights for many shadowed lights.
- **Tests:** Automation Test Framework / Automation Spec / CQTest; **Functional Tests** placed in
  test maps (visible level content); headless run:
  `UnrealEditor-Cmd.exe P.uproject -ExecCmds="Automation RunTests Project.Functional" -TestExit="Automation Test Queue Empty" -unattended -nullrhi`.

## UE5 pitfalls (LLM habits)

| Wrong | Right |
|---|---|
| `unreal.EditorLevelLibrary` | `EditorActorSubsystem`, `LevelEditorSubsystem`, `UnrealEditorSubsystem` |
| `BindAxis`/`BindAction`, `DefaultInput.ini` mappings | Enhanced Input actions + mapping contexts |
| PhysX / APEX `UDestructibleComponent` | Chaos Geometry Collections |
| Cascade, `SpawnEmitterAtLocation` | Niagara |
| Matinee, Sequence Recorder | Sequencer, Take Recorder |
| `FVector` assumed float | double in UE5; `FVector3f` where float is needed |
| missing Build.cs modules | EnhancedInput, Niagara, GeometryCollectionEngine, FieldSystemEngine, AIModule, NavigationSystem, GameplayTasks, StateTreeModule, UMG |
| `CreateDefaultSubobject` at runtime | constructor only; runtime: `NewObject` + `RegisterComponent` |
| Live Coding for new UPROPERTY/UFUNCTION | restart the editor + full build |
| `AssetImportTask.result` | `imported_object_paths` |
| Python attribute assignment | `set_editor_property()` |
| `SpawnActor` returning null silently | set `SpawnCollisionHandlingOverride` |
| reading the editor-world actor during PIE | read PIE values from probes; ObjectTools resolve the editor world |
| casting to `BP_*` everywhere | interfaces; avoid hard-reference chains |
| `SetMasterPoseComponent` | `SetLeaderPoseComponent` |

## Blender → Unreal import

- 1 Unreal unit = 1 cm. Follow Epic's Send to Unreal defaults: Blender scene **Unit Scale 1.0**;
  FBX Forward **Y**, Up **Z**, Apply Scalings "All Local", Apply Unit on, Add Leaf Bones off,
  primary bone axis Y / secondary X, smoothing Face; Unreal import Convert Scene off, Force Front X
  off. The stock FBX exporter does not scale armatures and animations cleanly — verify with a probe:
  imported bounds = Blender dimensions × 100, root bone scale 1.
- Apply rotation and scale, pivot at the origin, triangulate. Armature object named `Armature`
  (skipped by the importer) or a single `root` bone; deform bones only.
- Collision: `UBX_`/`UCP_`/`USP_`/`UCX_` + exact render mesh name (`UCX_SM_Wall_00`); convex hulls
  closed; one mesh per FBX (only the first mesh's collision imports).
- Sockets: `SOCKET_<Name>` empties for static meshes; skeletal sockets are added in Unreal
  (`SkeletalMeshTools`). LODs: `_LOD0`, `_LOD1`… or `generate_lods`; Nanite ignores LODs. An authored chain
  (asset-pipeline "LOD chain"): import LOD0, then "Import LOD Level N" per level, screen size =
  the level's `kiln_lod_screen`.
- Textures: base colour sRGB; ORM packed R=AO G=roughness B=metallic, sRGB off, compression Masks;
  normal maps BC5 — **Unreal expects DirectX normals: tick Flip Green Channel** on Blender (OpenGL)
  normals. glTF/GLB imports through Interchange.
- Import through the MCP: `StaticMeshTools.import_file`, `SkeletalMeshTools.import_file`,
  `TextureTools.import_file`.

## Playtest tools and probes

UE 5.8 lists toolsets by qualified name (`EditorToolset.EditorAppToolset`,
`EditorToolset.LogsToolset`, `AutomationTestToolset.AutomationTestToolset`,
`editor_toolset.toolsets.actor.ActorTools`, …); take the exact names from `list_toolsets`.

| Step | Tool |
|---|---|
| play / stop | EditorAppToolset `StartPIE` (in viewport), `StopPIE`, `IsPIERunning` |
| logs | LogsToolset `GetLogEntries` |
| input | Kiln toolset `inject_input` {action, x, y, z, duration_s}: `IEnhancedInputSubsystemInterface::InjectInputVectorForAction` for player 0, re-injected every frame while held |
| console | Kiln toolset `exec_console` {command} on the PIE world, allowlist `stat`, `csvprofile`, `trace.`, `HighResShot`, `profilegpu` |
| runtime values | `UKilnProbeComponent` from the acceptance skill (`scripts/unreal/KilnProbeComponent.h/.cpp`, copied to `Source/<Module>/Kiln/`, deps `RenderCore`, `RHI`, `Json`, full build): added to actors in test maps with ActorTools `add_component` {owner, component_type, name}, configured with ObjectTools `set_properties` {instance, values} (`Actors`, `Sockets`, `Values`, `SampleHz`), saved with SceneTools `save_actor`; ticks `TG_PostPhysics`, writes `Saved/Kiln/Probes/<task>/<run>_<actor>.jsonl` (cm, Z-up: positions, velocities, sockets, part HP, movement mode, `dt_ms`, `GGameThreadTime`/`GRenderThreadTime`, `RHIGetGPUFrameCycles`); started/stopped/read with Kiln toolset `kiln_probe_start` {task, run}, `kiln_probe_stop`, `kiln_probe_read` {file, tail_lines}. Read PIE values from probe output, never from ObjectTools |
| captures | EditorAppToolset `CaptureViewport` (PIE pixels; returned camera metadata is the editor's), Kiln toolset `highres_shot` {resolution} → `Saved/Screenshots/WindowsEditor`; downscale before reading |
| frame timing | probe `dt_ms`/`game_ms`/`render_ms`/`gpu_ms` → `analyze.py frames`; `exec_console` `stat unit`, `stat gpu`, `csvprofile start/stop` → `Saved/Profiling/CSV`, Unreal Insights traces; budgets are measured in a standalone `-game` run, not PIE |
| tests | AutomationTestToolset `DiscoverTests` (first), `ListTests`, `RunTests`, `GetTestStatus`, `GetTestResults`; Functional Tests in test maps |

The Kiln toolset is `${extensionPath}${/}skills${/}engine-unreal/../acceptance/scripts/unreal/kiln_toolset.py`: copy to
`Content/Python/kiln_toolset.py`, add `import kiln_toolset` + `kiln_toolset.register()` to
`Content/Python/init_unreal.py`, restart the editor (`init_unreal.py` runs at start;
`ModelContextProtocol.RefreshTools` only re-polls toolsets already registered). The toolset
registers through `unreal.ToolsetRegistry.register_toolset_class` and logs an error when the
registry is missing. The probe component is C++: an Unreal project for Kiln is a C++ project
(setup makes one; a Blueprint-only project is converted with File > New C++ Class first).

Acceptance loop: IsPIERunning → StartPIE → `kiln_probe_start` → `inject_input` script →
`kiln_probe_stop` → StopPIE → `analyze.py` (acceptance skill) on the returned files →
CaptureViewport for evidence. Write numbers with an invariant locale (`FString::SanitizeFloat` or
the JSON writer, never locale formatting).
