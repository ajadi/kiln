"""Tests for the art-2d skill's tiles.py: a 2D map image cut into a deduplicated tileset and a
Tiled JSON map (S08, /kiln:sprites map route)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "art-2d",
                      "scripts", "tiles.py")
H, V = 0x80000000, 0x40000000  # Tiled flip flags (top bits of a GID)


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=120)
    return p.returncode, json.loads(p.stdout)


def tile(seed):
    """An 8x8 RGBA tile with no symmetry, so every flip is a different picture."""
    a = np.random.default_rng(seed).integers(0, 256, (8, 8, 4), dtype=np.uint8)
    a[..., 3] = 255
    return a


class Extract(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-tiles-")
        a, b = tile(1), tile(2)
        rows = [[a, b, a[:, ::-1]], [a[::-1, :], a[::-1, ::-1], b]]
        self.image = os.path.join(self.root, "map.png")
        Image.fromarray(np.vstack([np.hstack(r) for r in rows]), "RGBA").save(self.image)
        self.out = os.path.join(self.root, "out")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_flipped_copies_become_one_tile_with_tiled_flip_flags(self):
        code, res = run("extract", self.image, "--tile", "8", "--flips", "--out", self.out)
        self.assertEqual(code, 0, res)
        self.assertEqual((res["unique"], res["cells"]), (2, 6))
        with open(os.path.join(self.out, "map.tmj"), encoding="utf-8") as fh:
            tmj = json.load(fh)
        self.assertEqual((tmj["orientation"], tmj["width"], tmj["height"], tmj["tilewidth"]),
                         ("orthogonal", 3, 2, 8))
        self.assertEqual(tmj["layers"][0]["data"], [1, 2, 1 | H, 1 | V, 1 | H | V, 2])
        ts = tmj["tilesets"][0]
        self.assertEqual((ts["firstgid"], ts["tilecount"], ts["image"]), (1, 2, "tileset.png"))
        sheet = np.asarray(Image.open(os.path.join(self.out, "tileset.png")).convert("RGBA"))
        self.assertEqual(sheet.shape[0] * sheet.shape[1], 2 * 8 * 8)
        self.assertTrue((sheet[:8, :8] == tile(1)).all())

    def test_without_flips_every_flip_is_its_own_tile(self):
        code, res = run("extract", self.image, "--tile", "8", "--out", self.out)
        self.assertEqual(code, 0, res)
        self.assertEqual(res["unique"], 5)

    def test_tolerance_merges_lossy_copies(self):
        a = tile(1)
        noisy = np.clip(a.astype(int) + np.random.default_rng(3).integers(-3, 4, a.shape), 0,
                        255).astype(np.uint8)
        noisy[..., 3] = 255
        Image.fromarray(np.hstack([a, noisy]), "RGBA").save(self.image)
        code, res = run("extract", self.image, "--tile", "8", "--out", self.out)
        self.assertEqual(res["unique"], 2)
        code, res = run("extract", self.image, "--tile", "8", "--tolerance", "4", "--out", self.out)
        self.assertEqual(res["unique"], 1)

    def test_size_that_is_not_a_tile_multiple_fails(self):
        Image.new("RGBA", (20, 16)).save(self.image)
        code, res = run("extract", self.image, "--tile", "8", "--out", self.out)
        self.assertEqual(code, 1, res)
        self.assertEqual(res["verdict"], "fail")
        self.assertIn("20x16", res["problems"][0])


if __name__ == "__main__":
    unittest.main()
