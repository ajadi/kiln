"""Tests for scripts/text_block.py: Kiln's additions to a project's own text files.

Install audit 2026-10-19: setup appended gitignore.tmpl to a .gitignore without a final newline
(`.env# --- kiln ---`: the user's last pattern stopped working), and "CLAUDE.md / GEMINI.md
contain only @AGENTS.md" dropped what the user had written there.
"""

import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "scripts", "text_block.py")


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=30)
    return p.returncode, p.stdout + p.stderr


class TextBlock(unittest.TestCase):
    def tmp(self, name, text=None, raw=False):
        path = os.path.join(tempfile.mkdtemp(prefix="kiln-tb-"), name)
        if text is not None:
            with open(path, "wb" if raw else "w", **({} if raw else {"encoding": "utf-8", "newline": ""})) as fh:
                fh.write(text)
        return path

    def read(self, path):
        with open(path, encoding="utf-8", newline="") as fh:
            return fh.read()

    def test_block_after_a_line_without_newline(self):
        src = self.tmp("gitignore.tmpl", "# --- kiln ---\n.kiln/\n")
        path = self.tmp(".gitignore", "node_modules/\n*.keystore")
        code, out = run("block", "--file", path, "--source", src, "--marker", "kiln")
        self.assertEqual(code, 0, out)
        lines = self.read(path).splitlines()
        self.assertIn("*.keystore", lines)               # the user's last pattern is intact
        self.assertIn(".kiln/", lines)
        self.assertTrue(self.read(path).endswith("\n"))

    def test_block_is_replaced_not_doubled_and_crlf_kept(self):
        src = self.tmp("t", "# --- kiln ---\n.kiln/\n")
        path = self.tmp(".gitignore", "a/\r\nb/\r\n")
        run("block", "--file", path, "--source", src, "--marker", "kiln")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("# --- kiln ---\n.kiln/\nexport/\n")
        run("block", "--file", path, "--source", src, "--marker", "kiln")
        text = self.read(path)
        self.assertEqual(text.count(".kiln/"), 1)
        self.assertIn("export/", text)
        self.assertNotIn("\n", text.replace("\r\n", ""))  # every line ends in CRLF, as before

    def test_include_keeps_the_users_text(self):
        path = self.tmp("CLAUDE.md", "# My notes\nUse tabs.\n")
        code, out = run("include", "--file", path, "--line", "@AGENTS.md")
        self.assertEqual(code, 0, out)
        text = self.read(path)
        self.assertTrue(text.startswith("@AGENTS.md\n"))
        self.assertIn("Use tabs.", text)
        run("include", "--file", path, "--line", "@AGENTS.md")
        self.assertEqual(self.read(path).count("@AGENTS.md"), 1)

    def test_include_creates_a_missing_file(self):
        path = self.tmp("GEMINI.md")
        self.assertEqual(run("include", "--file", path, "--line", "@AGENTS.md")[0], 0)
        self.assertEqual(self.read(path), "@AGENTS.md\n")

    def test_a_bom_is_kept_out_of_the_middle(self):
        path = self.tmp(".gitattributes", b"\xef\xbb\xbf*.psd binary", raw=True)
        run("include", "--file", path, "--line", "* text=auto eol=lf")
        with open(path, "rb") as fh:
            raw = fh.read()
        self.assertEqual(raw.count(b"\xef\xbb\xbf"), 0)
        self.assertEqual(raw.decode().splitlines(), ["* text=auto eol=lf", "*.psd binary"])


if __name__ == "__main__":
    unittest.main()
