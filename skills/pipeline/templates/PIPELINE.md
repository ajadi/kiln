# Production pipeline

Gates are never deleted. Going back to a phase = `pipeline.py reopen <n>`. Kinds: `check:` (the
script verifies), `user` (only the user can close it — ask), `manual` (the agent closes it with
evidence in the task file). On autopilot, user gates closed by the agent are marked PROXY and
listed for the user's review.

## Phase 0 — Setup
files: manifest.md, CLAUDE.md
- [ ] Kiln project files present — check: grep:framework=kiln@manifest.md
- [ ] Engine chosen — check: grep:^engine=(godot|unity|unreal)\s*$@manifest.md
- [ ] Dimension chosen — check: grep:^dimension=(2d|3d)\s*$@manifest.md
- [ ] MCP check ready: every server, tool and probe the project needs — check: grep:"ready": true@.kiln/mcp-check.json
- [ ] /kiln:doctor passed with real calls to Blender and the {{EDITOR}} — manual
- [ ] User saw the {{EDITOR}} and Blender connected — user

## Phase 1 — Concept
files: GAME.md, design/mechanics.md, production/SCOPE.md
- [ ] GAME.md has no placeholders — check: filled:GAME.md
- [ ] Mechanics table written (30-second loop first) — check: filled:design/mechanics.md
- [ ] Scope contract written — check: filled:production/SCOPE.md
- [ ] User approved the pitch card — user
- [ ] User chose signature hooks — user

## Phase 2 — Style
files: design/ART_BIBLE.md, design/audio/music_brief.md
- [ ] Style research notes — check: filled:research/style.md
- [ ] Board with 3+ directions shown — check: glob:production/boards/style-*/feedback.json>=1
- [ ] User locked the style — user
- [ ] Art bible filled (palette, light, shapes, signature techniques, forbidden list) — check: filled:design/ART_BIBLE.md
- [ ] Audio direction: SFX palette and music brief (states, references) — check: filled:design/audio/music_brief.md

## Phase 3 — Tech plan
files: design/tech/README.md
- [ ] Tech notes for every risky system (locomotion, destruction, AI, weapons…) — check: glob:design/tech/*.md>=3
- [ ] Spikes for high-risk options run in gyms, results in the notes — manual
- [ ] Hello build per target platform launches outside the editor (release skill) — check: grep:"verdict": "pass"@production/builds/hello/smoke.json

## Phase 4 — Look-dev
files: design/ART_BIBLE.md
- [ ] Look-dev scene built in the editor (lighting, 2–3 hero assets, HUD mock) — check: {{LOOKDEV_CHECK}}
- [ ] One SFX family and a music sketch heard in the look-dev scene — manual
- [ ] Value check and reference montage done — manual
- [ ] Art-director APPROVED the look-dev frame — manual
- [ ] User approved: "the game will look like this" — user

## Phase 5 — Mechanics
files: design/mechanics.md
- [ ] Mechanics table has no placeholders — check: noplaceholder:design/mechanics.md
- [ ] No MVP mechanic left open (all locked or cut) — check: nogrep:^\|[^|]*\|[^|]*\|\s*mvp\s*\|(?:[^|]*\|){3}\s*(planned|gym|accepted)\s*\|@design/mechanics.md
- [ ] User said "fun" for the core loop — user

## Phase 6 — Vertical slice
files: production/SLICE.md
- [ ] Validation question written before building — check: filled:production/SLICE.md
- [ ] Full flow works: title → game → pause → result → again — manual
- [ ] Settings menu works (audio, controls remapping, graphics, accessibility, language) — manual
- [ ] Slice export keeps non-shipping folders out (build.py audit) — check: grep:"verdict": "pass"@production/builds/slice/audit.json
- [ ] Slice build launches outside the editor (build.py smoke) — check: grep:"verdict": "pass"@production/builds/slice/smoke.json
- [ ] Game-ness checklist passed — manual
- [ ] Acceptors passed on the slice (feel, readability, performance, stability) — manual
- [ ] User played cold, verdict "continue" — user

## Phase 7 — Content
files: production/SCOPE.md
- [ ] Scope contract met: no open promise (scope.py check ticks counted ones) — check: nogrep:^\s*- \[ \]@production/SCOPE.md
- [ ] Every content unit differs from its neighbours on 2+ axes — manual
- [ ] Batch playtests recorded — check: grep:^## PT-@production/PLAYTESTS.md
- [ ] User approved the content — user

## Phase 8 — Polish
files: production/POLISH.md
- [ ] Polish rounds logged with before/after captures — check: lines:production/POLISH.md>=10
- [ ] First 60 seconds captured cold and checked with the user — user
- [ ] Performance acceptor PASS in the heaviest scene — manual
- [ ] User says "good enough" — user

## Phase 9 — Release
files: production/RELEASE.md
- [ ] Release checklist written — check: filled:production/RELEASE.md
- [ ] Release checklist complete (no unticked item) — check: nogrep:^\s*- \[ \]@production/RELEASE.md
- [ ] Licence registry built (licenses.py) — check: filled:production/LICENSES.md
- [ ] No unknown or non-commercial licence ships — check: nogrep:(?i)\|\s*(unknown|non-commercial|cc by-nc[^|]*)\s*\|[^|]*\|\s*yes\s*\|@production/LICENSES.md
- [ ] Every CC BY item that ships names whom to credit — check: nogrep:(?i)\|\s*cc[ -]by[^|]*\|\s*\|\s*yes\s*\|@production/LICENSES.md
- [ ] Saves from earlier builds load (save-system fixtures) — manual
- [ ] Release build launches (build.py smoke) — check: grep:"verdict": "pass"@production/builds/release/smoke.json
- [ ] 60-minute soak passes (build.py smoke --seconds 3600 --sample-every 900) — check: grep:"verdict": "pass"@production/builds/release/soak.json
- [ ] User decided where and whether to publish — user
