# Phase 6 — Vertical slice

Goal: the "publishable first playable" — a short continuous piece of the game at final quality
that proves the whole thing works and tells you what each further unit of content will cost.

## Steps

1. **Validation question first** (`production/SLICE.md`, template): what must this slice prove?
   ("A newcomer fights through two encounters and a mini-boss and wants to continue.") Plus
   length target (3–5 minutes of play), contents, and the measurements you will take.
2. **Full flow skeleton in grey** before filling anything: title → menu → game ⇄ pause → result
   → again/next. Every transition works with placeholder art.
3. **Fill** the slice route with real assets, locked mechanics, lighting, sound and effects.
4. **Game-ness checklist** (minimal versions are fine, absence is not):
   menu in the game's style · HUD · clear goal · a moment of progression · story beat (if the
   game has story) · sound on every action · win, loss and restart · pause and settings
   (volume, sensitivity) · save/continue (if the game needs it) · teaching through play, not text
   walls · an ending to the slice · juice on the main actions.
5. **Acceptance pass** on the whole slice: feel, readability, physics, locomotion, AI, audio,
   performance (heaviest moment), stability (a long run with zero new errors).
6. **Cold playtest with the user**: explain nothing; ask them to think aloud if they like; the
   studio watches the logs and notes where they hesitate. Then: "What is the game about? What were
   you trying to do? Where were you confused? Would you continue?"
7. **Verdict** (user): Continue / Rework / Pivot. Continue is not available if the core loop was
   called boring. Two or more red flags (confusion loops, unreadable combat, flat core loop,
   performance under budget) → recommend Rework honestly.
8. **Cost**: record how long each content unit took to build here; multiply by the scope
   contract; if it does not fit, cut scope now (decision recorded), not quality later.

Exit: SLICE.md filled with results, checklist passed, acceptance passed, the user played cold and
chose Continue.
