"""Tests for animation video_ref.py on a synthetic side-view walker (COCO-17 keypoints from
sinusoidal joint angles): the cycle is found, a phase shift is aligned away, a wrong knee
amplitude, a slower cycle, a growing figure and low confidence are caught."""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "animation",
                      "scripts", "video_ref.py")
H = 400.0


def walker(frames=90, T=30.0, knee_max=60.0, grow=0.0, score=0.9, shift=0, fps=30):
    out = []
    for f in range(frames):
        t = (f + shift) / T * 2 * math.pi
        h = H * (1 + grow * f)
        x0, y0 = 300.0, 100 + 0.55 * h + 3 * math.sin(2 * t)
        kp = [[0, 0, score] for _ in range(17)]
        sho = (x0 + 4, y0 - 0.30 * h)
        for i, (dx, dy) in enumerate([(12, -0.12), (14, -0.13), (10, -0.13), (6, -0.12), (2, -0.12)]):
            kp[i] = [sho[0] + dx, sho[1] + dy * h, score]
        for side, ph in ((0, 0.0), (1, math.pi)):
            th = math.radians(25) * math.sin(t + ph)
            kn = math.radians(10 + (knee_max - 10) * (1 + math.sin(t + ph + 1.0)) / 2)
            hip = (x0 + (2 if side else -2), y0)
            knee = (hip[0] + 0.245 * h * math.sin(th), hip[1] + 0.245 * h * math.cos(th))
            ank = (knee[0] + 0.246 * h * math.sin(th - kn), knee[1] + 0.246 * h * math.cos(th - kn))
            sw = -math.radians(20) * math.sin(t + ph)
            el = math.radians(20 + 10 * math.sin(t + ph))
            elb = (sho[0] + 0.186 * h * math.sin(sw), sho[1] + 0.186 * h * math.cos(sw))
            wri = (elb[0] + 0.146 * h * math.sin(sw + el), elb[1] + 0.146 * h * math.cos(sw + el))
            for idx, p in zip((5 + side, 7 + side, 9 + side, 11 + side, 13 + side, 15 + side),
                              (sho, elb, wri, hip, knee, ank)):
                kp[idx] = [p[0], p[1], score]
        out.append({"kp": kp})
    return {"format": "kiln-keypoints/1", "layout": "coco17", "fps": fps, "frames": out}


class VideoRef(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="kiln-vref-")

    def save(self, name, data):
        path = os.path.join(self.d, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path

    def run_cmd(self, *args):
        p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                           timeout=300)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            self.fail(p.stdout + p.stderr)

    def test_period_and_loop_cut(self):
        code, out = self.run_cmd("period", self.save("w.json", walker()))
        self.assertEqual(code, 0, out)
        self.assertAlmostEqual(out["period_frames"], 30, delta=0.6)
        self.assertLess(out["seam_H"], 0.01)
        code, out = self.run_cmd("period", self.save("w24.json", walker(frames=72, T=24, fps=24)))
        self.assertAlmostEqual(out["period_s"], 1.0, delta=0.03)     # 24 fps resampled to 30

    def test_compare_aligns_phase_and_passes(self):
        ref = self.save("ref.json", walker())
        ours = self.save("ours.json", walker(shift=7))
        code, out = self.run_cmd("compare", ref, ours)
        self.assertEqual((code, out["verdict"]), (0, "pass"), out["fails"])

    def test_compare_catches_amplitude_and_timing(self):
        ref = self.save("ref.json", walker())
        code, out = self.run_cmd("compare", ref, self.save("knee.json", walker(knee_max=85)))
        self.assertEqual(out["checks"]["angles"]["knee_l"]["verdict"], "fail", out)
        self.assertEqual(code, 1)
        code, out = self.run_cmd("compare", ref, self.save("slow.json", walker(T=33, frames=99)))
        self.assertEqual(out["checks"]["period"]["verdict"], "fail", out)

    def test_gates(self):
        code, out = self.run_cmd("gate", self.save("ok.json", walker()), "--loop")
        self.assertEqual((code, out["verdict"]), (0, "pass"), out)
        code, out = self.run_cmd("gate", self.save("grow.json", walker(grow=0.002)))
        self.assertEqual(out["gates"]["scale"]["verdict"], "fail", out)
        code, out = self.run_cmd("gate", self.save("dim.json", walker(score=0.3)))
        self.assertEqual(out["gates"]["confidence"]["verdict"], "fail", out)
        held = walker()
        held["frames"] = [f for f in held["frames"][::4] for _ in range(4)]   # 7.5 poses a second
        code, out = self.run_cmd("gate", self.save("held.json", held))
        self.assertEqual(out["gates"]["held_frames"]["verdict"], "fail", out)  # live: a GIF in mp4

    def test_keys_find_contacts_each_cycle(self):
        code, out = self.run_cmd("keys", self.save("w.json", walker()))
        self.assertEqual(code, 0, out)
        for name in ("contact_l", "contact_r"):
            self.assertGreaterEqual(len(out["keys"][name]), 2, out)
            steps = np.diff(out["keys"][name])
            self.assertTrue(all(abs(s - 30) <= 1 for s in steps), out["keys"][name])

    def test_noise_measures_the_estimator(self):
        truth = walker()
        rng = np.random.default_rng(0)
        est = json.loads(json.dumps(truth))
        for f in est["frames"]:
            for k in f["kp"]:
                k[0] += float(rng.normal(0, 3))
                k[1] += float(rng.normal(0, 3))
        code, out = self.run_cmd("noise", self.save("est.json", est), self.save("truth.json", truth),
                                 "--out", os.path.join(self.d, "noise.json"))
        self.assertEqual(code, 0, out)
        self.assertGreater(out["angle_sigma"]["knee_l"], 0.3)
        self.assertLess(out["position_sigma_H"], 0.05)

    @unittest.skipUnless(shutil.which("ffmpeg"), "no ffmpeg")
    def test_frames_from_a_video(self):
        from PIL import Image
        src = os.path.join(self.d, "src")
        os.makedirs(src)
        for i in range(20):
            Image.new("RGB", (64, 48), (i * 10, 0, 0)).save(os.path.join(src, f"{i:03d}.png"))
        video = os.path.join(self.d, "clip.mp4")
        subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-framerate", "24", "-i",
                        os.path.join(src, "%03d.png"), "-pix_fmt", "yuv420p", video], check=True)
        code, out = self.run_cmd("frames", video, "--out", os.path.join(self.d, "frames"),
                                 "--fps", "30")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["size"], [64, 48])
        self.assertGreaterEqual(out["count"], 24)


if __name__ == "__main__":
    unittest.main()
