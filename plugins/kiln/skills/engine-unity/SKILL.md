---
name: engine-unity
description: Unity 6 engine profile for Kiln projects (engine=unity) - editor work through the MCP for Unity server, scenes and prefabs built visually, project layout, C# style and data, Input System, FPS controller, PhysX, animation and rigging, NavMesh, render pipeline, VFX, audio, tests and profiling, Blender to Unity import rules, playtest tools, probe recorder, and the Unity 6 C# pitfalls table. Injected into Kiln agents automatically when manifest.md says engine=unity.
user-invocable: false
---

# Unity 6 conventions

## Editor work goes through MCP for Unity

Default server: **CoplayDev "MCP for Unity"** (MIT, Unity 2021.3–6.x), registered in Claude Code as
`unity` (`claude mcp add --scope user --transport http unity http://localhost:8080/mcp`, HTTP lets
several clients share one editor). Pin a release tag of the package; activate only the `core`,
`testing`, `scripting_ext` and `profiling` tool groups (`manage_tools`); keep `asset_gen` off — it
contains generators and a separate Blender bridge. Never run two Unity MCP bridges on one project.
Unity's official `unity mcp` (Unity CLI + `com.unity.pipeline`) is experimental and needs a Unity
sign-in; switch to it when it is stable (richer: prefab variants/overrides, autotick, input
simulation).

| Area | MCP for Unity tools (action-based) |
|---|---|
| Scenes | `manage_scene` {create, load, save, get_hierarchy, get_active, get_loaded_scenes, set_active_scene, close_scene, scene_view_frame, validate}, `find_gameobjects` |
| GameObjects / components | `manage_gameobject` {create, modify, delete, duplicate, move_relative, look_at}, `manage_components`, `manage_physics` (collision matrix, joints), `manage_camera` (+ Cinemachine, screenshot), `manage_graphics` (volumes, baking) |
| Prefabs | `manage_prefabs` {create_from_gameobject, get_info, get_hierarchy, modify_contents, open/save/close_prefab_stage} |
| Assets | `manage_asset`, `manage_material`, `manage_packages`, `refresh_unity`, `manage_scriptable_object`, `manage_shader`, `manage_texture` |
| Scripts | `create_script`, `script_apply_edits`, `apply_text_edits`, `validate_script` (Roslyn diagnostics), `find_in_file`, `delete_script` |
| Play mode / editor | `manage_editor` {play, pause, stop, undo, redo, add_layer, add_tag}, `execute_menu_item` |
| Logs / tests / profiling | `read_console`, `run_tests` + `get_test_job`, `manage_profiler` |
| Code in editor | `execute_code` (Roslyn; not a sandbox), `unity_reflect` |

Scenes, prefabs, materials, ScriptableObject assets and project settings change only through
these tools. Never hand-edit `.unity`, `.prefab`, `.asset`, `.mat`, `.meta` or
`ProjectSettings/*` YAML. C# files may be written directly (Unity recompiles), but every change is
checked with `validate_script` / `read_console` before handoff. Do not build scenes in bulk
through `execute_code` — use the explicit scene/prefab tools so the work is visible and undoable.

Tools that Kiln has only for Godot so far: import options are changed in the editor through
MCP for Unity (`manage_asset`), never in `.meta` by hand; headless probes are `KilnProbe.cs` in
PlayMode tests; CPU-skinned mesh fits use `SkinnedMeshRenderer.BakeMesh` in a test; there is no
Kiln autoplay base yet (Input System `InputTestFixture` is the route). A check that needs a
missing helper is NOT ASSESSED with that reason until the first task builds the helper.

## Scenes and prefabs are built visually (scene_first)

- Levels split into additive scenes; every reusable thing is a prefab (nested prefabs for
  composition, prefab variants for types — a base Mech with variants per class); edit the prefab
  asset in a prefab stage rather than overriding scene instances.
- Forbidden for static content: `new GameObject`, `GameObject.CreatePrimitive`,
  `AddComponent<MeshRenderer/MeshFilter/Collider/Light/Camera>`, `new Material(Shader.Find(...))` in
  `Awake`/`Start`/`[RuntimeInitializeOnLoadMethod]`, and `[ExecuteAlways]` scene generators.
  Exceptions carry `// kiln:runtime-node <reason>` on the line.
- Acceptable: `Instantiate` from `[SerializeField]` prefab references (spawners, projectiles, VFX,
  decals), `UnityEngine.Pool.ObjectPool<T>`, debris from prefabs (pre-author the Rigidbody as
  kinematic on the part and flip `isKinematic` on detach rather than `AddComponent` at runtime),
  objects created in tests.

## Layout and code

