"""Tests for plugins/kiln/skills/elements-materials/scripts/element_check.py (stdlib only).

Every expected number is computed by hand from the formula in the docstring, and every check is
also shown failing on a broken input — a check that cannot fail is not a check.
"""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "elements-materials", "scripts", "element_check.py")


def write(data, suffix=".json"):
    fd, path = tempfile.mkstemp(prefix="kiln-element-", suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        if suffix == ".jsonl":
            fh.write("\n".join(json.dumps(r) for r in data) + "\n")
        else:
            json.dump(data, fh)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *map(str, args)], capture_output=True,
                       text=True, timeout=60, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


def recording(samples, hz=10):
    n = max(len(v) for v in samples.values())
    return write({"physics_ticks_per_second": hz, "ticks": list(range(n)), "samples": samples})


class Predict(unittest.TestCase):
    def test_melt_ice_cube(self):
        # 1 kg ice at -10 C: 1*2100*10 + 1*334000 = 355000 J; at 500 W -> 710 s; x60 -> 11.83 s
        code, res = run("predict", "melt", "--mass", 1, "--c", 2100, "--t0", -10, "--t-melt", 0,
                        "--latent", 334000, "--power", 500, "--time-scale", 60)
        self.assertEqual(code, 0)
        self.assertEqual(res["prediction"]["energy_j"], 355000.0)
        self.assertEqual(res["prediction"]["real_s"], 710.0)
        self.assertAlmostEqual(res["prediction"]["game_s"], 11.83, places=2)

    def test_newton_cooling_time(self):
        # 90 -> 30 C at 20 C ambient, tau 60 s: t = -60 ln(10/70) = 116.75 s
        code, res = run("predict", "cool", "--t0", 90, "--ambient", 20, "--tau", 60,
                        "--target", 30)
        self.assertEqual(code, 0)
        self.assertAlmostEqual(res["prediction"]["real_s"], 60 * math.log(7), places=2)
        self.assertAlmostEqual(res["prediction"]["half_life_s"], 41.59, places=2)

    def test_tau_from_lump(self):
        # 1 kg aluminium (c 900) with 0.06 m2 in still air h 10: tau = 900/(0.6) = 1500 s
        code, res = run("predict", "tau", "--mass", 1, "--c", 900, "--h", 10, "--area", 0.06)
        self.assertEqual(res["prediction"]["tau_s"], 1500.0)

    def test_stability_limit(self):
        _, ok = run("predict", "stable", "--alpha", 1e-4, "--dx", 0.5, "--dt", 0.1, "--dims", 2)
        self.assertTrue(ok["prediction"]["stable"])
        self.assertAlmostEqual(ok["prediction"]["max_dt_s"], 625.0)  # 0.25 * 0.25 / 1e-4
        _, bad = run("predict", "stable", "--alpha", 0.1, "--dx", 0.1, "--dt", 0.1, "--dims", 2)
        self.assertFalse(bad["prediction"]["stable"])  # r = 1.0 > 0.25

    def test_front_lower_bound(self):
        _, res = run("predict", "front", "--p", 0.3, "--dx", 0.5, "--hz", 10)
        self.assertAlmostEqual(res["prediction"]["speed_m_s"], 1.5)

    def test_front_with_burn_time(self):
        # p 0.5, burns 3 ticks: q = 1 - 0.5^3 = 0.875, mean 1-D run 0.875/0.125 = 7 cells
        _, res = run("predict", "front", "--p", 0.5, "--dx", 1, "--hz", 1, "--burn", 3)
        self.assertAlmostEqual(res["prediction"]["pass_probability"], 0.875)
        self.assertAlmostEqual(res["prediction"]["mean_run_cells_1d"], 7.0)
        self.assertEqual(res["prediction"]["regime_2d"], "runs away")
        _, low = run("predict", "front", "--p", 0.3, "--dx", 1, "--hz", 1, "--burn", 1)
        self.assertEqual(low["prediction"]["regime_2d"], "dies out")

    def test_missing_input_is_an_error(self):
        code, res = run("predict", "melt", "--mass", 1, "--c", 2100, "--t0", -10)
        self.assertEqual(code, 2)
        self.assertEqual(res["verdict"], "ERROR")


