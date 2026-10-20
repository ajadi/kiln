"""Tests for plugins/kiln/skills/release/scripts/store_check.py: Steam capsules, Steam Deck text
size (a real headless Godot), Google Play target API and 16 KB pages (synthetic APK/AAB files
and the real Godot Android template when installed), web hosting headers (a real Godot web
export served locally with and without COOP/COEP), and the AI disclosure draft."""

import http.server
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from test_probe_base import GODOT  # noqa: E402

SCRIPT = os.path.join(HERE, "..", "plugins", "kiln", "skills", "release", "scripts", "store_check.py")


def run(cwd, *args, timeout=600):
    env = dict(os.environ)
    if GODOT:
        env["KILN_ENGINE_EXE"] = GODOT
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=cwd, capture_output=True,
                       text=True, timeout=timeout, env=env)
    try:
        return p.returncode, json.loads(p.stdout)
    except ValueError:
        raise AssertionError(p.stdout + p.stderr)


def temp():
    d = tempfile.mkdtemp(prefix="kiln-store-")
    return d


# ---------------------------------------------------------------- capsules

class Capsules(unittest.TestCase):
    def setUp(self):
        from PIL import Image, ImageDraw
        self.Image, self.Draw = Image, ImageDraw
        self.root = temp()
        self.folder = os.path.join(self.root, "store", "steam")
        os.makedirs(os.path.join(self.folder, "shots"))

    def make_all(self, skip=(), wrong=None):
        sizes = {"header": (920, 430), "small": (462, 174), "main": (1232, 706),
                 "vertical": (748, 896), "library_capsule": (600, 900),
                 "library_header": (920, 430), "library_hero": (3840, 1240)}
        for name, size in sizes.items():
            if name in skip:
                continue
            size = wrong if wrong and name == "main" else size
            img = self.Image.new("RGB", size, (40, 60, 90))
            self.Draw.Draw(img).rectangle([size[0] // 4, size[1] // 3, size[0] * 3 // 4,
                                           size[1] * 2 // 3], fill=(230, 200, 60))
            img.save(os.path.join(self.folder, name + ".png"))
        logo = self.Image.new("RGBA", (1280, 400), (0, 0, 0, 0))
        self.Draw.Draw(logo).rectangle([100, 100, 1180, 300], fill=(255, 255, 255, 255))
        logo.save(os.path.join(self.folder, "library_logo.png"))
        for i in range(5):
            self.Image.new("RGB", (1920, 1080), (i * 20, 80, 80)).save(
                os.path.join(self.folder, "shots", f"shot{i}.png"))

    def test_sizes_pass_and_the_text_rule_waits_for_the_review(self):
        self.make_all()
        code, res = run(self.root, "capsules", "store/steam", "--screenshots", "store/steam/shots")
        self.assertEqual((code, res["verdict"]), (0, "not assessed"), res)
        self.assertEqual(res["problems"], [])
        rev = os.path.join(self.root, "production", "release", "capsules")
        small = self.Image.open(os.path.join(rev, "small_120x45.png"))
        self.assertEqual(small.size, (360, 135))
        with open(os.path.join(rev, "review.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(len(data["items"]), 8)
        for item in data["items"]:
            item["answer"] = {"extra_text": item["asset"] == "header", "logo_legible": True,
                              "evidence": "'Best game 2026 - IGN' under the logo"}
        answers = os.path.join(rev, "answers.json")
        with open(answers, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        code, res = run(self.root, "capsules", "store/steam", "--screenshots", "store/steam/shots",
                        "--answers", answers)
        self.assertEqual((code, res["verdict"]), (1, "fail"), res)
        self.assertIn("header: text beyond the title", res["problems"][0])
        for item in data["items"]:
            item["answer"]["extra_text"] = False
        with open(answers, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        code, res = run(self.root, "capsules", "store/steam", "--screenshots", "store/steam/shots",
                        "--answers", answers)
        self.assertEqual((code, res["verdict"]), (0, "pass"), res)
        # bug hunt 2026-10-20: empty answers, or no screenshot check, are not a pass
        code, res = run(self.root, "capsules", "store/steam", "--answers", answers)
        self.assertEqual(res["verdict"], "not assessed", res)
        for item in data["items"]:
            item["answer"] = {}
        with open(answers, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        code, res = run(self.root, "capsules", "store/steam", "--screenshots", "store/steam/shots",
                        "--answers", answers)
        self.assertEqual((res["verdict"], len(res["unanswered"])), ("not assessed", 8), res)

    def test_wrong_size_missing_asset_opaque_logo_and_few_screenshots(self):
        self.make_all(skip=("vertical",), wrong=(1232, 700))
        self.Image.new("RGB", (1280, 400), (0, 0, 0)).save(
            os.path.join(self.folder, "library_logo.png"))
        os.remove(os.path.join(self.folder, "shots", "shot4.png"))
        self.Image.new("RGB", (1280, 720)).save(os.path.join(self.folder, "shots", "small.png"))
        code, res = run(self.root, "capsules", "store/steam", "--screenshots", "store/steam/shots")
        self.assertEqual(code, 1)
        text = "\n".join(res["problems"])
        for want in ("main: 1232x700, needs 1232x706", "vertical: missing",
                     "library_logo: needs a transparent background",
                     "screenshot small.png: 1280x720"):
            self.assertIn(want, text)


# ---------------------------------------------------------------- android

def elf(align, is64=True):
    """A minimal ELF shared object with two PT_LOAD program headers."""
    if is64:
        head = bytearray(64)
        head[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<QHH", head, 0x20, 64, 0, 0)
        struct.pack_into("<HH", head, 0x36, 56, 2)
        ph = b"".join(struct.pack("<IIQQQQQQ", 1, 5, 0, 0, 0, 0x100, 0x100, align) for _ in range(2))
    else:
        head = bytearray(52)
        head[:6] = b"\x7fELF\x01\x01"
        struct.pack_into("<I", head, 0x1C, 52)
        struct.pack_into("<HH", head, 0x2A, 32, 2)
        ph = b"".join(struct.pack("<IIIIIIII", 1, 0, 0, 0, 0x100, 0x100, 5, align) for _ in range(2))
    return bytes(head) + ph + b"\0" * 256


def pb_varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def pb(field, value):
    if isinstance(value, int):
        return pb_varint(field << 3) + pb_varint(value)
    value = value.encode() if isinstance(value, str) else value
    return pb_varint(field << 3 | 2) + pb_varint(len(value)) + value


def aab_manifest(target, as_string=True):
    """aapt2 XmlNode: element(1){name(3), attribute(4){name 2, value 3, resource_id 5,
    compiled_item 6 {prim 7 {int_decimal 6}}}, child(5) ...}."""
    attr = pb(1, "http://schemas.android.com/apk/res/android") + pb(2, "targetSdkVersion")
    attr += pb(3, str(target)) if as_string else b""
    attr += pb(5, 0x01010270) + pb(6, pb(7, pb(6, target)))
    uses = pb(1, pb(3, "uses-sdk") + pb(4, attr))
    return pb(1, pb(3, "manifest") + pb(5, uses))


class Android(unittest.TestCase):
    def setUp(self):
        self.root = temp()

    def aab(self, target, libs, as_string=True):
        path = os.path.join(self.root, "game.aab")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("base/manifest/AndroidManifest.xml", aab_manifest(target, as_string))
            for name, data in libs.items():
                z.writestr("base/lib/" + name, data)
        return path

    def test_aab_target_api_and_16k_alignment(self):
        good = {"arm64-v8a/libgame.so": elf(0x4000), "x86_64/libgame.so": elf(0x4000),
                "armeabi-v7a/libgame.so": elf(0x1000, False)}
        code, res = run(self.root, "android", self.aab(36, good))
        self.assertEqual((code, res["verdict"]), (0, "pass"), res)
        self.assertEqual(res["manifest"]["uses-sdk.targetSdkVersion"], 36)
        code, res = run(self.root, "android", self.aab(36, good, as_string=False))
        self.assertEqual(res["manifest"]["uses-sdk.targetSdkVersion"], 36, res)
        bad = dict(good, **{"arm64-v8a/libaddon.so": elf(0x1000)})
        code, res = run(self.root, "android", self.aab(35, bad))
        self.assertEqual(code, 1)
        text = "\n".join(res["problems"])
        self.assertIn("targetSdkVersion 35 < 36", text)
        self.assertIn("arm64-v8a/libaddon.so: LOAD segments aligned to 0x1000", text)
        self.assertNotIn("armeabi-v7a", text)          # 32-bit devices keep 4 KB pages

    def test_apk_stored_library_must_sit_on_a_16k_zip_offset(self):
        tmpl = os.path.join(os.environ.get("APPDATA", ""), "Godot", "export_templates")
        apks = sorted(p for p in (os.path.join(tmpl, v, "android_release.apk")
                                  for v in (os.listdir(tmpl) if os.path.isdir(tmpl) else []))
                      if os.path.isfile(p))
        if not apks:
            self.skipTest("no Godot Android export template installed")
        src = apks[-1]
        code, res = run(self.root, "android", src)        # the real template: API 36, 16 KB libs
        self.assertEqual((code, res["verdict"]), (0, "pass"), res)
        self.assertGreaterEqual(res["manifest"]["uses-sdk.targetSdkVersion"], 36)
        out = os.path.join(self.root, "stored.apk")
        with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
            zout.writestr("AndroidManifest.xml", zin.read("AndroidManifest.xml"))
            zout.writestr(zipfile.ZipInfo("lib/arm64-v8a/libgame.so"), elf(0x4000))  # stored
        code, res = run(self.root, "android", out)
        self.assertEqual(code, 1, res)
        self.assertIn("not 16 KB aligned", "\n".join(res["problems"]))

    def test_presets_report_target_sdk_and_format(self):
        with open(os.path.join(self.root, "project.godot"), "w") as fh:
            fh.write("config_version=5\n")
        with open(os.path.join(self.root, "export_presets.cfg"), "w") as fh:
            fh.write('[preset.0]\nname="Android"\nplatform="Android"\n[preset.0.options]\n'
                     'gradle_build/use_gradle_build=true\ngradle_build/export_format=0\n'
                     'gradle_build/target_sdk="34"\n')
        code, res = run(self.root, "android")
        self.assertEqual(code, 1)
        self.assertIn("target SDK 34 < 36", res["problems"][0])
        self.assertIn("AAB", "\n".join(res["warnings"]))


# ---------------------------------------------------------------- ai-disclosure

class AiDisclosure(unittest.TestCase):
    def test_draft_lists_generated_assets_and_runtime_model_calls(self):
        root = temp()

        def prov(folder, data, files=()):
            os.makedirs(os.path.join(root, folder), exist_ok=True)
            with open(os.path.join(root, folder, "provenance.json"), "w") as fh:
                json.dump(data, fh)
            for f in files:
                open(os.path.join(root, folder, f), "wb").close()

        prov("art/generated/crate", {"service": "meshy", "version": "image-to-3d meshy-6",
                                     "ai_generated": True, "outputs": [{"file": "crate.glb"}]})
        prov("audio/generated/wind", {"tool": "stable-audio-open", "version": "1.0"}, ["wind.ogg"])
        prov("art/generated/sign", {"tool": "flux", "ai_generated": True,
                                    "outputs": [{"file": "sign.png"}]})
        prov("art/library/barrel", {"kind": "library", "source": "kenney"}, ["barrel.glb"])
        prov("ref/boards/look", {"tool": "flux", "ai_generated": True,
                                 "outputs": [{"file": "a.png"}]})
        os.makedirs(os.path.join(root, "production"))
        with open(os.path.join(root, "production", "ai-content.csv"), "w") as fh:
            fh.write("item,category,tool,ships,notes\nnpc barks,text,Claude,yes,edited by hand\n")
        os.makedirs(os.path.join(root, "scripts"))
        with open(os.path.join(root, "scripts", "npc.gd"), "w") as fh:
            fh.write('extends Node\nconst URL = "http://127.0.0.1:8100/v1/chat/completions"\n')
        code, res = run(root, "ai-disclosure")
        self.assertEqual((code, res["verdict"]), (0, "draft"), res)
        self.assertEqual(res["pre_generated"]["3D models"], ["meshy image-to-3d meshy-6"])
        self.assertIn("sound and music", res["pre_generated"])
        self.assertIn("text", res["pre_generated"])
        self.assertEqual(res["shipping"], 4)                     # ref/ never ships, library skipped
        self.assertEqual(res["live_candidates"][0]["file"], "scripts/npc.gd")
        text = open(os.path.join(root, "production", "release", "AI_DISCLOSURE.md")).read()
        self.assertIn("guardrails", text)
        self.assertIn("- text: 1 items", text)          # not counted inside "images and textures"
        self.assertNotIn("kenney", text)


# ---------------------------------------------------------------- Godot: deck text, web export

DECK_SCENE = '''[gd_scene load_steps=3 format=3]

[ext_resource type="FontFile" path="res://body.ttf" id="f"]

[sub_resource type="LabelSettings" id="ls"]
font_size = 4

[node name="Menu" type="Control"]
layout_mode = 3
anchors_preset = 15

[node name="Title" type="Label" parent="."]
theme_override_font_sizes/font_size = 12
text = "Kiln Test"

[node name="Fine" type="Label" parent="."]
label_settings = SubResource("ls")
text = "fine print"

[node name="Body" type="Label" parent="."]
theme_override_fonts/font = ExtResource("f")
theme_override_font_sizes/font_size = 5
text = "body text"

[node name="Rich" type="RichTextLabel" parent="."]
theme_override_font_sizes/normal_font_size = 8
text = "[font_size=6]small[/font_size] normal"

[node name="Pause" type="Button" parent="."]
visible = false
text = "Resume"
'''

PROJECT = '''config_version=5

[application]
config/name="deck"

[display]
window/size/viewport_width=640
window/size/viewport_height=400
window/stretch/mode="canvas_items"
'''


def windows_font():
    for p in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.isfile(p):
            return p
    return None


@unittest.skipUnless(GODOT, "no Godot console binary found (set KILN_GODOT)")
class Deck(unittest.TestCase):
    def test_sizes_at_1280x800_with_the_stretch_scale(self):
        font = windows_font()
        if not font:
            self.skipTest("no TrueType font to copy into the project")
        root = temp()
        with open(os.path.join(root, "project.godot"), "w") as fh:
            fh.write(PROJECT)
        shutil.copy(font, os.path.join(root, "body.ttf"))
        with open(os.path.join(root, "menu.tscn"), "w") as fh:
            fh.write(DECK_SCENE)
        subprocess.run([GODOT, "--headless", "--path", root, "--import"], capture_output=True,
                       timeout=300)
        code, res = run(root, "deck", "--scene", "res://menu.tscn")
        self.assertEqual(res["stretch_scale"], 2.0, res)
        by = {r["node"]: r for r in res["smallest"]}
        self.assertEqual(by["Fine"]["px"], 8.0)                  # 4 x 2: below Valve's 9
        self.assertEqual(by["Title"]["px"], 24.0)
        self.assertEqual(by["Body"]["glyphs"], "measured")
        self.assertAlmostEqual(by["Body"]["cap_px"], 10 * 0.716, delta=0.3)   # Arial cap height
        self.assertFalse(by["Pause"]["visible"])                 # hidden menus are checked too
        sizes = sorted(r["px"] for r in res["smallest"] if r["node"] == "Rich")
        self.assertEqual(sizes, [12.0, 16.0])                    # [font_size=6] and normal 8
        self.assertEqual((code, res["verdict"]), (1, "fail"))
        self.assertEqual(len(res["problems"]), 1, res["problems"])
        self.assertIn("Fine", res["problems"][0])
        self.assertTrue(any("Body" in w and "capital letters" in w for w in res["warnings"]),
                        res["warnings"])
        code, res = run(root, "deck", "--scene", "res://menu.tscn", "--skip", "Fine")
        self.assertEqual((code, res["verdict"]), (0, "pass"), res)

    def test_integer_scale_never_goes_below_one(self):
        # bug hunt 2026-10-20: a 1920x1080 base in integer mode read 0.667 on the Deck; Godot
        # keeps 1.0 (its get_stretch_transform at 1280x800, checked live)
        root = temp()
        with open(os.path.join(root, "project.godot"), "w") as fh:
            fh.write(PROJECT.replace("640", "1920").replace("400", "1080") +
                     'window/stretch/scale_mode="integer"\n')
        with open(os.path.join(root, "menu.tscn"), "w") as fh:
            fh.write('[gd_scene format=3]\n\n[node name="M" type="Control"]\n\n'
                     '[node name="T" type="Label" parent="."]\ntext = "hi"\n')
        code, res = run(root, "deck", "--scene", "res://menu.tscn")
        self.assertEqual(res["stretch_scale"], 1.0, res)


WEB_PRESET = '''[preset.0]

name="Web"
platform="Web"
runnable=true
export_filter="all_resources"
export_path="export/web/index.html"

[preset.0.options]

variant/extensions_support=false
variant/thread_support={threads}
vram_texture_compression/for_desktop=true
vram_texture_compression/for_mobile=false
html/export_icon=false
progressive_web_app/enabled=false
'''


class Handler(http.server.SimpleHTTPRequestHandler):
    isolate = False

    def end_headers(self):
        if self.isolate:
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        super().end_headers()

    def log_message(self, *args):
        pass


def web_template():
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~/.local/share")),
                        "Godot", "export_templates")
    return os.path.isdir(base) and any(os.path.isfile(os.path.join(base, v, "web_release.zip"))
                                       for v in os.listdir(base))


@unittest.skipUnless(GODOT and web_template(), "needs Godot and its web export templates")
class Web(unittest.TestCase):
    def export(self, threads):
        root = temp()
        with open(os.path.join(root, "project.godot"), "w") as fh:
            fh.write('config_version=5\n\n[application]\nconfig/name="web"\n'
                     'run/main_scene="res://main.tscn"\n')
        with open(os.path.join(root, "main.tscn"), "w") as fh:
            fh.write('[gd_scene format=3]\n\n[node name="Main" type="Node2D"]\n')
        with open(os.path.join(root, "export_presets.cfg"), "w") as fh:
            fh.write(WEB_PRESET.format(threads="true" if threads else "false"))
        os.makedirs(os.path.join(root, "export", "web"))
        subprocess.run([GODOT, "--headless", "--path", root, "--import"], capture_output=True,
                       timeout=300)
        p = subprocess.run([GODOT, "--headless", "--path", root, "--export-release", "Web",
                            "export/web/index.html"], capture_output=True, text=True, timeout=600)
        out = os.path.join(root, "export", "web")
        self.assertTrue(os.path.isfile(os.path.join(out, "index.html")), p.stdout + p.stderr)
        return root, out

    def serve(self, folder, isolate):
        handler = type("H", (Handler,), {"isolate": isolate})
        srv = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), lambda *a, **k: handler(*a, directory=folder, **k))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_address[1]}/index.html"

    def test_threaded_export_needs_coop_coep_on_the_host(self):
        root, out = self.export(threads=True)
        code, res = run(root, "web", "export/web")
        self.assertEqual((res["threads"], res["verdict"]), (True, "not assessed"), res)
        code, res = run(root, "web", "export/web", "--url", self.serve(out, isolate=False))
        self.assertEqual((code, res["verdict"]), (1, "fail"), res)
        self.assertIn("Cross-Origin-Opener-Policy", res["problems"][0])
        code, res = run(root, "web", "export/web", "--url", self.serve(out, isolate=True))
        self.assertEqual((code, res["verdict"]), (0, "pass"), res)
        self.assertEqual(res["wasm_type"], "application/wasm")
        with open(os.path.join(out, "_headers"), "w") as fh:
            fh.write("/*\n  Cross-Origin-Opener-Policy: same-origin\n")
        code, res = run(root, "web", "export/web")
        self.assertIn("Cross-Origin-Embedder-Policy", "\n".join(res["problems"]))

    def test_single_threaded_export_runs_anywhere(self):
        root, out = self.export(threads=False)
        code, res = run(root, "web", "export/web", "--url", self.serve(out, isolate=False))
        self.assertEqual((code, res["threads"], res["verdict"]), (0, False, "pass"), res)


if __name__ == "__main__":
    unittest.main()
