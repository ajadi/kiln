---
name: animation
description: Rigging, skinning, animation clips and locomotion for game characters and mechs — export skeleton rules, clip contract, phase and speed matching, locomotion sets, mech weight, multi-legged stepping, wall climbing, hit reactions, deaths and ragdoll handoff, FPS arms, Blender 5.x keyframing API, measurable acceptance thresholds, and Godot 4.6/4.7 AnimationTree/IK specifics (Unity/Unreal specifics in their engine skills). Use when rigging, animating, or verifying movement.
user-invocable: false
---

# Animation and locomotion

Players judge movement in motion. A walk that looks right in Blender can still skate in the game
because the controller speed and the clip's stride disagree. Everything here ends with a
measurement in the running game. Load human-biomechanics or creature-locomotion for the subject;
traversal for jumps, vaults, climbing, hanging, crawling, falls, carried load, the joint range
gear allows, held-item overlays (arm swing, carry postures), sitting, mounting and driving poses; hands for grips, finger poses, two-handed holds and hand IK;
soft-bodies for spring bones, cloth and ropes on the rig.
2D sprite animation (frame counts, stride per cycle, fixed canvases, skeletal 2D): art-2d skill §5.

## Rig

- **Two rigs.** The control/IK rig stays in Blender. The export skeleton is one clean deform
  hierarchy: no B-bones, no scale keys, root = a deform bone at the origin on the floor. Any bone
  the engine needs (root for root motion, weapon sockets, bones of detachable parts) must have
  `use_deform=True` — Rigify's DEF bones are not one hierarchy and its `root` is non-deform; use a
  game-rig conversion (e.g. GameRig) or build the deform hierarchy yourself.
