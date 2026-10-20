"""Tests for plugins/kiln/skills/asset-pipeline/scripts/asset_budget.py (stdlib + Pillow).

g2 rows 101, 103, 106: what an asset costs (triangles, textures, VRAM) was worked out by hand
and only after an on-screen run; 12 crowd looks as 12 glbs would have loaded 12 atlas copies.
"""

import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "asset-pipeline", "scripts", "asset_budget.py")


def make_glb(path, tris=12, tex=(64, 32), joints=3, names=None):
    png = io.BytesIO()
    Image.new("RGBA", tex, (200, 100, 50, 255)).save(png, "PNG")
    png = png.getvalue()
    idx = struct.pack(f"<{tris * 3}H", *([0, 1, 2] * tris))
    pos = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    pad = lambda b: b + b"\0" * (-len(b) % 4)
    blob = pad(idx) + pad(pos) + pad(png)
    o1, o2 = len(pad(idx)), len(pad(idx)) + len(pad(pos))
    gltf = {"asset": {"version": "2.0"},
            "buffers": [{"byteLength": len(blob)}],
            "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(idx)},
                            {"buffer": 0, "byteOffset": o1, "byteLength": len(pos)},
                            {"buffer": 0, "byteOffset": o2, "byteLength": len(png)}],
            "accessors": [{"bufferView": 0, "componentType": 5123, "count": tris * 3,
                           "type": "SCALAR"},
                          {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"}],
            "images": [{"bufferView": 2, "mimeType": "image/png"}],
            "textures": [{"source": 0}],
            "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 1}, "indices": 0,
                                        "material": 0}]}],
            "skins": [{"joints": list(range(joints))}],
            "nodes": [{"mesh": 0, **({"name": n} if n else {})} for n in (names or [None, None])],
            "scenes": [{"nodes": [0, 1]}]}
    js = json.dumps(gltf).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(blob), 0x004E4942) + blob
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)


def run(cwd, *args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=cwd, capture_output=True,
                       text=True, timeout=60)
    return p.returncode, json.loads(p.stdout)


class AssetBudget(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-budget-")
        os.makedirs(os.path.join(self.root, "assets", "npc"))
        os.makedirs(os.path.join(self.root, "assets", "props"))
        make_glb(os.path.join(self.root, "assets", "npc", "goran.glb"), tris=12, tex=(64, 32))
        make_glb(os.path.join(self.root, "assets", "props", "cup.glb"), tris=4, tex=(16, 16),
                 joints=0)

    def test_lod_levels_count_once(self):
        # LOD research 2026-10-19: a glb with crate_LOD0 and crate_LOD1 counted both levels as
        # drawn (about 1.9x the real cost); only one level is drawn at a time.
        path = os.path.join(self.root, "assets", "props", "crate.glb")
        make_glb(path, tris=12, joints=0, names=["crate_LOD0", "crate_LOD1"])
        code, res = run(self.root, "assets/props/crate.glb")
        row = res["assets"][0]
        self.assertEqual(row["triangles"], 12)
        self.assertEqual(row["draw_calls"], 1)
        self.assertEqual(row["lods"], {"crate": [12, 12]})

    def test_counts(self):
        code, res = run(self.root, "assets/**/*.glb")
        rows = {os.path.basename(r["file"]): r for r in res["assets"]}
        g = rows["goran.glb"]
        self.assertEqual(g["triangles"], 24)          # 12 per instance, the mesh used twice
        self.assertEqual(g["unique_triangles"], 12)
        self.assertEqual(g["draw_calls"], 2)
        self.assertEqual(g["materials"], 1)
        self.assertEqual(g["bones"], 3)
        self.assertEqual(g["textures"][0]["size"], [64, 32])
        self.assertAlmostEqual(g["vram_mb_uncompressed"], 64 * 32 * 4 * 4 / 3 / 2 ** 20, places=4)
        self.assertEqual(res["totals"]["files"], 2)

    def test_budgets_by_glob(self):
        with open(os.path.join(self.root, "budgets.json"), "w", encoding="utf-8") as fh:
            json.dump({"assets/npc/*.glb": {"triangles": 20, "bones": 60},
                       "*": {"triangles": 5000, "texture_px": 2048}}, fh)
        code, res = run(self.root, "assets/**/*.glb", "--budgets", "budgets.json")
        self.assertEqual(code, 1, res)
        rows = {os.path.basename(r["file"]): r for r in res["assets"]}
        self.assertEqual(rows["goran.glb"]["verdict"], "FAIL")
        self.assertIn("triangles 24 > 20", rows["goran.glb"]["problems"][0])
        self.assertEqual(rows["cup.glb"]["verdict"], "PASS")


class AssetBudgetEdges(unittest.TestCase):
    """Bug hunt 2026-10-20: embedded .gltf textures read 0, no file matched read PASS, a broken
    GLB crashed the run."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-budget-")

    def gltf(self, name, images, buffers=None, views=None):
        data = {"asset": {"version": "2.0"}, "images": images, "buffers": buffers or [],
                "bufferViews": views or [], "meshes": [], "nodes": []}
        with open(os.path.join(self.root, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def test_embedded_textures_of_a_gltf_are_measured(self):
        import base64
        png = io.BytesIO()
        Image.new("RGBA", (4096, 2048), (9, 9, 9, 255)).save(png, "PNG")
        uri = "data:image/png;base64," + base64.b64encode(png.getvalue()).decode()
        self.gltf("a.gltf", [{"uri": uri}])
        buf = "data:application/octet-stream;base64," + base64.b64encode(png.getvalue()).decode()
        self.gltf("b.gltf", [{"bufferView": 0, "mimeType": "image/png"}],
                  [{"byteLength": len(png.getvalue()), "uri": buf}],
                  [{"buffer": 0, "byteOffset": 0, "byteLength": len(png.getvalue())}])
        with open(os.path.join(self.root, "budgets.json"), "w", encoding="utf-8") as fh:
            json.dump({"*": {"texture_px": 1024}}, fh)
        code, res = run(self.root, "*.gltf", "--budgets", "budgets.json")
        self.assertEqual(code, 1, res)
        for row in res["assets"]:
            self.assertEqual(row["texture_px"], 4096, row)
            self.assertEqual(row["verdict"], "FAIL")

    def test_nothing_matched_or_a_broken_glb_is_not_assessed(self):
        code, res = run(self.root, "assets/**/*.glb")
        self.assertEqual((code, res["verdict"]), (2, "NOT ASSESSED"), res)
        with open(os.path.join(self.root, "cut.glb"), "wb") as fh:
            fh.write(struct.pack("<III", 0x46546C67, 2, 100))   # a header and nothing else
        code, res = run(self.root, "*.glb")
        self.assertEqual((code, res["verdict"]), (2, "NOT ASSESSED"), res)


if __name__ == "__main__":
    unittest.main()
