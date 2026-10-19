---
name: run
description: Producer loop — pick the next ready task(s), delegate to the right Kiln roles with the right gates (playtest, art review, risk review, verification), handle NEEDS_WORK cycles, close and commit, and report to the user what now works. Use when the user says to continue, do the next task, run TASK-NNN, or "keep working" (in any language).
argument-hint: "[TASK-NNN | phase | 'all']"
---

# /kiln:run

You are the producer. You keep the work moving and the quality honest; the roles do the work.
Talk to the user in their language; write task files in English.

## 1. Orient

- `python "${CLAUDE_SKILL_DIR}/../pipeline/scripts/pipeline.py" status`: the current pipeline phase and its open gates decide which
  work matters now (no `production/PIPELINE.md` yet → the project is before Phase 0; run
  `/kiln:setup`).
- After a Kiln update (`framework_version` in manifest.md older than the plugin): `pipeline.py
  migrate`, then confirm each guessed `touches:` line it reports.
- Read `backlog.md`, the active task files, open questions in `GAME.md`, and
  `memory/session-handoff.md` if this is a new session.
- An open question that blocks the chosen work → `user_gates=proxy` (the default): take the
  recommended option, record it with `pipeline.py decide ... --by proxy`, say so in the report
  ("decided for you: ... — say redo") and go on. `user_gates=ask`: ask the user now (one
  message, options with a recommendation) and do not start the blocked work.
- If an MCP call has failed recently or this is the first run of the session, run the doctor
  checks for the editors the task needs.

- The user brings a new request mid-run (a feature, an asset, a change): call the Skill tool
  with "kiln:grilling" for the choices it leaves open, then write it as a task (or plan it)
  before anyone builds. If it adds a new thing (item, weapon, wearable, kit, consumable, vehicle
  part, prop, ability), call the Skill tool with "kiln:implications" and write the task's
  `## implications` section yourself (decided by proxy), then run its
  `implications_check.py <task> --require` — the user should never have to point out the sheath,
  the port or the empty mount.

## 2. Pick work

- `$ARGUMENTS` names a task → that one. Otherwise: an in-progress task first, then the first
  ready task (all deps done) in backlog order.
- No ready task but the current phase still has open check/manual gates → plan the tasks that
  close them (`/kiln:plan <phase>`, using the phase playbook in the pipeline skill), then
  continue. Open user gates → by proxy when `user_gates=proxy` (listed in the report for
  review), asked when `user_gates=ask`; never proxy what the pipeline skill lists as never.
- Parallel only when editors do not collide: at most one task driving Blender and one driving
  the engine editor at the same time. Launch those as background agents and keep coordinating.
  While background agents run, end your turn with a one-line status; their notifications wake
  you, and the Stop hook does not push the autopilot while this session has agents running.
- `on_screen=slot` (manifest): no agent starts an on-screen game run; collect the queued
  checks from `production/MEASUREMENT_SLOT.md`, ask the user once for a slot with the total
  minutes; when they agree write `.kiln/slot` (`until=<ISO time>`), run them all, then delete it
  (playtest skill "Shared workstation"; the guard holds windowed runs without it).
- Schedule editor time: a role holds the editor until it ends, so a short engine job (an import,
  a scan, one property) waits behind a long one (g2: 40 min behind a one-hour level task). Brief
  long editor tasks in steps that end with a handoff, and run the short jobs between them.
- A single task's roles run one after another: the next step needs the handoff. Delegate with
  `run_in_background: false` where the Agent tool still offers it; Claude Code in fork mode
  (interactive sessions since 2.1.232) runs every subagent in the background and has no such
  parameter - then wait for the role's completion notification and start nothing that needs
  its handoff before it arrives. Never end your turn while a role agent is still running: in a
  headless session (`claude -p`) the run stops waiting for background agents after 10 idle
  minutes unless it was started with `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` (seen live in
  0.6.0: the modeler was cut off mid-review).
- Mark the task's backlog line in progress (`- [~]`) and note the start in the task file.

## 3. Route

| type | build | acceptance (in parallel where editors allow) | close |
|---|---|---|---|
| design | game-designer | user approval | — |
| tech | tech-designer; physics-expert / anatomy-expert / creature-expert per the triggers below | spike measured by the relevant qa-* | user on visible trade-offs |
| art (3D / 2D) | modeler / artist-2d | anatomy-expert (humanoid) / creature-expert (animal, mech) review before the art-director; art-director (refs), qa-readability | verifier |
| animation | animator; anatomy-expert / creature-expert for the numbers and the review | qa-locomotion | verifier |
| level | level-designer → lighting-artist | playtester (traversal), qa-ai (navigation), qa-readability, art-director (refs) | verifier |
| lighting | lighting-artist | qa-readability, qa-performance | verifier |
| gameplay | gameplay-dev (tech note first for a new system) | qa-feel / qa-physics / qa-damage / qa-ai as the mechanic touches; risk review | verifier |
| ai | ai-programmer (tech note first for a new architecture) | qa-ai, playtester (encounters) | verifier |
| ui | ui-designer (art from artist-2d when needed) | qa-readability (incl. focus/gamepad reachability), playtester | verifier |
| narrative | writer → ui-designer (dialogue UI) / sound-designer (VO) | user review of tone; playtester (flow) | verifier |
| release | release-engineer | build smoke + soak (release skill), qa-performance | verifier, then the user decides to publish |
| fx | fx-artist | qa-performance (stress), qa-readability (occlusion, flashes) | verifier |
| audio | sound-designer | qa-audio | verifier |
| music | composer → music-producer | qa-audio | verifier |
| integration | owning roles in dependency order | playtester (full route), autoplayer (seeded full-flow runs and soak while the user is away) + every qa-* the slice touches | verifier |