- Bone axes: +Y along the bone, consistent rolls so flexion is about +X. Rest pose: T-pose for
  humans (Godot's reference pose faces +Z, +Y parent→child, +X flexes like a muscle contracting),
  a neutral mid-range pose for mechs — engines blend rotations from the rest, so a rest far from
  the motion range causes flips.
- Transforms applied (identity) before export; character faces -Y in Blender.
- Rigid mechanical parts: exactly one influence at weight 1.0, or bone-parented; each damageable
  part a separate mesh so it can be hidden or swapped on detach. Pistons: two bones aiming at each
  other (or an aim modifier in engine). Soft parts (cables, antennae): spring bones.
- Clip sharing between skeletons needs matching rests, not just matching names: use the engine's
  retargeting (Godot: BoneMap + SkeletonProfileHumanoid with Rest Fixer → Overwrite Axis,
  Normalize Position Tracks, Remove Tracks → Unimportant Positions, Unique Node). Humanoid profile
  names (Root above Hips, …) make the mapping trivial. Mechs: a custom profile or no retargeting.
- **Blender IK chains:** a nearly straight rest leg (or arm) makes Blender's IK bend the knee
  sideways or twist the thigh 90–180° whatever the pole angle — a pole fitted on the rest pose
  looks perfect and the crouch exposes it. Pre-bend the rest knees and elbows 2–3 cm toward the
  pole (mind that −Y is forward), lock the hinge joints to their flexion axis (knee: X only), and
  fit the pole angle on a bent chain (g2 row 126).
- **Shared clip libraries across scaled bodies** (one skeleton, `npc_scale` 0.94–1.06): every
  contact clip becomes scale-dependent — a 0.50 m seat or a 1.0 m rail authored at scale 1 lands
  ±3–5 cm off on the others. Seats: a per-body root lift; hand contacts: scale bands or per-body
  variants; lying poses fitted per body group. Ship a per-body probe that reports floor / seat /
  hand-contact error for every body in the crowd (g2 row 139).
- **Long skirts on a shared rig:** 4 skirt columns tear the hem at the diagonals and leg weights
  turn a skirt into trousers. What worked: 8 two-segment columns driven at bake time by a
  clearance solver (garment envelope vs leg capsules, gravity hang, floor, rate limit), plus a
  separate seated mode (front panel along the thighs, drop from the knees). See the soft-bodies
  skill for the solver pattern (g2 row 140).

## Clips

- One action per clip, stashed on the NLA, Manual Frame Range + Cyclic Animation (range includes
  the duplicated first key). Export `export_animation_mode='ACTIONS'`, `export_def_bones=True`,
  `export_force_sampling=True`, `export_reset_pose_bones=True`, `export_anim_slide_to_zero=True`
  when ranges do not start at 0.
- Names: `idle`, `walk`, `run`, `sprint`, `strafe_l`, `strafe_r`, `walk_back`, `crouch_idle`,
  `crouch_walk`, `jump_start`, `jump_loop`, `land`, `aim`, `fire`, `reload`, `melee`, `hit_<zone>`,
  `death`; starts/stops/turns as below. Set loop modes explicitly in the engine import (name
  tokens `loop`/`cycle` are a fallback).
- Blender fps = engine import fps (Godot default 30).
- Author pose-to-pose: extremes first (contact, down, passing, up), then breakdowns, then
  splines. Auto-clamped handles, Cycles modifier or cycle-aware keying, Euler filter (or
  quaternions on deform bones); check arcs with motion paths.
- **Blender 5.0 removed `Action.fcurves`, `.groups`, `.id_root`.** Key with
  `pose_bone.keyframe_insert(data_path, frame=..., keytype='EXTREME'|'BREAKDOWN')`, reach curves
  through channelbags (`Action.fcurve_ensure_for_datablock(...)`, `ActionChannelbagFCurves`),
  bake with `bpy_extras.anim_utils.bake_action`. Look up anything else with `search_api_docs`.

## Phase and speed matching

- Every locomotion cycle (walk, run, strafes, backwards, crouch-walk) puts left contact at
  normalized 0.00 and right contact at 0.50 (±0.02). Multi-legged mechs: record the gait table
  in `memory/pipeline.md`.
- Play rate = actual speed / authored speed, clamped to about 0.85–1.15; outside that add a blend
  point or stride warping. Store each clip's authored speed (from its root track) so slip can be
  checked.
- Walk/run blending must keep phase — the engine's plain "sync" may not (see Godot below).
- Starts, stops and pivots use root motion (distance matching) — in-place loops are fine for the
  FPS player.
- Swing paths must not arrive at heel strike with the full ground speed: a Hermite tangent equal
  to the stance velocity overshoots forward and pushes hip flexion up 10–20° (g2: run 80° → 60°
  after scaling the touchdown tangent to 0.3 of the stance speed). Slip is measured on the
  least-moving touching sole point (heel, ball, toe) per frame pair — a single sole point reads
  the forefoot rolling about a raised toe joint as 15–24 mm of skating (`analyze.py skating
  --foot heel,ball,toe`) (g2 row 128).
- A controller that accelerates (0.2–1.0 s speed ramps) needs start, stop and turn clips in the
  animation batch: without them every idle ↔ walk change slipped 28–110 cm in g2 (reads-wrong 14).

## Locomotion set and weight

- Set: idle; starts at 0/±90/180°; loop; stops with left/right foot planted; plant-pivot;
  turn-in-place 90/180. Heavy mechs need the full set to read heavy (response, inertia,
  momentum).
- Mech weight from physics: walking stays under Froude 0.5 (v²/(gL)); cadence scales with
  √(g/L) — a mech with 4 m legs steps about 2× slower than a human. Long anticipation,
  overshoot-and-settle on stops, 2–4 frames of lag per hierarchy level.
- Few strong key poses + procedural layers (springs, foot IK) beat many hand-keyed frames for
  responsive control.

## Idle that looks alive

A symmetric "mannequin" stance with a breathing loop is the default failure. Build the idle in
layers (numbers: human-biomechanics "Quiet standing"):

1. **Base pose, asymmetric**: weight on one leg (55/45–70/30), free knee 10–20° bent, pelvis
   dropped 1–5° on that side and shoulders countering (contrapposto), feet not mirrored (toe-out
   differs ≥ 2°), arms slightly forward with palms to the thighs, elbows 10–20°, fingers curled.
   No "twins" — left and right never mirror exactly.
2. **Breathing** as an additive layer: 12–20/min, exhale longer than inhale, chest/shoulders a few
   mm, abdomen-led at rest; faster and higher after exertion.
3. **Sway**: slow, small whole-body sway (CoM 2–8 mm front-back, 1–4 mm sideways, 0.1–0.3 Hz),
   larger at shoulders and head; procedural noise or a long sway layer — never a jitter.
4. **Weight shifts and fidgets**: one-shots at random intervals (game-compressed every 15–45 s,
   varying ≥ 25%), switching the loaded leg, adjusting gear, looking around; a shift is a short
   transition to the mirrored base pose, not a pop.
5. **Gaze**: look-at with eyes first, head following above ~20°; occasional glances at points of
   interest; blinks every 2.5–7.5 s at random if the face is rigged.
6. **Secondary motion**: loose straps, hoses, cloth and hair keep moving after shifts (spring
   bones, soft-bodies skill); armour plates never interpenetrate in any frame.
7. **No visible loop**: layer lengths that don't divide each other (4.0 s and 11.3 s repeat only
   every ~452 s); seams under 0.5 mm.
