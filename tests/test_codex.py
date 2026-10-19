"""Tests for the OpenAI Codex adapter.

Run: python -m unittest discover -s tests -v   (stdlib only)

- hooks/codex-hooks.json commands are launched the way Codex launches them, in every session shell
  it may pick (see session_shells) with PLUGIN_ROOT set and the hook JSON on stdin;
- the plugin manifest is the form whose hooks Codex 0.160 actually loads;
- guard.py handles Codex apply_patch payloads;
- scripts/codex_agents.py output parses as TOML and carries the documented required fields.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLUGIN = os.path.join(REPO, "plugins", "kiln")
HOOKS = json.load(open(os.path.join(PLUGIN, "hooks", "codex-hooks.json"), encoding="utf-8"))


def make_project(engine="godot"):
    root = tempfile.mkdtemp(prefix="kiln-codex-")
    with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write(f"project_name=t\nframework=kiln\nengine={engine}\n")
    return root


def handler(event):
    return HOOKS["hooks"][event][0]["hooks"][0]


def session_shells():
    """The launchers Codex 0.160 may use for a hook command on this OS.

    core/src/session/mod.rs build_hooks_config: the session shell's derive_exec_args (shell.rs:
    PowerShell `-NoProfile -Command`, cmd `/c`, bash/zsh/sh `-c`); with no session shell,
    hooks/src/engine/command_runner.rs falls back to %COMSPEC% /C "<command>" or $SHELL -lc.
    """
    if os.name != "nt":
        shells = [("fallback", lambda line: [os.environ.get("SHELL", "/bin/sh"), "-lc", line])]
        if shutil.which("bash"):
            shells.append(("bash", lambda line: [shutil.which("bash"), "-c", line]))
        return shells
    comspec = os.environ.get("COMSPEC", "cmd.exe")
    shells = [("fallback", lambda line: f'{comspec} /C "{line}"'),
              ("cmd", lambda line: f'{comspec} /c "{line}"')]
    if shutil.which("powershell.exe"):
        shells.append(("powershell",
                       lambda line: [shutil.which("powershell.exe"), "-NoProfile", "-Command", line]))
    if shutil.which("bash"):
        shells.append(("bash", lambda line: [shutil.which("bash"), "-c", line]))
    return shells


def run_like_codex(event, payload, root, shell=None):
    """Launch a hook command the way Codex's command runner does (default: the fallback)."""
    h = handler(event)
    env = dict(os.environ, PLUGIN_ROOT=PLUGIN, CLAUDE_PLUGIN_ROOT=PLUGIN)
    env.pop("CLAUDE_PROJECT_DIR", None)
    payload = {"session_id": "s", "transcript_path": None, "cwd": root, "hook_event_name": event,
               "model": "gpt-6.1-sol", "permission_mode": "default", **payload}
    line = (h.get("commandWindows") or h["command"]) if os.name == "nt" else h["command"]
    launch = shell or session_shells()[0][1]
    return subprocess.run(launch(line), input=json.dumps(payload), capture_output=True, text=True,
                          env=env, cwd=root, timeout=60)


def decision(proc):
    out = proc.stdout.strip()
    if not out:
        return "ALLOW"
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"].upper()


PATCH_SCENE = """*** Begin Patch
*** Add File: scenes/arena.tscn
+[gd_scene format=3]
*** End Patch
"""
PATCH_NOTE = """*** Begin Patch
*** Update File: tasks/TASK-001.md
@@
-old
+new
*** End Patch
"""
PATCH_CS = """*** Begin Patch
*** Add File: Assets/_Project/Scripts/Runtime/Arena.cs
+void Start() { var g = new GameObject("wall"); }
*** End Patch
"""
PATCH_MOVE = """*** Begin Patch
*** Update File: notes.md
*** Move to: scenes/level.tscn
@@
+x
*** End Patch
"""