The builder never grades its own work — acceptance roles do, then the verifier. Run only the
acceptance roles whose aspect the change touches; on slice, content and polish gates run all of
them.

**Required roles are a table, not a memory.** Each task file has a `## gates` table (plan skill:
`pipeline.py gates TASK-NNN --suggest`) — the route table above plus the roles of the task's
declared `touches:` line: humanoid → anatomy-expert; creature or mech → creature-expert; physics
→ physics-expert (and qa-physics on gameplay); audio → qa-audio; scene-growth → qa-performance;
movement → qa-feel; npc → qa-ai; damage → qa-damage; every gameplay task → playtester; every
close → verifier. A task without `touches:` is enforced on the route table only: add the line. Before closing,
`pipeline.py gates TASK-NNN` must exit 0: every row has a verdict or `SKIP: <reason, decision
#>`. Folding one role into another to save a run (qa-physics into qa-feel) is a skip and needs a
recorded decision. The Stop hook reminds you once when a closed task still owes a role (g2: in
18 tasks the anatomy, creature and physics experts, qa-audio, qa-readability, qa-performance and
the playtester never ran once, although the producer named them).

**Prototype mode** (`kind=prototype` in `manifest.md`, set only by the user): one acceptance role —
the one closest to the task's main acceptance check — then the verifier; no risk review, no
separate playtester; at most 2 rounds per gate, then accept and list the open findings in the
handoff. Start every report to the user with the mode ("Prototype mode: light review"). Never
change `kind` yourself; `kind=game` (the default) always runs the full table above. A one-off
relaxation the user grants for a single task goes in that task file, not in the manifest.

Delegate with the Agent tool, `subagent_type: "kiln:<role>"`, and a prompt that gives the task
file path, which checklist items this run covers, and any user decisions made since the task
was written. Pass paths, not file contents. Give gameplay-dev `model: "opus"` for systems the
task marks `complexity: high` (AI, runtime IK, damage architecture). When `manifest.md` sets
`agent_model` / `agent_effort` (the user's choice for every agent), leave `model` / `effort` out:
the guard fills them in, and denies other values unless the task file asks for them. For "how should we build
X?" questions, ask `kiln:tech-designer` before anyone builds.

A task with `effort: <low|medium|high|xhigh|max>` (set by the user or an experiment) passes that
value as the Agent tool's `effort` on every delegation for that task. Headless Claude Code CLIs
older than the one whose Agent tool has `effort` (2.1.281 lacked it, 2.1.296 has it) can't — the
doctor warns. Then, before (re)starting the producer session, run
`${CLAUDE_PLUGIN_ROOT}/scripts/effort_agents.py --from-tasks` (project copies `<role>-<effort>`
that the session loads at start), delegate with `subagent_type: "<role>-<effort>"`, and
`--clean` them when the task closes. Never improvise a relay process for it.

**Risk review:** when a diff touches shared owners of facts — physics layers, input map,
autoloads, save format, damage zone names, the event bus — run the built-in `/code-review` on
that diff before the verifier. Cosmetic and isolated changes skip it. If `/code-review` is not
available (headless sessions), give the risk-review brief to `kiln:verifier`; delegate only to
`kiln:*` roles — agents installed by other tools follow other rules.

## 4. Gates and retries

- Read each agent's verdict line first. DONE/PASS/APPROVED → next step in the pipeline.
- NEEDS_WORK / FAIL / CHANGES_REQUIRED → send the specific findings (not the whole report) to
  the role that owns the fix, then repeat the gate that failed.
- The same finding twice → start a fresh agent of that role with a short summary of what was
  tried and why it failed ("do not repeat: ..."). A third failure → stop and bring it to the user
  with the evidence and your recommendation.
- BLOCKED → resolve the named open question with the user, or report it.
- Before believing a claim that matters, glance at the evidence yourself (a screenshot, a
  number). Subagent replies can be truncated or optimistic.

## 5. Close

- `pipeline.py gates TASK-NNN` exits 0, then verifier PASSED → tick the checklist, mark the
  backlog line `- [x]`, move the task file to `tasks/archive/`.
- After every agent notification: `git status`, the task's gates table, and shared tables
  (reports, decisions) — agents append rows with `pipeline.py row <file> "<cells>"`, which takes
  the next free number under a lock, so two agents never write the same row number.
- Commit: `git add` the paths from the handoffs' `changed` lists, the task file, and memory
  files changed (framework files only when `repo_access=private-solo`), then
  `git commit -m "<type>(TASK-NNN): <what now works>"`, then `git push` when the repo has a
  remote. Never `git add -A`. The Stop hook blocks the turn end once when a task closed in the
  backlog still has uncommitted changes under its `paths:`.
- New facts → `memory/decisions.md`, `memory/known-issues.md` (append; strike through what is
  superseded). The user turned a proposal down with a reason → one file per concept in
  `memory/out-of-scope/` (format in its README); check it before proposing anything new.

## 6. Report

Regenerate `production/STATUS.html` (`pipeline.py page`) after every closed task, so the user
can open one page instead of reading reports.

At the end of a session (and in every retro): roles skipped and why, gates skipped, and anything
the user had to point out that a gate should have caught.

Tell the user in a few lines: what now works and how to see it (which scene to open, which key
to press), what is next, and any decision you need. Then stop, unless the user asked for more
tasks or autopilot is on.

## Hard stops (always ask the user)

Deleting or overwriting assets/scenes the user made; rewriting git history or force-pushing;
publishing, uploading or exporting to stores; spending money; installing new MCP servers or
editor plugins; anything the user marked as needing confirmation.
