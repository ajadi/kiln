---
name: report
description: Write the user's own complaint about Kiln into kiln-report.md - what went wrong, where, what they would want instead - as one numbered row next to the problems the agents report while working. Use when the user wants to complain about Kiln, report a Kiln problem or leave feedback for the framework.
disable-model-invocation: true
argument-hint: "[what went wrong]"
---

# /kiln:report

`kiln-report.md` (project root) collects problems with Kiln itself: the roles and the main session
add rows while they work (project rules, "Problem reports"); this command adds the user's.

1. The complaint is `$ARGUMENTS`. Empty → ask once, in the user's language: what went wrong and,
   if they have one, what they would want instead.
2. "This", "just now", "that denial" → take the facts from this session: the exact message, the
   command or tool call, the skill or role involved. Never invent a detail the session does not
   show; unknown stays unknown.
3. Fill the row in English, short, keeping the user's point (not softened):
   - `who` = `user`;
   - `area` = guard, hooks, setup, tools, pipeline, autopilot, a skill or role name, docs, other;
   - `what happened` with the exact error text when there is one;
   - `suggestion` = theirs, else `-`;
   - `status` = `open`.
   Replace `|` inside cells with `/`.
4. `python "${CLAUDE_SKILL_DIR}/../pipeline/scripts/pipeline.py" row kiln-report.md "<YYYY-MM-DD> | user | <area> | <what happened> | <suggestion> | open"`
   (creates the file with its header the first time).
5. Answer in one line: the row number and what was recorded.
6. Offer once: send it to the Kiln authors as a GitHub issue (`gh issue create --repo ajadi/kiln`).
   Show the exact title and body first, without paths, user names, project secrets or game
   content the user did not mention; create it only on their yes.

The file is framework state: it is committed according to `repo_access` like `memory/`.
