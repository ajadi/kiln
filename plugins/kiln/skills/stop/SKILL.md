---
name: stop
description: Ask a running autopilot to stop cleanly after the task it is working on — writes .kiln/stop-after-task so the run finishes the current task, writes a resume point, turns autopilot off and reports, instead of being killed mid-task. Use when the user says to stop, pause or wind down the autopilot (usage limit near, end of day).
disable-model-invocation: true
argument-hint: "[reason, e.g. 'usage limit']"
---

# /kiln:stop

1. Write `.kiln/stop-after-task` in the project root with the date, time and the reason
   (`$ARGUMENTS`, else "user request").
2. Say in one line what happens next: the autopilot finishes the task marked `[~]` in the
   backlog, writes `.kiln/resume.md`, removes `.kiln/autopilot` and this file, and reports. The
   Kiln Stop hook keeps it on the current task until then and lets it end afterwards.
3. If the user needs it stopped **now** (the limit is about to run out), say that killing the
   process leaves the task half-done and that the next autopilot run resumes it from the task's
   log and the uncommitted files (autopilot skill, "Resume"); kill only if they confirm.
