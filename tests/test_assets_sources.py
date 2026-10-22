"""Tests for the asset-libraries sources that have no JSON API of their own - Kenney (HTML pages
and pack zips), KayKit and game-icons (GitHub), Google Fonts (metadata JSON and METADATA.pb) -
plus `import` for files the user downloaded and the CREDITS.md that licenses.py builds. Shapes
recorded live 2026-10-19; every request goes to a local fake."""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills")
SCRIPT = os.path.join(ROOT, "asset-libraries", "scripts", "assets_api.py")
LICENSES = os.path.join(ROOT, "pipeline", "scripts", "licenses.py")

KENNEY_CC0 = (b"\tFurniture Kit (2.0)\r\n\tCreated/distributed by Kenney (www.kenney.nl)\r\n"
              b"\tLicense: (Creative Commons Zero, CC0)\r\n"
              b"\thttp://creativecommons.org/publicdomain/zero/1.0/\r\n")
KAYKIT_CC0 = b"KayKit : Furniture Bits (1.0)\nLicense: (Creative Commons Zero, CC0)\n"
GLTF, BIN, PNG, SVG, TTF = b'{"asset":{"version":"2.0"}}', b"\x00bin", b"\x89PNGtex", b"<svg/>", b"\x00\x01ttf"
ICON_LICENCE = (b"Icons provided under the Creative Commons 3.0 BY or CC0 if mentioned below.\n\n"
                b"- Lorc, http://lorcblog.blogspot.com\n- Viscious Speed, http://x - CC0\n\n"
                b'Please, include a mention "Icons made by {author}" in your derivative work.\n')
METADATA_PB = (b'name: "Press Start 2P"\ndesigner: "CodeMan38"\nlicense: "OFL"\n'
               b'category: "DISPLAY"\nfonts {\n  name: "Press Start 2P"\n  style: "normal"\n'
               b'  weight: 400\n  filename: "PressStart2P-Regular.ttf"\n'
               b'  copyright: "Copyright 2012 The Press Start 2P Project Authors"\n}\n')


def blob_sha(data):
    return hashlib.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


