"""Tests for plugins/kiln/scripts/mcp_check.py (stdlib only)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "scripts",
                      "mcp_check.py")


def project(engine="godot", dimension="3d"):
    root = tempfile.mkdtemp(prefix="kiln-mcp-")
    with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write(f"framework=kiln\nengine={engine}\ndimension={dimension}\n")
    return root


def run(root, *args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=root, capture_output=True,
                       text=True, timeout=30)
    return p.returncode, json.loads(p.stdout)


class McpCheck(unittest.TestCase):
    def test_required_follows_manifest(self):
        code, reqs = run(project("godot", "3d"), "required")
        self.assertEqual([r["server"] for r in reqs], ["blender", "godot-ai"])
        self.assertTrue(all(r["required"] for r in reqs))
        godot = reqs[1]
        self.assertIn("scene_open", godot["tools"])
        self.assertIn("test_manage", godot["tools"])  # named in qa role tool lists
        code, reqs = run(project("unreal", "3d"), "required", "--runtime", "codex")
        self.assertEqual(reqs[1]["server"], "unreal")
        self.assertIn("SceneTools", reqs[1]["toolsets"])
        self.assertTrue(reqs[1]["register"].startswith("codex mcp add unreal"))
        code, reqs = run(project("godot", "2d"), "required")
        self.assertFalse(reqs[0]["required"])  # Blender optional in 2D
        self.assertIn("tilemap_manage", reqs[1]["tools"])

    def test_asset_mode_needs_only_blender(self):
        # S08: engine=none (kind=assets) - no engine server; Blender required even for 2D,
        # where sprite sheets are rendered from a model.
        for dimension in ("3d", "2d"):
            code, reqs = run(project("none", dimension), "required")
            self.assertEqual([r["server"] for r in reqs], ["blender"])
            self.assertTrue(reqs[0]["required"])

    def test_opencode_register_entries(self):
        # OpenCode has no `mcp add`: the register line is the opencode.json "mcp" entry
        # (type local + command list, or type remote + url), checked live with OpenCode 1.19.0
        code, reqs = run(project("godot", "3d"), "required", "--runtime", "opencode")
        cmds = {r["server"]: r["register"] for r in reqs}
        self.assertEqual(json.loads(cmds["godot-ai"]),
                         {"godot-ai": {"type": "local", "command": ["godot-ai", "attach"]}})
        code, reqs = run(project("unity", "3d"), "required", "--runtime", "opencode")
        self.assertEqual(json.loads(reqs[1]["register"]),
                         {"unity": {"type": "remote", "url": "http://localhost:8080/mcp"}})

    def test_copilot_register_commands(self):
        # Copilot CLI 1.0.97 `copilot mcp add <name> -- <command> [args]`,
        # `copilot mcp add --transport http <name> <url>` (checked with the installed CLI)
        code, reqs = run(project("godot", "3d"), "required", "--runtime", "copilot")
        cmds = {r["server"]: r["register"] for r in reqs}
        self.assertEqual(cmds["godot-ai"], "copilot mcp add godot-ai -- godot-ai attach")
        code, reqs = run(project("unreal", "3d"), "required", "--runtime", "copilot")
        self.assertEqual(reqs[1]["register"],
                         "copilot mcp add --transport http unreal http://127.0.0.1:8000/mcp")

    def test_gemini_register_commands(self):
        # G03: gemini-cli 0.64.0 `gemini mcp add [-s user] [-t http] <name> <commandOrUrl> [args]`
        # (checked with the installed CLI: stdio command + args, http url)
        code, reqs = run(project("godot", "3d"), "required", "--runtime", "gemini")
        self.assertEqual(code, 0, reqs)
        cmds = {r["server"]: r["register"] for r in reqs}
        self.assertTrue(cmds["godot-ai"].startswith("gemini mcp add -s user godot-ai "), cmds)
        code, reqs = run(project("unity", "3d"), "required", "--runtime", "gemini")
        self.assertEqual(reqs[1]["register"], "gemini mcp add -s user -t http unity "
                                              "http://localhost:8080/mcp")

    def test_manifest_with_spaces_around_equals(self):
        # Review 2026-10-14: the hooks read "engine = unreal"; mcp_check fell back to Godot.
        root = tempfile.mkdtemp(prefix="kiln-mcp-")
        with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write("framework = kiln\nengine = unreal\n")
        code, reqs = run(root, "required")
        self.assertEqual([r["server"] for r in reqs], ["blender", "unreal"])

    def test_verify(self):
        root = project("godot", "3d")
        _, reqs = run(root, "required")
        names = [f"mcp__{r['server']}__{t}" for r in reqs for t in r["tools"]]
        avail = os.path.join(root, "tools.txt")
        with open(avail, "w") as fh:
            fh.write("\n".join(names))
        code, res = run(root, "verify", "--available", avail, "--probe", "blender=ok",
                        "--probe", "godot-ai=ok")
        self.assertEqual(code, 0, res)
        self.assertTrue(res["ready"])
        with open(os.path.join(root, ".kiln", "mcp-check.json")) as fh:
            self.assertIn('"ready": true', fh.read())
        with open(avail, "w") as fh:
            fh.write("\n".join(n for n in names if not n.endswith("__scene_save")))
        code, res = run(root, "verify", "--available", avail, "--probe", "blender=ok",
                        "--probe", "godot-ai=connection refused")
        self.assertEqual(code, 1)
        godot = [s for s in res["servers"] if s["server"] == "godot-ai"][0]
        self.assertIn("scene_save", " ".join(godot["problems"]))
        self.assertIn("connection refused", " ".join(godot["problems"]))


class UnrealNames(unittest.TestCase):
    def test_qualified_toolsets_and_alias(self):
        root = project("unreal", "3d")
        _, reqs = run(root, "required")
        unreal = reqs[1]
        lines = [f"mcp__unreal-mcp__{t}" for t in unreal["tools"]]
        lines += [f"unreal:toolset:editor_toolset.toolsets.x.{t}" for t in unreal["toolsets"]]
        lines += [f"mcp__blender__{t}" for t in reqs[0]["tools"]]
        avail = os.path.join(root, "tools.txt")
        with open(avail, "w") as fh:
            fh.write("\n".join(lines))
        code, res = run(root, "verify", "--available", avail, "--probe", "blender=ok",
                        "--probe", "unreal=ok")
        self.assertEqual(code, 0, res)


if __name__ == "__main__":
    unittest.main()
