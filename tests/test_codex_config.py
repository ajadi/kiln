"""Tests for scripts/codex_config.py: Kiln's on/off switch in a Codex config.toml (stdlib only).

Field report 2026-10-19: an agent following the install text appended
`[plugins."kiln@kiln"]` / `enabled = false` without a final newline; the next block Codex wrote
was glued to it (`enabled = false[features]`) and the Codex app would not start.
"""

import os
import subprocess
import sys
import tempfile
import tomllib
import unittest

HERE = os.path.dirname(__file__)
SCRIPT = os.path.join(HERE, "..", "plugins", "kiln", "scripts", "codex_config.py")


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=30)
    return p.returncode, p.stdout + p.stderr


class CodexConfig(unittest.TestCase):
    def file(self, text):
        path = os.path.join(tempfile.mkdtemp(prefix="kiln-cc-"), "config.toml")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    def read(self, path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_switch_off_in_a_file_without_a_final_newline(self):
        path = self.file('model = "gpt-6"\n[features]\njs_repl = false')
        code, out = run("--file", path, "--off")
        self.assertEqual(code, 0, out)
        text = self.read(path)
        self.assertTrue(text.endswith("\n"))
        data = tomllib.loads(text)
        self.assertFalse(data["plugins"]["kiln@kiln"]["enabled"])
        self.assertFalse(data["features"]["js_repl"])
        # something appended later still starts on its own line
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("[other]\nx = 1\n")
        tomllib.loads(self.read(path))

    def test_switch_on_an_existing_section_keeps_everything_else(self):
        path = self.file('[plugins."kiln@kiln"]\nenabled = false\n\n[mcp_servers.blender]\ncommand = "b"\n')
        code, out = run("--file", path, "--on")
        self.assertEqual(code, 0, out)
        data = tomllib.loads(self.read(path))
        self.assertTrue(data["plugins"]["kiln@kiln"]["enabled"])
        self.assertEqual(data["mcp_servers"]["blender"]["command"], "b")
        code, out = run("--file", path, "--plugin", "mattpocock-skills@mattpocock", "--off")
        self.assertFalse(tomllib.loads(self.read(path))["plugins"]["mattpocock-skills@mattpocock"]["enabled"])
        code, out = run("--file", path, "--on")              # idempotent
        self.assertEqual(self.read(path).count('[plugins."kiln@kiln"]'), 1)

    def test_a_missing_file_is_created(self):
        path = os.path.join(tempfile.mkdtemp(prefix="kiln-cc-"), ".codex", "config.toml")
        code, out = run("--file", path, "--on")
        self.assertEqual(code, 0, out)
        self.assertTrue(tomllib.loads(self.read(path))["plugins"]["kiln@kiln"]["enabled"])

    def test_a_broken_file_is_not_touched_and_the_line_is_named(self):
        broken = '[plugins."kiln@kiln"]\nenabled = false[features]\njs_repl = false\n'
        path = self.file(broken)
        code, out = run("--file", path, "--off")
        self.assertNotEqual(code, 0)
        self.assertIn("line 2", out)
        self.assertIn("--repair", out)
        self.assertEqual(self.read(path), broken)

    def test_repair_splits_a_value_glued_to_a_table_header(self):
        path = self.file('[plugins."kiln@kiln"]\nenabled = false[features]\njs_repl = false')
        code, out = run("--file", path, "--repair")
        self.assertEqual(code, 0, out)
        data = tomllib.loads(self.read(path))
        self.assertFalse(data["plugins"]["kiln@kiln"]["enabled"])
        self.assertFalse(data["features"]["js_repl"])
        self.assertTrue(os.path.isfile(path + ".kiln-backup"))
        self.assertIn("enabled = false[features]", self.read(path + ".kiln-backup"))

    def test_check_reports_ok_or_the_error(self):
        self.assertEqual(run("--file", self.file('[a]\nb = 1\n'), "--check")[0], 0)
        code, out = run("--file", self.file('b = 1[a]\n'), "--check")
        self.assertNotEqual(code, 0)
        self.assertIn("line 1", out)


if __name__ == "__main__":
    unittest.main()
