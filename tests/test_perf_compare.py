"""Tests for plugins/kiln/skills/optimization/scripts/perf_compare.py (stdlib only)."""

import json
import os
import random
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "optimization", "scripts", "perf_compare.py")
sys.path.insert(0, os.path.dirname(SCRIPT))
import perf_compare as pc  # noqa: E402


def frames(n=600, mean=16.0, sd=0.6, seed=1, spikes=()):
    rng = random.Random(seed)
    ms = [max(1.0, rng.gauss(mean, sd)) for _ in range(n)]
    for i, v in spikes:
        ms[i] = v
    return ms


def write(obj, suffix=".json"):
    fd, path = tempfile.mkstemp(prefix="kiln-perf-", suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(obj if isinstance(obj, str) else json.dumps(obj))
    return path


def run(before, after, *args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, before, after, *args],
                       capture_output=True, text=True, timeout=60)
    return p.returncode, json.loads(p.stdout)


class Metrics(unittest.TestCase):
    def test_percentile_matches_linear_interpolation(self):
        s = [float(i) for i in range(1, 101)]
        self.assertAlmostEqual(pc.percentile(s, 50), 50.5)
        self.assertAlmostEqual(pc.percentile(s, 99), 99.01)

    def test_low1_is_time_weighted(self):
        ms = [10.0] * 99 + [100.0]   # 1% of 1090 ms = 10.9 ms, reached by the 100 ms frame
        self.assertEqual(pc.low1_ms(ms), 100.0)
        self.assertAlmostEqual(pc.metrics(ms)["low1_fps"], 10.0)

    def test_hitches(self):
        ms = frames(spikes=[(300, 40.0), (400, 60.0)])
        self.assertEqual(pc.hitches(ms, 50.0), 2)


class Compare(unittest.TestCase):
    def test_same_distribution_is_unchanged(self):
        a, b = write({"frame_ms": frames(seed=1)}), write({"frame_ms": frames(seed=2)})
        code, res = run(a, b)
        self.assertEqual((code, res["change"], res["verdict"]), (0, "unchanged", "pass"), res)
        code, res = run(a, b, "--expect", "improve")
        self.assertEqual((code, res["verdict"]), (1, "fail"))

    def test_faster_is_improved(self):
        a = write({"frame_ms": frames(mean=16.0)})
        b = write({"frame_ms": frames(mean=12.5, seed=3)})
        code, res = run(a, b, "--expect", "improve")
        self.assertEqual((code, res["change"]), (0, "improved"), res)
        self.assertEqual(res["deltas"]["p50_ms"]["direction"], "better")
        self.assertLess(res["deltas"]["p50_ms"]["delta"], -3.0)

    def test_slower_or_hitches_is_regressed(self):
        a = write({"frame_ms": frames()})
        code, res = run(a, write({"frame_ms": frames(mean=18.0, seed=4)}))
        self.assertEqual((code, res["change"], res["verdict"]), (1, "regressed", "fail"))
        self.assertIn("p50_ms", " ".join(res["problems"]))
        code, res = run(a, write({"frame_ms": frames(seed=5, spikes=[(200, 80.0)])}))
        self.assertEqual(res["change"], "regressed")
        self.assertIn("hitches", " ".join(res["problems"]))
        code, res = run(a, write({"frame_ms": frames(seed=5, spikes=[(200, 80.0)])}),
                        "--hitch-tol", "1")
        self.assertNotIn("hitches", " ".join(res["problems"]))

    def test_too_few_samples_fails(self):
        code, res = run(write({"frame_ms": frames(n=60)}), write({"frame_ms": frames()}))
        self.assertEqual((code, res["change"]), (1, "insufficient"))

    def test_skip_drops_warmup(self):
        warm = frames(n=700, spikes=[(i, 90.0) for i in range(5)])
        code, res = run(write({"frame_ms": warm}), write({"frame_ms": frames(n=700, seed=7)}),
                        "--skip", "10")
        self.assertEqual(res["before"]["hitches"], 0)
        self.assertEqual(res["before"]["samples"], 690)


class Formats(unittest.TestCase):
    def test_samples_key_jsonl_and_csv(self):
        base = frames(n=300)
        dump = write({"frame_ms": [1.0] * 300, "samples": {"gpu_ms": base}})
        self.assertEqual(pc.load_series(dump, "gpu_ms"), base)
        jsonl = write("\n".join(json.dumps({"frame": i, "dt_ms": v}) for i, v in enumerate(base)),
                      ".jsonl")
        self.assertEqual(pc.load_series(jsonl, "dt_ms"), base)
        rows = "Frame,FrameTime,GPUTime\n" + "\n".join(f"{i},{v},{v / 2}"
                                                       for i, v in enumerate(base))
        self.assertAlmostEqual(pc.load_series(write(rows, ".csv"), "frametime")[5], base[5])
        code, res = run(write(rows, ".csv"), write(rows, ".csv"), "--key", "GPUTime")
        self.assertEqual((code, res["change"]), (0, "unchanged"))

    def test_missing_key_reports_error(self):
        code, res = run(write({"other": [1, 2]}), write({"frame_ms": frames()}))
        self.assertEqual((code, res["verdict"]), (1, "fail"))
        self.assertIn("frame_ms", res["error"])


if __name__ == "__main__":
    unittest.main()
