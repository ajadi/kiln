"""Tests for plugins/kiln/skills/doors/scripts/doors_check.py (stdlib only)."""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "doors",
                      "scripts", "doors_check.py")
G = 9.81


def write(data):
    fd, path = tempfile.mkstemp(prefix="kiln-doors-", suffix=".json")
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


def leaf_edge(angle_deg, leaf=0.9, side=1):
    a = math.radians(angle_deg)
    return [leaf * math.cos(a), 0.0, side * leaf * math.sin(a)]


class PredictClear(unittest.TestCase):
    def test_thin_leaf_clear_and_min_angle(self):
        # W = leaf = 0.9, t = 0: clear at 90 deg = 0.9; capsule 2*0.3 + 0.05 = 0.65 fits
        # with 0.25 spare; smallest angle: 0.9*cos a = 0.25 -> a = acos(0.2778) = 73.87 deg
        _, res = run("predict", "clear", "--leaf", 0.9, "--thickness", 0, "--radius", 0.3)
        p = res["prediction"]
        self.assertAlmostEqual(p["clear_m"], 0.9)
        self.assertTrue(p["fits"])
        self.assertAlmostEqual(p["spare_m"], 0.25)
        self.assertAlmostEqual(p["min_angle_deg"], 73.87, places=2)
        # at 60 deg the leaf still covers 0.9*cos 60 = 0.45 m: clear 0.45 < 0.65
        _, half = run("predict", "clear", "--leaf", 0.9, "--thickness", 0, "--angle", 60)
        self.assertAlmostEqual(half["prediction"]["clear_m"], 0.45)
        self.assertFalse(half["prediction"]["fits"])

    def test_godot_default_capsule_does_not_fit_a_36_inch_door(self):
        # 0.914 m leaf, 45 mm thick, open 90: clear 0.914 - 0.045 = 0.869 m; Godot's default
        # capsule r 0.5 needs 1.05 m -> never fits (no angle); nav cell 0.25 rounds r 0.3 up to 0.5:
        # corridor 0.869 - 1.0 = -0.131 m; cell 0.1 keeps 0.3: corridor 0.869 - 0.6 = 0.269 m
        _, big = run("predict", "clear", "--leaf", 0.914, "--thickness", 0.045, "--radius", 0.5)
        self.assertAlmostEqual(big["prediction"]["clear_m"], 0.869)
        self.assertFalse(big["prediction"]["fits"])
        self.assertIsNone(big["prediction"]["min_angle_deg"])
        _, coarse = run("predict", "clear", "--leaf", 0.914, "--thickness", 0.045, "--radius",
                        0.3, "--cell", 0.25)
        self.assertAlmostEqual(coarse["prediction"]["nav_radius_m"], 0.5)
        self.assertAlmostEqual(coarse["prediction"]["nav_corridor_m"], -0.131)
        self.assertFalse(coarse["prediction"]["nav_passable"])
        _, fine = run("predict", "clear", "--leaf", 0.914, "--thickness", 0.045, "--radius",
                      0.3, "--cell", 0.1)
        self.assertAlmostEqual(fine["prediction"]["nav_corridor_m"], 0.269)
        self.assertTrue(fine["prediction"]["nav_passable"])

    def test_thick_leaf_min_angle_closed_form_and_shoulders(self):
        # K = 0.9 - 0.65 = 0.25, R = hypot(0.9, 0.04) = 0.900888, d = atan2(0.04, 0.9) = 2.5448:
        # a = 2.5448 + acos(0.25/0.900888) = 2.5448 + 73.8883 = 76.43 deg
        _, res = run("predict", "clear", "--leaf", 0.9, "--thickness", 0.04)
        a = res["prediction"]["min_angle_deg"]
        expected = math.degrees(math.atan2(0.04, 0.9) + math.acos(0.25 / math.hypot(0.9, 0.04)))
        self.assertAlmostEqual(a, expected, places=2)
        r = math.radians(a)  # clear at that angle equals the capsule need
        self.assertAlmostEqual(0.9 - 0.9 * math.cos(r) - 0.04 * math.sin(r), 0.65, places=3)
        # 1.75 m: shoulders 0.259*1.75 = 0.4533 m; a 0.5 m gap is 1.10x -> turns the shoulders
        _, narrow = run("predict", "clear", "--leaf", 0.9, "--thickness", 0, "--hardware", 0.4)
        self.assertAlmostEqual(narrow["prediction"]["shoulder_ratio"], 0.5 / 0.45325, places=3)
        self.assertTrue(narrow["prediction"]["turns_shoulders"])


