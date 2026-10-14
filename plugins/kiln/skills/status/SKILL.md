---
name: status
description: Short Kiln project status — backlog progress, tasks in progress with open checklist items, blocked work and open questions, editor locks, autopilot state, last session handoff, and the next ready task. Use when the user asks where things stand, what is next, or to resume after a break.
allowed-tools: Read, Glob, Grep, Bash
model: haiku
---

# /kiln:status

Run `python "${CLAUDE_SKILL_DIR}/../pipeline/scripts/pipeline.py" status` (skip if there is no
`production/PIPELINE.md`). Read (skip missing): `backlog.md`, `tasks/TASK-*.md` (not archive), `GAME.md` open questions
table, `memory/session-handoff.md`, `memory/session-handoff.auto.md`, `.kiln/locks.json`, `.kiln/autopilot`, `.kiln/stop-after-task`, `.kiln/resume.md`, `git status --short`.

Reply in the user's language, at most 12 lines:

```
Pipeline: phase <n> <name> — <closed>/<total> gates (next open gate: <text>)
Backlog: <done>/<total>
In progress: TASK-NNN <name> — <k> open items (next: <first open item>)
Blocked: TASK-NNN — OQ-NNN <question>        (omit if none)
Open questions: <n>                            (omit if 0)
Editors: Blender <free|held by role>, <engine> <free|held by role>
Agents: <role> <n> min, last call <m> min ago   (from pipeline.py status; flag silent >= 20 min)
Autopilot: on (<scope>) | stopping after the current task | off (resume point: .kiln/resume.md)
Uncommitted: <n files>                         (omit if 0)
Next ready: TASK-NNN [type] <name> → /kiln:run
```

For the full picture write the page: `pipeline.py page` → `production/STATUS.html` (phases,
tasks with the roles they still owe, agents and editor queue, decisions taken for the user,
the last autoplay night, checks waiting for the user's screen); give the user its path.

If this looks like a resumed session (handoff newer than the last commit), add one line: where
the last session stopped.
