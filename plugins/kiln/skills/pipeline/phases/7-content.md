# Phase 7 — Content

Goal: the levels, encounters and moments the scope contract promises, each one different enough
to be remembered.

## Steps

1. Scope contract (`production/SCOPE.md`) is the plan: every promise is a line with a `count:`
   command or `manual`; `scope.py check` reports progress. Numbers are never lowered silently —
   a cut is a recorded decision and the line stays (BLOCKED or reduced, with the reason).
2. Each content unit (level section, arena, encounter) gets a row in `design/content.md`:
   signature moment, which locked mechanics it uses, how it differs from its neighbours on **at
   least two axes** (space shape, enemy mix, verticality, light/mood, objective, pacing —
   difficulty and lore do not count as axes), and its place in the difficulty curve (sawtooth:
   tension, release, higher tension).
3. Level work follows the level-design skill: beat sheet → blockout → playtest → art pass. Never
   put art on an untested blockout.
4. Encounter test (from DOOM's encounter design): in a working arena the player chooses targets —
   runs past some enemies to kill a priority one. If every enemy is handled the same way, the mix
   is wrong.
5. Build in batches by zone (one role owns a zone end to end); after each batch, one integrated
   play-through of the whole route by the playtester and a contact sheet of every unit's
   signature moment (`contact_sheet.py sheet`).
6. Batch playtests with the user; findings routed as in `references/playtest-with-user.md`.

Cutting ladder when time runs short: fewer units at full quality before more units at lower
quality; cut `full`-tier mechanics before shortening the core loop's polish.

Exit: scope contract met (or cuts decided), every unit differs on 2+ axes, playtests recorded,
the user approved the content.
