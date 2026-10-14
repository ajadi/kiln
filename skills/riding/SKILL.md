---
name: riding
description: Riding animals in games — horses first, camels, elephants and large or fantasy mounts — the mount as a creature with its own gaits (walk, trot, canter, gallop with speeds, stride frequency and length, footfall order, transitions with hysteresis, Froude scaling to other sizes), the rider as a passenger coupled to the saddle (seat motion per gait, sitting and rising trot, two-point at the gallop, hands that follow the bit, legs and stirrups, IK to saddle, stirrups and reins, rider clips driven by the horse's phase), mounting and dismounting (side, steps, timing, from a moving horse, falls), steering, lean in turns and turning circle by gait, acceleration and stopping distances, rearing, jumping, slopes and water, stamina, bond and panic, rider and load limits (rider + tack ≤ 20 % of the horse), combat and aiming from the saddle, camera and input, AI mounts and companions, two riders, the reads-wrong list, exact checks in riding_check.py and Godot/Unity/Unreal setup. Use when designing, animating, building or reviewing anything a character rides.
user-invocable: false
---

# Riding

Riding is two bodies. The mount moves by its own gait rules; the rider is a passenger coupled to
the saddle who follows it. Build the mount first — its phase is the clock — drive the rider from
that phase, and check both with `${extensionPath}${/}skills${/}riding/scripts/riding_check.py` (stdlib Python,
Bash). Froude, duty factor, foot placement and leg phase tables: creature-locomotion skill. Sitting,
seats and carried load: traversal. Motorbike lean and arcade-vs-sim: vehicles. Rein and grip
poses: hands. Rider body numbers: human-biomechanics. Camera rigs: controls-camera. Navigation
agents: game-ai. (working) = starting point to tune; [U] = unverified. Long tables:
`${extensionPath}${/}skills${/}riding/references/gaits.md`.

## 1. The mount: gaits

500 kg riding horse, leg length L ≈ 1.25 m (working), Fr = v²/(g·L):

| Gait | Beats | Speed | Stride | Saddle bounce | Fr |
|---|---|---|---|---|---|
| Walk | 4: LH LF RH RF | 1.8–1.9 m/s (0.9–2.1) | 0.7–1.1 Hz, 1.3–1.9 m | 2 per stride, 7 cm | < 0.34 |
| Trot | 2: diagonal pairs + suspension | 3.6 m/s (to 5.3) | 1.5 Hz at 3.5 m/s, 2.3 m | 2 per stride (~3 Hz), 9 cm | 0.34–1.3 |
| Canter | 3 + suspension; right lead LH, RH+LF, RF | 4.4–7.5 m/s | ~1.6 Hz, 3.7 m at 6 m/s | 1 per stride, 18 cm, pitch 8° | 1.3–5 |
| Gallop | 4 + suspension | 11–13 m/s (record 19.7) | 1.7 Hz sustained; racing 2.3–2.9 Hz, ~7.5 m | 1 per stride, ~15 cm | > 5 |

1. **Gait from speed and size, not from looks**: `predict gait --v --leg`. Walk→trot at Fr 0.34
   (1.6–2.3 m/s across 90–720 kg horses); ridden canter from ~4 m/s, though a free horse may trot to
   Fr ~2.8 (5.9 m/s at 500 kg). Stride numbers: `predict stride --gait --v [--mass]`.
2. **Hysteresis**: animals hold the old gait a little past each boundary in both directions —
   copy it (working: 10 % of speed) or the gait flickers at a boundary speed.
3. **Phase from distance**: phase += v·dt / stride (creature-locomotion). Gait changes start on the
   footfall that begins the new gait (RDR2: acceleration and deceleration cycles synced to the feet).
4. **Leads**: on a circle the inside legs lead; author left and right canter cycles and change lead
   at the turn. A wrong lead in a tight fast turn unbalances the horse.
5. **Hooves stay planted in stance** (≤ 2 cm, `hooves`); turning on the spot pivots around the front
   feet (RDR2). The back moves 7 / 9 / 18 cm (walk / trot / canter), pitches 2–8° and sways ~2 cm
   per trot step — the rider sits on a saddle socket on the spine bone, not on the horse's root.

## 2. The rider: coupled to the saddle

| Gait | Seat | Rider pelvis vs saddle | Check |
|---|---|---|---|
| Walk | sitting; pelvis rocks with the back | in phase, 2 bounces per stride | `follow --mode sitting` |
| Sitting trot | seat stays down; hips and lower back absorb ~9 cm at ~3 Hz | in phase | `follow --mode sitting` |
| Rising (posting) trot | up on one beat, down on the next: once per stride; sit when the outside fore and inside hind land | half the saddle frequency | `follow --mode posting` |
| Canter | seat bones stay down, hips roll, lower leg quiet | in phase, 1 bounce per stride | `follow --mode sitting` |
| Gallop, jump | two-point: seat off, short stirrups, weight down through knees and heels | rider moves ≤ ½ of the saddle (jockeys barely move; out of phase) | `follow --mode two-point` |

- A fast trot is "virtually impossible to sit": above ~4 m/s (working) rise or go two-point.
- **Hands follow the bit, not the saddle**: shoulders and elbows open and close so the hands change
  < 15 mm per trot stride relative to the bit; rein tension peaks at the head's lowest point. IK the
  hands to rein targets that move with the head. English reins between ring and little finger, thumb
  on top; western reins in one hand (hands skill for poses).
- **Posture and legs**: ear, shoulder, hip and heel in one vertical line at sitting gaits; ball of
  the foot in the stirrup, heel down (working); stirrups long (dressage) → very short (racing).
- **Sync**: horse clips carry footfall and high/low markers, rider clips matching markers (RDR2). The
  simple version: rider clips with the same normalized cycle as the horse clip, rider time written
  from the horse's phase each tick. IK order: horse pose → saddle socket → rider pelvis → feet to
  stirrups → hands to reins → head look.

## 3. Mounting and dismounting

- Left (near) side by tradition (swords on the left hip); train both sides. Ground mount: stand at
  the left shoulder, reins in the left hand, left foot in the stirrup, spring, swing the right leg
  over the croup without touching it, settle, find the right stirrup. 2–4 s real [U]; game clips
  1–1.5 s (working). Mounting blocks: 240–260 mm steps, ≤ 780 mm (BHS).
- Games: per-side clips plus a rear vault (BotW mounts from any angle); mount and dismount without
  stopping (Ghost of Tsushima) need a warp target on the saddle and the horse at walk or trot
  (working); jumping off starts slow-motion aiming (BotW). Camels kneel on command.
- Dismount: both feet out, right leg over, slide down the left side, land with bent knees (from a
  16 hh horse the feet drop ~1 m). Every mount clip ends with the seat on the saddle within 2 cm.

## 4. Steering and turning

- Lean θ = atan(v²/(g·r)); horses lean that much, on average 1.2 ± 2.4° less (Pfau 2012, trot).
  Grip limit μ ≈ 0.6: lean ≤ 31°, tightest radius v²/(μg) — walk 0.55 m (turns on the spot),
  trot 3.5 m/s 2.1 m, canter 6 m/s 6.1 m, gallop 13 m/s 28.7 m. Racehorses slow on every bend
  (`predict turn`). The rider leans with the horse (same formula as a motorbike: vehicles).
- No instant turns: lateral acceleration stays ≤ μg (`grip`). RDR2 adds strafe and drift while
  turning so the player guides the horse; its avoidance strafes around trees but lets the player
  hit one on purpose. A ridden horse avoids obstacles and follows paths by itself (BotW).

## 5. Speed changes and stopping

- Stopping distance d = v·t_delay + v²/(2a). Grip-limited (a ≈ 5.9 m/s²): 15 m/s stops in 19 m,
  2.5 s; a comfortable 3 m/s² (working): 37.5 m (`predict stop`). A reining sliding stop peaks at
  ~38 m/s² on the saddle pad — a peak on a prepared surface, not an average.
- The rider pitches forward by the deceleration (0.3–0.6 g); above ~0.6 g, a refusal or a collision
  at speed: unseat check (working). Speeding up: one gait per 1–2 strides (working). Tagged cliff
  edges make the horse halt by distance and speed instead of walking off (RDR2).

## 6. Terrain, jumps, rearing

- Slopes: incline and decline clips blended by pitch (RDR2), not IK alone; the rider stays plumb
  (working). Deep water, snow and mud slow the horse and change its clips (traversal: wading).
- Jumps: approach (last canter stride, forehand lowered) → take-off (hind legs push) → flight with
  bascule → landing on the trailing fore → recovery stride; Grand Prix fences to 1.6 m high, 2.0 m
  wide. The rider folds into two-point, hands forward. Landing is farther from the fence than
  take-off [U]. Refusals happen — decide the rule (show jumping: 4 faults, the second eliminates).
- Rearing: hind feet planted, forehand up; the rider leans forward and gives the reins (working).

## 7. Stamina, bond and panic

- A horse gallops 1.5–3 km before it must rest (~2–4 min). Games: spurs from the stamina stat (BotW).
- Low bond → bucking, drifting, refusals; full bond refuses only impassable ground (BotW). RDR2's
  motivations (agitation from gunfire or predators, tiredness, injury) change clips and can override
  the player; patting calms. Keep disobedience rare (Shadow of the Colossus). Game-by-game notes:
  `${extensionPath}${/}skills${/}riding/references/game-practice.md`.

## 8. Load: rider, tack and gear

- Rider + tack + gear ≤ 20 % of the horse's body mass (Powell 2008: soreness at 25–30 %); a pilot
  study stopped every test with a rider heavier than 15.3 % of the horse (Dyson 2020). 500 kg horse,
  10 kg saddle: rider ≤ 90 kg by 20 %, ≤ 75 kg by 15 % (`predict load`).
- Two adults (32 % for 2 × 80 kg) are past the limit: show it in the horse (shorter strides, earlier
  fatigue, faster stamina drain) before capping speed.

## 9. Combat, camera, input, AI

- Melee damage grows with speed relative to the target (Mount & Blade). The horse's head and neck
  block the front — limit aim arcs per side; aim sway follows the saddle bounce (working).
- Camera (working): behind and above, pull back and widen FOV with gait, lag the yaw, damp the
  bounce rather than lock it. Input: stick deflection for walk and trot, a button steps the gait up;
  auto-follow road (restored by a patch in Assassin's Creed Shadows); call the horse.
- The mount has its own navigation agent and navmesh (game-ai); NPC riders use the same rig, sync and
  checks; a passenger sits on a second socket behind the saddle.

## 10. Other mounts

Keep the horse's Froude number: v ∝ √L, f ∝ 1/√L, stride ∝ L, mass ∝ L³ (`predict scale`); a 3 m
leg canters at 9.3 m/s, 1.04 Hz, 8.9 m strides, ~14× the mass. Dromedaries pace (both legs on one
side — the rider rolls side to side) at 2.2–3.3 m/s; elephants reach 6.8 m/s without ever leaving
the ground (references/gaits.md). Flying mounts: flight skill.

## 11. Reads wrong

| Symptom | Cause | Check | Fix |
|---|---|---|---|
| Rider floats above or sinks into the saddle | rider attached to the horse root, not the spine | `seat` ≤ 2 cm while sitting | seat socket on the saddle bone |
| Rider slides fore and aft | IK target drifts, no pelvis lock | `seat` slide ≤ 2 cm | pin the pelvis, then IK the legs |
| Rider bounces against the horse | rider clip not driven by the horse's phase | `follow` lag ≤ 0.05 s, corr ≥ 0.8 | write rider time from horse phase |
| Hooves skate | clip rate not matched to speed, blends out of phase | `hooves` ≤ 2 cm | phase from distance, cyclic sync |
| Horse turns like a car, instantly | yaw set directly from input | `grip` ≤ μg | heading rate from speed and radius, pivot on the forehand |
| Horse upright in a fast turn | no lean | `lean` within 3° | roll from atan(v²/gr) |
| Instant stop from a gallop | velocity zeroed | stop distance vs `predict stop` within 15 % | deceleration cycle, sliding stop clip |
| Hands locked to the saddle while the head nods | hands parented to the horse body | wrist vs rein target ≤ 15 mm per stride | IK hands to rein targets on the head |
| One gait time-scaled for every speed | no gait bands | `predict gait` per speed | gait bands with hysteresis |

## 12. Lab gyms

| Check | Gym | Command | PASS |
|---|---|---|---|
| Gait bands | ride 1.5, 3.5, 5, 7, 12 m/s on a straight | `predict gait` vs the playing gait | gait matches; no flicker within ±10 % of a boundary |
| Stride | 10 strides per gait | foot contacts vs `predict stride` | frequency within 10 % |
| Hooves | straight, zig-zag, turn on the spot | `hooves --feet LF,RF,LH,RH` | slip ≤ 2 cm |
| Seat | each gait, mount and dismount | `seat --when sitting` | gap ≤ 2 cm |
| Rider follows | walk, sitting trot, rising trot, canter, gallop | `follow --mode …` | corr ≥ 0.8, lag ≤ 0.05 s, ratio 0.7–1.3; posting 0.5 ± 0.1; two-point ≤ 0.5 |
| Turns | circles of 5, 10, 20 m at the fastest speed the game allows | `lean`, `grip` | lean within 3°; lateral ≤ 0.66 g |
| Stop | full stop from canter and gallop | distance vs `predict stop` | within 15 % (working) |
| Load | 1 and 2 riders, saddlebags | `predict load` | status and penalties as designed |

## 13. Engines

Godot 4.6/4.7: rider under a `BoneAttachment3D` on the saddle bone (follow-only; `override_pose`
misbehaves next to SkeletonModifier3D), gaits in BlendSpace1D with `sync_mode` CYCLIC (4.7), rider
time from the horse's phase through `AnimationNodeTimeSeek`, `TwoBoneIK3D` for hands, feet and
hooves. Unity 6: `SetParent` to a saddle socket, phase from `normalizedTime`, Animation Rigging Two
Bone IK. Unreal 5.6–5.8: `Attach Actor To Component` with a socket, Motion Warping and Contextual
Animation for mounting. Details and probes: `${extensionPath}${/}skills${/}riding/references/engines.md`.
