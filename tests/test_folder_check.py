"""Tests for scripts/folder_check.py and its copy in kiln-start (install audit 2026-10-19: nothing
stopped setup in the home folder or a drive root)."""

import filecmp
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "plugins")
SCRIPT = os.path.join(ROOT, "kiln", "scripts", "folder_check.py")
COPY = os.path.join(ROOT, "kiln-start", "skills", "here", "scripts", "folder_check.py")


def check(folder):
    return subprocess.run([sys.executable, "-B", SCRIPT, folder], capture_output=True, text=True,
                          timeout=30)


class FolderCheck(unittest.TestCase):
    def test_refused(self):
        home = os.path.expanduser("~")
        for folder in (home, os.path.dirname(home), os.path.abspath(os.sep)):
            p = check(folder)
            self.assertEqual(p.returncode, 1, folder)
            self.assertIn("Not a project folder", p.stdout)

    def test_a_project_folder_is_fine(self):
        self.assertEqual(check(tempfile.mkdtemp(prefix="kiln-fc-")).returncode, 0)
        self.assertEqual(check(os.path.join(os.path.expanduser("~"), "games", "g1")).returncode, 0)

    def test_kiln_start_carries_the_same_script(self):
        self.assertTrue(filecmp.cmp(SCRIPT, COPY, shallow=False))


if __name__ == "__main__":
    unittest.main()
