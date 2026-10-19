---
name: autopilot
description: Run the backlog unattended — the producer loop from /kiln:run, chaining tasks without stopping between them, with Stop-hook continuation and hard stops. Use only when the user explicitly asks to work on their own / while they are away.
disable-model-invocation: true
argument-hint: "[scope note, e.g. 'only phase 1' or 'until the hero is done']"
---

# /kiln:autopilot

1. Confirm in one line what will run (scope from `$ARGUMENTS`, else the whole ready backlog) and
   that you will stop only on the hard stops below. Run `/kiln:doctor` checks for the editors
   the backlog needs; a failing editor is a hard stop before starting.
2. Turn autopilot on: write `.kiln/autopilot` with the date and the scope note.
   The Kiln Stop hook now reminds you of open checklist items and ready backlog work when a turn
   ends, up to `autopilot_max_nudges` times without progress. It pushes only the session that
   typed `/kiln:autopilot`; other sessions in the project end their turns normally.
   GitHub Copilot CLI ends a turn after 8 hook continuations in a row: there, check that the
   session is in Copilot's autopilot mode (`copilot --autopilot`, or Shift+Tab); if it is not,
   tell the user once that the run will stop after about 8 steps without it.
   Gemini CLI headless (`gemini -p`) needs `--approval-mode yolo`; roles run one at a time.
   Claude Code headless (`claude -p "/kiln:autopilot ..."`): start it with the environment
   variable `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` (Claude Code 2.1.182+); by default `-p`
   gives up on background roles after 10 idle minutes and drops their work. For long unattended
   runs an interactive session is better: signed in with a claude.ai subscription it waits for
   a usage limit to reset and continues; `-p` does not.
3. Run the `/kiln:run` loop, but after closing a task pick the next ready one instead of
   stopping. Keep each task's checklist current — the hook reads it to know what is left. Mark
   the task you work on `[~]` in the backlog.
   **Before picking the next task, check `.kiln/stop-after-task`** (written by `/kiln:stop`): if it
   exists, start nothing new — write `.kiln/resume.md` (tasks closed this run, the next ready
   task, anything half-built and where its files are), remove `.kiln/autopilot` and the stop
   file, run the retro and report.

## Resume after an interruption

On start, and whenever a run was killed (usage limit, crash): read `.kiln/resume.md` if present,
then `git status` — for each `[~]` task, uncommitted files in its paths are the interrupted
role's partial work. Read the task's latest log and handoff lines, continue from those files
(rerun the interrupted role with "continue from the uncommitted changes in <paths>"), and rerun
an interrupted acceptance role from scratch — partial measurements don't count.
4. The backlog empties before the pipeline does: run `pipeline.py status`, plan the tasks
   that close the current phase's open check/manual gates (`/kiln:plan <phase>`) and keep
   going; user gates are closed by proxy per the pipeline skill. The Stop hook also names open
   gates when the backlog is done.

## Standing instruction while autopilot is on

The user is away and wants the work done, not reported on. A message with no tool call ends
your turn and the work stops until the user returns. Do not end a turn with a summary that
announces the next step, with an offer to continue, with a list of decisions that do not block
the remaining work, or because a milestone feels like a good place to report. Put status notes
in the same message as your next tool call and carry on with whatever does not depend on the
user. The stops you should make are the hard stops below.

## Hard stops — remove `.kiln/autopilot`, write the report, stop

- An open question or BLOCKED handoff that blocks all remaining ready work.
- An editor is not connected or the doctor check fails.
- A third failure of the same gate on the same task.
- A test regression in previously passing gyms/tests that you cannot attribute and fix.
- Anything in the run skill's "Hard stops" list (deleting user work, publishing, money, new
  plugins). A paid generation is not a stop by itself: `gen_api.py request <job> --why ...`
  puts its estimate into `production/SPEND_REQUESTS.md` and the run goes on with work that
  needs no money (the local route, other tasks); it stops only when nothing else is left.
- Scope reached, or no ready task left and the current phase's remaining gates are ones you
  may not proxy (publishing, money, deleting user work).

## Retro, then the report

Before the report, call the Skill tool with "kiln:retro" for this autopilot run (since the
`.kiln/autopilot` start date, transcript = this session's log when there is one).

## Report (in the user's language)

Tasks closed (with what now works and how to see it), tasks blocked and why, decisions you took
on the user's behalf (for review), the retro's top three findings, the waiting rows of
`production/SPEND_REQUESTS.md` as one yes/no per row (credits, about how many dollars, why),
and the next ready task. If a push-notification tool is
available, send a one-line summary.
