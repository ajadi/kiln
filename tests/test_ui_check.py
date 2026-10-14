"""Tests for plugins/kiln/skills/ui/scripts/ui_check.py (synthetic data; numpy + Pillow)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "ui",
                      "scripts", "ui_check.py")


def el(path, typ, rect, text="", visible=True, disabled=False):
    x, y, w, h = rect
    return {"path": path, "name": path.rsplit("/", 1)[-1], "type": typ, "visible": visible,
            "disabled": disabled, "text": text,
            "global_rect": {"position": {"x": x, "y": y}, "size": {"x": w, "y": h}}}


def run(*args, cwd=None):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       encoding="utf-8", timeout=60, cwd=cwd)
    return p.returncode, json.loads(p.stdout)


class UiCheck(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-ui-")

    def dump(self, name, data):
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path

    def test_focus_diff(self):
        # g2 row 133: a slider's focus changed contrast by only 1.66:1 and nobody noticed;
        # `focus` checks reachability, not visibility.
        base = np.full((120, 200, 3), 40, np.uint8)
        base[40:80, 50:150] = 90                               # the control
        unfocused = os.path.join(self.root, "u.png")
        Image.fromarray(base).save(unfocused)
        ring = base.copy()
        ring[37:83, 47:153] = 240
        ring[40:80, 50:150] = 90                               # 3 px ring outside the control
        Image.fromarray(ring).save(os.path.join(self.root, "ring.png"))
        tint = base.copy()
        tint[40:80, 50:150] = 125                              # colour tint only
        Image.fromarray(tint).save(os.path.join(self.root, "tint.png"))
        code, res = run("focus-diff", os.path.join(self.root, "ring.png"), unfocused,
                        "--rect", "50,40,100,40")
        self.assertEqual(code, 0, res)
        self.assertGreaterEqual(res["thickness_px"], 2.5)
        self.assertGreaterEqual(res["contrast"], 3)
        code, res = run("focus-diff", os.path.join(self.root, "tint.png"), unfocused,
                        "--rect", "50,40,100,40")
        self.assertEqual(code, 1, res)
        self.assertLess(res["contrast"], 3)

    def test_layout(self):
        elements = {"data": {"elements": [
            el("/root/Hud", "Control", (0, 0, 1920, 1080)),                 # background: ignored
            el("/root/Hud/Ammo", "Label", (1700, 990, 200, 60), "30 / 90"),  # outside title safe
            el("/root/Hud/Score", "Label", (120, 80, 200, 40), "Score"),     # fine
            el("/root/Hud/Off", "Label", (1900, 500, 100, 40), "Clipped"),   # off screen
            el("/root/Menu/Play", "Button", (800, 500, 300, 60), "Play"),
            el("/root/Menu/Quit", "Button", (800, 540, 300, 60), "Quit"),    # overlaps Play
            el("/root/Menu/Tiny", "CheckBox", (800, 700, 16, 16)),           # small target
            el("/root/Menu/Play/Icon", "TextureButton", (810, 505, 30, 30)),  # child: no overlap
            el("/root/Menu/Hidden", "Button", (0, 0, 5, 5), "x", visible=False),
        ]}}
        code, res = run("layout", self.dump("e.json", elements), "--viewport", "1920x1080")
        self.assertEqual(code, 1)
        self.assertEqual([e["path"] for e in res["outside_safe_area"]], ["/root/Hud/Ammo"])
        self.assertEqual([e["path"] for e in res["offscreen"]], ["/root/Hud/Off"])
        self.assertEqual([e["path"] for e in res["small_targets"]], ["/root/Menu/Tiny"])
        self.assertEqual(res["overlapping_interactive"], [["/root/Menu/Play", "/root/Menu/Quit"]])
        ok = {"elements": [el("/root/Hud/Score", "Label", (120, 80, 200, 40), "Score")]}
        code, res = run("layout", self.dump("ok.json", ok), "--viewport", "1920x1080")
        self.assertEqual((code, res["verdict"]), (0, "pass"))

    def capture(self):
        """1920x1080 dark scene; three labels drawn as light glyph bars of known height."""
        img = np.full((1080, 1920, 3), 30, np.uint8)
        img[100:160, 100:500] = (40, 40, 40)
        for x in range(110, 480, 12):          # 30 px tall glyphs, white
            img[115:145, x:x + 5] = 255
        img[300:330, 100:500] = (40, 40, 40)
        for x in range(110, 480, 10):          # 12 px tall glyphs: too small
            img[309:321, x:x + 3] = 255
        img[500:560, 100:500] = (90, 90, 90)
        for x in range(110, 480, 12):          # 30 px tall, grey on grey: low contrast
            img[515:545, x:x + 5] = 120
        img[700:770, 100:500] = (40, 40, 40)   # two 20 px lines, 6 px apart, with "i-dots"
        for x in range(110, 480, 12):
            img[705:708, x:x + 3] = 255
            img[710:730, x:x + 5] = 255
            img[736:756, x:x + 5] = 255
        path = os.path.join(self.root, "cap.png")
        Image.fromarray(img).save(path)
        return path

    def test_text(self):
        cap = self.capture()
        elements = {"elements": [el("/root/Hud/Big", "Label", (100, 100, 400, 60), "Hgjpqy"),
                                 el("/root/Hud/Small", "Label", (100, 300, 400, 30), "tiny"),
                                 el("/root/Hud/Faint", "Label", (100, 500, 400, 60), "faint"),
                                 el("/root/Hud/Two", "Label", (100, 700, 400, 70), "a\nb")]}
        code, res = run("text", cap, self.dump("t.json", elements), "--viewport", "1920x1080")
        rows = {r["path"].rsplit("/", 1)[-1]: r for r in res["elements"]}
        self.assertEqual(rows["Two"]["body_px"], 25)  # dots join their line, lines stay apart
        self.assertEqual(rows["Big"]["body_px"], 30)
        self.assertGreater(rows["Big"]["contrast"], 10)
        self.assertEqual(rows["Big"]["verdict"], "pass")
        self.assertEqual(rows["Small"]["body_px"], 12)
        self.assertEqual(rows["Small"]["verdict"], "fail")
        self.assertLess(rows["Faint"]["contrast"], 2.0)
        self.assertEqual(rows["Faint"]["verdict"], "fail")
        self.assertEqual(code, 1)
        # console profile raises the bar: 30 px passes 26 px
        code, res = run("text", cap, self.dump("t2.json", {"elements": elements["elements"][:1]}),
                        "--viewport", "1920x1080", "--profile", "console")
        self.assertEqual((code, res["verdict"]), (0, "pass"))

    def test_focus(self):
        elements = {"elements": [el("/root/M/Play", "Button", (0, 0, 100, 40), "Play"),
                                 el("/root/M/Settings", "Button", (0, 50, 100, 40), "Settings"),
                                 el("/root/M/Quit", "Button", (0, 100, 100, 40), "Quit"),
                                 el("/root/M/Credits", "Button", (0, 150, 100, 40), "Credits")]}
        trace = [{"input": None, "focus": "/root/M/Play"},
                 {"input": "ui_down", "focus": "/root/M/Settings"},
                 {"input": "ui_down", "focus": "/root/M/Quit"},
                 {"input": "ui_down", "focus": "/root/M/Quit"},
                 {"input": "ui_up", "focus": ""}]
        code, res = run("focus", self.dump("tr.json", trace), "--elements",
                        self.dump("fe.json", elements))
        self.assertEqual(code, 1)
        self.assertEqual(res["unreachable"], ["/root/M/Credits"])
        self.assertEqual(res["focus_lost_at"], [4])
        self.assertEqual(len(res["no_move"]), 1)
        good = [{"input": None, "focus": "/root/M/Play"},
                {"input": "ui_down", "focus": "/root/M/Settings"},
                {"input": "ui_down", "focus": "/root/M/Quit"},
                {"input": "ui_down", "focus": "/root/M/Credits"},
                {"input": "ui_down", "focus": "/root/M/Play"}]
        code, res = run("focus", self.dump("g.json", {"steps": good}), "--elements",
                        self.dump("fe2.json", elements), "--expect-wrap")
        self.assertEqual((code, res["verdict"]), (0, "pass"))

    def test_colours_and_simulate(self):
        code, res = run("colours", "#d9534f", "#5cb85c", "--names", "danger,ok")
        self.assertEqual(code, 1)
        self.assertTrue(res["vision"]["deutan"]["too_close"])
        self.assertFalse(res["vision"]["normal"]["too_close"])
        code, res = run("colours", "#ff7f0e", "#1f77b4")
        self.assertEqual((code, res["verdict"]), (0, "pass"))
        code, res = run("simulate", self.capture(), "--out-dir", os.path.join(self.root, "cvd"))
        self.assertEqual(code, 0)
        self.assertEqual(len(res["written"]), 3)
        self.assertTrue(all(os.path.exists(p) for p in res["written"]))


if __name__ == "__main__":
    unittest.main()
