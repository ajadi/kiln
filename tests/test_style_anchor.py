"""Tests for asset-pipeline style_anchor.py on synthetic glbs: members of one series share
bevels, triangle density, texel density and palette while their shapes differ; a member built
in another style fails on the hard metrics."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from glb_util import box, cylinder, planar_uvs, png, sphere, write_glb  # noqa: E402

SCRIPT = os.path.join(HERE, "..", "plugins", "kiln", "skills", "asset-pipeline", "scripts",
                      "style_anchor.py")


def crate(sx, sy, sz, bevel):
    return [box(sx, sy, sz, bevel), box(sx * 0.9, sy * 0.9, 0.1, bevel * 0.5, centre=(0, 0, sz / 2 + 0.05))]


def views(folder, colours, shape="crate"):
    """Two flat-lit views with alpha: a crate-like or round silhouette in the given colours."""
    os.makedirs(folder, exist_ok=True)
    for i, name in enumerate(("front", "side")):
        img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if shape == "crate":
            d.rectangle([60 + 20 * i, 120, 340 - 20 * i, 360], fill=colours[0] + (255,))
            d.rectangle([80, 90, 320, 120], fill=colours[1] + (255,))
        else:
            d.ellipse([60, 60, 340, 340], fill=colours[0] + (255,))
        img.save(os.path.join(folder, name + ".png"))
    return folder


class StyleAnchor(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="kiln-style-")

    def glb(self, name, parts, tex=(256, 256), uv_scale=1.0, materials=1):
        mats = [{"name": f"m{i}", "texture": png(tex, (150, 90 + 30 * i, 50))} for i in range(materials)]
        nodes = [{"name": f"{name}_{i}", "tris": t, "uvs": planar_uvs(t, uv_scale),
                  "material": i % materials} for i, t in enumerate(parts)]
        path = os.path.join(self.d, name + ".glb")
        write_glb(path, nodes, mats)
        return path

    def run_cmd(self, *args):
        p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                           timeout=120)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            self.fail(p.stdout + p.stderr)

    def anchor(self):
        style = os.path.join(self.d, "anchors", "crates", "style.json")
        code, out = self.run_cmd("extract", self.glb("anchor", crate(1, 1, 0.8, 0.05)),
                                 "--views", views(os.path.join(self.d, "va"), [(150, 90, 50), (90, 60, 40)]),
                                 "--out", style)
        self.assertEqual(code, 0, out)
        return style

    def verdicts(self, out):
        return {m["metric"]: m["verdict"] for m in out["metrics"]}

    def test_a_series_member_with_another_shape_passes(self):
        style = self.anchor()
        code, out = self.run_cmd("check", style, self.glb("long", crate(1.6, 0.7, 0.6, 0.05)),
                                 "--views", views(os.path.join(self.d, "vb"), [(152, 92, 48), (88, 60, 42)]))
        self.assertEqual((code, out["verdict"]), (0, "pass"), out)
        self.assertNotIn("iou", json.dumps(out))                    # silhouettes may differ

    def test_another_style_fails_on_hard_metrics(self):
        style = self.anchor()
        code, out = self.run_cmd("check", style, self.glb("sharp", crate(1, 1, 0.8, 0.0)))
        self.assertEqual((code, out["verdict"]), (1, "fail"), out)
        v = self.verdicts(out)
        self.assertEqual((v["edge_sharpness"], v["tri_density"]), ("fail", "fail"))
        code, out = self.run_cmd("check", style, self.glb("round", [sphere()]))
        self.assertEqual(self.verdicts(out)["edge_sharpness"], "fail", out)

    def test_segments_and_texel_density_and_materials(self):
        style = os.path.join(self.d, "barrels.json")
        self.run_cmd("extract", self.glb("b32", [cylinder(32)]), "--out", style)
        code, out = self.run_cmd("check", style, self.glb("b8", [cylinder(8)]))
        self.assertEqual(self.verdicts(out)["tri_density"], "fail", out)
        code, out = self.run_cmd("check", style, self.glb("b32hi", [cylinder(32)], tex=(512, 512)))
        self.assertEqual(self.verdicts(out)["texel_density"], "fail", out)
        code, out = self.run_cmd("check", style, self.glb("b32m", [cylinder(32), cylinder(32, centre=(2, 0, 0)),
                                                                   cylinder(32, centre=(4, 0, 0))], materials=3))
        self.assertEqual(self.verdicts(out)["materials"], "fail", out)

    def test_palette_is_soft_unless_strict(self):
        style = self.anchor()
        member = self.glb("teal", crate(1.2, 0.9, 0.7, 0.05))
        teal = views(os.path.join(self.d, "vt"), [(40, 140, 150), (20, 70, 80)])
        code, out = self.run_cmd("check", style, member, "--views", teal)
        self.assertEqual((code, self.verdicts(out)["palette"], out["verdict"]), (0, "warn", "warn"), out)
        code, out = self.run_cmd("check", style, member, "--views", teal, "--profile", "strict")
        self.assertEqual((code, out["verdict"]), (1, "fail"))

    def test_calibrate_widens_to_the_approved_spread(self):
        style = self.anchor()
        approved = self.glb("big", crate(1, 1, 0.8, 0.05), tex=(512, 512))   # 2x texel density
        code, out = self.run_cmd("check", style, approved)
        self.assertEqual(self.verdicts(out)["texel_density"], "fail")
        code, out = self.run_cmd("calibrate", style, approved)
        self.assertEqual(code, 0, out)
        self.assertGreaterEqual(out["tolerances"]["texel_density"], 2.0)
        code, out = self.run_cmd("check", style, approved)
        self.assertEqual(self.verdicts(out)["texel_density"], "pass", out)


if __name__ == "__main__":
    unittest.main()
