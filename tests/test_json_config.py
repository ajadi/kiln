"""Tests for scripts/json_config.py and the BOM / broken-file handling of Kiln's own JSON.

Install audit 2026-10-19: opencode.json, .github/copilot/settings.json, .claude/settings.json,
Unity's Packages/manifest.json and the .uproject were merged by hand with no parse check and no
backup; ~/.kiln/*.json read as {} after any parse error (a BOM included) and the next save kept
one key.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
PLUGIN = os.path.join(HERE, "..", "plugins", "kiln")
SCRIPT = os.path.join(PLUGIN, "scripts", "json_config.py")
sys.path.insert(0, os.path.join(PLUGIN, "hooks"))
import kiln_hooklib as k  # noqa: E402


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=30)
    return p.returncode, p.stdout + p.stderr


class JsonConfig(unittest.TestCase):
    def file(self, name, text=None):
        path = os.path.join(tempfile.mkdtemp(prefix="kiln-jc-"), name)
        if text is not None:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        return path

    def load(self, path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_merge_keeps_everything_else_and_unions_lists(self):
        path = self.file("settings.json", '{"enabledPlugins": {"other@x": true},'
                                          ' "permissions": {"allow": ["Bash(git status)"]}}')
        code, out = run("merge", "--file", path, "--json",
                        '{"enabledPlugins": {"kiln@kiln": true}, "permissions": {"allow": '
                        '["Bash(git status)", "mcp__blender"]}}')
        self.assertEqual(code, 0, out)
        data = self.load(path)
        self.assertEqual(data["enabledPlugins"], {"other@x": True, "kiln@kiln": True})
        self.assertEqual(data["permissions"]["allow"], ["Bash(git status)", "mcp__blender"])
        self.assertTrue(os.path.isfile(path + ".kiln-backup"))

    def test_creates_a_missing_file(self):
        path = os.path.join(tempfile.mkdtemp(prefix="kiln-jc-"), ".github", "copilot", "settings.json")
        self.assertEqual(run("merge", "--file", path, "--json", '{"enabledPlugins": {"kiln@kiln": true}}')[0], 0)
        self.assertEqual(self.load(path), {"enabledPlugins": {"kiln@kiln": True}})

    def test_bom_and_jsonc(self):
        path = self.file("opencode.json", '\ufeff{\n  // my servers\n  "mcp": {"a": {"type": "local"},},\n}\n')
        code, out = run("merge", "--file", path, "--json", '{"mcp": {"godot-ai": {"type": "local"}}}')
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(self.load(path)["mcp"]), ["a", "godot-ai"])
        self.assertIn("comments", out)                    # it says the comments were not kept
        with open(path + ".kiln-backup", encoding="utf-8-sig") as fh:
            self.assertIn("// my servers", fh.read())

    def test_program_lines_are_replaced_and_named_entries_merged(self):
        # bug hunt 2026-10-20: joined lists ran the old program with the new path as an argument
        # and gave a .uproject the same plugin twice
        path = self.file("opencode.json", '{"mcp": {"blender": {"type": "local", "command": '
                                          '["C:/old/blender-mcp.exe"]}}}')
        run("merge", "--file", path, "--json",
            '{"mcp": {"blender": {"command": ["C:/new/blender-mcp.exe"]}}}')
        self.assertEqual(self.load(path)["mcp"]["blender"]["command"], ["C:/new/blender-mcp.exe"])
        path = self.file("Game.uproject", '{"Plugins": [{"Name": "PythonScriptPlugin", '
                                          '"Enabled": false}, {"Name": "Other", "Enabled": true}]}')
        run("merge", "--file", path, "--json",
            '{"Plugins": [{"Name": "PythonScriptPlugin", "Enabled": true}, '
            '{"Name": "ModelContextProtocol", "Enabled": true}]}')
        plugins = self.load(path)["Plugins"]
        self.assertEqual([(p["Name"], p["Enabled"]) for p in plugins],
                         [("PythonScriptPlugin", True), ("Other", True),
                          ("ModelContextProtocol", True)])

    def test_a_utf16_file_is_read(self):
        path = self.file("manifest.json")
        with open(path, "w", encoding="utf-16") as fh:
            fh.write('{"dependencies": {"a": "1"}}')
        self.assertEqual(run("check", "--file", path)[0], 0)
        code, out = run("merge", "--file", path, "--json", '{"dependencies": {"b": "2"}}')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.load(path)["dependencies"], {"a": "1", "b": "2"})

    def test_a_broken_file_is_not_touched(self):
        broken = '{"dependencies": {"a": "1",, }'
        path = self.file("manifest.json", broken)
        code, out = run("merge", "--file", path, "--json", '{"dependencies": {"b": "2"}}')
        self.assertNotEqual(code, 0)
        self.assertIn("line 1", out)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), broken)


class KilnStartCopy(unittest.TestCase):
    def test_kiln_start_carries_the_same_script(self):
        import filecmp
        copy = os.path.join(HERE, "..", "plugins", "kiln-start", "skills", "here", "scripts",
                            "json_config.py")
        self.assertTrue(filecmp.cmp(SCRIPT, copy, shallow=False))


class KilnJson(unittest.TestCase):
    def test_load_json_reads_a_bom_and_keeps_a_broken_file(self):
        folder = tempfile.mkdtemp(prefix="kiln-kj-")
        good = os.path.join(folder, "machine.json")
        with open(good, "w", encoding="utf-8-sig") as fh:
            fh.write('{"tools_root": "D:/t", "update_check": "off"}')
        self.assertEqual(k.load_json(good, {})["update_check"], "off")
        bad = os.path.join(folder, "projects.json")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write('{"D:/a": {"name": "a"},}')
        self.assertEqual(k.load_json(bad, {}), {})
        kept = [n for n in os.listdir(folder) if n.startswith("projects.json.broken")]
        self.assertEqual(len(kept), 1)                    # the next save cannot lose it


if __name__ == "__main__":
    unittest.main()
