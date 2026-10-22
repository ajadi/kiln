"""Tests for the tools skill's tools_check.py: machine config and tools_root, plan, install with
checksums, manual instructions, generator offers. Offline: sources are file:// fixtures.

User (0.7.1): find everything first; Kiln installs Blender, uv, git-lfs, Ollama and MCP servers
itself after the user confirms; Unity and Unreal get a short instruction; AI generators are
offered with a comparison and installed after confirmation; tools_root is asked once.
"""

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "tools",
                      "scripts", "tools_check.py")
CATALOG = os.path.join(os.path.dirname(SCRIPT), "..", "catalog.json")


def make_zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class Env:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="kiln-tools-")
        self.home = os.path.join(self.root, "home")
        self.api = os.path.join(self.root, "api")
        os.makedirs(self.home)

    def run(self, *args, cwd=None, extra_env=None):
        env = dict(os.environ, KILN_HOME=self.home, KILN_GITHUB_API="file:///" +
                   self.api.replace("\\", "/"), KILN_GPU_GB="8", PATH=os.environ.get("PATH", ""))
        env.pop("CLAUDE_PLUGIN_DATA", None)
        env.update(extra_env or {})
        p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=cwd or self.root, env=env,
                           capture_output=True, text=True, timeout=120)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            return p.returncode, {"raw": p.stdout + p.stderr}

    def github_release(self, repo, tag, assets):
        folder = os.path.join(self.api, "repos", *repo.split("/"), "releases")
        os.makedirs(folder, exist_ok=True)
        data = {"tag_name": tag, "assets": [
            {"name": n, "browser_download_url": "file:///" + p.replace("\\", "/"),
             "size": os.path.getsize(p), "digest": "sha256:" + d} for n, p, d in assets]}
        for name in ("latest.json", f"tags-{tag}.json"):
            with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
                json.dump(data, fh)

    def catalog(self, tools, offers=None):
        path = os.path.join(self.root, "catalog.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"format": "kiln-tools-catalog/1", "tools": tools, "offers": offers or {}},
                      fh)
        return path


FAKE_TOOL = {"title": "Fake", "action": "install", "when": "always",
             "source": {"kind": "github", "repo": "acme/fake", "tag": "v{version}"},
             "assets": {"windows": "fake-{version}.zip", "linux": "fake-{version}.zip",
                        "macos": "fake-{version}.zip"},
             "find": ["faketool.py"], "known": [],
             "verify": [sys.executable, "{path}"], "expect": "fake {version}", "size_mb": 1,
             "licence": "MIT"}


