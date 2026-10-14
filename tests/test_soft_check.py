"""Tests for plugins/kiln/skills/soft-bodies/scripts/soft_check.py (stdlib only).

Expected numbers come from closed forms (pendulum, catenary, spring) or from a small simulation
inside the test; every check is also shown failing on a broken input.
"""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "soft-bodies", "scripts", "soft_check.py")
G = 9.81


def write(data):
    fd, path = tempfile.mkstemp(prefix="kiln-soft-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *map(str, args)], capture_output=True,
                       text=True, timeout=120, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


def recording(samples, hz=60):
    n = max(len(v) for v in samples.values())
    return write({"physics_ticks_per_second": hz, "ticks": list(range(n)), "samples": samples})


def simulate_pendulum(length, amp_deg, seconds=20, hz=240):
    th, w, out = math.radians(amp_deg), 0.0, []
    for i in range(int(seconds * hz)):
        if i % (hz // 60) == 0:
            out.append(th)
        w -= G / length * math.sin(th) / hz
        th += w / hz
    return out


class Predict(unittest.TestCase):
    def test_pendulum_small_and_large_amplitude(self):
        # L 1 m: T0 = 2.00607 s; at 30 deg the exact period is 1.7408 % longer
        _, res = run("predict", "pendulum", "--length", 1, "--amplitude", 30)
        t0 = 2 * math.pi * math.sqrt(1 / G)
        self.assertAlmostEqual(res["prediction"]["small_angle_period_s"], t0, places=4)
        self.assertAlmostEqual(res["prediction"]["period_s"] / t0, 1.017408, places=5)

    def test_catenary_12_m_rope_over_10_m(self):
        _, res = run("predict", "catenary", "--span", 10, "--length", 12)
        a = res["prediction"]["parameter_a"]
        self.assertAlmostEqual(2 * a * math.sinh(5 / a), 12, places=3)
        self.assertAlmostEqual(res["prediction"]["sag_m"], a * (math.cosh(5 / a) - 1), places=3)
        self.assertGreater(res["prediction"]["sag_m"], 2.5)
        self.assertLess(res["prediction"]["sag_m"], 3.5)

    def test_spring_frequency_and_explicit_limit(self):
        # k 400, m 1: omega 20, f 3.183 Hz, dt_max 0.1 s; zeta = 4/(2*20) = 0.1
        _, res = run("predict", "spring", "--k", 400, "--mass", 1, "--c", 4, "--dt", 0.0167)
        p = res["prediction"]
        self.assertAlmostEqual(p["frequency_hz"], 20 / (2 * math.pi), places=4)
        self.assertAlmostEqual(p["damping_ratio"], 0.1)
        self.assertTrue(p["explicit_stable"])
        _, stiff = run("predict", "spring", "--k", 1e6, "--mass", 1, "--dt", 0.0167)
        self.assertFalse(stiff["prediction"]["explicit_stable"])  # dt_max 0.002 s


class Period(unittest.TestCase):
    def test_simulated_pendulum_matches_exact_period(self):
        _, pred = run("predict", "pendulum", "--length", 2, "--amplitude", 30)
        path = recording({"angle": simulate_pendulum(2, 30)})
        code, res = run("period", path, "--probe", "angle", "--expected",
                        pred["prediction"]["period_s"], "--tol", 0.01)
        self.assertEqual(code, 0, res)

    def test_wrong_length_fails(self):
        path = recording({"angle": simulate_pendulum(1, 10)})
        code, _ = run("period", path, "--probe", "angle", "--expected",
                      2 * math.pi * math.sqrt(2 / G))
        self.assertEqual(code, 1)


class Strain(unittest.TestCase):
    def test_stiff_cloth_passes_rubbery_fails(self):
        def edges(stretch):
            return {"edges": [{"rest": 0.1, "a": [0, 0, 0], "b": [0.1 * (1 + stretch * (i % 3) / 2),
                                                                 0, 0]} for i in range(30)]}
        self.assertEqual(run("strain", write(edges(0.01)))[0], 0)
        code, res = run("strain", write(edges(0.08)))
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["value"], 0.08, places=4)


class Sag(unittest.TestCase):
    def rope(self, span, length, extra=1.0):
        _, res = run("predict", "catenary", "--span", span, "--length", length)
        a = res["prediction"]["parameter_a"]
        pts = []
        for i in range(41):
            x = -span / 2 + span * i / 40
            pts.append([x + span / 2, extra * a * (math.cosh(x / a) - math.cosh(span / (2 * a))),
                        0.0])
        return write({"points": pts, "rest_length": length})

    def test_rope_hangs_as_a_catenary(self):
        self.assertEqual(run("sag", self.rope(10, 12))[0], 0)

    def test_overstretched_rope_fails(self):
        self.assertEqual(run("sag", self.rope(10, 12, extra=1.3))[0], 1)


class Energy(unittest.TestCase):
    def test_damped_passes_gaining_fails(self):
        damped = [100 * math.exp(-0.2 * i / 60) for i in range(600)]
        self.assertEqual(run("energy", recording({"E": damped}), "--total", "E")[0], 0)
        gaining = [100 * math.exp(-0.2 * i / 60) + (5 if i > 300 else 0) for i in range(600)]
        code, res = run("energy", recording({"E": gaining}), "--total", "E")
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["at_s"], 301 / 60, places=2)


class Settle(unittest.TestCase):
    def test_settles_in_time_or_never(self):
        speeds = [2 * math.exp(-1.5 * i / 60) for i in range(600)]
        self.assertEqual(run("settle", recording({"v": speeds}), "--speed", "v")[0], 0)
        jitter = [0.2 + 0.1 * math.sin(i) for i in range(600)]
        self.assertEqual(run("settle", recording({"v": jitter}), "--speed", "v")[0], 1)


if __name__ == "__main__":
    unittest.main()