class CodexManifest(unittest.TestCase):
    """Codex 0.160 loads plugin hooks only from the compatibility manifest.

    codex-rs/utils/plugins/src/plugin_namespace.rs: a root plugin.json with the Agent Plugins
    $schema wins over .codex-plugin/plugin.json; core-plugins/src/loader.rs then returns no hook
    sources for that format (seen live: no plugin hook ran). Without a `hooks` entry Codex falls
    back to hooks/hooks.json, which is the Claude Code file.
    """

    def test_no_portable_root_manifest(self):
        root = os.path.join(PLUGIN, "plugin.json")
        if os.path.isfile(root):
            data = json.load(open(root, encoding="utf-8"))
            self.assertNotIn("agent-plugins.org", data.get("$schema", ""),
                             "a portable root plugin.json makes Codex drop the plugin's hooks")

    def test_compat_manifest_points_at_codex_hooks(self):
        data = json.load(open(os.path.join(PLUGIN, ".codex-plugin", "plugin.json"),
                              encoding="utf-8"))
        self.assertEqual(data["hooks"], "./hooks/codex-hooks.json")
        paths = [data["hooks"], data["skills"], data["interface"]["composerIcon"],
                 data["interface"]["logo"]]
        for path in paths:
            self.assertTrue(path.startswith("./"), path)
            self.assertTrue(os.path.exists(os.path.join(PLUGIN, path[2:])), path)
        claude = json.load(open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"),
                                encoding="utf-8"))
        self.assertEqual(data["version"], claude["version"])
        self.assertEqual(data["name"], claude["name"])

    def test_session_start_covers_forked_sessions(self):
        # Codex 0.155 added the "fork" SessionStart source; without it a fork had no Kiln context
        matcher = HOOKS["hooks"]["SessionStart"][0]["matcher"]
        self.assertEqual(set(matcher.split("|")), {"startup", "resume", "clear", "compact", "fork"})

    def test_every_hook_has_a_readable_name_in_the_review(self):
        # User 2026-10-19: Codex's hook review listed Kiln's hooks as "Hook 1", "Hook 3".
        # Its /hooks browser titles a handler by statusMessage (tui hooks_browser_view.rs).
        want = {("PreToolUse", "guard.py"): "Protect Kiln project tools",
                ("SessionStart", "session.py start"): "Load Kiln project state",
                ("SubagentStart", "session.py subagent"): "Add engine rules to Kiln agents",
                ("SessionEnd", "session.py end"): "Save session handoff and release locks",
                ("Stop", "stop.py stop"): "Manage Kiln autopilot and release locks",
                ("SubagentStop", "stop.py subagent"): "Clean up Kiln agent state"}
        seen = {}
        for event, groups in HOOKS["hooks"].items():
            for group in groups:
                for hook in group["hooks"]:
                    script = next(s for (e, s) in want if e == event and s in hook["commandWindows"])
                    seen[(event, script)] = hook.get("statusMessage")
        self.assertEqual(seen, want)


class CodexHookLaunch(unittest.TestCase):
    def test_every_session_shell(self):
        # Live Codex on Windows ran the hooks through PowerShell, where %PLUGIN_ROOT% stays
        # literal: every hook failed and apply_patch went through. Each command must work in
        # every launcher Codex may pick.
        root = make_project()
        payload = {"tool_name": "apply_patch", "tool_use_id": "t", "turn_id": "u",
                   "tool_input": {"command": PATCH_SCENE}}
        for name, launch in session_shells():
            with self.subTest(shell=name):
                p = run_like_codex("PreToolUse", payload, root, shell=launch)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(decision(p), "DENY", p.stdout + p.stderr)
                p = run_like_codex("SessionStart", {"source": "startup"}, root, shell=launch)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn("kiln-<role>", p.stdout)
        for event, groups in HOOKS["hooks"].items():
            for h in (h for g in groups for h in g["hooks"]):
                self.assertNotIn("%", h.get("commandWindows", ""), event)

    def test_pre_tool_use_apply_patch(self):
        root = make_project()
        p = run_like_codex("PreToolUse", {"tool_name": "apply_patch", "tool_use_id": "t",
                                          "turn_id": "u", "tool_input": {"command": PATCH_SCENE}},
                           root)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(decision(p), "DENY", p.stdout)
        p = run_like_codex("PreToolUse", {"tool_name": "apply_patch", "tool_use_id": "t",
                                          "turn_id": "u", "tool_input": {"command": PATCH_NOTE}},
                           root)
        self.assertEqual(decision(p), "ALLOW", p.stdout)

    def test_pre_tool_use_bash_and_mcp(self):
        root = make_project()
        p = run_like_codex("PreToolUse", {"tool_name": "Bash", "tool_use_id": "t", "turn_id": "u",
                                          "tool_input": {"command": "git add -A"}}, root)
        self.assertEqual(decision(p), "DENY", p.stdout)
        p = run_like_codex("PreToolUse", {"tool_name": "mcp__blender__render_for_cli",
                                          "tool_use_id": "t", "turn_id": "u", "tool_input": {}},
                           root)
        self.assertEqual(decision(p), "DENY", p.stdout)

    def test_session_start_and_subagent(self):
        root = make_project("unreal")
        p = run_like_codex("SessionStart", {"source": "startup"}, root)
        ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("kiln-<role>", ctx)
        p = run_like_codex("SubagentStart", {"agent_id": "a", "agent_type": "kiln-gameplay-dev",
                                             "turn_id": "u"}, root)
        ctx = json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("engine=unreal", ctx)
        self.assertGreater(len(ctx), 5000)  # engine profile injected
        self.assertLess(len(ctx) / 4, handler("SubagentStart")["additionalContextLimit"])

    def test_stop_and_session_end(self):
        root = make_project()
        p = run_like_codex("Stop", {"turn_id": "u", "stop_hook_active": False,
                                    "last_assistant_message": "done"}, root)
        self.assertEqual(p.returncode, 0, p.stderr)
        if p.stdout.strip():
            json.loads(p.stdout)  # Stop output must be JSON when present
        p = run_like_codex("SessionEnd", {"reason": "other"}, root)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(os.path.exists(os.path.join(root, "memory", "session-handoff.md")))


