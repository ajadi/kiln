---
name: acceptance
description: Shared harness for Kiln acceptance roles — deterministic scenarios, an in-game probe recorder instead of per-frame MCP polling, metric analysis scripts, the report format, evidence and screenshot rules, and the limits of judging games from images. Preloaded into every qa-* agent; read it when designing or reviewing any acceptance check.
user-invocable: false
---

# Acceptance harness

Acceptance roles judge one aspect of the running game with numbers. They never fix what they
find, and they never accept a builder's claim without reproducing it.

Scripts in `${CLAUDE_SKILL_DIR}/scripts/`:

| Script | Use |
|---|---|
| `probe_base.gd` | Godot headless probes: copy to `tests/probes/probe_base.gd` once, `extends` it, override `_run()`; ticks / press / `check()` rows, JSON per task, watchdog, exit 0/1/2 |
| `mesh_fit.gd` | Godot headless: CPU skinning of a MeshInstance3D on its skeleton (the dummy renderer does not skin), vertices by bone, lowest point, capsule clearance — garment hems vs legs, seats, rails, corpses vs the floor (lowest vertex per body part) |
| `frames.py` | visual regression: `baseline` frames per scene from fixed cameras, `compare` after a task (SSIM + changed regions with boxes and a diff image), `accept --why` for an intended change (HISTORY.md) |
| `accepted.py` | `snapshot` at the end of a round (acceptor probe hashes + row counts, scene fingerprints), `check` at the start of the next |
| `recorder.gd` | Godot: copy to `tests/probes/recorder.gd` once; attach at runtime through game eval; samples values every physics tick, frame time every frame, dumps JSON |
| `unity/KilnProbe.cs` | Unity 6: MonoBehaviour (+ `IKilnProbeSource`), samples every FixedUpdate or LateUpdate, frame timing every Update, writes JSON Lines |
| `unreal/KilnProbeComponent.h/.cpp` | Unreal 5.x: `UKilnProbeComponent`, ticks post-physics, writes JSON Lines to `Saved/Kiln/Probes/` |
| `unreal/kiln_toolset.py` | Unreal: Kiln toolset for Epic's Unreal MCP — `exec_console`, `inject_input`, `kiln_probe_start/stop/read`, `highres_shot` |
| `analyze.py` | `skating`, `frames`, `settle`, `reaction` over any of these recordings (JSON or JSON Lines; globs) |
| `readability.py` | `contrast` (WCAG; boxes x,y,w,h, `--mask` + 15 px ring, or `--hex-a/--hex-b` palette pairs; `--parts 3` head/torso/legs bands; says when brightening cannot reach the threshold), `mask` (enemy mask from shots with/without it; `--largest --fill`), `cvd` (protan/deutan/tritan: Machado 2009, `--model brettel`; hex pairs too), `squint` (blur σ 1% width, 4 L* bands; `--expect same` for decoration), `saliency` (spectral residual peak rank; peaks within `--border` px of the edge, default 3% of width, are not ranked); `--out` writes review images |
| `../pipeline/scripts/contact_sheet.py` | `values` (luminance stats), `contrast` (region contrast ratio), `sheet` (frame sheets) |

Methods and limits found in real rounds — headless timing and audio, the Jolt job warning,
correction terms, contact logic, neighbour sweeps, one-line A/B, smoothness, baselines between
rounds: [references/methods.md](references/methods.md). Read it before designing a movement,
camera, physics, performance or audio check.

## 1. Scenario first

Write the scenario in the task file before running it: scene, start state, seed, input sequence
(action names and timings), duration, what is sampled, thresholds with their source. A check you
could not have failed is not a check — for every probe, state what result would mean FAIL.

## 2. Run deterministically

- Fixed random seed (the game's RNG autoload or the scene's seed export).
- Scripted input: Godot `game_manage` input simulation or `Input.action_press` /
  `action_release` through game eval, by action name; Unity Input System state events through
  `execute_code`; Unreal Kiln toolset `inject_input` (Enhanced Input action).
- Fixed physics rate (Godot 60 Hz, Unity 50 Hz defaults; Unreal steps with the frame); note the
  frame rate.

## 3. Sample inside the game, not through MCP

One MCP round trip is slower than a physics tick, so polling from outside skips and aliases
samples. The probe runs inside the game, records only, and is pulled once; analyse the file with
`analyze.py` or your own numpy code. Pull state snapshots (node properties, HP tables, layer
masks) with single calls; those do not need per-tick sampling. Probe code is installed once by a
builder role (the files below are not scene content); acceptance roles only attach, start, stop
and read.

**Godot.** Attach `recorder.gd` through `editor_manage` game eval, `add_probe(name, callable)`
(per physics tick) and `add_frame_probe` (per frame), `start(ticks)`, drive the scenario, wait
until `rec.done`, then `rec.dump("res://.kiln/tmp/<name>.json")`.

**Unity** (MCP for Unity). Install: `create_script` path
`Assets/_Project/Scripts/Runtime/Kiln/KilnProbe.cs` with the file's contents, then
`validate_script` + `read_console` (no errors). In a test scene: `manage_gameobject` create
`_KilnProbe`, `manage_components` add `KilnProbe` (targets, members, sources in the inspector
lists), `manage_scene` save. Without one, `KilnProbe.Attach()` makes a throwaway probe in Play
mode. Drive it through `execute_code` (`action` execute); the code is a method body that must
`return`, sees only `using UnityEngine; using UnityEditor;`, so fully qualify:

