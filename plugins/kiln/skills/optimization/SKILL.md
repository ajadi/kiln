---
name: optimization
description: Making a scene meet its frame, memory and load-time budget — profile first (measure, one hypothesis, one change, re-measure with perf_compare.py), budgets in ms per frame with the CPU/GPU split, triage by payoff (script hot paths, physics, navigation, allocations and GC, update staggering; draw calls, batching and instancing, overdraw, shadows, lights, post effects, resolution scaling; memory, streaming, loading), per-engine profilers and features for Godot 4.6/4.7, Unity 6 and Unreal 5.8 changed through the engine MCP, and the gates qa-performance measures (frame_ms and gpu_ms percentiles, 1% low, hitches). Use when a scene misses its budget, before a performance gate, or after rendering, effects or spawning changes.
user-invocable: false
---

# Optimization

Find what the frame waits for, change one thing, and prove in milliseconds what it bought. Think
in frame time, not fps (60 → 50 fps is 3.3 ms; 30 → 20 fps is 16.7 ms). Values marked (working)
are starting points; GAME.md overrides them. Per-engine details and sources:
`${CLAUDE_SKILL_DIR}/references/engines.md`. Shader cost: shaders skill §5; effect budgets:
destruction-vfx skill; shadow and GI costs: lighting skill.

## 1. Profile first

1. **Worst case, reproducible.** Heaviest scene, fixed seed, scripted input and camera path
   (acceptance skill §1–2). Measure a target-like run — Godot exported build or the running
   project, Unity Development player, Unreal standalone `-game` — with V-Sync off and no fps cap;
   note resolution, renderer, `vsync_mode`, `max_fps`.
2. **Baseline.** Recorder dump (`frame_ms`, `gpu_ms`, `cpu_render_ms`), Unity/Unreal probe JSON
   Lines or an Unreal `csvprofile` CSV; ≥ 600 frames after a 60-frame warm-up.
3. **Find the bound.** `gpu_ms` close to `frame_ms` → GPU-bound; well below → CPU-bound (scripts,
   physics, render submission). Halve the render scale: a large drop means pixel cost (overdraw,
   post, shadows). Then the engine profiler names the function or pass.
4. **One hypothesis** in the task file: "X costs ~N ms because Y; changing Z saves ≥ M ms".
5. **One change** through the engine MCP; nothing else differs between the runs.
6. **Re-measure** the same scenario and compare. Keep the change only when its metric
   `improved` and `frame_ms` did not regress; otherwise revert. The bottleneck moves — back to 3.

`python ${CLAUDE_SKILL_DIR}/scripts/perf_compare.py <before> <after> [--key frame_ms] [--skip 0]
[--min-samples 120] [--min-ms 0.1] [--min-pct 2] [--hitch-ms 50] [--hitch-tol 0]
[--expect no-regress|improve]` — a single command, no subcommands:

| Part | Behaviour |
|---|---|
| Inputs | recorder JSON: a top-level list (`frame_ms`, `gpu_ms`, `cpu_render_ms`) or one under `samples`; JSON Lines: the key on each line (`dt_ms`, `gpu_ms`, `main_ms`, `game_ms`, `render_ms`); CSV: header column, any case (`--key FrameTime`). Values ≤ 0 dropped (early `gpu_ms` frames are 0), then `--skip` |
| Metrics | mean, p50, p95, p99, max ms; `p1_fps` = 1000/p99; `low1_ms`/`low1_fps` = time-weighted 1% low (CapFrameX); hitches = frames > 2× the median of the last 31 or > `--hitch-ms` |
| Significance | a p50/p95/p99/low1 delta counts beyond max(`--min-ms`, `--min-pct` % of before, split-half noise of either run) |
| Result | one JSON line: `change` improved / unchanged / regressed (worse, or hitches up by > `--hitch-tol`) / insufficient (< `--min-samples`); `verdict` for `--expect`; exit 1 on fail |

The script's docstring still describes recorder format 1; in `kiln-probe/2`, `frame_ms` is real
time between rendered frames. `analyze.py frames` prints `low1_fps` = 1000/p99, which is `p1_fps`
here; gates use the time-weighted `low1_fps`.

## 2. Budgets

| Target fps | 30 | 60 | 90 | 120 | 144 |
|---|---|---|---|---|---|
| ms per frame | 33.3 | 16.7 | 11.1 | 8.33 | 6.94 |

- CPU and GPU run in parallel, so each must fit the frame alone; plan p95 ≤ 90% of it (working).
  Mobile: plan ~65% of the frame for thermal headroom (60 fps → 10.8 ms).
- 60 fps desktop split (working): CPU — scripts 3, physics 2, animation 1.5, AI and navigation
  1.5, render submission 4 ms; GPU — geometry and shadows 6, lighting/GI 4, post 2, VFX 2, UI
  0.5 ms. Unreal Lumen GI + reflections: ~4 ms at 1080p for 60 fps, ~8 ms for 30 fps.
- Memory (working): VRAM ≤ 80% of the minimum-spec card; RAM per GAME.md; flat over a soak.
- Loading (working): first playable ≤ 15 s, level load ≤ 10 s on minimum spec.

