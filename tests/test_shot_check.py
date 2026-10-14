"""Tests for the cinematic skill's shot_check.py: shot-list continuity (timeline gaps, the
180-degree line, the 30-degree rule) and subtitle timing (S09)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "cinematic",
                      "scripts", "shot_check.py")


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=60)
    return p.returncode, json.loads(p.stdout)


def shot(sid, start, end, cam, subject="hero", axis=("hero", "villain"), **extra):
    return dict({"id": sid, "start": start, "end": end, "camera": {"pos": cam},
                 "subject": subject, "axis": list(axis)}, **extra)


SUBJECTS = {"hero": [0, 0, 0], "villain": [4, 0, 0]}  # y up: the line runs along x


class Shots(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-shots-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def check(self, shots, **extra):
        path = os.path.join(self.root, "shots.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(dict({"fps": 24, "up": "y", "subjects": SUBJECTS, "shots": shots}, **extra),
                      fh)
        return run("shots", path)

    def test_a_clean_dialogue_passes(self):
        code, res = self.check([
            shot("1", 0, 4, [2, 1.6, 6], subject="villain"),     # master, line side z > 0
            shot("2", 4, 7, [-1, 1.6, 3], subject="villain"),    # over hero's shoulder
            shot("3", 7, 10, [5, 1.6, 3], subject="hero")])      # reverse, same side
        self.assertEqual(code, 0, res)
        self.assertEqual(res["verdict"], "pass")
        self.assertAlmostEqual(res["mean_shot_s"], 10 / 3, places=2)

    def test_crossing_the_line_fails_unless_marked(self):
        shots = [shot("1", 0, 4, [-1, 1.6, 3], subject="villain"),
                 shot("2", 4, 7, [5, 1.6, -3], subject="hero")]   # z < 0: other side
        code, res = self.check(shots)
        self.assertEqual(code, 1, res)
        self.assertIn("180", res["problems"][0])
        self.assertIn("1 -> 2", res["problems"][0])
        shots[1]["cross_line"] = "dolly move across the line on screen"
        code, res = self.check(shots)
        self.assertEqual(code, 0, res)

    def test_a_cut_under_30_degrees_on_one_subject_is_a_jump_cut(self):
        code, res = self.check([shot("1", 0, 3, [0, 1.6, 5], subject="hero"),
                                shot("2", 3, 6, [1, 1.6, 5], subject="hero")])  # about 11 deg
        self.assertEqual(code, 1, res)
        self.assertIn("30", res["problems"][0])
        # the same angle with a clear change of shot size (focal x2) is a cut-in, not a jump
        code, res = self.check([shot("1", 0, 3, [0, 1.6, 5], subject="hero", focal_mm=24),
                                shot("2", 3, 6, [1, 1.6, 5], subject="hero", focal_mm=85)])
        self.assertEqual(code, 0, res)

    def test_gaps_and_overlaps_in_the_timeline_fail(self):
        code, res = self.check([shot("1", 0, 3, [2, 1.6, 6]), shot("2", 3.5, 6, [2, 1.6, 6.5],
                                                                  subject="villain")])
        self.assertEqual(code, 1, res)
        self.assertIn("gap", res["problems"][0])

    def test_z_up_scenes(self):
        subjects = {"hero": [0, 0, 0], "villain": [4, 0, 0]}
        code, res = self.check([shot("1", 0, 4, [-1, 3, 1.6], subject="villain"),
                                shot("2", 4, 7, [5, -3, 1.6], subject="hero")],
                               up="z", subjects=subjects)
        self.assertEqual(code, 1, res)


class Subtitles(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-subs-")
        self.srt = os.path.join(self.root, "en.srt")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, cues):
        with open(self.srt, "w", encoding="utf-8") as fh:
            for i, (a, b, text) in enumerate(cues, 1):
                fh.write(f"{i}\n{a} --> {b}\n{text}\n\n")

    def test_good_cues_pass(self):
        self.write([("00:00:01,000", "00:00:03,000", "Where were you?"),
                    ("00:00:03,500", "00:00:06,000", "Out.\nLooking for the key.")])
        code, res = run("subs", self.srt, "--fps", "24")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["cues"], 2)

    def test_reading_speed_length_lines_duration_and_gap(self):
        self.write([
            ("00:00:01,000", "00:00:02,000", "This line is far too long to be read in one second."),
            ("00:00:02,040", "00:00:02,500", "Short."),
            ("00:00:05,000", "00:00:09,000", "one\ntwo\nthree"),
            ("00:00:10,000", "00:00:14,000",
             "A single line that runs well past the forty character limit")])
        code, res = run("subs", self.srt, "--fps", "24")
        self.assertEqual(code, 1, res)
        text = "\n".join(res["problems"])
        for word in ("chars/s", "gap", "frames", "lines", "chars per line"):
            self.assertIn(word, text)
        code, res = run("subs", self.srt, "--fps", "24", "--cps", "60", "--max-line", "80")
        self.assertNotIn("chars/s", "\n".join(res["problems"]))


if __name__ == "__main__":
    unittest.main()