```csharp
// kiln:probe
var p = Kiln.Probes.KilnProbe.Attach();
var hero = GameObject.Find("Hero").transform;
p.AddTarget("hero", hero).AddValue("speed", () => hero.GetComponent<CharacterController>().velocity.magnitude);
p.AddTarget("foot_l", hero.Find("Armature/Hips/UpLeg.L/Leg.L/Foot.L"), Kiln.Probes.KilnChannels.Position);
p.SetTiming(Kiln.Probes.KilnSampleTiming.LateUpdate);   // animated bones: after animation and IK
return p.StartRecording("T012", "walk", 600);           // -> production/captures/T012/probe_walk.jsonl
```

Then `return Kiln.Probes.KilnProbe.Find().Done;` until true (or `StopRecording()`). Input: queue
device state through `execute_code`, e.g.
`UnityEngine.InputSystem.InputSystem.QueueStateEvent(UnityEngine.InputSystem.Keyboard.current, new UnityEngine.InputSystem.LowLevel.KeyboardState(UnityEngine.InputSystem.Key.W));`
(held until a new state event; release with `new KeyboardState()`), or a project input seam.
FixedUpdate samples see the previous physics step plus this step's gameplay changes; use
LateUpdate for bones and for movers driven in Update. Frame timing comes from
`FrameTimingManager` (cpu/main/render/gpu, four frames late) and `Time.unscaledDeltaTime`; the
editor adds its own cost, so budgets are measured in a Development player.

**Unreal** (Epic Unreal MCP). Install: copy `unreal/KilnProbeComponent.h/.cpp` to
`Source/<Module>/Kiln/`, add `"RenderCore", "RHI", "Json"` to the module's dependencies, restart
the editor and do a full build; copy `unreal/kiln_toolset.py` to `Content/Python/` and register it
from `Content/Python/init_unreal.py` (steps at the top of the file); restart, `list_toolsets`.
In a test map: ActorTools `add_component` (KilnProbeComponent) on the actors to watch,
ObjectTools `set_properties` for `Actors`, `Sockets` (feet, muzzles), `Values` (part HP: property
or pure getter), `SampleHz` (0 = every frame), SceneTools `save_actor`. Loop: `IsPIERunning` →
`StartPIE` → Kiln toolset `kiln_probe_start` → `inject_input` (action, x, y, z, hold seconds) →
`kiln_probe_stop` → `StopPIE` → `analyze.py` on the returned files. Positions are cm and Z-up;
`analyze.py` converts. PIE frame times are indicative only; budgets come from a standalone
`-game` run.

**Recording formats** (both read by `analyze.py`; numbers always with `.` decimals, NaN → null):

| Format | Fields |
|---|---|
| JSON (`recorder.gd`, `kiln-probe/2`) | `physics_ticks_per_second`, `ticks`, `samples {name: [per tick]}`, `frame_ms` (wall-clock per frame), `frames`, `frame_tick`, `cpu_render_ms`, `gpu_ms`, `frame_samples`, `time_scale`, `max_fps`, `vsync_mode` |
| JSON Lines (`kiln-probe/1`) | `header` line: `engine`, `task`, `run`, `physics_hz`, `units_per_meter` (Unreal 100), `up` (`y`/`z`), `sample` timing; `tick` lines: `tick`, `t` (s since start), `<label>.pos/.vel/.rot`, values; `frame` lines (Unity) or fields on tick lines (Unreal): `dt_ms`, `gpu_ms`, `cpu_ms`/`main_ms`/`render_ms` (Unity), `game_ms`/`render_ms` (Unreal); `end` line |

## 4. Look, but confirm with data

- Screenshots (`editor_screenshot` source `game`) at the decisive ticks — name each by its
  physics tick. Look at them yourself; for small details or on-screen text take a tighter shot or
  crop ×3 before reading.
- A capture must not change what is being measured. Moving or flipping the gameplay camera
  inside a recording window also moves camera-relative input. Live: a front-view flip in the
  middle of a gait recording turned the walker by up to 36°, and the pelvis rotation read 20.7°
  instead of 4.9°. Take those shots outside the window, with a separate camera that drives no
  input, or cut those ticks from the dump.
- Readability captures: `mask` needs a pair of frames from the same camera with and without
  the target (hide the node through game eval, capture, show it, capture). Take them in the
  gameplay scene, not a scratch preview: contrast against a neutral sky and a brown plane is not
  the gameplay contrast. Saliency needs clean game captures (no gizmos, navmesh overlays or
  editor grid). Judge figures by `--parts` and the silhouette edge, not only the whole-mask mean
  (a dark vest on a dark wall averages out with a light face).
- Image models detect gross glitches reasonably (~80% on benchmarks) but miss clipping, pose
  errors and small UI changes, and they cannot judge fun. A visual finding becomes FAIL only when
  engine data confirms it (an overlap query, a bone angle, a measured contrast, a position).

## 5. Report

Append to the task file and reply with the verdict line first:

```markdown
## acceptance: <aspect> — <scene> — <date>
verdict: PASS | FAIL | NOT ASSESSED
| metric | value | threshold | source | verdict |
|---|---|---|---|---|
| foot_skating_ratio | 0.03 | ≤ 0.05 | motion-synthesis skating metric | PASS |
scenario: <scene, seed, inputs, duration>
probe: tests/probes/<name>.gd (+ dump path)
screenshots: tick 412 — <what it shows>; …
repro (FAIL): <smallest scenario that shows it>
send to: <role> — <specific fix> (FAIL only)
```

NOT ASSESSED is honest when the scenario could not run (editor down, scene missing) — never turn
it into PASS. Thresholds marked "working" in the role's table are starting points: report the
value either way, and flag when a value sits close to the line.

## 6. Leave no trace

Probe scripts stay in `tests/probes/`, dumps in `.kiln/tmp/` (Godot), `production/captures/<task>/`
(Unity) or `Saved/Kiln/Probes/` (Unreal); stop the game, which drops runtime-attached recorders;
`git status` before replying shows only your probe files and the task file.
