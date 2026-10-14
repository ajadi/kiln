"""Tests for plugins/kiln/skills/controls-camera/scripts/camera_probe.py (stdlib only)."""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "controls-camera", "scripts", "camera_probe.py")
HZ = 60
TMP = tempfile.TemporaryDirectory(prefix="kiln-cam-")


def tearDownModule():
    TMP.cleanup()


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=60)
    return p.returncode, json.loads(p.stdout)


def write(obj, suffix=".json", lines=False):
    fd, path = tempfile.mkstemp(suffix=suffix, dir=TMP.name)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        if lines:
            fh.write("\n".join(json.dumps(r) for r in obj))
        else:
            json.dump(obj, fh)
    return path


def orbit(n=180, deg_s=90.0, radius=3.0, start_turn=0, jump=None):
    """Camera orbiting a target at the origin, looking at it; optional instant extra yaw."""
    cam_pos, cam_fwd, target = [], [], []
    yaw = 0.0
    for i in range(n):
        if i >= start_turn and i > 0:
            yaw += math.radians(deg_s) / HZ
        if jump and i == jump[0]:
            yaw += math.radians(jump[1])
        p = [radius * math.sin(yaw), 1.5, radius * math.cos(yaw)]
        t = [0.0, 1.5, 0.0]
        cam_pos.append(p)
        cam_fwd.append([t[0] - p[0], 0.0, t[2] - p[2]])
        target.append(t)
    return cam_pos, cam_fwd, target


def recorder(n, **samples):
    return {"physics_ticks_per_second": HZ, "ticks": list(range(n)), "frame_ms": [16.6] * n,
            "samples": samples}


def by_name(res):
    return {m["metric"]: m for m in res["metrics"]}


class Camera(unittest.TestCase):
    def base(self, **over):
        n = 180
        pos, fwd, tgt = orbit(n)
        s = dict(cam_pos=pos, cam_fwd=fwd, target_pos=tgt, occ=[False] * n,
                 inside=[False] * n, fov=[70.0] * n, look=[0.0] * n)
        s.update(over)
        return recorder(n, **s)

    def args(self, path, *extra):
        return ["camera", path, "--cam-pos", "cam_pos", "--cam-fwd", "cam_fwd",
                "--target", "target_pos", "--occluded", "occ", "--inside", "inside",
                "--fov", "fov", "--fov-range", "60", "110", "--look", "look", "--lock-on", *extra]

    def test_smooth_orbit_passes(self):
        code, res = run(*self.args(write(self.base())))
        self.assertEqual(code, 0, res)
        self.assertEqual(res["verdict"], "PASS")
        m = by_name(res)
        self.assertAlmostEqual(m["auto_angular_speed_max_deg_s"]["value"], 90.0, delta=0.5)
        self.assertEqual(m["target_in_view_ratio"]["verdict"], "PASS")
        self.assertEqual(m["camera_pops"]["value"], 0)

    def test_inside_geometry_and_long_occlusion_fail(self):
        n = 180
        inside = [False] * n
        inside[50] = True
        occ = [60 <= i < 120 for i in range(n)]  # 1 s continuous, 33% of ticks
        code, res = run(*self.args(write(self.base(inside=inside, occ=occ))))
        self.assertEqual(code, 1)
        m = by_name(res)
        self.assertEqual(m["camera_inside_geometry_ticks"]["verdict"], "FAIL")
        self.assertEqual(m["camera_inside_geometry_ticks"]["first_ticks"], [50])
        self.assertEqual(m["target_occluded_ratio"]["verdict"], "FAIL")
        self.assertAlmostEqual(m["target_occluded_longest_s"]["value"], 1.0, places=3)

    def test_fast_automatic_turn_and_pop_fail_but_cut_is_allowed(self):
        n = 180
        pos, fwd, tgt = orbit(n, deg_s=300.0)
        code, res = run(*self.args(write(self.base(cam_pos=pos, cam_fwd=fwd, target_pos=tgt))))
        self.assertEqual(by_name(res)["auto_angular_speed_max_deg_s"]["verdict"], "FAIL")

        pos, fwd, tgt = orbit(n, deg_s=60.0, jump=(90, 45.0))
        code, res = run(*self.args(write(self.base(cam_pos=pos, cam_fwd=fwd, target_pos=tgt))))
        self.assertEqual(code, 1)
        self.assertEqual(by_name(res)["camera_pops"]["verdict"], "FAIL")
        cut = [i == 90 for i in range(n)]
        path = write(self.base(cam_pos=pos, cam_fwd=fwd, target_pos=tgt, cut=cut))
        code, res = run(*self.args(path, "--cut", "cut"))
        self.assertEqual(by_name(res)["camera_pops"]["verdict"], "PASS", res)

    def test_player_driven_turn_is_not_graded_as_automatic(self):
        n = 180
        pos, fwd, tgt = orbit(n, deg_s=400.0)
        look = [1.0] * n
        code, res = run(*self.args(write(self.base(cam_pos=pos, cam_fwd=fwd, target_pos=tgt,
                                                   look=look))))
        self.assertNotIn("auto_angular_speed_max_deg_s", by_name(res))

    def test_look_latency(self):
        n = 120
        look = [1.0 if i >= 30 else 0.0 for i in range(n)]
        pos, fwd, tgt = orbit(n, deg_s=120.0, start_turn=33)   # camera reacts 3 ticks late
        code, res = run(*self.args(write(self.base(cam_pos=pos, cam_fwd=fwd, target_pos=tgt,
                                                   look=look, occ=[False] * n, inside=[False] * n,
                                                   fov=[70.0] * n))))
        m = by_name(res)["look_latency_ticks"]
        self.assertEqual(m["value"], 3)
        self.assertEqual(m["verdict"], "FAIL")
        pos, fwd, tgt = orbit(n, deg_s=120.0, start_turn=30)
        code, res = run(*self.args(write(self.base(cam_pos=pos, cam_fwd=fwd, target_pos=tgt,
                                                   look=look, occ=[False] * n, inside=[False] * n,
                                                   fov=[70.0] * n))))
        self.assertEqual(by_name(res)["look_latency_ticks"]["verdict"], "PASS", res)

    def test_fov_out_of_range_and_too_fast(self):
        n = 180
        fov = [70.0 if i < 100 else 120.0 for i in range(n)]
        code, res = run(*self.args(write(self.base(fov=fov))))
        m = by_name(res)
        self.assertEqual(m["fov_range_deg"]["verdict"], "FAIL")
        self.assertEqual(m["fov_rate_max_deg_s"]["verdict"], "FAIL")

    def test_json_lines_with_unit_scale(self):
        n = 60
        rows = []
        for i in range(n):
            x = 0.0 if i < 30 else 50.0                           # 50 cm sideways step
            rows.append({"dt": 1.0 / HZ, "cam_pos": {"x": x, "y": 150.0, "z": -300.0},
                         "cam_fwd": [0.0, 0.0, 1.0], "target_pos": [x, 150.0, 0.0]})
        path = write(rows, suffix=".jsonl", lines=True)
        base = ["camera", path, "--cam-pos", "cam_pos", "--cam-fwd", "cam_fwd",
                "--target", "target_pos"]
        code, res = run(*base)
        self.assertEqual(by_name(res)["camera_pops"]["verdict"], "FAIL")   # 50 units > 1
        code, res = run(*base, "--unit-scale", "0.01")
        self.assertEqual(by_name(res)["camera_pops"]["verdict"], "PASS", res)

    def test_missing_probe_is_not_assessed(self):
        code, res = run("camera", write(self.base()), "--cam-pos", "nope", "--cam-fwd", "cam_fwd",
                        "--target", "target_pos")
        self.assertEqual(code, 2)
        self.assertEqual(res["verdict"], "NOT ASSESSED")


