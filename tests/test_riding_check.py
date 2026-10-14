"""Tests for plugins/kiln/skills/riding/scripts/riding_check.py (stdlib only)."""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "riding",
                      "scripts", "riding_check.py")
G = 9.81
HZ = 60


def write(data):
    fd, path = tempfile.mkstemp(prefix="kiln-riding-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *map(str, args)], capture_output=True,
                       text=True, timeout=60, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


def recording(samples, hz=HZ):
    n = max(len(v) for v in samples.values())
    return write({"physics_ticks_per_second": hz, "ticks": list(range(n)), "samples": samples})


def predict(*args):
    code, res = run("predict", *args)
    assert code == 0, res
    return res["prediction"]


class PredictGait(unittest.TestCase):
    def test_bands_and_boundaries(self):
        # L 1.25 m: g*L = 12.2625. Boundaries sqrt(Fr*g*L): 0.34 -> 2.042, 1.3 -> 3.993,
        # 2.8 -> 5.860, 5 -> 7.830 m/s
        p = predict("gait", "--v", 1.5)
        self.assertEqual(p["gait"], "walk")  # Fr = 2.25 / 12.2625 = 0.1835
        self.assertAlmostEqual(p["froude"], 0.1835, places=4)
        self.assertAlmostEqual(p["walk_trot_m_s"], 2.042, places=3)
        self.assertAlmostEqual(p["trot_canter_m_s"], 3.993, places=3)
        self.assertAlmostEqual(p["free_trot_max_m_s"], 5.860, places=3)
        self.assertAlmostEqual(p["canter_gallop_m_s"], 7.830, places=3)
        self.assertEqual(predict("gait", "--v", 3.5)["gait"], "trot")  # Fr 0.999
        p = predict("gait", "--v", 5)  # Fr = 25 / 12.2625 = 2.0387: canter, trot still possible
        self.assertEqual((p["gait"], p["also_possible"]), ("canter", "trot"))
        self.assertAlmostEqual(p["froude"], 2.0387, places=4)
        p = predict("gait", "--v", 12)  # Fr = 144 / 12.2625 = 11.743
        self.assertEqual((p["gait"], p["also_possible"]), ("gallop", None))

    def test_bigger_mount_walks_faster_at_the_same_froude(self):
        # 3 m leg: walk-trot at sqrt(0.34 * 9.81 * 3) = 3.163 m/s; 3.0 m/s walks, 3.5 m/s trots
        p = predict("gait", "--v", 3.5, "--leg", 3)
        self.assertAlmostEqual(p["walk_trot_m_s"], 3.163, places=3)
        self.assertEqual(p["gait"], "trot")  # 12.25 / 29.43 = 0.4162 > 0.34
        self.assertEqual(predict("gait", "--v", 3.0, "--leg", 3)["gait"], "walk")  # Fr 0.306


class PredictStride(unittest.TestCase):
    def test_walk_from_alexander(self):
        # Fr = 3.24 / 12.2625 = 0.26422; stride = 2.3 * 1.25 * 0.26422^0.3 = 1.9285 m;
        # f = 1.8 / 1.9285 = 0.9334 Hz; two saddle bounces per stride = 1.8667 Hz
        p = predict("stride", "--gait", "walk", "--v", 1.8)
        self.assertAlmostEqual(p["stride_m"], 1.9285, places=4)
        self.assertAlmostEqual(p["stride_hz"], 0.9334, places=4)
        self.assertAlmostEqual(p["saddle_bounce_hz"], 1.8667, places=4)
        self.assertEqual(p["beats_per_stride"], 4)

    def test_trot_regression_and_posting(self):
        # f = 0.623 + 0.25 * 3.5 = 1.498 Hz; stride 3.5 / 1.498 = 2.3364 m; period 0.6676 s;
        # sitting rider bounces 2.996 Hz, posting rider rises 1.498 Hz
        p = predict("stride", "--gait", "trot", "--v", 3.5)
        self.assertAlmostEqual(p["stride_hz"], 1.498, places=4)
        self.assertAlmostEqual(p["stride_m"], 2.3364, places=4)
        self.assertAlmostEqual(p["period_s"], 0.6676, places=4)
        self.assertAlmostEqual(p["saddle_bounce_hz"], 2.996, places=4)
        self.assertAlmostEqual(p["posting_rise_hz"], 1.498, places=4)
        self.assertIsNotNone(predict("stride", "--gait", "trot", "--v", 7)["note"])  # > 5.46

    def test_canter_and_gallop_from_heglund(self):
        # 500 kg: f_pref = 4.44 * 500^-0.156 = 1.6840 Hz at v_pref = 2.78 * 500^0.176 = 8.2997 m/s;
        # at 6 m/s: 1.6840 * (6 / 8.2997)^log2(1.1) = 1.6105 Hz, stride 3.7255 m (~ the 3.66 m
        # "standard canter stride")
        p = predict("stride", "--gait", "canter", "--v", 6)
        self.assertAlmostEqual(p["stride_hz"], 1.6105, places=4)
        self.assertAlmostEqual(p["stride_m"], 3.7255, places=4)
        self.assertEqual((p["beats_per_stride"], p["saddle_bounces_per_stride"]), (3, 1))
        self.assertIsNone(p["note"])
        # above the max sustained gallop 3.71 * 500^0.176 = 11.08 m/s: a note asks for --f
        self.assertIn("11.08", predict("stride", "--gait", "gallop", "--v", 17)["note"])
        p = predict("stride", "--gait", "gallop", "--v", 17, "--f", 2.34)
        self.assertAlmostEqual(p["stride_m"], 17 / 2.34, places=4)  # 7.265 m


class PredictScaleTurnStopLoad(unittest.TestCase):
    def test_scale_to_a_bigger_mount(self):
        # k = sqrt(3 / 1.25) = 1.54919: v 6 * k = 9.2952 m/s, f 1.61 / k = 1.0393 Hz,
        # stride 6 / 1.61 * k^2 = 8.9441 m, mass x (3 / 1.25)^3 = 13.824, Fr 2.9358 unchanged
        p = predict("scale", "--v", 6, "--f", 1.61, "--leg", 1.25, "--to-leg", 3)
        self.assertAlmostEqual(p["v_m_s"], 9.2952, places=4)
        self.assertAlmostEqual(p["stride_hz"], 1.0393, places=4)
        self.assertAlmostEqual(p["stride_m"], 8.9441, places=4)
        self.assertAlmostEqual(p["mass_ratio_isometric"], 13.824, places=3)
        self.assertAlmostEqual(p["froude"], 2.9358, places=4)

    def test_turn_lean_and_grip(self):
        # 6 m/s on r 10: v^2/(g r) = 0.36697 -> atan 20.152°; 3.6 m/s2; 0.6 rad/s = 34.377 °/s;
        # mu 0.6: r_min 36 / 5.886 = 6.116 m; v_max sqrt(58.86) = 7.672 m/s; max lean 30.96°
        p = predict("turn", "--v", 6, "--r", 10)
        self.assertAlmostEqual(p["lean_deg"], 20.152, places=3)
        self.assertAlmostEqual(p["heading_rate_deg_s"], 34.377, places=3)
        self.assertAlmostEqual(p["min_radius_m"], 6.116, places=3)
        self.assertAlmostEqual(p["max_speed_on_r_m_s"], 7.672, places=3)
        self.assertAlmostEqual(p["max_lean_deg"], 30.96, places=2)
        self.assertTrue(p["grip_ok"])
        self.assertFalse(predict("turn", "--v", 6, "--r", 5)["grip_ok"])  # 7.2 > 5.886 m/s2

    def test_stop(self):
        # grip-limited 15 m/s: a = 0.6 g = 5.886; d = 225 / 11.772 = 19.113 m; t = 2.548 s
        p = predict("stop", "--v", 15)
        self.assertAlmostEqual(p["distance_m"], 19.113, places=3)
        self.assertAlmostEqual(p["time_s"], 2.548, places=3)
        self.assertAlmostEqual(p["rider_load_g"], 0.6, places=4)
        # 6 m/s at 3 m/s2 after 0.5 s: 6 * 0.5 + 36 / 6 = 9.0 m, 0.5 + 2 = 2.5 s; 75 kg * 3 = 225 N
        p = predict("stop", "--v", 6, "--decel", 3, "--delay", 0.5, "--rider", 75)
        self.assertEqual((p["distance_m"], p["time_s"], p["rider_force_n"]), (9.0, 2.5, 225.0))
        self.assertFalse(p["exceeds_grip"])
        self.assertTrue(predict("stop", "--v", 6, "--decel", 8)["exceeds_grip"])  # 8 > 5.886

    def test_load_bands(self):
        # 500 kg horse, 10 kg saddle: rider 80 -> 16 % rider, 18 % total: caution;
        # 70 -> 14 / 16 %: ok; 95 -> 19 / 21 %: overloaded; heaviest riders 75 kg and 90 kg
        p = predict("load", "--horse", 500, "--rider", 80, "--tack", 10)
        self.assertEqual((p["rider_share"], p["total_share"], p["status"]), (0.16, 0.18, "caution"))
        self.assertEqual((p["max_rider_15pct_kg"], p["max_rider_20pct_total_kg"]), (75.0, 90.0))
        self.assertEqual(predict("load", "--horse", 500, "--rider", 70, "--tack", 10)["status"], "ok")
        self.assertEqual(predict("load", "--horse", 500, "--rider", 95, "--tack", 10)["status"],
                         "overloaded")
        # two 80 kg riders on one horse: 32 % rider share -> overloaded
        self.assertEqual(predict("load", "--horse", 500, "--rider", 160)["status"], "overloaded")

    def test_bad_input(self):
        self.assertEqual(run("predict", "turn", "--v", 6)[0], 2)
        self.assertEqual(run("predict", "load", "--rider", 80)[0], 2)


def saddle_wave(n, amp=0.045, hz=3.0, base=1.5, lag=0.0, phase=0.3):
    return [[i * 0.05, base + amp * math.sin(2 * math.pi * hz * (i / HZ - lag) + phase), 0]
            for i in range(n)]


class Seat(unittest.TestCase):
    def test_seated_floating_sliding(self):
        sad = saddle_wave(300)
        on = [[p[0], p[1] + 0.005, p[2]] for p in sad]
        self.assertEqual(run("seat", recording({"seat": on, "saddle": sad}), "--rider", "seat",
                             "--saddle", "saddle")[0], 0)
        # floats 5 cm above the saddle every other second
        fl = [[p[0], p[1] + (0.05 if (i // 60) % 2 else 0.0), p[2]] for i, p in enumerate(sad)]
        code, res = run("seat", recording({"seat": fl, "saddle": sad}), "--rider", "seat",
                        "--saddle", "saddle")
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["float_m"], 0.05, places=4)
        # slides 4 cm back along the horse
        sl = [[p[0] - 0.04, p[1], p[2]] for p in sad]
        code, res = run("seat", recording({"seat": sl, "saddle": sad}), "--rider", "seat",
                        "--saddle", "saddle")
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["slide_m"], 0.04, places=4)
        # only judged while sitting: the floating ticks are excluded
        sitting = [not (i // 60) % 2 for i in range(300)]
        self.assertEqual(run("seat", recording({"seat": fl, "saddle": sad, "sit": sitting}),
                             "--rider", "seat", "--saddle", "saddle", "--when", "sit")[0], 0)


class Follow(unittest.TestCase):
    def test_sitting_in_phase_vs_out_of_phase(self):
        sad = saddle_wave(300)  # trot: 3 Hz saddle bounce, 9 cm peak to peak
        rider = saddle_wave(300, base=1.9, lag=1 / HZ)  # one tick behind
        code, res = run("follow", recording({"pelvis": rider, "saddle": sad}), "--rider", "pelvis",
                        "--saddle", "saddle", "--mode", "sitting")
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["metrics"][1]["value"], 1 / HZ, places=4)  # lag 0.0167 s
        self.assertAlmostEqual(res["metrics"][2]["value"], 1.0, places=2)
        # half a bounce late (1/6 s): the rider hits the saddle as it rises
        late = saddle_wave(300, base=1.9, lag=1 / 6)
        self.assertEqual(run("follow", recording({"pelvis": late, "saddle": sad}), "--rider",
                             "pelvis", "--saddle", "saddle")[0], 1)
        # a rider who does not move at all is floating above a bouncing saddle
        still = [[p[0], 1.9, 0] for p in sad]
        self.assertEqual(run("follow", recording({"pelvis": still, "saddle": sad}), "--rider",
                             "pelvis", "--saddle", "saddle")[0], 1)

    def test_posting_rises_once_per_stride(self):
        sad = saddle_wave(300)  # 3 Hz bounce = 1.5 Hz stride
        post = saddle_wave(300, amp=0.06, hz=1.5, base=1.9)
        code, res = run("follow", recording({"pelvis": post, "saddle": sad}), "--rider", "pelvis",
                        "--saddle", "saddle", "--mode", "posting")
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["metrics"][0]["value"], 0.5, delta=0.02)
        bump = saddle_wave(300, amp=0.06, hz=3.0, base=1.9)  # rises on every beat
        self.assertEqual(run("follow", recording({"pelvis": bump, "saddle": sad}), "--rider",
                             "pelvis", "--saddle", "saddle", "--mode", "posting")[0], 1)

    def test_two_point_rider_stays_quiet(self):
        sad = saddle_wave(300, amp=0.075, hz=1.7)  # gallop: 15 cm, one bounce per stride
        quiet = saddle_wave(300, amp=0.075 * 0.3, hz=1.7, base=2.0, lag=0.3)
        code, res = run("follow", recording({"jockey": quiet, "saddle": sad}), "--rider",
                        "jockey", "--saddle", "saddle", "--mode", "two-point")
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["metrics"][0]["value"], 0.3, places=2)
        glued = saddle_wave(300, amp=0.075, hz=1.7, base=2.0)
        self.assertEqual(run("follow", recording({"jockey": glued, "saddle": sad}), "--rider",
                             "jockey", "--saddle", "saddle", "--mode", "two-point")[0], 1)

    def test_not_assessed(self):
        flat = [[0, 1.5, 0]] * 300
        code, res = run("follow", recording({"pelvis": flat, "saddle": flat}), "--rider",
                        "pelvis", "--saddle", "saddle")
        self.assertEqual((code, res["verdict"]), (0, "NOT ASSESSED"))


def hoof(n, offset, stride=1.8, slip_per_tick=0.0):
    """36-tick cycle: 18 ticks of stance at X, then 18 ticks of swing to X + stride."""
    pts, x = [], 0.0
    for i in range(n):
        k = (i + offset) % 36
        if k < 18:
            pts.append([x + slip_per_tick * k, 0.0, 0.0])
            if k == 17:
                x += slip_per_tick * 17
        else:
            s = k - 17  # 1..18
            pts.append([x + stride * s / 18, 0.15 * math.sin(math.pi * s / 18), 0.0])
            if s == 18:
                x += stride
    return pts


class Hooves(unittest.TestCase):
    def test_planted_vs_skating(self):
        feet = {"LF": hoof(360, 0), "RF": hoof(360, 18), "LH": hoof(360, 18), "RH": hoof(360, 0)}
        code, res = run("hooves", recording(feet), "--feet", "LF,RF,LH,RH")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["metrics"][0]["value"], 0.0)
        # 3 mm per tick in stance: 17 * 0.003 = 0.051 m of skating
        feet["RH"] = hoof(360, 0, slip_per_tick=0.003)
        code, res = run("hooves", recording(feet), "--feet", "LF,RF,LH,RH")
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["per_foot"]["RH"], 0.051, places=4)

    def test_contact_probes(self):
        feet = {"LF": hoof(360, 0, slip_per_tick=0.003),
                "cLF": [(i % 36) < 18 for i in range(360)]}
        code, res = run("hooves", recording(feet), "--feet", "LF", "--contact", "cLF")
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["value"], 0.051, places=4)
        self.assertEqual(run("hooves", recording(feet), "--feet", "LF", "--contact", "a,b")[0], 2)


