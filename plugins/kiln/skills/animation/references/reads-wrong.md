# Reads wrong — animation defects players notice, as pitfalls

Every entry was a live complaint the user had to spot. qa-locomotion runs every entry that applies
to the clips or systems a task touched; the plan copies the applicable entries into animation
tasks' acceptance. **When the user points out a new "looks wrong", add an entry** in the same
session, in this form - the next character must not need the user's eye:

- **Class** (the heading): the kind of defect, not this one clip.
- **Looks like:** the symptom, in the user's words.
- **Why:** what produces it.
- **Fix principle:** the rule that prevents the whole class, not one project's fix.
- **Caught by:** the check and its threshold that would have caught it, or `no check yet` - then
  the entry is a candidate for a new check (the retro proposes it).
- **Taught in:** where the skills explain it.

### 1. Foot slide on direction changes
- **Looks like:** "Feet slide when the runner changes direction several times."
- **Why:** the capsule's velocity turns faster than a planted foot can; no pivot clips, no foot lock.
- **Fix principle:** a planted foot never moves while it is in contact: the body turns about it
  (pivot clips, foot lock with IK), and the capsule turns no faster than the clips can follow.
- **Caught by:** zig-zag course + `analyze.py stance --root`: turning stances ≤ 10 mm typical,
  ≤ 20 mm worst.
- **Taught in:** animation "Direction changes without skating".

### 2. One jump for every approach
- **Looks like:** "A standing jump pose while running forward."
- **Why:** one jump clip serves every approach.
- **Fix principle:** a jump is chosen by approach speed and stance foot, and a running jump keeps
  its speed into the air.
- **Caught by:** jump from idle / walk / run / sprint with both feet in phase +
  `traversal_check.py jumps`: type by speed, takeoff = stance foot, run jumps keep ≥ 85 % speed.
- **Taught in:** animation "Jumps are a family"; traversal §2.

### 3. Lifeless idle
- **Looks like:** "The idle looks like a mannequin."
- **Why:** a symmetric pose with only a breathing loop.
- **Fix principle:** a standing body is never still or symmetric: weight on one leg, slow sway,
  visible breathing, every part moving a little.
- **Caught by:** 60 s idle + `analyze.py idle --pos --chest --bones`: sway AP 1–8 mm, ML 0.5–4 mm,
  breathing 12–20/min, nothing frozen, weight 55/45–70/30.
- **Taught in:** animation "Idle that looks alive".

### 4. Exaggerated pelvis motion
- **Looks like:** "Walks swaying the hips like a drunk or a catwalk walk."
- **Why:** pelvis obliquity, rotation or lateral shift too big; crossing steps.
- **Fix principle:** pelvis motion stays inside human gait ranges and the feet land either side
  of the midline.
- **Caught by:** 10 gait cycles + `analyze.py gait --pelvis --hips --feet`: obliquity and rotation
  ≤ ±5°, shift ≤ ±2.5 cm, step width 8–12 cm, no crossing.
- **Taught in:** human-biomechanics "Hip sway".

### 5. Body parts left unanimated in locomotion
- **Looks like:** "Arms hang frozen in the bind pose while walking."
- **Why:** the acceptance spoke only of the legs.
- **Fix principle:** acceptance covers the whole body: every limb has a motion range for each
  gait, reciprocal to the legs.
- **Caught by:** arm bone probes over a walk cycle: shoulder sagittal range 25–30° at a walk,
  elbow 15–20°, reciprocal to the legs.
- **Taught in:** plan "Whole-body acceptance"; human-biomechanics arm swing.

### 6. Range of motion blocked by worn gear
- **Looks like:** "Elbows can't bend in the armour (run and guard look stiff)."
- **Why:** the plates collide past 56°.
- **Fix principle:** gear is built around the range the joint needs: plates overlap, split or
  slide so the joint reaches every move's range.
