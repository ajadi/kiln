---
name: traversal
description: Physics and anatomy of how a human character moves through and uses the world — jumps by approach (standing, forward, walking, running, sprinting) with takeoff foot and speed rules, obstacle moves by height (step, vault, clamber, climb-up, jump-grab), hanging from ledges and grip endurance, climbing, crawling and squeezing through openings, balance and stepping (capture point, slips on ice), falls and landing tiers, carried load (clothing, armour, packs, weapons) and its effect on gait, speed and stamina, the joint range clothing and armour take away and how held items change the whole body, sitting on chairs, rocks and vehicles, getting in and out, driving and riding poses, wading, swimming and floating with gear, backpacks (loads, posture, bounce, access), with human numbers, detection and selection rules, exact test cases checked by traversal_check.py and Godot/Unity/Unreal setup. Use when designing, animating, building or reviewing jumping, parkour, climbing, hanging, crawling, falling, encumbrance, sitting or vehicle entry and driving poses.
user-invocable: false
---

# Traversal and body–world interaction

Every move here is a choice made from numbers: approach speed picks the jump, obstacle height
picks the move, fall height picks the landing, load picks the gait. Put the tables in data,
select by them in code, author a clip per row, and prove the selection with
`${CLAUDE_SKILL_DIR}/scripts/traversal_check.py` (stdlib Python, Bash). Base anatomy (proportions,
joint ranges, gait, simple jumps and landings): human-biomechanics skill; clip contracts and the
jump clip family: animation skill. Values marked (working) are starting points for a 1.80 m adult.

## 1. Body numbers (1.80 m man, ANSUR II means)

Shoulder width over the deltoids 0.52 m (95th pct 0.57), biacromial 0.42; chest depth 0.26; hip
breadth 0.35; head 0.155 × 0.20; shoulder height 1.48; crotch 0.87; knee 0.50; standing grip reach
2.19 m (1.219 × stature), fingertips ~2.29; mass ~90 kg. Popliteal height (seat-to-floor comfort):
men 39/43/47 cm (5th/50th/95th), women 35/39/43 cm.

## 2. Jumps by approach

| Type | Approach (working) | Takeoff | Numbers |
|---|---|---|---|
| standing vertical | ≤ 0.3 m/s | two feet, countermovement (CoM dips ~0.36 m: 0.7 s down + 0.3 s push, ~1 s total) | median men 20–24 0.49 m, 35–39 0.44; women 0.30–0.32 m; arm swing +10%; v₀ 2.5–3.1 m/s, airtime 0.5–0.64 s |
| standing broad | from idle, aimed | two feet, takeoff 31–39°, ~3.4 m/s | men 2.25 ± 0.24 m, women 1.79 ± 0.22 m (incl. ~0.8–0.9 m of leg reach at takeoff and landing) |
| walking | ≤ ~2.2 m/s | one foot = the stance foot | small hop, keeps walking speed (no published data — tune) |
| running | ≤ ~6 m/s | one foot = the stance foot; CoM lowered over the last two strides; knee bends only ~38°; contact ~0.11 s elite (0.15–0.25 s average, UNVERIFIED) | keeps 0.85–0.90 of speed and adds 2–2.5 m/s up: jog 3 → 1.1–1.4 m of CoM flight, run 6 → 2.2–2.75 m; foot-to-foot gaps ≈ 1.8 m jogging, 3–3.5 m running |
| sprinting / long jump | > 6 m/s | one foot, takeoff angle falls with speed to ~20° | sprint 7.5 m/s → ~4.3 m gap; elite 8.63 + 3.05 m/s at 20°, speed loss ~10% |

- A jump played the same at every speed is the classic failure (standing squat while running).
  Pick the type by horizontal speed at the input frame, take off from the foot on the ground,
  keep horizontal speed for running jumps (`predict runjump`, `jumps` check).
- A fixed takeoff angle is wrong at low speed: 20° at 3 m/s lifts the CoM 5 cm. Keep the
  approach speed and add vertical speed instead (`predict runjump --vy`).