class CodexGuard(unittest.TestCase):
    def guard(self, root, payload, role=None):
        data = {"tool_use_id": "t", "turn_id": "u", "cwd": root, **payload}
        if role:
            data.update(agent_type=f"kiln-{role}", agent_id="a1")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
        out = subprocess.run([sys.executable, "-B", os.path.join(PLUGIN, "hooks", "guard.py"),
                              "--runtime", "codex"], input=json.dumps(data), env=env,
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return "ALLOW" if not out else "DENY"

    def patch(self, text):
        return {"tool_name": "apply_patch", "tool_input": {"command": text}}

    def test_patch_rules(self):
        root = make_project()
        self.assertEqual(self.guard(root, self.patch(PATCH_SCENE)), "DENY")
        self.assertEqual(self.guard(root, self.patch(PATCH_MOVE)), "DENY")  # move into a .tscn
        self.assertEqual(self.guard(root, self.patch(PATCH_NOTE)), "ALLOW")

    def test_scene_first_in_patch(self):
        root = make_project("unity")
        self.assertEqual(self.guard(root, self.patch(PATCH_CS)), "DENY")

    def test_roles_when_agent_type_present(self):
        root = make_project()
        src = "*** Begin Patch\n*** Add File: tools/x.py\n+print(1)\n*** End Patch\n"
        self.assertEqual(self.guard(root, self.patch(src), role="qa-feel"), "DENY")
        self.assertEqual(self.guard(root, self.patch(src), role="gameplay-dev"), "ALLOW")
        # Research 2026-10-19 (codex-rs hook_runtime.rs, 0.160-0.163): only the main thread's hooks
        # lack agent_id / agent_type - a spawned subagent always has them ("default" without a
        # role) - so no identity is the producer, and orchestrator_writes applies.
        self.assertEqual(self.guard(root, self.patch(src)), "DENY")
        default = {**self.patch(src), "agent_type": "default", "agent_id": "a2"}
        self.assertEqual(self.guard(root, default), "ALLOW")  # a role-less subagent: not ours


class CodexAgents(unittest.TestCase):
    def test_manifest_agent_model_and_effort_for_codex(self):
        # V07: Codex has no Agent tool for the guard to fill; the generator applies the manifest.
        proj = tempfile.mkdtemp(prefix="kiln-cx-")
        with open(os.path.join(proj, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write("framework=kiln\nengine=godot\nagent_model=haiku\nagent_effort=low\n")
        out = os.path.join(proj, ".codex", "agents")
        subprocess.run([sys.executable, "-B", os.path.join(PLUGIN, "scripts", "codex_agents.py"),
                        "--out", out, "--user-config", os.path.join(proj, "none.toml")],
                       cwd=proj, check=True, capture_output=True, timeout=60)
        for name in ("kiln-modeler.toml", "kiln-autoplayer.toml", "kiln-verifier.toml"):
            with open(os.path.join(out, name), "rb") as fh:
                agent = tomllib.load(fh)
            self.assertEqual(agent["model"], "gpt-6-luna", name)
            self.assertEqual(agent["model_reasoning_effort"], "low", name)

    def test_a_codex_model_name_in_the_manifest_is_kept(self):
        # Review 2026-10-14: agent_model=gpt-6.1-sol (not a Claude alias) was silently dropped.
        proj = tempfile.mkdtemp(prefix="kiln-cx-")
        with open(os.path.join(proj, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write("framework=kiln\nengine=godot\nagent_model=gpt-6.1-sol\n")
        out = os.path.join(proj, ".codex", "agents")
        subprocess.run([sys.executable, "-B", os.path.join(PLUGIN, "scripts", "codex_agents.py"),
                        "--out", out, "--user-config", os.path.join(proj, "none.toml")],
                       cwd=proj, check=True, capture_output=True, timeout=60)
        with open(os.path.join(out, "kiln-modeler.toml"), "rb") as fh:
            self.assertEqual(tomllib.load(fh)["model"], "gpt-6.1-sol")
        # Review: a Claude-only name Codex does not know (fable) is left out, not written
        with open(os.path.join(proj, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write("framework=kiln\nengine=godot\nagent_model=fable\n")
        subprocess.run([sys.executable, "-B", os.path.join(PLUGIN, "scripts", "codex_agents.py"),
                        "--out", out, "--user-config", os.path.join(proj, "none.toml")],
                       cwd=proj, check=True, capture_output=True, timeout=60)
        with open(os.path.join(out, "kiln-modeler.toml"), "rb") as fh:
            self.assertNotIn("model", tomllib.load(fh))

    def test_generated_agents(self):
        out = tempfile.mkdtemp(prefix="kiln-agents-")
        cfg = os.path.join(out, "config.toml")
        with open(cfg, "w", encoding="utf-8") as fh:
            fh.write('[mcp_servers.blender]\ncommand = "blender-mcp"\n'
                     '[mcp_servers.godot-ai]\ncommand = "godot-ai"\n')
        proc = subprocess.run([sys.executable, "-B", os.path.join(PLUGIN, "scripts",
                                                                   "codex_agents.py"),
                               "--out", out, "--user-config", cfg], capture_output=True,
                              text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        files = sorted(f for f in os.listdir(out) if f.endswith(".toml") and f != "config.toml")
        self.assertEqual(len(files), len(os.listdir(os.path.join(PLUGIN, "agents"))))
        for name in files:
            with open(os.path.join(out, name), "rb") as fh:
                agent = tomllib.load(fh)
            for key in ("name", "description", "developer_instructions"):
                self.assertIsInstance(agent.get(key), str, f"{name}: {key}")
            self.assertEqual(agent["name"] + ".toml", name)
            self.assertNotIn("mcp_servers", agent, f"{name}: partial server tables are invalid")
        with open(os.path.join(out, "kiln-qa-feel.toml"), "rb") as fh:
            qa = tomllib.load(fh)
        self.assertNotIn("default_permissions", qa)  # permission profiles are opt-in
        subprocess.run([sys.executable, "-B", os.path.join(PLUGIN, "scripts", "codex_agents.py"),
                        "--out", out, "--user-config", cfg, "--with-permission-profiles"],
                       check=True, capture_output=True, timeout=60)
        with open(os.path.join(out, "kiln-qa-feel.toml"), "rb") as fh:
            qa = tomllib.load(fh)
        profile = qa["default_permissions"]
        fs = qa["permissions"][profile]["filesystem"][":workspace_roots"]
        self.assertEqual(fs["tasks"], "write")
        self.assertEqual(qa["permissions"][profile]["extends"], ":read-only")
        self.assertIn("From the godot-ai MCP server use only:", qa["developer_instructions"])
        self.assertIn("kiln:acceptance", qa["developer_instructions"])
        with open(os.path.join(out, "kiln-composer.toml"), "rb") as fh:
            composer = tomllib.load(fh)
        self.assertIn("Do not use these MCP servers: blender, godot-ai, unity, unreal",
                      composer["developer_instructions"])
        self.assertNotIn("default_permissions", composer)  # builders inherit the session's


class InstalledRoot(unittest.TestCase):
    def test_newest_cached_version_by_number(self):
        # Review 2026-10-14: a string sort put 0.9.0 after 0.10.0.
        import importlib.util
        path = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "scripts",
                            "codex_agents.py")
        spec = importlib.util.spec_from_file_location("kiln_codex_agents", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        home = tempfile.mkdtemp(prefix="kiln-codex-home-")
        for v in ("0.9.0", "0.10.0", "0.7.2"):
            os.makedirs(os.path.join(home, "plugins", "cache", "kiln", "kiln", v))
        self.assertTrue(mod.installed_root(home).endswith("0.10.0"))


if __name__ == "__main__":
    unittest.main()
