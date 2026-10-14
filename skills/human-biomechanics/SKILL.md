---
name: human-biomechanics
description: Human anatomy, biomechanics and neurobiology numbers for believable characters and fair AI — proportions, joint ranges of motion, gait parameters vs speed, stances, jumps and landings, hit reactions and collapse, reaction times, vision and hearing, aiming (Fitts), telegraph durations, with rules and a review checklist. Use when rigging, animating or reviewing humans, setting ragdoll limits, tuning AI perception and reaction, or sizing telegraphs and feel.
user-invocable: false
---

# Human biomechanics and perception

Numbers marked [U] are textbook values not re-verified online; treat them as working values and
measure in the game. H = character height.

## Proportions (1.80 m reference)

| Item | Value |
|---|---|
| Height in heads | 7.5 average / 8 ideal / 8.5 heroic (head ≈ 0.24 m) |
| Midpoint of height | greater trochanter, just above the pubis (0.90 m) |
| Arm span | = H |
| Eye height (FPS camera) [U] | 0.936 H (1.68 m) — the camera is at the eyes, not the head top |
| Shoulder / hip / knee / ankle height [U] | 0.818 / 0.530 / 0.285 / 0.039 H |
| Thigh / shank / foot [U] | 0.245 / 0.246 / 0.152 H |
| Upper arm / forearm / hand [U] | 0.186 / 0.146 / 0.108 H |
| Shoulder / hip width [U] | 0.259 / 0.191 H (shoulder:hip ≈ 1.18 men) |
| Mass fractions [U] | head+neck 8.1%, trunk 49.7%, upper arm 2.8%, forearm 1.6%, hand 0.6%, thigh 10%, shank 4.65%, foot 1.45% |
| Whole-body COM standing [U] | ≈ 0.55 H, in front of S2 |

## Joint ranges of motion (degrees) — rig, IK and ragdoll limits

| Joint | Limit to use |
|---|---|
| Hip flexion / extension | 120 / 15–20 |
| Hip abduction / adduction | 40 / 20 |
| Hip rotation | ±40 |
| Knee flexion / hyperextension | 140 / 0–2 (hinge only) |
| Ankle dorsi / plantar flexion | 20 / 50 |
| Shoulder | flexion 180 and abduction 180 include the scapula (~2:1); glenohumeral alone ≈ 120 abduction [U]; rotation 90/90 |
| Elbow flexion / extension | 145 / 0–2 |
| Forearm pronation / supination | 80 / 85 |
| Wrist flexion / extension / radial / ulnar | 60 / 60 / 20 / 30 |
| Neck flexion / extension / lateral / rotation | 60 / 75 / 45 / 80 |
| Thoracolumbar flexion / extension / lateral / rotation | 45–50 / 25 / 25 / 30, spread over spine bones |

Sources: CDC normal joint ROM study; AAOS/WikEM clinical norms.

## Gait vs speed

| Parameter | Walk 1.3–1.5 m/s | Jog 3.5 m/s | Sprint ~9 m/s |
|---|---|---|---|
| Cadence (steps/min) | ~117 (100–120) | ~160–180 [U] | ~250–270 [U] |
| Step length | 0.79 m men, 0.66 m women | ~1.2–1.3 m [U] | ~2.0–2.2 m [U] |
| Foot contact time | ~0.6–0.7 s [U] | ~0.26 s | ~0.11 s |
| Duty factor | ~0.60, double support 20–24% | ~0.35 | ~0.25 |
| Vertical COM | ~5 cm, **highest at midstance** (inverted pendulum) | 6–10 cm, **lowest at midstance** (spring-mass) [U] | — |
| Lateral COM sway | ~5–6 cm | smaller | — |
| Peak vertical GRF | 1.0–1.5 BW, double hump | 2.0–2.9 BW | higher |

- Walk→run at ~2.0 m/s (Froude v²/(gL) ≈ 0.5; L = 0.95 m → 2.16 m/s). Blend only around
  1.9–2.3 m/s; no "fast walk" above ~2.3 m/s.
- Speed rises by longer strides up to ~7 m/s, then mainly by cadence.
- Starts reach steady speed by step 3 (2–5); stops take 1–2 steps; weight shifts onto the stance
  leg before the first step.
- Walking angles [U]: knee 15–20° at loading, ~60° peak in swing; hip +30° at heel strike, −10°
  at terminal stance; ankle 15–20° plantarflexion at toe-off; pelvis rotation ±4°, obliquity
  ±4–5°; thorax counter-rotates; each arm swings opposite its same-side leg. Heel rise does
  about two-thirds of the COM smoothing.
