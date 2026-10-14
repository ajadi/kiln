"""Regression tests for plugins/kiln/hooks/guard.py.

Run: python -m unittest discover -s tests -v   (from the repo root; stdlib only)
Each case pipes a PreToolUse payload into guard.py with CLAUDE_PROJECT_DIR pointing at a
throwaway project whose manifest selects the engine.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

GUARD = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "hooks", "guard.py")


def make_project(engine="godot", extra=""):
    root = tempfile.mkdtemp(prefix=f"kiln-{engine}-")
    with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write(f"project_name=t\nframework=kiln\nengine={engine}\n{extra}")
    return root


def run_guard(root, payload):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
    out = subprocess.run([sys.executable, "-B", GUARD], input=json.dumps(payload), env=env,
                         capture_output=True, text=True, timeout=20).stdout.strip()
    if not out:
        return "ALLOW", ""
    decision = json.loads(out).get("hookSpecificOutput", {})
    return decision.get("permissionDecision", "?").upper(), decision.get(
        "permissionDecisionReason", "")


def write(path, role=None, content=None, agent="a1"):
    data = {"tool_name": "Write", "tool_input": {"file_path": path, "content": content or ""}}
    if role:
        data.update(agent_type=f"kiln:{role}", agent_id=agent)
    return data


def shell(command):
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def mcp(tool, role=None, agent="a1", **tool_input):
    data = {"tool_name": tool, "tool_input": tool_input}
    if role:
        data.update(agent_type=f"kiln:{role}", agent_id=agent)
    return data


def unreal(name, role=None, agent="a1", **arguments):
    return mcp("mcp__unreal__call_tool", role, agent, toolset_name="T", tool_name=name,
               arguments=arguments)


class GuardCase(unittest.TestCase):
    engine = "godot"

    def check(self, payload, expected, root=None):
        got, reason = run_guard(root or make_project(self.engine), payload)
        self.assertEqual(got, expected, f"{payload} -> {reason}")


class GodotTests(GuardCase):
    engine = "godot"

    def test_files(self):
        self.check(write("scenes/a.tscn"), "DENY")
        self.check(write("scenes/a.tscn", "level-designer"), "DENY")
        self.check(write("src/player.gd", "gameplay-dev"), "DENY")
        self.check(write("assets/m.tres", "fx-artist"), "DENY")
        self.check(write("art/mech.blend", "modeler"), "DENY")
        self.check(write("tests/probes/p.gd", "qa-feel"), "ALLOW")

    def test_orchestrator_and_zones(self):
        self.check(write("tasks/TASK-001.md"), "ALLOW")
        self.check(write("production/PLAYTESTS.md"), "ALLOW")
        self.check(write("research/style.md"), "ALLOW")
        self.check(write(".codex/config.toml"), "ALLOW")
        self.check(write("tools/audio/gen.py"), "DENY")
        self.check(write("tools/audio/gen.py", "sound-designer"), "ALLOW")
        self.check(write("tools/x.py", "qa-feel"), "DENY")
        self.check(write("playtests/run.md", "qa-feel"), "ALLOW")
        self.check(write("design/tech/fog-physics-expert.md", "physics-expert"), "ALLOW")
        self.check(write("src/x.py", "physics-expert"), "DENY")
        self.check(write("design/ART_BIBLE.md", "art-director"), "ALLOW")
        self.check(write(".claude/settings.json", "modeler"), "DENY")
        self.check(write("src/x.py", "general-purpose"), "ALLOW")

    def test_shell(self):
        self.check(shell("blender -b scene.blend -P build.py"), "DENY")
        self.check(shell('python -c "import bpy"'), "DENY")
        self.check(shell("godot --headless --script tools/gen.gd"), "DENY")
        self.check(shell("godot --version"), "ALLOW")
        self.check(shell("curl http://127.0.0.1:9876/"), "DENY")
        self.check(shell("git add -A"), "DENY")
        self.check(shell("git add src/a.gd tasks/TASK-001.md"), "ALLOW")
        self.check(shell("git push --force origin main"), "DENY")
        self.check(shell("git push --force-with-lease"), "ALLOW")
        self.check(shell("git commit --no-verify -m x"), "DENY")

    def test_bpy_scripts_run_vs_read(self):
        # Live run: the producer's `head -40 parts.py` was denied as if it ran the script.
        root = make_project(self.engine)
        os.makedirs(os.path.join(root, "art", "src"))
        for rel, body in (("parts.py", "import bpy\n"), ("art/src/review.py", "from bpy import ops\n"),
                          ("tool.py", "import json\n")):
            with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
                fh.write(body)
        for cmd in ("head -40 parts.py", 'grep -n "import bpy" parts.py art/src/review.py',
                    "cat art/src/review.py | head", "python tool.py --in parts.py",
                    "cd art/src && wc -l review.py",
                    # live run: a heredoc editing a markdown table that names parts.py
                    "python - <<'EOF'\ns = '| parts.py | J(neck) | 0.2 |'\nprint(s)\nEOF",
                    "cat > notes.md <<EOF\n| parts.py | x |\nEOF\nhead notes.md"):
            self.check(shell(cmd), "ALLOW", root)
        for cmd in ("python parts.py", "python3 -B -X utf8 parts.py", "py -3 parts.py",
                    "cd art/src && python review.py", r"python D:\x\..\missing.py; python parts.py",
                    "echo 'import bpy' | python", "python - <<'EOF'\nimport bpy\nEOF"):
            self.check(shell(cmd), "DENY", root)

    def test_agent_model_and_effort_from_the_manifest(self):
        # g2 rows 11/153: the user decided "agents run sonnet, effort medium"; ~12 agents ran on
        # Opus anyway and the session limit killed three of them.
        root = make_project("godot", "agent_model=sonnet\nagent_effort=medium\n")
        os.makedirs(os.path.join(root, "tasks"))
        with open(os.path.join(root, "tasks", "TASK-017.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-017\n## spec\nrole: gameplay-dev\ncomplexity: high\n")
        with open(os.path.join(root, "tasks", "TASK-018.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-018\n## spec\nrole: modeler\neffort: high\n")

        def agent(**extra):
            return {"tool_name": "Agent", "tool_input": {
                "subagent_type": "kiln:modeler", "description": "d",
                "prompt": "Task file tasks/TASK-018.md", **extra}}

        env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
        out = subprocess.run([sys.executable, "-B", GUARD], input=json.dumps(agent()), env=env,
                             capture_output=True, text=True, timeout=20).stdout
        spec = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(spec["permissionDecision"], "allow")
        self.assertEqual(spec["updatedInput"]["model"], "sonnet")
        self.assertEqual(spec["updatedInput"]["effort"], "high")       # the task's own line
        self.assertEqual(spec["updatedInput"]["prompt"], "Task file tasks/TASK-018.md")
        self.check(agent(model="opus"), "DENY", root)
        self.check(agent(model="sonnet", effort="max"), "DENY", root)
        ok = agent(model="opus", effort="medium")
        ok["tool_input"]["prompt"] = "Task file tasks/TASK-017.md (complexity high)"
        self.check(ok, "ALLOW", root)
        self.check(agent(model="sonnet", effort="high"), "ALLOW", root)
        # no manifest keys: nothing enforced
        self.check(agent(model="opus"), "ALLOW")

    def test_shared_memory_files_are_every_roles(self):
        # g2 rows 3/65/79/96: the protocol says anyone appends decisions/known issues and
        # whoever changes them writes registries/pipeline, but zones denied it.
        for role in ("art-director", "tech-designer", "anatomy-expert", "verifier", "playtester",
                     "qa-audio"):
            for rel in ("memory/decisions.md", "memory/known-issues.md", "memory/registries.md",
                        "memory/pipeline.md", "memory/kiln_reports.md"):
                self.check(write(rel, role), "ALLOW")
        self.check(write("research/style.md", "art-director"), "ALLOW")
        self.check(write("production/SCOPE.md", "tech-designer"), "ALLOW")
        self.check(write("memory/out-of-scope/x.md", "qa-feel"), "DENY")
        self.check(write("src/x.gd", "art-director"), "DENY")

    def test_notes_and_state_paths_from_the_manifest(self):
        # g2 row 17: a user-requested notes file at the root was denied to the main session.
        self.check(write("kiln_reports.md"), "DENY")
        root = make_project("godot", "notes_files=kiln_reports.md\nstate_paths=tools/infra/**\n")
        self.check(write("kiln_reports.md"), "ALLOW", root)
        self.check(write("kiln_reports.md", "playtester"), "ALLOW", root)
        self.check(write("tools/infra/sync.sh"), "ALLOW", root)
        self.check(write("tools/game/gen.py"), "DENY", root)

    def test_roles_write_their_tasks_paths(self):
        # g2 row 130: the producer asked the art-director for production/props/; the zone said no.
        root = make_project("godot")
        os.makedirs(os.path.join(root, "tasks", "archive"))
        with open(os.path.join(root, "tasks", "TASK-032.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-032: props prep\n## spec\ntype: art\nrole: modeler, art-director\n"
                     "paths: `production/props/`, art/source/props/**, tools/props/prep.py\n")
        with open(os.path.join(root, "tasks", "archive", "TASK-001.md"), "w",
                  encoding="utf-8") as fh:
            fh.write("# TASK-001\n## spec\nrole: art-director\npaths: src/\n")
        self.check(write("production/props/list.md", "art-director"), "ALLOW", root)
        self.check(write("tools/props/prep.py", "art-director"), "ALLOW", root)
        self.check(write("tools/other.py", "art-director"), "DENY", root)
        self.check(write("src/a.py", "art-director"), "DENY", root)       # archived task
        self.check(write("tools/props/prep.py", "qa-feel"), "DENY", root)  # not its task

    def test_roles_cannot_rewrite_the_spec_or_others_verdicts(self):
        # 0.7.0 review: a role named in a task's role line may write its paths, so a role that
        # edits the role/paths lines widens its own zone; a builder could fill an acceptor's
        # verdict cell.
        root = make_project("godot")
        os.makedirs(os.path.join(root, "tasks"))
        path = os.path.join(root, "tasks", "TASK-017.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# TASK-017\n## spec\ntype: gameplay\nrole: gameplay-dev\npaths: src/player/\n"
                     "touches: movement\n## gates\n| role | why | verdict |\n|---|---|---|\n"
                     "| qa-feel | movement | |\n| verifier | close | |\n")

        def edit(role, old, new):
            return {"tool_name": "Edit", "agent_type": f"kiln:{role}", "agent_id": "x",
                    "tool_input": {"file_path": path, "old_string": old, "new_string": new}}

        self.check(edit("qa-feel", "role: gameplay-dev", "role: gameplay-dev, qa-feel"), "DENY",
                   root)
        self.check(edit("qa-feel", "paths: src/player/", "paths: src/"), "DENY", root)
        self.check(edit("gameplay-dev", "touches: movement", "touches: none"), "DENY", root)
        self.check(edit("gameplay-dev", "| qa-feel | movement | |",
                        "| qa-feel | movement | PASS |"), "DENY", root)
        self.check(edit("qa-feel", "| qa-feel | movement | |", "| qa-feel | movement | FAIL |"),
                   "ALLOW", root)
        self.check(edit("qa-feel", "| verifier | close | |",
                        "| verifier | close | |\n## acceptance: qa-feel\nverdict: FAIL"), "ALLOW",
                   root)
        main = edit("qa-feel", "role: gameplay-dev", "role: gameplay-dev, qa-feel")
        del main["agent_type"], main["agent_id"]
        self.check(main, "ALLOW", root)                     # the producer plans

    def test_on_screen_slot_holds_windowed_runs(self):
        # g2 rows 7/19 + 0.7.0 review: on_screen=slot was only prose; agents still took the screen.
        root = make_project("godot", "on_screen=slot\n")
        run_game = mcp("mcp__godot-ai__project_run", "playtester")
        windowed = shell("godot --path . -s res://tests/autoplay/run_full.gd -- --seed 1")
        self.check(run_game, "DENY", root)
        self.check(windowed, "DENY", root)
        self.check(shell("godot --headless --path . -s res://tests/probes/p.gd"), "ALLOW", root)
        self.check(shell("godot --editor --path ."), "ALLOW", root)
        os.makedirs(os.path.join(root, ".kiln"), exist_ok=True)
        with open(os.path.join(root, ".kiln", "slot"), "w", encoding="utf-8") as fh:
            fh.write("until=2099-01-01T00:00\n")
        self.check(run_game, "ALLOW", root)
        with open(os.path.join(root, ".kiln", "slot"), "w", encoding="utf-8") as fh:
            fh.write("until=2000-01-01T00:00\n")             # the slot is over
        self.check(run_game, "DENY", root)
        os.remove(os.path.join(root, ".kiln", "slot"))
        open(os.path.join(root, ".kiln", "away"), "w").close()
        self.check(windowed, "ALLOW", root)
        self.check(mcp("mcp__godot-ai__project_run", "playtester"), "ALLOW")   # default anytime

    def test_shell_writes_follow_the_file_rules(self):
        # 0.7.0 review: Write/Edit were guarded, `cat > file` was not.
        root = make_project("godot")
        os.makedirs(os.path.join(root, "tasks"))
        with open(os.path.join(root, "tasks", "TASK-1.md"), "w", encoding="utf-8") as fh:
            fh.write("# TASK-1\n## spec\nrole: gameplay-dev\npaths: src/\n")

        def sh(cmd, role=None):
            data = shell(cmd)
            if role:
                data.update(agent_type=f"kiln:{role}", agent_id="r")
            return data

        for cmd, role in (
                ("cat > tests/probes/probe_qa_cam.gd <<'EOF'\nextends Node\nEOF", "gameplay-dev"),
                ("echo x > src/a.py", "qa-feel"),
                ("sed -i s/a/b/ src/x.py", "qa-feel"),
                ("python gen.py | tee -a src/log.py", "qa-feel"),
                ("Set-Content -Path src/x.py -Value 1", "qa-feel"),
                ("cp notes.md src/notes.py", "qa-feel"),
                ("echo x > tasks/TASK-1.md", "qa-feel"),
                ("echo [gd_scene] > scenes/a.tscn", None)):
            self.check(sh(cmd, role), "DENY", root)
        for cmd, role in (
                ("echo '## acceptance: qa-feel' >> tasks/TASK-1.md", "qa-feel"),
                ("python probe.py > .kiln/tmp/out.json 2>/dev/null", "qa-feel"),
                ("cp a.json production/captures/T1/", "qa-feel"),
                ("git log > .kiln/tmp/log.txt", None),
                ("godot --version > NUL", "qa-feel"),
                ("Get-ChildItem | Out-Null", "qa-feel"),
                ("echo x > src/a.py", "gameplay-dev")):
            self.check(sh(cmd, role), "ALLOW", root)

    def test_acceptor_probes_belong_to_acceptors(self):
        # g2 row 55: a builder rewrote qa-feel's probe rows into tautologies.
        self.check(write("tests/probes/probe_qa_cam.gd", "qa-feel"), "ALLOW")
        self.check(write("tests/probes/probe_qa_cam.gd", "gameplay-dev"), "DENY")
        self.check(write("tests/probes/probe_cam_dev.gd", "gameplay-dev"), "ALLOW")
        self.check(mcp("mcp__godot-ai__script_patch", "gameplay-dev",
                       path="res://tests/probes/probe_qa_cam.gd", new_text="x"), "DENY")
        self.check(mcp("mcp__godot-ai__script_patch", "qa-physics",
                       path="res://tests/probes/probe_qa_cam.gd", new_text="x"), "ALLOW")

    def test_import_options_route(self):
        got, reason = run_guard(make_project("godot"), write("assets/a.ogg.import", "composer"))
        self.assertEqual(got, "DENY")
        self.assertIn("import_edit.py", reason)

    def test_project_godot_bootstrap(self):
        # g2 row 2: setup's one sanctioned project.godot write was denied once manifest existed.
        root = make_project("godot")
        self.check(write(os.path.join(root, "project.godot"), content="config_version=5\n"),
                   "ALLOW", root)
        self.check(write(os.path.join(root, ".godot", "editor", "project_metadata.cfg")),
                   "ALLOW", root)
        with open(os.path.join(root, "project.godot"), "w", encoding="utf-8") as fh:
            fh.write("config_version=5\n")
        self.check(write(os.path.join(root, "project.godot"), content="x"), "DENY", root)
        self.check(write(os.path.join(root, "project.godot"), "gameplay-dev"), "DENY", root)

    def test_bpy_text_written_to_a_file_is_not_run(self):
        # g2 rows 38/67: a heredoc that only wrote a recipe or a markdown row naming bpy was
        # denied because the same command also ran python.
        root = make_project(self.engine)
        with open(os.path.join(root, "tool.py"), "w", encoding="utf-8") as fh:
            fh.write("import json\n")
        for cmd in ("cat > art/recipe.py <<'EOF'\nimport bpy\nbpy.ops.x()\nEOF\npython tool.py",
                    "cat >> memory/kiln_reports.md <<EOF\n| 67 | guard | import bpy in text |\n"
                    "EOF\npython tool.py",
                    "python - <<'EOF'\nrow = '| 67 | text names import bpy |'\nprint(row)\nEOF"):
            self.check(shell(cmd), "ALLOW", root)
        for cmd in ("python - <<'EOF'\nimport bpy\nEOF", "echo 'import bpy' | python",
                    'python -c "import bpy; bpy.ops.x()"',
                    "cat > a.md <<EOF\nx\nEOF\npython -c 'from bpy import ops'"):
            self.check(shell(cmd), "DENY", root)

    def test_generator_words_in_reads_are_not_runs(self):
        # g2 row 33: reading the image-to-model skill and a hardware check were denied as
        # generator runs while model_generators=off.
        for cmd in ("ls ~/.claude/plugins/kiln/skills/image-to-model",
                    'grep -n "trellis\\|hunyuan3d" skills/image-to-model/SKILL.md',
                    "cat skills/music/SKILL.md | grep -i musicgen",
                    "Get-Content skills/image-to-model/SKILL.md | Select-String TripoSR",
                    "Get-CimInstance Win32_ComputerSystem; vswhere -latest -property "
                    "installationPath; echo $env:CUDA_PATH"):
            self.check(shell(cmd), "ALLOW")
        self.check(shell("python run.py --model trellis2 photo.png"), "DENY")
        self.check(shell("cat cfg.json | python -m musicgen --prompt x"), "DENY")

    def test_headless_godot_probes_and_parse_checks(self):
        # g2 rows 26/75/96/151: probes and --check-only had to go through a wrapper script.
        for cmd in ("godot --headless -s res://tests/probes/p.gd | grep FAIL",
                    "godot --headless -s res://tests/probes/p.gd | tail -5",
                    "Godot_v4.7.2-stable_win64_console.exe --headless --fixed-fps 60 --script "
                    "tests/probes/probe_edges.gd",
                    "godot --headless --script res://.kiln/tmp/scratch.gd",
                    "godot --headless --check-only -s src/player.gd"):
            self.check(shell(cmd), "ALLOW")
        for cmd in ("godot --headless --script tools/gen.gd",
                    "godot --headless -s res://src/build_level.gd | tail -5"):
            self.check(shell(cmd), "DENY")

    def test_no_kill_by_image_name(self):
        # g2 rows 39/50: taskkill /IM python.exe killed every MCP server; /IM on the console
        # launcher killed the editor.
        for cmd in ("taskkill /IM python.exe /F", "taskkill /F /IM Godot_v4.7.2_console.exe",
                    "pkill python", "killall godot", "Stop-Process -Name python -Force",
                    "Get-Process python | Stop-Process"):
            self.check(shell(cmd), "DENY")
        for cmd in ("taskkill /PID 24948 /T /F", "Stop-Process -Id 24948", "kill 24948",
                    "tasklist /FI \"IMAGENAME eq python.exe\""):
            self.check(shell(cmd), "ALLOW")

    def test_scene_first(self):
        code = "func _ready():\n    var m = MeshInstance3D.new()\n"
        self.check(mcp("mcp__godot-ai__script_create", "gameplay-dev", path="res://src/a.gd",
                       content=code), "DENY")
        marked = code.replace(".new()", ".new()  # kiln:runtime-node pooled debris")
        self.check(mcp("mcp__godot-ai__script_create", "gameplay-dev", path="res://src/a.gd",
                       content=marked), "ALLOW")
        self.check(mcp("mcp__godot-ai__script_create", "gameplay-dev", path="res://tests/p.gd",
                       content=code), "ALLOW")
        self.check(mcp("mcp__godot-ai__script_create", "qa-feel",
                       path="res://tests/probes/p.gd", content=code), "ALLOW")
        self.check(mcp("mcp__godot-ai__script_create", "qa-feel", path="res://src/p.gd",
                       content="extends Node\n"), "DENY")
        self.check(mcp("mcp__godot-ai__script_create", "gameplay-dev", path="res://src/a.gd",
                       content="var q = PhysicsRayQueryParameters3D.new()\n"), "ALLOW")

    def test_mcp_rules(self):
        self.check(mcp("mcp__blender__execute_blender_code", "art-director", code="bpy.ops.x()"),
                   "DENY")
        self.check(mcp("mcp__blender__execute_blender_code", "art-director",
                       code="# Kiln review view\nimport bpy\n"), "ALLOW")
        self.check(mcp("mcp__blender__render_for_cli", "modeler"), "DENY")
        self.check(mcp("mcp__godot-ai__client_manage", "gameplay-dev"), "DENY")

    def test_read_only_roles(self):
        self.check(mcp("mcp__godot-ai__project_run", "qa-feel"), "ALLOW")
        self.check(mcp("mcp__godot-ai__game_manage", "qa-feel", op="input_action",
                       params={"action": "jump"}), "ALLOW")
        self.check(mcp("mcp__godot-ai__project_manage", "qa-feel", op="settings_set"), "DENY")
        self.check(mcp("mcp__godot-ai__script_manage", "qa-feel", op="detach"), "DENY")
        self.check(mcp("mcp__godot-ai__filesystem_manage", "qa-feel", op="remove",
                       params={"path": "res://scenes/a.tscn"}), "DENY")
        self.check(mcp("mcp__godot-ai__filesystem_manage", "qa-feel", op="write_text",
                       params={"path": "res://tests/probes/feel.gd", "content": "x"}), "ALLOW")
        self.check(mcp("mcp__godot-ai__filesystem_manage", "qa-feel", op="write_text",
                       params={"path": "res://src/player.gd", "content": "x"}), "DENY")
        self.check(mcp("mcp__godot-ai__node_create", "playtester"), "DENY")
        self.check(mcp("mcp__godot-ai__node_create", "level-designer"), "ALLOW")

    def test_experts_read_only_in_editors(self):
        self.check(mcp("mcp__godot-ai__project_manage", "physics-expert", op="settings_set"),
                   "DENY")
        self.check(mcp("mcp__godot-ai__scene_get_hierarchy", "tech-designer"), "ALLOW")
        self.check(mcp("mcp__godot-ai__filesystem_manage", "creature-expert", op="remove",
                       params={"path": "res://a.gd"}), "DENY")

    def test_text_write_bypass(self):
        self.check(mcp("mcp__godot-ai__filesystem_manage", "gameplay-dev", op="write_text",
                       params={"path": "res://scenes/a.tscn", "content": "[gd_scene]"}), "DENY")
        self.check(mcp("mcp__godot-ai__filesystem_manage", "gameplay-dev", op="write_text",
                       params={"path": "res://src/a.gd", "content": "extends Node"}), "DENY")
        self.check(mcp("mcp__godot-ai__filesystem_manage", "gameplay-dev", op="write_text",
                       params={"path": "res://data/waves.json", "content": "{}"}), "ALLOW")
        root = make_project("godot", "godot_files_via_mcp=scenes,resources\n")
        self.check(write("src/a.gd", "gameplay-dev", "var m = MeshInstance3D.new()"), "DENY",
                   root)

    def test_generator_policies(self):
        self.check(shell("python run.py --model trellis2 photo.png"), "DENY")
        self.check(shell("curl https://api.meshy.ai/v2/image-to-3d"), "DENY")
        self.check(shell("python -m musicgen --prompt x"), "DENY")
        root = make_project("godot", "model_generators=local\n")
        self.check(shell("python run.py --model trellis2 photo.png"), "ALLOW", root)
        self.check(shell("curl https://api.tripo3d.ai/v2/task"), "DENY", root)

    def test_user_gates_and_cli(self):
        self.check({**shell("python pipeline.py tick 'User locked the style' --by user"),
                    "agent_type": "kiln:qa-feel", "agent_id": "q"}, "DENY")
        self.check(shell("python pipeline.py tick 'User locked the style' --by user"), "ALLOW")
        self.check(shell("codex mcp add godot-ai -- godot-ai attach"), "ALLOW")
        self.check(shell("python mcp_check.py verify --available t.txt --probe blender=ok "
                         "--probe godot-ai=ok"), "ALLOW")
        self.check(shell("python mcp_check.py verify --probe godot-ai=ok; godot-ai attach"),
                   "DENY")
        # live run: a gate note naming the servers was denied as a server call
        self.check(shell('python pipeline.py tick "/kiln:doctor passed" --by agent --note '
                         '"blender+godot-ai connected; blender -b not used"'), "ALLOW")
        self.check(shell("godot-ai --version"), "ALLOW")
        self.check(shell("uvx godot-ai attach --port 8000"), "DENY")
        self.check(shell('"C:\\Program Files\\Blender\\blender.exe" --background x.blend'), "DENY")
        self.check(shell("blmcp serve"), "DENY")

    def test_editor_lock(self):
        root = make_project("godot")
        self.check(mcp("mcp__blender__execute_blender_code", "modeler", "m1", code="x=1"),
                   "ALLOW", root)
        self.check(mcp("mcp__blender__execute_blender_code", "animator", "m2", code="x=1"),
                   "DENY", root)
        self.check(mcp("mcp__blender__get_scene_info", "animator", "m2"), "ALLOW", root)

    def test_editor_queue_and_lease(self):
        # g2 row 6: a modeler's short import step retried for 40 min behind a level designer
        # holding the editor for an hour.
        import time
        root = make_project("godot", "editor_lease_s=900\n")
        kdir = os.path.join(root, ".kiln")
        os.makedirs(kdir, exist_ok=True)

        def call(agent, role):
            return dict(mcp("mcp__blender__execute_blender_code", role, agent, code="x=1"),
                        session_id="s")

        def hold(agent, role, since):
            with open(os.path.join(kdir, "locks.json"), "w", encoding="utf-8") as fh:
                json.dump({"blender": {"owner": agent, "role": role, "session": "s",
                                       "ts": time.time(), "since": since}}, fh)

        def queue():
            with open(os.path.join(kdir, "queue.json"), encoding="utf-8") as fh:
                return [w["owner"] for w in json.load(fh).get("blender", [])]

        hold("lvl", "level-designer", time.time() - 60)
        got, reason = run_guard(root, call("mod", "modeler"))
        self.assertEqual(got, "DENY")
        self.assertIn("#1 in the queue", reason)
        self.assertEqual(queue(), ["mod"])
        self.check(call("lvl", "level-designer"), "ALLOW", root)   # lease not over yet
        hold("lvl", "level-designer", time.time() - 1000)          # held for 16 min
        got, reason = run_guard(root, call("lvl", "level-designer"))
        self.assertEqual(got, "DENY")
        self.assertIn("lease", reason)
        got, _ = run_guard(root, call("fx", "fx-artist"))          # free, but mod is first
        self.assertEqual(got, "DENY")
        self.check(call("mod", "modeler"), "ALLOW", root)
        self.assertEqual(queue(), ["lvl", "fx"])

    def test_editor_lock_goes_to_exactly_one_of_parallel_agents(self):
        root = make_project("godot")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
        procs = []
        for i in range(10):
            p = subprocess.Popen([sys.executable, "-B", GUARD], env=env, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True)
            p.stdin.write(json.dumps(dict(mcp("mcp__blender__execute_blender_code", "modeler",
                                              f"m{i}", code="x=1"), session_id="s")))
            p.stdin.close()
            procs.append(p)
        outs = [p.stdout.read() for p in procs]
        for p in procs:
            p.wait(timeout=60)
        allowed = [o for o in outs if '"deny"' not in o]
        self.assertEqual(len(allowed), 1, outs)

    def test_editor_lock_of_a_killed_session(self):
        # Live run: a killed headless session left its modeler's lock; the next session's
        # modeler was denied for the full TTL.
        import time
        root = make_project("godot")
        os.makedirs(os.path.join(root, ".kiln"), exist_ok=True)

        def lock(session, age):
            with open(os.path.join(root, ".kiln", "locks.json"), "w", encoding="utf-8") as fh:
                json.dump({"blender": {"owner": "old", "role": "modeler", "session": session,
                                       "ts": time.time() - age, "since": time.time() - age}}, fh)

        def call(agent):
            return dict(mcp("mcp__blender__execute_blender_code", "modeler", agent, code="x=1"),
                        session_id="s2")

        lock("s1", 200)  # another session, silent for 200 s → stale
        self.check(call("new"), "ALLOW", root)
        lock("s2", 200)  # a live agent of this session thinking for 200 s → still held
        self.check(call("new"), "DENY", root)
        lock("s1", 30)   # another session driving right now → held
        self.check(call("new"), "DENY", root)

    def test_main_session_hands_the_editor_to_its_agent(self):
        # Live autopilot: the producer's doctor probe locked Blender; its animator was denied.
        root = make_project("godot")
        main = dict(mcp("mcp__blender__execute_blender_code", code="x=1"), session_id="s")
        agent = dict(mcp("mcp__blender__execute_blender_code", "animator", "a1", code="x=1"),
                     session_id="s")
        self.check(main, "ALLOW", root)
        self.check(agent, "ALLOW", root)   # takes over from its producer
        self.check(main, "DENY", root)     # the producer may not drive it back while it works
        other = dict(agent, session_id="other", agent_id="b2")
        self.check(other, "DENY", root)    # another session's agent stays out

    def test_denials_are_recorded_for_the_retro(self):
        root = make_project("godot")
        self.check(shell("git add -A"), "DENY", root)
        self.check(shell("git status"), "ALLOW", root)
        with open(os.path.join(root, ".kiln", "denials.jsonl"), encoding="utf-8") as fh:
            entries = [json.loads(line) for line in fh]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["tool"], "Bash")
        self.assertEqual(entries[0]["input"], "git add -A")
        self.assertIn("Stage specific files", entries[0]["reason"])

    def test_not_a_kiln_project(self):
        root = tempfile.mkdtemp(prefix="plain-")
        self.check(write("scenes/a.tscn"), "ALLOW", root)
        self.check(shell("git add -A"), "ALLOW", root)


class UnityTests(GuardCase):
    engine = "unity"

    def test_files(self):
        self.check(write("Assets/_Project/Scenes/L1.unity", "gameplay-dev"), "DENY")
        self.check(write("ProjectSettings/TagManager.asset", "gameplay-dev"), "DENY")
        self.check(write("scenes/a.tscn", "gameplay-dev"), "ALLOW")

    def test_scene_first_csharp(self):
        path = "Assets/_Project/Scripts/Runtime/Mech.cs"
        self.check(write(path, "gameplay-dev", 'void Start(){ var g = new GameObject("x"); }'),
                   "DENY")
        self.check(write(path, "gameplay-dev", "var b = Instantiate(prefab);"), "ALLOW")
        self.check(write("Assets/_Project/Scripts/Editor/Tool.cs", "gameplay-dev",
                         'new GameObject("x");'), "ALLOW")
        self.check(mcp("mcp__unity__create_script", "gameplay-dev", path=path,
                       contents="gameObject.AddComponent<MeshRenderer>();"), "DENY")

    def test_read_only_roles(self):
        self.check(mcp("mcp__unity__manage_scene", "qa-feel", action="get_hierarchy"), "ALLOW")
        self.check(mcp("mcp__unity__manage_gameobject", "qa-feel", action="delete"), "DENY")
        self.check(mcp("mcp__unity__execute_code", "qa-feel", code="// kiln:probe\nreturn 1;"),
                   "ALLOW")
        self.check(mcp("mcp__unity__execute_code", "qa-feel", code="Object.Destroy(x);"), "DENY")
        self.check(mcp("mcp__unity__manage_gameobject", "level-designer", action="create"),
                   "ALLOW")

    def test_source_verified_cases(self):
        # names and parameters from MCP for Unity v10.3.0 sources
        self.check(mcp("mcp__unity__manage_scene", "qa-feel", action="validate"), "ALLOW")
        self.check(mcp("mcp__unity__manage_scene", "qa-feel", action="validate",
                       auto_repair=True), "DENY")
        self.check(mcp("mcp__unity__manage_physics", "qa-physics", action="overlap"), "ALLOW")
        self.check(mcp("mcp__unity__manage_tools", "qa-feel", action="activate"), "DENY")
        self.check(mcp("mcp__unity__execute_code", "qa-feel", action="replay",
                       note="// kiln:probe"), "DENY")
        edits = [{"newText": "// harmless"}, {"newText": "var g = new GameObject(\"x\");"}]
        self.check(mcp("mcp__unity__apply_text_edits", "gameplay-dev",
                       uri="unity://path/Assets/_Project/Scripts/Runtime/A.cs", edits=edits),
                   "DENY")
        self.check(mcp("mcp__unity__apply_text_edits", "gameplay-dev",
                       uri="unity://path/Assets/_Project/Scripts/Editor/A.cs", edits=edits),
                   "ALLOW")
        self.check(mcp("mcp__unity__manage_script", "gameplay-dev", action="create",
                       path="Assets/_Project/Scripts/Runtime/B.cs",
                       contents="gameObject.AddComponent<Light>();"), "DENY")
        self.check(mcp("mcp__unity__batch_execute", "gameplay-dev", commands=[
            {"tool": "create_script", "params": {"path": "Assets/_Project/Scripts/Runtime/C.cs",
                                                 "contents": "new GameObject(\"y\");"}}]),
                   "DENY")

    def test_shell(self):
        self.check(shell("Unity.exe -batchmode -projectPath . -executeMethod Gen.MakeLevel"),
                   "DENY")
        self.check(shell("Unity.exe -batchmode -projectPath . -executeMethod BuildScript.Win"),
                   "ALLOW")

    def test_reads_skip_lock(self):
        root = make_project("unity")
        self.check(mcp("mcp__unity__manage_gameobject", "level-designer", "w1", action="create"),
                   "ALLOW", root)
        self.check(mcp("mcp__unity__manage_scene", "qa-feel", "q1", action="get_hierarchy"),
                   "ALLOW", root)
        self.check(mcp("mcp__unity__manage_gameobject", "gameplay-dev", "w2", action="modify"),
                   "DENY", root)


class UnrealTests(GuardCase):
    engine = "unreal"

    def test_files(self):
        self.check(write("Content/Game/Maps/L1.umap", "level-designer"), "DENY")
        self.check(write("Content/Game/Mechs/SK_Mech.uasset", "modeler"), "DENY")
        self.check(write("Config/DefaultEngine.ini", "gameplay-dev"), "DENY")

    def test_scene_first_cpp(self):
        path = "Source/Game/Private/Arena.cpp"
        spawn = "GetWorld()->SpawnActor<AStaticMeshActor>(Loc, Rot);"
        self.check(write(path, "gameplay-dev", spawn), "DENY")
        self.check(write(path, "gameplay-dev", spawn + " // kiln:runtime-node debris"), "ALLOW")
        self.check(write(path, "gameplay-dev", "GetWorld()->SpawnActor<AProjectile>(C, T);"),
                   "ALLOW")
        self.check(write("Source/GameEditor/Private/Tool.cpp", "gameplay-dev", spawn), "ALLOW")

    def test_read_only_roles(self):
        self.check(mcp("mcp__unreal__list_toolsets", "qa-feel"), "ALLOW")
        self.check(unreal("get_current_level", "qa-feel"), "ALLOW")
        self.check(unreal("CaptureViewport", "qa-feel"), "ALLOW")
        self.check(unreal("StartPIE", "qa-feel"), "ALLOW")
        self.check(unreal("remove_from_scene", "qa-feel"), "DENY")
        self.check(unreal("execute_tool_script", "qa-feel", script="x"), "DENY")
        self.check(unreal("exec_console", "qa-feel", command="stat unit"), "ALLOW")
        self.check(unreal("exec_console", "qa-feel", command="destroyall"), "DENY")
        self.check(unreal("add_to_scene_from_asset", "level-designer"), "ALLOW")

    def test_qualified_names_and_server_aliases(self):
        self.check(unreal("editor_toolset.toolsets.scene.SceneTools.get_current_level",
                          "qa-feel"), "ALLOW")
        self.check(unreal("editor_toolset.toolsets.scene.SceneTools.remove_from_scene",
                          "qa-feel"), "DENY")
        self.check(mcp("mcp__unreal-mcp__call_tool", "qa-feel", toolset_name="T",
                       tool_name="remove_from_scene", arguments={}), "DENY")
        self.check(mcp("mcp__unreal-mcp__list_toolsets", "qa-feel"), "ALLOW")
        self.check(mcp("mcp__unreal-mcp-proxy__unreal_mcp_status", "qa-feel"), "ALLOW")
        self.check(unreal("exec_console", "qa-feel", command="Input.+key W"), "DENY")

    def test_generators(self):
        self.check(unreal("create_town", "level-designer"), "DENY")
        self.check(mcp("mcp__unreal__construct_house", "level-designer"), "DENY")

    def test_shell(self):
        self.check(shell("UnrealEditor-Cmd.exe P.uproject -ExecutePythonScript=gen.py"), "DENY")
        self.check(shell('UnrealEditor-Cmd.exe P.uproject -ExecCmds="Automation RunTests '
                         'Project" -unattended -nullrhi'), "ALLOW")


if __name__ == "__main__":
    unittest.main()