8. **Variants** by state: tired (more sway, heavier breathing), cold, injured, heavy load (trunk
   forward, wider base), combat-ready (human-biomechanics stance).

## Direction changes without skating

Live failure: running and changing direction a few times makes the feet slide — the capsule's
velocity swings faster than any planted foot can turn. A real plant at 5 m/s turns the body only
~18° (~35° at 2 m/s); an instant 90° velocity flip with a foot planted 0.25 s slides it ~1.8 m,
84× the ~21 mm people notice.

- **Controller limits** (in data): heading change per step ≤ ~35° at walk, ~18–30° at 4–5 m/s;
  sustained lateral acceleration ≤ ~0.5–0.7 g (curve sprints: 0.54 g at r 6 m, 0.69 g at r 3 m);
  sharper changes go through a pivot or spread over 2–3 steps; brake on the step before a cut of
  60°+ (entry speeds fall to ~3.8 / 3.5 / 3.4 m/s for 90 / 135 / 180°). Velocity follows the input
  through a spring (half-life ~0.27 s in Holden's reference controller), and rotation
  responsiveness is not set so high the character spins on the spot.
- **Capsule vs mesh**: let the mesh lag the capsule and pull it back with a damper capped at ~0.5
  of the character's speed, clamped to ~0.15 m and 90° (Holden; Unreal Offset Root Bone does the
  same) — the feet stay planted while the capsule turns.
- **Warping**: orientation warping twists legs toward the real movement direction and
  counter-twists the spine (one forward clip covers up to 90°; cardinal clips + warping instead of
  8-way diagonals); stride warping scales stride by actual / clip speed; distance matching drives
  starts, stops and pivots by distance, not time.
- **Pivots and cuts**: plant-and-turn clips chosen by the foot in stance at the moment of the
  turn — a step turn (other foot, wide base) or a spin turn (pivot on the stance foot); 180°
  reversals plant over 1–3 steps (contact ~0.45–0.5 s). Starts may not interrupt a pivot.
- **Foot locking**: when the clip's contact flag turns on, lock that foot's contact point in
  world space; release when the contact ends or the animated foot drifts > ~0.2 m; blend both
  ways over ~0.1 s; two-bone leg IK places the foot. The foot may yaw in stance (pivot) — the
  contact point may not slide.
- **Body language**: lean into the turn atan(a_lat/g) (±5°, capped ~35–40°); the head turns toward
  the new direction first (~0.2 s / 10–25° ahead of the body, looking at the new path ~1 s before a
  corner); the inner leg's stride shortens.

## Jumps are a family, not one clip

One standing-jump clip played at every speed is a known failure (live: a two-foot squat and a
vertical pose while running forward). A character that can jump while moving gets a jump per
approach, picked by horizontal speed at the input frame (thresholds in data; numbers and checks
in the traversal skill, `traversal_check.py jumps`):

| Approach | Takeoff | Flight | Landing |
|---|---|---|---|
| standing (≤ ~0.3 m/s) | two feet, countermovement squat, arms swing up | vertical, legs tuck for clearance | two-foot squat to idle |
| standing forward (aimed jump from idle) | two feet, deep lean forward, arms swing forward | body extends, then knees forward | two-foot, absorb forward |
| walking | one foot — the stance foot at the input frame — short push, no squat | stride hop, small rise | onto the other foot, back into walk |
| running | one foot from the stance foot, shallow knee bend, no stop | stride leap: lead knee driven up, trail leg back, arms counter | lead foot lands and the run continues |
| sprinting | as running, lower takeoff angle, longest flight | long leap (legs cycle or hang), arms wide | continue-run, or roll above the fall tier |

- Author left- and right-foot starts for walking, running and sprinting jumps and choose by the
  locomotion phase (the foot on the ground when the button is pressed); a jump that waits for "the
  right foot" adds input lag — pick the matching variant instead.
- Running jumps lower the body over the last two strides and take off with a shallow knee bend
  (~38°, contact ~0.1–0.25 s); the standing jump's countermovement is real (~1 s) but games
  shorten it to 0.1–0.25 s for response.
- Running and sprinting jumps keep most of the horizontal speed (0.85–0.90, no stop-and-launch)
  and never plant both feet at takeoff; landings at speed continue the cycle on the matching foot, landings
  from height follow the traversal fall tiers (soft, roll, hard).
- In-air clips per type (apex, falling loop) and a blend from the type's air pose to the common
  fall loop for long drops; no added horizontal acceleration mid-air.
