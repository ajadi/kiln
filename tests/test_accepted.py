"""Tests for plugins/kiln/skills/acceptance/scripts/accepted.py (stdlib only).

g2 row 72: acceptor probes are untracked until the task closes, so "git diff shows no weakened
probe_qa_* row" had nothing to diff against. Row 92: the level scene was replaced during a
re-acceptance and a row silently stopped testing what it guarded.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "acceptance",
                      "scripts", "accepted.py")


def run(root, *args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=root, capture_output=True,
                       text=True, timeout=30)
    return p.returncode, json.loads(p.stdout)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class Accepted(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-acc-")
        write(self.root, "tests/probes/probe_qa_cam.gd",
              'check("CAM-1", a, "<", 1)\ncheck("CAM-2", b, ">=", 2)\n')
        write(self.root, "tests/probes/probe_dev.gd", 'check("DEV-1", c, "==", 1)\n')
        write(self.root, "scenes/plaza.tscn", "[gd_scene]\n")

    def test_unchanged_round_passes(self):
        code, res = run(self.root, "snapshot", "--scenes", "scenes/plaza.tscn")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["probes"]["tests/probes/probe_qa_cam.gd"]["rows"], 2)
        self.assertNotIn("tests/probes/probe_dev.gd", res["probes"])
        code, res = run(self.root, "check")
        self.assertEqual(code, 0, res)

    def test_edited_probe_and_replaced_scene_are_named(self):
        run(self.root, "snapshot", "--scenes", "scenes/plaza.tscn")
        write(self.root, "tests/probes/probe_qa_cam.gd", 'check("CAM-1", a, "<", 9)\n')
        write(self.root, "scenes/plaza.tscn", "[gd_scene]\n[node name=\"Fountain\"]\n")
        write(self.root, "tests/probes/probe_qa_new.gd", 'check("N-1", x, ">", 0)\n')
        code, res = run(self.root, "check")
        self.assertEqual(code, 1, res)
        changed = {c["path"]: c for c in res["changed"]}
        self.assertEqual(changed["tests/probes/probe_qa_cam.gd"]["rows"], [2, 1])
        self.assertIn("scenes/plaza.tscn", changed)
        self.assertEqual(res["added"], ["tests/probes/probe_qa_new.gd"])


if __name__ == "__main__":
    unittest.main()
