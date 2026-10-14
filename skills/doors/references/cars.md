# Car doors and getting in and out

Long tables for doors SKILL §8. [U] = not confirmed in a primary source; (working) = a starting
point; (calc) = `doors_check.py predict car|cardoor` from the stated geometry, for a 1.80 m adult.
Seated driving posture and the wheel and bars: traversal §11. Sources: the research notes for this skill (kept in Kiln's development repository).

## 1. Car doors

| Item | Numbers and rules | Source |
|---|---|---|
| Front door | hinged at the A-pillar, swings out; wind pushes an open door shut | Wikipedia "Car door" |
| Check link / door brake | holds the door at one or two intermediate positions; the current trend is three stages | US6513193; Wikipedia |
| Opening angle | lab studies fix the door at 70° (review) or 30° (Okane mock-up); 60–75° maximum [U] (a RAV4 rear strap stops at 60°, owner forum) | review; Okane |
| Gap and side space (calc) | a 1.1 m door [U length] at 70° leaves 1.03 m to the B-pillar and sticks out 1.03 m; with 0.6 m beside the car it opens 33° and leaves a 0.6 m gap — the tight-parking squeeze | `predict cardoor` |
| Speed (calc) | 70° in 0.7 s = 100°/s, edge 1.92 m/s | `predict cardoor` |
| Handles | pull, lift or tug; flush (folds), electric pop-out, press-to-release hidden, none (the door pops ajar and the hand pulls the frame); handle heights and opening forces [U] | Wikipedia |
| Closing | closing energy goes into seals, latch, hinges, check link and cabin air; customers judge quality by swing speed and the energy to latch; latching speeds [U] (SAE papers paywalled) | SAE 2009-01-0084, 2016-01-0434, 2021-01-0333 abstracts |
| Rear-hinged ("suicide") | hinged at the trailing edge; flies open if unlatched while moving | Wikipedia |
| Scissor / butterfly / gull-wing / swan | scissor rotates up about a hinge near the windscreen (Lamborghini); butterfly goes up and out (easier entry); gull-wing hinges at the roof; swan opens out at an upward angle to clear kerbs | Wikipedia |
| Sliding | minivans, vans, minibuses; the door runs back along tracks; no swing space needed | Wikipedia |
| Canopy | lifts over the car; Le Mans prototypes, concepts | Wikipedia |

## 2. What makes getting in hard

- Okane mock-up (small car): door top 1330 mm (minivan 1500), sill 160 mm above the car floor,
  floor 240 mm above ground (sill top 400 mm), H-point 355 mm above the floor (595 mm above
  ground, for a 1.80 m sitter), doorway 950 mm, door 845 mm opened to 30°. People fixated the roof
  only at 1330 mm and kept less head clearance there.
- Comfort weights (Causse 2009, review): sill width from the ground 30% and from the H-point 30%,
  seat height 16%, doorway width 13%, doorway height 11%. Acceptable and unacceptable roof heights
  differed by only 45 mm. A wide sill makes the left leg hit it on the way out.
- SUVs: step height and step-over width drive discomfort (FISITA 2008). H-points: Subaru Outback
  633 mm, Mazda CX-8 ~800 mm; ~600 mm or more eases entry and exit (CarAdvice). Buses, minivans,
  SUVs sit higher than sedans; sports cars lower (Wikipedia "H-point").
- A higher seat shortens seating time for older people (Shino 2016 via Okane). Avoid forcing large
  ankle movement and lumbar flexion or extension (Shippen & May 2016).
- Older people: 37,000 US seniors are injured a year getting in or out, over 40% of them falls;
  33% report trouble getting in and 25% getting out; injury is more than twice as likely on exit.

## 3. Strategies and times

- Five ways in (lateral sliding, backward, forward, trunk-forward, trunk-backward) and three out
  (head-forward, parallel, two-foot) (Ait El Menceur); healthy older adults used lateral sliding
  and backward more; vehicle geometry did not change the strategy. Game terms: buttocks-first
  (sit, then swing the legs in) ≈ backward / lateral sliding; head-first ≈ forward.
- Out: left leg first (driver, left-hand drive) or both legs together — 10% of exits, mostly older
  people (Chateauroux & Wang). Hands were used in more than 65% of observations.
- Gaze predicts the strategy: looking into the cabin goes with leaning back, at the floor with
  head-first, at floor and door with lateral sliding (Okane).

| Group (IMU study, 93 people, vehicle not stated) | In (s) | Out (s) |
|---|---|---|
| Control | 2.97 | 2.95 |
| High BMI | 2.71 | 4.42 |
| Older | 4.33 | 5.26 |

Older / control: ×1.46 in, ×1.78 out (calc) — use it for NPC age variety. A fully timed task
(Bodenmiller 2002): fastest vehicle means 6.44 s in (large sedan) and 5.91 s out (minivan); the
minivan was easiest overall, the full-size pickup hardest; older women significantly slower.
Seat-belt reminder chime 4–8 s (FMVSS 208); time to buckle [U].

## 4. Body demands by vehicle (calc, 1.80 m)

`predict car`: duck = H + 3 cm − door top; trunk lean with the hips at the H-point =
acos((door top − 3 cm − H-point)/0.47H); hips = H-point − 0.53H; foot lift = sill + 5 cm and the
hip flexion it needs with a vertical shank acos(1 − lift/0.245H). Entry bands (working): deep
< −0.45 m, sit −0.45…−0.2, slide −0.2…+0.05, climb > +0.05.

| Vehicle | Door top / H-point / sill (m) | Duck standing | Lean seated | Hips | Foot lift; hip flexion | Entry |
|---|---|---|---|---|---|---|
| Small sedan (Okane) | 1.33 / 0.595 / 0.40 | 0.50 m | 34° | −0.36 m | 0.45 m; 91° | sit |
| Minivan roof (Okane) | 1.50 / 0.595 / 0.40 | 0.33 m | 0° | −0.36 m | 0.45 m; 91° | sit |
| SUV (working) | 1.55 / 0.78 / 0.50 | 0.28 m | 29° | −0.17 m | 0.55 m; 104° | slide |
| Pickup (working) | 1.70 / 0.95 / 0.60 | 0.13 m | 32° | 0.00 m | 0.65 m; 118° | slide |
| Sports car (working) | 1.15 / 0.40 / 0.42 | 0.68 m | 32° | −0.55 m | 0.47 m; 94° | deep |
| Cab-over truck (working) | 2.6 / 1.7 / 1.3 | 0 | 0° | +0.75 m | steps | climb |

Stepping over a sill standing needs 91–118° of hip flexion, close to the 120° limit
(human-biomechanics) — consistent with older people sitting first and lifting the legs in. Measured joint angles
during ingress were not found in reachable papers [U]; animate from these demands and check
the clip with traversal `rom`.

## 5. Step sequences (phase times are working splits of the measured totals)

**Sedan, driver, buttocks-first (default)**
1. Walk to the spot just behind the door's rear edge, hand nearer the handle on it, pull to the
   2nd detent, step back with the door (pull-door rule; door open 0.6–1.0 s, working).
2. Turn the back to the seat, a hand on the roof rail, door frame or seat bolster, outer foot by
   the sill (0.5 s).
3. Duck (0.50 m) and lower the hips 0.36 m onto the seat (1.0 s).
4. Lift and swing the legs in over the sill, turning 90° on the seat (1.0 s).
5. Settle, reach the inner pull handle and close (0.5 s + 0.4–0.6 s door, working). Body total
   ≈ 3.0 s (control group), 4.3 s older.

**Sedan, head-first** (younger and hurried drivers, working): inner leg steps over the sill first (hip ~91°), duck, sit,
second leg follows; faster, needs more hip range and roof clearance.

**Egress** (3.0 s control, 4.4 s high BMI, 5.3 s older): inner handle, door to a detent, outer leg out to the ground
(or both legs), hands on the frame and seat, stand up while ducking (sit-to-stand 1.1–1.5 s;
hands push on low seats), step out, turn, close from outside.

**SUV / crossover**: slide — back to the seat, hips move back and only a little down; hand on the
A-pillar grab handle; the step-over width and the step height are the hard part.

**Minivan, rear sliding door**: walk in stooped through a door that runs back along the side;
rated easiest overall (Bodenmiller).

**Pickup and truck**: grab handle, foot on the running board or step, then slide. Cab-over trucks
(49 CFR 399.207): first step ≤ 609 mm, three limbs in contact at all times, an intermediate step
for two feet, a stable rest at every step with ≤ 35% of body weight per hand grasp, handholds
that take 250 lb (114 kg). Facing the cab on the way down [U practice]. The full-size pickup was
rated hardest (Bodenmiller).

**Sports car**: deep — sit on the seat first, swing both legs in together (working), duck 0.68 m;
out: legs out, hands push on the sill, seat and door frame. Upward doors (scissor, butterfly,
gull-wing) leave no door edge in the path but put the pull handle high when open [U].

**Bus**: walk in. Low-floor first step ≤ 250 mm (270 mm at two doors) for city buses (UNECE R107
Annex 8 wording in a 2004 proposal); kneeling lowers the entrance. Per passenger (TCQSM via a
WCTRS paper): boarding 2.5 s prepaid to 4.0 s exact change, alighting 3.3 s front door and 2.1 s
rear; Montréal measured 3.8 s boarding and 2.6 / 1.6 / 1.3 s alighting by door. Two steps at the
front door slow boarding; seniors are slower.

## 6. Building it

- Markers per door, made in the vehicle scene: outside stand spot (behind the door edge, facing
  the seat), handle socket, inner handle socket, roof-rail / grab-handle hand target, seat
  (H-point and facing), wheel or bar grips (traversal §11).
- One synced interaction per door side and vehicle class (sedan, SUV, pickup, sports, van
  slider, bus): the door's angle curve and the character clip share one timeline; the door goes
  to the detent the clip uses (Unreal Contextual Animation roles and warp points, Smart Object
  slots per seat; Unity Timeline + `MatchTarget`; Godot AnimationPlayer driving both).
- Warp to the stand spot over 0.2–0.3 s (working) before the clip; never snap.
- Character collision off from "sit" to "out"; attach to the seat; feet IK on sill, step and
  ground, hands IK on handle, rail and wheel; head clears the roof edge by ≥ 3 cm (`contact` and
  a head–roof distance probe).
- Mirror for the other side; left- and right-hand drive swap which leg leads.
- Exits from a moving vehicle, pulling out a driver, smashed windows (GTA-style): [U] — design
  per game.
