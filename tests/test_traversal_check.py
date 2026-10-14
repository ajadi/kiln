"""Tests for plugins/kiln/skills/traversal/scripts/traversal_check.py (stdlib only).

Expected numbers come from closed forms; every check is also shown failing on a broken input.
"""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "traversal", "scripts", "traversal_check.py")
G = 9.81


def write(data):
    fd, path = tempfile.mkstemp(prefix="kiln-trav-", suffix=".json")
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
    def test_jump_from_height(self):
        # 0.5 m rise: v0 = 3.132 m/s, airtime 0.6386 s (human-biomechanics skill: 3.13, 0.64)
        _, res = run("predict", "jump", "--height", 0.5)
        self.assertAlmostEqual(res["prediction"]["v0_m_s"], math.sqrt(2 * G * 0.5), places=3)
        self.assertAlmostEqual(res["prediction"]["airtime_s"], 2 * math.sqrt(G) / G, places=3)

    def test_long_jump_com_flight(self):
        _, res = run("predict", "longjump", "--run-speed", 9, "--angle", 20)
        vx, vy = 9 * math.cos(math.radians(20)), 9 * math.sin(math.radians(20))
        self.assertAlmostEqual(res["prediction"]["com_distance_m"], vx * 2 * vy / G, places=2)

    def test_fall_speed_stop_distance_and_tier(self):
        # 3 m: v = 7.672 m/s; under 6 BW the stop needs v^2/(2*g*5) = 0.6 m; tier "roll"
        _, res = run("predict", "fall", "--height", 3)
        p = res["prediction"]
        self.assertAlmostEqual(p["impact_speed_m_s"], math.sqrt(2 * G * 3), places=2)
        self.assertAlmostEqual(p["stop_distance_m"], 3 / 5, places=3)
        self.assertEqual(p["landing"], "roll")

    def test_move_tiers_default_and_custom(self):
        expect = {0.3: "step-up", 1.0: "vault", 1.4: "mantle", 2.0: "climb-up", 2.6: "jump-grab",
                  3.5: "blocked"}
        for h, move in expect.items():
            self.assertEqual(run("predict", "move", "--obstacle", h)[1]["prediction"]["move"], move)
        custom = write([{"max": 0.3, "move": "step-up"}, {"max": 99, "move": "blocked"}])
        self.assertEqual(run("predict", "move", "--obstacle", 1.0, "--tiers", custom)[1]
                         ["prediction"]["move"], "blocked")

    def test_capture_point(self):
        # v 0.6 m/s, CoM 1.0 m: x = 0.6*sqrt(1/9.81) = 0.1916 m
        _, res = run("predict", "capture", "--speed", 0.6)
        self.assertAlmostEqual(res["prediction"]["capture_point_m"], 0.6 / math.sqrt(G), places=3)

    def test_capsule_through_a_vent(self):
        _, res = run("predict", "fit", "--radius", 0.3, "--height", 1.8, "--gap-w", 0.7,
                     "--gap-h", 0.6, "--crouch", 1.2, "--crawl", 0.5)
        self.assertEqual(res["prediction"]["best"], "crawl")
        _, none = run("predict", "fit", "--radius", 0.3, "--height", 1.8, "--gap-w", 0.5,
                      "--gap-h", 2.0)
        self.assertIsNone(none["prediction"]["best"])

    def test_pandolf_load(self):
        # 80 kg, 20 kg load, 1.34 m/s level: 1.5*80 + 2*100*(0.25)^2 + 100*1.5*1.7956 = 401.84 W
        _, res = run("predict", "load", "--mass", 80, "--load", 20, "--speed", 1.34)
        self.assertAlmostEqual(res["prediction"]["metabolic_w"],
                               1.5 * 80 + 2 * 100 * 0.25 ** 2 + 100 * 1.5 * 1.34 ** 2, places=1)

    def test_motorcycle_lean_and_steering(self):
        # 50 km/h on r 30: tan(phi) = 13.89^2/(9.81*30) = 0.6553 -> 33.24 deg
        _, res = run("predict", "lean", "--v-kmh", 50, "--radius", 30)
        v = 50 / 3.6
        self.assertAlmostEqual(res["prediction"]["lean_deg"],
                               math.degrees(math.atan(v * v / (G * 30))), places=2)
        _, st = run("predict", "steer", "--road-deg", 10, "--ratio", 15)
        self.assertEqual(st["prediction"]["wheel_deg"], 150)