class PredictSwing(unittest.TestCase):
    def test_speed_and_closer_rules(self):
        # 90 deg at 90 deg/s = 1 s; edge 0.9*pi/2 = 1.4137 m/s; 30 kg 0.9 m leaf I = 30*0.81/3 = 8.1,
        # KE = 0.5*8.1*(pi/2)^2 = 9.992 J; ADA closer 78/90 = 0.867 s < 5 s
        _, res = run("predict", "swing", "--speed", 90, "--mass", 30)
        p = res["prediction"]
        self.assertAlmostEqual(p["time_s"], 1.0)
        self.assertAlmostEqual(p["edge_speed_m_s"], 0.9 * math.pi / 2, places=4)
        self.assertAlmostEqual(p["kinetic_energy_j"], 0.5 * 8.1 * (math.pi / 2) ** 2, places=3)
        self.assertFalse(p["ada_closer_ok"])
        # closing at 15 deg/s: 90 -> 12 in 78/15 = 5.2 s >= 5 (ADA closer); 70/15 = 4.67 >= 1.5
        _, slow = run("predict", "swing", "--speed", 15)
        self.assertAlmostEqual(slow["prediction"]["time_90_to_12_s"], 5.2)
        self.assertTrue(slow["prediction"]["ada_closer_ok"])
        self.assertTrue(slow["prediction"]["ada_spring_hinge_ok"])
        self.assertTrue(slow["prediction"]["a156_low_energy_ok"])  # 80/15 = 5.33 s >= 3

    def test_torque_from_rest(self):
        # 18.7 N*m (5 lbf at 0.84 m) on I = 8.1: alpha 2.3086 rad/s2, 90 deg in
        # sqrt(2*(pi/2)/2.3086) = 1.1665 s; KE = tau*theta = 18.7*pi/2 = 29.37 J;
        # Godot hinge motor max_impulse = 18.7/60 = 0.3117
        _, res = run("predict", "swing", "--torque", 18.7, "--mass", 30, "--leaf", 0.9)
        p = res["prediction"]
        self.assertAlmostEqual(p["time_s"], math.sqrt(math.pi / (18.7 / 8.1)), places=3)
        self.assertAlmostEqual(p["kinetic_energy_j"], 18.7 * math.pi / 2, places=2)
        self.assertAlmostEqual(p["godot_motor_max_impulse"], 18.7 / 60, places=4)
        # 20 N at the handle, 0.9 - 0.065 = 0.835 m from the hinge: tau 16.7 N*m
        _, f = run("predict", "swing", "--force", 20, "--mass", 30)
        self.assertAlmostEqual(f["prediction"]["torque_n_m"], 16.7)


class PredictStandoff(unittest.TestCase):
    # 1.75 m: shoulder 0.818*1.75 = 1.4315 m, arm to mid-grip 0.386*1.75 = 0.6755 m, 80% = 0.5404;
    # handle 1.0 m: horizontal reach sqrt(0.5404^2 - 0.4315^2) = 0.3253 m; handle at
    # 0.9 - 0.065 = 0.835 m; half shoulders 0.2266 m -> body x 0.6084, y 0.06 + 0.3253 = 0.3853
    RH = math.sqrt((0.8 * 0.386 * 1.75) ** 2 - (0.818 * 1.75 - 1.0) ** 2)
    BX, BY = 0.835 - 0.259 * 1.75 / 2, 0.06 + RH

    def test_push_spot_and_hand(self):
        _, res = run("predict", "standoff", "--side", "push")
        p = res["prediction"]
        self.assertAlmostEqual(p["horizontal_reach_m"], self.RH, places=3)
        self.assertAlmostEqual(p["front_spot"]["x"], self.BX, places=3)
        self.assertAlmostEqual(p["front_spot"]["y"], self.BY, places=3)
        self.assertEqual(p["front_spot"]["hand"], "latch-side")
        self.assertFalse(p["needs_lean"])

    def test_pull_hits_body_and_clear_spot(self):
        # body at R0 = hypot(0.6084, 0.3853) = 0.7201 m, bearing 32.35 deg; it touches the leaf
        # face when R0*sin(beta - a) = 0.3: a = 32.35 - asin(0.3/0.7201) = 7.73 deg; step back to
        # 0.9 + 0.3 + 0.05 = 1.25 m from the hinge: 1.25 - 0.7201 = 0.5299 m.
        # clear spot beyond the latch edge x = 1.25, hinge-side shoulder at 1.0234, 0.1884 m past
        # the handle: y = 0.06 + sqrt(0.3253^2 - 0.1884^2) = 0.3252 m (>= r 0.3)
        _, res = run("predict", "standoff", "--side", "pull")
        p = res["prediction"]
        r0 = math.hypot(self.BX, self.BY)
        hit = math.degrees(math.atan2(self.BY, self.BX) - math.asin(0.3 / r0))
        self.assertAlmostEqual(p["front_spot"]["door_hits_body_deg"], hit, places=1)
        self.assertAlmostEqual(p["front_spot"]["step_back_m"], 1.25 - r0, places=3)
        dx = (1.25 - 0.259 * 1.75 / 2) - 0.835
        self.assertAlmostEqual(p["clear_spot"]["x"], 1.25)
        self.assertAlmostEqual(p["clear_spot"]["y"], 0.06 + math.sqrt(self.RH ** 2 - dx ** 2),
                               places=3)
        self.assertEqual(p["clear_spot"]["hand"], "hinge-side")

    def test_low_handle_needs_lean(self):
        # handle 0.3 m: 1.4315 - 0.3 = 1.13 m drop > 0.54 m reach -> no horizontal reach, lean
        _, res = run("predict", "standoff", "--side", "push", "--handle-height", 0.3)
        p = res["prediction"]
        self.assertEqual(p["horizontal_reach_m"], 0.0)
        self.assertTrue(p["needs_lean"])
        self.assertAlmostEqual(p["front_spot"]["y"], 0.3)  # body kept outside the door


