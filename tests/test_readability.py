"""Tests for plugins/kiln/skills/acceptance/scripts/readability.py (synthetic images, unittest)."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "acceptance",
                      "scripts", "readability.py")
spec = importlib.util.spec_from_file_location("kiln_readability", SCRIPT)
rd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rd)


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=120)
    return p.returncode, json.loads(p.stdout)


def save(path, arr):
    Image.fromarray(np.asarray(arr, np.uint8), "RGB").save(path)
    return path


class Readability(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-read-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.root, name)

    def red_on_black(self):
        a = np.zeros((120, 160, 3), np.uint8)
        a[40:80, 60:100] = (255, 0, 0)
        return save(self.path("red.png"), a)

    def test_matrices_keep_white_and_grey(self):
        for model in ("machado", "brettel"):
            for kind in ("protan", "deutan", "tritan"):
                for v in (1.0, 0.18):
                    out = rd.simulate(np.full((1, 1, 3), v), kind, model)[0, 0]
                    np.testing.assert_allclose(out, v, atol=0.01 * max(v, 0.2),
                                               err_msg=f"{model} {kind} {v}")

    def test_contrast_boxes_ring_and_mask(self):
        img = self.red_on_black()
        code, res = run("contrast", img, "--a", "60,40,40,40", "--b", "40,20,80,80")
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["contrast"], (0.2126 + 0.05) / 0.05, places=2)
        self.assertEqual(res["Y_background"], 0.0)  # --b minus --a: the black ring only
        code, res = run("contrast", img, "--target", "60,40,40,40", "--min", "6")
        self.assertEqual(code, 1)
        self.assertIn("< 6.0:1", res["problems"][0])
        black = save(self.path("black.png"), np.zeros((120, 160, 3)))
        code, m = run("mask", img, black, "--out", self.path("mask.png"))
        self.assertEqual(code, 0, m)
        self.assertEqual(m["bbox"], [60, 40, 40, 40])
        code, res = run("contrast", img, "--mask", self.path("mask.png"), "--ring", "10")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["background"], "10px ring")
        code, m = run("mask", img, img, "--out", self.path("none.png"))
        self.assertEqual(code, 1)

    def test_cvd_protan_loses_red(self):
        img = self.red_on_black()
        code, res = run("cvd", img, "--a", "60,40,40,40", "--b", "40,20,80,80", "--min", "4.5",
                        "--out", self.path("review"))
        self.assertEqual(code, 1)
        by = {r["vision"]: r for r in res["results"]}
        self.assertEqual(by["normal"]["verdict"], "pass")
        self.assertEqual(by["deutan"]["verdict"], "pass")
        self.assertEqual(by["protan"]["verdict"], "fail")
        self.assertAlmostEqual(by["protan"]["contrast"], 3.29, delta=0.05)
        self.assertEqual(len(res["problems"]), 1)
        for kind in ("protan", "deutan", "tritan"):
            self.assertTrue(os.path.isfile(by[kind]["image"]))
        sim = np.asarray(Image.open(by["protan"]["image"]))
        self.assertLess(int(sim[60, 80, 0]), 200)  # red darkened in the written image
        code, res = run("cvd", img, "--a", "60,40,40,40", "--b", "40,20,80,80", "--min", "3",
                        "--model", "brettel", "--type", "protan")
        self.assertEqual(code, 0, res)
        self.assertEqual([r["vision"] for r in res["results"]], ["normal", "protan"])

    def test_cvd_colour_cue_pair_by_delta_e(self):
        a = np.full((60, 160, 3), 40, np.uint8)
        a[10:50, 10:60] = (200, 30, 30)    # "enemy" red
        a[10:50, 100:150] = (30, 140, 30)  # "ally" green
        img = save(self.path("cues.png"), a)
        code, res = run("cvd", img, "--a", "10,10,50,40", "--b", "100,10,50,40", "--min", "3",
                        "--min-de", "20")
        self.assertEqual(code, 1)
        by = {r["vision"]: r for r in res["results"]}
        self.assertEqual(by["normal"]["verdict"], "pass")  # dE carries it in normal vision
        self.assertEqual(by["deutan"]["verdict"], "fail")
        self.assertLess(by["deutan"]["delta_e"], by["normal"]["delta_e"] * 0.5)

    def test_squint_bands(self):
        a = np.full((200, 400, 3), 30, np.uint8)
        a[60:140, 150:250] = 230  # big bright block: survives the blur
        img = save(self.path("block.png"), a)
        code, res = run("squint", img, "--target", "150,60,100,80", "--out", self.path("r"))
        self.assertEqual(code, 0, res)
        self.assertNotEqual(res["target"]["band"], res["surround"]["band"])
        self.assertEqual(res["sigma_px"], 4.0)  # 1% of 400 px
        self.assertTrue(os.path.isfile(res["image_blur"]))
        self.assertTrue(os.path.isfile(res["image_bands"]))
        b = np.full((200, 400, 3), 128, np.uint8)
        b[100:104, 200:204] = 140  # tiny, low-contrast detail dissolves into the surround
        b[:, :40] = 0
        b[:, -40:] = 255
        img = save(self.path("speck.png"), b)
        code, res = run("squint", img, "--target", "200,100,4,4")
        self.assertEqual(code, 1)
        self.assertEqual(res["target"]["band"], res["surround"]["band"])

    def test_saliency_finds_odd_blob(self):
        a = np.zeros((180, 320, 3), np.uint8)
        for x in range(0, 320, 8):
            a[:, x:x + 4] = 90  # repetitive background is suppressed by the spectral residual
        a[120:140, 240:260] = 255
        img = save(self.path("stripes.png"), a)
        code, res = run("saliency", img, "--target", "240,120,20,20", "--out", self.path("s"))
        self.assertEqual(code, 0, res)
        self.assertEqual(res["target_rank"], 1)
        self.assertTrue(res["target_above_object_threshold"])
        self.assertTrue(os.path.isfile(res["image"]))
        x, y, w, h = res["top_region"]
        self.assertTrue(x <= 250 <= x + w and y <= 130 <= y + h)
        code, res = run("saliency", img, "--target", "20,20,20,20")
        self.assertEqual(code, 1)
        self.assertEqual(res["verdict"], "fail")
        code, res = run("saliency", img)
        self.assertEqual(code, 0)
        self.assertEqual(res["verdict"], "report")

    def test_glob_and_bad_input(self):
        self.red_on_black()
        save(self.path("red2.png"), np.zeros((120, 160, 3)))
        code, res = run("contrast", self.path("red*.png"), "--a", "60,40,40,40", "--b",
                        "0,0,20,20", "--min", "1")
        self.assertIsInstance(res, list)
        self.assertEqual(len(res), 2)
        code, res = run("contrast", self.path("red.png"), "--a", "500,500,5,5", "--b", "0,0,5,5")
        self.assertEqual(code, 1)
        self.assertIn("outside", res["problems"][0])

    def test_hex_pairs_without_an_image(self):
        # g2 row 53a: palette checks needed a hand-written script around simulate().
        code, res = run("contrast", "--hex-a", "#ffffff", "--hex-b", "000000")
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["contrast"], 21.0, places=1)
        code, res = run("cvd", "--hex-a", "d62728", "--hex-b", "2ca02c", "--type", "protan",
                        "--min", "3")
        self.assertEqual(code, 1, res)
        self.assertEqual(res["results"][1]["vision"], "protan")

    def test_contrast_parts_find_the_dark_band(self):
        # g2 row 97: a figure with a light head and legs and a dark vest averaged to a pass.
        a = np.full((300, 200, 3), 60, np.uint8)
        a[60:120, 80:120] = 255
        a[120:180, 80:120] = 50
        a[180:240, 80:120] = 255
        img = save(self.path("fig.png"), a)
        m = np.zeros((300, 200), np.uint8)
        m[60:240, 80:120] = 255
        Image.fromarray(m, "L").save(self.path("fig_mask.png"))
        code, res = run("contrast", img, "--mask", self.path("fig_mask.png"), "--min", "3")
        self.assertEqual(code, 0, res)
        code, res = run("contrast", img, "--mask", self.path("fig_mask.png"), "--min", "3",
                        "--parts", "3")
        self.assertEqual(code, 1, res)
        self.assertEqual([p["verdict"] for p in res["parts"]], ["pass", "fail", "pass"])

    def test_unreachable_by_brightening_says_darken(self):
        # g2 row 138c: 3:1 against a light ring cannot be reached by brightening the target.
        a = np.full((120, 160, 3), 235, np.uint8)
        a[40:80, 60:100] = 205
        code, res = run("contrast", save(self.path("light.png"), a), "--target", "60,40,40,40")
        self.assertEqual(code, 1, res)
        self.assertTrue(any("darken" in p for p in res["problems"]), res["problems"])

    def test_squint_expect_same_for_decoration(self):
        # g2 row 53c: decoration should sit in the same value band as its surround.
        a = np.full((120, 160, 3), 90, np.uint8)
        a[40:80, 60:100] = 94
        a[:, :20] = 10
        a[:, -20:] = 250
        img = save(self.path("deco.png"), a)
        code, res = run("squint", img, "--target", "60,40,40,40")
        self.assertEqual(code, 1, res)
        code, res = run("squint", img, "--target", "60,40,40,40", "--expect", "same")
        self.assertEqual(code, 0, res)

    def test_saliency_ignores_border_peaks(self):
        # g2 rows 53b/97/138a: the top peaks sat on the frame edges and corners.
        rng = np.random.default_rng(3)
        a = rng.integers(100, 140, (360, 640, 3)).astype(np.uint8)
        a[:, :12] = 255
        a[:, -12:] = 0
        a[160:200, 300:340] = (230, 40, 40)
        img = save(self.path("busy.png"), a)
        code, res = run("saliency", img, "--target", "300,160,40,40", "--border", "40")
        self.assertEqual(code, 0, res)
        for p in res["peaks"]:
            self.assertTrue(40 <= p["x"] <= 600, p)
        self.assertEqual(res["border_px"], 40)

    def test_mask_largest_and_fill(self):
        # g2 row 138b: a 150x270 figure came back with a 916x276 bbox (stray diff components).
        bg = np.full((300, 400, 3), 90, np.uint8)
        fg = bg.copy()
        fg[20:290, 100:250] = 200
        fg[100:140, 150:200] = 90           # a hole the same colour as the background
        fg[5:9, 380:396] = 30               # a stray speck (particle)
        save(self.path("with.png"), fg)
        save(self.path("without.png"), bg)
        code, res = run("mask", self.path("with.png"), self.path("without.png"), "--out",
                        self.path("m.png"), "--largest", "--fill")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["bbox"], [100, 20, 150, 270])
        self.assertEqual(res["pixels"], 150 * 270)

    def test_blur_is_normalised_gaussian(self):
        img = np.zeros((41, 41))
        img[20, 20] = 1.0
        out = rd.blur(img, 3.0)
        self.assertAlmostEqual(out.sum(), 1.0, places=6)
        ys, xs = np.mgrid[:41, :41]
        var = float((out * (xs - 20) ** 2).sum())
        self.assertAlmostEqual(var, 9.0, delta=0.2)  # kernel truncated at 3 sigma


if __name__ == "__main__":
    unittest.main()
