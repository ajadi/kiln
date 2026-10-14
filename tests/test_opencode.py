"""Tests for the OpenCode adapter: scripts/opencode_setup.py and its plugin opencode/kiln.js
(node runs the plugin; stdlib only on the Python side).

Shapes recorded live from OpenCode 1.19.0 (opencode run against a local fake OpenAI-compatible
API): tool.execute.before(input {tool, sessionID, callID}, output {args}); bash {command},
write {filePath, content}, edit {filePath, oldString, newString}, task {description, prompt,
subagent_type}; MCP tools <server>_<tool>; a subagent runs in a child session whose
session.created event carries parentID; a plugin denies a call by throwing;
experimental.chat.system.transform pushes text into the system prompt; skills are read from
.opencode/skills (a directory junction to Kiln's skill works).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
PLUGIN = os.path.join(ROOT, "plugins", "kiln")
SETUP = os.path.join(PLUGIN, "scripts", "opencode_setup.py")

HARNESS = r"""
import { pathToFileURL } from "node:url"
const [, , pluginPath, stepsJson] = process.argv
const mod = await import(pathToFileURL(pluginPath).href)
const prompted = []
const client = { session: { prompt: async (req) => { prompted.push(req.body.parts[0].text) } } }
const plugin = await Object.values(mod)[0]({ directory: process.env.PROJ, client })
const out = []
for (const step of JSON.parse(stepsJson)) {
  try {
    if (step.kind === "tool") {
      const output = { args: step.args }
      await plugin["tool.execute.before"]({ tool: step.tool, sessionID: step.sid, callID: "c" }, output)
      out.push({ ok: true, args: output.args })
    } else if (step.kind === "event") {
      await plugin.event({ event: step.event })
      out.push({ ok: true, note: prompted.length ? "prompted: " + prompted[prompted.length - 1] : "" })
    } else if (step.kind === "system") {
      const output = { system: [] }
      await plugin["experimental.chat.system.transform"]({ sessionID: step.sid }, output)
      out.push({ ok: true, system: output.system })
    }
  } catch (e) { out.push({ ok: false, error: String(e.message || e) }) }
}
console.log(JSON.stringify(out))
"""


@unittest.skipUnless(shutil.which("node"), "node not installed")
class OpenCode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proj = tempfile.mkdtemp(prefix="kiln-oc-")
        with open(os.path.join(cls.proj, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write("project_name=o\nframework=kiln\nengine=godot\nruntimes=opencode\n")
        p = subprocess.run([sys.executable, "-B", SETUP, "--project", cls.proj],
                           capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, p.stdout + p.stderr
        cls.report = json.loads(p.stdout)
        cls.harness = os.path.join(cls.proj, "harness.mjs")
        with open(cls.harness, "w", encoding="utf-8") as fh:
            fh.write(HARNESS)

    @classmethod
    def tearDownClass(cls):
        # The skills are links into this Kiln checkout: remove each link itself first, so no
        # later cleanup can follow one into the real skills.
        skills = os.path.join(cls.proj, ".opencode", "skills")
        for name in os.listdir(skills) if os.path.isdir(skills) else []:
            path = os.path.join(skills, name)
            if os.name == "nt":
                subprocess.run(["cmd", "/c", "rmdir", path], capture_output=True)
            elif os.path.islink(path):
                os.remove(path)
        if not os.listdir(skills):
            shutil.rmtree(cls.proj, ignore_errors=True)

    def run_steps(self, steps):
        p = subprocess.run(["node", self.harness,
                            os.path.join(self.proj, ".opencode", "plugins", "kiln.js"),
                            json.dumps(steps)], capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, PROJ=self.proj))
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])

    def test_setup_lays_out_plugin_roles_and_skills(self):
        oc = os.path.join(self.proj, ".opencode")
        self.assertTrue(os.path.isfile(os.path.join(oc, "plugins", "kiln.js")))
        roles = os.listdir(os.path.join(PLUGIN, "agents"))
        self.assertEqual(len(os.listdir(os.path.join(oc, "agents"))), len(roles))
        text = open(os.path.join(oc, "agents", "kiln-art-director.md"), encoding="utf-8").read()
        self.assertIn("mode: subagent", text)
        self.assertTrue(os.path.isfile(os.path.join(oc, "skills", "protocol", "SKILL.md")))
        self.assertEqual(self.report["skills"], len(os.listdir(os.path.join(PLUGIN, "skills"))))

    def test_guard_denies_by_throwing(self):
        res = self.run_steps([
            {"kind": "tool", "tool": "bash", "sid": "ses_main",
             "args": {"command": "git add -A", "description": "stage"}},
            {"kind": "tool", "tool": "bash", "sid": "ses_main",
             "args": {"command": "git status", "description": "status"}},
            {"kind": "tool", "tool": "write", "sid": "ses_main",
             "args": {"filePath": os.path.join(self.proj, "level.tscn"), "content": "[gd_scene]"}},
            {"kind": "tool", "tool": "blender_execute_blender_code_for_cli", "sid": "ses_main",
             "args": {"code": "x"}}])
        self.assertFalse(res[0]["ok"])
        self.assertIn("Stage specific files", res[0]["error"])
        self.assertTrue(res[1]["ok"])
        self.assertFalse(res[2]["ok"])
        self.assertFalse(res[3]["ok"])

    def test_a_subagent_is_its_role_in_its_child_session(self):
        game = os.path.join(self.proj, "GAME.md")
        res = self.run_steps([
            {"kind": "tool", "tool": "write", "sid": "ses_main", "args": {"filePath": game, "content": "x"}},
            {"kind": "tool", "tool": "task", "sid": "ses_main",
             "args": {"description": "art", "prompt": "Review TASK-001", "subagent_type": "kiln-art-director"}},
            {"kind": "event", "event": {"type": "session.created", "properties": {
                "sessionID": "ses_child", "info": {"id": "ses_child", "parentID": "ses_main"}}}},
            {"kind": "tool", "tool": "write", "sid": "ses_child", "args": {"filePath": game, "content": "x"}},
            {"kind": "tool", "tool": "write", "sid": "ses_main", "args": {"filePath": game, "content": "x"}}])
        self.assertTrue(res[0]["ok"], res[0])                       # the producer may
        self.assertIn("Kiln project", res[1]["args"]["prompt"])     # the role gets the profile
        self.assertTrue(res[1]["args"]["prompt"].endswith("Review TASK-001"))
        self.assertFalse(res[3]["ok"])
        self.assertIn("art-director may not write GAME.md", res[3]["error"])
        self.assertTrue(res[4]["ok"], res[4])

    def test_autopilot_continues_a_turn_without_tool_calls(self):
        # live run: the producer answered with text only, so no tool call named the main session
        # and session.idle never reached the stop hook; session.created (no parentID) names it
        os.makedirs(os.path.join(self.proj, "tasks"), exist_ok=True)
        with open(os.path.join(self.proj, "tasks", "TASK-001.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-001: helmet\n\n- [ ] model\n")
        os.makedirs(os.path.join(self.proj, ".kiln"), exist_ok=True)
        with open(os.path.join(self.proj, ".kiln", "autopilot"), "w", encoding="utf-8") as fh:
            fh.write("scope: demo\n")
        try:
            res = self.run_steps([
                {"kind": "event", "event": {"type": "session.created", "properties": {
                    "sessionID": "ses_m2", "info": {"id": "ses_m2"}}}},
                {"kind": "event", "event": {"type": "session.idle",
                                            "properties": {"sessionID": "ses_m2"}}}])
            self.assertIn("prompted:", res[-1].get("note", ""))
            self.assertIn("TASK-001", res[-1]["note"])
        finally:
            os.remove(os.path.join(self.proj, ".kiln", "autopilot"))

    def test_the_session_context_goes_into_the_system_prompt(self):
        res = self.run_steps([{"kind": "system", "sid": "ses_main"}])
        system = "\n".join(res[0]["system"])
        self.assertIn("Kiln project 'o'", system)
        self.assertIn(".opencode/skills/<name>", system)   # where Kiln's skill paths point


if __name__ == "__main__":
    unittest.main()
