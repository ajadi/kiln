"""Tests for plugins/kiln/skills/accessibility/scripts/subtitle_check.py (stdlib only)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "accessibility", "scripts", "subtitle_check.py")

GOOD_SRT = """1
00:00:01,000 --> 00:00:03,500
KAI: The gate is open.
Move, now!

2
00:00:03,600 --> 00:00:06,000
[distant explosion]
"""

BAD_SRT = """1
00:00:01,000 --> 00:00:01,400
Too quick.

2
00:00:01,300 --> 00:00:09,000
This line is far too long to read comfortably on a television
and there is a second line
and a third one

3
00:00:09,100 --> 00:00:10,100
WE ARE UNDER ATTACK EVERYONE

4
00:00:10,200 --> 00:00:11,200
Way too many words crammed into this one short second.
"""

VTT = """WEBVTT

NOTE produced by the cutscene tool

intro-1
00:01.000 --> 00:03.000 line:90%
<v Kai>Hold the line.</v>
"""


def write(root, name, text):
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    return p.returncode, json.loads(p.stdout)


class SubtitleCheck(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-subs-")

    def test_good_and_vtt(self):
        write(self.root, "a.srt", GOOD_SRT)
        write(self.root, "b.vtt", VTT)
        code, res = run(os.path.join(self.root, "*.*"))
        self.assertEqual((code, res["verdict"]), (0, "pass"))
        self.assertEqual([f["cues"] for f in res["files"]], [2, 1])

    def test_bad(self):
        code, res = run(write(self.root, "bad.srt", BAD_SRT))
        self.assertEqual(code, 1)
        issues = {f["cue"]: " | ".join(f["issues"]) for f in res["files"][0]["failures"]}
        self.assertIn("duration 0.40 s", issues[1])
        self.assertIn("3 lines", issues[2])
        self.assertIn("chars > 40", issues[2])
        self.assertIn("overlaps", issues[2])
        self.assertIn("duration 7.70 s > 7.0", issues[2])
        self.assertIn("ALL CAPS", issues[3])
        self.assertIn("chars/s", issues[4])

    def test_speaker_labels(self):
        rows = [{"start": 0, "end": 2, "speaker": "Kai", "text": "KAI: Ready?"},
                {"start": 2.1, "end": 4, "speaker": "Kai", "text": "Then go."},
                {"start": 4.1, "end": 6, "speaker": "Mira", "text": "Going."},
                {"start": 6.1, "end": 8, "speaker": "Narrator", "text": "Years later."}]
        path = write(self.root, "c.json", json.dumps(rows))
        code, res = run(path, "--no-label-speakers", "Narrator")
        self.assertEqual(code, 0)
        self.assertEqual([w["cue"] for w in res["files"][0]["warnings"]], [3])
        code, res = run(path, "--no-label-speakers", "Narrator", "--speakers-need-labels")
        self.assertEqual(code, 1)
        self.assertEqual([f["cue"] for f in res["files"][0]["failures"]], [3])
        csv_path = write(self.root, "d.csv", "start,end,speaker,text\n"
                                             "00:00:01.000,00:00:03.000,Kai,KAI: Cover me.\n")
        code, res = run(csv_path)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
