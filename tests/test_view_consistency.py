"""Tests for image-to-model view_consistency.py on synthetic car silhouettes (the prototype cases
of docs research 2026-10-19 image-to-3d inputs): opposite views must be mirror images; IoU alone
passes a 4 % wheelbase error, the outline profiles do not."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw, ImageFilter

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                       "image-to-model", "scripts")
VC = os.path.join(SCRIPTS, "view_consistency.py")
IOU = os.path.join(SCRIPTS, "silhouette_iou.py")


def car(path, wheelbase=1.0, pillar=0.0, roof=1.0, scale=1.0, shift=(0, 0), dilate=0, mirror=False):
    """Side view of a car, 1024 px wide canvas, RGBA with the background transparent."""
    w, h = 1024, 640
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    s = lambda x, y: (x * scale + shift[0], y * scale + shift[1])  # noqa: E731
    d.rectangle([s(112, 300), s(912, 440)], fill=255)                       # body
    top = 300 - 110 * roof
    d.polygon([s(300, 300), s(380 + pillar * 800, top), s(640 + pillar * 800, top),
               s(740 + pillar * 800, 300)], fill=255)                       # cabin
    centre, half = 512, 290 * wheelbase
    for cx in (centre - half, centre + half):
        x0, y0 = s(cx - 70, 400)
        x1, y1 = s(cx + 70, 540)
        d.ellipse([x0, y0, x1, y1], fill=255)                               # wheels
    if dilate:
        img = img.filter(ImageFilter.MaxFilter(dilate))
    if mirror:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    rgba = Image.new("RGBA", (w, h), (200, 200, 200, 0))
    rgba.putalpha(img)
    rgba.save(path)
    return path


class ViewConsistency(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kiln-vc-")
        self.left = car(os.path.join(self.dir, "left.png"))

    def check(self, **right):
        path = car(os.path.join(self.dir, "right.png"), mirror=True, **right)
        p = subprocess.run([sys.executable, "-B", VC, "--left", self.left, "--right", path,
                            "--diff", os.path.join(self.dir, "diff")],
                           capture_output=True, text=True, timeout=60)
        out = json.loads(p.stdout)
        return p.returncode, out["verdict"], out["pairs"][0]

    def test_mirror_and_framing_pass(self):
        self.assertEqual(self.check()[:2], (0, "pass"))
        self.assertEqual(self.check(scale=0.8, shift=(60, 40))[:2], (0, "pass"))
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "diff", "left_right_diff.png")))

    def test_matting_noise_passes(self):
        code, verdict, m = self.check(dilate=7)
        self.assertNotEqual(verdict, "fail", m)

    def test_wheelbase_error_fails_though_iou_is_high(self):
        code, verdict, m = self.check(wheelbase=1.04)
        self.assertEqual((code, verdict), (1, "fail"), m)
        self.assertGreater(m["iou"], 0.95)                  # what an IoU gate would have passed
        self.assertGreater(m["bottom_disagree"], 0.08)

    def test_moved_roof_pillar_fails(self):
        code, verdict, m = self.check(pillar=0.05)
        self.assertEqual(verdict, "fail", m)
        self.assertGreater(m["top_disagree"], 0.08)

    def test_a_second_view_of_the_same_side_is_not_a_mirror(self):
        # front and back given as the same unmirrored drawing: an asymmetric object fails
        p = subprocess.run([sys.executable, "-B", VC, "--front", self.left, "--back", self.left],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(json.loads(p.stdout)["verdict"], "fail")

    def test_silhouette_iou_reports_and_gates_profiles(self):
        render = car(os.path.join(self.dir, "render.png"), wheelbase=1.04)
        p = subprocess.run([sys.executable, "-B", IOU, self.left, render, "--min", "0.9"],
                           capture_output=True, text=True, timeout=60)
        out = json.loads(p.stdout)
        self.assertEqual(out["verdict"], "pass")                   # IoU alone passes it
        self.assertGreater(out["bottom_disagree"], 0.08)
        p = subprocess.run([sys.executable, "-B", IOU, self.left, render, "--min", "0.9",
                            "--max-disagree", "0.08"], capture_output=True, text=True, timeout=60)
        self.assertEqual((p.returncode, json.loads(p.stdout)["verdict"]), (1, "fail"))

    def test_canvas_sizes_and_windows_paths(self):
        # bug hunt 2026-10-20: a render on another canvas size was stretched to the reference
        # and failed; --pairs split D:/x.png:D:/y.png at the drive letter's colon
        def disc(name, size, r):
            img = Image.new("RGBA", size, (0, 0, 0, 0))
            cx, cy = size[0] / 2, size[1] / 2
            ImageDraw.Draw(img).ellipse([cx - r, cy - r, cx + r, cy + r], fill=(200, 200, 200, 255))
            path = os.path.join(self.dir, name)
            img.save(path)
            return os.path.abspath(path).replace("\\", "/")
        ref, ren = disc("ref.png", (512, 512), 150), disc("ren.png", (400, 300), 100)
        p = subprocess.run([sys.executable, "-B", IOU, ref, ren], capture_output=True, text=True,
                           timeout=60)
        out = json.loads(p.stdout)
        self.assertEqual(out["verdict"], "pass", out)
        p = subprocess.run([sys.executable, "-B", IOU, "--pairs", f"{ref}:{ren}"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(json.loads(p.stdout)["verdict"], "pass", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
