"""Tests for plugins/kiln/skills/flight/scripts/flight_check.py (stdlib only)."""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "flight",
                      "scripts", "flight_check.py")
G = 9.81


def write(data):
    fd, path = tempfile.mkstemp(prefix="kiln-flight-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *map(str, args)], capture_output=True,
                       text=True, timeout=60, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


def recording(samples, hz=60):
    n = max(len(v) for v in samples.values())
    return write({"physics_ticks_per_second": hz, "ticks": list(range(n)), "samples": samples})


class Predict(unittest.TestCase):
    def test_jetpack_hover_and_lean(self):
        # 100 kg, T/W 1.3: climb 2.943 m/s2, max level lean acos(1/1.3) = 39.7 deg
        _, res = run("predict", "hover", "--mass", 100, "--thrust", 1.3 * 100 * G)
        p = res["prediction"]
        self.assertAlmostEqual(p["thrust_to_weight"], 1.3)
        self.assertAlmostEqual(p["climb_accel"], 0.3 * G, places=3)
        self.assertAlmostEqual(p["max_level_lean_deg"], math.degrees(math.acos(1 / 1.3)), places=1)
        _, rocket_belt = run("predict", "hover", "--mass", 57 + 80, "--thrust", 1334)
        self.assertFalse(rocket_belt["prediction"]["hovers"])  # Bell belt + 80 kg pilot

    def test_stall_speed(self):
        # wing loading 69.7 kg/m2, CLmax 1.5: Vs = sqrt(2*69.7*9.81/(1.225*1.5)) = 27.3 m/s
        _, res = run("predict", "stall", "--mass", 69.7, "--area", 1, "--clmax", 1.5)
        self.assertAlmostEqual(res["prediction"]["stall_m_s"], 27.3, delta=0.1)

    def test_turn_radius_and_load(self):
        _, res = run("predict", "turn", "--v", 60, "--bank", 60, "--vs", 27.3)
        p = res["prediction"]
        self.assertAlmostEqual(p["radius_m"], 3600 / (G * math.tan(math.radians(60))), places=1)
        self.assertAlmostEqual(p["load_factor"], 2.0, places=3)
        self.assertAlmostEqual(p["stall_in_turn_m_s"], 27.3 * math.sqrt(2), places=2)

    def test_glide_and_rotor_and_fuel(self):
        _, g = run("predict", "glide", "--ratio", 2.5, "--height", 3000, "--v", 160 / 3.6)
        self.assertEqual(g["prediction"]["distance_m"], 7500.0)
        self.assertAlmostEqual(g["prediction"]["time_s"], 3000 / (160 / 3.6 / 2.5), places=0)
        _, r = run("predict", "rotor", "--mass", 2000, "--diameter", 11)
        self.assertAlmostEqual(r["prediction"]["induced_m_s"], 9.18, delta=0.02)
        self.assertAlmostEqual(r["prediction"]["ideal_power_kw"], 180, delta=1.0)
        _, f = run("predict", "fuel", "--capacity", 40, "--burn", 4)
        self.assertEqual(f["prediction"]["endurance_min"], 10.0)


class Loadout(unittest.TestCase):
    def test_fuel_and_gadget_weight(self):
        # Bell-belt-like: 30.6 kg dry + 80 kg pilot + 26.4 kg fuel = 137 kg, 1334 N:
        # T/W 0.993 full (can't take off), 1.229 empty; hovers once 1.0 kg of fuel is gone
        _, res = run("predict", "loadout", "--dry", 30.6, "--pilot", 80, "--fuel", 26.4,
                     "--thrust", 1334, "--isp", 140)
        p = res["prediction"]
        self.assertFalse(p["hovers_at_takeoff"])
        self.assertAlmostEqual(p["tw_empty"], 1334 / (110.6 * G), places=3)
        m_hover = 1334 / G
        expected = 140 * 9.80665 / G * math.log(m_hover / 110.6)
        self.assertAlmostEqual(p["hover_endurance_s"], expected, places=1)

    def test_gadgets_cut_lift(self):
        _, light = run("predict", "loadout", "--dry", 27, "--pilot", 80, "--fuel", 30,
                       "--thrust", 1800)
        _, heavy = run("predict", "loadout", "--dry", 27, "--pilot", 80, "--fuel", 30,
                       "--thrust", 1800, "--gadgets", 50)  # 187 kg > 183.5 kg
        self.assertGreater(light["prediction"]["tw_full"], heavy["prediction"]["tw_full"])
        self.assertAlmostEqual(light["prediction"]["max_gadgets_kg"], 1800 / G - 137, places=1)
        self.assertFalse(heavy["prediction"]["hovers_at_takeoff"])


class Measure(unittest.TestCase):
    def test_hover_steady_vs_bobbing(self):
        steady = [[0, 10 + 0.05 * math.sin(i / 10), 0] for i in range(300)]
        bob = [[0, 10 + 0.6 * math.sin(i / 10), 0] for i in range(300)]
        self.assertEqual(run("hover", recording({"jet": steady}), "--pos", "jet")[0], 0)
        self.assertEqual(run("hover", recording({"jet": bob}), "--pos", "jet")[0], 1)

    def test_glide_ratio(self):
        path = [[i * 10 / 60, 1000 - i * (10 / 9) / 60, 0] for i in range(600)]
        self.assertEqual(run("glide", recording({"pg": path}), "--pos", "pg", "--ratio", 9)[0], 0)
        self.assertEqual(run("glide", recording({"pg": path}), "--pos", "pg", "--ratio", 2.5)[0], 1)

    def test_coordinated_turn(self):
        v, bank = 20.0, 30.0
        r = v * v / (G * math.tan(math.radians(bank)))
        w = v / r
        circle = [[r * math.cos(w * i / 60), 100, r * math.sin(w * i / 60)] for i in range(900)]
        self.assertEqual(run("turn", recording({"plane": circle}), "--pos", "plane", "--bank",
                             bank)[0], 0)
        self.assertEqual(run("turn", recording({"plane": circle}), "--pos", "plane", "--bank",
                             60)[0], 1)


if __name__ == "__main__":
    unittest.main()
