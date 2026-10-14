"""Tests for plugins/kiln/skills/fields-forces/scripts/field_check.py (stdlib only).

Expected numbers come from the closed-form answers in the script's docstring; every check is also
shown failing on a broken input.
"""

import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "fields-forces", "scripts", "field_check.py")


def write(data):
    fd, path = tempfile.mkstemp(prefix="kiln-field-", suffix=".json")
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


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


class Predict(unittest.TestCase):
    def test_low_earth_orbit(self):
        # mu 3.986e14, r 6771 km: v = 7672.6 m/s, T = 5544.9 s, v_esc = sqrt(2)*v
        _, res = run("predict", "orbit", "--mu", 3.986e14, "--r", 6.771e6)
        p = res["prediction"]
        self.assertAlmostEqual(p["v_circular"], math.sqrt(3.986e14 / 6.771e6), places=2)
        self.assertAlmostEqual(p["period_s"], 2 * math.pi * math.sqrt(6.771e6 ** 3 / 3.986e14),
                               places=1)
        self.assertAlmostEqual(p["v_escape"] / p["v_circular"], math.sqrt(2), places=4)

    def test_kepler_mars(self):
        _, res = run("predict", "kepler", "--a1", 1, "--t1", 365.25, "--a2", 1.524)
        self.assertAlmostEqual(res["prediction"]["t2"], 365.25 * 1.524 ** 1.5, places=2)

    def test_projectile_vacuum_and_drag(self):
        # 30 m/s at 45 deg: range v^2/g = 91.74 m, flight 4.325 s, apex 22.94 m
        _, vac = run("predict", "projectile", "--v", 30, "--angle", 45)
        self.assertAlmostEqual(vac["prediction"]["vacuum_range_m"], 900 / 9.81, places=2)
        self.assertAlmostEqual(vac["prediction"]["vacuum_apex_m"], 450 / (2 * 9.81) * 1, places=2)
        _, drag = run("predict", "projectile", "--v", 30, "--angle", 45, "--mass", 0.43,
                      "--cd", 0.25, "--area", 0.038)
        self.assertLess(drag["prediction"]["drag_range_m"], vac["prediction"]["vacuum_range_m"])
        # independent check: semi-implicit Euler at 0.1 ms
        k = 0.5 * 1.225 * 0.25 * 0.038 / 0.43
        x, y = 0.0, 0.0
        vx = vy = 30 * math.cos(math.radians(45))
        dt = 1e-4
        while y >= 0:
            sp = math.hypot(vx, vy)
            vx -= k * sp * vx * dt
            vy -= (9.81 + k * sp * vy) * dt
            x, y = x + vx * dt, y + vy * dt
        self.assertAlmostEqual(drag["prediction"]["drag_range_m"], x, delta=0.05)

    def test_drag_free_limit_matches_vacuum(self):
        _, res = run("predict", "projectile", "--v", 20, "--angle", 30, "--mass", 1000,
                     "--cd", 1e-6, "--area", 1e-6)
        p = res["prediction"]
        self.assertAlmostEqual(p["drag_range_m"], p["vacuum_range_m"], places=1)

    def test_skydiver_terminal_speed(self):
        # 80 kg, Cd 1.0, A 0.7, rho 1.225: vt = sqrt(2*80*9.81/(1.225*0.7)) = 42.78 m/s
        _, res = run("predict", "terminal", "--mass", 80, "--cd", 1.0, "--area", 0.7)
        vt = math.sqrt(2 * 80 * 9.81 / (1.225 * 0.7))
        self.assertAlmostEqual(res["prediction"]["v_terminal"], vt, places=2)
        self.assertAlmostEqual(res["prediction"]["t95_s"], vt / 9.81 * math.atanh(0.95), places=2)

    def test_float32_spacing(self):
        # float32 step at 10 km is 2^-10 m = 0.977 mm; at 1 km 2^-14 = 0.061 mm
        _, far = run("predict", "ulp", "--distance", 10000)
        self.assertAlmostEqual(far["prediction"]["float32_step_m"], 2 ** -10)
        _, near = run("predict", "ulp", "--distance", 1000)
        self.assertAlmostEqual(near["prediction"]["float32_step_m"], 2 ** -14)

    def test_refraction_and_total_internal_reflection(self):
        _, res = run("predict", "refract", "--n1", 1.0, "--n2", 1.33, "--angle", 30)
        self.assertAlmostEqual(res["prediction"]["refracted_deg"],
                               math.degrees(math.asin(0.5 / 1.33)), places=3)
        _, tir = run("predict", "refract", "--n1", 1.5, "--n2", 1.0, "--angle", 60)
        self.assertTrue(tir["prediction"]["total_internal_reflection"])
        self.assertAlmostEqual(tir["prediction"]["critical_angle_deg"],
                               math.degrees(math.asin(1 / 1.5)), places=3)


