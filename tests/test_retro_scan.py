"""Tests for plugins/kiln/skills/retro/scripts/retro_scan.py (stdlib only)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "retro",
                      "scripts", "retro_scan.py")


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def scan(root, *extra):
    p = subprocess.run([sys.executable, "-B", SCRIPT, "--root", root, *extra],
                       capture_output=True, text=True, timeout=60, encoding="utf-8")
    return json.loads(p.stdout)


class RetroScan(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-retro-")
        den = [
            {"ts": "2026-10-08 10:00:00", "tool": "Bash", "role": "gameplay-dev",
             "reason": "[kiln] scripts/a.gd is a Godot script. Use script_patch", "input": "x"},
            {"ts": "2026-10-08 10:05:00", "tool": "Write", "role": "fx-artist",
             "reason": "[kiln] scripts/b.gd is a Godot script. Use script_patch", "input": "y"},
            {"ts": "2026-10-08 10:06:00", "tool": "Write", "role": "fx-artist",
             "reason": "[kiln] scripts/b.gd is a Godot script. Use script_patch", "input": "y"},
            {"ts": "2026-10-01 09:00:00", "tool": "Bash", "role": "main",
             "reason": "[kiln] old", "input": "z"},
        ]
        write(self.root, ".kiln/denials.jsonl", "\n".join(json.dumps(d) for d in den) + "\n")
        write(self.root, ".kiln/hooks.log", "2026-10-08 11:00:00 hook error:\nTraceback\nNameError: boom\n"
                                            "2026-10-08 11:01:00 trace claude PreToolUse\n")
        write(self.root, "tasks/TASK-001.md", "# T\n## review: art-director (r1)\nverdict: CHANGES_REQUIRED\n"
                                              "## review: art-director (r2)\nverdict: APPROVED\n## log\n"
                                              "- 2026-10-08 user: \"the arms are frozen\" — fix\n")
        write(self.root, "production/PIPELINE.md", "- [x] look approved — user PROXY 2026-10-08\n")
        log = [{"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "id": "1", "name": "mcp__godot-ai__editor_manage", "input": {}},
                    {"type": "tool_use", "id": "2", "name": "Agent", "input": {"subagent_type": "code-reviewer"}}]}},
               {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "1", "is_error": True}]}},
               {"type": "user", "message": {"content": "plain text message"}},
               {"type": "result", "num_turns": 9, "total_cost_usd": 1.5, "subtype": "success"}]
        self.log = write(self.root, "run.jsonl", "\n".join(json.dumps(x) for x in log) + "\n")

    def test_groups_denials_and_flags_repeats(self):
        rep = scan(self.root, "--since", "2026-10-08")
        d = rep["denials"]
        self.assertEqual(d["total"], 3)
        top = d["by_rule"][0]
        self.assertEqual(top["count"], 3)          # same rule, different files
        self.assertEqual(top["repeated_same_input"], 1)
        self.assertEqual(top["roles"], {"gameplay-dev": 1, "fx-artist": 2})

    def test_hook_errors_tasks_and_proxy(self):
        rep = scan(self.root, "--since", "2026-10-08")
        self.assertEqual(rep["hook_errors"]["count"], 1)
        self.assertIn("NameError", rep["hook_errors"]["errors"][0]["error"])
        task = rep["tasks"]["tasks"][0]
        self.assertEqual((task["reviews"], task["changes_required"]), (2, 1))
        self.assertEqual(task["user_lines"][0]["date"], "2026-10-08")
        self.assertEqual(len(rep["decisions"]["pipeline_proxy_gates"]), 1)

    def test_transcript_errors_and_foreign_agents(self):
        rep = scan(self.root, "--transcript", self.log)
        t = rep["transcripts"]
        self.assertEqual(t["tool_errors"], {"mcp__godot-ai__editor_manage": 1})
        self.assertEqual(t["non_kiln_agents"], ["code-reviewer"])
        self.assertEqual(t["result"]["turns"], 9)

    def test_subagent_effort_and_thinking(self):
        sub = os.path.join(self.root, "sess", "subagents")
        rows = [{"type": "assistant", "effort": "medium", "timestamp": "2026-10-11T10:00:00Z",
                 "message": {"id": "m1", "content": [{"type": "tool_use", "id": "a"}],
                             "usage": {"output_tokens": 5}}},          # streamed part, same id
                {"type": "assistant", "effort": "medium", "timestamp": "2026-10-11T10:00:01Z",
                 "message": {"id": "m1", "content": [{"type": "tool_use", "id": "a"}],
                             "usage": {"output_tokens": 100, "output_tokens_details": {"thinking_tokens": 60}}}},
                {"type": "user", "timestamp": "2026-10-11T10:03:01Z",
                 "message": {"content": [{"type": "tool_result", "tool_use_id": "a"}]}},
                {"type": "assistant", "effort": "medium", "timestamp": "2026-10-11T10:10:01Z",
                 "message": {"id": "m2", "content": [{"type": "text", "text": "DONE"}],
                             "usage": {"output_tokens": 100, "output_tokens_details": {"thinking_tokens": 20}}}}]
        write(self.root, "sess/subagents/agent-x.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
        write(self.root, "sess/subagents/agent-x.meta.json", '{"agentType": "modeler", "description": "T1 build"}')
        run = scan(self.root, "--subagents", sub)["subagents"]["runs"][0]
        self.assertEqual((run["agent"], run["effort"], run["responses"]), ("modeler", "medium", 2))
        self.assertEqual((run["output_tokens"], run["thinking_tokens"], run["thinking_share"]), (200, 80, 0.4))
        self.assertEqual((run["wall_min"], run["tool_wait_min"], run["model_min"]), (10.0, 3.0, 7.0))

    def test_role_coverage(self):
        # g2 row 45: in 18 tasks the anatomy, creature and physics experts, qa-audio and the
        # playtester never ran once; nobody saw it until the user asked.
        write(self.root, "tasks/archive/TASK-001.md",
              "# TASK-001: merchant\n## spec\ntype: art\nrole: modeler\ntouches: humanoid\n"
              "## gates\n| role | why | verdict |\n|---|---|---|\n"
              "| anatomy-expert | humanoid | SKIP: user said no review (decision #4) |\n"
              "| art-director | refs | APPROVED |\n| qa-readability | art | PASS |\n"
              "| verifier | close | PASSED |\n## handoff: modeler\nstatus: DONE\n")
        write(self.root, "tasks/TASK-002.md",
              "# TASK-002: controller\n## spec\ntype: gameplay\nrole: gameplay-dev\n"
              "touches: physics, movement\n## handoff: gameplay-dev\nstatus: DONE\n"
              "## acceptance: qa-feel — gym — 2026-10-12\nverdict: PASS\n")
        rep = scan(self.root)["roles"]
        self.assertIn("modeler", rep["ran"])
        self.assertIn("qa-feel", rep["ran"])
        self.assertIn("art-director", rep["ran"])                    # by its gates verdict
        for role in ("physics-expert", "qa-physics", "playtester"):
            self.assertIn(role, rep["required_never_ran"])
        self.assertNotIn("verifier", rep["required_never_ran"])       # ran on TASK-001
        self.assertIn("verifier", rep["owed"]["TASK-002"])
        self.assertIn("qa-audio", rep["never_used"])
        self.assertEqual(rep["skipped"][0]["role"], "anatomy-expert")
        self.assertIn("decision #4", rep["skipped"][0]["reason"])
        self.assertIn("physics-expert", rep["owed"]["TASK-002"])

    def test_missing_sources_are_absent_not_errors(self):
        rep = scan(tempfile.mkdtemp())
        self.assertFalse(rep["denials"]["present"])
        self.assertFalse(rep["hook_errors"]["present"])
        self.assertEqual(rep["tasks"]["count"], 0)


class Pitfalls(unittest.TestCase):
    # K05: defect knowledge in one format, and the retro proposes a check where none exists.
    CATALOGUE = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                             "animation", "references", "reads-wrong.md")

    def test_every_entry_has_the_five_parts(self):
        import re
        text = open(self.CATALOGUE, encoding="utf-8").read()
        entries = re.split(r"^### ", text, flags=re.M)[1:]
        self.assertGreaterEqual(len(entries), 14)             # nothing lost in the reformat
        for entry in entries:
            for part in ("**Looks like:**", "**Why:**", "**Fix principle:**", "**Caught by:**"):
                self.assertIn(part, entry, entry[:60])

    def test_scan_lists_entries_without_a_check_and_the_user_s_defects(self):
        root = tempfile.mkdtemp(prefix="kiln-retro-pit-")
        write(root, "manifest.md", "framework=kiln\nengine=godot\n")
        catalogue = os.path.join(root, "pitfalls.md")
        with open(catalogue, "w", encoding="utf-8") as fh:
            fh.write("# x\n\n### 1. Caught one\n- **Looks like:** a\n- **Why:** b\n"
                     "- **Fix principle:** c\n- **Caught by:** `analyze.py idle`\n\n"
                     "### 2. Not caught\n- **Looks like:** the cape clips the sword\n- **Why:** d\n"
                     "- **Fix principle:** e\n- **Caught by:** no check yet\n")
        write(root, "tasks/TASK-007.md", "# TASK-007: cape\n## log\n"
              "- 2026-10-14 user: the cape goes through the sword when he turns\n")
        res = scan(root, "--pitfalls", catalogue)
        self.assertEqual([e["title"] for e in res["pitfalls"]["no_check_yet"]], ["2. Not caught"])
        self.assertEqual(res["pitfalls"]["user_reported"][0]["task"], "TASK-007")
        self.assertIn("cape", res["pitfalls"]["user_reported"][0]["text"])


if __name__ == "__main__":
    unittest.main()
