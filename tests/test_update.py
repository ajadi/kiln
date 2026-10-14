"""Tests for plugins/kiln/skills/update/scripts/kiln_update.py (stdlib only).

0.7.0 review: a same-version plugin update does not refresh the cache, and a project planned by an
older Kiln needed `migrate` by hand; nothing told the user what changed since their version.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
PLUGIN = os.path.join(HERE, "..", "plugins", "kiln")
SCRIPT = os.path.join(PLUGIN, "skills", "update", "scripts", "kiln_update.py")


def run(root, *args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=root, capture_output=True,
                       text=True, timeout=60)
    return p.returncode, json.loads(p.stdout)


def plugin_version():
    with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        return json.load(fh)["version"]


class Update(unittest.TestCase):
    def project(self, version):
        root = tempfile.mkdtemp(prefix="kiln-upd-")
        with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write(f"project_name=t\nframework=kiln\nframework_version={version}\nengine=godot\n")
        os.makedirs(os.path.join(root, "tasks"))
        with open(os.path.join(root, "tasks", "TASK-001.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-001: merchant\n## spec\ntype: art\nbatch: one human merchant\n")
        return root

    def test_status_lists_what_changed_since_the_project_version(self):
        root = self.project("0.6.0")
        code, res = run(root, "status")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["project_version"], "0.6.0")
        self.assertEqual(res["plugin_version"], plugin_version())
        self.assertTrue(res["behind"])
        versions = [c["version"] for c in res["changes"]]
        self.assertIn(plugin_version(), versions)
        self.assertNotIn("0.6.0", versions)
        self.assertIn("migrate", " ".join(res["next"]))

    def test_apply_migrates_and_records_the_version(self):
        root = self.project("0.6.0")
        code, res = run(root, "apply")
        self.assertEqual(code, 0, res)
        with open(os.path.join(root, "manifest.md"), encoding="utf-8") as fh:
            self.assertIn(f"framework_version={plugin_version()}", fh.read())
        with open(os.path.join(root, "tasks", "TASK-001.md"), encoding="utf-8") as fh:
            self.assertIn("touches: humanoid", fh.read())
        code, res = run(root, "status")
        self.assertFalse(res["behind"])

    def test_session_start_says_to_update(self):
        root = self.project("0.6.0")
        session = os.path.join(PLUGIN, "hooks", "session.py")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
        p = subprocess.run([sys.executable, "-B", session, "start"], env=env,
                           input=json.dumps({"session_id": "s", "source": "startup"}),
                           capture_output=True, text=True, timeout=30)
        ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("run /kiln:update", ctx)
        run(root, "apply")
        p = subprocess.run([sys.executable, "-B", session, "start"], env=env,
                           input=json.dumps({"session_id": "s", "source": "startup"}),
                           capture_output=True, text=True, timeout=30)
        self.assertNotIn("/kiln:update", json.loads(p.stdout)["hookSpecificOutput"]
                         ["additionalContext"])

    def test_not_a_kiln_project(self):
        root = tempfile.mkdtemp(prefix="kiln-upd-")
        code, res = run(root, "status")
        self.assertEqual(code, 1)
        self.assertIn("manifest", res["problems"][0])


if __name__ == "__main__":
    unittest.main()
