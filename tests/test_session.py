"""Tests for plugins/kiln/hooks/session.py start context (stdlib only)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SESSION = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "hooks", "session.py")


def make_project(extra=""):
    root = tempfile.mkdtemp(prefix="kiln-session-")
    with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write(f"project_name=t\nframework=kiln\nengine=godot\n{extra}")
    return root


def context(root):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
    out = subprocess.run([sys.executable, "-B", SESSION, "start"], input=json.dumps(
        {"session_id": "s", "cwd": root, "hook_event_name": "SessionStart", "source": "startup"}),
        env=env, capture_output=True, text=True, timeout=30).stdout
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


class ProjectKind(unittest.TestCase):
    def test_prototype_is_announced(self):
        ctx = context(make_project("kind=prototype\n"))
        self.assertIn("Project kind: PROTOTYPE", ctx)
        self.assertIn("Never change kind yourself", ctx)

    def test_game_is_the_default_and_silent(self):
        for extra in ("", "kind=game\n"):
            self.assertNotIn("PROTOTYPE", context(make_project(extra)))


class UserGates(unittest.TestCase):
    def test_proxy_is_the_default_and_ask_is_shown(self):
        self.assertIn("user_gates=proxy", context(make_project()))
        self.assertIn("user_gates=ask", context(make_project("user_gates=ask\n")))


if __name__ == "__main__":
    unittest.main()