```
Assets/_Project/{Art/{Models,Materials,Textures,Animations}, Audio, Prefabs, Scenes,
                 Data (ScriptableObjects), Scripts/{Runtime,Editor}, Settings,
                 Tests/{EditMode,PlayMode}, VFX}
```
One asmdef per Runtime/Editor/Tests; commit `.meta` files; no spaces in names; third-party content
outside `_Project`.

- One MonoBehaviour per file, file name = class name. Inspector fields `[SerializeField] private`;
  auto-properties `[field: SerializeField]` (`[SerializeField]` on a property is a compile error
  since 6.3). Tuning data in ScriptableObjects. Composition: small components + interfaces
  (`IDamageable`).
- Input System with project-wide actions (`InputSystem.actions.FindAction("Move")`); read
  presses in `Update`, not `FixedUpdate`. The legacy Input Manager is not for new projects.
- FPS player: `CharacterController` (step offset 0.1–0.4 m for a 2 m human, never > height; skin
  width ~10% of radius; min move distance 0; slope limit ~45° for FPS); `Physics.SyncTransforms()`
  or disable the controller to teleport.
- Physics (PhysX): named layers (Player, Enemy, Environment, Projectile, Debris, Ragdoll) + Layer
  Collision Matrix; fixed timestep 0.02 s (50 Hz) default; interpolation only when jitter
  appears; CCD (sweep or speculative) works only on Box/Sphere/Capsule colliders; bullets are
  raycasts; move rigid bodies with `MovePosition`/forces, not `transform`.
- Animation: Animator with blend trees (1D speed, 2D Freeform Directional for strafes); hash
  parameter names; Humanoid avatar for the hero, Generic for mechs; with "Optimize Game Objects"
  list detachable parts under Extra Transforms to Expose; Animation Rigging (Animator + RigBuilder
  + Rig) — TwoBoneIK for hands on the weapon and legs, Multi-Aim for head/spine.
- Navigation: AI Navigation package — one `NavMeshSurface` per agent type, `NavMeshModifier`,
  `NavMeshLink`; bake in the editor.
- Render pipeline: **URP** by default (Built-in is deprecated in 6.5); HDRP only when the look
  needs volumetric fog/clouds, SSR, SSGI. Adaptive Probe Volumes + baked GI; static geometry
  "Contribute GI". URP Lit uses smoothness (inverse of roughness).
- VFX: VFX Graph (GPU, millions of particles) for sparks and smoke; Particle System (CPU, real
  collisions) for casings and debris.
- Audio: AudioMixer groups (Weapons, SFX, Music, UI, Ambience) with exposed parameters, snapshots
  via `TransitionTo`, `spatialBlend = 1` for 3D. FMOD/Wwise are options for complex adaptive music.
- Tests: Unity Test Framework — EditMode for logic and data validation, PlayMode (`[UnityTest]`)
  for physics and scenes. Profiling: Profiler, Frame Debugger, Profile Analyzer, Memory Profiler,
  Project Auditor, `ProfilerRecorder`; measure performance targets in a Development player.

## 2D (dimension=2d)

URP with the 2D Renderer (2D lights, shadow casters), Pixel Perfect Camera for pixel art,
Tilemap + Rule Tiles, Sprite Atlas, 2D Animation + PSD Importer for cut-out characters;
`Rigidbody2D`/`Collider2D` (Box2D) — never mix with 3D physics. Pixel-art sprites: Filter Point,
Compression None, one Pixels Per Unit for the whole project. Art rules in the art-2d skill.

## Unity 6 pitfalls (LLM habits)

| Wrong | Right |
|---|---|
| `FindObjectOfType` / `FindObjectsOfType` | `FindFirstObjectByType` / `FindAnyObjectByType` / `FindObjectsByType(FindObjectsSortMode.None)` |
| `Rigidbody.velocity`, `drag`, `angularDrag` | `linearVelocity`, `linearDamping`, `angularDamping` |
| `PhysicMaterial` | `PhysicsMaterial` |
| `Rigidbody.SetDensity` | set `mass` |
| `GameObject.rigidbody`, `.camera`, `Component.light` shortcuts | `GetComponent<T>()` (removed in 6.5) |
| `[SerializeField]` on a property | `[field: SerializeField]` |
| `int` instance IDs, `Scene.handle` as int | `EntityId`, `SceneHandle` (6.5) |
| URP `Execute`/`SetupRenderPasses`, Compatibility Mode | Render Graph `RecordRenderGraph` |
| `Shader.Find("Standard")`, `_MainTex`, `_Color` | `Universal Render Pipeline/Lit`, `_BaseMap`, `_BaseColor` |
| roughness into URP smoothness | invert: smoothness = 1 − roughness |
| `Input.GetAxis` with the Input System active | Input System actions |
| mouse delta × `Time.deltaTime` | delta is already per frame |
| `WasPressedThisFrame` in `FixedUpdate` | read in `Update` |
| moving a Rigidbody via `transform` | `MovePosition` / forces; `Physics.SyncTransforms` after direct transform changes |
| layer index where a mask is expected | `1 << layer` / `LayerMask.GetMask` |
| legacy Navigation window / `NavMeshBuilder` | `NavMeshSurface` |
| `LightShadowCasterMode.NonLightmappedOnly/Everything` | `ShadowMask` / `DistanceShadowMask` (6.4) |
| `VisualElement.transform` | `style.translate/rotate/scale` (6.2) |
| `async void` without cancellation | `Awaitable` + `destroyCancellationToken`; never await the same Awaitable twice |
| `Object.Destroy` teardown assumptions | 6.4 calls `OnDisable` across the hierarchy |

