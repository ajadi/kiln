"""Tests for plugins/kiln/skills/image-to-model/scripts/value_bands.py (Pillow + numpy)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "image-to-model", "scripts", "value_bands.py")


def figure(path, dark_rows=(), size=(200, 400), box=(60, 40, 140, 360), light=230, dark=40):
    """A light rectangle 'body' on a transparent canvas; dark_rows are (f0, f1) of its height."""
    img = np.zeros((size[1], size[0], 4), np.uint8)
    x0, y0, x1, y1 = box
    img[y0:y1, x0:x1] = (light, light, light, 255)
    h = y1 - y0
    for f0, f1 in dark_rows:
        img[y0 + int(f0 * h):y0 + int(f1 * h), x0:x1, :3] = dark
    Image.fromarray(img).save(path)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=60)
    return p.returncode, json.loads(p.stdout)


class ValueBands(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="kiln-vb-")

    def p(self, name):
        return os.path.join(self.d, name)

    def test_missing_dark_joints_flagged(self):
        ref = figure(self.p("ref.png"), dark_rows=[(0.45, 0.55), (0.9, 1.0)])
        tube = figure(self.p("tube.png"))  # one white tube: no knee, no sole
        code, rep = run(ref, tube, "--bands", "10")
        self.assertEqual(code, 1)
        flagged = {tuple(f) for f in rep["flagged"]}
        self.assertIn((0.9, 1.0), flagged)
        self.assertTrue(any(f[0] >= 0.4 and f[1] <= 0.6 for f in flagged), flagged)
        self.assertEqual(rep["bands"][-1]["flag"], "model lighter")

    def test_matching_pattern_passes_across_scale_and_shading(self):
        ref = figure(self.p("ref.png"), dark_rows=[(0.3, 0.4)])
        # rendered at another size and framing, with grey plates instead of white: Otsu adapts
        model = figure(self.p("model.png"), dark_rows=[(0.3, 0.4)], size=(300, 500),
                       box=(100, 20, 220, 500), light=170, dark=60)
        code, rep = run(ref, model, "--bands", "10")
        self.assertEqual(code, 0, rep["flagged"])
        self.assertLess(abs(rep["light_fraction"]["ref"] - rep["light_fraction"]["model"]), 0.03)

    def test_xlim_and_errors(self):
        ref = figure(self.p("ref.png"))
        code, rep = run(ref, ref, "--xlim", "0.05")
        self.assertEqual(code, 0)
        opaque = self.p("opaque.png")
        Image.new("RGBA", (50, 50), (255, 255, 255, 255)).save(opaque)
        code, rep = run(ref, opaque)
        self.assertEqual(code, 1)
        self.assertIn("transparent", rep["error"])


if __name__ == "__main__":
    unittest.main()
