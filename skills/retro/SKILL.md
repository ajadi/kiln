---
name: retro
description: Retrospective on a Kiln session or task batch — mine the evidence (guard denials, tool errors, review rounds, the user's corrections, proxy decisions), turn each real problem into a fix for Kiln or the project, most costly first. Use when the user runs /kiln:retro, at the end of an autopilot run, or after a task needed three or more review rounds.
argument-hint: "[since: date or task id]"
---

# /kiln:retro

A retro finds what made this session slower or wrong and changes the environment so it does not
happen again. In the first live pipeline run, every framework fix (guard false positives, frozen
arms, lost editor locks, wrong delegation) was found by hand; this skill makes that a step.

## 1. Evidence

`python "${extensionPath}${/}skills${/}retro/scripts/retro_scan.py" --root . --since "<start>" --transcript <log>`
(`--since`: `$ARGUMENTS`, else the session or autopilot start; transcript: the autopilot's
stream-json log or the session transcript, when there is one). It groups guard denials by rule,
hook crashes, tool errors per tool, review rounds and verdicts per task, the user's requests and
corrections written into task logs, PROXY decisions, and agents that are not Kiln roles.
Add `--subagents ~/.claude/projects/<project>/<session>/subagents` (one per session of the run)
for each role run's effort, responses, output and thinking tokens and wall / tool / model minutes.
Judge effort or model changes with these measured numbers; text length badly misestimates
thinking (live: estimated 71 %, measured 36 %).

Role coverage comes in its `roles` block: roles that ran, roles the tasks required (route
table + `touches:`) that never ran, skips with their reasons, Kiln roles never used, and what
open tasks still owe. Put "roles never used" and "required roles that never ran" in every
retro report, each with why (g2: the anatomy, creature and physics experts, qa-audio and the
playtester never ran in 18 tasks, and only the user's question showed it).

Read the project's `memory/out-of-scope/` (and Kiln's own rejected ideas, when the fix is to Kiln and they are at hand) before
proposing anything — a rejected idea is not proposed again.

## 2. Findings

Each finding traces to a moment in the evidence — no hypothetical improvements. For each:

- **What happened and what it cost** — turns, review rounds, minutes, a user correction (the
  most expensive kind), a wrong result that shipped.
- **Mechanical or judgement.** A mistake a rule can catch every time is mechanical: fix it with a
  check — a guard rule or a narrower one (a false positive is a mechanical defect too), a test, a
  script, a template field. Prefer a check that runs to a rule that is read. Only what needs
  judgement becomes text in a skill or role, written as the positive target, with the live
  failure in the CHANGELOG rather than in the skill.
- **Where** — Kiln (which skill, role, hook, script) or this project (task template, memory,
  `known-issues.md`).
- **Prove it bites** — a new check is shown failing on the recorded case before it counts.

Signals worth a look: the same denial rule several times (a role that does not know the rule,
or a false positive when the work then succeeded another way); tool errors concentrated on one
MCP tool (the engine skill lacks a working call); a task with three or more CHANGES_REQUIRED
(the acceptance or the brief missed something — which check would have caught it on round 1?);
user lines after a task started (a question the grilling should have asked); PROXY decisions the
user later redid; non-Kiln agents; editor locks or hook crashes.

Defects in the pitfall format (animation `references/reads-wrong.md` is the model): write each
defect finding as class -> what it looks like (the user's words) -> why it happens -> the
principle of the fix (for the whole class, not this one clip) -> how to catch it. When the user
reported a defect that no check caught (`retro_scan.py` `pitfalls.user_reported`, and every
catalogue entry with `Caught by: no check yet`), propose the check as a follow-up task: a new
check, or an extension of an existing one (`analyze.py rigid` / `pops` / `hits`, `frames.py
anim` / `ramp`, `ref_compare.py`, a scene QA contract state); add the catalogue entry with `no
check yet` until the check exists.

## 3. Report

Write `production/retro/<YYYY-MM-DD>.md`: a table of findings, most costly first — evidence, cost,
class, proposed fix, where. Apply project-level fixes. Kiln fixes change the framework for every
project: list them for the user (with `user_gates=proxy`, apply the mechanical ones whose test
proves them and list them as decided-for-you; judgement changes wait for the user). Tell the user
the top three in a few lines.

A retro that finds nothing is fine; say so in one line.
