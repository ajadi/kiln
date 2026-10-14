---
name: concept
description: Shape the game with the user — read their briefs and references, interview in short rounds with recommended options, and produce GAME.md plus design specs with acceptance checks (via the game-designer agent). Use at the start of a project, when the user brings new task briefs, or when the design must change ("add a feature", "change the enemies").
argument-hint: "[brief file or topic]"
---

# /kiln:concept

The interview happens here, in the main session, because only the main session can wait for the
user's answers. The game-designer agent writes the documents.

1. **Read first.** `GAME.md` (if any), the briefs (`$ARGUMENTS`, `task*.md`, notes the user
   points to), `ref/` images (look at them), `AGENTS.md`/`CLAUDE.md` requirements. Summarise in
   3–5 lines what is already decided.
2. **Find the gaps** that change what the player experiences: camera, scale, enemy roster,
   weapon set, win/lose, difficulty, art direction specifics, performance target. Technical
   choices are not interview material.
3. **Grill.** Call the Skill tool with "kiln:grilling": rounds of the whole frontier, each
   question with a recommended answer, until the frontier is empty; what the user leaves open
   becomes an `OQ-NNN` row in `GAME.md` (or a PROXY decision under `user_gates=proxy`).
4. **Delegate writing** to `kiln:game-designer` with: the brief paths, the user's answers
   (verbatim), the list of open questions. It writes `GAME.md` and `design/*.md` with acceptance
   checks.
5. **Show the user** the pitch, pillars, non-goals and open questions (short), and ask for an
   approval or one change. Then suggest `/kiln:plan`.

When the user adds a feature mid-project: same flow, but only about the new feature, and the
designer appends a dated section instead of rewriting existing design.
