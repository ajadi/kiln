# Acceptance methods learned the hard way (g2, Godot 4.7.2 + Jolt)

Each rule names the g2 report row that cost a round when it was missing.

## Headless probes (Godot)

- Start from `scripts/probe_base.gd` (copy to `tests/probes/` once): `--fixed-fps 60` makes one
  frame one physics tick (18 min of play in 15 s), `Input.use_accumulated_input = false`, press /
  release by action, `check()` rows, JSON to `production/captures/<task>/` (`--task`) or
  `.kiln/tmp/`, a wall-clock watchdog, exit 0 / 1 / 2. Rows 30, 143, 151.
- Headless runs are allowed directly for scripts under `tests/` and `.kiln/tmp/` (the guard);
  exploration scripts go to `.kiln/tmp/` so `tests/probes/` keeps only kept probes.
- **What headless cannot measure:** `Performance` TIME_PHYSICS_PROCESS / TIME_PROCESS read 0, draw
  calls 0, no gpu_ms (dummy renderer). A cost row must time the work itself (`time_usec()`:
  `Time.get_ticks_usec()` around `tree.advance()` + `skeleton.advance()` for animation, around a
  physics step for bodies) or wait for a windowed run; a probe that logs a monitor reading 0 has
  measured nothing (rows 82, 103, 137). Budgets for one system (23 AnimationPlayers) can be
  measured in a scratch headless project outside the game in minutes, before the engine pass
  (row 141).
- Render cost before any on-screen run: frustum-cull the scene's MeshInstance3Ds from the game
  camera, pick each mesh LOD by the engine's pixel-error rule, count surfaces and triangles per
  pass including the shadow cascades. Calibrated in g2 against windowed runs: primitives within
  about ±25 %, draw calls about 1.7x too high - trust the primitive estimate only (row 103).
- **Audio in headless runs:** the Dummy driver mixes in real time (about 8 % slower than the wall
  clock) while `--fixed-fps` runs the loop as fast as it can, so timers, tweens and the recorded
  Master disagree. Pace the frames (`pace_realtime()`) and locate events in the recording by
  detection, not by wall time (row 109). Sounds still playing at quit are reported as leaked
  `AudioStreamPlaybackWAV` and fail a clean-log gate: in headless runs, UI and SFX players count
  requests (`played += 1`) instead of calling `play()`, and the probe asserts the count (row 123).
- **Jolt "job system exceeded the maximum number of jobs"** appears in every second headless run
  on a many-core machine under load (Blender and the editor open): the worker pool is starved.
  Fix it in the project (`threading/worker_pool/max_threads = 8`), not by filtering the log; a
  clean-log gate may list this one message as known-benign only after the fix, and never with a
  blanket WARNING filter (rows 37, 51).

- Mesh-level fits headless (hem vs leg capsules, seat / rail / counter gaps, a corpse vs the floor):
  `scripts/mesh_fit.gd` skins on the CPU; silhouettes compared with the animator's Blender
  renders via image-to-model `silhouette_iou.py` (g2: within 0.02) (row 149).

## Rows that can fail

- No row may read the implementation's own formula (`fade_for_distance()` asserted against
  itself) or assert a value the code clamps to: it passes by construction. Measure the world:
  positions, distances, contacts, pixels (rows 54, 55).
- A row that passes trivially once a feature is switched off (a camera pivot that no longer rises)
  says so in the report.
- Physics or layer settings change: re-check the probe fixtures. A camera mask change would have
  made every `StaticBody3D.new()` wall in the acceptors' synthetic worlds invisible to the camera
  and the camera rows pass trivially (row 70).

## Movement, camera and contact logic

- **Correction terms** (anything fed back into its own input - arm length -> pivot rise -> arm
  sweep, a speed compensation through a wall-slide): require (a) a still-hold convergence test -
  arm, pivot and fade variance over 1 s at every reachable cell x 8 yaws; (b) a per-tick speed
  envelope (<= 1.1 x set speed) in every contact configuration (ramp + wall, crest, corner). A
  builder's few static poses missed a 3 Hz pumping camera at 34 cells and a 3.8 -> 13.7 m/s
  run-away (row 54).
- **Contact-triggered logic** (step-up, snap, ledge grab): sweep the start phase (>= 6 offsets
  over one tick of travel) and raster the geometry classes at <= 5 cm; a "not reachable in the
  level" claim needs that raster, not the BFS cell grid. A 0.5 m cell scan said "unreachable";
  a phase sweep found the stall in 11 % of approaches to a 0.18 m plinth (row 81).
- **Neighbour sweep** on every movement or camera rework: rerun every earlier probe file plus one
  randomised start-phase / start-position sweep per touched function, not only the rows of the
  reported findings. Three rounds each fixed the reported defect and broke a neighbouring path
  (row 74).
- **Attribute a regression without old code:** read the controller source, replace one line in
  memory, `GDScript.new()` + `source_code` + `reload()`, `set_script()` on the live node (drop the
  `class_name` line, copy the script variables back) and rerun the same sweep (11 of 252 stalls
  became 1 of 252). Ask builders to keep the previous round's behaviour reachable by a flag so
  acceptors can A/B it (row 73).
- **Rendered-frame smoothness** is invisible to physics-rate probes. `--headless --fixed-fps N`
  with N != 60 keeps physics at 60 Hz and gives real `process_frame` samples;
  `get_global_transform_interpolated()` works. Sweep N in 30 / 60 / 144 / 240, report the
  coefficient of variation of per-frame body and camera motion and the share of zero-move frames,
  and prove the check can fail by forcing `physics_interpolation_mode = OFF` (CV 1.18 in g2)
  (row 36).
- **Third-person camera inside the character:** minimum arm length vs the character's capsule
  radius with a wall behind it, over a cell grid x 8 yaws (20 % of plaza cells failed in g2)
  (row 36).

## Rounds and baselines

- Visual regression: every scene that has a look-dev or art pass gets fixed review cameras
  (`kiln_view_<name>` Camera3D nodes) and baseline frames in `production/baselines/<scene>/`
  (`scripts/frames.py baseline`). After any art, level, lighting or fx task the verifier runs
  `frames.py compare` on fresh captures from the same cameras: a changed region the task did not
  intend is a finding; an intended one is accepted with `frames.py accept --why`. This is what
  catches a level replaced under a running round and art regressions the user would otherwise
  spot by eye.

- End every acceptance round with `scripts/accepted.py snapshot --scenes <scenes under test>`
  and start the next with `accepted.py check`: acceptor probes are untracked while the task is
  open, so this is the only baseline that shows a weakened row (row 72).
- The level can change under a running round (another agent replaced the plaza: a step row stopped
  testing a step, a probe started inside a new collider). `accepted.py check` at the end of a long
  round names it; a row that depends on one level feature gets a synthetic copy of that feature on
  the test floor (row 92).
- Effects and bus settings are measured on identical content: the same stream with the setting
  off, then on, or an in-engine A/B - never two moments of a live mix (13.5 dB for the builder,
  6.2 dB on the re-run, 12.8 dB content-matched). Ducking: pre/post the compressor on the same
  bus (row 112).
