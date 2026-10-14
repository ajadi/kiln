---
name: pipeline
description: The whole game production pipeline from idea to release, run by the Kiln studio with the user as director — phases with gates (setup, concept, style, tech plan, look-dev, mechanics one by one in gyms, vertical slice, content, polish, release), a state file that makes every session resumable, user interaction rules, playtests with the user, separate evaluation, game-first and scope guards, a game-designer idea layer and blind A/B against a bar. Use when the user wants to make a game, continue the game, "what's next", or move to the next phase.
argument-hint: "[idea | 'continue' | phase number]"
---

# /kiln:pipeline — idea to release

**The user is the director**: they decide taste, scope, money and publishing. The studio does
everything else and regularly lets them look and play. Every phase ends with the user seeing or
playing something and making a decision. Never try to make "the whole game" in one pass.

Scripts: `${CLAUDE_SKILL_DIR}/scripts/` (normal Python on Windows; run from the project root).
Phase playbooks: `${CLAUDE_SKILL_DIR}/phases/`. References: `${CLAUDE_SKILL_DIR}/references/`.
Templates for production files: `${CLAUDE_SKILL_DIR}/templates/`.

## Every session

1. `python ${CLAUDE_SKILL_DIR}/scripts/pipeline.py status` — it auto-checks gates, shows the
   current phase (first one with open gates), its open gates, game-first warnings, the last
   decisions and playtest. First run: `pipeline.py init`. Disk beats memory: trust the status
   over what you remember.
2. Read the playbook of the current phase (`phases/<n>-*.md`) and do its next step.
3. Record as you go: `pipeline.py decide` for every choice (by user / agent / proxy),
   `pipeline.py tick` when a gate is met (with a short note), task files for the work itself.
4. End the session with the task checklist current and a one-line "where we are / next" in the
   active task file.

| # | Phase | User does | Studio does | Playbook |
|---|---|---|---|---|
| 0 | Setup | sees editors connected | `/kiln:setup`, `/kiln:doctor` | `0-setup.md` |
| 1 | Concept | answers 2–3 rounds of option questions, approves the pitch | pitch, pillars, loop, mechanics table, scope contract, hooks | `1-concept.md` |
| 2 | Style | marks references on a board, locks a direction | reference hunt, directions, art bible | `2-style.md` |
| 3 | Tech plan | approves risky choices | tech-designer notes and spikes | `3-tech.md` |
| 4 | Look-dev | approves "the game will look like this" | one lit scene with hero assets and HUD mock | `4-lookdev.md` |
| 5 | Mechanics | plays each gym, says what is off | one mechanic at a time: spec in numbers, gym, acceptors, tuning | `5-mechanics.md` |
| 6 | Vertical slice | plays cold, decides continue / rework / pivot | full flow at final quality, game-ness checklist | `6-slice.md` |
| 7 | Content | plays batches | levels and encounters to the scope contract | `7-content.md` |
| 8 | Polish | says "good enough" | one biggest gap per round, first 60 seconds, performance | `8-polish.md` |
| 9 | Release | decides whether and where to publish | builds, soak test, credits, store material from real captures | `9-release.md` |

Going back is normal: `pipeline.py reopen <n>` when a later phase shows an earlier decision was
wrong (e.g. the style does not survive real lighting). Gates are reopened, never deleted.

## Talking to the user

- Questions go through AskUserQuestion: 1–4 questions per call, 2–4 options each, the
  recommended option first and marked "(Recommended)". Clicking every recommendation must give a
  coherent result. Show what each option means in `preview` when it helps (an ASCII camera
  mock-up, a pitch card).
- Ask only what is the user's taste and expensive to change later. Technical choices are the
  studio's; record them with `decide --by agent`.
- Every summary you ask the user to approve ends with an **Assumed:** line listing the defaults
  you chose silently — a visible assumption is fine, a hidden one is not.
- Never re-ask something already recorded in `GAME.md`, `memory/decisions.md` or
  `production/PLAYTESTS.md`.
- Talk in the user's language; files stay in English.

## Rules that hold in every phase

1. **Evidence, not claims.** A gate closes on a capture, a measurement, a command result or the
   user's word — never on an agent's report alone. Agents have reported "done" with nothing
   written.
2. **The builder never grades its own work.** Implementation roles hand off; acceptance roles,
   the art-director and the verifier judge. Self-grading reliably skews positive.
3. **Fun is the user's call.** Agents measure (numbers, captures, checklists); only the user says
   whether it is fun. Models cannot judge engagement from footage.
4. **Decide what "done" means before building**: every mechanic, level and system gets its
   acceptance checks and test interface (start state, player actions, what is measured,
   invariants) written first.
5. **Game first.** `pipeline.py status` warns when commits drift into docs/tests/tools or tests
   outgrow game code — the next step is then game work.
6. **Cut scope, not quality.** The scope contract (`production/SCOPE.md`, checked by
   `scope.py`) can only shrink through a recorded decision, never by deleting a line.
7. **Fresh facts before key steps.** Phases that depend on external knowledge (style, tech,
   mechanics, release) start with a short research note in `research/<topic>.md`.
8. **Kiln rules apply throughout**: Blender and the engine editor only through their MCP servers, scenes
   built visually, one driver per editor (see the protocol skill).

## Cross-cutting tools

- **Playtests with the user** — `references/playtest-with-user.md`: how to hand over a build,
  the feedback questions, recording `PT-NN` entries verbatim, routing findings.
- **Game-designer layer** — `references/designer-layer.md`: at fixed points the game-designer
  proposes hooks, twists, synergies and moments as cards; the user approves; unapproved ideas are
  never built; every idea gets a row so rejected ones are not re-pitched.
- **Gauntlet (blind A/B)** — `references/gauntlet.md`: for critical parts or when the user is
  unimpressed, compare our capture with a bar without knowing which is which (`ab.py`).
- **Feel in numbers** — `references/feel-numbers.md`: translate "floaty", "weak", "sluggish" into
  milliseconds, frames and metres before tuning.
- **Boards** — `scripts/board.py`: show images to the user in the browser, collect likes,
  comments and a choice; run `serve` in the background, its exit means the user answered.
- **Preferences** — when the user states how they like to work, or a phase ends, ask once
  which lessons to keep; store game taste in `memory/preferences.md`, working-style rules (not
  taste) in `${CLAUDE_PLUGIN_DATA}/preferences.md`. The project's file wins over the global one.

## Deciding for the user (`user_gates`)

`user_gates=proxy` (the default; the user is often busy and would rather redo a choice later than
be blocked): user gates and user decisions — scope details, the look, "fun" — are closed **by
proxy** with the recommended option, recorded with `--by proxy` (marked PROXY; automatic while
`.kiln/autopilot` exists), and every proxy decision is listed in the next report for review. When
the user returns, ask in one multiSelect which proxy decisions to redo. The game-designer layer may
approve at most two S/M-cost ideas per phase by proxy. `user_gates=ask` (opt-in): the agent never
stands in for the user — it asks and waits on every user gate.

Never proxy, in either mode: publishing, spending money, deleting user work, and overriding a
decision the user made themselves (a style they locked, a choice they answered).

## Autopilot

`/kiln:autopilot` runs this pipeline unattended under the same `user_gates` rule.
