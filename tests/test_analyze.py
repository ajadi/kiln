"""Tests for plugins/kiln/skills/acceptance/scripts/analyze.py.

Run: python -m unittest discover -s tests -v   (from the repo root; analyze.py needs numpy)
Synthetic recordings with known answers, in the Godot JSON format and the Unity/Unreal JSON Lines
format (Unreal: centimetres, Z-up), so both loaders must agree.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "acceptance",
                      "scripts", "analyze.py")
HZ = 60


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=60)
    return p.returncode, json.loads(p.stdout)


def tmpdir():
    return tempfile.mkdtemp(prefix="kiln-analyze-")


def write_json(path, samples, frame_ms=None, ticks=None, **extra):
    n = len(next(iter(samples.values())))
    data = {"format": "kiln-probe/2", "physics_ticks_per_second": HZ,
            "ticks": ticks or list(range(1000, 1000 + n)), "samples": samples,
            "frame_ms": frame_ms or [], **extra}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


def write_jsonl(path, header, ticks=(), frames=(), truncate=False):
    lines = [json.dumps({"type": "header", "format": "kiln-probe/1", **header})]
    lines += [json.dumps({"type": "tick", **t}) for t in ticks]
    lines += [json.dumps({"type": "frame", **f}) for f in frames]
    lines.append(json.dumps({"type": "end", "ticks": len(ticks)}))
    text = "\n".join(lines) + "\n"
    if truncate:
        text += '{"type": "tick", "tick": 9'  # probe still writing
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def foot_track(slip_ticks):
    """Foot planted at y=0 for ticks 0..59 (59 planted pairs), moving 1 cm per tick during
    slip_ticks, then lifted 0.2 m for 61 ticks. Returns [(x, height)]."""
    x, out = 0.0, []
    for i in range(121):
        if i in slip_ticks:
            x += 0.01  # 0.6 m/s at 60 Hz > 0.15 m/s slip speed
        out.append((x, 0.0 if i < 60 else 0.2))
    return out


class Skating(unittest.TestCase):
    def test_godot_json_fail_and_pass(self):
        d = tmpdir()
        bad = write_json(os.path.join(d, "bad.json"),
                         {"foot": [[x, h, 0.0] for x, h in foot_track({11, 12, 13})]})
        code, res = run("skating", bad, "--foot", "foot")
        self.assertEqual(code, 0)
        self.assertEqual(res["verdict"], "FAIL")
        self.assertEqual(res["value"], round(3 / 59, 4))  # 0.0508
        self.assertEqual(res["planted_ticks"], 59)
        good = write_json(os.path.join(d, "good.json"),
                          {"foot": [[x, h, 0.0] for x, h in foot_track({11, 12})]})
        _, res = run("skating", good, "--foot", "foot")
        self.assertEqual((res["verdict"], res["value"]), ("PASS", round(2 / 59, 4)))

    def test_unreal_jsonl_centimetres_z_up(self):
        path = write_jsonl(os.path.join(tmpdir(), "foot.jsonl"),
                           {"engine": "unreal", "units_per_meter": 100, "up": "z"},
                           ticks=[{"tick": i, "t": i / HZ, "foot": [x * 100, 0.0, h * 100]}
                                  for i, (x, h) in enumerate(foot_track({11, 12, 13}))])
        code, res = run("skating", path, "--foot", "foot")
        self.assertEqual(code, 0)
        self.assertEqual((res["verdict"], res["value"]), ("FAIL", round(3 / 59, 4)))
        self.assertEqual(res["source"]["engine"], "unreal")

    def test_ground_probe_and_no_contact(self):
        d = tmpdir()
        n = 30
        path = write_json(os.path.join(d, "g.json"),
                          {"foot": [[0.0, 1.0, 0.0]] * n, "ground": [1.0] * n})
        _, res = run("skating", path, "--foot", "foot", "--ground", "ground")
        self.assertEqual((res["verdict"], res["value"]), ("PASS", 0.0))
        _, res = run("skating", path, "--foot", "foot")  # 1 m above y=0: never in contact
        self.assertEqual(res["verdict"], "FAIL")
        self.assertIn("no contact", res["note"])


class Frames(unittest.TestCase):
    def test_hitches_in_json(self):
        ms = [10.0] * 98 + [40.0, 60.0]
        path = write_json(os.path.join(tmpdir(), "f.json"), {"x": [0] * 3}, frame_ms=ms,
                          gpu_ms=[5.0] * 100)
        _, res = run("frames", path)
        self.assertEqual(res["verdict"], "FAIL")
        self.assertEqual(res["value"], 10.8)
        self.assertEqual((res["hitches"], res["frames"], res["worst_ms"]), (2, 100, 60.0))
        self.assertEqual(res["gpu_ms"]["mean"], 5.0)

    def test_a_small_spike_is_reported_not_failed(self):
        # bug hunt 2026-10-20: one 5 ms frame among 2 ms ones failed a 16.67 ms budget
        path = write_json(os.path.join(tmpdir(), "s.json"), {"x": [0] * 3},
                          frame_ms=[2.0] * 199 + [5.0])
        _, res = run("frames", path)
        self.assertEqual((res["verdict"], res["hitches"], res["over_max_frame"]), ("PASS", 1, 0))
        path = write_json(os.path.join(tmpdir(), "b.json"), {"x": [0] * 3},
                          frame_ms=[2.0] * 199 + [120.0])
        _, res = run("frames", path)
        self.assertEqual((res["verdict"], res["over_max_frame"]), ("FAIL", 1))

    def test_jsonl_frames_skip_loading(self):
        frames = [{"frame": i, "dt_ms": 250.0 if i == 0 else 10.0, "gpu_ms": 4.0,
                   "cpu_ms": 6.0} for i in range(120)]
        path = write_jsonl(os.path.join(tmpdir(), "f.jsonl"), {"engine": "unity",
                                                                "physics_hz": 50},
                           frames=frames)
        _, res = run("frames", path)
        self.assertEqual((res["verdict"], res["hitches"]), ("FAIL", 1))
        _, res = run("frames", path, "--skip", "1")
        self.assertEqual((res["verdict"], res["value"], res["low1_fps"]), ("PASS", 10.0, 100.0))
        self.assertEqual((res["gpu_ms"]["mean"], res["cpu_ms"]["p95"]), (4.0, 6.0))

    def test_format1_dump_still_reads(self):
        path = os.path.join(tmpdir(), "old.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"physics_ticks_per_second": 60, "ticks": [1, 2, 3],
                       "frame_ms": [12.0, 12.0, 12.0], "samples": {"p": [1, 2, 3]}}, fh)
        _, res = run("frames", path)
        self.assertEqual((res["verdict"], res["value"]), ("PASS", 12.0))


class Settle(unittest.TestCase):
    def test_json_settles_at_half_second(self):
        pos = [[min(i, 30) / HZ, 0.0, 0.0] for i in range(120)]  # 1 m/s until tick 30
        path = write_json(os.path.join(tmpdir(), "s.json"), {"body": pos})
        _, res = run("settle", path, "--pos", "body")
        self.assertEqual((res["verdict"], res["value"], res["settled"]), ("PASS", 0.5, True))

    def test_jsonl_variable_dt_and_never_settles(self):
        t, ticks = 0.0, []
        for i in range(40):
            ticks.append({"tick": i, "t": round(t, 6), "body": [0.0, min(i, 20) * 0.1, 0.0]})
            t += 0.01 if i % 2 else 0.03
        path = write_jsonl(os.path.join(tmpdir(), "s.jsonl"), {"engine": "unity"}, ticks=ticks)
        _, res = run("settle", path, "--pos", "body")
        self.assertEqual(res["verdict"], "PASS")
        self.assertAlmostEqual(res["value"], ticks[20]["t"], places=3)  # 0.4 s
        moving = [{"tick": i, "t": i * 0.02, "body": [i * 0.1, 0.0, 0.0]} for i in range(10)]
        path = write_jsonl(os.path.join(tmpdir(), "m.jsonl"), {}, ticks=moving)
        _, res = run("settle", path, "--pos", "body")
        self.assertEqual((res["verdict"], res["settled"]), ("FAIL", False))


class Reaction(unittest.TestCase):
    def test_json_bool_input_vector_response(self):
        n = 30
        inp = [i >= 10 for i in range(n)]
        resp = [[0.0, 0.0, 0.0] if i < 12 else [0.0, 0.0, 1.0] for i in range(n)]
        path = write_json(os.path.join(tmpdir(), "r.json"), {"fire": inp, "muzzle": resp})
        _, res = run("reaction", path, "--input", "fire", "--response", "muzzle")
        self.assertEqual((res["verdict"], res["value"], res["ms"]), ("PASS", 2, 33.3))

    def test_jsonl_eps_and_truncated_line(self):
        ticks = [{"tick": i, "t": i * 0.02, "trigger": 1 if i >= 5 else 0,
                  "recoil": 0.0005 * i if i < 8 else 1.0} for i in range(20)]
        path = write_jsonl(os.path.join(tmpdir(), "r.jsonl"), {"physics_hz": 50}, ticks=ticks,
                           truncate=True)
        _, res = run("reaction", path, "--input", "trigger", "--response", "recoil",
                     "--eps", "0.01")
        self.assertEqual((res["verdict"], res["value"], res["ms"]), ("FAIL", 3, 60.0))


class Inputs(unittest.TestCase):
    def test_missing_probe_is_not_assessed(self):
        path = write_json(os.path.join(tmpdir(), "x.json"), {"a": [1, 2]})
        code, res = run("settle", path, "--pos", "nope")
        self.assertEqual((code, res["verdict"]), (0, "NOT ASSESSED"))
        self.assertIn("a", res["note"])

    def test_glob_combines_verdicts(self):
        d = tmpdir()
        write_json(os.path.join(d, "a.json"), {"x": [0]}, frame_ms=[10.0] * 10)
        write_json(os.path.join(d, "b.json"), {"x": [0]}, frame_ms=[30.0] * 10)
        code, res = run("frames", os.path.join(d, "*.json"))
        self.assertEqual((code, res["verdict"]), (0, "FAIL"))
        self.assertEqual([r["verdict"] for r in res["results"]], ["PASS", "FAIL"])
        code, res = run("frames", os.path.join(d, "*.none"))
        self.assertEqual((code, res["verdict"]), (1, "NOT ASSESSED"))


def zigzag(slip_m):
    """Root runs 4 m/s and turns 60 deg every 0.5 s (ticks 30, 60, ...). The left foot's stances
    (12 ticks) span each turn, the right foot's never do; the left foot slides slip_m during each
    stance, the right foot stays planted."""
    import math
    root, heading, x, z = [], 0.0, 0.0, 0.0
    for i in range(HZ * 4):
        if i and i % 30 == 0:
            heading += math.radians(60) * (1 if (i // 30) % 2 else -1)
        x += 4 * math.cos(heading) / HZ
        z += 4 * math.sin(heading) / HZ
        root.append([x, 1.0, z])

    def foot(starts, slide):
        track, anchor, k0 = [], None, None
        for i in range(HZ * 4):
            k = next((s for s in starts if s <= i < s + 12), None)
            if k is None:
                anchor = None
                track.append([root[i][0], 0.25, root[i][2]])
                continue
            if anchor is None:
                anchor, k0 = list(root[i]), k
            frac = (i - k0) / 11
            track.append([anchor[0] + slide * frac, 0.0, anchor[2]])
        return track

    left = foot([30 * n - 6 for n in range(1, 8)], slip_m)
    right = foot([30 * n + 9 for n in range(0, 8)], 0.0)
    return root, left, right

class Stance(unittest.TestCase):
    def test_planted_feet_pass_and_turn_skating_fails(self):
        d = tmpdir()
        root, fl, fr = zigzag(0.0)
        ok = write_json(os.path.join(d, "ok.json"), {"hero": root, "fl": fl, "fr": fr})
        code, res = run("stance", ok, "--feet", "fl,fr", "--root", "hero")
        self.assertEqual(res["verdict"], "PASS", res)
        self.assertGreater(res["stances"], 10)
        root, fl, fr = zigzag(0.06)
        bad = write_json(os.path.join(d, "bad.json"), {"hero": root, "fl": fl, "fr": fr})
        code, res = run("stance", bad, "--feet", "fl,fr", "--root", "hero")
        self.assertEqual(res["verdict"], "FAIL", res)
        self.assertGreaterEqual(res["turning_slip_max_m"], 0.05)

    def test_no_contact_is_not_assessed(self):
        d = tmpdir()
        air = [[0.0, 1.0, 0.0]] * 120
        path = write_json(os.path.join(d, "air.json"), {"fl": air})
        self.assertEqual(run("stance", path, "--feet", "fl")[1]["verdict"], "NOT ASSESSED")

class SolePoints(unittest.TestCase):
    # g2 rows 128/148: a low swing toe and the heel strike counted as planted; the forefoot
    # rolling about a raised toe joint read as 15-24 mm of "skating".
    def track(self):
        heel, toe, flag = [], [], []
        for i in range(240):
            phase = i % 120
            if phase < 60:                                   # stance: toe planted, heel rolls
                x0 = (i // 120) * 1.0
                toe.append([x0 + 0.2, 0.01, 0.0])
                heel.append([x0 + 0.3 * phase / 60, 0.02, 0.0])
                flag.append(1)
            else:                                            # swing, kept low
                x = (i // 120) * 1.0 + 1.5 * (phase - 60) / 60 * 0.6
                toe.append([x + 0.2, 0.03, 0.0])
                heel.append([x, 0.03, 0.0])
                flag.append(0)
        return heel, toe, flag

    def test_contact_flag_and_planted_point(self):
        d = tmpdir()
        heel, toe, flag = self.track()
        path = write_json(os.path.join(d, "walk.json"), {"heel": heel, "toe": toe, "flag": flag})
        code, naive = run("skating", path, "--foot", "heel")
        self.assertEqual(naive["verdict"], "FAIL", naive)
        code, res = run("skating", path, "--foot", "heel,toe", "--contact-flag", "flag")
        self.assertEqual(res["verdict"], "PASS", res)
        self.assertLess(res["value"], 0.02)
        code, res = run("stance", path, "--feet", "heel+toe", "--contact-flag", "flag")
        self.assertEqual(res["verdict"], "PASS", res)
        self.assertLess(res["value"], 0.005)


def idle_track(seconds=60, sway_mm=4.0, breath_hz=0.25, chest_mm=4.0, freeze=False):
    """Pelvis sways at 0.2 Hz (AP) and 0.3 Hz (ML), chest-pelvis distance breathes, an arm
    angle drifts unless frozen."""
    import math
    n = HZ * seconds
    pelvis, chest, arm = [], [], []
    for i in range(n):
        t = i / HZ
        ap = sway_mm / 1000 * math.sqrt(2) * math.sin(2 * math.pi * 0.2 * t)
        ml = sway_mm / 2000 * math.sqrt(2) * math.sin(2 * math.pi * 0.3 * t + 1)
        pelvis.append([ml, 1.0, ap])
        d = 0.45 + chest_mm / 2000 * math.sin(2 * math.pi * breath_hz * t)
        chest.append([ml, 1.0 + d, ap])
        arm.append(0.0 if freeze else 3.0 * math.sin(2 * math.pi * 0.1 * t))
    return pelvis, chest, arm


class Idle(unittest.TestCase):
    def test_alive_calm_idle_passes(self):
        d = tmpdir()
        pelvis, chest, arm = idle_track()
        path = write_json(os.path.join(d, "idle.json"), {"pelvis": pelvis, "chest": chest,
                                                         "arm": arm})
        code, res = run("idle", path, "--pos", "pelvis", "--chest", "chest", "--bones", "arm")
        self.assertEqual(res["verdict"], "PASS", res)
        self.assertAlmostEqual(res["breaths_per_min"], 15, delta=1)

    def test_mannequin_and_hyperventilating_idle_fail(self):
        d = tmpdir()
        pelvis, chest, arm = idle_track(sway_mm=0.1, breath_hz=0.8, freeze=True)
        path = write_json(os.path.join(d, "dead.json"), {"pelvis": pelvis, "chest": chest,
                                                         "arm": arm})
        code, res = run("idle", path, "--pos", "pelvis", "--chest", "chest", "--bones", "arm")
        self.assertEqual(res["verdict"], "FAIL")
        self.assertEqual(len(res["frozen"]), 1)
        self.assertGreaterEqual(len(res["problems"]), 3)

    def test_invisible_breathing_is_named_not_a_wrong_rate(self):
        # g2 row 150: a 0.1 mm chest amplitude made the 8 s loop the dominant peak, and the
        # check reported "breathing outside 12-20/min" for clips breathing at 15/min.
        d = tmpdir()
        pelvis, chest, arm = idle_track(chest_mm=0.1)
        path = write_json(os.path.join(d, "flat.json"), {"pelvis": pelvis, "chest": chest,
                                                         "arm": arm})
        code, res = run("idle", path, "--pos", "pelvis", "--chest", "chest", "--bones", "arm")
        self.assertEqual(res["verdict"], "FAIL")
        self.assertTrue(any("breathing invisible" in p for p in res["problems"]), res)
        self.assertFalse(any("12-20" in p for p in res["problems"]), res)

    def test_short_recording_not_assessed(self):
        d = tmpdir()
        pelvis, _, _ = idle_track(seconds=5)
        path = write_json(os.path.join(d, "short.json"), {"pelvis": pelvis})
        self.assertEqual(run("idle", path, "--pos", "pelvis")[1]["verdict"], "NOT ASSESSED")

def walk(lat=0.02, obl=4.0, rot=4.0, foot_l=-0.05, foot_r=0.05, seconds=12):
    """Straight walk along +x at 1.4 m/s, stride 0.9 Hz: pelvis sways sideways, the hip line
    tilts (obliquity) and turns (rotation); feet plant alternately at the given lateral offsets
    (Godot axes: walking +X, the left side is -Z)."""
    import math
    hz, fs = HZ, 0.9
    pelvis, hl, hr, fl, fr = [], [], [], [], []
    for i in range(hz * seconds):
        t = i / hz
        ph = 2 * math.pi * fs * t
        x, z = 1.4 * t, lat * math.sin(ph)
        pelvis.append([x, 1.0, z])
        o, r = math.radians(obl) * math.sin(ph), math.radians(rot) * math.cos(ph)
        v = [0.09 * math.sin(r) * math.cos(o), 0.09 * math.sin(o), 0.09 * math.cos(r) * math.cos(o)]
        hl.append([x - v[0], 1.0 - v[1], z - v[2]])
        hr.append([x + v[0], 1.0 + v[1], z + v[2]])
        cyc = (fs * t) % 1.0
        step_x = 1.4 * (math.floor(fs * t * 2) / (2 * fs))
        fl.append([step_x, 0.0, foot_l] if cyc < 0.5 else [x, 0.2, foot_l])
        fr.append([step_x, 0.0, foot_r] if cyc >= 0.5 else [x, 0.2, foot_r])
    return {"pelvis": pelvis, "hip_l": hl, "hip_r": hr, "foot_l": fl, "foot_r": fr}


class Gait(unittest.TestCase):
    def run_gait(self, samples):
        d = tmpdir()
        path = write_json(os.path.join(d, "walk.json"), samples)
        return run("gait", path, "--pelvis", "pelvis", "--hips", "hip_l,hip_r",
                   "--feet", "foot_l,foot_r")[1]

    def test_neutral_heavy_walk_passes(self):
        res = self.run_gait(walk())
        self.assertEqual(res["verdict"], "PASS", res)
        self.assertAlmostEqual(res["obliquity_amp_deg"], 4.0, delta=0.3)
        self.assertAlmostEqual(res["step_width_m"], 0.10, delta=0.01)

    def test_catwalk_and_drunk_walk_fail(self):
        catwalk = self.run_gait(walk(lat=0.03, obl=8, rot=10, foot_l=0.02, foot_r=-0.02))
        self.assertEqual(catwalk["verdict"], "FAIL")
        text = " ".join(catwalk["problems"])
        for expected in ("obliquity", "rotation", "cross the midline"):
            self.assertIn(expected, text)
        drunk = self.run_gait(walk(lat=0.07, foot_l=-0.11, foot_r=0.11))
        self.assertIn("lateral pelvis shift", " ".join(drunk["problems"]))

    def test_wide_boots_scale_step_width(self):
        d = tmpdir()
        path = write_json(os.path.join(d, "boots.json"), walk(foot_l=-0.145, foot_r=0.145))
        args = ("gait", path, "--pelvis", "pelvis", "--hips", "hip_l,hip_r", "--feet", "foot_l,foot_r")
        self.assertIn("step width", " ".join(run(*args)[1]["problems"]))
        self.assertEqual(run(*args, "--foot-width", "0.247")[1]["verdict"], "PASS")

    def test_stride_and_cadence_kept(self):
        res = self.run_gait(walk())                       # 1.4 m/s at 0.9 cycles/s
        self.assertAlmostEqual(res["stride_m"], 1.4 / 0.9, delta=0.03)
        self.assertAlmostEqual(res["cadence_spm"], 108.0, delta=2.0)
        d = tmpdir()
        path = write_json(os.path.join(d, "w.json"), walk())
        moved = run("gait", path, "--pelvis", "pelvis", "--hips", "hip_l,hip_r", "--feet",
                    "foot_l,foot_r", "--ref-stride", "1.40", "--ref-cadence", "108")[1]
        self.assertEqual(moved["verdict"], "FAIL")
        self.assertIn("stride", " ".join(moved["problems"]))
        self.assertNotIn("cadence", " ".join(moved["problems"]))


# K01: animation that is only a whole-object transform. Skeleton: a 1.8 m figure, joints at
# hip, chest, head, both hands and both feet (metres, Y up).
REST = {"hips": (0.0, 1.0, 0.0), "chest": (0.0, 1.4, 0.0), "head": (0.0, 1.75, 0.0),
        "hand_l": (-0.4, 1.0, 0.0), "hand_r": (0.4, 1.0, 0.0),
        "foot_l": (-0.12, 0.05, 0.0), "foot_r": (0.12, 0.05, 0.0)}


def rigid_track(mode, seconds=2.0, joints=REST):
    import math
    n = int(seconds * HZ)
    out = {name: [] for name in joints}
    for i in range(n):
        t = i / HZ
        ph = 2 * math.pi * t / 1.0          # one cycle per second
        for name, (x, y, z) in joints.items():
            if mode == "alive":             # limbs swing against each other
                swing = 0.15 * math.sin(ph) * (1 if name.endswith("_l") else -1)
                if name.startswith("hand"):
                    z += swing
                elif name.startswith("foot"):
                    z -= swing
                    y += 0.05 * max(0.0, math.sin(ph + (0 if name.endswith("_l") else math.pi)))
                elif name == "chest":
                    y += 0.004 * math.sin(2 * ph)
            elif mode == "rigid":           # the whole sprite bobs, tilts and breathes in scale
                a = 0.15 * math.sin(ph)
                k = 1.0 + 0.03 * math.sin(2 * ph)
                cx, cy = x * k, (y - 1.0) * k
                x, y = cx * math.cos(a) - cy * math.sin(a), 1.0 + cx * math.sin(a) + cy * math.cos(a)
                x += 0.3 * t
                y += 0.05 * math.sin(2 * ph)
            elif mode == "slide":           # translated only
                x += 0.5 * t
            out[name].append([x, y, z])
    return out


class Rigid(unittest.TestCase):
    def check(self, samples, *extra):
        path = write_json(os.path.join(tmpdir(), "loop.json"), samples)
        return run("rigid", path, "--joints", ",".join(samples), "--root", "hips", *extra)[1]

    def test_a_living_cycle_passes(self):
        res = self.check(rigid_track("alive"), "--height", "1.8")
        self.assertEqual(res["verdict"], "PASS", res)
        self.assertGreater(res["residual_max"], res["threshold"]["rigid"])

    def test_a_whole_object_transform_fails(self):
        res = self.check(rigid_track("rigid"), "--height", "1.8")
        self.assertEqual(res["verdict"], "FAIL", res)
        self.assertIn("rigid", res["problem"])
        self.assertLess(res["residual_max"], 1e-6)
        self.assertGreater(res["motion_max"], 0.01)

    def test_nothing_moving_fails(self):
        for mode in ("still", "slide"):          # a pure translation moves no joint vs the root
            res = self.check(rigid_track(mode), "--height", "1.8")
            self.assertEqual(res["verdict"], "FAIL", (mode, res))
            self.assertIn("nothing moves", res["problem"])

    def test_screen_space_traces_and_height_from_the_skeleton(self):
        flat = {k: [[p[0], p[1]] for p in v] for k, v in rigid_track("rigid").items()}
        res = self.check(flat, "--dims", "2")
        self.assertEqual(res["verdict"], "FAIL", res)
        alive = {k: [[p[2], p[1]] for p in v] for k, v in rigid_track("alive").items()}
        res = self.check(alive, "--dims", "2")
        self.assertEqual(res["verdict"], "PASS", res)
        self.assertGreater(res["height"], 1.5)       # head-to-foot span when --height is not given

    def test_pixel_snapped_sprites_with_unit_noise(self):
        # a 64 px sprite moved as one piece but snapped to whole pixels: rounding alone leaves a
        # residual, so --unit-noise 1 (one pixel) is the floor; a moving limb still passes
        def px(mode):
            return {k: [[round(p[0] * 36), round(p[1] * 36)] for p in v]
                    for k, v in rigid_track(mode).items()}
        res = self.check(px("rigid"), "--dims", "2", "--unit-noise", "1")
        self.assertEqual(res["verdict"], "FAIL", res)
        alive = {k: [[round(p[2] * 36), round(p[1] * 36)] for p in v]
                 for k, v in rigid_track("alive").items()}
        res = self.check(alive, "--dims", "2", "--unit-noise", "1")
        self.assertEqual(res["verdict"], "PASS", res)

    def test_fewer_than_three_joints_is_not_assessed(self):
        two = {k: v for k, v in rigid_track("alive").items() if k in ("hips", "head")}
        res = self.check(two, "--height", "1.8")
        self.assertEqual(res["verdict"], "NOT ASSESSED", res)


# K04: pops on transitions and attacks that miss.
def transition_track(pop=False, fast=False, seconds=1.0):
    """Hips stay; a hand moves from rest to a guard pose over the transition. `fast`: an eased
    move in 4 frames (quick but smooth). `pop`: the hand teleports 12 cm in one frame."""
    import math
    n = int(seconds * HZ)
    hips, hand, head = [], [], []
    for i in range(n):
        t = i / HZ
        if fast:
            u = min(1.0, max(0.0, (t - 0.4) / (4 / HZ)))
        else:
            u = min(1.0, max(0.0, (t - 0.3) / 0.3))
        e = u * u * (3 - 2 * u)                      # smoothstep: eased in and out
        x = 0.4 - 0.25 * e
        if pop and i >= int(0.5 * HZ):
            x -= 0.12                                # a break in the motion
        hips.append([0.0, 1.0, 0.0])
        head.append([0.0, 1.7, 0.01 * math.sin(2 * math.pi * t)])
        hand.append([x, 1.1 + 0.2 * e, 0.1])
    return {"hips": hips, "hand_r": hand, "head": head}


class Pops(unittest.TestCase):
    def check(self, samples, *extra):
        path = write_json(os.path.join(tmpdir(), "t.json"), samples)
        return run("pops", path, "--joints", ",".join(samples), "--height", "1.8", *extra)[1]

    def test_smooth_and_fast_eased_transitions_pass(self):
        for fast in (False, True):
            res = self.check(transition_track(fast=fast))
            self.assertEqual(res["verdict"], "PASS", (fast, res))

    def test_a_break_in_motion_fails_and_names_the_joint_and_frame(self):
        res = self.check(transition_track(pop=True))
        self.assertEqual(res["verdict"], "FAIL", res)
        self.assertEqual(res["worst"]["joint"], "hand_r")
        self.assertIn(res["worst"]["frame"], (int(0.5 * HZ) - 1, int(0.5 * HZ)))


def swing_track(miss_dir=None):
    """A sword swept round 360 degrees in 1 s; eight targets at 1.2 m in all directions. The
    impact frame of each direction is when the blade points at it. `miss_dir`: that target sits
    at 2.5 m, out of reach."""
    import math
    n = HZ
    hilt, tip = [], []
    for i in range(n):
        ang = 2 * math.pi * i / n
        hilt.append([0.3 * math.cos(ang), 1.2, 0.3 * math.sin(ang)])
        tip.append([1.4 * math.cos(ang), 1.2, 1.4 * math.sin(ang)])
    samples = {"hilt": hilt, "tip": tip}
    targets = []
    for k in range(8):
        ang = 2 * math.pi * k / 8
        r = 2.5 if k == miss_dir else 1.2
        name = f"target_{k}"
        samples[name] = [[r * math.cos(ang), 1.2, r * math.sin(ang)]] * n
        targets.append(f"{name}@{round(k * n / 8)}")
    return samples, targets


class Hits(unittest.TestCase):
    def check(self, samples, targets, *extra):
        path = write_json(os.path.join(tmpdir(), "a.json"), samples)
        return run("hits", path, "--segment", "hilt,tip", "--targets", ",".join(targets),
                   "--radius", "0.3", *extra)[1]

    def test_every_target_round_the_character_is_hit(self):
        res = self.check(*swing_track())
        self.assertEqual(res["verdict"], "PASS", res)
        self.assertEqual(res["hits"], 8)

    def test_a_target_out_of_reach_at_its_impact_frame_fails(self):
        res = self.check(*swing_track(miss_dir=3))
        self.assertEqual(res["verdict"], "FAIL", res)
        self.assertEqual([m["target"] for m in res["misses"]], ["target_3"])
        self.assertGreater(res["misses"][0]["distance"], 0.3)


if __name__ == "__main__":
    unittest.main()