- **Caught by:** Blender joint sweep + `traversal_check.py rom --moves …`: elbow ≥ 130°,
  shoulder ≥ 130° (≥ 160° to climb), knee ≥ 140° to crouch.
- **Taught in:** traversal §9; blender-modeling worn gear.

### 7. Stride and speed mismatch
- **Looks like:** "Feet skate in straight walking or running."
- **Why:** stride does not match speed; phase drifts in blends.
- **Fix principle:** the clip's stride follows the travel speed (or travel follows root motion),
  phase-matched across blends.
- **Caught by:** `analyze.py skating`, stride vs root travel: skating ratio ≤ 0.05, slip per
  stance ≤ 10 mm in engine.
- **Taught in:** animation "Phase and speed matching".

### 8. Strikes without acceleration
- **Looks like:** "Strikes look slow and weightless."
- **Why:** no acceleration into contact; long anticipation.
- **Fix principle:** strikes follow human timing: short anticipation, acceleration into contact,
  peak speed at contact.
- **Caught by:** clip timing vs human-biomechanics strike times, peak speed at contact: about
  0.22 s to contact, speed peaking at contact.
- **Taught in:** human-biomechanics strikes.

### 9. Non-ballistic flight
- **Looks like:** "The body floats or drifts in the air."
- **Why:** horizontal acceleration mid-air; the apex is off the physics.
- **Fix principle:** a body in the air is ballistic: no horizontal acceleration in flight, apex at
  v₀²/2g.
- **Caught by:** a jump recording: |Δvx| in flight ≈ 0, apex within 5 % of v₀²/2g.
- **Taught in:** traversal §2.

### 10. Ground penetration at rest
- **Looks like:** "The corpse's legs sink into the floor."
- **Why:** bones placed at floor level; the check looked only at pelvis, chest and hands.
- **Fix principle:** resting poses are checked on the deformed mesh, every body part, against the
  floor.
- **Caught by:** lowest vertex per body part over the death pose (CPU-skinned in headless runs):
  ≥ 0 cm into the floor, ≤ 2 cm above.
- **Taught in:** animation "Death on the floor".

### 11. Cloth intersecting the limbs
- **Looks like:** "The skirt hem cuts through the legs when running."
- **Why:** the hem envelope is smaller than the swinging thigh; no clearance solve.
- **Fix principle:** loose garments are sized to the swing envelope of the limbs under them, or
  solved for clearance every frame.
- **Caught by:** hem vertices vs leg capsules per frame, hem vs floor: clearance ≥ 0 at every
  frame, the hem never under the floor.
- **Taught in:** animation "Long skirts"; soft-bodies.

### 12. Unmatched phase in a transition
- **Looks like:** "A double step when walk turns into run (or back)."
- **Why:** a crossfade without phase match; the run's flight pose lands a foot.
- **Fix principle:** locomotion blends are phase-matched so foot contacts alternate through every
  transition.
- **Caught by:** foot contacts through the transition (`analyze.py stance`): no extra contact,
  phase matched both ways.
- **Taught in:** animation "Phase and speed matching".

### 13. Secondary motion too small to read
- **Looks like:** "The idle does not breathe."
- **Why:** spine and chest move < 0.5°: the breath has 0.1 mm amplitude.
- **Fix principle:** secondary motion is sized to read at game distance, not merely present.
- **Caught by:** `analyze.py idle --chest`: `chest_p2p_mm` ≥ 2 mm at 12–20/min.
- **Taught in:** animation "Idle that looks alive".

### 14. Missing transition clips
- **Looks like:** "Feet slide every time the character starts or stops."
- **Why:** the library has no start / stop / turn clips; speed ramps over 0.2–1.0 s.
- **Fix principle:** speed changes have their own clips (start, stop, turn), so the feet stay
  planted while the speed ramps.
- **Caught by:** idle ↔ walk transitions + `analyze.py stance`: slip per stance ≤ 20 mm in starts
  and stops.
- **Taught in:** add start / stop / turn clips to the animation batch.
