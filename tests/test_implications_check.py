"""Tests for plugins/kiln/skills/implications/scripts/implications_check.py (stdlib only)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "implications", "scripts", "implications_check.py")

DAGGER = """# TASK-099: dagger

## spec
type: art

## implications
### dagger (category: handheld)
- job: backup blade for close quarters
- states: stowed, drawing, in hand, stowing, dropped
- home: cross-draw sheath on the left hip (PROXY)
- interfaces: dagger-sheath friction + strap; sheath-belt loops - host assets: sheath, belt loops
- empty: sheath stays on the belt, strap open, readable from the camera
- transitions: right hand draws across the body; not while hanging
- ripple: sockets hand_r and hip_l; thigh clearance; icon; sounds; save; AI notices
- premortem: sheath clips the thigh in a sprint; draw hand passes through the chest plate
- grip: hand_r grip socket, closed fist
- carry: left hip, angled forward, strap retention

## checklist
- [ ] model
"""


def write(text):
    fd, path = tempfile.mkstemp(prefix="kiln-impl-", suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=60, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


class Implications(unittest.TestCase):
    def test_complete_dagger_passes(self):
        code, res = run(write(DAGGER))
        self.assertEqual(code, 0, res)
        self.assertEqual(res["things"][0]["category"], "handheld")

    def test_the_live_miss_fails(self):
        # a breathing kit without the helmet side and its empty state (what the user had to add)
        kit = """## implications
### breathing kit (category: wearable)
- job: emergency air
- states: off, on
- home: back
- interfaces: hoses to the helmet
- transitions: put on, take off
- ripple: HUD gauge
- premortem: hoses clip
- region: back
"""
        code, res = run(write(kit))
        self.assertEqual(code, 1)
        text = " ".join(res["problems"])
        for expected in ("missing 'empty'", "missing 'left_behind'", "host-side assets",
                         "at least 2 risks"):
            self.assertIn(expected, text)

    def test_bare_na_and_scope_creep_fail(self):
        bad = DAGGER.replace("- empty: sheath stays on the belt, strap open, readable from the camera",
                             "- empty: n/a").replace(
            "- ripple: sockets hand_r and hip_l; thigh clearance; icon; sounds; save; AI notices",
            "- ripple: " + "; ".join(f"thing{i}" for i in range(20)))
        code, res = run(write(bad))
        self.assertEqual(code, 1)
        text = " ".join(res["problems"])
        self.assertIn("n/a without a reason", text)
        self.assertIn("more than 12 entries", text)

    def test_na_with_reason_and_unknown_category(self):
        ok = DAGGER.replace("- grip: hand_r grip socket, closed fist",
                            "- grip: n/a — thrown weapon only, no grip pose")
        self.assertEqual(run(write(ok))[0], 0)
        bad = DAGGER.replace("(category: handheld)", "(category: sword)")
        code, res = run(write(bad))
        self.assertEqual(code, 1)
        self.assertIn("unknown", res["problems"][0])

    def test_missing_section(self):
        path = write("# TASK-100\n\n## spec\ntype: art\n")
        self.assertEqual(run(path)[1]["verdict"], "NOT ASSESSED")
        code, res = run(path, "--require")
        self.assertEqual((code, res["verdict"]), (1, "FAIL"))


if __name__ == "__main__":
    unittest.main()
