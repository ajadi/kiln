# Door types, sizes, forces and speeds

Long tables for the doors SKILL. [U] = not confirmed in a primary source; (working) = a starting
point to tune; (calc) = computed here from sourced inputs. Sources: the research notes for this skill (kept in Kiln's development repository).

## 1. Sizes

| Where | Leaf / opening | Height | Source |
|---|---|---|---|
| US | room doors mostly 30 in (0.76 m), exterior 36 in (0.91 m) | 78 or 80 in (1.98 / 2.03 m) | Wikipedia "Door" |
| UK | internal 762 mm (Scotland 726), external 838 × 44 mm; metric series 526–926 mm | 1981 mm (metric 2040) | UK suppliers |
| Germany DIN 18101 | openings 635 / 760 / 885 / 1010 / 1135 mm | 2005 or 2125 mm | DIN via Baunetz Wissen |
| Accessible (ADA) | clear width ≥ 32 in (0.813 m) with the leaf at 90°, stop to leaf face; 36 in if the doorway is deeper than 24 in | nothing projects into the width below 34 in; up to 4 in per side between 34 and 80 in | ADA guide ch. 4 |

Clear width of a leaf (calc, `predict clear`): 0.914 m × 45 mm → 0.869 m at 90°; 762 mm × 35 mm →
0.727 m (a r 0.3 capsule fits only from 84°); 838 mm × 44 mm → 0.794 m (r 0.35 from 87°; nav cell
0.1 rounds r 0.35 up to 0.4 and closes it).

## 2. Code numbers worth copying

| Item | Value | Source |
|---|---|---|
| Hardware height | 34–48 in (0.864–1.219 m); UK 900–1050 mm (trade), switches line up with handles at 900–1100 mm | ADA; ADM; IMD |
| Hardware use | one hand, no tight grasp, pinch or wrist twist; levers and U-pulls comply, round knobs do not; UK: works with a closed fist | ADA; ADM |
| Opening force | interior hinged ≤ 5 lbf (22.2 N), latch release excluded, fire and exterior doors unlimited; UK ≤ 30 N at the leading edge 0–30°, ≤ 22.5 N 30–60° | ADA; ADM |
| Torque (calc) | 22.2 N at 0.84 m = 18.7 N·m; 30 N at 0.9 m = 27 N·m | — |
| Manoeuvring space, front approach | pull side 60 in (1525 mm) deep and 18 in (455 mm) beyond the latch; push side 48 in deep, 0 beyond the latch (12 in with closer and latch); UK 300 mm beside the leading edge on the pull side | ADA 404.2.4.1; ADM |
| Closers | ≥ 5 s from 90° to 12° (mean ≤ 15.6°/s, edge ≤ 0.245 m/s on a 0.9 m leaf, calc); spring hinges ≥ 1.5 s from 70° to 0°; latch speed = last 10–15°; delayed action slows the first half | ADA; Wikipedia "Door closer" |
| Thresholds | ≤ ½ in new (¾ in bevelled when altered) | ADA |
| Doors in series | 48 in plus the width of any leaf swinging into the space | ADA |
| Exit direction | side-hinged doors serving ≥ 50 people swing with exit travel (IBC 1010.1.2.1) [U: forum quote]; public exterior doors open outward | IBC; Wikipedia |
| Full-power automatic swing | ≥ 1.5 s to 80°; hold open ≥ 5 s after a knowing act (+1 s per extra foot beyond 12 ft); ≤ 30 lbf (133 N) to stop it in the last 10° | ANSI A156.10 (via Construction Canada) |
| Low-energy automatic swing | ≥ 3 s to back-check or 80° (3–5.5 s by size and weight; 36 in × 125 lb ≥ 3.5 s), back-check not before 60°, hold open ≥ 5 s (3 s push-pull) | ANSI A156.19 (via iDigHardware, Construction Canada) |
| Powered door hits something | reverse within 2 s of contact; 1 in test block; photo-eye beam ≤ 6 in (152 mm) above the floor | 16 CFR 1211.7; DASMA |
| Revolving, automatic standard speed | 8 ft 7.2 rpm, 10 ft 5.7 rpm … 24 ft 2.4 rpm ≈ 180 ft/min (0.91 m/s) at the edge | A156.27 table in a manufacturer manual [secondary] |
| Revolving, access | manual revolving doors and turnstiles are not accessible; put a hinged door beside them | ADA; ADM |

## 3. Types

| Type | Motion and numbers | Game use | Build |
|---|---|---|---|
| Hinged single | 90–110° about side hinges; "handing" is named from outside (hinges on the left = left-hand door) | default room door | animated by default, physics when bodies must push it |
| Double / French | two leaves, often one bolted (inactive) | grand entrances; open both for big agents | two hinged leaves, one interaction |
| Double-action | swings both ways, spring returns to centre (kitchens); saloon pair at chest height | walk-through, no handle | physics hinge, spring to 0°, limits ±95° (working), or animated opening away from the body |
| Sliding (barn, bypass, automatic) | along a track; automatic sliding speeds [U] | sci-fi, shops | animated (kinematic body) + sensor area |
| Pocket | slides into the wall; saves ~0.93 m² of swing floor; flush finger pull | tight rooms | animated; finger-pull grip (precision) |
| Revolving | 3–4 wings, speed governor, "bookfold" collapses wings for escape | lobbies | animated at a capped rpm; pushes bodies gently; hinged door beside it |
| Rolling shutter / garage | rolls or folds up; powered closing reverses on contact | warehouses, timed escapes | animated; reverse-on-contact rule, no crushing unless designed |
| Hatch / trapdoor | horizontal hinge, gravity closes it; manholes ≥ 0.61 m (traversal) | cellars, ships, vents | physics with a stay, or animated; ladder link below |
| Gate | hinged in a fence, self-latching; see-through | outdoors, farms | as hinged; sight and shots pass |
| Airlock / interlock | two doors that are never open together; cycle time (working 3–10 s) | pacing, a breather or a trap | state machine owning both doors and the nav links |
| Blast / vault door | heavy, powered, slow (working 10–30 s) | set pieces | animated; sound and camera shake sell mass |
| Curtains (cloth, strips, beads) | parted by the body | shops, cold rooms, tents | SKILL §7 |

## 4. People and doors

- Delay per door in a drill (Son 2020): push +1.96–2.88 s, pull +3.91–4.43 s; in poor
  visibility 7.4–12.6 s (push) and 12.9–16.4 s (pull); knob, lever or panic bar made no
  significant difference.
- Shoulders turn below ~1.3× shoulder width (Warren & Whang 1987; 1.33 in Wilmut 2010); people
  slow ~1.8 s before a gap of 0.9× shoulders, ~0.7 s before 1.7×; they judge a gap passable at
  15–20% wider than the shoulders (Fajen).
- Flow through a doorway (SFPE as implemented in Pathfinder): 1.316 persons/s per metre of
  effective width, 0.15 m boundary layer each side → 0.92 persons/s through a 1 m door.
- Which hand reaches first, footwork on pull doors and holding a door for someone: [U].

## 5. Physics numbers

- Leaf masses (working): hollow-core 10–15 kg, solid timber 25–45 kg, steel fire door 40–70 kg [U].
- Uniform leaf about its hinge edge I = m·w²/3: 30 kg × 0.9 m → 8.1 kg·m²; 10 J at 90°/s (calc).
- Constant 18.7 N·m from rest: 90° in 1.17 s and 29 J at the end — a slam without a closer (calc).
- Car door at 70° in 0.7 s: 100°/s, a 1.1 m edge at 1.92 m/s (calc; door length [U]).

## 6. Games

| Game | What it does | Copy |
|---|---|---|
| Half-Life 2 (Source SDK `props.cpp`) | `prop_door_rotating` defaults 90° and 100°/s; opens away from the user, toward them if blocked; locked use plays a locked sequence and sound; `returndelay` auto-close (−1 never); light physics objects (< 32 kg) are pushed, heavier ones block; `forceclosed` crushes; NPCs stand 64 in (1.63 m) off the door and 24 in (0.61 m) from the hinge, face it and play ACT_OPEN_DOOR; while open, a blocker keeps NPCs out of the swing | open-away rule, NPC stand spot, light-object rule |
| Amnesia, Penumbra | doors and drawers opened by dragging the mouse the way the object moves; barricades; monsters break doors | physics doors with hand-driven angle |
| Rainbow Six Siege | breach charges, shotgun holes, reinforcements defenders place and attackers destroy | breach as a state with HP |
| Ready or Not | breaching devices, a fibre-optic "optiwand" under the door, ordering AI to breach | look-under before entry; squad door commands |
| Resident Evil (1996) | door-opening animations covered loading between rooms | doors as hidden loading screens |
| The Door Problem (Liz England) | can it lock, how does a player tell locked from fake, do enemies use doors, does a co-op player block the doorway, do allies and mini-bosses fit | the design question list for every door |

GTA, Dishonored, Hitman and HL2 door wiki pages could not be read: [U].