class PredictStripsCars(unittest.TestCase):
    def test_strip_curtain(self):
        # 200 mm strips, 50% overlap: pitch 0.1 m, 1 m door: ceil(0.8/0.1) + 1 = 9 strips;
        # 0.47 m body pushes (0.47 + 0.2)/0.1 = 6.7; strip 0.2*0.002*2.2*1250 = 1.1 kg;
        # strip period 2*pi*sqrt(2*2.2/(3*9.81)) = 2.429 s; bead string 4*pi/2.4048*sqrt(2.2/9.81)
        # = 2.475 s
        _, res = run("predict", "strips", "--width", 1.0)
        p = res["prediction"]
        self.assertEqual(p["strips"], 9)
        self.assertAlmostEqual(p["strips_pushed"], 6.7)
        self.assertAlmostEqual(p["strip_mass_kg"], 1.1)
        self.assertAlmostEqual(p["strip_period_s"], 2 * math.pi * math.sqrt(4.4 / (3 * G)),
                               places=3)
        self.assertAlmostEqual(p["bead_string_period_s"],
                               4 * math.pi / 2.404825557695773 * math.sqrt(2.2 / G), places=3)
        # 80% overlap: pitch 0.04 -> 20 + 1 = 21 strips; body pushes 0.67/0.04 = 16.75
        _, dense = run("predict", "strips", "--width", 1.0, "--overlap", 0.8)
        self.assertEqual(dense["prediction"]["strips"], 21)
        self.assertAlmostEqual(dense["prediction"]["strips_pushed"], 16.75)

    def test_car_ingress_okane_mockup(self):
        # 1.80 m under a 1.33 m door top: duck 1.80 + 0.03 - 1.33 = 0.50 m; hips at the 0.595 m
        # H-point: lean acos((1.33 - 0.03 - 0.595)/(0.47*1.80)) = acos(0.8333) = 33.56 deg;
        # H-point - hip 0.595 - 0.954 = -0.359 -> sit; foot lift 0.40 + 0.05 = 0.45 m,
        # hip flexion acos(1 - 0.45/0.441) = 91.17 deg; control-group means 2.97 s in / 2.95 s out
        _, res = run("predict", "car", "--roof", 1.33, "--hpoint", 0.595, "--sill", 0.40)
        p = res["prediction"]
        self.assertAlmostEqual(p["head_drop_standing_m"], 0.5)
        self.assertAlmostEqual(p["trunk_lean_seated_deg"],
                               math.degrees(math.acos(0.705 / 0.846)), places=2)
        self.assertEqual(p["entry"], "sit")
        self.assertAlmostEqual(p["step_over_hip_flex_deg"],
                               math.degrees(math.acos(1 - 0.45 / 0.441)), places=2)
        self.assertFalse(p["needs_step"])
        self.assertEqual((p["ingress_s"], p["egress_s"]), (2.97, 2.95))
        # 1.50 m minivan roof: 1.5 - 0.03 - 0.595 = 0.875 >= 0.846 -> sits upright
        _, van = run("predict", "car", "--roof", 1.50, "--hpoint", 0.595, "--sill", 0.40)
        self.assertEqual(van["prediction"]["trunk_lean_seated_deg"], 0.0)

    def test_truck_and_older_driver(self):
        # cab floor 0.9 m > 0.609 m (49 CFR 399.207) -> steps; H-point 1.3 > hip 0.954 + 0.05
        _, res = run("predict", "car", "--roof", 2.4, "--hpoint", 1.3, "--sill", 0.9,
                     "--group", "older")
        p = res["prediction"]
        self.assertTrue(p["needs_step"])
        self.assertEqual(p["entry"], "climb")
        self.assertEqual((p["ingress_s"], p["egress_s"]), (4.33, 5.26))

    def test_car_door_arc(self):
        # 1.1 m door at 70 deg: gap and side space 1.1*sin 70 = 1.0337 m; 0.7 s -> 100 deg/s,
        # edge 1.1*(70 deg in rad)/0.7 = 1.9199 m/s; 0.6 m body needs asin(0.6/1.1) = 33.06 deg
        _, res = run("predict", "cardoor", "--length", 1.1, "--angle", 70, "--time", 0.7,
                     "--body", 0.6)
        p = res["prediction"]
        self.assertAlmostEqual(p["gap_m"], 1.1 * math.sin(math.radians(70)), places=4)
        self.assertAlmostEqual(p["angular_speed_deg_s"], 100.0)
        self.assertAlmostEqual(p["edge_speed_m_s"], 1.1 * math.radians(70) / 0.7, places=4)
        self.assertAlmostEqual(p["min_angle_for_body_deg"],
                               math.degrees(math.asin(0.6 / 1.1)), places=2)

    def test_bad_input_exits_2(self):
        code, res = run("predict", "car", "--roof", 1.33)
        self.assertEqual(code, 2)
        self.assertEqual(res["verdict"], "ERROR")


