---
name: doors
description: Doors and entries in games — hinged, double-action, sliding, revolving, shutters, hatches, gates and airlocks; sizes and clear width against the character capsule and navmesh; push vs pull and how the character approaches (stand-off spot, hand, grip on lever, knob or push bar); opening angles, speeds, closers, slams; physics vs animated doors with synced interactions; locks, keys, barricades, breaching; AI through doors (nav links, door state, crowds, blocked paths); curtains parted by the body; car doors and getting into and out of cars, trucks and buses step by step with timings; audio, save state, accessibility, pitfalls, test cases checked by doors_check.py, Godot/Unity/Unreal setup. Use when designing, building, animating or reviewing any door, gate, hatch, curtain, vehicle door or vehicle entry and exit.
user-invocable: false
---

# Doors and entries

A door is four things at once: a gap sized against the bodies that use it, an interaction the
hand must meet, a moving obstacle that physics and navigation must agree on, and a state the save
keeps. Size it first, pick physics or animation second, then build the approach, the AI link and
the save. Check with `${CLAUDE_SKILL_DIR}/scripts/doors_check.py` (stdlib Python, Bash). Long
tables: `${CLAUDE_SKILL_DIR}/references/types.md` (types, sizes, codes, speeds, games),
`${CLAUDE_SKILL_DIR}/references/cars.md` (car doors, getting in and out by vehicle),
`${CLAUDE_SKILL_DIR}/references/engines.md`. Types — hinged, double, double-action, sliding,
pocket, revolving, rolling shutter, hatch, gate, airlock, blast door — each with numbers and a
build choice in types.md. Grips: hands skill; body numbers: human-biomechanics; seats and driving
poses: traversal; cloth: soft-bodies; hinge joints: rigid-body-physics; agents: game-ai.
(working) = starting point, [U] = unverified.

## 1. Size against the body

- Leaves: US 30–36 × 80 in (0.76–0.91 × 2.03 m), UK internal 762 × 1981 mm. Accessible clear
  width ≥ 0.813 m (32 in), measured from the stop to the leaf face with the leaf at 90° (ADA).
- Clear width = W − max(0, w·cos θ) − t·sin θ − hardware (`predict clear`): 0.869 m for a
  0.914 m × 45 mm leaf at 90°. A capsule fits from clear ≥ 2r + margin: r 0.3 in a 0.9 m door
  needs 76° of opening — a body that goes through earlier clips the leaf.
- Godot's default capsule and agent radius (0.5) need 1.0 m and fit no ordinary door: use r
  0.25–0.35 for humans. The navmesh rounds the radius up to a multiple of the cell size — cell
  0.25 turns r 0.3 into 0.5 and seals the door (`--cell`).
