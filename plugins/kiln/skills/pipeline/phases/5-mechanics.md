# Phase 5 — Mechanics, one at a time

Goal: every MVP mechanic proven in its own gym, tuned in numbers, accepted by the acceptance
roles and called fun by the user. Only then do levels use it.

## Order

1. The 30-second loop mechanic (`M01`) first.
2. What puts pressure on it (enemies, threats), then the 5-minute loop, then progression.
3. Within a layer, the riskiest first. Only `mvp` mechanics in this phase; `full` ones wait.

## The cycle for one mechanic

1. **Research** `research/mech-<id>.md`: how 2–3 reference games do it, with numbers where
   possible (frame-stepped videos, GDC talks, docs). For non-trivial tech the tech-designer's note
   from Phase 3 is the starting point.
2. **Spec** in `design/mechanics.md` row + `design/<id>.md` (5–15 lines):
   - a falsifiable hypothesis: "If the player <does X>, they feel <Y> — visible in <Z>";
   - the numbers (`references/feel-numbers.md`): no adjective without a number ("responsive" →
     "input to visible response ≤ 3 frames at 60 fps");
   - the **test interface**, written before building: start state, player actions (input
     sequence), what is sampled, invariants that must always hold (e.g. "30 s of torso fire → no
     limb detaches", "destroyed mech is at rest on the ground within 4 s").
3. **Gym** (`/kiln:gym <id>`): its own scene, production code (not throwaway), tuning values in a
   data resource, the standard gym keys (R restart, Tab tuning panel, O debug overlay, P dump
   tuned values, 1/2 A/B presets, T slow motion), minimal juice from day one (a hit is never
   silent or invisible).
4. **Build** by the owning role (gameplay-dev, animator, fx-artist…), scene structure in the
   editor first.
5. **Acceptance**: the acceptance roles for this mechanic's aspects run their probes (feel,
   physics, locomotion, readability, AI, audio, performance as relevant); the verifier closes the
   task. The builder does not grade its own mechanic.
6. **User plays** (`references/playtest-with-user.md`): run the gym, give the hypothesis, the
   controls and 3–5 things to try, then stop and wait.
7. **Feedback**: "Fun?" — Yes, want more / Okay / Boring / Annoying (no recommended mark on this
   one); "What's off?" (multiSelect from this mechanic's feel profile); "Next?". Record `PT-NN`
   verbatim.
8. **Tune** one parameter group at a time; re-run acceptance on what changed; play again.
9. **Lock**: status `locked` in the mechanics table, commit, `decide` the final numbers.

## Rules

- "Boring" is about rules, not numbers — change what the player does or decides, not the
  speed. "Annoying" is usually about control or fairness — look at feel numbers and telegraphs.
- Stop rule: about three rounds (or ~2 hours) without "Yes, want more" → bring the
  game-designer's 2–3 alternative designs (one bold) to the user instead of tuning further.
  Three pivots without success → cut it, one line in the mechanics table (`cut`, why).
- Combat mechanics with destructible enemies: weak points are visible parts of the model, each
  with its own HP and a behavioural consequence when destroyed (a destroyed gun stops firing);
  attacks have multi-sense wind-ups (pose, light, sound) long enough to react to; limit how many
  enemies attack at once.
- After all MVP mechanics: a holism check with the user — do they form one game (pillars served,
  no mechanic orphaned, the 30-second loop still central)?

Exit: every `mvp` row is `locked` or `cut`, acceptance passed for each locked one, the user said
"fun" for the core loop.
