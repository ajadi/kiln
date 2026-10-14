"""Live checks with a real Claude Code session (`claude -p --plugin-dir plugins/kiln`) in a
throwaway Kiln project. They spend money (cheap models, a few cents), so they run only with
KILN_LIVE=1:

  KILN_LIVE=1 python -m unittest tests.test_live -v

Release gate for every version: the hooks behave in a real session, not only when fed JSON.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

PLUGIN = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln"))
CLAUDE = shutil.which("claude")   # claude.cmd / claude.exe on Windows: the full path is needed
LIVE = os.environ.get("KILN_LIVE") == "1" and CLAUDE


def session(root, prompt, timeout=600):
    p = subprocess.run([CLAUDE, "-p", prompt, "--plugin-dir", PLUGIN, "--permission-mode",
                        "bypassPermissions", "--output-format", "stream-json", "--verbose"],
                       cwd=root, capture_output=True, text=True, timeout=timeout,
                       stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace")
    events = []
    for line in p.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    return events


def project(extra=""):
    root = tempfile.mkdtemp(prefix="kiln-live-")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write("project_name=live\nframework=kiln\nengine=godot\ndimension=3d\n" + extra)
    return root


@unittest.skipUnless(LIVE, "set KILN_LIVE=1 (spends money) and have claude on PATH")
class Live(unittest.TestCase):
    def test_manifest_agent_model_reaches_the_subagent(self):
        # V06: the guard fills `model` into an Agent call through updatedInput.
        root = project("agent_model=haiku\nagent_effort=low\n")
        events = session(root, "Call the Agent tool exactly once with subagent_type "
                               "general-purpose, description ping, prompt 'Reply with the single "
                               "word pong.' Do not pass model or effort. Then reply done.")
        sub = [e["message"].get("model") for e in events
               if e.get("type") == "assistant" and e.get("parent_tool_use_id")]
        self.assertTrue(sub, "no subagent turn seen")
        self.assertTrue(all("haiku" in (m or "") for m in sub), sub)

    def test_session_start_injects_the_project_context(self):
        root = project("perf_gate=informational\n")
        events = session(root, "Without using any tool: which engine and which user_gates value "
                               "does the Kiln project context of this session name? Answer as "
                               "engine=<x> user_gates=<y>.", timeout=300)
        final = " ".join(str(e.get("result", "")) for e in events if e.get("type") == "result")
        self.assertIn("engine=godot", final.lower().replace(" ", ""))
        self.assertIn("user_gates=proxy", final.lower().replace(" ", ""))

    def test_guard_denies_a_scene_write_in_a_real_session(self):
        root = project()
        session(root, "Use the Write tool to create scenes/x.tscn with the text [gd_scene]. If "
                      "it is refused, do not try another way; reply with the refusal reason.",
                timeout=300)
        self.assertFalse(os.path.exists(os.path.join(root, "scenes", "x.tscn")))
        with open(os.path.join(root, ".kiln", "denials.jsonl"), encoding="utf-8") as fh:
            self.assertIn("tscn", fh.read())


if __name__ == "__main__":
    unittest.main()