class JumpVariants(unittest.TestCase):
    def test_running_jump_keeps_speed(self):
        # 6 m/s run, keep 90 % -> vx 5.4, vy 2.0: flight 0.4077 s, distance 2.202 m, rise 0.204 m
        _, res = run("predict", "runjump", "--run-speed", 6, "--vy", 2.0)
        p = res["prediction"]
        self.assertEqual(p["jump_type"], "running")
        self.assertAlmostEqual(p["flight_s"], 4 / G, places=3)
        self.assertAlmostEqual(p["com_distance_m"], 5.4 * 4 / G, places=2)
        self.assertAlmostEqual(p["takeoff_angle_deg"], math.degrees(math.atan2(2, 5.4)), places=1)

    def test_jump_events(self):
        ok = write({"events": [
            {"approach_speed": 0.0, "type": "standing"},
            {"approach_speed": 1.4, "type": "walking", "takeoff_foot": "L", "stance_foot": "L"},
            {"approach_speed": 3.5, "type": "running", "takeoff_foot": "R", "stance_foot": "R",
             "speed_before": 3.5, "speed_after": 3.3}]})
        self.assertEqual(run("jumps", ok)[0], 0)
        bad = write({"events": [
            {"approach_speed": 3.5, "type": "standing"},  # the reported bug: standing pose at run
            {"approach_speed": 3.5, "type": "running", "takeoff_foot": "L", "stance_foot": "R",
             "speed_before": 3.5, "speed_after": 1.0}]})
        code, res = run("jumps", bad)
        self.assertEqual(code, 1)
        self.assertEqual({m["metric"] for m in res["metrics"] if m["verdict"] == "FAIL"},
                         {"jump_type_mismatches", "takeoff_foot_not_stance_foot",
                          "run_jumps_losing_speed"})


class Jump(unittest.TestCase):
    def test_apex_from_recording(self):
        v0 = math.sqrt(2 * G * 0.5)
        pos = [[0, max(0.0, v0 * t - G * t * t / 2), 0] for t in (i / 120 for i in range(90))]
        self.assertEqual(run("jump", recording({"hero": pos}, 120), "--pos", "hero", "--apex",
                             0.5)[0], 0)
        self.assertEqual(run("jump", recording({"hero": pos}, 120), "--pos", "hero", "--apex",
                             1.0)[0], 1)


class Events(unittest.TestCase):
    def test_moves_follow_the_tier_table(self):
        ok = write({"events": [{"height": 0.4, "move": "step-up"}, {"height": 1.0, "move": "vault"},
                               {"height": 1.5, "move": "mantle"}]})
        self.assertEqual(run("moves", ok)[0], 0)
        bad = write({"events": [{"height": 1.5, "move": "vault"}]})
        code, res = run("moves", bad)
        self.assertEqual(code, 1)
        self.assertEqual(res["metrics"][0]["examples"][0]["expected"], "mantle")

    def test_landings_follow_the_tier_table(self):
        ok = write({"events": [{"fall_height": 0.5, "landing": "none"},
                               {"fall_height": 3.0, "landing": "roll"}]})
        self.assertEqual(run("landings", ok)[0], 0)
        bad = write({"events": [{"fall_height": 9.0, "landing": "soft"}]})
        self.assertEqual(run("landings", bad)[0], 1)


class WaterAndPack(unittest.TestCase):
    def test_body_floats_with_air_and_armour_sinks(self):
        # 75 kg at 15 % fat: Siri density 1.0647; +2.4 L lungs, +0.1 L gut: floats in fresh water
        _, res = run("predict", "float", "--mass", 75, "--fat", 15, "--lungs", 2.4)
        p = res["prediction"]
        volume = 75 / (4.95 / (0.15 + 4.50)) + 2.5
        self.assertAlmostEqual(p["water"]["fresh"]["buoyancy_kg"], volume * 0.998 - 75, places=1)
        self.assertGreater(p["water"]["sea"]["buoyancy_kg"], p["water"]["fresh"]["buoyancy_kg"])
        _, armour = run("predict", "float", "--mass", 75, "--fat", 15, "--lungs", 2.4,
                        "--gear-mass", 20)
        self.assertFalse(armour["prediction"]["floats_with_gear_fresh"])  # plate sinks you

    def test_wading_speed_falls_with_depth(self):
        # Postacchini: 0.3 m -> 0.96 m/s, 0.9 m -> 0.63 m/s in still water
        _, shallow = run("predict", "wade", "--depth", 0.3)
        _, deep = run("predict", "wade", "--depth", 0.9)
        self.assertAlmostEqual(shallow["prediction"]["speed_m_s"], 0.96, delta=0.01)
        self.assertAlmostEqual(deep["prediction"]["speed_m_s"], 0.63, delta=0.01)

    def test_pack_bounce_and_lean(self):
        # k 5 N/mm: 20 kg -> 2.52 Hz; at 2.8 steps/s and zeta 0.1 the pack moves ~3.1x the body
        _, b = run("predict", "packbounce", "--load", 20, "--k", 5)
        self.assertAlmostEqual(b["prediction"]["natural_hz"], math.sqrt(5000 / 20) / (2 * math.pi),
                               places=2)
        self.assertAlmostEqual(b["prediction"]["bounce_ratio"], 3.1, delta=0.2)
        for load, deg in ((10, 6), (20, 10), (30, 13)):
            _, l = run("predict", "packlean", "--mass", 75, "--load", load, "--offset", 0.18)
            self.assertAlmostEqual(l["prediction"]["trunk_lean_deg"], deg, delta=1.0)