## Blender → Unity import

- **FBX** by default (rigs, Humanoid, animation); glTFast (`com.unity.cloud.gltfast`) is fine for
  static props. Do not import `.blend` directly.
- Unity is left-handed, Y-up, +Z forward, 1 unit = 1 m. Apply rotation and scale in Blender;
  export FBX with Apply Scalings "FBX All", Forward −Z, Up Y; prefer Unity's **Bake Axis
  Conversion** import option over Blender's experimental Apply Transform for rigs; check a test
  asset faces +Z. No 100× scale, no −90° X.
- Collision: Unity has no collider naming convention (`UCX_` does nothing); build compound
  primitive colliders on the prefab (the only shapes CCD supports), or `*_COL` child meshes turned
  into convex MeshColliders by a project `AssetPostprocessor`; non-kinematic bodies need convex
  mesh colliders.
- LOD: `Name_LOD0`, `Name_LOD1`… under one parent → automatic LODGroup.
- Materials: URP Lit smoothness in the Metallic map's alpha (invert Blender roughness); HDRP Mask
  Map R metallic, G AO, B detail mask, A smoothness; data maps sRGB off. Normal maps are OpenGL
  (+Y) like Blender — do not flip; Texture Type = Normal map.
- Rigs: hero Humanoid (Avatar from this model, T-pose fixed in Configure); mechs Generic; Blender
  export with Add Leaf Bones off, deform bones only, one clip per action; 4 bone influences.

## Playtest tools and probes

| Step | Tool |
|---|---|
| play / stop | `manage_editor` {action: play / stop} |
| logs | `read_console` {action: get, types: [error, warning], count} |
| input | Input System device state through `execute_code` (fully qualified: `UnityEngine.InputSystem.InputSystem.QueueStateEvent(UnityEngine.InputSystem.Keyboard.current, new UnityEngine.InputSystem.LowLevel.KeyboardState(UnityEngine.InputSystem.Key.W))`, applied next update, held until the next state event) or an injectable input seam (`IPlayerInput`); tests use `InputTestFixture` (override `Setup`/`TearDown`) |
| runtime values / recorder | `KilnProbe` from the acceptance skill (`scripts/unity/KilnProbe.cs`): install with `create_script` {path: `Assets/_Project/Scripts/Runtime/Kiln/KilnProbe.cs`, contents}; add to a `_KilnProbe` object in the test scene (`manage_gameobject` create, `manage_components` add, `manage_scene` save) or `KilnProbe.Attach()` in Play mode; FixedUpdate or LateUpdate samples → `production/captures/<task>/probe_<run>.jsonl`. The class compiles only under `UNITY_EDITOR \|\| DEVELOPMENT_BUILD`; gameplay components may implement the always-compiled `IKilnProbeSource` |
| driving the probe | `execute_code` {action: execute, code} — a method body that must `return`; only `UnityEngine`/`UnityEditor` are imported, so write `Kiln.Probes.KilnProbe.Find()`; `StartRecording(task, run, samples)`, `Done`, `StopRecording()` |
| captures | `manage_camera` {action: screenshot, capture_source: game_view, include_image, screenshot_file_name}, or `ScreenCapture.CaptureScreenshot("production/captures/...png")` (path relative to the project in the editor) |
| frame timing | `KilnProbe` frame lines (`FrameTimingManager` cpu/main/render/gpu, four frames late, always on in the editor and Development players), `manage_profiler` {action: get_frame_timing} for one snapshot, `ProfilerRecorder` |
| tests | `run_tests` {mode: EditMode/PlayMode} + `get_test_job` |

Set Play Mode Input Behavior to "All Device Input Always Goes To Game View" for agent sessions;
the editor may stop ticking while unfocused — enable Run In Background. Write numbers with
`CultureInfo.InvariantCulture` (a Russian-locale Windows writes `1,5`). Read-only roles mark their
`execute_code` probes with `// kiln:probe`; the guard refuses other code from them. `execute_code`
is in the `scripting_ext` tool group; `run_tests`/`get_test_job` in `testing`; `manage_profiler`
in `profiling`.
