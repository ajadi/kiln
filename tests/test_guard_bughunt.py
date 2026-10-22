"""Guard regressions from the 2026-10-20 bug hunt: line continuations, removing framework files,
effort copies of roles, Windows path aliases, interpreter options, PowerShell parameters, cd,
'..' in probe paths, git option parsing, paid generators' MCP servers in every runtime, Codex
apply_patch on task files, odd manifests and the editor queue lock.

GUARD can point at another copy of the hooks (KILN_TEST_HOOKS) to show the tests fail on it."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.environ.get("KILN_TEST_HOOKS") or os.path.join(
    os.path.dirname(__file__), "..", "plugins", "kiln", "hooks")
GUARD = os.path.join(HOOKS, "guard.py")


def make_project(engine="godot", extra="", git=False):
    root = tempfile.mkdtemp(prefix=f"kiln-hunt-{engine}-")
    with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write(f"project_name=t\nframework=kiln\nengine={engine}\n{extra}")
    if git:
        subprocess.run(["git", "init", "-q", root], capture_output=True)
    return root


def run_guard(root, payload, args=(), env_root=True):
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    if env_root:
        env["CLAUDE_PROJECT_DIR"] = root
    p = subprocess.run([sys.executable, "-B", GUARD, *args], input=json.dumps(payload), env=env,
                       capture_output=True, text=True, timeout=30)
    out = p.stdout.strip()
    if not out:
        return "ALLOW", p.stderr[-300:]
    data = json.loads(out)
    spec = data.get("hookSpecificOutput", data)
    decision = spec.get("permissionDecision") or data.get("decision") or "?"
    return decision.upper(), spec.get("permissionDecisionReason") or data.get("reason", "")


def shell(command, role=None, tool="Bash", cwd=None):
    data = {"tool_name": tool, "tool_input": {"command": command}}
    if role:
        data.update(agent_type=f"kiln:{role}", agent_id="a1")
    if cwd:
        data["cwd"] = cwd
    return data


def write(path, role=None, content=""):
    data = {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}
    if role:  # effort copies and built-in agents are project/agent names without kiln:
        plain = role == "general-purpose" or role.endswith(("-high", "-low", "-medium", "-max"))
        data.update(agent_type=role if plain else f"kiln:{role}", agent_id="a1")
    return data


class Case(unittest.TestCase):
    def check(self, payload, expected, root=None, **kw):
        got, reason = run_guard(root or make_project(), payload, **kw)
        self.assertEqual(got, expected, f"{payload} -> {reason}")


class ShellBypasses(Case):
    def test_line_continuations(self):
        for cmd in ("cp /tmp/new.tscn \\\n  scenes/main.tscn",
                    "blender \\\n -b x.blend -P y.py",
                    "git push \\\n --force origin main",
                    "git add \\\n -A",
                    "Set-Content `\n -Path scenes/main.tscn -Value x"):
            self.check(shell(cmd, "modeler"), "DENY")
        # a here-document body keeps its backslashes and its end marker
        self.check(shell("cat > notes.txt <<EOF\nline \\\nEOF\necho ok", "modeler"), "ALLOW")

    def test_removing_or_moving_framework_files(self):
        for cmd in ("mv manifest.md manifest.bak", "rm manifest.md", "Remove-Item manifest.md",
                    "Rename-Item manifest.md m.bak", "rm -rf .claude", "git rm manifest.md",
                    "cd art && rm ../manifest.md"):
            self.check(shell(cmd, "modeler"), "DENY")
            self.check(shell(cmd), "DENY")
        self.check(shell("rm -rf art/tmp", "modeler"), "ALLOW")
        self.check(shell("rm scenes/main.tscn", "modeler"), "DENY")   # scenes change in the editor

    def test_interpreter_options_before_kiln_scripts(self):
        root = make_project(extra="model_generators=api\nasset_libraries=off\n")
        os.makedirs(os.path.join(root, ".kiln"))
        open(os.path.join(root, ".kiln", "autopilot"), "w").close()
        for cmd in ("python -X utf8 skills/api-generators/scripts/gen_api.py submit j1",
                    "py -3 -u gen_api.py submit j1",
                    "python -X utf8 assets_api.py fetch polyhaven x"):
            self.check(shell(cmd), "DENY", root)

    def test_powershell_parameters(self):
        for cmd in ('"x" | Out-File -Encoding utf8 scenes/main.tscn',
                    "Set-Content -Value 'x' scenes/main.tscn",
                    "sc scenes/main.tscn x", "New-Item scenes/main.tscn -Value x",
                    "Copy-Item a.tscn -Destination scenes/main.tscn"):
            self.check(shell(cmd, "modeler", tool="PowerShell"), "DENY")
        self.check(shell('"x" | Out-File -Encoding utf8 playtests/r.md', "playtester",
                         tool="PowerShell"), "ALLOW")

    def test_copy_into_a_folder_and_target_directory(self):
        root = make_project()
        os.makedirs(os.path.join(root, "scenes"))
        os.makedirs(os.path.join(root, ".claude", "agents"))
        self.check(shell("cp /tmp/main.tscn scenes", "modeler"), "DENY", root)
        self.check(shell("cp -t .claude/agents evil.md", "modeler"), "DENY", root)

    def test_cd_moves_relative_targets(self):
        root = make_project()
        os.makedirs(os.path.join(root, "scenes"))
        os.makedirs(os.path.join(root, "tests", "probes"))
        self.check(shell("cd scenes && echo x > ../project.godot", "modeler"), "DENY", root)
        self.check(shell("cd tests/probes && echo x > out.txt", "playtester"), "ALLOW", root)

    def test_wrapped_and_substituted_commands(self):
        for cmd in ("bash -c 'blender -b x.blend -P y.py'", "cmd /c blender -b x.blend",
                    "echo $(godot-ai attach)", 'python -c "import os, bpy"',
                    "cat <<EOF | python -\nimport bpy\nEOF",
                    "uv run python - <<EOF\nimport bpy\nEOF",
                    "curl http://127.1:8080/mcp", "curl http://[::1]:9876/"):
            self.check(shell(cmd, "modeler"), "DENY")

    def test_stop_process_by_pid_is_fine(self):
        self.check(shell("Stop-Process 1234", tool="PowerShell"), "ALLOW")
        self.check(shell("Stop-Process -Id 1234 -Force", tool="PowerShell"), "ALLOW")
        self.check(shell("Stop-Process -Name godot", tool="PowerShell"), "DENY")


class GitOptions(Case):
    def test_add_everything_spellings(self):
        for cmd in ("git add -vA", "git add -v .", "git add ./", "git add -- .", "git add :/",
                    "git -C . add -A", "& git add -A", "git.exe add -A", "git add secrets/"):
            self.check(shell(cmd), "DENY")
        self.check(shell("git add src/a.py README.md"), "ALLOW")

    def test_force_push_and_skipped_hooks(self):
        for cmd in ("git push -uf o HEAD:main", "git push o +HEAD:main", "git commit -n -m x",
                    "git push --no-verify", "git commit -anm x"):
            self.check(shell(cmd), "DENY")
        self.check(shell('git commit -m "docs: never use --no-verify"'), "ALLOW")
        self.check(shell("git push --force-with-lease o main"), "ALLOW")

    def test_directory_add_then_commit_with_a_secret(self):
        root = make_project(git=True)
        os.makedirs(os.path.join(root, "cfg"))
        open(os.path.join(root, "cfg", ".env"), "w").close()
        self.check(shell("git add cfg && git commit -m x"), "DENY", root)


class GitContext(Case):
    """KILN-REV-04 (review 2026-10-21): the secrets check read the Kiln root's index, not the
    repository a `git -C <dir>` or `cd <dir> &&` commit acts on."""

    def repos(self):
        root = make_project(git=True)
        nested = os.path.join(root, "nested")
        subprocess.run(["git", "init", "-q", nested], capture_output=True)
        return root, nested

    def stage(self, repo, name):
        with open(os.path.join(repo, name), "w") as fh:
            fh.write("x")
        subprocess.run(["git", "-C", repo, "add", "-f", name], capture_output=True)

    def test_the_index_of_the_repository_the_commit_acts_on(self):
        root, nested = self.repos()
        self.stage(nested, ".env")                                   # the secret is nested
        for cmd in ("git -C nested commit -m x", "cd nested && git commit -m x",
                    "git -C . -C nested commit -m x",
                    f"git --git-dir={nested}/.git --work-tree={nested} commit -m x"):
            self.check(shell(cmd), "DENY", root)
        self.check(shell("git commit -m x"), "ALLOW", root)          # the parent index is clean

    def test_a_clean_nested_commit_does_not_inherit_the_parent_index(self):
        root, nested = self.repos()
        self.stage(root, ".env")
        self.stage(nested, "README.md")
        self.check(shell("git -C nested commit -m x"), "ALLOW", root)
        self.check(shell("git commit -m x"), "DENY", root)


class Roles(Case):
    def test_effort_copies_are_their_role(self):
        self.check(write("src/game.cs", "verifier-high"), "DENY")
        self.check(write(".claude/settings.json", "verifier-high"), "DENY")
        self.check(write("src/game.cs", "modeler-high"), "ALLOW")

    def test_builtin_agents_follow_the_producer_rule(self):
        self.check(write("manifest.md", "general-purpose"), "DENY")
        self.check(write("src/game.cs", "general-purpose"), "DENY")
        self.check(write("tasks/TASK-001.md", "general-purpose"), "ALLOW")

    def test_runtime_configs_are_protected(self):
        for path in (".opencode/plugins/kiln.js", ".github/copilot/settings.json",
                     ".gemini/settings.json", "opencode.json", ".codex/agents/kiln-modeler.toml"):
            self.check(write(path, "modeler"), "DENY")

    def test_a_role_cannot_create_a_task_for_itself(self):
        text = "# TASK-999\nrole: playtester\npaths: src/\n"
        root = make_project()
        os.makedirs(os.path.join(root, "tasks"))
        self.check(write("tasks/TASK-999.md", "playtester", text), "DENY", root)
        self.check(write("src/player.cs", "playtester"), "DENY", root)


class WindowsPaths(Case):
    @unittest.skipUnless(os.name == "nt", "Windows path spellings")
    def test_aliases_of_project_files(self):
        root = make_project()
        drive, rest = os.path.splitdrive(os.path.abspath(root))
        for path in ("\\\\?\\" + os.path.join(root, ".claude", "settings.json"),
                     f"\\\\localhost\\{drive[0]}$" + os.path.join(rest, ".claude", "settings.json"),
                     os.path.join(root, "manifest.md") + "::$DATA",
                     os.path.join(root, "scenes", "main.tscn") + ":hidden"):
            self.check(write(path, "modeler"), "DENY", root)
        cmd = f"Set-Content -LiteralPath '\\\\?\\{root}\\scenes\\main.tscn' -Value hacked"
        self.check(shell(cmd, "modeler", tool="PowerShell"), "DENY", root)


class ProbePaths(Case):
    def test_dotdot_leaves_the_probe_folders(self):
        mcp = {"tool_name": "mcp__godot-ai__script_create", "agent_type": "kiln:verifier",
               "agent_id": "a1", "tool_input": {"path": "res://tests/probes/../../scripts/p.gd",
                                                "content": "extends Node\n"}}
        self.check(mcp, "DENY")
        self.check(shell("godot --headless -s tests/../tools/build.gd"), "DENY")
        self.check(shell("godot --headless -s tests/probes/probe_x.gd"), "ALLOW")


class VendorServers(Case):
    def test_every_runtime_routes_paid_generators_to_the_guard(self):
        here = os.path.dirname(__file__)
        hooks = json.load(open(os.path.join(HOOKS, "hooks.json"), encoding="utf-8"))
        import re
        matchers = [e.get("matcher", "") for e in hooks["hooks"]["PreToolUse"]]
        for tool in ("mcp__meshy__text_to_3d", "mcp__claude_ai_ElevenLabs__speak",
                     "mcp__fal-ai__generate"):
            self.assertTrue(any(re.fullmatch(m, tool) for m in matchers), tool)
        codex = open(os.path.join(HOOKS, "codex-hooks.json"), encoding="utf-8").read()
        self.assertIn("mcp__.*", codex)
        sys.path.insert(0, HOOKS)
        import kiln_hooklib as k
        self.assertEqual(k.mcp_name("meshy_text_to_3d", "_"), "mcp__meshy__text_to_3d")
        self.assertEqual(k.mcp_name("fal-ai-generate", "-"), "mcp__fal-ai__generate")
        self.assertEqual(k.mcp_name("blender_get_objects", "_"), "mcp__blender__get_objects")
        js = open(os.path.join(here, "..", "plugins", "kiln", "opencode", "kiln.js"),
                  encoding="utf-8").read()
        for names in k.VENDOR_MCP.values():
            for name in names.split("|"):
                self.assertIn(name, js)

    def test_paid_generator_mcp_is_off_by_default(self):
        self.check({"tool_name": "mcp__meshy__text_to_3d", "tool_input": {}}, "DENY")
        root = make_project()
        payload = {"hook_event_name": "BeforeTool", "tool_name": "mcp_meshy_text_to_3d",
                   "tool_input": {}, "session_id": "s", "cwd": root}
        got, reason = run_guard(root, payload, args=("--runtime", "gemini"))
        self.assertEqual(got, "DENY", reason)


class CodexPatches(Case):
    def test_a_role_appends_its_handoff_with_apply_patch(self):
        root = make_project()
        os.makedirs(os.path.join(root, "tasks"))
        task = ("# TASK-001\nrole: modeler\npaths: art/\n\n## gates\n| role | verdict |\n"
                "|---|---|\n| verifier | |\n")
        with open(os.path.join(root, "tasks", "TASK-001.md"), "w", encoding="utf-8") as fh:
            fh.write(task)
        patch = ("*** Begin Patch\n*** Update File: tasks/TASK-001.md\n@@\n | verifier | |\n"
                 "+\n+## handoff modeler\n+done\n*** End Patch\n")
        data = {"tool_name": "apply_patch", "tool_input": {"command": patch},
                "agent_type": "kiln-modeler", "agent_id": "a1", "cwd": root}
        self.check(data, "ALLOW", root, args=("--runtime", "codex"))
        bad = patch.replace("+done", "+done\n").replace("@@\n | verifier | |",
                                                       "@@\n-paths: art/\n+paths: src/")
        data["tool_input"]["command"] = bad
        self.check(data, "DENY", root, args=("--runtime", "codex"))


class Manifests(Case):
    def test_subfolder_session_reads_a_bom_manifest(self):
        root = tempfile.mkdtemp(prefix="kiln-hunt-bom-")
        with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8-sig") as fh:
            fh.write("framework = kiln\nengine=godot\n")
        sub = os.path.join(root, "art")
        os.makedirs(sub)
        data = {**write(os.path.join(root, "scenes", "a.tscn"), "modeler"), "cwd": sub}
        self.check(data, "DENY", root, env_root=False)

    def test_utf16_manifest(self):
        root = tempfile.mkdtemp(prefix="kiln-hunt-u16-")
        with open(os.path.join(root, "manifest.md"), "w", encoding="utf-16") as fh:
            fh.write("framework=kiln\nengine=godot\n")
        self.check(write("scenes/a.tscn", "modeler"), "DENY", root)

    def test_a_ttl_that_is_not_a_number_does_not_open_the_editor(self):
        root = make_project(extra="editor_lock_ttl=10m\n")
        one = {"tool_name": "mcp__godot-ai__node_create", "tool_input": {},
               "agent_type": "kiln:modeler", "agent_id": "a1", "session_id": "s"}
        two = dict(one, agent_type="kiln:animator", agent_id="a2")
        self.check(one, "ALLOW", root)
        self.check(two, "DENY", root)


def mcp(tool, role=None, **tool_input):
    data = {"tool_name": tool, "tool_input": tool_input, "session_id": "s"}
    if role:
        data.update(agent_type=f"kiln:{role}", agent_id="a-" + role)
    return data


class UnityUnreal(Case):
    """Block 4 of the bug hunt: theoretical checks against MCP for Unity v10.3.0, Epic's UE 5.8
    server and the ChiR24 fallback server."""

    def test_unreal_fallback_server_reads_the_action(self):
        root = make_project("unreal")
        self.check(mcp("mcp__unreal__inspect", "qa-feel", action="get_property"), "ALLOW", root)
        self.check(mcp("mcp__unreal__control_editor", "qa-feel", action="screenshot"), "ALLOW",
                   root)
        self.check(mcp("mcp__unreal__system_control", "qa-performance", action="console_command",
                       command="stat unit"), "ALLOW", root)
        self.check(mcp("mcp__unreal__control_editor", "qa-feel", action="set_property"), "DENY",
                   root)
        self.check(mcp("mcp__unreal__build_environment", "level-designer",
                       action="create_procedural_terrain"), "DENY", root)

    def test_unreal_read_names_that_change_things(self):
        root = make_project("unreal")
        data = mcp("mcp__unreal__call_tool", "qa-feel", toolset_name="SequencerTools",
                   tool_name="find_or_create_track", arguments={})
        self.check(data, "DENY", root)

    def test_play_needs_a_slot_in_every_engine(self):
        for engine, data in (("unreal", mcp("mcp__unreal__call_tool", "playtester",
                                            toolset_name="EditorAppToolset", tool_name="StartPIE",
                                            arguments={})),
                             ("unity", mcp("mcp__unity__execute_menu_item", "playtester",
                                           action="execute", menu_path="Edit/Play"))):
            self.check(data, "DENY", make_project(engine, "on_screen=slot\n"))

    def test_unity_tool_groups_and_probe_code(self):
        root = make_project("unity")
        self.check(mcp("mcp__unity__manage_tools", "qa-feel", action="activate", group="testing"),
                   "ALLOW", root)
        self.check(mcp("mcp__unity__manage_tools", "qa-feel", action="activate", group="asset_gen"),
                   "DENY", root)
        probe = "// kiln:probe\nreturn Kiln.Probes.KilnProbe.Find().Done;"
        self.check(mcp("mcp__unity__execute_code", "qa-feel", action="execute", code=probe),
                   "ALLOW", root)
        save = ("// kiln:probe\nvar g = GameObject.Find(\"x\"); Object.DestroyImmediate(g);\n"
                "UnityEditor.SceneManagement.EditorSceneManager.SaveOpenScenes(); return 1;")
        self.check(mcp("mcp__unity__execute_code", "qa-feel", action="execute", code=save),
                   "DENY", root)
        bulk = "for (int i = 0; i < 500; i++) { var g = new GameObject(\"p\"); }\nreturn 0;"
        self.check(mcp("mcp__unity__execute_code", "level-designer", action="execute", code=bulk),
                   "DENY", root)

    def test_unity_editor_assets_and_unreal_configs_are_protected(self):
        root = make_project("unity")
        for path in ("Assets/A/walk.anim", "Assets/S/water.shadergraph", "Assets/V/rain.vfx",
                     "Assets/UI/atlas.spriteatlas", "Assets/L/day.lighting"):
            self.check(write(path, "animator"), "DENY", root)
        root = make_project("unreal")
        self.check(write("Plugins/Foo/Config/DefaultFoo.ini", "gameplay-dev"), "DENY", root)
        self.check(write("Game/Config/DefaultEngine.ini", "gameplay-dev"), "DENY", root)

    def test_headless_editor_scripts(self):
        for engine, cmd in (
                ("unreal", 'UnrealEditor-Cmd.exe P.uproject -ExecCmds="py Content/Python/gen.py;quit"'),
                ("unreal", "UnrealEditor-Cmd.exe P.uproject -run=ResavePackages"),
                ("unity", "Unity.exe -batchmode -executeMethod LevelBuilder.GenerateTown")):
            self.check(shell(cmd), "DENY", make_project(engine))
        self.check(shell("Unity.exe -batchmode -quit -executeMethod KilnRelease.KilnBuild.Build"),
                   "ALLOW", make_project("unity"))


class EditorQueue(unittest.TestCase):
    def test_stop_and_guard_share_the_lock(self):
        text = open(os.path.join(HOOKS, "stop.py"), encoding="utf-8").read()
        start = text.index("def leave_queues")
        body = text[start:text.index("\ndef ", start + 10)]
        self.assertIn('"locks.json"', body)


if __name__ == "__main__":
    unittest.main()
