# Optimization per engine

Details behind the optimization skill §3–4. Every setting, node and asset below changes through the
engine MCP named in the engine profile. Numbers in brackets point to the sources at the end;
UNVERIFIED marks items not confirmed in official documentation.

## Godot 4.6/4.7

**Measure.**
- Recorder (`acceptance/scripts/recorder.gd`, `kiln-probe/2`): `frame_ms` = wall-clock time between
  rendered frames; `gpu_ms` / `cpu_render_ms` from `RenderingServer.viewport_get_measured_render_time_gpu`
  / `_cpu` + `get_frame_setup_time_cpu` after `viewport_set_measure_render_time(rid, true)`. Never use
  `Performance.TIME_PROCESS` as frame time — it is the slowest frame of the last second.
- Monitors through `editor_manage` or game eval: `TIME_PHYSICS_PROCESS`, `TIME_NAVIGATION_PROCESS`,
  `RENDER_TOTAL_DRAW_CALLS_IN_FRAME`, `RENDER_TOTAL_PRIMITIVES_IN_FRAME`, `RENDER_VIDEO_MEM_USED`,
  `OBJECT_COUNT`, `OBJECT_NODE_COUNT`, `OBJECT_ORPHAN_NODE_COUNT`, `PHYSICS_3D_ACTIVE_OBJECTS`,
  `PIPELINE_COMPILATIONS_*`.
- Debugger: Profiler (started and stopped by hand; script functions), Visual Profiler (CPU and GPU
  time per render pass), Monitors. 4.6+: tracing profilers Tracy, Perfetto and Instruments for
  script and engine API calls (setup per the 4.6 notes) [2]; 4.7 makes Perfetto the default
  tracing on Android builds [3]. External GPU tools: Nsight Graphics, Radeon GPU Profiler, PIX,
  Xcode, Arm Performance Studio [1].
- Command line: `--disable-vsync`, `--print-fps`, `--gpu-profile` (GPU tasks that took the most
  time), `--benchmark-file <absolute path>` (run-time benchmark as JSON — use for load time) [4].
- Fill-rate test: V-Sync off, compare a large and a small window (or halve `scaling_3d_scale`);
  a large fps gain means pixel-bound [5]. `Viewport.debug_draw` = OVERDRAW for overdraw.

**CPU levers.**
- Typed GDScript, cached node references, StringName constants (engine-godot skill). Fewer, fuller
  nodes; removing a node from the tree saves more than hiding or pausing it [6].
  `VisibleOnScreenEnabler2D/3D` (a node in the scene) disables a target's processing off-screen.
- Only profiled hot loops move to C# (watch GC pauses) or GDExtension C++; engine calls cost the
  same from any language [6]. `WorkerThreadPool` for parallel pure computation.
- Server APIs (RenderingServer, PhysicsServer) for tens of thousands of objects per frame: keep
  your own reference to every RID, never query servers every frame (it stalls them) [7]. Server
  objects are not scene content — a `# kiln:runtime-node <reason>` marker and a tech-design note
  are required.
- Physics: primitive shapes, then few convex shapes, trimesh last [8]; 60 ticks default; if frames
  drop, the engine runs at most `max_physics_steps_per_frame` (default 8) steps per frame — over
  that, the "spiral of death" ends at 1–2 fps [8]. Lower the tick rate only with physics
  interpolation on [6]. Jolt (default for new 3D projects since 4.6), settings under
  `physics/jolt_physics_3d/`: keep `simulation/generate_all_kinematic_contacts` off (many
  kinematic bodies overlapping complex statics waste CPU and memory); `*/use_enhanced_internal_edge_removal`
  trades ghost collisions against cost; `queries/enable_ray_cast_face_index` adds ~25% to
  ConcavePolygonShape3D memory [9].
- Navigation: collision shapes as bake source (not visual meshes), bake on a background thread,
  larger `cell_size`/`cell_height`, monotone or layers partition for simple levels; path cost
  grows with navmesh polygons, not world size; no path query every frame, agents updated across
  frames [10].

