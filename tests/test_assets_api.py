"""Tests for the asset-libraries assets_api.py against a local fake of Poly Haven and ambientCG
(shapes recorded live 2026-10-19), and for licenses.py reading library provenance."""

import hashlib
import io
import json
import os
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
GLTF, TEX = b'{"asset": {"version": "2.0"}}', b"\xff\xd8jpeg"


def zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Bricks097_1K-JPG_Color.jpg", TEX)
        z.writestr("Bricks097.png", b"png")
    return buf.getvalue()


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, obj=None, raw=None):
        body = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}"
        p = self.path
        if p.startswith("/assets?type=textures"):
            return self.reply({"red_brick": {"name": "Red Brick", "tags": ["brick", "wall"],
                                             "categories": ["brick"], "download_count": 9,
                                             "thumbnail_url": base + "/thumb.png"},
                               "grass": {"name": "Grass", "tags": ["grass"], "categories": []}})
        if p.startswith("/info/red_brick"):
            return self.reply({"name": "Red Brick", "type": 1, "authors": {"Rob Tuytel": "All"},
                               "thumbnail_url": base + "/thumb.png"})
        if p.startswith("/files/red_brick"):
            return self.reply({"gltf": {"1k": {"gltf": {
                "url": base + "/dl/red_brick_1k.gltf", "md5": hashlib.md5(GLTF).hexdigest(),
                "include": {"textures/red_brick_diff_1k.jpg": {
                    "url": base + "/dl/red_brick_diff_1k.jpg", "md5": hashlib.md5(TEX).hexdigest()}}}}}})
        if p.startswith("/dl/red_brick_1k.gltf"):
            return self.reply(raw=GLTF)
        if p.startswith("/dl/red_brick_diff_1k.jpg"):
            return self.reply(raw=TEX)
        if p.startswith("/api/v3/assets"):
            return self.reply({"assets": [{"id": "Bricks097", "downloads": [
                {"attributes": "1K-JPG", "url": base + "/get?file=Bricks097_1K-JPG.zip"}],
                "previews": [{"url": base + "/p/Bricks097.jpg"}]}]})
        if p.startswith("/get?file=Bricks097_1K-JPG.zip"):
            return self.reply(raw=zip_bytes())
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


class AssetsApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-lib-")
        self.manifest("framework=kiln\nengine=godot\n")

    def manifest(self, text):
        with open(os.path.join(self.root, "manifest.md"), "w", encoding="utf-8") as fh:
            fh.write(text)

    def run_api(self, *args):
        env = dict(os.environ, KILN_ASSETS_FAKE=f"http://127.0.0.1:{self.server.server_port}")
        p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=self.root, env=env,
                           capture_output=True, text=True, timeout=60)
        return p.returncode, json.loads(p.stdout)

    def test_search_filters_by_words_and_licence(self):
        code, out = self.run_api("search", "all", "brick wall", "--kind", "texture")
        self.assertEqual(code, 0, out)
        ids = [(r["source"], r["id"]) for r in out["results"]]
        self.assertIn(("polyhaven", "red_brick"), ids)
        self.assertIn(("ambientcg", "Bricks097"), ids)
        self.assertNotIn(("polyhaven", "grass"), ids)

    def test_fetch_with_checksums_provenance_and_licence_registry(self):
        code, out = self.run_api("fetch", "polyhaven", "red_brick", "--res", "1k")
        self.assertEqual(code, 0, out)
        folder = os.path.join(self.root, "art", "library", "polyhaven", "red_brick")
        self.assertTrue(os.path.isfile(os.path.join(folder, "textures", "red_brick_diff_1k.jpg")))
        with open(os.path.join(folder, "provenance.json"), encoding="utf-8") as fh:
            prov = json.load(fh)
        self.assertEqual((prov["kind"], prov["licence"], prov["author"]), ("library", "CC0-1.0", "Rob Tuytel"))
        self.assertTrue(os.path.isfile(os.path.join(folder, "evidence", "info.json")))
        code, out = self.run_api("fetch", "ambientcg", "Bricks097", "--res", "1k")
        self.assertEqual(code, 0, out)
        self.assertIn("Bricks097_1K-JPG_Color.jpg", out["files"])
        p = subprocess.run([sys.executable, "-B", LICENSES, "build"], cwd=self.root,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        with open(os.path.join(self.root, "production", "LICENSES.md"), encoding="utf-8") as fh:
            table = fh.read()
        self.assertIn("polyhaven: https://polyhaven.com/a/red_brick", table)
        self.assertIn("Created using Bricks097 from ambientCG.com", table)  # their attribution line
        self.assertNotIn("generated: assets_api.py", table)

    def test_off_downloads_nothing(self):
        self.manifest("framework=kiln\nasset_libraries=off\n")
        code, out = self.run_api("fetch", "polyhaven", "red_brick", "--res", "1k")
        self.assertNotEqual(code, 0)
        self.assertIn("not allowed", out["error"])
        self.assertFalse(os.path.exists(os.path.join(self.root, "art")))


if __name__ == "__main__":
    unittest.main()
