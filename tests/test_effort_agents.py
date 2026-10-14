"""Tests for plugins/kiln/scripts/effort_agents.py (stdlib only)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "scripts",
                      "effort_agents.py")


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=60, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


class EffortAgents(unittest.TestCase):
    def project(self):
        root = tempfile.mkdtemp(prefix="kiln-effort-")
        os.makedirs(os.path.join(root, "tasks"))
        with open(os.path.join(root, "tasks", "TASK-019.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-019\n\n## spec\ntype: art\nrole: modeler\neffort: medium\n")
        return root

    def test_copy_has_new_name_effort_and_namespaced_skills(self):
        root = self.project()
        code, res = run("--project", root, "--from-tasks")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["delegate_as"], ["modeler-medium"])
        text = open(os.path.join(root, ".claude", "agents", "modeler-medium.md"),
                    encoding="utf-8").read()
        self.assertIn("name: modeler-medium", text)
        self.assertIn("effort: medium", text)
        self.assertNotIn("effort: high", text)
        self.assertIn("  - kiln:protocol", text)
        self.assertIn("  - kiln:blender-modeling", text)

    def test_role_with_the_kiln_prefix(self):
        # Review 2026-10-14: "role: kiln:animator" (the hooks accept the prefix) aborted the run.
        root = self.project()
        with open(os.path.join(root, "tasks", "TASK-020.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-020\n\n## spec\ntype: animation\nrole: kiln:animator\neffort: high\n")
        code, res = run("--project", root, "--from-tasks")
        self.assertEqual(code, 0, res)
        self.assertEqual(sorted(res["delegate_as"]), ["animator-high", "modeler-medium"])

    def test_clean_removes_only_generated_copies(self):
        root = self.project()
        run("--project", root, "--role", "animator", "--effort", "low")
        mine = os.path.join(root, ".claude", "agents", "custom.md")
        with open(mine, "w", encoding="utf-8") as fh:
            fh.write("---\nname: custom\n---\nhand-made\n")
        code, res = run("--project", root, "--clean")
        self.assertEqual(res["removed"], ["animator-low.md"])
        self.assertTrue(os.path.exists(mine))

    def test_unknown_role_and_effort_are_errors(self):
        root = self.project()
        self.assertEqual(run("--project", root, "--role", "wizard", "--effort", "low")[0], 2)
        self.assertEqual(run("--project", root, "--role", "modeler", "--effort", "huge")[0], 2)


if __name__ == "__main__":
    unittest.main()