class ToolsRoot(unittest.TestCase):
    def test_root_default_then_set_and_shared(self):
        e = Env()
        code, res = e.run("root")
        self.assertIsNone(res["tools_root"])
        self.assertTrue(res["suggested"].endswith("kiln-tools"))
        target = os.path.join(e.root, "MyTools")
        code, res = e.run("root", "--set", target)
        self.assertEqual(code, 0, res)
        self.assertTrue(os.path.isdir(target))
        with open(os.path.join(e.home, "machine.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["tools_root"], target.replace("\\", "/"))

    def test_old_plugin_data_machine_json_is_migrated(self):
        e = Env()
        old = os.path.join(e.root, "plugindata")
        os.makedirs(old)
        with open(os.path.join(old, "machine.json"), "w", encoding="utf-8") as fh:
            json.dump({"tools_root": "D:/Old", "godot_exe": "D:/Old/godot.exe"}, fh)
        code, res = e.run("root", extra_env={"CLAUDE_PLUGIN_DATA": old})
        self.assertEqual(res["tools_root"], "D:/Old")
        with open(os.path.join(e.home, "machine.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["godot_exe"], "D:/Old/godot.exe")


class Install(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.tools_root = os.path.join(self.e.root, "kt")
        self.e.run("root", "--set", self.tools_root)
        z = os.path.join(self.e.root, "fake-1.2.3.zip")
        self.digest = make_zip(z, {"fake/faketool.py": "print('fake 1.2.3')\n"})
        self.e.github_release("acme/fake", "v1.2.3", [("fake-1.2.3.zip", z, self.digest)])
        self.cat = self.e.catalog({"fake": FAKE_TOOL})

    def test_needs_confirmation_then_installs_and_registers(self):
        code, res = self.e.run("install", "fake", "--catalog", self.cat)
        self.assertEqual(code, 3, res)                         # nothing done without --yes
        self.assertEqual(res["would_install"]["version"], "1.2.3")
        self.assertFalse(os.path.exists(os.path.join(self.tools_root, "fake")))
        code, res = self.e.run("install", "fake", "--catalog", self.cat, "--yes")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["checksum"], "sha256 verified")
        self.assertTrue(res["path"].endswith("faketool.py"))
        self.assertIn(os.path.join("kt", "fake", "1.2.3").replace("\\", "/"), res["path"].replace("\\", "/"))
        with open(os.path.join(self.e.home, "machine.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["tools"]["fake"]["version"], "1.2.3")
        code, res = self.e.run("plan", "--catalog", self.cat)
        self.assertEqual(res["tools"][0]["status"], "found")

    def test_installed_lists_everything_kiln_put_on_the_machine(self):
        # User (0.7.1): setup shows everything Kiln installed.
        code, res = self.e.run("installed")
        self.assertEqual(res["installed"], [])
        self.e.run("install", "fake", "--catalog", self.cat, "--yes")
        self.e.run("mark", "fake", "--mcp", "claude", "--addon", "Blender add-on fake 1.2.3")
        self.e.run("mark", "fake", "--mcp", "codex")
        code, res = self.e.run("installed")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["tools_root"], self.tools_root.replace("\\", "/"))
        [row] = res["installed"]
        self.assertEqual((row["tool"], row["version"], row["checksum"]),
                         ("fake", "1.2.3", "sha256 verified"))
        self.assertTrue(row["path"].endswith("faketool.py"))
        self.assertRegex(row["installed_on"], r"^\d{4}-\d\d-\d\d$")
        self.assertEqual(row["size_bytes"], len("print('fake 1.2.3')\n"))
        self.assertEqual(row["mcp"], ["claude", "codex"])
        self.assertEqual(row["addons"], ["Blender add-on fake 1.2.3"])
        code, res = self.e.run("mark", "nope", "--mcp", "claude")
        self.assertEqual(code, 1, res)

    def test_bad_checksum_installs_nothing(self):
        z = os.path.join(self.e.root, "fake-1.2.3.zip")
        self.e.github_release("acme/fake", "v1.2.3", [("fake-1.2.3.zip", z, "0" * 64)])
        code, res = self.e.run("install", "fake", "--catalog", self.cat, "--yes")
        self.assertEqual(code, 1, res)
        self.assertIn("checksum", res["problems"][0])
        self.assertFalse(os.path.exists(os.path.join(self.tools_root, "fake", "1.2.3")))

    def test_blender_style_index_with_sha256_file(self):
        rel = os.path.join(self.e.root, "blender", "Blender5.2")
        os.makedirs(rel)
        z = os.path.join(rel, "blender-5.2.2-windows-x64.zip")
        d = make_zip(z, {"blender-5.2.2-windows-x64/faketool.py": "print('fake Blender 5.2.2')\n"})
        for plat in ("linux-x64.tar.xz", "macos-arm64.dmg"):
            open(os.path.join(rel, f"blender-5.2.2-{plat}"), "w").close()
        with open(os.path.join(rel, "index.html"), "w", encoding="utf-8") as fh:
            fh.write('<a href="blender-5.2.1-windows-x64.zip">x</a><a href="blender-5.2.2-windows-x64.zip">y</a>')
        with open(os.path.join(rel, "blender-5.2.2.sha256"), "w", encoding="utf-8") as fh:
            fh.write(f"{d}  blender-5.2.2-windows-x64.zip\n")
        tool = dict(FAKE_TOOL, source={"kind": "blender", "series": "5.2",
                                       "index": "file:///" + rel.replace("\\", "/") + "/index.html",
                                       "checksums": "blender-{version}.sha256"},
                    assets={"windows": "blender-{version}-windows-x64.zip",
                            "linux": "blender-{version}-windows-x64.zip",
                            "macos": "blender-{version}-windows-x64.zip"},
                    expect="Blender {series}")
        cat = self.e.catalog({"blender": tool})
        code, res = self.e.run("install", "blender", "--catalog", cat, "--yes")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["version"], "5.2.2")

    def test_manual_tools_get_instructions(self):
        code, res = self.e.run("install", "unity", "--yes")
        self.assertEqual(code, 2, res)
        self.assertIn("Unity Hub", res["instruction"])


class Plan(unittest.TestCase):
    def test_plan_for_a_godot_project_with_ollama_and_local_generators(self):
        e = Env()
        e.run("root", "--set", os.path.join(e.root, "kt"))
        proj = os.path.join(e.root, "game")
        os.makedirs(proj)
        with open(os.path.join(proj, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write("framework=kiln\nengine=godot\ndimension=3d\nllm_npc=local\n"
                     "model_generators=local\n")
        code, res = e.run("plan", "--project", proj, extra_env={"PATH": ""})
        rows = {r["tool"]: r for r in res["tools"]}
        for name in ("godot", "blender", "uv", "git-lfs", "ollama", "godot-ai", "blender-mcp"):
            self.assertIn(name, rows)
        self.assertNotIn("unity", rows)
        self.assertEqual(rows["ollama"]["action"], "install")
        offers = {o["offer"]: o for o in res["offers"]}
        self.assertTrue(offers["triposg"]["fits"])               # 8 GB on this "machine"
        self.assertFalse(offers["trellis2"]["fits"])
        self.assertIn("needs", res["confirm"])                   # one question for the user

    def test_music_generators_follow_audio_generators(self):
        # S08: /kiln:track - text-to-music offers come with audio_generators, not model_generators.
        e = Env()
        proj = os.path.join(e.root, "tracks")
        os.makedirs(proj)
        with open(os.path.join(proj, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write("framework=kiln\nengine=none\nkind=assets\naudio_generators=local\n")
        code, res = e.run("offers", "--project", proj)
        offers = {o["offer"]: o for o in res["offers"]}
        self.assertTrue(offers["ace-step-1.5"]["fits"])          # < 4 GB on an 8 GB "machine"
        self.assertTrue(offers["ace-step-1.5"]["commercial"])
        self.assertNotIn("triposg", offers)
        self.assertIn("musicgen", res["not_offered"])
        with open(os.path.join(proj, "manifest.md"), "a", encoding="utf-8") as fh:
            fh.write("model_generators=local\naudio_generators=off\n")
        code, res = e.run("offers", "--project", proj)
        offers = {o["offer"] for o in res["offers"]}
        self.assertIn("triposg", offers)
        self.assertNotIn("ace-step-1.5", offers)

    def test_video_offers_follow_video_generators_and_pose_is_on_request(self):
        # research 2026-10-19 video reference: own policy; the pose library only when asked
        e = Env()
        e.run("root", "--set", os.path.join(e.root, "kt"))
        proj = os.path.join(e.root, "anim")
        os.makedirs(proj)
        with open(os.path.join(proj, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write("framework=kiln\nengine=godot\nmodel_generators=local\n")
        code, res = e.run("offers", "--project", proj)
        self.assertNotIn("wan22-ti2v-5b", {o["offer"] for o in res["offers"]})
        self.assertIn("hunyuanvideo-1.5", res["not_offered"])
        with open(os.path.join(proj, "manifest.md"), "a", encoding="utf-8") as fh:
            fh.write("video_generators=local\n")
        code, res = e.run("offers", "--project", proj)
        offers = {o["offer"]: o for o in res["offers"]}
        self.assertTrue(offers["wan22-ti2v-5b"]["fits"])          # 8 GB on this "machine"
        self.assertFalse(offers["wan21-flf2v-14b"]["fits"])
        self.assertEqual(offers["ltx2"]["commercial"], "under $10M annual revenue")
        code, res = e.run("plan", "--project", proj, extra_env={"PATH": ""})
        self.assertNotIn("pose", {r["tool"] for r in res["tools"]})
        code, res = e.run("install", "pose")
        self.assertEqual(code, 3, res)                               # asks first
        self.assertIn("rtmlib==0.0.16", res["would_install"]["packages"])

    def test_unity_project_names_the_manual_step(self):
        e = Env()
        proj = os.path.join(e.root, "u")
        os.makedirs(proj)
        with open(os.path.join(proj, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write("framework=kiln\nengine=unity\n")
        code, res = e.run("plan", "--project", proj, extra_env={"PATH": ""})
        rows = {r["tool"]: r for r in res["tools"]}
        self.assertEqual(rows["unity"]["action"], "manual")
        self.assertIn("Unity Hub", rows["unity"]["instruction"])
        self.assertIn("unity-mcp", rows)
        self.assertNotIn("godot", rows)


class PosixArchives(unittest.TestCase):
    """KILN-REV-05 / KILN-REV-07 (review 2026-10-21). Runs on any OS: the macOS and Linux paths
    are taken by setting the module's PLATFORM, and the download and the verify call are
    replaced, so nothing is fetched or launched."""

    def setUp(self):
        sys.path.insert(0, os.path.dirname(SCRIPT))
        import tools_check
        self.tc = tools_check
        self.home = tempfile.mkdtemp(prefix="kiln-tch-")
        self.root = tempfile.mkdtemp(prefix="kiln-tcr-")
        self.saved = (os.environ.get("KILN_HOME"), tools_check.PLATFORM, tools_check.fetch,
                      tools_check.resolve, tools_check.run_verify)
        os.environ["KILN_HOME"] = self.home
        with open(CATALOG, encoding="utf-8") as fh:
            self.catalog = json.load(fh)

    def tearDown(self):
        home, self.tc.PLATFORM, self.tc.fetch, self.tc.resolve, self.tc.run_verify = self.saved
        if home is None:
            os.environ.pop("KILN_HOME", None)
        else:
            os.environ["KILN_HOME"] = home

    def zip_bytes(self, entries):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, mode in entries:
                info = zipfile.ZipInfo(name)
                info.external_attr = (0o100000 | mode) << 16
                z.writestr(info, "#!/bin/sh\necho Godot 4.7.2.stable\n")
        return buf.getvalue()

    def install(self, platform, entries, verified=True):
        import argparse
        self.tc.PLATFORM = platform
        data = self.zip_bytes(entries)
        self.tc.fetch = lambda url, binary=False: data
        self.tc.resolve = lambda name, tool, version=None: (
            "4.7.2", "https://example.invalid/godot.zip", hashlib.sha256(data).hexdigest(),
            "godot.zip")
        seen = []

        def verify(tool, path, version, series):
            seen.append(path)
            return verified, "Godot 4.7.2.stable"
        self.tc.run_verify = verify
        machine = {"tools_root": self.root}
        res, code = self.tc.cmd_install(argparse.Namespace(tool="godot", version=None, yes=True),
                                        self.catalog, machine)
        return res, code, machine, seen

    def test_the_macos_bundle_executable_is_found_and_a_bundle_without_it_fails(self):
        res, code, machine, seen = self.install("macos", [
            ("Godot.app/Contents/Info.plist", 0o644),
            ("Godot.app/Contents/MacOS/Godot", 0o755)])
        self.assertEqual(code, 0, res)
        self.assertTrue(res["path"].endswith("Godot.app/Contents/MacOS/Godot"), res)
        self.assertEqual(seen, [os.path.join(self.root, "godot", "4.7.2", "Godot.app", "Contents",
                                             "MacOS", "Godot")])
        self.assertTrue(machine["tools"]["godot"]["path"].endswith("MacOS/Godot"))
        res, code, machine, seen = self.install("macos", [("Godot.app/Contents/Info.plist", 0o644)])
        self.assertEqual(code, 1, res)                     # no executable: not a success
        self.assertNotIn("godot", machine.get("tools", {}))
        self.assertFalse(os.path.isdir(os.path.join(self.root, "godot", "4.7.2")))

    def test_a_failed_verification_is_not_registered(self):
        res, code, machine, seen = self.install(
            "linux", [("Godot_v4.7.2-stable_linux.x86_64", 0o755)], verified=False)
        self.assertEqual(code, 1, res)
        self.assertNotIn("godot", machine.get("tools", {}))

    def test_zip_entries_keep_their_executable_bit(self):
        chmods = []
        real = os.chmod
        self.tc.os.chmod = lambda path, mode: (chmods.append((os.path.basename(path), mode)),
                                               real(path, mode))
        try:
            archive = os.path.join(self.root, "t.zip")
            with open(archive, "wb") as fh:
                fh.write(self.zip_bytes([("bin/tool", 0o755), ("bin/readme.txt", 0o644)]))
            self.tc.unpack(archive, os.path.join(self.root, "out"))
        finally:
            self.tc.os.chmod = real
        modes = dict(chmods)
        self.assertTrue(modes.get("tool", 0) & 0o111, chmods)
        self.assertFalse(modes.get("readme.txt", 0) & 0o111, chmods)
        if os.name == "posix":                             # the real bit, where it exists
            self.assertTrue(os.access(os.path.join(self.root, "out", "bin", "tool"), os.X_OK))

    def test_a_registered_folder_is_not_a_found_executable(self):
        folder = os.path.join(self.root, "godot", "4.7.2")
        os.makedirs(folder)
        machine = {"tools": {"godot": {"path": folder}}}
        tool = dict(self.catalog["tools"]["godot"], find=[], known=[])
        self.assertEqual(self.tc.find_tool("godot", tool, machine), [])


if __name__ == "__main__":
    unittest.main()
