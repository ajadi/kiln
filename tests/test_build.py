"""Tests for plugins/kiln/skills/release/scripts/build.py (stdlib only).

Run: python -m unittest tests.test_build -v   (from the repo root)
Fake Godot/Unity/Unreal projects are written to temp folders; fake engines and games are tiny
Python scripts (build.py runs a .py executable under the current interpreter).
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "plugins", "kiln", "skills", "release", "scripts", "build.py")
GUARD = os.path.join(HERE, "..", "plugins", "kiln", "hooks", "guard.py")

sys.dont_write_bytecode = True  # keep __pycache__ out of the plugin folder
spec = importlib.util.spec_from_file_location("kiln_build", SCRIPT)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

PRESETS = """[preset.0]

name="Windows Desktop"
platform="Windows Desktop"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter="{include}"
exclude_filter="{exclude}"
export_path="export/windows/mech.exe"
encryption_include_filters=""
encryption_exclude_filters=""
encrypt_pck=false
encrypt_directory=false
script_export_mode=2

[preset.0.options]

custom_template/debug=""
custom_template/release=""
debug/export_console_wrapper=1
binary_format/embed_pck=false
ssh_remote_deploy/run_script="#!/usr/bin/env bash
export DISPLAY=:0
unzip -o -q \\"{{temp_dir}}/{{archive_name}}\\" -d \\"{{temp_dir}}\\"
\\"{{temp_dir}}/{{exe_name}}\\" {{cmd_args}}"
shader_baker/enabled=true
"""


def write(root, rel, content="x"):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return path


def project(engine):
    root = tempfile.mkdtemp(prefix=f"kiln-build-{engine}-")
    write(root, "manifest.md", f"project_name=t\nframework=kiln\nengine={engine}\nmcp_only=on\n")
    return root


def godot_project(include="", exclude="tests/*, addons/godot_ai/*", ignore=()):
    root = project("godot")
    write(root, "project.godot", 'config_version=5\n\n[application]\n\nconfig/name="Mech Test"\n'
          'config/version="0.3.0"\nconfig/features=PackedStringArray("4.7", "Forward Plus")\n')
    write(root, "export_presets.cfg", PRESETS.format(include=include, exclude=exclude))
    for rel in ("scenes/main.tscn", "assets/a.png", "data/balance.json", "ref/hero.png",
                "ref/sheets/mech.blend", "ref/notes.md", "production/captures/c.png",
                "production/data.json", "tools/audio/gen.py", "tests/test_damage.gd",
                "design/notes.md", "design/mock.png", "research/r.md",
                "addons/godot_ai/plugin.gd"):
        write(root, rel)
    for folder in ignore:
        write(root, f"{folder}/.gdignore", "")
    return root


def run(root, *args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=root, capture_output=True,
                       text=True, timeout=120)
    try:
        return p.returncode, json.loads(p.stdout)
    except ValueError:
        raise AssertionError(f"no JSON from build.py: {p.stdout}\n{p.stderr}")


def guard(root, command):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
    out = subprocess.run([sys.executable, "-B", GUARD], input=json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}}), env=env,
        capture_output=True, text=True, timeout=20).stdout.strip()
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else "allow"


def pid_alive(pid):
    if os.name == "nt":
        import ctypes
        k32 = ctypes.WinDLL("kernel32")
        k32.OpenProcess.restype = ctypes.c_void_p
        handle = k32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        k32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        k32.CloseHandle(ctypes.c_void_p(handle))
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def fake(root, rel, body):
    return write(root, rel, "import os, sys, time, subprocess\n" + textwrap.dedent(body))


class GodotMatch(unittest.TestCase):
    def test_wildcards_follow_godot(self):
        self.assertTrue(build.godot_match("ref/*", "ref/sheets/mech.blend"))
        self.assertTrue(build.godot_match("REF/*", "ref/a.png"))
        self.assertTrue(build.godot_match("*.png", "res://assets/a.png"))
        self.assertFalse(build.godot_match("ref/*", "prefab/a.png"))
        self.assertFalse(build.godot_match("a?png", "a.png"))  # '?' never matches '.'
        self.assertTrue(build.godot_match("a?png", "a_png"))
        self.assertFalse(build.godot_match("", "x"))

    def test_config_parser_multiline(self):
        cfg = build.parse_cfg(PRESETS.format(include="", exclude="tests/*"))
        opts = cfg["preset.0.options"]
        self.assertIn("unzip -o -q", opts["ssh_remote_deploy/run_script"])
        self.assertIs(opts["shader_baker/enabled"], True)
        self.assertEqual(cfg["preset.0"]["exclude_filter"], "tests/*")
        self.assertEqual(build.parse_cfg('a=PackedStringArray("4.7", "Forward Plus")')[""]["a"],
                         ["4.7", "Forward Plus"])


class GodotAudit(unittest.TestCase):
    def test_leaks_and_uncovered_folders_fail(self):
        root = godot_project(ignore=("production",))
        code, res = run(root, "audit")
        self.assertEqual(code, 1)
        self.assertEqual(res["verdict"], "fail")
        preset = res["presets"][0]
        self.assertEqual(preset["non_shipping"]["ref"], "NOT COVERED")
        self.assertEqual(preset["non_shipping"]["production"], "gdignore")
        self.assertEqual(preset["non_shipping"]["tests"], "excluded")
        self.assertEqual(preset["leaks"]["ref"]["files"], 2)  # png + blend; the .md is text
        self.assertEqual(preset["leaks"]["design"]["files"], 1)
        self.assertNotIn("production", preset["leaks"])
        self.assertNotIn("tests", preset["leaks"])
        self.assertTrue(any("tools/" in i for i in res["issues"]))
        self.assertEqual(res["project_version"], "0.3.0")
        self.assertEqual(res["godot_version"], "4.7")
        self.assertTrue(preset["options"]["shader_baker/enabled"])

    def test_covered_project_passes(self):
        root = godot_project(include="*.json", exclude="tests/*, addons/godot_ai/*, design/*",
                             ignore=("ref", "production", "tools", "research"))
        code, res = run(root, "audit")
        self.assertEqual(code, 0, res["issues"])
        preset = res["presets"][0]
        self.assertEqual(preset["leaks"], {})
        self.assertEqual(preset["non_shipping"]["design"], "excluded")
        folders = preset["ships"]["by_folder"]
        self.assertIn("scenes", folders)
        self.assertIn("data", folders)  # include_filter *.json
        self.assertNotIn("production", folders)  # include_filter never enters .gdignore folders
        self.assertNotIn("addons", folders)

    def test_editor_addon_and_tests_gdignore_warn(self):
        root = godot_project(exclude="tests/*", ignore=("ref", "production", "tools", "design",
                                                        "research", "tests"))
        code, res = run(root, "audit")
        self.assertEqual(code, 0, res["issues"])
        self.assertTrue(any("addons/godot_ai" in w for w in res["warnings"]))
        self.assertTrue(any("tests/ holds a .gdignore" in w for w in res["warnings"]))

    def test_missing_presets_fail(self):
        root = godot_project()
        os.remove(os.path.join(root, "export_presets.cfg"))
        code, res = run(root, "audit")
        self.assertEqual(code, 1)
        self.assertTrue(any("export_presets.cfg missing" in i for i in res["issues"]))


class GodotBuild(unittest.TestCase):
    def setUp(self):
        self.root = godot_project(exclude="tests/*, design/*",
                                  ignore=("ref", "production", "tools", "research"))
        self.engine = fake(self.root, ".fake/godot.py", """
            args = sys.argv[1:]
            if os.environ.get("FAKE_FAIL"):
                print("ERROR: Project export for preset failed"); sys.exit(1)
            out = args[-1]
            with open(out, "wb") as fh:
                fh.write(b"MZ" + b"0" * 4096)
            print("export ok", " ".join(args))
        """)

    def test_dry_run_command_and_guard(self):
        code, res = run(self.root, "build", "--preset", "Windows Desktop", "--engine-exe",
                        self.engine, "--dry-run")
        self.assertEqual(code, 0, res.get("issues"))
        cmd = res["command"]
        self.assertEqual(cmd[2:4], ["--headless", "--path"])
        self.assertIn("--export-release", cmd)
        self.assertEqual(cmd[cmd.index("--export-release") + 1], "Windows Desktop")
        self.assertTrue(res["out"].endswith("export/windows/mech.exe"))
        self.assertNotIn("--script", cmd)
        self.assertEqual(guard(self.root, res["command_line"]), "allow")
        self.assertFalse(os.path.exists(os.path.join(self.root, "export")))  # dry run
        _, res = run(self.root, "build", "--preset", "Windows Desktop", "--engine-exe",
                     self.engine, "--dry-run", "--debug")
        self.assertIn("--export-debug", res["command"])

    def test_unknown_preset_fails(self):
        code, res = run(self.root, "build", "--preset", "Linux", "--engine-exe", self.engine,
                        "--dry-run")
        self.assertEqual(code, 1)
        self.assertTrue(any("not in export_presets.cfg" in i for i in res["issues"]))

    def test_build_runs_and_checks_artefact(self):
        code, res = run(self.root, "build", "--preset", "Windows Desktop", "--engine-exe",
                        self.engine)
        self.assertEqual(code, 0, res.get("issues"))
        self.assertTrue(res["artefact"]["fresh"])
        self.assertGreater(res["artefact"]["bytes"], 4000)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "export", ".gdignore")))
        self.assertTrue(os.path.isfile(res["log"]))
        self.assertEqual(res["output_dir"]["files"], 1)

    def test_failed_export_fails(self):
        env = dict(os.environ, FAKE_FAIL="1")
        p = subprocess.run([sys.executable, "-B", SCRIPT, "build", "--preset", "Windows Desktop",
                            "--engine-exe", self.engine, "--out", "export/win2/m.exe"],
                           cwd=self.root, capture_output=True, text=True, timeout=60, env=env)
        res = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1)
        self.assertIn("exit code 1", res["issues"])
        self.assertTrue(any("artefact missing" in i for i in res["issues"]))
        self.assertTrue(res["log_errors"])


class UnityProject(unittest.TestCase):
    def setUp(self):
        self.root = project("unity")
        write(self.root, "ProjectSettings/ProjectVersion.txt", "m_EditorVersion: 6000.2.5f1\n")
        write(self.root, "ProjectSettings/ProjectSettings.asset",
              "PlayerSettings:\n  productName: Mech Arena\n  bundleVersion: 0.3.0\n")
        write(self.root, "ProjectSettings/EditorBuildSettings.asset",
              "EditorBuildSettings:\n  m_Scenes:\n  - enabled: 1\n    path: "
              "Assets/_Project/Scenes/Main.unity\n")
        write(self.root, "Assets/_Project/Scripts/Editor/KilnBuild.cs", textwrap.dedent("""
            using UnityEditor;
            namespace KilnRelease
            {
                public static class KilnBuild
                {
                    public static void Build() { var r = BuildPipeline.BuildPlayer(Options()); }
                    static BuildPlayerOptions Options() { return new BuildPlayerOptions(); }
                }
            }
        """))
        write(self.root, "Assets/_Project/Tests/EditMode/Kiln.Tests.EditMode.asmdef",
              '{"name": "Kiln.Tests.EditMode", "includePlatforms": ["Editor"]}')

    def test_audit_finds_build_method(self):
        code, res = run(self.root, "audit")
        self.assertEqual(code, 0, res["issues"])
        self.assertEqual(res["build_methods"][0]["method"], "KilnRelease.KilnBuild.Build")
        self.assertTrue(res["build_methods"][0]["guard_allowed"])
        self.assertEqual(res["scenes_in_build"], ["Assets/_Project/Scenes/Main.unity"])
        self.assertEqual(res["project_version"], "0.3.0")

    def test_reference_folder_in_resources_fails(self):
        write(self.root, "Assets/Resources/ref/hero.png")
        code, res = run(self.root, "audit")
        self.assertEqual(code, 1)
        self.assertTrue(any("ships unconditionally" in i for i in res["issues"]))
        self.assertIn("Assets/Resources", res["ships_unconditionally"])

    def test_dry_run_uses_build_method(self):
        unity = write(self.root, ".fake/Unity.py", "")
        code, res = run(self.root, "build", "--preset", "StandaloneWindows64", "--engine-exe",
                        unity, "--dry-run")
        self.assertEqual(code, 0, res.get("issues"))
        cmd = res["command"]
        self.assertIn("-batchmode", cmd)
        self.assertEqual(cmd[cmd.index("-executeMethod") + 1], "KilnRelease.KilnBuild.Build")
        self.assertTrue(res["out"].endswith("export/standalonewindows64/mech-arena.exe"))
        self.assertEqual(guard(self.root, res["command_line"]), "allow")
        code, res = run(self.root, "build", "--preset", "Win64", "--engine-exe", unity,
                        "--method", "Tools.MakeLevel", "--dry-run")
        self.assertEqual(code, 1)
        self.assertEqual(guard(self.root, res["command_line"]), "deny")


class UnrealProject(unittest.TestCase):
    def setUp(self):
        self.root = project("unreal")
        write(self.root, "Mech.uproject", '{"EngineAssociation": "5.8"}')
        write(self.root, "Config/DefaultGame.ini", textwrap.dedent("""
            [/Script/EngineSettings.GeneralProjectSettings]
            ProjectVersion=0.3.0
            [/Script/UnrealEd.ProjectPackagingSettings]
            BuildConfiguration=PPBC_Shipping
            +MapsToCook=(FilePath="/Game/Mech/Maps/Arena")
            +DirectoriesToNeverCook=(Path="/Game/Developers")
        """))
        write(self.root, "Source/Mech.Target.cs", "Type = TargetType.Game;")
        self.uat = write(self.root, ".fake/RunUAT.py", "")

    def test_audit(self):
        code, res = run(self.root, "audit")
        self.assertEqual(code, 0, res["issues"])
        self.assertEqual(res["project_version"], "0.3.0")
        self.assertEqual(res["targets"][0]["type"], "Game")
        self.assertEqual(res["warnings"], [])

    def test_dry_run_buildcookrun(self):
        code, res = run(self.root, "build", "--preset", "Win64", "--engine-exe", self.uat,
                        "--dry-run")
        self.assertEqual(code, 0, res.get("issues"))
        cmd = res["command"]
        self.assertIn("BuildCookRun", cmd)
        self.assertIn("-clientconfig=Shipping", cmd)
        self.assertIn("-platform=Win64", cmd)
        self.assertEqual(guard(self.root, res["command_line"]), "allow")
        _, res = run(self.root, "build", "--preset", "Win64", "--engine-exe", self.uat,
                     "--dry-run", "--debug")
        self.assertIn("-clientconfig=Development", res["command"])

    def test_runuat_derived_from_editor(self):
        editor = os.path.join("UE_5.8", "Engine", "Binaries", "Win64", "UnrealEditor.exe")
        self.assertEqual(os.path.normpath(build.runuat_from(editor)).split(os.sep)[-4:-1],
                         ["Engine", "Build", "BatchFiles"])


class Smoke(unittest.TestCase):
    def setUp(self):
        self.root = godot_project()
        self.dir = os.path.join(self.root, "export", "windows")

    def smoke(self, rel, *args):
        return run(self.root, "smoke", os.path.join(self.dir, rel), *args)

    def test_alive_game_passes_and_tree_is_killed(self):
        fake(self.root, "export/windows/game.py", """
            here = os.path.dirname(os.path.abspath(__file__))
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            with open(os.path.join(here, "pids.txt"), "w") as fh:
                fh.write(f"{os.getpid()} {child.pid}")
            print("started", sys.argv[1:]); sys.stdout.flush()
            time.sleep(60)
        """)
        code, res = self.smoke("game.py", "--seconds", "2", "--", "--fullscreen", "0")
        self.assertEqual(code, 0, res["issues"])
        self.assertTrue(res["alive_at_end"])
        self.assertIn("--fullscreen", res["stdout_tail"][0])
        with open(os.path.join(self.dir, "pids.txt")) as fh:
            pids = [int(p) for p in fh.read().split()]
        time.sleep(0.5)
        self.assertFalse(any(pid_alive(p) for p in pids), "process tree still running")

    def test_exit_codes(self):
        fake(self.root, "export/windows/ok.py", "sys.exit(0)\n")
        fake(self.root, "export/windows/bad.py", "sys.exit(3)\n")
        code, res = self.smoke("ok.py", "--seconds", "5")
        self.assertEqual(code, 0, res["issues"])
        self.assertFalse(res["alive_at_end"])
        code, res = self.smoke("bad.py", "--seconds", "5")
        self.assertEqual(code, 1)
        self.assertEqual(res["exit_code"], 3)

    def test_error_lines_and_ignore(self):
        fake(self.root, "export/windows/err.py", """
            print("ERROR: Failed to instantiate an autoload, script 'x.gd' does not inherit")
            print("loading level"); sys.stdout.flush(); time.sleep(30)
        """)
        code, res = self.smoke("err.py", "--seconds", "1.5")
        self.assertEqual(code, 1)
        self.assertEqual(len(res["errors"]), 1)
        code, res = self.smoke("err.py", "--seconds", "1.5", "--ignore", "autoload")
        self.assertEqual(code, 0, res["issues"])

    def test_log_must_be_fresh(self):
        log = os.path.join(self.root, "game.log")
        fake(self.root, "export/windows/logs.py", f"""
            with open({log!r}, "w") as fh:
                fh.write("Godot Engine v4.7\\nSCRIPT ERROR: Invalid call\\n")
            time.sleep(30)
        """)
        code, res = self.smoke("logs.py", "--seconds", "1.5", "--log", log)
        self.assertEqual(code, 1)
        self.assertTrue(res["log"]["fresh"])
        self.assertIn("SCRIPT ERROR: Invalid call", res["errors"][0])
        fake(self.root, "export/windows/quiet.py", "time.sleep(30)\n")
        old = time.time() - 3600
        os.utime(log, (old, old))
        code, res = self.smoke("quiet.py", "--seconds", "1", "--log", log)
        self.assertEqual(code, 1)
        self.assertFalse(res["log"]["fresh"])

    def test_glob_needs_one_match(self):
        fake(self.root, "export/windows/a.py", "sys.exit(0)\n")
        code, res = run(self.root, "smoke", os.path.join(self.dir, "a.p*"), "--seconds", "3")
        self.assertEqual(code, 0, res["issues"])
        fake(self.root, "export/windows/b.py", "sys.exit(0)\n")
        code, res = run(self.root, "smoke", os.path.join(self.dir, "*.py"))
        self.assertEqual(code, 1)
        self.assertEqual(len(res["matches"]), 2)

    def test_memory_samples_and_growth_limit(self):
        fake(self.root, "export/windows/leak.py", """
            hold = []
            while True:
                hold.append(b"x" * 25_000_000); time.sleep(0.4)
        """)
        code, res = self.smoke("leak.py", "--seconds", "3", "--sample-every", "0.5",
                               "--warmup", "0.5")
        self.assertGreaterEqual(len(res["memory"]["samples"]), 2)
        self.assertEqual(code, 1)
        self.assertGreater(res["memory"]["growth_pct"], 20)
        fake(self.root, "export/windows/flat.py", "time.sleep(30)\n")
        code, res = self.smoke("flat.py", "--seconds", "2.5", "--sample-every", "0.5",
                               "--warmup", "0.5")
        self.assertEqual(code, 0, res["issues"])


if __name__ == "__main__":
    unittest.main()