def circle(r, v, n=600):
    w = v / r
    return [[r * math.cos(w * i / HZ), 0.0, r * math.sin(w * i / HZ)] for i in range(n)]


class Lean(unittest.TestCase):
    def test_steady_turn(self):
        # 6 m/s on r 10: predicted atan(36 / 98.1) = 20.152°
        pos = circle(10, 6)
        code, res = run("lean", recording({"horse": pos, "lean": [19.0] * 600}), "--pos", "horse",
                        "--lean", "lean")
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["metrics"][0]["predicted_deg"], 20.152, delta=0.01)
        self.assertAlmostEqual(res["metrics"][0]["radius_m"], 10.0, places=3)
        # an upright horse in the same turn
        self.assertEqual(run("lean", recording({"horse": pos, "lean": [0.0] * 600}), "--pos",
                             "horse", "--lean", "lean")[0], 1)
        # the lean given as the body's up vector
        t = math.radians(20.152)
        up = [[math.sin(t), math.cos(t), 0.0]] * 600
        self.assertEqual(run("lean", recording({"horse": pos, "up": up}), "--pos", "horse",
                             "--lean", "up")[0], 0)


class Grip(unittest.TestCase):
    def test_turns_within_grip(self):
        # r 10 at 6 m/s: 3.6 m/s2 = 0.367 g <= 0.6 * 1.1 = 0.66 g
        code, res = run("grip", recording({"horse": circle(10, 6)}), "--pos", "horse")
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["metrics"][0]["value"], 0.367, places=3)
        # r 4 at 6 m/s: 9 m/s2 = 0.917 g
        self.assertEqual(run("grip", recording({"horse": circle(4, 6)}), "--pos", "horse")[0], 1)

    def test_instant_turn_and_standstill(self):
        step = 6 / HZ  # 0.1 m per tick
        path = [[i * step, 0, 0] for i in range(60)] + [[59 * step, 0, i * step]
                                                        for i in range(1, 60)]
        self.assertEqual(run("grip", recording({"horse": path}), "--pos", "horse")[0], 1)
        spin = [[0, 0, 0]] * 120  # turning on the spot: below --min-speed
        code, res = run("grip", recording({"horse": spin}), "--pos", "horse")
        self.assertEqual((code, res["verdict"]), (0, "NOT ASSESSED"))

    def test_missing_probe(self):
        code, res = run("grip", recording({"other": circle(10, 6)}), "--pos", "horse")
        self.assertEqual((code, res["verdict"]), (0, "NOT ASSESSED"))


if __name__ == "__main__":
    unittest.main()