class Cooling(unittest.TestCase):
    def curve(self, tau):
        return recording({"T": [20 + 70 * math.exp(-(i / 10) / tau) for i in range(1200)]})

    def test_matching_tau_passes(self):
        code, res = run("cooling", self.curve(60), "--temp", "T", "--ambient", 20, "--tau", 60)
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["metrics"][0]["value"], 60, places=1)

    def test_wrong_tau_fails(self):
        code, res = run("cooling", self.curve(30), "--temp", "T", "--ambient", 20, "--tau", 60)
        self.assertEqual(code, 1)
        self.assertEqual(res["verdict"], "FAIL")

    def test_missing_probe_not_assessed(self):
        code, res = run("cooling", self.curve(60), "--temp", "X", "--ambient", 20, "--tau", 60)
        self.assertEqual(res["verdict"], "NOT ASSESSED")


class Threshold(unittest.TestCase):
    def freeze(self, at_temp):
        temps = [5 - 0.5 * i for i in range(21)]  # 5 .. -5
        states = ["wet" if t > at_temp else "frozen" for t in temps]
        return recording({"T": temps, "S": states})

    def test_freezes_at_zero(self):
        code, res = run("threshold", self.freeze(0), "--temp", "T", "--state", "S", "--to",
                        "frozen", "--from", "wet", "--at", 0, "--tol", 0.5)
        self.assertEqual(code, 0, res)

    def test_early_freeze_fails(self):
        code, res = run("threshold", self.freeze(3), "--temp", "T", "--state", "S", "--to",
                        "frozen", "--at", 0, "--tol", 0.5)
        self.assertEqual(code, 1)
        self.assertTrue(res["metrics"][0]["early"])

    def test_never_changing_after_crossing_fails(self):
        path = recording({"T": [5 - 0.5 * i for i in range(21)], "S": ["wet"] * 21})
        code, res = run("threshold", path, "--temp", "T", "--state", "S", "--to", "frozen",
                        "--at", 0)
        self.assertEqual(code, 1)

    def test_heating_threshold_with_jsonl(self):
        rows = [{"t": i * 0.1, "T": 250 + 5 * i, "S": "wood" if 250 + 5 * i < 300 else "burning"}
                for i in range(20)]
        code, res = run("threshold", write(rows, ".jsonl"), "--temp", "T", "--state", "S",
                        "--to", "burning", "--at", 300, "--tol", 5, "--above")
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["metrics"][0]["t_s"], 1.0)


class Conserve(unittest.TestCase):
    def test_small_drift_passes_large_fails(self):
        ok = recording({"E": [1000 + 5 * math.sin(i) for i in range(100)]})
        self.assertEqual(run("conserve", ok, "--total", "E", "--tol", 0.01)[0], 0)
        bad = recording({"E": [1000 * (1 + 0.001 * i) for i in range(100)]})  # +9.9 %
        code, res = run("conserve", bad, "--total", "E", "--tol", 0.01)
        self.assertEqual(code, 1)