def integrate_orbit(mu, r, steps, dt, symplectic=True):
    x, y, vx, vy = r, 0.0, 0.0, math.sqrt(mu / r)
    pos = []
    for _ in range(steps):
        pos.append([x, 0.0, y])
        ax, ay = -mu * x / (x * x + y * y) ** 1.5, -mu * y / (x * x + y * y) ** 1.5
        if symplectic:  # semi-implicit Euler
            vx, vy = vx + ax * dt, vy + ay * dt
            x, y = x + vx * dt, y + vy * dt
        else:  # explicit Euler gains energy every step
            x, y = x + vx * dt, y + vy * dt
            vx, vy = vx + ax * dt, vy + ay * dt
    return pos


class Orbit(unittest.TestCase):
    MU, R = 1000.0, 10.0  # T = 2*pi*sqrt(1000/1000) = 6.283 s

    def test_symplectic_orbit_passes(self):
        path = recording({"moon": integrate_orbit(self.MU, self.R, 60 * 13, 1 / 60)})
        code, res = run("orbit", path, "--pos", "moon", "--mu", self.MU)
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["metrics"][0]["value"], 2 * math.pi, delta=0.05)

    def test_explicit_euler_drifts_and_fails(self):
        path = recording({"moon": integrate_orbit(self.MU, self.R, 60 * 13, 1 / 60,
                                                  symplectic=False)})
        code, res = run("orbit", path, "--pos", "moon", "--mu", self.MU)
        self.assertEqual(code, 1)
        drift = next(m for m in res["metrics"] if m["metric"] == "orbit_energy_drift")
        self.assertEqual(drift["verdict"], "FAIL")

    def test_short_recording_not_assessed(self):
        path = recording({"moon": integrate_orbit(self.MU, self.R, 60, 1 / 60)})
        self.assertEqual(run("orbit", path, "--pos", "moon", "--mu", self.MU)[1]["verdict"],
                         "NOT ASSESSED")


class FallAndTerminal(unittest.TestCase):
    def drop(self, g):
        pos, y, v = [], 20.0, 0.0
        for _ in range(240):
            pos.append([0.0, y, 0.0])
            v -= g / 60
            y += v / 60
            if y < 0:
                y, v = 0.0, -0.5 * v
        return recording({"ball": pos})

    def test_earth_gravity_passes_moon_fails(self):
        self.assertEqual(run("fall", self.drop(9.81), "--pos", "ball")[0], 0)
        code, res = run("fall", self.drop(1.62), "--pos", "ball", "--g", 9.81)
        self.assertEqual(code, 1)

    def test_terminal_plateau(self):
        vt = 42.78
        speeds = [vt * math.tanh(9.81 * (i / 60) / vt) for i in range(60 * 30)]
        self.assertEqual(run("terminal", recording({"v": speeds}), "--vel", "v", "--vt", vt)[0], 0)
        self.assertEqual(run("terminal", recording({"v": speeds}), "--vel", "v", "--vt", 53)[0], 1)


class Jitter(unittest.TestCase):
    def test_float32_far_from_origin(self):
        # an object gliding at 1 m/s, stored as float32 at 100 km from the origin: steps of
        # 7.8 mm show up as jitter; near the origin the same motion is smooth
        far = [[f32(100000.0 + i / 60), 0.0, 0.0] for i in range(300)]
        near = [[f32(10.0 + i / 60), 0.0, 0.0] for i in range(300)]
        code, res = run("jitter", recording({"p": far}), "--pos", "p", "--max-mm", 1)
        self.assertEqual(code, 1, res)
        self.assertEqual(run("jitter", recording({"p": near}), "--pos", "p", "--max-mm", 1)[0], 0)


class Beams(unittest.TestCase):
    def test_reflection_and_refraction(self):
        s = math.sin(math.radians(30)) / 1.33
        t = math.asin(s)
        hits = [{"kind": "reflect", "normal": [0, 1, 0], "in": [1, -1, 0], "out": [1, 1, 0]},
                {"kind": "refract", "n1": 1.0, "n2": 1.33, "normal": [0, 1, 0],
                 "in": [math.sin(math.radians(30)), -math.cos(math.radians(30)), 0],
                 "out": [math.sin(t), -math.cos(t), 0]}]
        code, res = run("beams", write({"hits": hits}))
        self.assertEqual(code, 0, res)

    def test_wrong_reflection_fails(self):
        hits = [{"kind": "reflect", "normal": [0, 1, 0], "in": [1, -1, 0], "out": [1, 2, 0]}]
        code, res = run("beams", write({"hits": hits}))
        self.assertEqual(code, 1)
        self.assertEqual(len(res["metrics"][0]["failures"]), 1)


if __name__ == "__main__":
    unittest.main()