- Hip sway is small and reads loud (live: an armoured man walked "swaying the hips like a drunk or
  a catwalk walk"). Caps for a neutral walk [U]: pelvis obliquity ≤ ±5°, pelvis rotation ≤ ±5°,
  lateral pelvis/COM shift ≤ ±2.5 cm per step, step width 8–12 cm with the feet never crossing
  the midline, the torso staying over the pelvis (no counter-swing of the shoulders sideways).
  The 8–12 cm is for ~10 cm wide shoes, about 0.8–1.25 × the foot width. Wide boots or armoured
  feet scale it: `analyze.py gait --foot-width <m>`. Live: armour boots 24.7 cm wide would overlap
  at 12 cm, and the lower legs kept only 43 mm of clearance passing each other.
  Larger pelvic rotation/obliquity and a narrow, crossing step are what reads as feminine or
  flirtatious; uneven, larger sway reads as drunk. Heavy armour or a big build: smaller pelvic
  motion, slightly wider steps, a stiffer trunk.
- Arm swing, walking: shoulder sagittal range 25–30°, elbow flexion range 15–20° at 0.8–1.0 m/s,
  rising with speed (non-paretic arm data, PMC11698429); a reciprocal 1:1 pattern — each arm
  moves with the contralateral leg. Running [U]: elbows held ~80–100°, shoulder range ~50–70°,
  hands toward the midline. Armour or bulky torsos limit adduction — check the clearance.
- Strafe: side-steps slow, crossover or hip reorientation fast; backpedal at ~60–70% of forward
  speed, toe-first contact. Turns: head and eyes lead the trunk by ~100–200 ms.

## Stances and actions [U]

- Combat ready stance: feet about shoulder width, support-side foot half a step forward, knees
  15–30° flexed, torso 10–20° forward, nose over the front toes, ~55–60% of weight on the front
  foot, firing elbow angled down. COM inside the support polygon.
- Crouch-walk: knees stay at 30–45° through stance, heel-to-toe roll, steps 0.5–0.6 m at
  0.8–1.2 m/s, head bob < 2–3 cm, upper body a stable "turret" over the pelvis. Not a deep
  symmetric squat.
- Knife: anticipation 150–300 ms, strike 80–150 ms, recovery 250–400 ms. Rifle reload 2–3 s.
- Punches (competition boxers, Piorkowski et al. 2011): single maximal cross 223 ± 99 ms from
  fist projection to contact (older studies 100–143 ms); hooks ~477 ms from first movement;
  four-punch combination ≈ 1.05 s contact to contact; the cross sequences shoulder → hip →
  elbow → fist. Kicks (Taekwondo literature): front kick ≈ 0.25 s total, roundhouse
  0.30–0.65 s, foot speed 12–26 m/s. Heavy armour or bulk: longer anticipation and recovery,
  lower targets within the armour's hip and shoulder clearance.

## Quiet standing (idle)

- Nobody stands symmetric: weight 55/45 to 70/30 (CoM 8–34 mm off the feet's midpoint), the
  free knee 10–20° bent, the loaded knee 0–5° (never locked back, hyperextension ≤ 10° is
  already a pathology sign), pelvis dropped 1–5° on the free side and the shoulders tilted the
  opposite way (contrapposto); bending the free knee 10/15/20/25° drops that hip ~1/2.4/4.3/6.7°.
- Feet: preferred heel spacing ~0.17 m (~10% of height), ~7° toe-out each, left and right not
  identical.
- Arms hang slightly forward of the anatomical pose: palms toward the thighs, elbows 10–20°
  bent, fingers loosely curled (working). Head a little forward of the shoulders.
- Postural sway (40 young adults, 60 s, quiet standing): centre of pressure RMS 4.1 mm front-back,
  2.4 mm sideways; CoM RMS ~3.6 / 2.2 mm, range over 60 s ~17 / 10 mm; median frequency
  0.2–0.3 Hz, > 80% of power below 0.5 Hz, nothing strong above 1 Hz; shoulders sway ~1.6×, head
  ~1.8× the CoM. These are lower bounds — subjects were told to stand still.
- Weight shifts every ~200–300 s (17–22 mm), quick fidget excursions every ~50–60 s, about two
  such events per minute in any condition; gaps vary widely. Sway grows after 30 min standing.
- Breathing 12–20/min (mean ~14), exhale longer than inhale (1:1.1–1.2), mostly abdominal at
  rest; upper chest moves 3–5 mm up and forward per breath.
- Blinks ~17/min at rest (8–21), 100–400 ms each; 2–3 gaze fixations per second; gaze shifts
  > ~20° bring the head along, eyes first. Face touching ~23/hour.
- Loads and armour: trunk and head forward, more knee flexion (load carriage studies); fatigue
  raises sway.

## Jumps, landings, falls

- Airborne COM is a pure parabola at g = 9.81 (airtime t = 2v₀/g; 0.5 m rise → v₀ 3.13 m/s,
  0.64 s). Never add horizontal acceleration mid-air — viewers detect it best.
- Soft vs stiff landing from a 0.59 m drop (Devita & Skelly 1992): peak knee flexion ~117° soft
  vs ~77° stiff — the soft landing spreads the stop over more distance and time (150–300 ms [U])
  and reads light, the stiff one reads as a heavy impact (forces ~1.6 vs ~2.6 BW [U]). Muscles
  pre-activate ~100 ms before contact.
- Fall from standing: 715–1200 ms from loss of balance to impact.
- Beyond these basics — jump reach, parkour moves by obstacle height, hanging, crawling, openings,
  balance and stepping, fall tiers, carried load, sitting and driving poses: traversal skill.

## Hit reactions and death

- Bullets do not throw bodies back: a 5.56 mm round gives an 80 kg body ~0.05 m/s. Visible
  reactions are neuromuscular.
- Startle cascade (ms): jaw 14, blink 20–40, head 60–120, neck 75–121, shoulder 100–121, arms
  125–195, legs 145–395. Passive impulse on frame 0, active flinch follows the cascade, head first.
- Incapacitation = loss of muscle tone: knees buckle and the body folds roughly in place over
  0.7–1.2 s; arms brace only if conscious. Fade active-ragdoll stiffness over 0.2–0.5 s [U]
  rather than snapping to a limp ragdoll.

## Perception and reaction (AI fairness, telegraphs, feel)

| Item | Value |
|---|---|
| Simple reaction time | visual ~190 ms, auditory ~160 ms |
| Choice reaction (Hick) | RT = a + b·log₂(n+1), b ≈ 150 ms/bit [U] |
| Saccade | latency ~200 ms (express ~100); duration ≈ 37 + 2.7·A ms (A degrees) |
| Visual field | 200–220° binocular; fovea 5°; acuity at 30° is 1/16 of foveal; colour weak by 40°; motion/flicker detection holds in the periphery |
| Hearing direction (minimum audible angle) [U] | 1.1–1.2° ahead, 3.1–3.3° at the side; front/back confusions |
| Aiming (Fitts) | MT = a + b·log₂(2D/W); mouse throughput 2.6–4.7 bits/s |
| Latency | 10 ms of added latency measurably lowers aiming accuracy; local latency hurts ~2× network latency |
| Animation error sensitivity | 3% limb-length change noticed with attention; horizontal velocity errors and added accelerations in ballistic motion are easier to spot |

## Rules

1. Derive rig, camera and sockets from H; FPS eye height ≈ 0.936 H, leg length ≈ 0.53 H.
2. Walk below Froude 0.5, run above; blend only near the transition.
3. Speed = step length × cadence; scale playback ≤ ±15–20%, beyond that switch or blend clips.
4. A planted foot has zero velocity relative to the floor through stance (~60% of the cycle
   walking, 25–35% running).
5. Don't copy walk bob into run: walk COM peaks at midstance, run COM bottoms out there.
6. Arms counter-swing legs; with both hands on a rifle, steady the weapon and let the torso
   absorb pelvis motion.
7. Knees and elbows are hinges (0–2° hyperextension); ROM table limits for ragdolls; knee pole
   targets in front.
8. Every static pose keeps the COM over the support polygon.
9. Weight reads through timing: heavy = longer contact, deeper flexion, late follow-through.
10. AI reaction budget = detection (190 ms simple, 300–500 ms choice) + gaze shift (~200 ms) +
    Fitts aim time: first accurate shot ~0.4–0.7 s after the player appears [U]. Scale
    difficulty through these terms, never by snapping aim.
11. AI vision: fine detail within ~±30°, motion-only detection to ~±100°; hearing direction
    error ~1° ahead growing to ≥3° at the side, occasional front/back flips.
12. Telegraphs ≥ 2× simple reaction time plus system latency: 400–600 ms for normal enemies,
    250–300 ms only for expert single-choice reads [U]; more possible attacks → longer
    telegraphs (Hick). Measure on-screen time, not clip time.
13. Camera follows input, never animation — latency is felt at 10 ms.

## Review checklist

- [ ] Segment ratios within ±5%; FPS camera at eye height.
- [ ] No joint beyond the ROM table; no backward knees or elbows; shoulder over 120° uses the clavicle.
- [ ] Foot drift ≤ 1–2 cm per stance measured in the running game.
- [ ] Clip speed matches game speed; walk/run switch near 2 m/s; phase kept across blends.
- [ ] Bob amplitude and phase correct for walk and for run.
- [ ] Starts ~3 steps, stops 1–2, no slide.
- [ ] Jump arcs parabolic, no mid-air acceleration; landing knee flexion ≥ 45° over ≥ 150 ms.
- [ ] COM inside the support polygon in idle, aim, crouch, reload.
- [ ] Hit reactions follow the startle cascade; no backward launch from bullets.
- [ ] Deaths collapse with lost muscle tone; no frozen or floating torso.
- [ ] IK limb stretch < 3% in first-person view.
- [ ] AI first-shot delay ≥ 400 ms; peripheral detection slower; hearing has angular error.
- [ ] Telegraphs ≥ 400 ms on screen for normal enemies.
