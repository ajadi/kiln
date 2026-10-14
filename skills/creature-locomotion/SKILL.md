---
name: creature-locomotion
description: Physics of non-humanoid creatures and machines — Froude scaling of speed and timing with size, gait phase tables for 4/6/8 legs, duty factor and gait selection, Raibert foot placement and step triggers, swing/stance timing, heavy-mech weight cues and actuator motion, wall and ceiling climbing statics, leg loss re-gaiting, collapse and topple timing, review thresholds and engine implementation notes. Use when designing, animating or reviewing mechs, spiders, quadrupeds or any non-human walker.
user-invocable: false
---

# Creature and machine locomotion

Marked (derived) = computed from the formulas; (working) = heuristic to measure against.
h = hip height / leg length, g = 9.81 m/s². Ridden quadrupeds (rider, saddle, load): `riding` skill.

## Scaling: speed and timing grow with √h

- Froude number Fr = v²/(g·h). Walk→run at Fr ≈ 0.5; inverted-pendulum walking is impossible
  above Fr = 1; comfortable walking ≈ 0.2. Bodies of different size move alike at equal Fr.
- Stride (two steps) λ/h = 2.3·Fr^0.3 (Alexander). Stride period T = 0.734·Fr^−0.2·√h s (derived).
  Swing time ≈ 0.4·√h s at duty factor ~0.6.
- Square–cube: mass ∝ L³, actuator/bone section ∝ L² → big walkers stand upright on column legs.
- Never scale insect speeds by body length (spiders run > 70 body lengths/s) — use Froude.

| h (m) | v at Fr 0.2 | v at Fr 0.5 | stride at Fr 0.2 | stride period Fr 0.2 / 0.5 |
|---|---|---|---|---|
| 0.9 (human) | 1.33 m/s | 2.10 | 1.28 m | 0.96 / 0.80 s |
| 2 (light mech) | 1.98 | 3.13 | 2.84 m | 1.43 / 1.19 s |
| 3 (medium / spider) | 2.43 | 3.84 | 4.26 m | 1.75 / 1.46 s |
| 4.5 (heavy biped) | 2.97 | 4.70 | 6.39 m | 2.15 / 1.79 s |

## Gaits

Phase in fractions of a cycle; β = duty factor (share of cycle a foot is down). General wave rule:
rear-to-front lag on one side = (1 − β); opposite side offset 0.5 — it generates all of these.

| Gait | β | Phases | Min feet down |
|---|---|---|---|
| Hexapod tripod | 0.5–0.65 | {L1,R2,L3}=0; {R1,L2,R3}=0.5 | 3 |
| Hexapod tetrapod | ≈ 0.67 | L3&R2=0; L2&R1=1/3; L1&R3=2/3 | 4 |
| Hexapod wave | ≈ 0.83 | L3 0, L2 1/6, L1 2/6, R3 3/6, R2 4/6, R1 5/6 | 5 |
| Octopod alternating tetrapod (spiders) | 0.63–0.68 | {L1,R2,L3,R4}=0; {R1,L2,R3,L4}=0.5 | 4 |
| Octopod slow wave (heavy spider, derived) | 0.75 | L4&R2=0; L3&R1=.25; L2&R4=.5; L1&R3=.75 | 6 |
| Quadruped walk (lateral sequence) | ≥ 0.75 stable | LH 0, LF .25, RH .5, RF .75 | 3 |
| Quadruped trot | 0.3–0.6 | LF+RH 0; RF+LH 0.5 | 2 |

- Choose by β: ≥ 0.8 wave; 0.65–0.8 tetrapod; 0.5–0.65 tripod; < 0.5 running.
- In walkers, swing time stays roughly constant and stance shrinks with speed: with stroke S and
  swing time T_sw, β = S/(S + v·T_sw).
- Swing-foot speed = v/(1 − β) — at β 0.75 the swinging foot moves 4× body speed: high-β heavy
  gaits need snappy swings or lower body speed.
- References: spiders β ≈ 0.63–0.68 at 0.06–0.11 m/s, cycles 1.55–1.77 s; elephants keep a
  lateral-sequence walk up to 6.8 m/s and never gallop; BigDog (110 kg hydraulic) crawl 1 km/h,
  trot 5.3 km/h.

## Foot placement and step triggers

- Raibert: x_foot = v·T_stance/2 + k·(v − v_desired) from the hip's neutral point; k = 0 puts the
  foot under the hip at mid-stance (no net acceleration).
- Coordination: a leg may not lift while an adjacent leg swings; a rear leg's touchdown primes the
  leg in front to lift.
- Trigger (working): lift when foot-to-target distance > 0.3–0.5·S or the phase clock says so —
  only if no neighbour is swinging and the support polygon without this foot still contains the
  projected COM with margin.
- Step height 0.1–0.25·L (higher on rubble); sine/parabolic vertical arc; horizontal path eased,
  fastest mid-swing.

## Rules

1. Choose speed from Froude, not looks: heavy mechs cruise at Fr 0.1–0.3, walking capped at 0.5.
2. Scale every timing by √(h/0.9) relative to human data; lengths by h/0.9.
3. Drive the gait cycle from distance travelled (phase += v·dt/λ), not clip time; keep phase
   continuous through gait and speed changes.