class Diffusion(unittest.TestCase):
    def ftcs(self, alpha, dx=0.05, n=201, steps=1000, every=100):
        """Explicit heat equation, a hot spike in the middle, edges held at ambient; the spot
        stays > 3 sigma from the edges (sigma 1.4 m at the end, edges at 5 m)."""
        dt = 0.4 * dx * dx / alpha
        u = [20.0] * n
        u[n // 2] = 520.0
        frames = []
        for k in range(steps + 1):
            if k % every == 0:
                frames.append({"t": k * dt, "temp": list(u)})
            r = alpha * dt / dx ** 2
            u = [u[i] + r * (u[i - 1] - 2 * u[i] + u[i + 1]) if 0 < i < n - 1 else u[i]
                 for i in range(n)]
        return write({"dx": dx, "frames": frames})

    def test_solver_with_the_design_diffusivity_passes(self):
        code, res = run("diffusion", self.ftcs(1e-4), "--alpha", 1e-4)
        self.assertEqual(code, 0, res)
        self.assertLess(res["metrics"][0]["relative_error"], 0.05)

    def test_wrong_diffusivity_fails(self):
        code, res = run("diffusion", self.ftcs(1e-4), "--alpha", 3e-4)
        self.assertEqual(code, 1)

    def test_two_dimensional_gaussian(self):
        alpha, dx, n = 2e-3, 0.1, 61
        frames = []
        for t in (1.0, 5.0, 9.0):
            var = 0.04 + 2 * alpha * t
            c = (n - 1) / 2
            frames.append({"t": t, "temp": [[math.exp(-(((x - c) * dx) ** 2 + ((y - c) * dx) ** 2)
                                                      / (2 * var)) for x in range(n)]
                                            for y in range(n)]})
        code, res = run("diffusion", write({"dx": dx, "frames": frames}), "--alpha", alpha,
                        "--tol", 0.05)
        self.assertEqual(code, 0, res)


class Spread(unittest.TestCase):
    def line(self, speed=0.5, dx=0.5, n=20, wall_at=None, burn=6.0):
        cells = []
        for x in range(n):
            flammable = x != wall_at
            t = x * dx / speed
            cells.append({"x": x, "y": 0, "flammable": flammable, "ignite_t": t,
                          "out_t": t + burn})
        return cells

    def test_front_speed_and_burn_out(self):
        path = write({"dx": 0.5, "cells": self.line()})
        code, res = run("spread", path, "--speed", 0.5, "--max-burn", 10, "--cap", 20)
        self.assertEqual(code, 0, res)
        speed = next(m for m in res["metrics"] if m["metric"] == "front_speed_m_s")
        self.assertAlmostEqual(speed["value"], 0.5)
        peak = next(m for m in res["metrics"] if m["metric"] == "concurrent_burning_peak")
        self.assertEqual(peak["value"], 6)  # burn 6 s, a new cell every 1 s; out before in at ties

    def test_stone_igniting_and_endless_fire_fail(self):
        cells = self.line(wall_at=10)
        cells[3]["out_t"] = None
        code, res = run("spread", write({"dx": 0.5, "cells": cells}), "--speed", 0.5,
                        "--max-burn", 10, "--cap", 5)
        self.assertEqual(code, 1)
        failed = {m["metric"] for m in res["metrics"] if m["verdict"] == "FAIL"}
        self.assertEqual(failed, {"non_flammable_ignited", "burn_out", "concurrent_burning_peak"})

    def test_too_slow_front_fails(self):
        path = write({"dx": 0.5, "cells": self.line(speed=0.2)})
        self.assertEqual(run("spread", path, "--speed", 0.5)[0], 1)


class Conduction(unittest.TestCase):
    def graph(self, wood_powered=False, last_powered=False):
        nodes = [{"id": "battery", "conductive": True, "powered": True, "source": True},
                 {"id": "rail1", "conductive": True, "powered": True},
                 {"id": "puddle", "conductive": True, "powered": True},
                 {"id": "crate", "conductive": False, "powered": wood_powered},
                 {"id": "rail2", "conductive": True, "powered": last_powered}]
        edges = [["battery", "rail1"], ["rail1", "puddle"], ["puddle", "crate"],
                 ["crate", "rail2"]]
        return write({"nodes": nodes, "edges": edges})

    def test_current_stops_at_wood(self):
        code, res = run("conduction", self.graph())
        self.assertEqual(code, 0, res)

    def test_current_through_wood_fails(self):
        code, res = run("conduction", self.graph(wood_powered=True, last_powered=True))
        self.assertEqual(code, 1)
        self.assertEqual(res["metrics"][0]["nodes"], ["crate", "rail2"])

    def test_unpowered_reachable_conductor_fails(self):
        nodes = [{"id": "s", "conductive": True, "powered": True, "source": True},
                 {"id": "a", "conductive": True, "powered": False}]
        code, res = run("conduction", write({"nodes": nodes, "edges": [["s", "a"]]}))
        self.assertEqual(code, 1)
        self.assertEqual(res["metrics"][1]["nodes"], ["a"])


if __name__ == "__main__":
    unittest.main()
