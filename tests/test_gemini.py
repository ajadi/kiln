"""Tests for the Gemini CLI runtime of Kiln's hooks (--runtime gemini), stdlib only.

Built from gemini-cli v0.64.0 (docs/hooks/reference.md, packages/core/src/hooks/*): BeforeTool
payloads carry Gemini tool names (run_shell_command, write_file, replace, mcp_<server>_<tool>);
a denial is {"decision": "deny", "reason"}; a tool input is rewritten with
hookSpecificOutput.tool_input; SessionStart takes hookSpecificOutput.additionalContext; an
AfterAgent {"decision": "block", "reason"} makes the agent continue with the reason. Payloads name
no subagent, so a role is known from the invoke_agent call that runs it.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "hooks")


def project(extra=""):
    root = tempfile.mkdtemp(prefix="kiln-gem-")
    with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write(f"project_name=g\nframework=kiln\nengine=godot\nruntimes=gemini\n{extra}")
    return root


def hook(root, script, event, *args, **payload):
    data = dict({"session_id": "gs", "transcript_path": "", "cwd": root,
                 "hook_event_name": event, "timestamp": "2026-10-14T10:00:00Z"}, **payload)
    env = dict(os.environ, GEMINI_PROJECT_DIR=root, CLAUDE_PROJECT_DIR=root)
    p = subprocess.run([sys.executable, "-B", os.path.join(HOOKS, script), *args,
                        "--runtime", "gemini"], input=json.dumps(data), env=env,
                       capture_output=True, text=True, timeout=30)
    return json.loads(p.stdout) if p.stdout.strip() else None


def tool(root, name, **tool_input):
    return hook(root, "guard.py", "BeforeTool", tool_name=name, tool_input=tool_input)


class Guard(unittest.TestCase):
    def test_denials_use_gemini_s_shape(self):
        root = project()
        res = tool(root, "run_shell_command", command="git add -A")
        self.assertEqual(res["decision"], "deny")
        self.assertIn("Stage specific files", res["reason"])
        self.assertIsNone(tool(root, "run_shell_command", command="git status"))

    def test_file_tools_and_mcp_names_are_understood(self):
        root = project()
        self.assertEqual(tool(root, "write_file", file_path="level.tscn",
                              content="[gd_scene]")["decision"], "deny")
        self.assertEqual(tool(root, "replace", file_path="level.tscn", old_string="a",
                              new_string="b")["decision"], "deny")
        self.assertEqual(tool(root, "mcp_blender_execute_blender_code_for_cli",
                              code="x")["decision"], "deny")

    def test_a_role_is_known_while_invoke_agent_runs_it(self):
        root = project()
        self.assertIsNone(tool(root, "write_file", file_path="GAME.md", content="x"))  # main
        start = hook(root, "session.py", "BeforeTool", "subagent", tool_name="invoke_agent",
                     tool_input={"agent_name": "kiln-art-director", "prompt": "Review TASK-001"})
        rewritten = start["hookSpecificOutput"]["tool_input"]
        # live gemini-cli 0.64.0: the rewritten input is validated on its own, so it carries every
        # parameter ("params must have required property 'agent_name'")
        self.assertEqual(rewritten["agent_name"], "kiln-art-director")
        prompt = rewritten["prompt"]
        self.assertIn("Kiln project", prompt)                 # the role gets the engine profile
        self.assertTrue(prompt.endswith("Review TASK-001"))
        self.assertEqual(tool(root, "write_file", file_path="GAME.md",
                              content="x")["decision"], "deny")  # not the art-director's zone
        hook(root, "stop.py", "AfterTool", "subagent", tool_name="invoke_agent",
             tool_input={"agent_name": "kiln-art-director", "prompt": "Review TASK-001"},
             tool_response={"llmContent": "status: DONE"})
        self.assertIsNone(tool(root, "write_file", file_path="GAME.md", content="x"))


    def test_one_role_at_a_time(self):
        # Research 2026-10-19: Gemini runs invoke_agent calls of one turn in parallel, and the one
        # role marker would name the wrong role for the other's calls.
        root = project()
        first = hook(root, "session.py", "BeforeTool", "subagent", tool_name="invoke_agent",
                     tool_input={"agent_name": "kiln-art-director", "prompt": "Review TASK-001"})
        self.assertNotEqual((first or {}).get("decision"), "deny")
        second = hook(root, "session.py", "BeforeTool", "subagent", tool_name="invoke_agent",
                      tool_input={"agent_name": "kiln-modeler", "prompt": "Build TASK-002"})
        self.assertEqual(second["decision"], "deny")
        self.assertIn("kiln-art-director", second["reason"])
        self.assertEqual(tool(root, "write_file", file_path="GAME.md",
                              content="x")["decision"], "deny")  # still the art-director's turn
        hook(root, "stop.py", "AfterTool", "subagent", tool_name="invoke_agent",
             tool_input={"agent_name": "kiln-art-director", "prompt": "Review TASK-001"},
             tool_response={"llmContent": "status: DONE"})
        again = hook(root, "session.py", "BeforeTool", "subagent", tool_name="invoke_agent",
                     tool_input={"agent_name": "kiln-modeler", "prompt": "Build TASK-002"})
        self.assertNotEqual((again or {}).get("decision"), "deny")

    def test_the_role_mark_ends_with_the_main_turn(self):
        # live run: an invoke_agent that failed before running left its role on the main
        # session's next calls; AfterAgent (the main turn's end) clears it
        root = project()
        hook(root, "session.py", "BeforeTool", "subagent", tool_name="invoke_agent",
             tool_input={"agent_name": "kiln-art-director", "prompt": "Review"})
        hook(root, "stop.py", "AfterAgent", "stop", prompt="go", prompt_response="x",
             stop_hook_active=False)
        self.assertIsNone(tool(root, "write_file", file_path="GAME.md", content="x"))


class Session(unittest.TestCase):
    def test_session_start_gives_the_project_context(self):
        root = project()
        res = hook(root, "session.py", "SessionStart", "start", source="startup")
        self.assertIn("Kiln project 'g'", res["hookSpecificOutput"]["additionalContext"])

    def test_autopilot_keeps_going_after_the_agent_stops(self):
        root = project()
        os.makedirs(os.path.join(root, "tasks"))
        with open(os.path.join(root, "tasks", "TASK-001.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-001: helmet\n\n- [ ] model\n")
        os.makedirs(os.path.join(root, ".kiln"), exist_ok=True)
        with open(os.path.join(root, ".kiln", "autopilot"), "w", encoding="utf-8") as fh:
            fh.write("scope: demo\n")
        res = hook(root, "stop.py", "AfterAgent", "stop", prompt="go",
                   prompt_response="done", stop_hook_active=False)
        self.assertEqual(res["decision"], "block")
        self.assertIn("TASK-001", res["reason"])


if __name__ == "__main__":
    unittest.main()