- Root motion vs code: the controller owns the arc (exact v₀ from the design apex height), clips
  are timed to it — the takeoff frame of the clip lands on the frame the body leaves the ground.

## Multi-legged stepping and climbing

- A leg steps when its target leaves IK reach or passes a distance threshold; gait groups:
  diagonal pairs (4 legs), tripod (6), alternating tetrapod (8); never lift a leg whose neighbour
  is mid-swing; swing follows an arc.
- Body height and tilt from a plane fitted to the planted feet.
- Wall climbing: probe down and forward, gravity along the averaged surface normal, the body's up
  set to that normal; floor↔wall transitions over convex and concave edges tested explicitly.

## Hit reactions, deaths, FPS arms

- Hit reactions: short, interruptible one-shots filtered to the hit region; mechs react per part.
- Deaths: animation → blended → ragdoll over ~0.15 s, physics bodies synced first and inheriting
  the animation's velocities. Mechs: a power-down sag, then parts go physical and the hull settles
  on the ground.
- FPS arms: viewmodel camera ~70–75° FOV; procedural sway, bob and recoil layered additively over
  keyed poses; each reload beat distinct; aim-down-sights 8–15 frames (up to ~25 for heavy
  weapons).
- Crossfades: locomotion 0.1–0.2 s, combat 0.05–0.1 s.
- **Weapon draw from a belt sheath:** a hammer grip on a blade-down hilt needs the thumb pointing
  down (elbow into a stout belly, wrist 70–80°) — anatomically impossible. Give the weapon a
  **prop bone** under the hand whose frame is the weapon's frame: the hand takes the hilt in a
  reverse grip and the prop bone spins the blade into the hammer grip during the pull-out (the
  grip-window swap: the swap happens while the blade is out of view or in motion). Same for back
  sheaths; the hands skill picks the grips (g2 row 127).
- **Death on the floor:** the check is the lowest vertex per body part, not the pelvis, chest and
  hands only — prone legs and knees sank 7–9 cm into the floor when bones were put at floor
  level (reads-wrong 10).

## Acceptance thresholds (also used by qa-locomotion)

Players notice certain failures at once — the catalogue
`${extensionPath}${/}skills${/}animation/references/reads-wrong.md` lists each as a pitfall with its check; run every entry that
applies to the clips you touched before handing off, and add an entry whenever the user spots a
new one.

| Check | Pass | Fail / note |
|---|---|---|
| Contact | sole ≤ 1 cm above ground and horizontal speed ≤ 0.1 m/s | — |
| Slip per stance, authored | ≤ 5 mm | — |
| Slip per stance, in engine | ≤ 10 mm | > 20 mm (perception threshold ≈ 21 mm, Pražák 2011) |
| Skating ratio (contact ticks with speed > 0.15 m/s) | ≤ 0.05 | — |
| Sole height in stance | authored 0 ± 5 mm; runtime flat ±10 mm; stairs/slopes with IK ±25 mm | penetration > 10 mm |
| Root travel vs foot plants | within ±2% | — |
| Play rate | 0.85–1.15 | outside → new blend point |
| Phase | L 0.00 ± 0.02, R 0.50 ± 0.02 in all synced clips; contacts alternate through blends | double step |
| Loop seam | first vs last ≤ 0.5°/bone, ≤ 1 mm | — |
| Pops (working) | ≤ 25°/frame at 30 fps; not > 4× the clip's p95 unless a tagged impact; across transitions `analyze.py pops`: no isolated one-frame step ≥ 3× its neighbours and ≥ 2 % of the height | Euler flips |
| Joint limits (working) | knee 0–150°, hyperextension ≤ 5°, elbow 0–145°; mech hinges off-axis ≤ 0.5°; pistons within stroke | — |
| Self-intersection (working) | ≤ 5 mm; arms vs weapon ≤ 2 mm | — |
| Transition slip | ≤ 2 cm | — |
| Prop in free flight (tossed, dropped), from the keyed prop bone | vertical acceleration g ± 10 %; horizontal velocity keeps its sign and size (no mid-air reversal, no speed jumps) | live: a back unit fell at 4.4 g and flew forward, then 1.1 m backward ("telekinesis") |
| Catch or set-down of a load | the hand meets the load at ≤ 1.5 m/s; deceleration ≤ 2 g spread over ≥ 6 frames at 30 fps; elbow, knees and trunk yield (dip 3–5 cm, trunk 4–6°) | a dead stop on a straight arm (12 kg in one frame ≈ 950 N) reads weightless |
| Lift of a load ≥ 5 kg | hips and knees extend 2–4 frames before the arm pulls; the trunk leans away from a one-sided load (5–8°) and back at release | an all-arm heave with the trunk still reads weightless |
| Real animation, not a moved pose (every loop and cycle: player, NPC idle and work loops, animals) | `analyze.py rigid --joints <>= 3 joints> --root <root>`: joints move ≥ 0.2 % of the height against the root and the similarity-fit residual stays ≥ 0.02 % of the height | "nothing moves" (a frozen pose, or a pose only slid); "moves rigidly" (a sprite or mesh bobbed, tilted or scaled as one piece) |
| Hip sway in walk/run (`analyze.py gait` over 10 cycles) | pelvis obliquity ≤ ±5°, rotation ≤ ±5°, lateral shift ≤ ±2.5 cm, step width 8–12 cm, feet never cross the midline (human-biomechanics) | a catwalk or drunk walk: big lateral sway, crossing steps |
| Idle alive but calm (≥ 60 s recording) | `analyze.py idle --pos pelvis --chest chest --bones <limbs, head>`: sway RMS AP 1–8 mm, ML 0.5–4 mm, ≥ 80% of sway power below 0.5 Hz, breathing 12–20/min, no part frozen (< 0.5° in 10 s) | symmetric base pose; weight never shifts in 60 s; plates interpenetrate |
| Direction changes (zig-zag course: 45/90/135/180° left and right at 1.5/3/5 m/s, turn at a random step phase; slalom r 2/3/5 m) | `analyze.py stance --root`: turning stances ≤ 10 mm typical, ≤ 20 mm worst | heading change > the per-step limit without a pivot clip; lean off atan(a/g) by > 5° |
| Multi-leg stability (working) | COM inside support polygon with ≥ 10% margin at slow gait | — |