**GPU levers.**
- Fewer distinct materials, then fewer shaders [5]. Automatic instancing of identical
  MeshInstance3D (Forward+) [11]. MultiMesh: one draw for up to millions of instances, culled as
  one AABB; allocate the maximum and change `visible_instance_count`; per-instance data via
  `INSTANCE_CUSTOM` [12].
- 2D batching in every renderer since 4.4; batches break on texture or material changes, so share
  atlases [13].
- Distance: automatic mesh LOD (`rendering/mesh_lod/lod_change/threshold_pixels`, default 1.0;
  raise to 2–4 for performance, working); visibility ranges for HLOD — `visibility_parent` hides
  children when the merged parent shows; fade mode Disabled is cheapest (fades make objects
  transparent) [14]. Both work together, even on one mesh [14].
- Occlusion culling: project setting Use Occlusion Culling + OccluderInstance3D baked in the
  editor; rasterised on the CPU with Embree; largest gain on the Mobile renderer (no depth
  prepass); not worth it where little is hidden; do not move baked occluders (BVH rebuild) —
  moving occluders use primitive Occluder3D shapes [15].
- Shadows, GI, SSAO, fog and clustered limits: lighting skill table. 4.6 rewrote SSR with a
  half-resolution mode and cheaper octahedral reflection/radiance probes [2].
- Resolution: `rendering/scaling_3d/mode` Bilinear (all renderers), FSR 1.0 or FSR 2.2
  (Forward+); `scaling_3d_scale` is per axis (0.5 = ¼ of the pixels); FSR can cost more than it
  saves on very slow GPUs [16]. 4.7 adds a nearest-neighbour viewport scaling option [3].
- Baked lighting for statics (lights in Static bake mode, LightmapGI), especially on mobile [11].

**Stutter, memory, loading.** Ubershaders + pipeline precompilation (4.4+) cover pipelines known
at load; shader baker (4.5+, export option) ships compiled shaders for the drivers of the platform
the editor runs on; 2D canvas pipelines and runtime material changes are not precompiled — draw
every effect once at load (hidden instance) [17]. ObjectDB snapshots and diffs (4.6+) find leaked
objects [2]. Stream sub-scenes with `ResourceLoader.load_threaded_request`; VRAM-compressed
textures for 3D.

## Unity 6 (URP)

**Measure.**
- Profile a Development Build on the target device (Autoconnect Profiler); the editor shares the
  machine and distorts timings. Deep Profiling instruments every call — use it only to narrow a
  hotspot [18].
- `KilnProbe` frame lines: `FrameTimingManager` cpu/main/render/gpu, four frames late; GPU time is
  unavailable on some Linux, WebGL and XR targets [19].
- Bound: main thread in `Gfx.WaitForPresentOnGfxThread` while the render thread shows
  `Gfx.PresentFrame` → GPU-bound; `WaitForTargetFPS` = headroom [20]. Profile Analyzer compares two
  captures; Frame Debugger (`manage_profiler` `frame_debugger_get_events`) shows batches and why
  they break; Memory Profiler package captures and compares snapshots; mobile budget ≈ 65% of the
  frame for thermal headroom [20].

**CPU levers.** No `GetComponent`/`Find` in `Update`; Burst-compiled jobs for profiled math over
many items; incremental GC is on by default but every per-frame `GC.Alloc` still costs — pool
(`UnityEngine.Pool.ObjectPool<T>`) and pre-allocate [21]. Animator Culling Mode off-screen; Layer
Collision Matrix; primitive colliders; NavMesh baked in the editor.

**GPU levers.**
- URP draw-call order: GPU Resident Drawer (Forward+, compute shaders, not OpenGL ES, BatchRendererGroup
  Variants = Keep All, MeshRenderer only) → SRP Batcher → GPU instancing off (extra variants).
  Reuse materials; no MaterialPropertyBlock in URP; Material Variants for families; dynamic
  batching is no longer recommended [22][23][24].
