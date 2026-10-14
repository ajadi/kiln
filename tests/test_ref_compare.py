"""Tests for the acceptance skill's ref_compare.py: fidelity to a reference image in numbers
(K03). numpy + Pillow; synthetic images with known answers."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "acceptance",
                      "scripts", "ref_compare.py")


def run(cwd, *args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=cwd, capture_output=True,
                       text=True, timeout=120)
    return p.returncode, json.loads(p.stdout)


def picture(scale=1, dark_pool=False, swap_palette=False, lamp=True):
    """A 2D scene: sky band, ground, a house, a lamp pool. `scale` multiplies the size."""
    h, w = 120 * scale, 160 * scale
    a = np.zeros((h, w, 3), np.float32)
    a[: h // 2] = (90, 140, 200) if not swap_palette else (200, 90, 160)   # sky
    a[h // 2:] = (70, 110, 60)                                             # grass
    a[40 * scale:80 * scale, 30 * scale:70 * scale] = (150, 100, 70)       # house
    a[50 * scale:60 * scale, 40 * scale:50 * scale] = (240, 220, 140)      # lit window
    if lamp:
        yy, xx = np.mgrid[0:h, 0:w]
        pool = np.exp(-(((yy - 95 * scale) / (12 * scale)) ** 2 + ((xx - 120 * scale) / (18 * scale)) ** 2))
        a += (0.0 if dark_pool else 90.0) * pool[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


class RefCompare(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-refcmp-")
        self.ref = os.path.join(self.root, "ref.png")
        picture().save(self.ref)

    def ours(self, name, **kw):
        path = os.path.join(self.root, name)
        picture(scale=2, **kw).save(path)          # our capture is twice the reference size
        return path

    def test_a_faithful_capture_passes_every_axis(self):
        code, res = run(self.root, "report", "--ref", self.ref, "--ours", self.ours("same.png"),
                        "--points", "window:45,55;grass:10,110", "--region", "lamp:100,80,40,30")
        self.assertEqual((code, res["verdict"]), (0, "PASS"), res)
        self.assertAlmostEqual(res["scale"], 2.0)
        for axis in ("values", "palette", "tones"):
            self.assertEqual(res[axis]["verdict"], "PASS", (axis, res[axis]))

    def test_a_missing_light_pool_fails_values_and_ranks_its_region_first(self):
        code, res = run(self.root, "report", "--ref", self.ref,
                        "--ours", self.ours("dark.png", dark_pool=True),
                        "--region", "house:30,40,40,40", "--region", "lamp:100,80,40,30")
        self.assertEqual((code, res["verdict"]), (1, "FAIL"), res)
        self.assertEqual(res["values"]["verdict"], "FAIL")
        self.assertEqual(res["regions"][0]["name"], "lamp")
        self.assertLess(res["regions"][0]["brightness_ratio"], 0.9)

    def test_a_wrong_palette_fails_and_names_the_missing_colour(self):
        code, res = run(self.root, "palette", "--ref", self.ref,
                        "--ours", self.ours("pink.png", swap_palette=True))
        self.assertEqual((code, res["verdict"]), (1, "FAIL"), res)
        self.assertLess(res["near_share"], 0.8)
        self.assertTrue(res["missing"], res)

    def test_tones_at_points(self):
        code, res = run(self.root, "tones", "--ref", self.ref,
                        "--ours", self.ours("pink2.png", swap_palette=True), "--points",
                        "sky:80,20;grass:10,110")
        rows = {r["name"]: r for r in res["points"]}
        self.assertEqual(rows["grass"]["verdict"], "PASS")
        self.assertEqual(rows["sky"]["verdict"], "FAIL")
        self.assertGreater(rows["sky"]["delta_e"], 10)

    def test_side_writes_magnified_pairs_with_rulers(self):
        out = os.path.join(self.root, "side")
        code, res = run(self.root, "side", "--ref", self.ref, "--ours", self.ours("s.png"),
                        "--region", "house:30,40,40,40", "--out", out)
        self.assertEqual(code, 0, res)
        img = Image.open(res["files"][0])
        self.assertGreaterEqual(img.width, 2 * 40 * 4)   # both crops, magnified at least 4x


if __name__ == "__main__":
    unittest.main()