class MeasureHands(unittest.TestCase):
    def test_grab_distance(self):
        handle = [[0.835, 1.0, 0.0]] * 120
        when = [30 <= i < 90 for i in range(120)]
        close = [[0.835, 1.0, 0.01]] * 120          # 1 cm off -> PASS (<= 2 cm)
        far = [[0.835, 1.0, 0.05]] * 120            # 5 cm off -> FAIL
        code, res = run("grab", recording({"hand": close, "handle": handle, "grab": when}),
                        "--hand", "hand", "--handle", "handle", "--when", "grab")
        self.assertEqual(code, 0)
        self.assertAlmostEqual(res["metrics"][0]["value"], 0.01)
        self.assertEqual(res["metrics"][0]["grabs"], 1)
        self.assertEqual(run("grab", recording({"hand": far, "handle": handle, "grab": when}),
                             "--hand", "hand", "--handle", "handle", "--when", "grab")[0], 1)

    def test_grab_missing_probe_not_assessed(self):
        code, res = run("grab", recording({"hand": [[0, 0, 0]] * 5}), "--hand", "hand",
                        "--handle", "handle")
        self.assertEqual(code, 0)
        self.assertEqual(res["verdict"], "NOT ASSESSED")

    def test_door_follows_hand(self):
        # door opens 0 -> 90 deg over 60 ticks; the hand on the handle (0.835 m) at the same angle
        angles = [1.5 * i for i in range(61)]
        edge = [leaf_edge(a) for a in angles]
        hand = [leaf_edge(a, 0.835) for a in angles]
        code, res = run("follow", recording({"hand": hand, "edge": edge}), "--hand", "hand",
                        "--edge", "edge", "--hinge", "0,0")
        self.assertEqual(code, 0)
        self.assertAlmostEqual(res["metrics"][0]["value"], 0.0)
        self.assertAlmostEqual(res["metrics"][0]["door_travel_deg"], 90.0)
        # the hand runs ahead of the door by 20% (18 deg at the end) -> FAIL at tol 5
        ahead = [leaf_edge(a * 1.2, 0.835) for a in angles]
        code, res = run("follow", recording({"hand": ahead, "edge": edge}), "--hand", "hand",
                        "--edge", "edge", "--hinge", "0,0")
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["value"], 18.0, places=2)