4. Heavy = high β, no aerial phase, straight column legs, low COM. Light = lower β, crouched
   compliant legs, running allowed.
5. Feet never slide in stance — all horizontal motion is the body moving over planted feet.
6. Shift weight over the stance foot before lifting the other — anticipation, not reaction.
7. Body bob ~3–5% of h per step (working); low point just after touchdown for compliant mechs,
   at double support for stiff walkers.
8. Never swing two adjacent legs at once; projected COM inside the support polygon through slow
   gaits, climbing and idles with a lifted leg.
9. Fast swing, slow stance; ease the foot into contact — the impact cue sells weight.
10. Actuators: S-curve/trapezoidal velocity with limited acceleration; small overshoot (2–5%)
    with a damped settle of 1–2 oscillations for servos/hydraulics (working).
11. Stabilise torso/cockpit against bob with a lagged spring; torso yaw separate from the legs.
12. Heavy turns are step-turns (~15–30° yaw per step), not pivots on planted feet (working).
13. Heavy acceleration and braking take 1–3 strides.
14. Every footfall gets a mass-scaled response: distance-faded camera shake, dust, decal, sound,
    brief stance compression ~2–5% of h.

## Wall and ceiling climbing

- Vertical wall statics: the upper feet must pull out with F_n = m·g·d/L (d = COM distance from
  the wall, L = fore-aft spacing of upper and lower feet); lower feet press in by the same; the
  gripping feet share shear m·g. Keep the body close to the wall and the feet widely spread. Example
  (derived): 2 t mech, d = 1 m, L = 4 m → 4.9 kN pull on the upper feet + 19.6 kN shear.
- Ceiling: total adhesion ≥ m·g × ~2 dynamic margin (working).
- Gecko-style engagement: preload then drag; release by peeling past ~30° — toes curl and peel.
- Climbing template (Goldman/Chen/Full): the COM surges up at step frequency, swings sideways at
  half the step frequency; legs pull inward toward the midline.
- Climbing is slower than ground walking (robots: 0.04–0.66 m/s). Keep ≥ 4 feet gripping
  (hexapod) or ≥ 5–6 (octopod) on walls (working), raise β.
- Body up-vector toward the averaged contact normal, rate-limited; lead with the front legs over
  edges; pitch before a concave corner and after clearing a convex one.

## Damage, leg loss and collapse

- Leg loss means re-gaiting, not collapse: a hexapod with a failed leg moves to a quadruped-like
  periodic gait; shift the COM toward the remaining support and slow down.
- Support failure: free fall of the COM through the gap (t = √(2Δh/g): 1 m 0.45 s, 2 m 0.64 s,
  4 m 0.90 s), then topple. Rigid topple from 5° lean: 2 m → 1.34 s, 4 m → 1.90 s, 8 m → 2.68 s,
  12 m → 3.29 s. **Big things fall slowly** — an 8 m mech never hits the ground in under ~1.5 s
  unless its legs drive it down. The body settles on the ground; it never hangs in the air.

## Review thresholds (working unless sourced)

- Foot slip in stance ≤ max(2 cm, 1% of h) world displacement.
- Walking clips: Fr ≤ 0.5, β > 0.5; elephant-class mechs never have both feet off the ground.
- Measured λ/h within ±20% of 2.3·Fr^0.3.
- Static stability margin ≥ 0 every frame of slow gait/climb/idle; target ≥ 10% of the support
  polygon's minimum width.
- Feet in stance: tripod ≥ 3, tetrapod ≥ 4, octopod wave ≥ 6.
- Phase plot: anti-phase pairs at 0.5 ± 0.05; no overlapping swing in adjacent legs.
- Step-time coefficient of variation < 5% on flat steady ground.
- Flat ground: body height oscillation 2–6% of h; heavy mech pitch/roll < 3–5°; no jumps > 0.5°/frame.
- Swing duration ≈ 0.4·√h s ±30% at walking β.
- Phase continuity error < 0.05 cycle through speed transitions.
- Death / leg loss: time to ground matches the topple table ±30%.

## Engine notes

- Godot 4.6+: `TwoBoneIK3D` (deterministic; one node can solve several legs via `setting_count`;
  intermediate bones as virtual bones for 3-segment legs), `IterateIK3D` → `FABRIK3D`/`CCDIK3D`/
  `JacobianIK3D` (defaults: 4 iterations, 2°/iteration limit; hinge via `set_joint_rotation_axis`,
  limits via `set_joint_limitation` — limits can stop the solver reaching its target). Add
  `LimitAngularVelocityModifier3D` after deterministic IK. Modifiers run after the AnimationMixer in
  child order; fade IK with `influence`/`active` (e.g. on death).
- Runtime structure (working): gait controller in physics tick; foot targets as world-space
  (`top_level`) markers pinned during stance; footholds by shape/ray casts — over convex edges cast
  along −body_up first, then back toward the body; body normal slerped toward the average contact
  normal at ≤ 90–180°/s; swing trajectory from a curve resource.
- Death: disable IK and hand over to physical bones or rigid pieces so the hull settles.
- Metrics per frame for phase plots: per-foot stance displacement, support margin, per-leg phase, Fr.
- Unity/Unreal equivalents (Animation Rigging / Control Rig, Full Body IK) are in the engine skills.
