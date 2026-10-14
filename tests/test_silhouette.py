"""Tests for blender-modeling silhouette_measure.py (synthetic masks) and silhouette_shot.py
(a real background Blender render, skipped without Blender).

g2 rows 64, 76, 78, 87, 88: yes/no shoulder checks passed while the arm contour was a straight
tube; renders did not record their px/m; builder and reviewer measured the "V angle" differently.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(__file__)
SCRIPTS = os.path.join(HERE, "..", "plugins", "kiln", "skills", "blender-modeling", "scripts")
MEASURE = os.path.join(SCRIPTS, "silhouette_measure.py")
SHOT = os.path.join(SCRIPTS, "silhouette_shot.py")
sys.path.insert(0, HERE)
from test_mesh_qa import BLENDER  # noqa: E402

PPM = 1000.0   # 1 mm per pixel


def save(root, name, draw_fn, w=600, h=1000):
    """Figure drawn in world metres: h from -0.3 to 0.3, z from 0.5 to 1.5 (centre 0, 1.0)."""
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)

    def px(hh, zz):
        return (hh * PPM + w / 2, (1.0 - zz) * PPM + h / 2)

    draw_fn(d, px)
    path = os.path.join(root, name + ".png")
    img.save(path)
    with open(os.path.join(root, name + ".json"), "w", encoding="utf-8") as fh:
        json.dump({"view": "front", "px_per_m": PPM, "width": w, "height": h,
                   "center_world": [0.0, 1.0], "h_axis": "x", "h_sign": 1}, fh)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", MEASURE, *args], capture_output=True, text=True,
                       timeout=60)
    return json.loads(p.stdout)


def rect(d, px, h0, z0, h1, z1):
    a, b = px(h0, z1), px(h1, z0)
    d.rectangle([a[0], a[1], b[0] - 1, b[1] - 1], fill=0)


class Measure(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-sil-")

    def figure(self, bulge):
        def draw(d, px):
            rect(d, px, -0.10, 0.80, 0.10, 1.40)            # torso
            rect(d, px, 0.10, 1.00, 0.18, 1.40)             # upper arm, a straight tube
            if bulge:                                       # deltoid cap over 1.28..1.40
                c0, c1 = px(0.13, 1.40), px(0.215, 1.28)
                d.ellipse([c0[0], c0[1], c1[0], c1[1]], fill=0)
        return draw

    def test_deltoid_reads_a_tube_and_a_cap(self):
        tube = save(self.root, "tube", self.figure(False))
        cap = save(self.root, "cap", self.figure(True))
        args = ["--side", "max", "--fit", "1.05", "1.20", "--peak", "1.25", "1.40", "--top", "1.40"]
        t = run("deltoid", tube, *args)
        c = run("deltoid", cap, *args)
        self.assertAlmostEqual(t["deviation_cm"], 0.0, delta=0.15)
        self.assertGreater(c["deviation_cm"], 2.5)
        self.assertGreater(c["peak_z_m"], 1.28)

    def test_holes_gap_and_width(self):
        def draw(d, px):
            rect(d, px, -0.10, 0.80, 0.10, 1.40)            # torso
            rect(d, px, 0.13, 0.95, 0.18, 1.40)             # arm, 3 cm from the torso
            rect(d, px, 0.10, 1.30, 0.13, 1.40)             # armpit closes the gap at the top
            rect(d, px, -0.04, 1.10, 0.04, 1.14)            # a see-through slit: cut below
        path = save(self.root, "fig", draw)
        img = Image.open(path)
        d = ImageDraw.Draw(img)
        d.rectangle([300 - 20, 1000 / 2 - 0.12 * PPM, 300 + 20, 1000 / 2 - 0.115 * PPM], fill=255)
        img.save(path)
        res = run("holes", path)
        self.assertEqual(res["count"], 1, res)
        z0, z1 = res["holes"][0]["z_range_m"]
        self.assertAlmostEqual(z0, 1.115, delta=0.003)
        g = run("gap", path, "--z", "0.96", "1.29")
        self.assertAlmostEqual(g["min_gap_m"], 0.03, delta=0.002)
        w = run("width", path, "--z", "1.35", "--min-between", "0.96", "1.29")
        self.assertAlmostEqual(w["width_m"], 0.28, delta=0.002)

    def test_chord_angle_is_one_definition(self):
        def draw(d, px):
            d.polygon([px(-0.25, 1.20), px(0.0, 1.45), px(0.25, 1.20), px(0.25, 1.0),
                       px(-0.25, 1.0)], fill=0)            # two 45 degree slopes
        path = save(self.root, "v", draw)
        res = run("chord-angle", path, "--a", "-0.22", "-0.03", "--b", "0.03", "0.22")
        self.assertAlmostEqual(res["v_angle_deg"], 90.0, delta=1.5)


ATLAS = os.path.join(SCRIPTS, "card_atlas.py")


class CardAtlas(unittest.TestCase):
    # g2 rows 57/115: atlases generated on white kept white texels under alpha and at strand
    # edges; a black beard rendered silver at 3 m.
    def test_made_atlas_passes_and_a_white_fill_fails(self):
        root = tempfile.mkdtemp(prefix="kiln-atlas-")
        p = subprocess.run([sys.executable, "-B", ATLAS, "make", "--out", root, "--tag", "t",
                            "--size", "256"], capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr)
        albedo = os.path.join(root, "T_t_cards_albedo.png")
        ok = subprocess.run([sys.executable, "-B", ATLAS, "check", albedo], capture_output=True,
                            text=True, timeout=60)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        img = np.asarray(Image.open(albedo).convert("RGBA")).copy()
        img[img[..., 3] < 230, :3] = 255                 # the old bug: white under the alpha
        Image.fromarray(img, "RGBA").save(albedo)
        bad = subprocess.run([sys.executable, "-B", ATLAS, "check", albedo], capture_output=True,
                             text=True, timeout=60)
        self.assertEqual(bad.returncode, 1, bad.stdout)
        self.assertGreater(json.loads(bad.stdout)["light_edge_share"], 0.5)


DRIVER = r'''
import bpy, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
coll = bpy.data.collections.new("asset")
bpy.context.scene.collection.children.link(coll)
bpy.ops.mesh.primitive_cube_add(size=0.5, location=(0.1, 0, 1.0))
o = bpy.context.active_object
for c in o.users_collection:
    c.objects.unlink(o)
coll.objects.link(o)
src = open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8").read()
src = src.replace('OUT = "//.kiln/tmp/sil/front.png"', 'OUT = r"%s"' % sys.argv[sys.argv.index("--") + 2])
ns = {}
exec(compile(src, "silhouette_shot.py", "exec"), ns)
'''


@unittest.skipUnless(BLENDER, "no Blender found (set KILN_BLENDER)")
class Shot(unittest.TestCase):
    def test_shot_and_measure_a_known_cube(self):
        root = tempfile.mkdtemp(prefix="kiln-shot-")
        driver = os.path.join(root, "driver.py")
        with open(driver, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        png = os.path.join(root, "front.png")
        p = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", driver, "--",
                            os.path.abspath(SHOT), png], capture_output=True, text=True,
                           timeout=300)
        self.assertTrue(os.path.isfile(png), p.stdout[-2000:] + p.stderr[-2000:])
        res = run("width", png, "--z", "1.0")
        self.assertAlmostEqual(res["width_m"], 0.5, delta=0.003)
        side = json.load(open(os.path.join(root, "front.json"), encoding="utf-8"))
        self.assertEqual(side["px_per_m"], 1000.0)
        c = run("contour", png, "--side", "max", "--z", "0.9", "1.1")
        self.assertAlmostEqual(c["points"][0][1], 0.35, delta=0.003)   # cube's +x face at 0.35


if __name__ == "__main__":
    unittest.main()