- The arc is physics: v₀ = √(2gh) from the design apex; viewers spot horizontal-velocity errors
  and added acceleration far more easily than vertical ones (Reitsma & Pollard 2003) — never add
  horizontal speed mid-air (a takeoff boost like Celeste's is a platformer choice, not realism).
- Responsiveness beats realism for the standing jump's ~1 s countermovement: keep a short dip
  (0.1–0.25 s, working) and let the player regain control during the landing follow-through.
  Coyote time ~0.1 s and jump buffering make it feel fair (Celeste `JumpGraceTime` 0.1 s).
- Landing heavy or light by landing speed (Unreal Game Animation Sample: JustLandedLight /
  JustLandedHeavy); scrub the landing clip by distance to the ground (distance matching).

## 3. Obstacles by height (top of obstacle above the feet)

| Height | Move | Notes |
|---|---|---|
| ≤ ~0.5 m (knee) | step-up / step-over | no hands |
| ~0.5–1.2 m (to waist/chest) | vault (speed, lazy, kong, dash) or step-on vault | hands on top, keep speed |
| ~1.2–1.5 m (to shoulder) | clamber / mantle: hands on, one leg up, over | slows to a stop on top or drops over |
| ~1.5–2.2 m (to grip reach) | climb-up: grab, pull, mantle | from standing |
| ~2.2–2.8 m | jump-grab (grip reach + jump) | 2.49 / 2.64 / 2.79 m with a 0.30 / 0.45 / 0.60 m jump |
| > ~2.8 m | wall-run step or blocked | parkour wall run-up uses an intermediate run speed |

Bands are anthropometric heuristics (no study gives technique by height) — set the game's own
table in data (`predict move`, `moves` check). Police agility tests treat a 1.83 m wall as a fence
to clear in 5–20 s.

**Detection** (Dying Light replaced 50 000 hand-placed grab points with a real-time geometry scan
ahead of the player that picks climb, vault or slide from speed and position — "the biggest
turning point" of their development): shape-cast forward at chest height for the wall normal; ray
down from reach height 0.1–0.2 m into the wall for the top; check the top's slope; shape-cast the
capsule on top for room; height = top − feet → the band. Delay the parkour response slightly when
the player can't see the edge (Dying Light).

## 4. Hanging, climbing, shimmying

- Grip endurance (Frey-Law & Avin): t = 33.55·f^−1.61 s at a fraction f of max grip. Two-hand dead
  hang: an 85 kg person with 50 kg grip (f 0.85) ≈ 44 s; 70 kg with 60 kg grip ≈ 80 s. One-hand
  hang needs grip ≥ body weight — not for average characters. Measured: fit untrained men 62–97 s,
  never-trained 10–30 s.
- Games limit hang and climb with stamina (Celeste: 110 points, holding 10/s, climbing 45/s, a
  climb-jump 27.5, tired at 20; BotW: linear drain, ladders free). Show it.
- Dropping from a full hang lowers the fall by the reach: from a 3 m ledge 0.81 m (3.98 m/s
  impact) instead of 3 m (7.67 m/s).
- Hands on the ledge with two-bone IK and a pole; body swings under the hands; feet find the wall
  if it is there.
- Ladders cost 17% more oxygen vertical than at 75°. Climb, shimmy and climb-up times: no sourced
  numbers — tune in a gym (working: shimmy ~0.5 m/s, climb-up 1.0–1.5 s).

## 5. Crawling, crouching, openings

- Speeds: stoop-walk under a 1.2 m ceiling 1.01 m/s (24% slower than upright); hands-and-knees
  0.50–0.84 m/s; hands-and-feet 1.2 m/s; low (army) crawl 0.77 m/s; knee-walk 0.32 m/s. People
  slow after ~9 m and rarely crawl more than ~75 m.
- Openings: egress window ≥ 0.51 × 0.61 m (20 × 24 in), crawl-space access 0.41–0.46 × 0.61 m,
  manholes ≥ 0.61 m; arms-down shoulders need ~0.52 m, arms overhead pass ~0.46 m.
- Capsule check: passes w × h if w ≥ 2r and h ≥ H (`predict fit` gives the best pose). Shrink the
  capsule from the top (move it down by half the change) and shape-cast up before standing again.

## 6. Balance and slips

- Extrapolated CoM / capture point x + v·√(z/g): 0.32 m per m/s at CoM height 1 m. Without a step
  a person survives a push of ~0.47 m/s forward, ~0.19 m/s backward, ~0.63 m/s sideways (feet
  0.3 m apart), ~0.16 m/s sideways on a 10 cm beam; a late step must land e^(ω₀T) farther (2.2×
  after 250 ms). So: stumble steps sized by the capture point, a fall when it leaves reach
  (`predict capture`, `balance` check).
- Walking needs a friction coefficient of ~0.2 (0.09–0.22); slip chance is 50% when need exceeds
  supply by only 0.006. Ice 0.02–0.09; rubber on dry asphalt 0.6–0.7. Max acceleration μ·g, stop
  from 6 m/s in 3.1 m at μ 0.6 vs 18 m at 0.1; steepest standable slope atan(μ). Hook surface μ
  to the elements-materials skill (wet, frozen).

## 7. Falls and landings

| Fall | Impact | Landing (working tiers) |
|---|---|---|
| ≤ 1 m | ≤ 4.4 m/s | none (continue) |
| 1–2.5 m | 4.4–7 m/s | soft: forefoot, knees absorb |
| 2.5–4 m | 7–8.9 m/s | roll |
| 4–8 m | 8.9–12.5 m/s | hard landing, stagger, damage |
| > 8 m | > 12.5 m/s | lethal or heavy damage (half of real falls are fatal at ~15–20 m) |

- Peak force falls with technique: from 0.75 m traditional 5.2 BW, precision 3.2, roll 2.9;
  traceurs 2.5/3.6 BW from 0.44/0.89 m vs untrained 4.4/7.4. Keeping the average force at N body
  weights needs a stopping distance d = h/(N − 1) (2 m at 5 BW: 0.5 m) — that is the squat or roll
  the landing clip must show (`predict fall`, `landings` check).
- Game damage: Minecraft 1 HP per block beyond 3; soft surfaces (hay 20%, water 0) cut it. Show
  the tier before it hurts (camera, sound).

## 8. Carried load

- Gait under load: shorter steps, longer double support, more knee flexion, more forward trunk
  and head lean; spinal muscles jump at ~47 kg. Load close to the body's CoM is cheapest and most
  upright; chest armour restricts breathing.
- Energy (Pandolf): M = 1.5W + 2(W + L)(L/W)² + η(W + L)(1.5V² + 0.35VG); 80 kg at 1.34 m/s:
  336 W unloaded, 402 W with 20 kg, 503 W with 40 kg; η: road 1.0, dirt 1.1, brush 1.2–1.5, sand 2.1,
  snow 2.5–4.1 (`predict load`).
- Plate armour (15–25 kg real field harness; studies use 30–50 kg): walking costs ×2.1–2.3,
  running ×1.9 (the same weight as a backpack +70% / +50%) — the extra is swinging armoured limbs;
  stride kinematics barely change; sustainable speed drops to ~0.63×. Armour does not make people
  waddle — it makes them tire.
- Speed vs load (field test): 95 / 91 / 87 / 83% of unloaded speed at 10 / 20 / 30 / 40% of body
  weight, falling faster beyond — a usable encumbrance curve.
- Weapons: rifle 3–3.5 kg; moving its CoM 7 cm forward raises support-arm load > 30%; hold-aim
  fatigue ~1–3 min (UNVERIFIED) → sway grows with hold time and load (Arma: load speeds sway
  growth and slows recovery).
- Design: thresholds (free → encumbered → overloaded) shown in the body (lean, shorter stride),
  penalties on stamina and sway before hard speed caps (Skyrim: over the limit = walk only, no
  fast travel; Kingdom Come: no sprint/jump, speed ∝ excess; Death Stranding: cargo balance).

## 9. Clothing, armour and held items

Gear takes joint range away, and that has to be known before anyone animates (live: armour plates
stopped the elbow at 56° — 39% of normal, below the ~130° everyday tasks need — and a pauldron
stopped the shoulder at 60°; found only when the arm clips were made).

- **Measure the dressed model first**: sweep each joint in Blender until parts collide, write the
  stops (`{"stops": {"elbow_flex": …}}`) and run `rom --moves run,crouch,…`. Needs (working where
  not sourced): elbow ≥ 130°, shoulder flexion and abduction ≥ 130° (≥ ~160° to climb), hip ≥ 95°,
  knee ≥ 120° (≥ ~140° to crouch or kneel; a deep squat reaches ~157°), ankle dorsiflexion ≥ 10°
  to squat. Normal adult: elbow 145–150°, shoulder flexion ~170°, hip ~130°, knee ~140°, ankle 13–14°.
- **Real armour solved joints**, copy it: overlapping lames riveted or laced (sliding rivets), fan
  wings on the knee couter/poleyn, a besagew disc over the armpit with mail filling gaps, cut-away
  joint pits, padding kept thin at joints; a full field harness (15–25 kg) let the wearer run and
  jump. Spacesuit joints keep volume constant with gores and convolutes — past that, bending costs
  work.
- **What real gear costs**: body armour −16% shoulder cross-body reach, −5% hip, −17° shoulder
  extension; police kit −13 to −42% on mobility tasks; firefighter gear cuts shoulder, neck and
  trunk range and lengthens contact times; heels and stiff boots cut ankle range and the hip and knee
  compensate; tight hems limit stride (hobble skirts needed slits and pleats); gloves cut grip
  23–54%; night-vision goggles shorten steps 7–17%; mass on the feet costs 7–10% energy per kg
  (thigh 4%).
- **Held items change the whole body**: two-handed carry (rifle, box) stops arm swing — add trunk
  counter-rotation (still arms cost +5–12% energy and raise the body's twisting moment 63%); one-hand
  loads (10–20% of body weight) bend the trunk away from the load, abduct the free arm and narrow
  steps; a box carried in front leans the trunk back and hides the feet; a holster or scabbard makes
  stride asymmetric toward its side; aim error grows while walking (+0.66 cm per cm of standing
  error, more with longer double support).
- **Per item** (with the implications skill): grip sockets and hand pose (grip type, finger
  ranges, handle diameter: hands skill), second-hand IK target for two-handed items; its locomotion set or upper-body overlay with a bone mask (unarmed,
  pistol, rifle, two-handed melee, carry-object — Lyra links one animation layer per weapon); arm
  swing on or off; posture from the load; speed modifier and aim sway while moving; clearance through
  run, crouch, climb, kneel and roll — scabbards against the legs, back-slung items against the
  head; draw and stow with the stowed place (no over-the-shoulder draw for long blades — a modern
  invention; real ones came off the back first).
- **Loose gear moves on**: coats, skirts, capes, straps and pouches follow through after stops and
  turns (soft-bodies skill, spring bones); a Foley cloth pass and footwear-matched steps carry
  weight.
## 10. Sitting

- Seat heights: chair 43–46 cm, counter stool 61–66, bar stool 76 (needs a footrest ~29 cm up).
  Comfort: seat ≤ popliteal height + shoe (1.80 m man ~47 cm with shoes; on a 30 cm rock his knees
  rise ~17 cm, thighs tilt ~19°).
- Sit-to-stand: 1.1–1.5 s per transition at maximum speed (five-times test 11–15 s for older
  adults); normal pace 1.5–2.5 s (working); trunk leans forward ~40–50° at seat-off (UNVERIFIED);
  hands push on low seats, for heavy or armoured characters.
- Pattern (Unreal Smart Objects / Contextual Animation, furniture markers): a seat marker gives
  position and facing; the character reaches an approach point, warps or root-moves into enter,
  loops, exits; IK fixes hips, hands and feet on irregular seats (rocks, crates, ledges).

## 11. Vehicles: getting in, driving, riding

- Cars: steering ratio 12–20:1; wheel angle = road-wheel angle × ratio (10° → 150° at 15:1; a 10 m
  radius at 2.7 m wheelbase → 15.1° road → 227° wheel); lock-to-lock ~2.9 turns at ±35°. Hands at
  9 and 3, wrists straight; seated hip angles 90–115°, knees 100–140°, elbows 85–160° (UNVERIFIED).
  Gaze leads steering by ~1 s toward the bend's tangent point (UNVERIFIED).
- Getting in and out: in 3.0 s (control group), 2.7 s (high BMI), 4.3 s (older adults); out
  3.0, 4.4 and 5.3 s (IMU study, 93 people); fully timed tasks 5.9–6.4 s (fastest vehicle means,
  Bodenmiller 2002). Older people sit first and swing the legs in rather than step in head-first;
  hands help in > 65% of observations; exits injure more than twice as often. The head ducks
  stature + 3 cm − door top (1.80 m under 1.33 m: 0.50 m); stepping over a 0.40 m sill standing
  needs ~91° of hip flexion. Truck cabs: first step ≤ 0.609 m, three limbs on the vehicle. Steps,
  timings and body demands per vehicle: doors skill (`predict car`).
- Motorcycles: lean tan φ = v²/(g·r) (50 km/h on r 30 m → 33°, needs μ 0.66; 100 km/h on 100 m →
  38°); max lean atan(μ) ~45–55°; wide tyres add 6–8°; counter-steer briefly to start a lean.
  Seat heights: cruiser 0.64–0.68 m, sport 0.80–0.86, adventure 0.85–0.87. Postures: sport crouch,
  standard upright, cruiser feet forward and leaning back. Mount by swinging the leg over behind
  the seat.
- Animation: per-door enter points with root-motion or warped clips; character attached to the
  seat (collision off); hands IK'd to grip targets on the wheel or bars that the vehicle rotates;
  head look toward the turn; rider lean follows the bike plus a little extra (hang-off).
- Ragdoll ejection on crashes by a speed-change threshold (working ~40–50 km/h unbelted).
- Riding animals (horses, camels, mounts): riding skill.

## 12. Water: wading and swimming

- **Floating**: body density ≈ 0.98 with full lungs; buoyancy is a breath: +1.4 kg (75 kg man, 15%
  fat, fresh water) with lungs full, −2 kg after a normal exhale; lean men sink, most people (93%)
  float; sea water adds ~2 kg. Above water is only V − m/ρ_water (~1.4 L fresh — the top third of
  the head; ~3.4 L sea — down to the nose), so a resting float needs sculling; legs sink first,
  the body settles vertical; one 0.5 L breath bobs ~0.5 kg (`predict float`).
- **Armour and gear**: plate keeps ~87% of its weight in water (13–22 kg for 15–25 kg of steel),
  far more than lung buoyancy — armoured characters sink unless swimming hard; wet cotton weighs
  4× dry dripping (2.5× after 30 min) but almost nothing while submerged — apply the penalty on
  climbing out and dry it over minutes (`predict float --gear-mass`).
- **Wading**: speed by depth and current (Postacchini) — still water 0.3 m → 0.96 m/s, 0.5 → 0.79,
  0.9 → 0.63; at 0.35 m people slow ~40%, steps shorten ~35%, side sway +70–130%; use land speed
  below ~0.1 m (`predict wade`). Drag on legs ½ρC_dAu²: at 1 m/s ~70 N knee-deep, ~210 N chest-deep.
- **Swimming**: recreational crawl 0.5–1.0 m/s (elite 1.7–2.2), breaststroke slower; play the
  stroke cycle at speed / stroke length (1.2–1.6 m recreational, ~30–38 cycles/min); treading
  water is cheap with a breaststroke kick (eggbeater for experts); energy 3.4× walking per km;
  elite underwater dolphin kick 2.4 m/s.
- **Breath**: untrained holds ~30 s after a normal exhale, ~55 s after a full breath (range
  20–270 s); water below ~15 °C cuts it to seconds and triggers a 2–3 min cold-shock gasp; air
  spaces halve at 10 m — ear pressure from the first metres.
- **States and set**: wading (feet down, legs push water), surface swim, tread, underwater,
  enter (step, jump — 1 m → 4.4 m/s, dive), climb out (mantle from water, §3 bands); 8–12 clips,
  0.3–0.5 s wade-to-swim blend at chest depth, foot IK off while swimming, head-vs-surface ray
  picks surface or underwater. Stamina or oxygen meters (BotW swim stamina; GTA lung capacity).

## 13. Backpacks

- **Loads**: hikers 20–25% of body weight on long trips, militaries 33–40% (peaks 60–70%);
  capacity ~0.2–0.3 kg/L packed (35 L → 7–10 kg, 65 L → 13–20 kg).
- **Hips vs shoulders**: the "80% on the hips" rule is a rule of thumb — one measured study put
  ~70% on the shoulders even with a hip belt; hips tolerate ~2× the pressure; strap angle 24–30°;
  over body armour the hip belt can't cinch.
- **Posture**: keep the pack CoM close and high over the hip belt; the trunk leans to balance it —
  ~6 / 10 / 13° for 10 / 20 / 30 kg at 18 cm behind the spine (75 kg man) (`predict packlean`).
- **Bounce**: the pack is a mass on a spring — 20 kg on a soft suspension (k 5 N/mm) resonates
  near 2.5 Hz and moves ~3× the body at a 2.8 steps/s run; tight compression straps (stiffer) or
  damping cut it; spring bones (Godot SpringBoneSimulator3D, Unreal AnimDynamics) for the look
  (`predict packbounce`).
- **As a system**: capacity and weight (Tarkov grids — a bag that takes as much space as it
  holds gains nothing; Skyrim/KCD weight limits), access time (take off to open 4–8 s, pouches
  < 1 s, working), visible fill state, put on / take off / drop / stash animations, clearance with
  the helmet when prone and with arm swing, climbing, crawling (take it off for tight openings),
  swimming (gear weight in water; dry bags float, metal sinks), seats and vehicles (games usually
  hide it — state the choice), a jetpack's thrust line through the CoM (flight skill).
## 14. Lab gyms

| Check | Gym | Command | PASS |
|---|---|---|---|
| Jump types | jump from idle, walk, run, sprint, both feet in phase | `jumps` (events) | type by speed, takeoff = stance foot, run jumps keep ≥ 85% speed |
| Jump height | standing jump | `jump --apex` | apex within 5% |
| Obstacles | course of 0.4/0.9/1.3/1.9/2.5/3.2 m obstacles | `moves` | move matches the table at every height |
| Landings | drops of 0.5/2/3.5/6/10 m | `landings` | tier matches the table |
| Hands and feet on contact | ledge hang, ladder, steering wheel, motorbike bars, seat | `contact --when` | hand/foot/hip within 2 cm of its target |
| Balance | beam, push recovery | `balance` | CoM inside support except while stepping |
| Openings | vent, window, crawl tunnel | `predict fit` + `penetration` | passes in the predicted pose, no capsule penetration > 2 cm |
| Load | walk with 0 / 20 / 40% body weight | speed and stride probes | speed curve as designed; lean and stride visible |
| Gear range | joint sweep of the dressed model in Blender | `rom --moves …` | every joint reaches what the move sets need |
| Held items | run, crouch, climb, kneel with each held/worn item | clearance probe + `penetration`; arm swing on/off as designed | no clipping > 2 cm; posture changes as designed |

## 15. Review checklist

- [ ] Jump, obstacle, landing, load and seat tables in data with sources or "(working)".
- [ ] Jumps per approach with L/R starts; speed kept on run jumps; arc from physics.
- [ ] Ledge detection scans geometry; no hand-placed grab points as the only source.
- [ ] Hang/climb limited by visible stamina; drop-from-hang reduces the fall.
- [ ] Capsule shapes for crouch/crawl with a stand-up clearance check.
- [ ] Stumble/fall from the capture point; slips from surface μ.
- [ ] Landing tier shows a stopping distance that matches its force (squat, roll).
- [ ] Load changes posture and stamina before speed caps.
- [ ] Dressed model's joint stops measured and `rom` passes before rigging; held items have grips, overlays, clearance and a stowed place.
- [ ] Seats and vehicles: markers, approach points, IK for hands/feet/hips, attach and detach.
- [ ] Lab gyms pass.

## 16. Engine notes

**Godot 4.6/4.7** — CharacterBody3D defaults: `floor_snap_length` 0.1, `floor_max_angle` 45°,
`floor_stop_on_slope`, `floor_block_on_wall`, `max_slides` 6, `wall_min_slide_angle` 15°;
`is_on_wall_only()` and `get_wall_normal()` for wall runs and wall jumps. ShapeCast3D
(`force_shapecast_update`, `get_closest_collision_safe_fraction`, `max_results`) for ledge and
clearance probes — test what it reports when it starts inside geometry. `CapsuleShape3D.height`
includes the caps (≥ 2·radius). Root motion on AnimationMixer (`root_motion_track`,
`get_root_motion_position`; velocity = basis × delta / dt into `move_and_slide`). IK (4.6+,
SkeletonModifier3D): `TwoBoneIK3D` (root/middle/end, target, pole — hands on ledges, wheels, bars,
feet on pegs), `ChainIK3D` → `FABRIK3D`/`CCDIK3D`/`JacobianIK3D`, `LookAtModifier3D`;
`SkeletonIK3D` is deprecated. Seats: disable the character's collision, `reparent(seat_marker,
true)` or a RemoteTransform3D; BoneAttachment3D for props on bones. Load as a BlendSpace axis with
cyclic sync; OneShot/Blend filters for upper-body layers. All built as nodes in the editor.

**Unity 6** — CharacterController (`stepOffset`, `slopeLimit`, `skinWidth`); `Animator.MatchTarget`
(root motion, base layer, one match at a time) for vault/mantle hand and foot targets; Animation
Rigging Two Bone IK (root/mid/tip, target, hint), Multi-Aim, Multi-Parent; `Transform.SetParent`
for seats.

**Unreal 5.6–5.8** — Motion Warping (notify windows on root-motion montages, Skew Warp/Scale,
"Add or Update Warp Target"; first window where the hand lands on a mantle); Game Animation Sample
traversal (vault, climb, drop chosen with Motion Matching, montages in the Default Slot); Smart
Objects and Contextual Animation (scene assets, selection criteria, IK windows) for seats and
interactions; Control Rig Full Body IK and IK Rig; Mover is experimental.
