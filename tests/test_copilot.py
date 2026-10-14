"""Tests for the GitHub Copilot CLI runtime of Kiln's hooks (--runtime copilot), stdlib only.

Payload shapes recorded live from Copilot CLI 1.0.97 (BYOK against a local fake model API,
COPILOT_OFFLINE): camelCase events, toolName + toolArgs (an object), Windows shell tool
`powershell`, create {path, file_text}, edit {path, old_str, new_str}, task {agent_type, prompt,
name, description}. A subagent's tool calls carry their own sessionId, which subagentStop
reports as agentId; subagentStart (in the parent session) names the role in agentName.
Output: preToolUse {permissionDecision, permissionDecisionReason, modifiedArgs};
sessionStart / subagentStart {additionalContext}; agentStop / subagentStop {decision, reason}.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "hooks")
MAIN = "8468a9eb-main"
SUB = "c5c63c4e-sub"


def project(extra=""):
    root = tempfile.mkdtemp(prefix="kiln-cop-")
    with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write(f"project_name=c\nframework=kiln\nengine=godot\n{extra}")
    return root


def hook(root, script, *args, **payload):
    data = dict({"timestamp": 1791990657558, "cwd": root}, **payload)
    env = dict(os.environ, PLUGIN_ROOT=os.path.dirname(HOOKS), CLAUDE_PROJECT_DIR=root)
    p = subprocess.run([sys.executable, "-B", os.path.join(HOOKS, script), *args,
                        "--runtime", "copilot"], input=json.dumps(data), env=env,
                       capture_output=True, text=True, timeout=30)
    return json.loads(p.stdout) if p.stdout.strip() else None


def tool(root, name, args, session=MAIN):
    return hook(root, "guard.py", sessionId=session, toolName=name, toolArgs=args)


class Guard(unittest.TestCase):
    def setUp(self):
        self.root = project()
        hook(self.root, "session.py", "start", sessionId=MAIN, source="new", initialPrompt="x")

    def test_denials_use_copilot_s_shape(self):
        res = tool(self.root, "powershell", {"command": "git add -A", "description": "stage"})
        self.assertEqual(res["permissionDecision"], "deny")
        self.assertIn("Stage specific files", res["permissionDecisionReason"])
        self.assertIsNone(tool(self.root, "bash", {"command": "git status", "description": "s"}))

    def test_file_tools_mcp_names_and_string_args(self):
        scene = os.path.join(self.root, "level.tscn")
        self.assertEqual(tool(self.root, "create", {"path": scene, "file_text": "[gd_scene]"})
                         ["permissionDecision"], "deny")
        self.assertEqual(tool(self.root, "edit", json.dumps(
            {"path": scene, "old_str": "a", "new_str": "b"}))["permissionDecision"], "deny")
        self.assertEqual(tool(self.root, "blender-execute_blender_code_for_cli", {"code": "x"})
                         ["permissionDecision"], "deny")

    def test_a_subagent_is_its_role_by_its_own_session(self):
        game = os.path.join(self.root, "GAME.md")
        self.assertIsNone(tool(self.root, "create", {"path": game, "file_text": "x"}))  # main
        ctx = hook(self.root, "session.py", "subagent", sessionId=MAIN,
                   agentName="kiln:art-director", agentDisplayName="art-director")
        self.assertIn("Kiln project", ctx["additionalContext"])
        res = tool(self.root, "create", {"path": game, "file_text": "x"}, session=SUB)
        self.assertEqual(res["permissionDecision"], "deny")
        self.assertIn("art-director may not write GAME.md", res["permissionDecisionReason"])
        self.assertIsNone(tool(self.root, "create", {"path": game, "file_text": "x"}))  # main
        hook(self.root, "stop.py", "subagent", sessionId=MAIN, agentId=SUB,
             agentType="kiln:art-director", agentName="kiln:art-director",
             response="status: DONE", stop_hook_active=False)
        self.assertIsNone(tool(self.root, "create", {"path": game, "file_text": "x"}, session=SUB))


class Agents(unittest.TestCase):
    # Recorded live (Copilot CLI 1.0.97): an agent's Claude tool names Bash and mcp__<server>
    # gave no shell and no MCP tools; `shell` gives powershell/bash, `<server>/*` gives the
    # server's tools, `read` gives view; grep and glob must be named.
    def test_generated_agents_are_current_and_use_copilot_tool_names(self):
        import glob as g
        plugin = os.path.dirname(HOOKS)
        p = subprocess.run([sys.executable, "-B", os.path.join(plugin, "scripts", "copilot_agents.py"),
                            "--check"], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        roles = g.glob(os.path.join(plugin, "agents", "*.md"))
        made = g.glob(os.path.join(plugin, "copilot", "agents", "*.md"))
        self.assertEqual(len(made), len(roles))
        text = open(os.path.join(plugin, "copilot", "agents", "art-director.md"), encoding="utf-8").read()
        head = text.split("---")[1]
        for name in ("shell", "grep", "glob", "view", "skill", "blender/execute_blender_code"):
            self.assertIn(name, head)
        self.assertNotIn("mcp__", head)
        self.assertNotIn("Bash", head)
        manifest = json.load(open(os.path.join(plugin, ".github", "plugin", "plugin.json"), encoding="utf-8"))
        self.assertEqual(manifest["agents"], "copilot/agents/")


class Stop(unittest.TestCase):
    def test_autopilot_continues_the_main_agent_only(self):
        root = project()
        hook(root, "session.py", "start", sessionId=MAIN, source="new")
        os.makedirs(os.path.join(root, "tasks"))
        with open(os.path.join(root, "tasks", "TASK-001.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-001: helmet\n\n- [ ] model\n")
        with open(os.path.join(root, ".kiln", "autopilot"), "w", encoding="utf-8") as fh:
            fh.write("scope: demo\n")
        res = hook(root, "stop.py", "stop", sessionId=MAIN, stopReason="end_turn",
                   stop_hook_active=False)
        self.assertEqual(res["decision"], "block")
        self.assertIn("TASK-001", res["reason"])
        # agentStop also fires for a subagent's own session: not the producer's turn
        self.assertIsNone(hook(root, "stop.py", "stop", sessionId=SUB, stopReason="end_turn",
                               stop_hook_active=False))


if __name__ == "__main__":
    unittest.main()
