"""Stop / SubagentStop hook for Kiln projects.

stop:     release the main session's editor locks. In autopilot mode, if the active tasks still
          have open checklist items (or ready backlog work remains) and nothing is blocked, ask
          the model to continue instead of ending the turn — at most `autopilot_max_nudges`
          times in a row without progress, so a stuck run still stops and can be reviewed.
          Only the session that typed /kiln:autopilot is pushed; another session open in the
          same project (the user asking for status) ends its turn normally. With
          `.kiln/stop-after-task` present it pushes only to finish the task in progress (backlog
          `[~]`), then lets the run end so it never stops half-way through a task.
subagent: release that agent's editor locks; if a Kiln role ended without a status line at the
          top of its reply, ask it once to append its handoff and lead with the status.
"""

import hashlib
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kiln_hooklib as k  # noqa: E402

STATUS_LINE = re.compile(
    r"^\W*(status|verdict)?\W*(DONE|NEEDS_WORK|BLOCKED|PASSED|PASS|FAIL|APPROVED|"
    r"CHANGES_REQUIRED)\b", re.I)


# A gate the user closes ends with "- user", optionally followed by pipeline.py's markers
# ("REOPENED <date>", "REGRESSED ...").
USER_GATE = re.compile(r"\u2014 user(\s+(REOPENED|REGRESSED)\b.*)?$")


def leave_queues(root, owner, session):
    """Drop a stopped agent from every editor queue: a finished agent cannot be first in line."""
    path = os.path.join(k.kiln_dir(root), "queue.json")
    with k.locked(path):
        queues = k.load_json(path, {})
        kept = {res: [w for w in line if w.get("owner") != owner
                      or w.get("session", session) != session] for res, line in queues.items()}
        if kept != queues:
            k.save_json(path, kept)


def release_locks(root, owner, session):
    """Free this session's locks of `owner` — every session's main is "main", so a lock taken
    by another session (e.g. a headless autopilot) is never released from here."""
    path = os.path.join(k.kiln_dir(root), "locks.json")
    with k.locked(path):
        locks = k.load_json(path, {})
        kept = {res: entry for res, entry in locks.items()
                if entry.get("owner") != owner or entry.get("session", session) != session}
        if kept != locks:
            k.save_json(path, kept)


