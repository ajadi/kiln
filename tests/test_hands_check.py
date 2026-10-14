"""Tests for plugins/kiln/skills/hands/scripts/hands_check.py (stdlib only)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "hands",
                      "scripts", "hands_check.py")


def write(data):
    fd, path = tempfile.mkstemp(prefix="kiln-hands-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *map(str, args)], capture_output=True,
                       text=True, timeout=60, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


def recording(samples):
    n = max(len(v) for v in samples.values())
    return write({"physics_ticks_per_second": 60, "ticks": list(range(n)), "samples": samples})


class Hands(unittest.TestCase):
    def test_handle_diameter_and_grip_table(self):
        _, res = run("predict", "handle", "--hand-length", 191)
        self.assertAlmostEqual(res["prediction"]["diameter_mm"], 37.6, places=1)
        _, g = run("predict", "grip", "--object", "rifle")
        self.assertIn("foregrip", g["prediction"]["grip"])
        self.assertEqual(run("predict", "grip", "--object", "banana")[0], 2)

    def test_finger_rom(self):
        ok = recording({"i_mcp": [0, 45, 85], "i_pip": [10, 60, 110], "i_dip": [-5, 30, 80]})
        self.assertEqual(run("rom", ok, "--joints", "i_mcp=mcp,i_pip=pip,i_dip=dip")[0], 0)
        bent_back = recording({"i_pip": [-15, 40], "i_dip": [-25, 30]})
        code, res = run("rom", bent_back, "--joints", "i_pip=pip,i_dip=dip")
        self.assertEqual(code, 1)
        self.assertEqual(len(res["metrics"][0]["violations"]), 2)
        crimp = recording({"i_dip": [-25, 30]})
        self.assertEqual(run("rom", crimp, "--joints", "i_dip=dip", "--crimp")[0], 0)

    def test_support_hand_drift_and_wrist(self):
        grip = [[0.3, 1.2, 0.1 * i / 60] for i in range(120)]
        hand_ok = [[g[0] + 0.002, g[1], g[2]] for g in grip]
        hand_slide = [[g[0] + 0.002 + (0.02 if i > 60 else 0), g[1], g[2]] for i, g in enumerate(grip)]
        self.assertEqual(run("drift", recording({"h": hand_ok, "g": grip}), "--hand", "h",
                             "--grip", "g")[0], 0)
        self.assertEqual(run("drift", recording({"h": hand_slide, "g": grip}), "--hand", "h",
                             "--grip", "g")[0], 1)
        wr = recording({"rad": [5, 10], "uln": [20, 50]})
        self.assertEqual(run("wrist", wr, "--radial", "rad", "--ulnar", "uln")[0], 1)
        self.assertEqual(run("wrist", wr, "--radial", "rad", "--ulnar", "uln", "--support")[0], 0)


if __name__ == "__main__":
    unittest.main()