class Rom(unittest.TestCase):
    def test_the_live_armour_fails_and_a_relieved_one_passes(self):
        live = write({"stops": {"elbow_flex": 56, "shoulder_flex": 60, "shoulder_abd": 140,
                                "hip_flex": 120, "knee_flex": 140, "ankle_dorsi": 12}})
        code, res = run("rom", live, "--moves", "run,crouch,guard")
        self.assertEqual(code, 1)
        short = " ".join(res["metrics"][0]["shortfalls"])
        self.assertIn("elbow_flex 56", short)
        self.assertIn("shoulder_flex 60", short)
        fixed = write({"stops": {"elbow_flex": 135, "shoulder_flex": 135, "shoulder_abd": 140,
                                 "hip_flex": 120, "knee_flex": 145, "ankle_dorsi": 12}})
        self.assertEqual(run("rom", fixed, "--moves", "run,crouch,guard")[0], 0)

    def test_climbing_needs_more_shoulder_and_unmeasured_joints_fail(self):
        stops = write({"stops": {"elbow_flex": 135, "shoulder_flex": 135, "shoulder_abd": 140,
                                 "hip_flex": 120, "knee_flex": 145}})
        code, res = run("rom", stops, "--moves", "climb")
        self.assertEqual(code, 1)
        self.assertTrue(any("shoulder_flex" in s for s in res["metrics"][0]["shortfalls"]))
        code, res = run("rom", stops, "--moves", "crouch")
        self.assertIn("ankle_dorsi (not measured)", res["metrics"][0]["shortfalls"])

    def test_unknown_move_set_is_an_error(self):
        self.assertEqual(run("rom", write({"stops": {}}), "--moves", "fly")[0], 2)


class Contact(unittest.TestCase):
    def test_hands_stay_on_the_wheel_while_driving(self):
        grip = [[0.2 * math.cos(i / 30), 1.0, 0.2 * math.sin(i / 30)] for i in range(300)]
        hand = [[g[0] + 0.005, g[1], g[2]] for g in grip]
        drift = [[g[0] + 0.005 + (0.05 if i > 150 else 0), g[1], g[2]] for i, g in enumerate(grip)]
        holding = [True] * 300
        self.assertEqual(run("contact", recording({"h": hand, "g": grip, "hold": holding}),
                             "--a", "h", "--b", "g", "--when", "hold")[0], 0)
        self.assertEqual(run("contact", recording({"h": drift, "g": grip, "hold": holding}),
                             "--a", "h", "--b", "g", "--when", "hold")[0], 1)


class Balance(unittest.TestCase):
    def test_com_inside_feet(self):
        feet = [[-0.15, -0.1], [0.15, -0.1], [0.15, 0.15], [-0.15, 0.15]]
        com_ok = [[0.0, 1.0, 0.02]] * 100
        com_out = [[0.0, 1.0, 0.02 + 0.004 * i] for i in range(100)]
        self.assertEqual(run("balance", recording({"com": com_ok, "support": [feet] * 100}),
                             "--com", "com", "--support", "support")[0], 0)
        code, res = run("balance", recording({"com": com_out, "support": [feet] * 100}),
                        "--com", "com", "--support", "support")
        self.assertEqual(code, 1)
        stepping = [i > 30 for i in range(100)]
        self.assertEqual(run("balance", recording({"com": com_out, "support": [feet] * 100,
                                                   "stepping": stepping}),
                             "--com", "com", "--support", "support")[0], 0)


class Penetration(unittest.TestCase):
    def test_capsule_into_wall(self):
        self.assertEqual(run("penetration", recording({"d": [0.0, 0.005, 0.01]}), "--depth",
                             "d")[0], 0)
        self.assertEqual(run("penetration", recording({"d": [0.0, 0.05, 0.01]}), "--depth",
                             "d")[0], 1)


if __name__ == "__main__":
    unittest.main()
