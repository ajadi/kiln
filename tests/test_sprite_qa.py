"""Tests for plugins/kiln/skills/art-2d/scripts/sprite_qa.py (synthetic sprites, unittest).

g2 row 47 (artist-2d, a Mega Drive 9-bit sprite in a rug texture): contrast compared the sprite's
mean with the field, so an outlined blue sprite failed; no cluster-cleanliness check; colours
snapped to a hardware grid had their distance from the art bible reported by hand.
"""

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
                      "scripts", "sprite_qa.py")


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=60)
    return p.returncode, json.loads(p.stdout)


class SpriteQa(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-sprite-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def save(self, name, arr):
        path = os.path.join(self.root, name)
        Image.fromarray(np.asarray(arr, np.uint8), "RGBA").save(path)
        return path

    def outlined(self, body=(40, 80, 200), line=(250, 250, 250)):
        a = np.zeros((20, 20, 4), np.uint8)
        a[4:16, 4:16] = (*line, 255)
        a[5:15, 5:15] = (*body, 255)
        return a

    def test_contrast_reads_the_edge_not_the_mean(self):
        sprite = self.save("s.png", self.outlined(body=(30, 60, 160), line=(10, 10, 10)))
        code, res = run("contrast", sprite, "--bg", "#6e6e6e", "--gate", "mean")
        self.assertEqual(code, 1, res)
        code, res = run("contrast", sprite, "--bg", "#6e6e6e")
        self.assertEqual(code, 0, res)                      # default gate: the silhouette edge
        self.assertGreater(res["edge_contrast"], 3)
        self.assertEqual(len(res["regions"]), 2)            # body colour and outline colour
        code, res = run("contrast", sprite, "--bg", "#6e6e6e", "--gate", "worst")
        self.assertEqual(code, 1, res)
        self.assertIn("1e3ca0", res["problems"][0])          # the body colour fails

    def test_clusters_find_orphans_and_outline_gaps(self):
        clean = self.save("clean.png", self.outlined())
        code, res = run("clusters", clean)
        self.assertEqual(code, 0, res)
        a = self.outlined()
        a[9, 9] = (255, 0, 0, 255)                          # orphan pixel inside the body
        a[4, 10] = (40, 80, 200, 255)                       # body colour leaks through the outline
        code, res = run("clusters", self.save("dirty.png", a))
        self.assertEqual(code, 1, res)
        self.assertEqual(res["orphans"], 1)
        self.assertEqual(res["outline_gaps"], 1)

    def test_hardware_grid_and_distance_to_the_bible(self):
        with open(os.path.join(self.root, "bible.hex"), "w", encoding="utf-8") as fh:
            fh.write("2850c8\nfafafa\n")
        on_grid = self.outlined(body=(36, 72, 218), line=(255, 255, 255))   # 3-bit levels
        code, res = run("palette", self.save("md.png", on_grid), "--bits", "3", "--palette",
                        os.path.join(self.root, "bible.hex"), "--max-distance", "40")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["off_grid_colors"], 0)
        dist = {d["color"]: d["distance"] for d in res["distances"]}
        self.assertAlmostEqual(dist["#2448da"], 20.1, places=1)
        off = self.outlined(body=(40, 80, 200))
        code, res = run("palette", self.save("off.png", off), "--bits", "3")
        self.assertEqual(code, 1, res)
        self.assertGreater(res["off_grid_colors"], 0)


if __name__ == "__main__":
    unittest.main()
