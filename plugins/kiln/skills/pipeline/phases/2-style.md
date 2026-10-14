# Phase 2 — Style

Goal: a locked visual direction written down so precisely that every asset can be checked
against it. No questions before the first board — show, then ask.

## Steps

1. **Research** (`research/style.md`, 40–80 lines): what the genre's best-looking games do, what
   the user's references (`ref/`) have in common, what this team can actually produce with
   scripted modeling and the engine's lighting (or 2D pipeline).
2. **3–5 directions**: one close to the user's references, one bolder, one borrowed from another
   medium (film, illustration, architecture photography). Each gets a card: opinionated name, the
   visual rule in one sentence, mood, shape language, palette idea, lighting idea, and an honest
   "can we pull it off" note.
3. **References per direction**: 6–10 real images each (`scripts/refs_fetch.py fetch` from a
   URL list you assembled with WebSearch; references are for study, never shipped). Curate: open
   every image, `drop` weak ones, `note` what to take from each. Hunts for different directions can
   run as parallel subagents (no editor needed).
4. **Board**: `board.py build production/boards/style-1 --images <dir per direction> --mode
   single --question "Which direction?"`, edit `board.json` group titles/text to the direction
   cards, `board.py serve production/boards/style-1` in the background. The user likes, comments,
   chooses, presses Send.
5. **Rounds**: directions → variations of the chosen one (2–3) → frames that look like game
   screens (paint-overs or quick engine/Blender mock frames) → lock. Lock question: "Lock it"
   (Recommended) / "One more round" / "Mix …".
6. **Art bible** `design/ART_BIBLE.md` (template `templates/ART_BIBLE.md`), written by the
   art-director with the game-designer:
   - identity statement; palette of 5–7 colours with roles (from `refs_fetch.py palette --liked`
     plus judgement), value rules (what is darkest/lightest), saturation budget;
   - shape language per faction (hero, each mech class, environment) — readable silhouettes
     first;
   - lighting and atmosphere (key/fill ratios, colour temperature, fog), materials and wear;
   - at least 3 signature techniques visible in a single still frame;
   - UI and VFX direction; **Forbidden** list; "Requires from the tech" list;
   - 2D games (`dimension=2d`): base resolution and integer scale, method (pixel / vector /
     painterly / pre-rendered), palette size and ramps, sprite sizes, outline rule, animation fps
     (art-2d skill). 3D games delete that section.
7. **Audio direction** `design/audio/music_brief.md` (template `templates/music_brief.md`), by the
   game-designer: SFX palette (materials, spaces, signature sounds), gameplay states and
   intensity signals for music, emotional arc, 3–6 reference tracks with timestamps and what to
   take from each (analysis only). The user confirms it with the style lock.

Anti-generic test before locking: could this direction be attached to any decent game in the
genre without anyone noticing? If yes, push the bolder variation. A bold direction done timidly
looks like a mistake — commit to it.

Exit: a board with ≥3 directions shown, the user locked one, the art bible and the audio brief
have no placeholders.