- GPU occlusion culling needs the GPU Resident Drawer and Render Graph; it can cost more than it
  saves in scenes without much occlusion [25]. Baked occlusion culling for static levels.
- LOD Group (more options, more memory and CPU) or Mesh LOD (6.2+, triangles only, smaller
  footprint) [26].
- Resolution: URP Render Scale + STP upscaler (Shader Model 5 compute, not OpenGL ES, enables TAA)
  [27].

**Stutter and loading.** Prewarm shader variants at load (ShaderVariantCollection; Unity 6
GraphicsStateCollection PSO tracing — UNVERIFIED for the project's Unity version); Addressables
and `SceneManager.LoadSceneAsync` additive scenes; music as Streaming audio.

## Unreal 5.8

**Measure.** Standalone `-game` or packaged Development/Test builds; PIE is indicative only [28].
`stat unit` — frame, game thread, rendering thread (Draw), RHI thread and GPU; the largest of
Game/Draw/GPU close to Frame is the bound [29]. `stat unitgraph`, `stat gpu` (per pass, Lumen
included), `ProfileGPU`, `stat scenerendering` (draw calls), `stat initviews` (culling time and
effectiveness), `stat game` (ticks), `stat memory`, `stat streaming` [29]. `csvprofile start/stop`
writes CSVs that perf_compare reads (`--key FrameTime`; other column names as in the header).
Unreal Insights for frame-by-frame CPU/GPU/memory traces [28]. The Kiln toolset `exec_console`
allows `stat`, `csvprofile`, `trace.`, `profilegpu`.

**CPU levers.** Disable Tick where unused and raise tick intervals; Significance Manager and
Animation Budget Allocator for many actors (UNVERIFIED for 5.8 specifics); hot loops in C++, not
Blueprint; Mass for crowds; simple collision and sleeping Chaos bodies.

**GPU levers.**
- Nanite for dense opaque/masked static meshes; World Position Offset splits clusters and costs
  more; translucency is never Nanite [30]. Instanced static meshes for repeats.
- World Partition HLOD layers: Instancing (ISM with lowest LODs), Merged Mesh, Simplified Mesh;
  Build HLODs or the WorldPartitionHLODsBuilder commandlet; `wp.Runtime.HLOD 0` measures their
  effect [31][32].
- Lumen: ~4 ms (60 fps, High) / ~8 ms (30 fps, Epic) at 1080p on consoles; each scalability level
  costs about half the level above; render Lumen at 1080p and upscale with TSR rather than run
  4K natively; software ray tracing is cheaper than hardware; `sg.GlobalIlluminationQuality`,
  `sg.ReflectionQuality` 0–3 [33].
- Scalability groups `sg.ResolutionQuality`, `sg.ShadowQuality`, `sg.PostProcessQuality`,
  `sg.EffectsQuality`, `sg.ViewDistanceQuality`, `sg.FoliageQuality`, `sg.TextureQuality`;
  `r.ScreenPercentage` with TSR.

**Streaming and loading.** World Partition: one runtime grid (more hurts performance), cell size
and loading range per grid, `wp.Runtime.ToggleDrawRuntimeHash2D` to see cells,
`wp.Runtime.MaxLoadingLevelStreamingCells` caps concurrent loads, Block on Slow Streaming [32].
PSO precaching plus a bundled PSO cache for shipping (engine-unreal skill). Meshes: StaticMeshTools
`set_nanite_enabled`, `generate_lods`; SceneTools `merge_actors`.

## Sources

1. Godot docs, General optimization tips (4.7) — docs.godotengine.org/en/stable/tutorials/performance/general_optimization.html
2. Godot 4.6 release notes — godotengine.org/releases/4.6/
3. Godot 4.7 release notes — godotengine.org/releases/4.7/
4. Godot docs, Command line tutorial — docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html
5. Godot docs, GPU optimization — …/tutorials/performance/gpu_optimization.html
6. Godot docs, CPU optimization — …/tutorials/performance/cpu_optimization.html
7. Godot docs, Optimization using Servers — …/tutorials/performance/using_servers.html
8. Godot docs, Troubleshooting physics issues — …/tutorials/physics/troubleshooting_physics_issues.html
9. Godot docs, Using Jolt Physics — …/tutorials/physics/using_jolt_physics.html
10. Godot docs, Optimizing navigation performance — …/tutorials/navigation/navigation_optimizing_performance.html
11. Godot docs, Optimizing 3D performance — …/tutorials/performance/optimizing_3d_performance.html
12. Godot docs, Optimization using MultiMeshes — …/tutorials/performance/using_multimesh.html
13. Godot 4.4 release notes (2D batching in Forward+ and Mobile) — godotengine.org/releases/4.4/
14. Godot docs, Visibility ranges (HLOD) — …/tutorials/3d/visibility_ranges.html
15. Godot docs, Occlusion culling — …/tutorials/3d/occlusion_culling.html
16. Godot docs, Resolution scaling — …/tutorials/3d/resolution_scaling.html
17. Godot docs, Reducing stutter from shader (pipeline) compilations — …/tutorials/performance/pipeline_compilations.html
18. Unity Manual, Profiling on a target device — docs.unity3d.com/Manual/profiling-target-device.html
19. Unity Manual, FrameTimingManager — docs.unity3d.com/Manual/frame-timing-manager.html
20. Unity, Best practices for profiling game performance — unity.com/how-to/best-practices-for-profiling-game-performance
21. Unity Manual, Incremental garbage collection — docs.unity3d.com/Manual/performance-incremental-garbage-collection.html
22. Unity Manual, Choose a draw call optimization method — docs.unity3d.com/Manual/optimizing-draw-calls-choose-method.html
23. Unity Manual, GPU Resident Drawer in URP — docs.unity3d.com/6000.0/Documentation/Manual/urp/gpu-resident-drawer.html
24. Unity Manual, Draw call batching — docs.unity3d.com/6000.0/Documentation/Manual/DrawCallBatching.html
25. Unity Manual, GPU occlusion culling in URP — docs.unity3d.com/6000.0/Documentation/Manual/urp/gpu-culling.html
26. Unity Manual, Level of detail (6.2) — docs.unity3d.com/6000.2/Documentation/Manual/LevelOfDetail.html
27. Unity Manual, Spatial-Temporal Post-processing — docs.unity3d.com/Manual/urp/stp/stp-upscaler.html
28. Unreal Engine 5.8 docs, Introduction to performance profiling and configuration — dev.epicgames.com/documentation/en-us/unreal-engine/introduction-to-performance-profiling-and-configuration-in-unreal-engine
29. Unreal Engine 5.8 docs, Stat commands — dev.epicgames.com/documentation/en-us/unreal-engine/stat-commands-in-unreal-engine
30. Unreal Engine 5.8 docs, Nanite virtualized geometry — dev.epicgames.com/documentation/en-us/unreal-engine/nanite-virtualized-geometry-in-unreal-engine
31. Unreal Engine 5.8 docs, World Partition HLOD — dev.epicgames.com/documentation/en-us/unreal-engine/world-partition---hierarchical-level-of-detail-in-unreal-engine
32. Unreal Engine 5.8 docs, World Partition — dev.epicgames.com/documentation/en-us/unreal-engine/world-partition-in-unreal-engine
33. Unreal Engine 5.8 docs, Lumen performance guide — dev.epicgames.com/documentation/en-us/unreal-engine/lumen-performance-guide-for-unreal-engine
34. CapFrameX, Explanation of different performance metrics (time-weighted 1% low) — capframex.com/blog/post/Explanation%20of%20different%20performance%20metrics
