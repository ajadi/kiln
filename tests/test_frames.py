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

    def test_review_pack_only_for_changed_frames_and_two_reviewer_verdict(self):
        self.shot("gate.png", scene())
        self.shot("hall.png", scene(seed=1))
        run(self.root, "baseline", "cap/gate.png", "cap/hall.png", "--scene", "plaza")
        self.shot("gate.png", scene(square=True))          # changed
        self.shot("hall.png", scene(noise=2))               # capture noise only
        code, res = run(self.root, "review", "cap/gate.png", "cap/hall.png", "--scene", "plaza",
                        "--out", "rev")
        self.assertEqual((code, res["items_to_review"], res["unchanged"]), (0, 1, 1), res)
        rev = os.path.join(self.root, "rev")
        with open(os.path.join(rev, "review.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        item = data["items"][0]
        pack = Image.open(os.path.join(rev, item["pack"]))
        self.assertGreater(pack.width, pack.height * 2)        # baseline | new | changed
        self.assertIn("z-fighting", open(os.path.join(rev, "REVIEW.md"), encoding="utf-8").read())

        def answers(name, glitch, intended=True):
            d = json.loads(json.dumps(data))
            d["items"][0]["answer"] = {"intended": intended, "glitch": glitch,
                                       "class": "floating object" if glitch else None,
                                       "evidence": "white box top right"}
            path = os.path.join(rev, name)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(d, fh)
            return path

        review = os.path.join(rev, "review.json")
        for a, b, want in ((False, False, "PASS"), (True, True, "FAIL"), (True, False, "DISPUTED")):
            code, out = run(self.root, "verdict", review, "--a", answers("a.json", a),
                            "--b", answers("b.json", b))
            self.assertEqual(out["verdict"], want, out)
        code, out = run(self.root, "verdict", review, "--a", answers("a.json", False, False),
                        "--b", answers("b.json", False, True))
        self.assertEqual(out["verdict"], "UNINTENDED")

    def test_failures_without_a_region_still_reach_the_review(self):
        # bug hunt 2026-10-20: an SSIM-only failure and a size change were dropped, review PASS
        flat = Image.fromarray(np.full((120, 160, 3), 128, np.uint8))
        self.shot("flat.png", flat)
        self.shot("wide.png", scene())
        run(self.root, "baseline", "cap/flat.png", "cap/wide.png", "--scene", "s")
        noisy = np.clip(128 + np.random.default_rng(1).integers(-15, 16, (120, 160, 3)), 0, 255)
        self.shot("flat.png", Image.fromarray(noisy.astype(np.uint8)))
        self.shot("wide.png", scene().resize((160, 120)))
        code, res = run(self.root, "compare", "cap/flat.png", "--scene", "s")
        self.assertEqual(code, 1, res)
        code, res = run(self.root, "review", "cap/flat.png", "cap/wide.png", "--scene", "s",
                        "--out", "rev")
        self.assertEqual((res["verdict"], res["items_to_review"]), ("REVIEW", 2), res)
        with open(os.path.join(self.root, "rev", "review.json"), encoding="utf-8") as fh:
            ids = [i["id"] for i in json.load(fh)["items"]]
        self.assertEqual(ids, ["flat.png#whole", "wide.png#whole"])

    def test_no_image_or_no_baseline_is_not_a_pass(self):
        code, res = run(self.root, "compare", "cap/none*.png", "--scene", "x")
        self.assertEqual((code, res["verdict"]), (2, "NOT ASSESSED"), res)
        self.shot("a.png", scene())
        code, res = run(self.root, "review", "cap/a.png", "--scene", "x", "--out", "rev")
        self.assertEqual((code, res["verdict"]), (2, "NOT ASSESSED"), res)

    def test_missing_baseline_and_size_change(self):
        self.shot("a.png", scene())
        code, res = run(self.root, "compare", "cap/a.png", "--scene", "x")
        self.assertEqual(res["results"][0]["verdict"], "NOT ASSESSED")
        self.assertEqual((code, res["verdict"]), (2, "NOT ASSESSED"))
        run(self.root, "baseline", "cap/a.png", "--scene", "x")
        self.shot("a.png", scene().resize((160, 120)))
        code, res = run(self.root, "compare", "cap/a.png", "--scene", "x")
        self.assertEqual(code, 1)
        self.assertIn("size", res["results"][0]["problems"][0])


# K02: frozen effects and sweeps on a state change. A rain-like streak field scrolls down by
# `phase` pixels; frames are 1/60 s apart.
def streaks(phase, base=None, box_only=True):
    a = np.full((120, 160, 3), 70.0, np.float32) if base is None else base.copy()
    y = (np.arange(120)[:, None] + phase) % 24
    stripe = (y < 3) & (np.arange(160)[None, :] % 9 == 0)
    a[stripe] = (190, 200, 210)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


class Motion(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-motion-")

    def seq(self, name, phases):
        folder = os.path.join(self.root, name)
        os.makedirs(folder)
        for i, ph in enumerate(phases):
            streaks(ph).save(os.path.join(folder, f"f{i:03d}.png"))
        return os.path.join(folder, "*.png")

    def still(self, name, n=30):
        folder = os.path.join(self.root, name)
        os.makedirs(folder)
        for i in range(n):
            Image.fromarray(np.full((120, 160, 3), 70, np.uint8)).save(
                os.path.join(folder, f"f{i:03d}.png"))
        return os.path.join(folder, "*.png")

    def test_anim_passes_a_moving_effect_and_fails_a_frozen_one(self):
        off = self.still("off")
        moving = self.seq("on", [i * 4 for i in range(30)])           # 240 px/s of fall
        code, res = run(self.root, "anim", "--on", moving, "--off", off)
        self.assertEqual((code, res["verdict"]), (0, "PASS"), res)
        frozen = self.seq("frozen", [7] * 30)                          # drawn, never advanced
        code, res = run(self.root, "anim", "--on", frozen, "--off", off)
        self.assertEqual((code, res["verdict"]), (1, "FAIL"), res)
        self.assertIn("frozen", res["problem"])
        code, res = run(self.root, "anim", "--on", frozen, "--off", off, "--box", "0,0,10,10")
        self.assertEqual(res["box"], [0, 0, 10, 10])

    def noise_seq(self, name, phases):
        """A rain/fog-like noise texture (512 px period) scrolled down by `phase` pixels."""
        tex = np.random.default_rng(3).uniform(0, 255, (512, 160))
        for _ in range(3):                                     # smooth it into blobs
            tex = (np.roll(tex, 1, 0) + tex + np.roll(tex, -1, 0)) / 3
            tex = (np.roll(tex, 1, 1) + tex + np.roll(tex, -1, 1)) / 3
        tex = (tex - tex.min()) / (tex.max() - tex.min()) * 200 + 30
        folder = os.path.join(self.root, name)
        os.makedirs(folder)
        for i, ph in enumerate(phases):
            ip, fr = int(np.floor(ph)), ph - np.floor(ph)
            a = np.roll(tex, -ip, 0) * (1 - fr) + np.roll(tex, -(ip + 1), 0) * fr
            img = np.repeat(np.round(a[:120])[..., None], 3, axis=2).astype(np.uint8)
            Image.fromarray(img).save(os.path.join(folder, f"f{i:03d}.png"))
        return os.path.join(folder, "*.png")

    def test_ramp_fails_a_phase_from_rate_times_absolute_time(self):
        steady = self.noise_seq("steady", [i * 1 for i in range(30)])  # 60 px/s
        # the rain picks up over the 30 frames: speed 60 -> 90 px/s
        speeds = [60 + 30 * i / 29 for i in range(30)]
        good, phase = [], 0.0
        for v in speeds:                       # integrated: phase += speed * dt
            good.append(phase)
            phase += v / 60
        ok = self.noise_seq("good", good)
        code, res = run(self.root, "ramp", "--change", ok, "--steady", steady)
        self.assertEqual((code, res["verdict"]), (0, "PASS"), res)
        t0 = 600.0                              # ten minutes into the session
        bad = self.noise_seq("bad", [v * (t0 + i / 60) for i, v in enumerate(speeds)])
        code, res = run(self.root, "ramp", "--change", bad, "--steady", steady)
        self.assertEqual((code, res["verdict"]), (1, "FAIL"), res)
        self.assertIn("rate", res["problem"])
        flat = self.still("held_still")                       # nothing to judge against
        code, res = run(self.root, "ramp", "--change", ok, "--steady", flat)
        self.assertEqual(res["verdict"], "NOT ASSESSED", res)

    def test_missing_frames_are_not_assessed(self):
        code, res = run(self.root, "anim", "--on", os.path.join(self.root, "none*.png"),
                        "--off", os.path.join(self.root, "none*.png"))
        self.assertEqual(res["verdict"], "NOT ASSESSED", res)


if __name__ == "__main__":
    unittest.main()
