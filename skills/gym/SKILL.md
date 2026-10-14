---
name: gym
description: Create or update an isolated test scene ("gym") for one mechanic — terrain features, targets and on-screen debug readouts for the values being tuned — so the mechanic can be played and measured before it goes into a level. Use when starting a mechanic, tuning feel, or reproducing a bug in isolation.
argument-hint: "<mechanic, e.g. locomotion | mech-damage | weapons | spider-wall-walk>"
---

# /kiln:gym

1. Read the design spec for `$ARGUMENTS` (`design/*.md`) and the acceptance checks of the tasks
   that use it.
2. Decide what the gym needs to exercise every check. Typical kits:
   - locomotion: flat 30 m strip, stairs (0.18 m steps), ramps at 10°/20°/35°, curb, uneven
     debris, a marked 10 m distance, readouts for speed, foot slip, stride, IK offsets;
   - damage: a static target with labelled parts, part HP readouts, a reset key;
   - weapons: targets at 5/15/40 m, hit markers, spread and DPS readouts;
   - AI: corridor + small arena with cover, navigation debug visible;
   - wall walking: vertical walls, an inside corner and an outside corner, a ceiling strip.
3. Delegate to `kiln:gameplay-dev` (or `kiln:level-designer` for traversal-heavy gyms) with the
   kit list and the checks; the scene goes to the gyms folder (Godot `scenes/gyms/<mechanic>_gym.tscn`, Unity
   `Assets/_Project/Scenes/Gyms/`, Unreal `Content/<Project>/Maps/Gyms/`).
4. Have `kiln:playtester` run it once to confirm it loads clean and the readouts update.
5. Tell the user how to open and play it.