## Godot 4.6/4.7

- AnimationTree blend spaces: in **4.6** `sync=true` only keeps blended clips advancing — it does
  not normalise phase, so clips of different length drift. Use `AnimationNodeAnimation.
  use_custom_timeline` with the same `timeline_length` and `stretch_time_scale` on each clip
  (`start_offset` picks the leading foot). In **4.7** use `sync_mode = SYNC_MODE_CYCLIC_MUTABLE`
  (or `CYCLIC_CONSTANT` with `cyclic_length`); every blend point must be an AnimationNodeAnimation
  with a finite length, and a TimeSeek after the blend space breaks it. State-machine transitions
  with `switch_mode = SYNC` seek absolute time, so they keep phase only for equal-length clips.
- Root motion lives on **AnimationMixer** (base of AnimationTree and AnimationPlayer):
  `root_motion_track = "Skeleton3D:Root"`, `get_root_motion_position()` etc.; set
  `callback_mode_process = PHYSICS` when driving a CharacterBody3D; rotate the delta by the
  character's basis.
- IK (4.6+, SkeletonModifier3D family): `TwoBoneIK3D` (needs a pole node), `ChainIK3D` →
  `SplineIK3D`, `IterateIK3D` → `FABRIK3D` / `CCDIK3D` / `JacobianIK3D`; joint limits with
  `JointLimitationCone3D`, hinge axes via `set_joint_rotation_axis`. Also `LookAtModifier3D`,
  `AimModifier3D`, `SpringBoneSimulator3D`, `LimitAngularVelocityModifier3D` (caps IK pops),
  `RetargetModifier3D`. `SkeletonIK3D` is deprecated.
- Bones a state does not key drift to their rest pose (AnimationMixer `deterministic`). If a
  one-shot's frame 0 puts such bones somewhere else, the crossfade into it slides them there in
  view. Live: a back unit went from the worn rest pose to the floor at 15 m/s in the first 0.1 s of
  kit_on. Hand off, for every prop or attachment bone, the pose it must hold between clips: a hold
  clip on a filtered layer, a zero crossfade on those bones, or a mesh swap after the fade. Check
  it with per-tick bone speed at each transition.
- Ragdoll: `PhysicalBoneSimulator3D` with PhysicalBone3D nodes (made in the editor),
  `physical_bones_start_simulation()`, `influence` for partial blends.
- Import: Animation FPS, explicit loop modes, Import As → Animation Library for shared clips.
  Godot: `import_edit.py set clips.glb.import --importer animation_library --sub
  "animations::walk::settings/loop_mode=1"` then reimport (engine-godot
  `references/import-settings.md`).
  `RootMotionView` in the editor checks root motion against the floor.
- All of it is built as nodes in the character's scene in the open editor (scene-first rule);
  scripts only feed parameters.
