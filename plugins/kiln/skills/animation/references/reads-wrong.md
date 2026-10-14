# Reads wrong — animation failures players notice, each with its check

Every row was a live complaint the user had to spot. qa-locomotion runs every row that applies to
the clips or systems a task touched; the plan copies the applicable rows into animation tasks'
acceptance. **When the user points out a new "looks wrong", add a row** (symptom in their words,
cause, check, threshold, fix) in the same session — the next character must not need the user's eye.

| # | Symptom (user's words) | Cause | Check | Threshold | Fix |
|---|---|---|---|---|---|
| 1 | Feet slide when the runner changes direction several times | capsule velocity turns faster than a planted foot can; no pivots, no foot lock | zig-zag course + `analyze.py stance --root` | turning stances ≤ 10 mm typical, ≤ 20 mm worst | animation "Direction changes without skating" |
| 2 | A standing jump pose while running forward | one jump clip for every approach | jump from idle/walk/run/sprint, both feet in phase + `traversal_check.py jumps` | type by speed, takeoff = stance foot, run jumps keep ≥ 85% speed | animation "Jumps are a family"; traversal §2 |
| 3 | The idle looks like a mannequin | symmetric pose, breathing loop only | 60 s idle + `analyze.py idle --pos --chest --bones` | sway AP 1–8 mm, ML 0.5–4 mm, breathing 12–20/min, nothing frozen, weight 55/45–70/30 | animation "Idle that looks alive" |
| 4 | Walks swaying the hips like a drunk or a catwalk walk | pelvis obliquity/rotation/lateral shift too big, crossing steps | 10 gait cycles + `analyze.py gait --pelvis --hips --feet` | obliquity and rotation ≤ ±5°, shift ≤ ±2.5 cm, step width 8–12 cm, no crossing | human-biomechanics "Hip sway" |
| 5 | Arms hang frozen in the bind pose while walking | acceptance spoke only of legs | arm bone probes over a walk cycle | shoulder sagittal range 25–30° at walk, elbow 15–20°, reciprocal to the legs | plan "Whole-body acceptance"; human-biomechanics arm swing |
| 6 | Elbows can't bend in the armour (run and guard look stiff) | plates collide past 56° | Blender joint sweep + `traversal_check.py rom --moves …` | elbow ≥ 130°, shoulder ≥ 130° (≥ 160° to climb), knee ≥ 140° to crouch | traversal §9; blender-modeling worn gear |
| 7 | Feet skate in straight walking or running | stride vs speed mismatch, phase drift in blends | `analyze.py skating`, stride vs root travel | skating ratio ≤ 0.05; slip per stance ≤ 10 mm (in engine) | animation "Phase and speed matching" |
| 8 | Strikes look slow and weightless | no acceleration into contact, long anticipation | clip timing vs human-biomechanics strike times; peak speed at contact | cross ~0.22 s to contact; speed peaks at contact | human-biomechanics strikes |
| 9 | The body floats or drifts in the air | horizontal acceleration mid-air, apex off the physics | jump recording: |Δvx| in flight, apex vs v₀²/2g | Δvx ≈ 0; apex within 5% | traversal §2 |
| 10 | The corpse's legs sink into the floor | bones placed at floor level; the check looked at pelvis, chest and hands | lowest vertex per body part over the death pose (CPU-skinned in headless runs) | ≥ 0 cm into the floor, ≤ 2 cm above | animation "Death on the floor" |
| 11 | The skirt hem cuts through the legs when running | hem envelope smaller than the swing thigh, no clearance solve | hem vertices vs leg capsules per frame; hem vs floor | clearance ≥ 0 at every frame; hem never under the floor | animation "Long skirts"; soft-bodies |
| 12 | A double step when walk turns into run (or back) | crossfade without phase match; the run's flight pose lands a foot | foot contacts through the transition (`analyze.py stance`) | no extra contact in the transition; phase matched both ways | animation "Phase and speed matching" |
| 13 | The idle does not breathe | spine/chest move < 0.5°: the breath has 0.1 mm amplitude | `analyze.py idle --chest` | `chest_p2p_mm` ≥ 2 mm at 12–20/min | animation "Idle that looks alive" |
| 14 | Feet slide every time the character starts or stops | the library has no start / stop / turn clips; speed ramps 0.2–1.0 s | idle↔walk transitions + `analyze.py stance` | slip per stance ≤ 20 mm in starts and stops | add start/stop/turn clips to the animation batch |
