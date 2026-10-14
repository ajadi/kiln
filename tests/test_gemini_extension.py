"""Tests for scripts/gemini_extension.py: Kiln built as a Gemini CLI extension (stdlib only).

Layout from gemini-cli v0.64.0 (packages/cli/src/config/extension-manager.ts): gemini-extension.json
at the root, skills/<name>/SKILL.md, agents/*.md (frontmatter schema is strict:
packages/core/src/agents/agentLoader.ts), commands/**/*.toml, hooks/hooks.json. ${extensionPath}
and ${/} are expanded in hooks.json and in extension skills and agents.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
PLUGIN = os.path.join(ROOT, "plugins", "kiln")
SCRIPT = os.path.join(PLUGIN, "scripts", "gemini_extension.py")
AGENT_KEYS = {"name", "description", "kind", "display_name", "tools", "mcp_servers", "model",
              "temperature", "max_turns", "timeout_mins"}


def frontmatter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return m.group(1), text[m.end():]


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = os.path.join(tempfile.mkdtemp(prefix="kiln-gext-"), "kiln")
        p = subprocess.run([sys.executable, "-B", SCRIPT, "--out", cls.out], capture_output=True,
                           text=True, timeout=120)
        assert p.returncode == 0, p.stdout + p.stderr
        cls.report = json.loads(p.stdout)

    def test_manifest(self):
        with open(os.path.join(self.out, "gemini-extension.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            version = json.load(fh)["version"]
        self.assertEqual((manifest["name"], manifest["version"]), ("kiln", version))
        self.assertTrue(os.path.isfile(os.path.join(self.out, manifest["contextFileName"])))

    def test_every_role_is_a_gemini_agent_with_only_allowed_keys(self):
        roles = glob.glob(os.path.join(PLUGIN, "agents", "*.md"))
        agents = glob.glob(os.path.join(self.out, "agents", "*.md"))
        self.assertEqual(len(agents), len(roles))
        for path in agents:
            head, body = frontmatter(path)
            keys = {line.split(":", 1)[0] for line in head.splitlines()
                    if re.match(r"^[a-z_]+:", line)}
            self.assertLessEqual(keys, AGENT_KEYS, path)
            self.assertTrue(re.search(r"^name: kiln-[a-z0-9-]+$", head, re.M), path)
            self.assertIn("activate_skill", body)
        for path in roles:                           # a role writes in Gemini iff it does in Claude
            claude, _ = frontmatter(path)
            role = os.path.basename(path)[:-3]
            head, _ = frontmatter(os.path.join(self.out, "agents", f"kiln-{role}.md"))
            tools = re.search(r"^tools:\s*(.*)$", claude, re.M)
            if tools:
                writes = bool(re.search(r"\bWrite\b", tools.group(1)))
                self.assertEqual("write_file" in head, writes, role)
        head, _ = frontmatter(os.path.join(self.out, "agents", "kiln-modeler.md"))
        self.assertIn('"mcp_blender_*"', head)

    def test_commands_for_every_user_command(self):
        commands = glob.glob(os.path.join(PLUGIN, "skills", "*", "SKILL.md"))
        user = [os.path.basename(os.path.dirname(p)) for p in commands
                if not re.search(r"^user-invocable:\s*false", open(p, encoding="utf-8").read(), re.M)]
        for name in user:
            with open(os.path.join(self.out, "commands", "kiln", name + ".toml"), "rb") as fh:
                cmd = tomllib.load(fh)
            self.assertIn(f"`{name}`", cmd["prompt"])
            self.assertIn("{{args}}", cmd["prompt"])

    def test_hooks_cover_the_events_kiln_needs(self):
        with open(os.path.join(self.out, "hooks", "hooks.json"), encoding="utf-8") as fh:
            hooks = json.load(fh)["hooks"]
        self.assertEqual(set(hooks), {"BeforeTool", "AfterTool", "SessionStart", "SessionEnd",
                                      "AfterAgent"})
        for entries in hooks.values():
            for entry in entries:
                if entry.get("matcher"):
                    self.assertTrue(entry["matcher"].startswith("^"), entry)  # regexes are unanchored
                for h in entry["hooks"]:
                    self.assertIn("--runtime gemini", h["command"])
                    self.assertIn("${extensionPath}", h["command"])

    def test_skills_use_gemini_variables(self):
        for path in glob.glob(os.path.join(self.out, "skills", "*", "SKILL.md")):
            text = open(path, encoding="utf-8").read()
            self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", text, path)
            self.assertNotIn("${CLAUDE_SKILL_DIR}", text, path)

    @unittest.skipUnless(shutil.which("gemini"), "gemini-cli not installed")
    def test_the_real_gemini_cli_accepts_it(self):
        home = tempfile.mkdtemp(prefix="kiln-gemhome-")
        env = dict(os.environ, HOME=home, USERPROFILE=home, GEMINI_CLI_TRUST_WORKSPACE="true")
        p = subprocess.run(["gemini", "extensions", "validate", self.out], env=env,
                           capture_output=True, text=True, timeout=120, shell=os.name == "nt")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
