"""Tests for plugins/kiln/skills/acceptance/scripts/frames.py (numpy + Pillow).

g2 row 92 / 0.7.0 review: the level scene was replaced while a re-acceptance ran and nobody saw
it; art regressions were found only by the user's eye.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "acceptance",
                      "scripts", "frames.py")


def run(cwd, *args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=cwd, capture_output=True,
                       text=True, timeout=120)
    return p.returncode, json.loads(p.stdout)


def scene(seed=0, square=False, noise=0):
    rng = np.random.default_rng(seed)
    a = np.zeros((240, 320, 3), np.float32)
    a[..., 0] = np.linspace(40, 200, 320)[None, :]
    a[..., 1] = np.linspace(60, 120, 240)[:, None]
    a[..., 2] = 90
    a[100:160, 40:100] = (200, 180, 60)                 # a landmark
    if square:
        a[30:70, 220:270] = (250, 250, 250)            # something new in the frame
    if noise:
        a += rng.normal(0, noise, a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


class Frames(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-frames-")
        os.makedirs(os.path.join(self.root, "cap"))

    def shot(self, name, img):
        path = os.path.join(self.root, "cap", name)
        img.save(path)
        return path

    def test_baseline_compare_accept(self):
        self.shot("plaza_ref.png", scene())
        code, res = run(self.root, "baseline", "cap/plaza_ref.png", "--scene", "plaza")
        self.assertEqual(code, 0, res)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "production", "baselines",
                                                    "plaza", "plaza_ref.png")))
        self.shot("plaza_ref.png", scene(noise=2))          # capture noise only
        code, res = run(self.root, "compare", "cap/plaza_ref.png", "--scene", "plaza")
        self.assertEqual(code, 0, res)
        self.shot("plaza_ref.png", scene(square=True))
        code, res = run(self.root, "compare", "cap/plaza_ref.png", "--scene", "plaza",
                        "--out", "diff")
        self.assertEqual(code, 1, res)
        region = res["results"][0]["regions"][0]
        for got, want in zip(region["bbox"], [220, 30, 50, 40]):   # the 3x3 blur adds 1 px
            self.assertLessEqual(abs(got - want), 2, region)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "diff", "plaza_ref_diff.png")))
        code, res = run(self.root, "accept", "cap/plaza_ref.png", "--scene", "plaza",
                        "--why", "TASK-034 adds the bank sign")
        self.assertEqual(code, 0, res)
        code, res = run(self.root, "compare", "cap/plaza_ref.png", "--scene", "plaza")
        self.assertEqual(code, 0, res)
        with open(os.path.join(self.root, "production", "baselines", "plaza", "HISTORY.md"),
                  encoding="utf-8") as fh:
            self.assertIn("TASK-034 adds the bank sign", fh.read())

    def test_missing_baseline_and_size_change(self):
        self.shot("a.png", scene())
        code, res = run(self.root, "compare", "cap/a.png", "--scene", "x")
        self.assertEqual(res["results"][0]["verdict"], "NOT ASSESSED")
        run(self.root, "baseline", "cap/a.png", "--scene", "x")
        self.shot("a.png", scene().resize((160, 120)))
        code, res = run(self.root, "compare", "cap/a.png", "--scene", "x")
        self.assertEqual(code, 1)
        self.assertIn("size", res["results"][0]["problems"][0])


if __name__ == "__main__":
    unittest.main()
