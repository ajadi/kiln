"""Reference-sheet preparation: crop_ref.py --auto and prep_image.py on flat backdrops.
Synthetic sheet: three figures on white, the first two touching at the hands (T-pose), legs with a
contact shadow between the feet, white plates that nearly match the backdrop."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

SKILLS = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills")
CROP = os.path.join(SKILLS, "blender-modeling", "scripts", "crop_ref.py")
PREP = os.path.join(SKILLS, "image-to-model", "scripts", "prep_image.py")


def figure(d, cx, top, white=(244, 244, 244)):
    d.rectangle([cx - 30, top, cx + 30, top + 40], fill=(90, 70, 60))            # head
    d.rectangle([cx - 60, top + 40, cx + 60, top + 160], fill=(40, 40, 45))       # torso
    d.rectangle([cx - 40, top + 60, cx + 40, top + 120], fill=white)              # white plate
    d.rectangle([cx - 55, top + 160, cx - 10, top + 330], fill=(40, 40, 45))      # left leg
    d.rectangle([cx + 10, top + 160, cx + 55, top + 330], fill=(40, 40, 45))      # right leg
    d.ellipse([cx - 70, top + 322, cx + 70, top + 342], fill=(232, 232, 232))     # contact shadow
    d.rectangle([cx - 55, top + 300, cx - 10, top + 330], fill=(35, 35, 35))      # boots
    d.rectangle([cx + 10, top + 300, cx + 55, top + 330], fill=(35, 35, 35))


def make_sheet(path):
    img = Image.new("RGB", (900, 420), (254, 254, 254))
    d = ImageDraw.Draw(img)
    for cx in (150, 450):
        figure(d, cx, 30)
        d.rectangle([cx - 150, 90, cx + 150, 110], fill=(40, 40, 45))  # arms; 150+150 = touch
    figure(d, 760, 30)
    d.text((120, 390), "FRONT VIEW", fill=(60, 60, 60))
    img.save(path)


class Prep(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kiln-sheet-")
        self.sheet = os.path.join(self.dir, "sheet.png")
        make_sheet(self.sheet)

    def test_auto_crop_splits_touching_views_and_drops_labels(self):
        out = os.path.join(self.dir, "crops")
        p = subprocess.run([sys.executable, "-B", CROP, self.sheet, out, "--auto",
                            "front,back,side"], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        sizes = {v: Image.open(os.path.join(out, f"{v}.png")).size for v in ("front", "back",
                                                                           "side")}
        heights = [h for _, h in sizes.values()]
        self.assertLess(max(heights) - min(heights), 6, sizes)   # labels not included
        self.assertLess(sizes["side"][0], sizes["front"][0])

    def test_prep_mask_keeps_white_plates_and_frees_leg_gap(self):
        out = os.path.join(self.dir, "prepped")
        crop = os.path.join(self.dir, "side.png")
        Image.open(self.sheet).crop((680, 25, 840, 375)).save(crop)
        p = subprocess.run([sys.executable, "-B", PREP, "prep", crop, "--out-dir", out,
                            "--size", "512", "--bg", "#fefefe"], capture_output=True, text=True,
                           timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        res = json.loads(p.stdout)
        self.assertIn("flat backdrop", res["images"][0]["matte"])
        a = np.asarray(Image.open(os.path.join(out, "side_prep.png")))[..., 3]
        ys, xs = np.nonzero(a)
        cy = int(ys.min() + 0.3 * (ys.max() - ys.min()))
        cx = int((xs.min() + xs.max()) / 2)
        self.assertEqual(a[cy, cx], 255, "white plate punched out of the mask")
        gy = int(ys.min() + 0.75 * (ys.max() - ys.min()))
        self.assertEqual(a[gy, cx], 0, "gap between the legs kept as foreground")

    def test_inspect_ignores_backdrop(self):
        p = subprocess.run([sys.executable, "-B", PREP, "inspect", self.sheet],
                           capture_output=True, text=True, timeout=120)
        info = json.loads(p.stdout)[0]
        self.assertEqual(info["flat_background"], "#fefefe")
        self.assertLess(info["coverage"], 0.6)
        self.assertLess(info["clipped_highlights"], 0.02)


if __name__ == "__main__":
    unittest.main()