class MeasureBodies(unittest.TestCase):
    def test_penetration_geometry_and_depth_probe(self):
        # body (0.45, 0.5), r 0.3, leaf 0.04 thick: closed leaf along x is 0.5 m away -> 0;
        # at 45 deg the leaf passes |0.45 - 0.5|*0.7071 = 0.0354 m from the centre:
        # penetration 0.3 + 0.02 - 0.0354 = 0.2846 m
        body = [[0.45, 1.0, 0.5]] * 2
        closed = run("penetration", recording({"b": body, "e": [leaf_edge(0)] * 2}),
                     "--body", "b", "--edge", "e", "--hinge", "0,0", "--radius", 0.3)
        self.assertEqual(closed[0], 0)
        self.assertEqual(closed[1]["metrics"][0]["value"], 0.0)
        code, res = run("penetration", recording({"b": body, "e": [leaf_edge(45)] * 2}),
                        "--body", "b", "--edge", "e", "--hinge", "0,0", "--radius", 0.3)
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["value"], 0.32 - 0.05 * math.sqrt(0.5), places=4)
        code, res = run("penetration", recording({"d": [0.0, 0.01, 0.03]}), "--depth", "d")
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["value"], 0.03)

    def test_door_open_before_body_passes(self):
        # body walks along z at x = 0.6 through a 0.9 m doorway (hinge 0,0, closed edge 0.9,0);
        # required angle for r 0.3 + 0.05 margin, 0.04 leaf: 2.5448 + 73.8883 = 76.43 deg
        n = 121
        body = [[0.6, 1.0, -1.0 + 2.0 * i / (n - 1)] for i in range(n)]   # crosses z = 0 at i = 60
        opened = [leaf_edge(min(90.0, 3.0 * i), side=-1) for i in range(n)]   # 90 deg by i = 30
        late = [leaf_edge(0.75 * i, side=-1) for i in range(n)]               # 45 deg at i = 60
        args = ["--body", "b", "--edge", "e", "--hinge", "0,0", "--closed", "0.9,0",
                "--radius", 0.3]
        code, res = run("passage", recording({"b": body, "e": opened}), *args)
        self.assertEqual(code, 0)
        self.assertAlmostEqual(res["metrics"][0]["value"], 90.0)
        self.assertAlmostEqual(res["metrics"][0]["required_deg"], 76.43, places=2)
        code, res = run("passage", recording({"b": body, "e": late}), *args)
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["value"], 45.0)
        self.assertEqual(run("passage", recording({"b": body, "e": late}), *args,
                             "--min-angle", 40)[0], 0)

    def test_ai_passes_without_stopping(self):
        # 1 m/s along x from -5 to +5 through the door at the origin (zone 2 m)
        walk = [[-5.0 + i / 60, 1.0, 0.0] for i in range(601)]
        code, res = run("aipass", recording({"npc": walk}), "--agents", "npc", "--door", "0,0")
        self.assertEqual(code, 0)
        self.assertTrue(res["metrics"][0]["passed"])
        self.assertAlmostEqual(res["metrics"][0]["transit_s"], 4.0, places=2)
        # waits 4 s (240 ticks) at x = -1 inside the zone -> longest stop 4.0 s > 3 s
        stuck = walk[:241] + [walk[240]] * 240 + walk[241:]
        code, res = run("aipass", recording({"npc": stuck}), "--agents", "npc", "--door", "0,0")
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["value"], 4.0, places=2)
        # turns back on its own side -> did not pass
        back = walk[:301] + walk[300::-1]
        code, res = run("aipass", recording({"npc": back}), "--agents", "npc", "--door", "0,0")
        self.assertEqual(code, 1)
        self.assertFalse(res["metrics"][0]["passed"])
        # never reaches the door
        code, res = run("aipass", recording({"npc": [[-10.0, 1.0, 0.0]] * 60}), "--agents", "npc",
                        "--door", "0,0")
        self.assertEqual(code, 1)

    def test_closing_time(self):
        # closer at 15 deg/s: 90 -> 12 deg in 78/15 = 5.2 s >= 5 s (ADA); at 20 deg/s 3.9 s
        slow = [max(0.0, 90 - 15 * i / 60) for i in range(480)]
        fast = [max(0.0, 90 - 20 * i / 60) for i in range(480)]
        code, res = run("swing", recording({"a": slow}), "--angle", "a", "--from", 90, "--to", 12,
                        "--min-s", 5)
        self.assertEqual(code, 0)
        self.assertAlmostEqual(res["metrics"][0]["value"], 5.2, places=3)
        code, res = run("swing", recording({"a": fast}), "--angle", "a", "--from", 90, "--to", 12,
                        "--min-s", 5)
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["value"], 3.9, places=3)
        # opening 0 -> 80 deg at 40 deg/s = 2.0 s: A156.10 full power (>= 1.5 s) passes
        opening = [min(90.0, 40 * i / 60) for i in range(240)]
        self.assertEqual(run("swing", recording({"a": opening}), "--angle", "a", "--from", 0,
                             "--to", 80, "--min-s", 1.5)[0], 0)


if __name__ == "__main__":
    unittest.main()
