"""Tests for plugins/kiln/hooks/stop.py autopilot continuation and lock release (stdlib only).

Live case (kiln-sandbox 2026-10-11): a headless `claude -p "/kiln:autopilot ..."` ran in the
background; the user opened a second session to ask for status, and the Stop hook pushed that
session to "continue with the open checklist items" three times — the autopilot's own tasks.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "hooks")
STOP = os.path.join(HOOKS, "stop.py")
SESSION = os.path.join(HOOKS, "session.py")

TYPED = ("<command-message>kiln:autopilot</command-message>\n"
         "<command-name>/kiln:autopilot</command-name>\n<command-args>demo</command-args>")


def make_project():
    root = tempfile.mkdtemp(prefix="kiln-stop-")
    with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write("project_name=t\nframework=kiln\nengine=godot\n")
    os.makedirs(os.path.join(root, "tasks"))
    with open(os.path.join(root, "tasks", "TASK-001.md"), "w", encoding="utf-8") as fh:
        fh.write("# TASK-001: helmet\n\n- [x] model\n- [ ] verifier re-check\n")
    os.makedirs(os.path.join(root, ".kiln"))
    with open(os.path.join(root, ".kiln", "autopilot"), "w", encoding="utf-8") as fh:
        fh.write("date: 2026-10-11\nscope: demo\n")
    return root


def transcript(root, name, entries):
    path = os.path.join(root, name + ".jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")
    return path


def typed(ts):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": TYPED}}


def quoted():
    """A tool result that quotes the command (e.g. reading another session's log) — not typed."""
    return {"type": "user", "timestamp": "2026-10-11T09:00:00Z", "message": {"role": "user",
            "content": [{"type": "tool_result", "content": "log: " + TYPED}]}}


def run(script, mode, root, session, path, event):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
    payload = {"session_id": session, "transcript_path": path, "cwd": root,
               "hook_event_name": event, "stop_hook_active": False, "source": "startup"}
    return subprocess.run([sys.executable, "-B", script, mode], input=json.dumps(payload),
                          env=env, capture_output=True, text=True, timeout=30).stdout


def stop(root, session, path):
    out = run(STOP, "stop", root, session, path, "Stop")
    return json.loads(out) if out.strip() else None


class AutopilotOwner(unittest.TestCase):
    def test_only_the_session_that_typed_autopilot_is_pushed(self):
        root = make_project()
        pilot = transcript(root, "pilot", [typed("2026-10-11T07:48:00Z")])
        user = transcript(root, "user", [quoted()])
        self.assertEqual(stop(root, "pilot", pilot)["decision"], "block")
        self.assertIsNone(stop(root, "user", user))
        self.assertEqual(stop(root, "pilot", pilot)["decision"], "block")

    def test_no_owner_known_does_not_push_a_plain_session(self):
        root = make_project()  # e.g. the autopilot never ended a turn since it started
        self.assertIsNone(stop(root, "user", transcript(root, "user", [quoted()])))

    def test_a_newer_autopilot_takes_over(self):
        root = make_project()
        old = transcript(root, "old", [typed("2026-10-11T07:00:00Z")])
        new = transcript(root, "new", [typed("2026-10-11T10:00:00Z")])
        self.assertIsNotNone(stop(root, "old", old))
        self.assertIsNotNone(stop(root, "new", new))
        self.assertIsNone(stop(root, "old", old))

    def test_session_start_tells_another_session_to_keep_off(self):
        root = make_project()
        stop(root, "pilot", transcript(root, "pilot", [typed("2026-10-11T07:48:00Z")]))
        out = run(SESSION, "start", root, "user", transcript(root, "user", []), "SessionStart")
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Autopilot is ON in another session", ctx)


class Locks(unittest.TestCase):
    def locks(self, root, value=None):
        path = os.path.join(root, ".kiln", "locks.json")
        if value is not None:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(value, fh)
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def held(self):
        return {"blender": {"owner": "main", "role": "main session", "session": "pilot", "ts": 1},
                "godot": {"owner": "main", "role": "main session", "session": "user", "ts": 1}}

    def test_stop_releases_only_this_sessions_main_lock(self):
        root = make_project()
        self.locks(root, self.held())
        stop(root, "user", transcript(root, "user", []))
        self.assertEqual(list(self.locks(root)), ["blender"])

    def test_session_end_keeps_another_sessions_locks(self):
        root = make_project()
        self.locks(root, self.held())
        run(SESSION, "end", root, "user", transcript(root, "user", []), "SessionEnd")
        self.assertEqual(list(self.locks(root)), ["blender"])


class StopAfterTask(unittest.TestCase):
    def project_with(self, backlog):
        root = make_project()
        with open(os.path.join(root, "backlog.md"), "w", encoding="utf-8") as fh:
            fh.write(backlog)
        with open(os.path.join(root, ".kiln", "stop-after-task"), "w", encoding="utf-8") as fh:
            fh.write("usage limit\n")
        return root

    def test_finishes_the_task_in_progress(self):
        root = self.project_with("- [~] TASK-001 helmet\n- [ ] TASK-002 kit\n")
        res = stop(root, "pilot", transcript(root, "pilot", [typed("2026-10-11T07:48:00Z")]))
        self.assertEqual(res["decision"], "block")
        self.assertIn("Stop requested", res["reason"])
        self.assertIn("TASK-001", res["reason"])

    def test_task_1_in_progress_is_not_task_12(self):
        # Review 2026-10-14: ids matched by substring, so TASK-1 pulled in TASK-12's items.
        root = self.project_with("- [~] TASK-1 crate\n- [ ] TASK-12 door\n")
        os.remove(os.path.join(root, "tasks", "TASK-001.md"))
        with open(os.path.join(root, "tasks", "TASK-12-door.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-12: door\n\n- [ ] hinge\n")
        with open(os.path.join(root, "tasks", "TASK-1.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-1: crate\n\n- [x] model\n")
        self.assertIsNone(stop(root, "pilot",
                               transcript(root, "pilot", [typed("2026-10-11T07:48:00Z")])))

    def test_a_blocked_task_and_no_progress_end_the_stop(self):
        # KILN-REV-10 (review 2026-10-21): the stop-after-task branch demanded completion before
        # looking at BLOCKED or counting nudges, so a blocked task was pushed on forever
        root = self.project_with("- [~] TASK-001 helmet\n- [ ] TASK-002 kit\n")
        path = transcript(root, "pilot", [typed("2026-10-11T07:48:00Z")])
        with open(os.path.join(root, "tasks", "TASK-001.md"), "a", encoding="utf-8") as fh:
            fh.write("status: BLOCKED\nwhy: the helmet scan is missing\n")
        for _ in range(3):
            self.assertIsNone(stop(root, "pilot", path))
        with open(os.path.join(root, "tasks", "TASK-001.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-001: helmet\n\n- [x] model\n- [ ] verifier re-check\n")
        results = [stop(root, "pilot", path) for _ in range(6)]       # nothing ever changes
        self.assertEqual(results[0]["decision"], "block")
        self.assertIsNone(results[-1], results)                       # bounded, as autopilot nudges
        self.assertLessEqual(sum(r is not None for r in results), 3, results)

    def test_lets_the_run_end_between_tasks(self):
        # TASK-001 has open items but is not started ([ ]); nothing is in progress
        root = self.project_with("- [ ] TASK-001 helmet\n- [ ] TASK-002 kit\n")
        self.assertIsNone(stop(root, "pilot",
                               transcript(root, "pilot", [typed("2026-10-11T07:48:00Z")])))

def agent_event(script, mode, root, session, agent_id, role, event):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
    payload = {"session_id": session, "cwd": root, "hook_event_name": event,
               "agent_id": agent_id, "agent_type": f"kiln:{role}", "stop_hook_active": False,
               "last_assistant_message": "status: DONE"}
    return subprocess.run([sys.executable, "-B", script, mode], input=json.dumps(payload),
                          env=env, capture_output=True, text=True, timeout=30).stdout


class InFlightAgents(unittest.TestCase):
    # g2 rows 10/125: every open item was being worked by background agents, yet the Stop hook
    # kept pushing the producer to "continue with the open checklist items".
    def test_running_agents_let_the_producer_wait(self):
        root = make_project()
        pilot = transcript(root, "pilot", [typed("2026-10-11T07:48:00Z")])
        agent_event(SESSION, "subagent", root, "pilot", "m1", "modeler", "SubagentStart")
        self.assertIsNone(stop(root, "pilot", pilot))
        agent_event(STOP, "subagent", root, "pilot", "m1", "modeler", "SubagentStop")
        self.assertEqual(stop(root, "pilot", pilot)["decision"], "block")

    def test_parallel_agent_starts_are_all_recorded(self):
        # 0.7.0 review: concurrent hooks read-modify-wrote agents.json; the last writer won.
        root = make_project()
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
        procs = []
        for i in range(20):
            payload = {"session_id": "pilot", "cwd": root, "hook_event_name": "SubagentStart",
                       "agent_id": f"a{i}", "agent_type": "kiln:modeler"}
            p = subprocess.Popen([sys.executable, "-B", SESSION, "subagent"], env=env,
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, text=True)
            p.stdin.write(json.dumps(payload))
            procs.append(p)
        for p in procs:
            p.stdin.close()
        for p in procs:
            p.wait(timeout=60)
        with open(os.path.join(root, ".kiln", "agents.json"), encoding="utf-8") as fh:
            self.assertEqual(len(json.load(fh)), 20)

    def test_guarded_calls_are_the_heartbeat(self):
        root = make_project()
        agent_event(SESSION, "subagent", root, "pilot", "m1", "modeler", "SubagentStart")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
        call = {"session_id": "pilot", "agent_id": "m1", "agent_type": "kiln:modeler",
                "tool_name": "Bash", "tool_input": {"command": "git status"}}
        subprocess.run([sys.executable, "-B", os.path.join(HOOKS, "guard.py")],
                       input=json.dumps(call), env=env, capture_output=True, text=True,
                       timeout=30)
        with open(os.path.join(root, ".kiln", "agents.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["m1"]["last_tool"], "Bash")

    def test_a_stopped_agent_leaves_the_editor_queue(self):
        # Review 2026-10-14: SubagentStop freed the lock but kept the queue entry, so a free
        # editor stayed "asked first" by a finished agent for 5 minutes.
        import time
        root = make_project()
        with open(os.path.join(root, ".kiln", "queue.json"), "w", encoding="utf-8") as fh:
            json.dump({"blender": [{"owner": "a1", "role": "animator", "session": "pilot",
                                    "since": time.time(), "ts": time.time()},
                                   {"owner": "m2", "role": "modeler", "session": "pilot",
                                    "since": time.time(), "ts": time.time()}]}, fh)
        agent_event(STOP, "subagent", root, "pilot", "a1", "animator", "SubagentStop")
        with open(os.path.join(root, ".kiln", "queue.json"), encoding="utf-8") as fh:
            self.assertEqual([w["owner"] for w in json.load(fh)["blender"]], ["m2"])

    def test_another_sessions_agents_do_not_count(self):
        root = make_project()
        pilot = transcript(root, "pilot", [typed("2026-10-11T07:48:00Z")])
        agent_event(SESSION, "subagent", root, "other", "x1", "modeler", "SubagentStart")
        self.assertEqual(stop(root, "pilot", pilot)["decision"], "block")


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=root,
                   capture_output=True, text=True, timeout=30, check=True)


class ClosedTaskUncommitted(unittest.TestCase):
    # g2 row 18: a closed task stayed uncommitted until the user asked.
    def project(self):
        root = tempfile.mkdtemp(prefix="kiln-commit-")
        with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write("project_name=t\nframework=kiln\nengine=godot\n")
        os.makedirs(os.path.join(root, "tasks"))
        with open(os.path.join(root, "tasks", "TASK-002.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-002: dagger\n## spec\nrole: modeler\npaths: art/dagger/, "
                     "assets/dagger.glb\n## checklist\n- [x] model\n")
        with open(os.path.join(root, "backlog.md"), "w", encoding="utf-8") as fh:
            fh.write("- [x] TASK-002 dagger\n")
        git(root, "init", "-q")
        git(root, "add", "manifest.md", "tasks/TASK-002.md", "backlog.md")
        git(root, "commit", "-q", "-m", "init")
        os.makedirs(os.path.join(root, "art", "dagger"))
        with open(os.path.join(root, "art", "dagger", "dagger.py"), "w", encoding="utf-8") as fh:
            fh.write("x = 1\n")
        return root

    def test_blocks_once_until_committed(self):
        root = self.project()
        session = transcript(root, "s", [])
        res = stop(root, "s", session)
        self.assertEqual(res["decision"], "block")
        self.assertIn("TASK-002", res["reason"])
        self.assertIn("art/dagger/dagger.py", res["reason"])
        self.assertIsNone(stop(root, "s", session))       # same state: said once
        git(root, "add", "art/dagger/dagger.py")
        git(root, "commit", "-q", "-m", "TASK-002")
        self.assertIsNone(stop(root, "s", session))

    def test_unrelated_changes_are_not_its_business(self):
        root = self.project()
        os.remove(os.path.join(root, "art", "dagger", "dagger.py"))
        with open(os.path.join(root, "notes.txt"), "w", encoding="utf-8") as fh:
            fh.write("x")
        self.assertIsNone(stop(root, "s", transcript(root, "s", [])))


class ClosedTaskGates(unittest.TestCase):
    # g2 row 46: tasks closed on the builder + one acceptor; nobody checked the gate list.
    def test_a_closed_task_with_open_gates_blocks_once(self):
        root = make_project()
        os.remove(os.path.join(root, ".kiln", "autopilot"))
        with open(os.path.join(root, "tasks", "TASK-020.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-020: merchants\n## spec\ntype: art\nbatch: five human merchants\n"
                     "## gates\n| role | why | verdict |\n|---|---|---|\n"
                     "| anatomy-expert | humanoid | |\n| art-director | refs | APPROVED |\n"
                     "| qa-readability | art | PASS |\n| verifier | close | PASSED |\n")
        with open(os.path.join(root, "backlog.md"), "w", encoding="utf-8") as fh:
            fh.write("- [x] TASK-020 merchants\n")
        session = transcript(root, "s", [])
        res = stop(root, "s", session)
        self.assertEqual(res["decision"], "block")
        self.assertIn("anatomy-expert", res["reason"])
        self.assertIsNone(stop(root, "s", session))


class PhaseGates(unittest.TestCase):
    # Review 2026-10-14: `pipeline.py reopen` appends " REOPENED <date>" to every gate, and the
    # user gates stopped matching "ends with '- user'", so the autopilot was pushed to close them.
    def test_reopened_user_gates_are_still_the_users(self):
        root = make_project()
        with open(os.path.join(root, "tasks", "TASK-001.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-001: helmet\n\n- [x] model\n")
        os.makedirs(os.path.join(root, "production"))
        with open(os.path.join(root, "production", "PIPELINE.md"), "w", encoding="utf-8") as fh:
            fh.write("## Phase 3 look-dev\n- [ ] User approved the look-dev frame \u2014 user "
                     "REOPENED 2026-10-14\n")
        self.assertIsNone(stop(root, "pilot",
                               transcript(root, "pilot", [typed("2026-10-11T07:48:00Z")])))


class Handoff(unittest.TestCase):
    # g2 row 23: SessionEnd replaced the human-written handoff with the auto summary.
    def test_a_written_handoff_is_kept(self):
        root = make_project()
        os.makedirs(os.path.join(root, "memory"))
        handoff = os.path.join(root, "memory", "session-handoff.md")
        with open(handoff, "w", encoding="utf-8") as fh:
            fh.write("# Handoff\nNext: retake the shoulder renders.\n")
        run(SESSION, "end", root, "s", transcript(root, "s", []), "SessionEnd")
        with open(handoff, encoding="utf-8") as fh:
            self.assertIn("retake the shoulder renders", fh.read())
        auto = os.path.join(root, "memory", "session-handoff.auto.md")
        with open(auto, encoding="utf-8") as fh:
            self.assertIn("verifier re-check", fh.read())
        out = run(SESSION, "start", root, "s2", transcript(root, "s2", []), "SessionStart")
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("session-handoff.auto.md", ctx)

    def test_an_auto_handoff_is_refreshed(self):
        root = make_project()
        run(SESSION, "end", root, "s", transcript(root, "s", []), "SessionEnd")
        run(SESSION, "end", root, "s", transcript(root, "s", []), "SessionEnd")
        self.assertFalse(os.path.exists(os.path.join(root, "memory",
                                                     "session-handoff.auto.md")))


if __name__ == "__main__":
    unittest.main()
