"""Tests for plugins/kiln/skills/vehicles/scripts/vehicle_check.py (stdlib only).

Expected numbers come from closed forms or from a small simulation inside the test; every check is
also shown failing on a broken input.
"""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "vehicles", "scripts", "vehicle_check.py")
G = 9.81


def write(data):
    fd, path = tempfile.mkstemp(prefix="kiln-vehicle-", suffix=".json")
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


class Predict(unittest.TestCase):
    def test_stopping_distance_dry_and_wet(self):
        # 100 km/h = 27.78 m/s: dry mu 0.8 -> 49.16 m; wet 0.5 -> 78.66 m; +1 s reaction 27.78 m
        v = 100 / 3.6
        _, dry = run("predict", "stop", "--v-kmh", 100, "--mu", 0.8, "--reaction-s", 1)
        self.assertAlmostEqual(dry["prediction"]["braking_m"], v * v / (2 * 0.8 * G), places=2)
        self.assertAlmostEqual(dry["prediction"]["total_m"], v * v / (2 * 0.8 * G) + v, places=2)
        _, wet = run("predict", "stop", "--v-kmh", 100, "--mu", 0.5)
        self.assertAlmostEqual(wet["prediction"]["braking_m"], v * v / (2 * 0.5 * G), places=2)

    def test_skidpad(self):
        # mu 0.9, r 50 m: v = sqrt(0.9*9.81*50) = 21.01 m/s = 75.6 km/h
        _, res = run("predict", "corner", "--mu", 0.9, "--radius", 50)
        self.assertAlmostEqual(res["prediction"]["v_max_m_s"], math.sqrt(0.9 * G * 50), places=3)

    def test_ride_frequency(self):
        # 30 kN/m on a 375 kg corner: f = sqrt(80)/(2*pi) = 1.4235 Hz; c 2500 -> zeta 0.3727
        _, res = run("predict", "ride", "--k", 30000, "--mass", 375, "--c", 2500)
        self.assertAlmostEqual(res["prediction"]["frequency_hz"],
                               math.sqrt(30000 / 375) / (2 * math.pi), places=3)
        self.assertAlmostEqual(res["prediction"]["damping_ratio"],
                               2500 / (2 * math.sqrt(30000 * 375)), places=3)

    def test_top_speed_balances_power(self):
        _, res = run("predict", "topspeed", "--power", 100000, "--cd", 0.3, "--area", 2.2,
                     "--crr", 0.012, "--mass", 1500)
        v = res["prediction"]["v_max_m_s"]
        need = (0.5 * 1.225 * 0.3 * 2.2 * v * v + 0.012 * 1500 * G) * v
        self.assertAlmostEqual(need, 100000, delta=50)
        self.assertGreater(res["prediction"]["v_max_kmh"], 200)

    def test_launch_traction_and_power(self):
        # traction only, mu 1.0, half the weight on driven wheels: 27.78/(4.905) = 5.66 s
        _, res = run("predict", "launch", "--v-kmh", 100, "--mu", 1.0, "--driven-share", 0.5,
                     "--power", 100000, "--mass", 1500)
        self.assertAlmostEqual(res["prediction"]["traction_limited_s"], (100 / 3.6) / (0.5 * G),
                               places=2)
        self.assertGreater(res["prediction"]["time_s"], res["prediction"]["traction_limited_s"])

    def test_weight_transfer(self):
        # 1500 kg, 0.8 g, h 0.55, L 2.7: 1500*0.8*9.81*0.55/2.7 = 2398 N = 16.3 % of weight
        _, res = run("predict", "transfer", "--mass", 1500, "--a-g", 0.8, "--h", 0.55,
                     "--wheelbase", 2.7)
        self.assertAlmostEqual(res["prediction"]["load_transfer_n"],
                               1500 * 0.8 * G * 0.55 / 2.7, places=1)


class Stop(unittest.TestCase):
    def brake_run(self, mu):
        v, speeds, brakes = 100 / 3.6, [], []
        for i in range(600):
            braking = i >= 60
            speeds.append(max(v, 0.0))
            brakes.append(braking)
            if braking:
                v -= mu * G / 60
        return recording({"v": speeds, "brake": brakes})

    def test_brakes_match_design_mu(self):
        expected = (100 / 3.6) ** 2 / (2 * 0.8 * G)
        code, res = run("stop", self.brake_run(0.8), "--speed", "v", "--brake", "brake",
                        "--expected-m", expected, "--tol", 0.03)
        self.assertEqual(code, 0, res)

    def test_icy_brakes_fail(self):
        expected = (100 / 3.6) ** 2 / (2 * 0.8 * G)
        code, _ = run("stop", self.brake_run(0.3), "--speed", "v", "--brake", "brake",
                      "--expected-m", expected)
        self.assertEqual(code, 1)


class Corner(unittest.TestCase):
    def circle(self, v, r):
        w = v / r
        pos = [[r * math.cos(w * i / 60), 0.5, r * math.sin(w * i / 60)] for i in range(600)]
        return recording({"car": pos, "v": [v] * 600})

    def test_skidpad_lateral_g(self):
        v = math.sqrt(0.9 * G * 50)
        self.assertEqual(run("corner", self.circle(v, 50), "--pos", "car", "--speed", "v",
                             "--expected-g", 0.9)[0], 0)
        self.assertEqual(run("corner", self.circle(v * 0.7, 50), "--pos", "car", "--speed", "v",
                             "--expected-g", 0.9)[0], 1)


class Ride(unittest.TestCase):
    def bump(self, f, zeta):
        wn = 2 * math.pi * f
        wd = wn * math.sqrt(1 - zeta ** 2)
        return recording({"y": [0.5 + 0.05 * math.exp(-zeta * wn * i / 240) * math.cos(wd * i / 240)
                                for i in range(240 * 6)]}, hz=240)

    def test_frequency_and_damping(self):
        code, res = run("ride", self.bump(1.4, 0.25), "--height", "y", "--expected-hz", 1.4,
                        "--zeta", 0.25, "--zeta-tol", 0.03)
        self.assertEqual(code, 0, res)

    def test_bouncy_soft_suspension_fails(self):
        code, _ = run("ride", self.bump(0.8, 0.05), "--height", "y", "--expected-hz", 1.4,
                      "--zeta", 0.25)
        self.assertEqual(code, 1)


class Launch(unittest.TestCase):
    def test_launch_time(self):
        speeds = [min(i / 60 * 4.905, 40) for i in range(60 * 10)]
        t = (100 / 3.6) / 4.905
        self.assertEqual(run("launch", recording({"v": speeds}), "--speed", "v", "--target-kmh",
                             100, "--expected-s", t)[0], 0)
        self.assertEqual(run("launch", recording({"v": speeds}), "--speed", "v", "--target-kmh",
                             100, "--expected-s", 3.5)[0], 1)


if __name__ == "__main__":
    unittest.main()