def zip_of(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


KAYKIT = "addons/kaykit_furniture_bits/Assets/"
KAYKIT_FILES = {"LICENSE.txt": KAYKIT_CC0, KAYKIT + "LICENSE.txt": KAYKIT_CC0,
                KAYKIT + "gltf/armchair.gltf": GLTF, KAYKIT + "gltf/armchair.bin": BIN,
                KAYKIT + "gltf/bed_double_A.gltf": GLTF, KAYKIT + "gltf/bed_double_A.bin": BIN,
                KAYKIT + "fbx/armchair.fbx": b"fbx",
                KAYKIT + "texture/furniturebits_texture.png": PNG,
                "addons/kaykit_furniture_bits/sample.png": PNG}
ICONS = {"lorc/broadsword.svg": SVG, "lorc/shield.svg": SVG, "viscious-speed/sword-clash.svg": SVG}


class Fake(BaseHTTPRequestHandler):
    bad_sha = {"on": False}

    def log_message(self, *a):
        pass

    def reply(self, obj=None, raw=None, code=200):
        body = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        base = "https://kenney.nl"
        p = self.path
        # Kenney: search and category pages list pack links; a pack page links its zip
        if p.startswith(("/assets?search=", "/assets/category:3D?search=")):
            links = "".join(f"<a href='{base}/assets/{s}'>x</a>" for s in
                            ("furniture-kit", "odd-pack")) if "furniture" in p or "kit" in p else ""
            return self.reply(raw=(f"<a href='{base}/assets/category:2D?search=x'>2D</a>"
                                   f"<a href='{base}/assets/tag:pixel'>p</a>{links}").encode())
        for slug in ("furniture-kit", "odd-pack"):
            if p == f"/assets/{slug}":
                return self.reply(raw=(
                    f"<meta property='og:title' content='Furniture Kit &middot; Kenney' />"
                    f"<meta property='og:image' content='{base}/media/pages/assets/{slug}/1/sample.png' />"
                    f"<meta property='og:description' content='Download this package (140 assets) "
                    f"for free, CC0 licensed!' /><a href='{base}/assets/category:3D'>3D</a>"
                    f"<a href='{base}/media/pages/assets/{slug}/ab-1/kenney_{slug}.zip'>Download</a>"
                ).encode())
        if p == "/media/pages/assets/furniture-kit/ab-1/kenney_furniture-kit.zip":
            return self.reply(raw=zip_of({"License.txt": KENNEY_CC0, "Models/GLB format/chair.glb": GLTF}))
        if p == "/media/pages/assets/odd-pack/ab-1/kenney_odd-pack.zip":
            return self.reply(raw=zip_of({"License.txt": b"All rights reserved", "a.png": PNG}))
        # GitHub API and raw files (KayKit, game-icons, Google Fonts)
        if p.startswith("/users/KayKit-Game-Assets/repos"):
            return self.reply([{"name": "KayKit-Furniture-Bits-1.0", "default_branch": "main",
                                "description": "Furniture Bits pack, CC0", "size": 3458},
                               {"name": "KayKit-Space-Base-Bits-1.0", "default_branch": "main",
                                "description": "Space base", "size": 5158}])
        if p.startswith("/repos/KayKit-Game-Assets/KayKit-Furniture-Bits-1.0/git/trees/main"):
            return self.reply({"truncated": False, "tree": [
                {"path": k, "type": "blob", "size": len(v),
                 "sha": "0" * 40 if self.bad_sha["on"] and k.endswith(".bin") else blob_sha(v)}
                for k, v in KAYKIT_FILES.items()]})
        if p.startswith("/KayKit-Game-Assets/KayKit-Furniture-Bits-1.0/main/"):
            rel = p.split("/main/", 1)[1]
            if rel in KAYKIT_FILES:
                return self.reply(raw=KAYKIT_FILES[rel])
        if p.startswith("/repos/game-icons/icons/git/trees/master"):
            return self.reply({"truncated": False, "tree": [
                {"path": k, "type": "blob", "size": len(v), "sha": blob_sha(v)} for k, v in ICONS.items()]})
        if p == "/game-icons/icons/master/license.txt":
            return self.reply(raw=ICON_LICENCE)
        if p.startswith("/game-icons/icons/master/"):
            rel = p.split("/master/", 1)[1]
            if rel in ICONS:
                return self.reply(raw=ICONS[rel])
        if p == "/metadata/fonts":
            return self.reply(raw=b")]}'\n" + json.dumps({"familyMetadataList": [
                {"family": "Press Start 2P", "category": "Display", "designers": ["CodeMan38"],
                 "popularity": 300},
                {"family": "Roboto", "category": "Sans Serif", "designers": ["Christian Robertson"],
                 "popularity": 1}]}).encode())
        if p == "/google/fonts/main/ofl/pressstart2p/METADATA.pb":
            return self.reply(raw=METADATA_PB)
        if p == "/google/fonts/main/ofl/pressstart2p/PressStart2P-Regular.ttf":
            return self.reply(raw=TTF)
        if p == "/google/fonts/main/ofl/pressstart2p/OFL.txt":
            return self.reply(raw=b"SIL OPEN FONT LICENSE Version 1.1")
        self.reply(raw=b"404", code=404)


class AssetSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        Fake.bad_sha["on"] = False
        self.root = tempfile.mkdtemp(prefix="kiln-src-")
        self.manifest("framework=kiln\nengine=godot\n")

    def manifest(self, text):
        with open(os.path.join(self.root, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write(text)

    def run_api(self, *args):
        env = dict(os.environ, KILN_ASSETS_FAKE=f"http://127.0.0.1:{self.server.server_port}")
        p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=self.root, env=env,
                           capture_output=True, text=True, timeout=60)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            self.fail(p.stdout + p.stderr)

    def prov(self, *parts):
        with open(os.path.join(self.root, "art", "library", *parts, "provenance.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)

    def test_kenney_pack_is_checked_against_its_licence_file(self):
        code, out = self.run_api("search", "kenney", "furniture", "--kind", "model")
        self.assertEqual(code, 0, out)
        self.assertEqual([r["id"] for r in out["results"]], ["furniture-kit", "odd-pack"])
        code, out = self.run_api("fetch", "kenney", "furniture-kit")
        self.assertEqual(code, 0, out)
        self.assertIn("Models/GLB format/chair.glb", out["files"])
        prov = self.prov("kenney", "furniture-kit")
        self.assertEqual((prov["licence"], prov["title"], prov["author"]),
                         ("CC0-1.0", "Furniture Kit", "Kenney"))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "art", "library", "kenney",
                                                    "furniture-kit", "evidence", "License.txt")))
        code, out = self.run_api("fetch", "kenney", "odd-pack")              # not CC0 inside
        self.assertNotEqual(code, 0)
        self.assertIn("License.txt", out["error"])
        self.assertFalse(os.path.exists(os.path.join(self.root, "art", "library", "kenney", "odd-pack")))
        self.assertEqual(os.listdir(os.path.join(self.root, "art", "library", "kenney")),
                         ["furniture-kit"])                                   # no partial folder

    def test_kaykit_from_github_with_blob_checksums(self):
        code, out = self.run_api("search", "kaykit", "furniture", "--kind", "model")
        self.assertEqual([r["id"] for r in out["results"]], ["furniture-bits"], out)
        code, out = self.run_api("fetch", "kaykit", "furniture-bits", "--only", "armchair")
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(out["files"]), ["LICENSE.txt", "gltf/armchair.bin",
                                                "gltf/armchair.gltf",
                                                "texture/furniturebits_texture.png"])
        self.assertEqual(self.prov("kaykit", "furniture-bits")["licence"], "CC0-1.0")
        Fake.bad_sha["on"] = True
        code, out = self.run_api("fetch", "kaykit", "furniture-bits", "--only", "bed")
        self.assertNotEqual(code, 0)
        self.assertIn("checksum", out["error"])

    def test_game_icons_carry_their_author_and_licence(self):
        code, out = self.run_api("search", "gameicons", "sword", "--kind", "icon")
        self.assertEqual(sorted(r["id"] for r in out["results"]),
                         ["lorc/broadsword", "viscious-speed/sword-clash"], out)
        code, out = self.run_api("fetch", "gameicons", "lorc/broadsword")
        self.assertEqual(code, 0, out)
        prov = self.prov("gameicons", "lorc", "broadsword")
        self.assertEqual((prov["licence"], prov["author"]), ("CC-BY-3.0", "Lorc"))
        self.assertEqual(prov["attribution"],
                         "Icons made by Lorc. Available on https://game-icons.net")
        code, out = self.run_api("fetch", "gameicons", "viscious-speed/sword-clash")
        self.assertEqual(self.prov("gameicons", "viscious-speed", "sword-clash")["licence"], "CC0-1.0")
        self.manifest("framework=kiln\nasset_libraries=cc0\n")
        code, out = self.run_api("fetch", "gameicons", "lorc/shield")
        self.assertNotEqual(code, 0)                                         # CC BY not opted in
        code, out = self.run_api("search", "gameicons", "sword", "--kind", "icon")
        self.assertEqual([r["id"] for r in out["results"]], ["viscious-speed/sword-clash"])

    def test_google_fonts_ship_their_licence_file(self):
        code, out = self.run_api("search", "googlefonts", "press start", "--kind", "font")
        self.assertEqual([r["id"] for r in out["results"]], ["pressstart2p"], out)
        code, out = self.run_api("fetch", "googlefonts", "pressstart2p")
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(out["files"]), ["OFL.txt", "PressStart2P-Regular.ttf"])
        prov = self.prov("googlefonts", "pressstart2p")
        self.assertEqual((prov["licence"], prov["author"]), ("OFL-1.1", "CodeMan38"))

    def test_import_records_files_the_user_downloaded(self):
        src = tempfile.mkdtemp(prefix="kiln-dl-")
        with open(os.path.join(src, "Knight.glb"), "wb") as fh:
            fh.write(GLTF)
        with open(os.path.join(src, "License.txt"), "w", encoding="utf-8") as fh:
            fh.write("Quaternius Asset License")
        code, out = self.run_api("import", src, "--source", "quaternius", "--id", "knight",
                                 "--url", "https://quaternius.com/packs/knight.html")
        self.assertNotEqual(code, 0)                       # QAL is a custom licence: opt-in only
        self.assertIn("not allowed", out["error"])
        self.manifest("framework=kiln\nasset_libraries=sharealike\n")
        code, out = self.run_api("import", src, "--source", "quaternius", "--id", "knight",
                                 "--url", "https://quaternius.com/packs/knight.html")
        self.assertEqual(code, 0, out)
        prov = self.prov("quaternius", "knight")
        self.assertEqual(prov["licence"], "LicenseRef-Quaternius-QAL-1.0")
        self.assertTrue(any("redistribut" in f for f in prov["flags"]), prov["flags"])
        self.assertEqual(prov["evidence"], ["evidence/License.txt"])
        os.remove(os.path.join(src, "License.txt"))
        code, out = self.run_api("import", src, "--source", "kenney", "--id", "mini",
                                 "--url", "https://kenney.nl/assets/mini")
        self.assertEqual(code, 0, out)
        self.assertIn("licence declared by the user (no licence file)", self.prov("kenney", "mini")["flags"])
        code, out = self.run_api("import", src, "--source", "itch", "--id", "x", "--url", "u")
        self.assertIn("--licence", out["error"])                 # unknown source: say the licence
        shutil.rmtree(src)

    def test_special_ids_never_touch_the_library(self):
        # KILN-REV-01 (review 2026-10-21): --id .. made the destination art/library itself, and
        # replacing it deleted every pack. Every special or escaping id must fail before anything
        # is written or removed, on a throwaway library with sentinel packs.
        lib = os.path.join(self.root, "art", "library")
        sentinels = {os.path.join(lib, "kenney", "mini", "keep.txt"): "kenney pack",
                     os.path.join(lib, "polyhaven", "rock", "keep.txt"): "other source"}
        for path, text in sentinels.items():
            os.makedirs(os.path.dirname(path))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        before = sorted(os.path.relpath(os.path.join(d, f), lib)
                        for d, _, fs in os.walk(lib) for f in fs)
        src = tempfile.mkdtemp(prefix="kiln-dl-")
        with open(os.path.join(src, "pack.glb"), "wb") as fh:
            fh.write(GLTF)
        for bad in ("..", ".", "mini/..", "../kenney", "x/../../polyhaven"):
            code, out = self.run_api("import", src, "--source", "kenney", "--id", bad,
                                     "--url", "https://kenney.nl/assets/x")
            self.assertNotEqual(code, 0, (bad, out))
            after = sorted(os.path.relpath(os.path.join(d, f), lib)
                           for d, _, fs in os.walk(lib) for f in fs)
            self.assertEqual(after, before, bad)
        for path, text in sentinels.items():
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), text)
        code, out = self.run_api("import", src, "--source", "kenney", "--id", "mini",
                                 "--url", "https://kenney.nl/assets/mini")      # a real update
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.isfile(os.path.join(lib, "kenney", "mini", "pack.glb")))
        self.assertTrue(os.path.isfile(os.path.join(lib, "polyhaven", "rock", "keep.txt")))
        shutil.rmtree(src)

    def test_credits_md_lists_required_lines_fonts_and_thanks(self):
        self.run_api("fetch", "gameicons", "lorc/broadsword")
        self.run_api("fetch", "kenney", "furniture-kit")
        self.run_api("fetch", "googlefonts", "pressstart2p")
        p = subprocess.run([sys.executable, "-B", LICENSES, "build"], cwd=self.root,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        with open(os.path.join(self.root, "production", "CREDITS.md"), encoding="utf-8") as fh:
            credits = fh.read()
        self.assertIn("Icons made by Lorc. Available on https://game-icons.net", credits)
        self.assertIn("Press Start 2P", credits)
        self.assertIn("SIL Open Font License 1.1", credits)
        self.assertIn("Kenney", credits)
        with open(os.path.join(self.root, "production", "LICENSES.md"), encoding="utf-8") as fh:
            table = fh.read()
        self.assertEqual(table.count("PressStart2P-Regular.ttf"), 0)          # one row per item
        self.assertIn("googlefonts: ", table)


if __name__ == "__main__":
    unittest.main()