## 3. Triage by payoff

| Bound | Try, in this order |
|---|---|
| CPU | 1 script hot paths: cache lookups, no per-frame searches or string building, events over polling; only profiled hot loops move to C#, C++ or Burst jobs · 2 update staggering: AI think 5–10 Hz, perception and re-pathing spread over frames, less logic and animation off-screen · 3 physics: primitive before convex before trimesh shapes, sleeping, layers, pooled bodies; never reach max physics steps per frame (spiral of death) · 4 navigation: bake on a thread from simple collision geometry, fewer navmesh polygons, re-path only when the target moved · 5 allocations/GC: 0 managed allocations per gameplay frame; pools · 6 object count: remove from the tree rather than hide; instancing or server APIs for thousands |
| GPU, pixels | 1 overdraw and transparency (overdraw view; hot spots ≤ 4–6 layers) · 2 post effects, each toggled and measured; half-resolution variants · 3 shadows: fewest shadowed lights, cascades, distance, atlas size · 4 resolution scaling with an upscaler at 0.67–0.77 per axis (working; 0.5 per axis = ¼ of the pixels) |
| GPU, draws and geometry | 1 draw calls: shared materials, batching, instancing, atlases in 2D · 2 LOD and HLOD by distance · 3 occlusion culling where walls hide a lot (it costs CPU or GPU time itself) · 4 lights: bake static ones, distance fade, no shadows on transient lights |
| Memory and streaming | compressed textures with mipmaps (3D), size caps per asset category, streamed music; levels streamed in chunks on background threads; leaks found by object-count and snapshot diffs |
| Loading and stutter | precompile pipelines/PSOs and prewarm every material and effect at load; async loading behind a loading screen; no synchronous loads during play |

## 4. Engine tools and levers

| | Godot 4.6/4.7 | Unity 6 (URP) | Unreal 5.8 |
|---|---|---|---|
| Frame, bound | recorder; Visual Profiler (CPU/GPU per pass) | `KilnProbe` (FrameTimingManager); main thread waiting in `Gfx.WaitForPresentOnGfxThread` = GPU-bound | `stat unit` (Game, Draw, RHIT, GPU), `csvprofile` |
| Deep dive | Profiler, Tracy/Perfetto/Instruments (4.6+), `--gpu-profile` | Profiler in a Development player, Profile Analyzer, Frame Debugger | Unreal Insights, `stat gpu`, `ProfileGPU`, `stat scenerendering` |
| Draws | automatic instancing (Forward+), MultiMesh, 2D batching (4.4+) | GPU Resident Drawer + SRP Batcher (Forward+) | Nanite, instanced static meshes, HLOD |
| Distance, culling | mesh LOD, visibility ranges (HLOD), OccluderInstance3D | LOD Group, Mesh LOD (6.2+), GPU occlusion culling | World Partition HLOD, `stat initviews` |
| Resolution | `scaling_3d_mode` FSR 1 / FSR 2.2, `scaling_3d_scale` | Render Scale + STP | TSR, `r.ScreenPercentage`, `sg.*` scalability |
| Memory | Monitors, ObjectDB snapshots + diff (4.6+) | Memory Profiler snapshot compare | `stat memory`, `stat streaming`, Insights memory |
| Stutter, load | pipeline precompilation (4.4+), shader baker (4.5+), threaded `ResourceLoader` | shader warm-up, Addressables, async scenes | PSO precaching + bundled cache, World Partition streaming |

Settings, nodes and assets change through the engine MCP (Godot `project_manage`,
`node_set_property`, `batch_execute`; MCP for Unity tools; Unreal MCP toolsets), never as
`project.godot`, ProjectSettings YAML or `Config/*.ini` text; console variables only for
experiments. MultiMeshes, occluders, LOD scenes and pools are scene content built in the editor.

## 5. How qa-performance verifies

qa-performance runs the heaviest scene (most enemies, effects, destruction) with the acceptance
recorder and reports per the acceptance skill. Gates unless GAME.md says otherwise:

| Check | PASS |
|---|---|
| Mean `frame_ms` | ≤ budget (16.67 ms at 60 fps) |
| p50 / p95 / p99 `frame_ms` | ≤ 0.9 × / ≤ 1.0 × / ≤ 1.5 × budget (working) |
| 1% low (`low1_fps`) | ≥ 0.75 × target fps (working) |
| Hitches | 0 frames > 100 ms after loading; spikes > 2× rolling median or > 50 ms counted and reported (working) |
| `gpu_ms` p95 | ≤ the GPU budget |
| An optimisation | `perf_compare --expect improve` on its key and `--expect no-regress` on `frame_ms`, both exit 0 |
| Pipelines | CANVAS, MESH, SURFACE, DRAW compilation counters flat during play |
| Physics | steps never reach the per-frame maximum |
| Soak (release gate) | 60 min: 0 crashes, object counts and VRAM flat (growth < 20%) |

Handoff: hypothesis, change, both `perf_compare` JSON lines, the new bound.