- People turn their shoulders below ~1.3× shoulder width (Warren & Whang) and slow ~1.8 s before
  a 0.9× gap; a 0.813 m door is 1.74× a 1.80 m man's shoulders — walk straight through. Mechs,
  bosses and co-op pairs need their own sizes (Liz England's door problem; level-design §1).

## 2. Push or pull: the approach

- **Signifiers**: a flat plate says push, a bar handle says pull (Norman); hardware that lies is a
  "Norman door" and players misread it too. Handles 0.864–1.219 m (ADA), 0.9–1.05 m (UK); levers
  work with one hand and no wrist twist, round knobs do not.
- **Stand-off** (`predict standoff`): at 80% arm reach a 1.75 m character reaches 0.33 m forward to
  a 1.0 m handle, so the body centre stands 0.39 m from the door face, half a shoulder width from
  the handle toward the hinge; a handle too low for any forward reach needs a lean.
- **Push**: centre line, latch-side hand on the lever or plate, the leaf swings away and the body
  follows (+1.96–2.88 s per door in a drill, Son 2020).
- **Pull**: the leaf swings into the body — from the front spot a 0.9 m leaf hits a r 0.3 capsule
  after ~8°. Start from the clear spot beside the latch edge with the hinge-side hand (ADA keeps
  455 mm beyond the latch and 1525 mm of depth free; UK 300 mm) or step back ~0.5 m while
  pulling. Pull doors cost +3.91–4.43 s, about twice push.
- **Hand**: grip from the hands skill (lever: hooked fingers; knob: twist; pull handle: power grip;
  push bar: flat palm), IK to a handle socket, held while the door moves (`follow`), released once
  the gap passes `min_angle`. Warp to the stand spot over 0.2–0.3 s (working) while turning to
  face the door (Motion Warping, `MatchTarget`, root motion); never snap.

## 3. Angles, speed, closing

- Time = angle / speed: 90° at 90°/s is 1.0 s. Half-Life 2's `prop_door_rotating` defaults to 90°
  at 100°/s and opens away from the user — toward them if that side is blocked.
- Closers (ADA): ≥ 5 s from 90° to 12° (≤ 15.6°/s); spring hinges ≥ 1.5 s from 70° to 0°; latch
  speed in the last 10–15°. Automatic doors: ≥ 1.5 s to 80° at full power, ≥ 3 s low energy,
  hold open ≥ 5 s (ANSI A156.10/.19).
- A 30 kg 0.9 m leaf has I = mw²/3 = 8.1 kg·m²; 18.7 N·m (5 lbf at the handle) swings it 90° in
  1.17 s and leaves 29 J — a slam (`predict swing`). Add damping or a closer curve; detents are
  small torque wells (working); a slam ends in a latch click and a 1–2° bounce (working).
- Powered doors stop and reverse on contact (16 CFR 1211.7); crushing is a stated design choice.

## 4. Physics door or animated door

| | Physics (hinge joint) | Animated (kinematic, synced) |
|---|---|---|
| Use when | bodies and props push it, partial opening, peeking, mouse-drag opening (Amnesia), barricades, kicks | scripted beats, multiplayer authority, many AI users, a hand clip that must match |
| Setup | hinge at the leaf edge, limits 0–open angle, mass 20–45 kg (working), damping, motor or spring to close | kinematic body moved in physics steps; the angle curve on the interaction's timeline |

Cap the door's push on characters, mass ratios ≤ 10:1 (rigid-body-physics); characters push it
with a capped impulse; kicks and blasts switch an animated leaf to physics on one frame with its
angular velocity. HL2 pushes props under 32 kg aside; heavier ones block.

## 5. Locks, breaching, prompts

- Locked must read different from fake: a handle rattle and lock sound (HL2 plays a locked
  sequence), a lock icon and the verb; fake doors get no handle. Keys, cards, hacks: shape plus
  colour on the prompt, never colour only. Barricades are props or boards with HP (Amnesia's
  monsters break them); breaching detaches the leaf as a rigid body (destruction-vfx), kicks hit
  the latch side; look under first (Ready or Not's optiwand; Rainbow Six Siege reinforcements).
- Prompt within 1.5–2 m and ±60° of facing (working) with the side's verb and the live binding
  (controls-camera); tap to open, holds only for lockpicks and barricades (≤ 1 s, toggle option);
  the door moves within 0.1 s of input (working). Door clips can hide loading (Resident Evil 1996).

## 6. AI through doors

- Door state lives on the navmesh: closed = a link with extra cost, locked = link off, open =
  normal. Links don't move agents — handle the link event: claim, open, wait, walk. Never block
  with an obstacle that cannot re-route (Godot NavigationObstacle3D only bakes or steers).
- One opener at a time: the first agent claims the door (Smart Object slot), others wait 1–1.5 m
  back (working). HL2 NPCs stand 64 in (1.63 m) off the door and 24 in from the hinge, face it,
  and the opening leaf spawns a blocker that keeps NPCs out of its swing. Allies never park in a
  doorway; the player has right of way.
- Crowds: ~1.3 persons/s per metre of effective width (SFPE, 0.15 m off each side) → 0.92
  persons/s through a 1 m door. Stealth: opening is a hearing event (louder fast or slammed), a
  closed door muffles sound (procedural-audio), light spills through an open one.
- Stuck at doors = link not handled, radius rounded past the gap, or the leaf parked in the path
  (game-ai `references/techniques.md`); prove it with `aipass`.

## 7. Curtains

- **Cloth**: soft-bodies — pin the top row, collide with capsules on the walker's bones (Unity
  Cloth only with assigned spheres and capsules and pushes nothing back; Godot SoftBody3D
  precision ≥ 5 on Jolt). Shoulder push when walking, hand sweep when slow (working; [U]).
- **PVC strips**: 200 × 2 mm strips for openings up to 3 m high, 300 mm for 3–5 m, 400 mm above
  5 m (not for people); overlap 50% by default (40–95%). A 1 m door with 200 mm strips at 50% has
  9 strips; a body pushes ~7; a 2.2 m strip weighs ~1.1 kg and swings with a 2.43 s period
  (`predict strips`). Top-hinged chains with spring return.
- **Beads**: strings as chains (2.47 s at 2.2 m) against the walker's capsule, a clack per
  contact; simulate only strings near the body.

## 8. Car doors and getting in

- Front doors hinge at the A-pillar with a check link of one or two intermediate stops; max angle
  60–75° [U]. At 70° a 1.1 m door leaves 1.03 m to the B-pillar and juts 1.03 m; with 0.6 m beside
  the car it opens 33° (`predict cardoor`). Scissor, gull-wing, sliding doors: `references/cars.md`.
- In 3.0 s (control group), 2.7 s (high BMI), 4.3 s (older); out 3.0, 4.4 and 5.3 s (IMU study,
  93 people). Buttocks-first
  (sit, then swing the legs in — older people prefer it) or head-first; hands help in > 65% of
  observations; exits injure more than twice as often. Sequences per vehicle: cars.md.
- `predict car` (Okane mock-up): a 1.80 m adult ducks 0.50 m under a 1.33 m door top, leans 34°
  to sit on a 0.595 m H-point, and needs ~91° of hip flexion to step over a 0.40 m sill standing.
  H-point vs standing hip picks the set — deep (sports car), sit (sedan), slide (SUV, minivan),
  climb (truck, bus); trucks: first step ≤ 0.609 m, three limbs on (49 CFR 399.207). Per door: a
  stand spot, handle socket, roof-rail target, seat marker; one synced clip drives door and body.

## 9. Audio, save, accessibility

- Sounds: latch release, creak scaled by angular speed, close thud plus latch click, locked
  rattle, slam above an edge-speed threshold, detent clicks on car doors; 3+ variations; an open
  door changes occlusion between rooms (procedural-audio).
- Save per door: id, state (closed / ajar angle / open / locked / broken / barricaded) as deltas
  from the level (save-system); on load set the angle, zero velocity, then the nav link.
- Tap not hold, a toggle for every hold, an auto-open option, locked shown by icon, text and sound,
  no timed door puzzles without an assist (accessibility skill).

## 10. Reads wrong

| What the viewer sees | Usual cause | Fix |
|---|---|---|
| Hand closes on air beside the handle | no warp to the stand spot; no socket | warp to `standoff`, IK to the socket; `grab` ≤ 2 cm |
| Pull door swings through the body | front-spot pull without a step back | clear spot or step-back clip; `penetration` ≤ 2 cm |
| Walks through a half-open door | movement not gated by the gap | gate by `min_angle`; `passage` |
| Door ahead of or behind the hand | door curve not on the clip's timeline | one timeline; `follow` ≤ 5° |
| AI stuck or dancing at doors | link not handled, radius rounding, two openers | link event, radius by cell, claim slot; `aipass` |
| Door shoves the player, slams or never latches | heavy door vs capsule; constant torque | cap the push, damping, closer curve; `swing` |
| Head through the car roof | no duck for that door top | `predict car`; head–roof probe ≥ 3 cm |

## 11. Acceptance (lab gyms)

| Check | Gym | Command | PASS |
|---|---|---|---|
| Gap | leaves at 30/60/90°, each agent capsule | `predict clear` vs a shape cast | passes from `min_angle` only; nav corridor > 0 |
| Hand on handle | push and pull, both sides, 1.60/1.75/1.90 m | `grab --when grabbing` | ≤ 0.02 m |
| Door follows hand | open by interaction | `follow --when holding` | ≤ 5° |
| No clipping | pull from the front spot; run into a push door | `penetration --radius r` | ≤ 0.02 m |
| Open before passing | walk into an opening door | `passage` | angle at crossing ≥ `min_angle` |
| Closing | door with a closer | `swing --from 90 --to 12 --min-s 5` | ≥ design time (5 s for an ADA closer) |
| AI | 5 agents through closed doors both ways, one locked | `aipass --max-stop 3` | all pass, no stop > 3 s, none at the locked door |
| Curtain | walk through strips, beads, cloth | soft-bodies `settle`, `strain` | rest ≤ 10 s, strain ≤ 2%, no pass-through |
| Car | every door of every vehicle class, in and out | traversal `contact`; clip time | hands, hips, feet ≤ 0.02 m; head ≥ 0.03 m below the roof; time ±20% of design |

## 12. Engine notes

**Godot 4.6/4.7** — AnimatableBody3D (`sync_to_physics` on) for animated leaves; RigidBody3D +
HingeJoint3D (limits off by default; velocity motor, `motor/max_impulse` × tick rate = torque under
Jolt) for physics leaves; NavigationLink3D `enabled`/`enter_cost` + `NavigationAgent3D.link_reached`;
TwoBoneIK3D with a pole for the hand; Area3D for prompts and auto-open. **Unity 6** — kinematic
Rigidbody `MoveRotation` or HingeJoint (limits, spring, motor, break force); NavMeshLink
`Activated`, carving NavMeshObstacle (a frame late); `MatchTarget`, Two Bone IK. **Unreal
5.6–5.8** — Physics Constraint hinge with an angular drive; Contextual Animation + Motion Warping;
NavLinkProxy smart links and Smart Object slots. Detail: `references/engines.md`.
