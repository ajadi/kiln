# Phase 8 — Polish

Goal: close the biggest gaps between this game and the bar, one at a time, until the user says
"good enough".

## A polish round

1. Pick one **facet**: play (pacing, difficulty), feel (controls, hits), UX (HUD, menus,
   readability), audio (mix, variety, space), visual (lighting, materials, VFX), performance,
   first-time experience.
2. Capture a frozen **before** with a fixed scenario (same scene, same input sequence, same camera
   — so before and after are comparable).
3. Name exactly one gap, phrased against the bar: "The bar has X, we have Y" (bar = a reference
   game or the art bible).
4. Make one change addressing it (owning role), capture **after**, append a row to
   `production/POLISH.md`: facet · gap · change · before/after paths · verdict.
5. Every 3–5 rounds, show the user a before/after/bar sheet (`contact_sheet.py sheet`).
6. For critical parts where the gap is hard to see, use the gauntlet (`references/gauntlet.md`).

## Checklists

- **Juice** on the main actions: anticipation, impact frame (hit-stop scaled to hit strength),
  hit flash, particles, sound in the same 2–3 frames as the visual, screen shake that decays,
  recoil/kick, persistent marks (decals, debris), enemy reaction that escalates
  (twitch → falter → stagger), and **restraint** — effects never hide the next threat.
- **Sound log**: play 60 seconds and list every action; zero silent actions.
- **First 60 seconds**: delete saves, start cold, capture a frame every 2 s. Time to first
  meaningful action, time to first combat, is the goal clear? Ask the user: "What is the game
  about? What does winning mean right now? What would you come back for?"
- **Performance**: frame-time p95 within budget at the heaviest moment; no hitches over 2× the
  median frame in a combat minute (performance acceptor).

Stop when the user says "good enough" — polish has no natural end.

Exit: POLISH.md rounds logged with captures, first 60 seconds checked with the user, performance
acceptance passed, the user said "good enough".
