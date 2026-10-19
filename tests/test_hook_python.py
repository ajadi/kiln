"""Tests for the hook launchers hooks/py.sh (Claude Code) and hooks/py.cjs (Gemini CLI).

Install audit 2026-10-19: Claude Code and Gemini started every hook as plain `python`; macOS and
many Linux systems have only python3, so every hook failed (a non-blocking error) and nothing was
guarded. The launchers find a working Python 3.10+ and cache it.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "hooks")
BASH = shutil.which("bash")
NODE = shutil.which("node")
ECHO = "import sys; print(sys.argv[1:], sys.stdin.read())"


def fake_bin(names):
    """A folder with sh scripts: name -> body (None = a stub that runs nothing, like the Store
    alias; 'real' = forwards to this Python)."""
    folder = tempfile.mkdtemp(prefix="kiln-bin-")
    for name, kind in names.items():
        body = 'exit 9009' if kind is None else f'exec "{sys.executable}" "$@"'
        path = os.path.join(folder, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("#!/bin/sh\n" + body + "\n")
        os.chmod(path, 0o755)
    return folder


def hook_script():
    folder = tempfile.mkdtemp(prefix="kiln-hk-")
    path = os.path.join(folder, "echo_hook.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(ECHO)
    return path


@unittest.skipUnless(BASH, "bash not installed")
class ShLauncher(unittest.TestCase):
    def run_sh(self, path_dirs, home):
        bash_dir = os.path.dirname(BASH)
        env = dict(os.environ, PATH=os.pathsep.join(path_dirs + [bash_dir]), KILN_HOME=home)
        return subprocess.run([BASH, os.path.join(HOOKS, "py.sh"), hook_script(), "a", "b"],
                              input="payload", capture_output=True, text=True, env=env,
                              timeout=60)

    def test_python3_when_python_is_a_stub(self):
        home = tempfile.mkdtemp(prefix="kiln-home-")
        p = self.run_sh([fake_bin({"python": None, "python3": "real"})], home)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("['a', 'b'] payload", p.stdout)
        with open(os.path.join(home, "hook-python"), encoding="utf-8") as fh:
            self.assertTrue(fh.read().strip().endswith("python3"))

    def test_python_first_when_it_works(self):
        home = tempfile.mkdtemp(prefix="kiln-home-")
        p = self.run_sh([fake_bin({"python": "real", "python3": None})], home)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("payload", p.stdout)

    def test_no_python_says_so(self):
        p = self.run_sh([fake_bin({"python": None})], tempfile.mkdtemp(prefix="kiln-home-"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("no Python 3.10+", p.stderr)


@unittest.skipUnless(NODE, "node not installed")
class NodeLauncher(unittest.TestCase):
    def test_runs_the_hook_with_stdin_and_caches(self):
        home = tempfile.mkdtemp(prefix="kiln-home-")
        env = dict(os.environ, KILN_HOME=home)
        p = subprocess.run([NODE, os.path.join(HOOKS, "py.cjs"), hook_script(), "a", "b"],
                           input="payload", capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("['a', 'b'] payload", p.stdout)
        with open(os.path.join(home, "hook-python.json"), encoding="utf-8") as fh:
            self.assertTrue(os.path.isfile(json.load(fh)["python"]))

    def test_no_python_says_so(self):
        empty = tempfile.mkdtemp(prefix="kiln-empty-")
        env = dict(os.environ, KILN_HOME=tempfile.mkdtemp(prefix="kiln-home-"),
                   PATH=os.path.dirname(NODE) + os.pathsep + empty)
        p = subprocess.run([NODE, os.path.join(HOOKS, "py.cjs"), hook_script()],
                           input="", capture_output=True, text=True, env=env, timeout=60)
        if p.returncode == 0:
            self.skipTest("a python sits next to node on this machine")
        self.assertIn("no Python 3.10+", p.stderr)


class HookFilesUseTheLaunchers(unittest.TestCase):
    def test_claude_code_hooks(self):
        with open(os.path.join(HOOKS, "hooks.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        for event, groups in data["hooks"].items():
            for group in groups:
                for hook in group["hooks"]:
                    self.assertNotIn("args", hook, event)
                    self.assertEqual(hook.get("shell"), "bash", event)
                    self.assertIn('/hooks/py.sh" "${CLAUDE_PLUGIN_ROOT}/hooks/', hook["command"])


if __name__ == "__main__":
    unittest.main()