def ready_backlog_items(root):
    try:
        text = open(os.path.join(root, "backlog.md"), encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    return re.findall(r"^\s*- \[ \]\s*(.+)$", text, re.M)


def in_progress_ids(root):
    """TASK ids marked in progress in the backlog (`- [~] TASK-NNN`)."""
    try:
        text = open(os.path.join(root, "backlog.md"), encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    return re.findall(r"^\s*- \[~\]\s*(TASK-\d+)", text, re.M)


def porcelain_paths(root):
    try:
        out = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=root,
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    paths = []
    for line in out.splitlines():
        name = line[3:].split(" -> ")[-1].strip().strip('"')
        if name:
            paths.append(name)
    return paths


def closed_ids(root):
    try:
        text = open(os.path.join(root, "backlog.md"), encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    return re.findall(r"^\s*- \[[xX]\]\s*(TASK-\d+)", text, re.M)


def check_closed_tasks_committed(root, session):
    """A task closed in the backlog whose paths still have uncommitted changes blocks the turn
    end once (g2 row 18: the commit step slipped with many agents running)."""
    ids = closed_ids(root)
    if not ids:
        return False
    changed = porcelain_paths(root)
    if not changed:
        return False
    found = []
    for task_id in ids:
        globs = k.task_globs(k.task_text(root, task_id)) + [f"tasks/{task_id}*"]
        hits = [p for p in changed if k.path_matches(p, globs) or
                re.match(rf"tasks/(archive/)?{task_id}\b", p)]
        if hits:
            found.append((task_id, hits))
    if not found:
        return False
    state_path = os.path.join(k.kiln_dir(root), "commit-nudge.json")
    signature = hashlib.sha1(repr(found).encode()).hexdigest()
    if k.load_json(state_path, {}).get("signature") == signature:
        return False
    k.save_json(state_path, {"signature": signature})
    listed = "; ".join(f"{tid}: {', '.join(hits[:6])}" for tid, hits in found[:4])
    k.emit({"decision": "block", "reason": (
        f"Closed task(s) with uncommitted changes — {listed}. Commit and push them now "
        "(git add <those paths> + the task file, commit, push), or say why they stay "
        "uncommitted. This reminder is shown once for this state.")})
    return True


def check_closed_tasks_gated(root, policy):
    """A task closed in the backlog whose `## gates` table still owes a role a verdict blocks the
    turn end once (g2 rows 45-46: roles skipped without a recorded reason)."""
    found = []
    for task_id in closed_ids(root):
        text = k.task_text(root, task_id)
        if k.gate_rows(text) is None:
            continue  # tasks planned before the gates table
        missing = k.missing_gates(text, policy.get("kind", "game"),
                                  policy.get("perf_gate", "on"))
        if missing:
            found.append((task_id, missing))
    if not found:
        return False
    state_path = os.path.join(k.kiln_dir(root), "gates-nudge.json")
    signature = hashlib.sha1(repr(found).encode()).hexdigest()
    if k.load_json(state_path, {}).get("signature") == signature:
        return False
    k.save_json(state_path, {"signature": signature})
    listed = "; ".join(f"{tid}: {', '.join(m)}" for tid, m in found[:4])
    k.emit({"decision": "block", "reason": (
        f"Closed task(s) with open gates — {listed}. Run those roles, or record `SKIP: <reason, "
        "decision #>` in the task's gates row and reopen the backlog line if the work is not "
        "accepted (`pipeline.py gates TASK-NNN` lists them). Shown once for this state.")})
    return True


def stop(data, root, policy):
    if data.get("subagent_turn"):
        return  # Copilot fires agentStop in a subagent's own session too: not the producer's turn
    session = data.get("session_id") or ""
    release_locks(root, "main", session)
    if check_closed_tasks_committed(root, session) or check_closed_tasks_gated(root, policy):
        return
    if not os.path.exists(os.path.join(root, ".kiln", "autopilot")):
        return
    who = k.autopilot_session(data, root)
    if who == "other" or (who is None and k.runtime() not in ("codex", "gemini", "copilot", "opencode")):
        return  # only the session that typed /kiln:autopilot is kept going (Codex, Gemini, Copilot, OpenCode: unknown)
    running = k.running_agents(root, session)
    if running:
        # Their notifications wake this session; a nudge now only buys busy-work (g2 row 125).
        k.log(root, "autopilot: waiting on " + ", ".join(f"{r} {a}" for a, r, _ in running))
        return
    tasks = k.active_tasks(root)
    stop_file = os.path.join(root, ".kiln", "stop-after-task")
    if os.path.exists(stop_file):
        started = set(in_progress_ids(root))
        unfinished = [(t["file"], item) for t in tasks for item in t["open"]
                      if any(re.search(rf"(?<![\w-]){re.escape(tid)}(?!\d)",
                                       os.path.basename(t["file"])) for tid in started)]
        if not unfinished:
            k.log(root, "autopilot: stop requested and no task in progress, letting the turn end")
            return
        listed = "; ".join(f"{f}: {item}" for f, item in unfinished[:5])
        k.emit({"decision": "block", "reason": (
            f"Stop requested (.kiln/stop-after-task): finish the task in progress — {listed} — "
            "then start nothing new: write .kiln/resume.md (task, state, next step), remove "
            ".kiln/autopilot and .kiln/stop-after-task, report to the user and end.")})
        return
    if any(task["blocked"] for task in tasks):
        return  # a blocked task is a hard stop; the run skill reports it
    open_items = [(task["file"], item) for task in tasks for item in task["open"]]
    backlog = ready_backlog_items(root)
    phase, gates = open_phase_gates(root)
    agent_gates = [g for g in gates if not USER_GATE.search(g)]
    if not open_items and not backlog and not agent_gates:
        return
    state_path = os.path.join(k.kiln_dir(root), "autopilot-state.json")
    signature = hashlib.sha1(repr((open_items, backlog, agent_gates)).encode()).hexdigest()
    limit = int(policy.get("autopilot_max_nudges", 3))
    with k.locked(state_path):  # the owner fields are written by other sessions' hooks
        state = k.load_json(state_path, {})
        nudges = state.get("nudges", 0) + 1 if state.get("signature") == signature else 1
        state.update({"signature": signature, "nudges": nudges})
        k.save_json(state_path, state)
    if nudges > limit:
        k.log(root, f"autopilot: no progress after {limit} nudges, letting the turn end")
        return
    if open_items:
        listed = "; ".join(f"{f}: {item}" for f, item in open_items[:5])
        reason = (f"Autopilot: open checklist items remain — {listed}. Continue with them. "
                  "If one is blocked, record why in the task file (status: BLOCKED) and say so.")
    elif backlog:
        reason = (f"Autopilot: the active task is closed but the backlog still has "
                  f"{len(backlog)} open item(s), next: {backlog[0][:120]}. Pick the next ready "
                  "task per the kiln run skill and continue.")
    else:
        reason = (f"Autopilot: the backlog is done but pipeline {phase} still has open gates: "
                  + "; ".join(g[:90] for g in agent_gates[:4]) + ". Plan tasks that close them "
                  "(kiln plan skill, the phase playbook in the pipeline skill) and continue.")
    k.emit({"decision": "block", "reason": reason})


def open_phase_gates(root):
    """(phase title, open gate lines) of the first pipeline phase that still has open gates."""
    path = os.path.join(root, "production", "PIPELINE.md")
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return "", []
    phase, gates = "", []
    for line in lines:
        if line.startswith("## Phase"):
            if gates:
                return phase, gates
            phase = line[3:].strip()
        elif re.match(r"^\s*- \[ \]", line) and not re.search(r"\b(SKIP:|BLOCKED:)", line):
            gates.append(re.sub(r"^\s*- \[ \]\s*", "", line).strip())
    return phase, gates


def delegated_task(data):
    """True if the subagent's delegation prompt pointed at a task file (TASK-NNN). OpenCode has
    no transcript file: its plugin passes the prompt as delegation_prompt."""
    head = data.get("delegation_prompt") or ""
    path = data.get("agent_transcript_path") or ""
    if not head:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                head = fh.read(20000)
        except OSError:
            return False
    return re.search(r"TASK-\d+", head) is not None


def subagent(data, root, policy):
    release_locks(root, k.actor_id(data), data.get("session_id") or "")
    leave_queues(root, k.actor_id(data), data.get("session_id") or "")
    k.agent_stopped(root, data)
    if k.runtime() == "gemini":
        # invoke_agent finished: later calls are the main session's again. Its result is already
        # the main agent's; a handoff nudge here would only replace it.
        k.clear_gemini_agent(root)
        return
    role = k.role_of(data)
    if role not in k.KILN_ROLES or data.get("stop_hook_active") or not delegated_task(data):
        return  # ad-hoc questions to a role need no handoff
    message = (data.get("last_assistant_message") or "").strip()
    if message and not STATUS_LINE.match(message):
        k.emit({"decision": "block", "reason": (
            "Kiln protocol: append your '## handoff' section to the task file (status, changed, "
            "evidence, open, next) and start your final reply with the status line.")})


def main(data):
    root = k.project_dir(data)
    policy = k.kiln_manifest(root)
    if policy is None:
        return
    mode = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "stop"
    if mode == "subagent":
        subagent(data, root, policy)
    else:
        stop(data, root, policy)


if __name__ == "__main__":
    k.run_safely(main)
