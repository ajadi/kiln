"""Tests for the project templates setup copies (stdlib only)."""

import json
import os
import unittest

TEMPLATES = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "templates", "project")


class ProjectTemplates(unittest.TestCase):
    def test_settings_turn_overlapping_skill_packs_off(self):
        with open(os.path.join(TEMPLATES, ".claude", "settings.json"), encoding="utf-8") as fh:
            settings = json.load(fh)
        self.assertIs(settings["enabledPlugins"]["mattpocock-skills@claude-plugins-official"], False)
        self.assertIn("mcp__blender", settings["permissions"]["allow"])

    def test_manifest_defaults(self):
        with open(os.path.join(TEMPLATES, "manifest.md"), encoding="utf-8") as fh:
            lines = dict(line.strip().split("=", 1) for line in fh if "=" in line)
        self.assertEqual(lines["kind"], "game")
        self.assertEqual(lines["user_gates"], "proxy")
        self.assertEqual(lines["mcp_only"], "on")


if __name__ == "__main__":
    unittest.main()
