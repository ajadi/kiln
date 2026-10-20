"""Tests for art-2d pixelfix.py: a real 16x16 sprite is upscaled the way image models draw
"pixel art" (8x blocks at an offset, noise, soft edges, extra colours); snap must find the grid
and give back the sprite at its true size with its own palette."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageFilter

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "art-2d",
                      "scripts", "pixelfix.py")
PALETTE = [(20, 20, 30), (200, 60, 50), (240, 200, 80), (60, 120, 200), (90, 170, 80),
           (250, 250, 240)]


def sprite():
    rng = np.random.default_rng(3)
    s = np.zeros((16, 16, 4), np.uint8)
    for y in range(2, 14):
        for x in range(3, 13):
            s[y, x, :3] = PALETTE[rng.integers(0, len(PALETTE))]
            s[y, x, 3] = 255
    return s


def generated(s, scale=8, offset=(3, 5)):
    big = np.zeros((16 * scale + offset[1] + 4, 16 * scale + offset[0] + 2, 4), np.uint8)
    up = np.repeat(np.repeat(s, scale, 0), scale, 1)
    big[offset[1]:offset[1] + up.shape[0], offset[0]:offset[0] + up.shape[1]] = up
    img = Image.fromarray(big).filter(ImageFilter.GaussianBlur(0.8))
    arr = np.asarray(img).astype(int)
    noise = np.random.default_rng(0).integers(-12, 13, arr.shape)
    noise[..., 3] = 0
    return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))


class PixelFix(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="kiln-pix-")
        self.truth = sprite()
        self.src = os.path.join(self.d, "ai.png")
        generated(self.truth).save(self.src)

    def run_cmd(self, *args):
        p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                           timeout=120)
        return p.returncode, json.loads(p.stdout)

    def test_grid_is_found(self):
        code, out = self.run_cmd("grid", self.src)
        self.assertEqual(out["scale"], [8, 8], out)
        self.assertEqual(out["offset"], [3, 5], out)

    def test_snap_returns_the_true_sprite(self):
        dst = os.path.join(self.d, "hero.png")
        code, out = self.run_cmd("snap", self.src, "--out", dst, "--colors", "6", "--preview", "4")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["size"], [16, 16], out)
        self.assertGreater(out["colours_before"], 100)
        self.assertLessEqual(out["colours_after"], 6)
        got = np.asarray(Image.open(dst).convert("RGBA")).astype(int)
        self.assertTrue(set(np.unique(got[..., 3])) <= {0, 255})
        self.assertTrue(((got[..., 3] > 0) == (self.truth[..., 3] > 0)).all())
        diff = np.abs(got[..., :3] - self.truth[..., :3].astype(int)).max(-1)[self.truth[..., 3] > 0]
        self.assertLessEqual(float((diff > 30).mean()), 0.02)
        self.assertTrue(os.path.isfile(out["preview"]))

    def test_project_palette_and_a_photo_without_grid(self):
        pal = os.path.join(self.d, "p.hex")
        with open(pal, "w", encoding="utf-8") as fh:
            fh.write("\n".join("%02x%02x%02x" % c for c in PALETTE))
        dst = os.path.join(self.d, "hero.png")
        code, out = self.run_cmd("snap", self.src, "--out", dst, "--palette", pal)
        got = np.asarray(Image.open(dst).convert("RGB")).reshape(-1, 3)
        alpha = np.asarray(Image.open(dst).convert("RGBA"))[..., 3].reshape(-1)
        self.assertTrue(all(tuple(c) in PALETTE for c in got[alpha > 0]))
        photo = os.path.join(self.d, "photo.png")
        rng = np.random.default_rng(1)
        Image.fromarray(rng.integers(0, 255, (96, 96, 3), dtype=np.uint8)).save(photo)
        code, out = self.run_cmd("snap", photo, "--out", os.path.join(self.d, "x.png"))
        self.assertEqual(code, 1, out)


if __name__ == "__main__":
    unittest.main()