def stick_dump(fn, inner=0.15):
    stick, out = [], []
    for k in range(72):
        a = math.radians(k * 5)
        for m in [0.0, 0.05, 0.1, 0.14, 0.16, 0.18, 0.2, 0.3, 0.5, 0.7, 0.9, 0.96, 1.0]:
            v = [m * math.cos(a), m * math.sin(a)]
            stick.append(v)
            out.append(fn(v, inner))
    return recorder(len(stick), stick=stick, look_rate=out)


def scaled_radial(v, dz):
    m = math.hypot(*v)
    if m < dz:
        return [0.0, 0.0]
    t = min((m - dz) / (1 - dz), 1.0)
    return [v[0] / m * t, v[1] / m * t]


def unscaled_radial(v, dz):
    return [0.0, 0.0] if math.hypot(*v) < dz else list(v)


def axial(v, dz):
    return [math.copysign(max(abs(c) - dz, 0.0) / (1 - dz), c) for c in v]


class Stick(unittest.TestCase):
    def check(self, fn):
        code, res = run("stick", write(stick_dump(fn)), "--input", "stick",
                        "--response", "look_rate", "--inner", "0.15")
        return code, res, by_name(res)

    def test_scaled_radial_passes(self):
        code, res, m = self.check(scaled_radial)
        self.assertEqual(code, 0, res)
        self.assertEqual(res["verdict"], "PASS")

    def test_unscaled_radial_jumps_at_edge(self):
        code, res, m = self.check(unscaled_radial)
        self.assertEqual(m["edge_output_ratio"]["verdict"], "FAIL")
        self.assertEqual(m["dead_zone_leak_ratio"]["verdict"], "PASS")

    def test_axial_slows_diagonals(self):
        code, res, m = self.check(axial)
        self.assertEqual(m["diagonal_vs_cardinal_ratio"]["verdict"], "FAIL")

    def test_no_dead_zone_leaks(self):
        code, res, m = self.check(lambda v, dz: list(v))
        self.assertEqual(code, 1)
        self.assertEqual(m["dead_zone_leak_ratio"]["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()
