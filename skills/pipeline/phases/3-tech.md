# Phase 3 — Tech plan

Goal: for every risky system, the team knows HOW it will be built before building it, and the
riskiest unknowns are already answered by spikes.

## Steps

1. List the systems in the mechanics table and `GAME.md` whose implementation is not obvious
   (locomotion and IK, destruction, multi-part damage, enemy AI and navigation, wall climbing,
   weapons, large-scale effects, save system, procedural audio/music pipeline, anything the user
   guessed at). `design/tech/README.md` holds the list with an owner and status per system.
2. `kiln:tech-designer` writes a tech design note per system (tech-design skill): 2–4 real
   options, recommendation, risks, a spike with measurable pass/kill criteria. It consults the
   physics, anatomy or creature expert where their domain is involved.
3. Show the user the recommendations that change what they will see or that contradict their
   guess — one AskUserQuestion with the recommended option first and a one-line "what you give
   up". Technical choices that do not change the player's experience are recorded with
   `decide --by agent`.
4. Spikes for high-risk options: the owning role builds the minimal gym, the relevant acceptance
   role measures the pass/kill criteria, the result goes back into the note (accepted or
   superseded).
5. Budgets: each note states its per-frame cost; the sum fits the performance budget in `GAME.md`.

Exit: notes for every risky system (accepted), high-risk spikes run with results recorded.
