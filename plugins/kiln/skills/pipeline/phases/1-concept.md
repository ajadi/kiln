# Phase 1 — Concept

Goal: an approved concept that can say "no" to features. Run the interview with `/kiln:concept`
(it holds the question method); this playbook says what must come out of it.

## Outputs

- `GAME.md`: one-line pitch; **3–4 pillars**, each phrased so it can reject a feature (test: of
  five plausible feature ideas, each pillar rejects at least one); anti-pillars; player fantasy;
  loops at three scales — 30 seconds (the action repeated all game), 5 minutes (an encounter or
  space), a session; platform and performance budget; non-goals.
- `design/mechanics.md` (template `templates/mechanics.md`): 6–10 rows, `M01` = the 30-second
  loop, each with tier (`mvp` / `full`), pillar it serves, risk, status. The 30-second loop is
  replayed in different spaces, with different weapons and enemies — note what varies it.
- `production/SCOPE.md` (template `templates/SCOPE.md`): countable promises for the milestone
  (`count:` lines) plus manual ones; a cut list of what goes first if time runs out.
- Story skeleton in `GAME.md` (or "No story: <why>") when the game has one: logline, world rule,
  beats tied to places in the game.

## Steps

1. Read everything the user already gave (briefs, `task*.md`, `ref/`, `AGENTS.md`). Tag each
   concept slot as stated / implied / open.
2. Interview with `/kiln:concept` — only open slots that are the user's taste and costly to
   change. Budget: 2–3 question calls.
3. `kiln:game-designer` writes the documents from the answers.
4. Designer layer (`references/designer-layer.md`): 3–4 signature hooks as one multiSelect.
5. Pitch card for approval (preview): pitch, pillars, loops, scope, hooks, and **Assumed:** line.
   Options: Approve (Recommended) / Bolder / Change one thing.

## Why this matters

Analyses of 155 game postmortems put a clear vision with a hook at the top of what went right,
and features that were "individually doable but added up" among the top failures. Pillars and the
scope contract exist to stop the second.

Exit: placeholders gone from GAME.md, mechanics table and scope contract written, user approved
the pitch and chose hooks.
