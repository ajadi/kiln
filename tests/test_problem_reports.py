"""Tests for problem_reports: Kiln writes its own problems into kiln-report.md (stdlib only).

User (2026-10-14): the reports stay for good, also while developing Kiln, and are optional in
/kiln:settings. The rule tells agents to write rows; with problem_reports=on (default) a crashed
hook writes its row by code; off switches both off.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "hooks")


def project(extra=""):
    root = tempfile.mkdtemp(prefix="kiln-rep-")
    with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write(f"project_name=r\nframework=kiln\nengine=godot\n{extra}")
    return root


def crash(root):
    """A payload the guard cannot read (tool_input is not an object)."""
    p = subprocess.run([sys.executable, "-B", os.path.join(HOOKS, "guard.py")],
                       input=json.dumps({"tool_name": "Write", "tool_input": "oops"}),
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=root), capture_output=True,
                       text=True, timeout=30)
    return p.returncode


def report(root):
    try:
        with open(os.path.join(root, "kiln-report.md"), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def start(root):
    p = subprocess.run([sys.executable, "-B", os.path.join(HOOKS, "session.py"), "start"],
                       input=json.dumps({"session_id": "s", "source": "startup"}),
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=root), capture_output=True,
                       text=True, timeout=30)
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


class ProblemReports(unittest.TestCase):
    def test_a_crashed_hook_writes_its_own_row_once(self):
        root = project()
        self.assertEqual(crash(root), 0)                 # fail open: the action is not blocked
        text = report(root)
        self.assertIn("| 1 |", text)
        self.assertIn("| hook | hooks | guard.py crashed: AttributeError", text)
        self.assertIn(".kiln/hooks.log", text)
        crash(root)
        self.assertNotIn("| 2 |", report(root))           # the same crash is not repeated

    def test_off_writes_nothing_and_tells_the_agents(self):
        root = project("problem_reports=off\n")
        crash(root)
        self.assertEqual(report(root), "")
        self.assertIn("problem_reports=off", start(root))
        self.assertNotIn("problem_reports=off", start(project()))


if __name__ == "__main__":
    unittest.main()
