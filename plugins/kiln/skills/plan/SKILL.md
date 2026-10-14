---
name: plan
description: Turn GAME.md and design specs into a phased backlog of task files — batches per role, dependency order (model → rig → animation → gameplay → integration), gyms before levels, editor-exclusive scheduling, acceptance checks copied from the design. Use after /kiln:concept, when the design changes, or when the backlog runs dry.
argument-hint: "[phase or feature]"
---

# /kiln:plan

## Principles

- **Big batches, few starts.** A task gives one role a coherent zone of work ("all parts of the
  enemy walker: model, damage split, collision, export"), not one operation. Starting an agent
  costs reading the rules and the project every time, so fewer, larger tasks finish faster —
  measured on a real project as 22 tasks in 12 agent starts versus 9 starts per task before.
- **Playable early.** Phase 1 ends with something the user can play: the core mechanic in a gym
  with placeholder art beats beautiful art with nothing to do.
- **Gyms before levels.** Every mechanic is proven in its gym scene before a level uses it.
- **Dependency chain for characters:** model (+ damage parts) → rig + clips → in-engine
  animation setup → gameplay. Environment kit → level blockout can start in parallel with greybox.
- **Name the move set.** For a controllable character, list the moves in scope and confirm them
  with the user before planning — a brief saying "just walk around" still left the user
  expecting jump and crouch (live run). Default third-person set to offer: idle, walk, run,
  jump + land, crouch + crouch-walk, turn in place; combat moves only when asked.
- **Whole-body acceptance for animation tasks.** Besides feet, slip and stride, every clip task
  checks arms (swing range and phase against the legs), spine and head — the live rig task's
  acceptance spoke only of legs, and all its clips shipped with the arms frozen in the A-pose.
- **Editors are exclusive.** Only one task at a time can drive Blender and one can drive the
  engine editor. Plan so that a Blender task (modeling, rigging) can run alongside an engine task
  (gameplay, level, fx) — that is the real parallelism available.
- **Plan by pipeline phase.** Read `production/PIPELINE.md` and the phase playbook
  (`${CLAUDE_SKILL_DIR}/../pipeline/phases/<n>-*.md`): every open check/manual gate of the
  phase is closed by some task's acceptance.
- **Scale to the ask.** A demo, prototype, test scene or single feature the user described in a
  brief is not a game: the brief is the concept and the style direction. Plan only the tasks
  that produce what it asks for (asset, rig, scene, mechanic, and a build only if asked); fold
  technique decisions into those tasks instead of separate concept interviews, style boards,
  art bibles or tech notes, and give the user one look check on the result. Name what you left
  out in one line. Live run: "a simple demo scene" was planned as 10 tasks with two user
  decisions on the critical path; the user cut it to 6.

## Steps

1. Read `GAME.md`, `design/*.md`, `backlog.md`, existing `tasks/`, `memory/*.md` and
   `memory/out-of-scope/` (do not plan a rejected idea; matched by meaning). Open player-facing
   choices left (move set, look, scope) → call the Skill tool with "kiln:grilling" first. Skip what
   already exists in the project (check files and scenes) — plan completion, not rewrites.
2. Draft phases (at most 3 ahead) and tasks. For each task write `tasks/TASK-NNN.md` using the
   task format from the protocol skill: type, role, batch, paths, depends_on, refs, acceptance
   (copied from the design spec's acceptance checks, sharpened into observable checks), and a
   checklist of 4–10 concrete steps. A task that adds a new thing (item, wearable, part,
   consumable, prop, ability) also gets an `## implications` section — call the Skill tool with
   "kiln:implications"; `implications_check.py <task> --require` must pass, and the host-side
   assets it names become checklist steps or tasks of their own. Animation and locomotion tasks
   copy the applicable rows of the animation skill's `references/reads-wrong.md` into their
   acceptance.
   Every task declares what it touches — `touches: humanoid, physics, audio, ...` or
   `touches: none` — from what it builds or changes, not from words in its acceptance (a facade
   a character walks past does not touch `humanoid`). Then `pipeline.py gates TASK-NNN
   --suggest` prints the `## gates` table: route-table roles plus the roles of each touch
   (humanoid → anatomy-expert, creature/mech → creature-expert, physics → physics-expert and
   qa-physics, movement → qa-feel, npc → qa-ai, damage → qa-damage, audio → qa-audio,
   scene-growth → qa-performance). Without the line it guesses from the title, batch and paths
   only — confirm the guess and write the line; the gates enforce declared touches, never
   guesses. Keep every row; a role that truly does not apply gets `SKIP: <reason>` now, never a
   silent deletion and never "if needed" in parentheses.
3. Add one line per task to `backlog.md`:
   `- [ ] TASK-NNN [type] name · role:<role> · deps:<ids|none> · editor:<blender|engine|both|none> → tasks/TASK-NNN.md`
4. Check: no dependency cycles; every acceptance check in the design is covered by some task;
   no two tasks write the same paths in the same phase unless they are ordered.
5. Show the user the phase list with task one-liners and the critical path; ask for approval or
   one change. Then suggest `/kiln:run`.
6. `kind=prototype`: the brief is the concept (scale to the ask). When the user switches the
   project to `kind=game`, plan a **promotion** task first: re-run the full acceptance (every
   acceptance role the run skill's route table names, risk review, playtester) over everything
   closed while it was a prototype, and open tasks for what fails.

Write task files and backlog in English. Keep each task file under ~80 lines at creation.
