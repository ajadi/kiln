"""Tests for the playtest skill's autoplay scripts: presence.py, autoplay_loop.py,
autoplay_report.py (stdlib), and autoplay_base.gd in a real headless Godot (skipped without one).

g2 rows 56, 104, 105: gameplay gates waited for the user's screen; trace.csv lacked the counters
qa-performance asks for and the snapshot it ran; two chaos runs crashed at engine shutdown after
"AUTOPLAY done", which a "0 crashes" soak gate would count as mid-run crashes.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
SCRIPTS = os.path.join(HERE, "..", "plugins", "kiln", "skills", "playtest", "scripts")
sys.path.insert(0, HERE)
from test_probe_base import GODOT  # noqa: E402


def py(script, *args, cwd=None):
    p = subprocess.run([sys.executable, "-B", os.path.join(SCRIPTS, script), *args], cwd=cwd,
                       capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout, p.stderr


class Presence(unittest.TestCase):
    def test_away_flag_and_idle_threshold(self):
        root = tempfile.mkdtemp(prefix="kiln-pres-")
        code, out, _ = py("presence.py", "--min-idle", "999999", cwd=root)
        self.assertEqual(code, 1, out)
        self.assertFalse(json.loads(out)["away"])
        os.makedirs(os.path.join(root, ".kiln"))
        open(os.path.join(root, ".kiln", "away"), "w").close()
        code, out, _ = py("presence.py", "--min-idle", "999999", cwd=root)
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["reason"], "flag .kiln/away")


FAKE_GAME = r'''
import json, os, sys
args = sys.argv
seed = int(args[args.index("--seed") + 1])
out = args[args.index("--out") + 1]
os.makedirs(out, exist_ok=True)
crash_at_exit = seed % 3 == 0
crash_mid = seed % 5 == 0
if crash_mid:
    print("AUTOPLAY start")
    sys.exit(3)
json.dump({"seed": seed, "verdict": "PASS" if seed % 2 else "FAIL",
           "objectives": {"talk_merchants": 10.0, "pause": None},
           "stuck": [] if seed % 2 else [{"t": 42.0, "where": [1, 0, 2]}],
           "hitches": 2, "hitches_after_shot": 3}, open(os.path.join(out, "summary.json"), "w"))
print("AUTOPLAY done", "PASS")
sys.exit(-1073741819 & 0xFF if crash_at_exit else 0)
'''


class LoopAndReport(unittest.TestCase):
    def test_night_loop_classifies_exit_crashes(self):
        root = tempfile.mkdtemp(prefix="kiln-night-")
        game = os.path.join(root, "fake_game.py")
        with open(game, "w", encoding="utf-8") as fh:
            fh.write(FAKE_GAME)
        os.makedirs(os.path.join(root, ".kiln"))
        open(os.path.join(root, ".kiln", "away"), "w").close()
        code, out, err = py("autoplay_loop.py", "--runs", "6", "--seed", "1", "--out",
                            "production/autoplay/night1", "--", sys.executable, game, cwd=root)
        self.assertEqual(code, 0, out + err)
        code, out, err = py("autoplay_report.py", "production/autoplay/night1", cwd=root)
        rep = json.loads(out)
        self.assertEqual(rep["runs"], 6)
        seeds = {r["seed"]: r for r in rep["results"]}
        self.assertEqual(seeds[3]["crash"], "exit")       # crashed after AUTOPLAY done
        self.assertEqual(seeds[5]["crash"], "mid-run")
        self.assertEqual(rep["crashes_mid_run"], 1)
        self.assertEqual(rep["crashes_at_exit"], 2)       # seeds 3 and 6
        self.assertEqual(rep["objectives"]["talk_merchants"]["reached"], 5)
        self.assertTrue(os.path.isfile(os.path.join(root, "production", "autoplay", "night1",
                                                    "REPORT.md")))

    def test_loop_stops_when_the_user_returns(self):
        root = tempfile.mkdtemp(prefix="kiln-night-")
        game = os.path.join(root, "fake_game.py")
        with open(game, "w", encoding="utf-8") as fh:
            fh.write(FAKE_GAME)
        code, out, err = py("autoplay_loop.py", "--runs", "3", "--seed", "1", "--out", "o",
                            "--min-idle", "999999", "--", sys.executable, game, cwd=root)
        self.assertEqual(code, 2, out + err)
        self.assertIn("user present", out)


AUTOPLAY = '''extends "res://tests/autoplay/autoplay_base.gd"
var hero: Node3D
func _setup() -> void:
	hero = Node3D.new()  # kiln:runtime-node test fixture
	root.add_child(hero)
	add_objective("walk_right", func(): return hero.position.x > 2.0, 30.0)
	add_objective("never", func(): return false, 2.0)
	set_progress(func(): return hero.position)
func _play() -> void:
	for i in 240:
		hero.position.x += 0.02
		await process_frame
	await seconds(3.0)
'''


@unittest.skipUnless(GODOT, "no Godot console binary found (set KILN_GODOT)")
class AutoplayBase(unittest.TestCase):
    def test_objectives_stuck_trace_and_summary(self):
        root = tempfile.mkdtemp(prefix="kiln-ap-")
        with open(os.path.join(root, "project.godot"), "w", encoding="utf-8") as fh:
            fh.write('config_version=5\n\n[application]\n\nconfig/name="ap"\n')
        os.makedirs(os.path.join(root, "tests", "autoplay"))
        shutil.copy(os.path.join(SCRIPTS, "autoplay_base.gd"),
                    os.path.join(root, "tests", "autoplay", "autoplay_base.gd"))
        with open(os.path.join(root, "tests", "autoplay", "run_walk.gd"), "w",
                  encoding="utf-8") as fh:
            fh.write(AUTOPLAY)
        out = os.path.join(root, "production", "autoplay", "r1")
        p = subprocess.run([GODOT, "--headless", "--fixed-fps", "60", "--path", root, "-s",
                            "res://tests/autoplay/run_walk.gd", "--", "--seed", "7", "--out", out,
                            "--stuck-s", "1.5", "--shots-every", "0"],
                           capture_output=True, text=True, timeout=120)
        self.assertIn("AUTOPLAY done", p.stdout, p.stdout + p.stderr)
        with open(os.path.join(out, "summary.json"), encoding="utf-8") as fh:
            s = json.load(fh)
        self.assertEqual(s["seed"], 7)
        self.assertIsNotNone(s["objectives"]["walk_right"])
        self.assertIsNone(s["objectives"]["never"])
        self.assertEqual(s["verdict"], "FAIL")
        self.assertTrue(s["stuck"], s)                    # 3 s standing still after the walk
        with open(os.path.join(out, "trace.csv"), encoding="utf-8") as fh:
            header = fh.readline().strip().split(",")
        for col in ("frame_ms", "draw_calls", "video_mem", "node_count", "object_count",
                    "pipeline_compilations", "after_shot"):
            self.assertIn(col, header)


if __name__ == "__main__":
    unittest.main()
