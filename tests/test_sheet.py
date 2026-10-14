"""Tests for plugins/kiln/skills/art-2d/scripts/sheet.py (synthetic frames, unittest)."""

import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "art-2d",
                      "scripts", "sheet.py")
spec = importlib.util.spec_from_file_location("kiln_sheet", SCRIPT)
sheet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sheet)


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=120)
    return p.returncode, json.loads(p.stdout)


def make_frames(root):
    """run_0..5 (underscore), idle-0..3 (hyphen), jump/ folder with 2 frames; 24x32 canvases
    with an opaque block that moves, so trimming changes spriteSourceSize."""
    rng = random.Random(7)
    os.makedirs(os.path.join(root, "jump"))
    blocks = {}

    def frame(path, i):
        a = np.zeros((32, 24, 4), np.uint8)
        x, y, w, h = rng.randint(0, 9), rng.randint(0, 12), 10, 14 + i % 4
        a[y:y + h, x:x + w] = (40 + 30 * i, 200, 90, 255)
        a[y, x] = (255, 0, 0, 255)  # mark the top-left so the crop is identifiable
        Image.fromarray(a, "RGBA").save(path)
        blocks[os.path.basename(path)] = (x, y, w, h)
    for i in range(6):
        frame(os.path.join(root, f"run_{i}.png"), i)
    for i in range(4):
        frame(os.path.join(root, f"idle-{i}.png"), i)
    for i in range(2):
        frame(os.path.join(root, "jump", f"{i:04d}.png"), i)
    return blocks


class Pack(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-sheet-")
        self.blocks = make_frames(self.root)
        self.out = os.path.join(self.root, "out")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def pack(self, *extra, name="s"):
        png, data = os.path.join(self.out, name + ".png"), os.path.join(self.out, name + ".json")
        code, res = run("pack", os.path.join(self.root, "*.png"), os.path.join(self.root, "jump"),
                        "--out", png, "--data", data, *extra)
        with open(data, encoding="utf-8") as fh:
            return code, res, json.load(fh), np.asarray(Image.open(png).convert("RGBA"))

    def test_packed_trim_extrude_roundtrip(self):
        code, res, data, img = self.pack("--trim", "--padding", "2", "--extrude", "1",
                                         "--tag-fps", "run=12", "--once", "jump",
                                         "--pingpong", "idle")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["frames"], 12)
        tags = {t["name"]: t for t in data["meta"]["frameTags"]}
        self.assertEqual(list(tags), ["idle", "run", "jump"])  # glob order, then the folder
        self.assertEqual((tags["idle"]["from"], tags["idle"]["to"]), (0, 3))
        self.assertEqual(tags["idle"]["direction"], "pingpong")
        self.assertEqual(tags["jump"]["repeat"], "1")
        self.assertNotIn("repeat", tags["run"])
        for f in data["frames"]:
            for key in ("filename", "frame", "rotated", "trimmed", "spriteSourceSize",
                        "sourceSize", "duration", "pivot"):
                self.assertIn(key, f)
            self.assertFalse(f["rotated"])
            self.assertEqual(f["sourceSize"], {"w": 24, "h": 32})
            self.assertEqual(f["pivot"], {"x": 0.5, "y": 1.0})
            name = f["filename"].split("/")[-1]
            x, y, w, h = self.blocks[name]
            s, r = f["spriteSourceSize"], f["frame"]
            self.assertEqual((s["x"], s["y"], s["w"], s["h"]), (x, y, w, h))  # pivot info kept
            self.assertTrue(f["trimmed"])
            crop = img[r["y"]:r["y"] + r["h"], r["x"]:r["x"] + r["w"]]
            self.assertEqual(tuple(crop[0, 0]), (255, 0, 0, 255))
            self.assertTrue((crop[..., 3] == 255).all())
            ring = img[r["y"] - 1:r["y"] + r["h"] + 1, r["x"] - 1:r["x"] + r["w"] + 1]
            self.assertTrue(np.array_equal(ring, np.pad(crop, ((1, 1), (1, 1), (0, 0)),
                                                        mode="edge")))
        run_d = {f["duration"] for f in data["frames"][tags["run"]["from"]:tags["run"]["to"] + 1]}
        self.assertEqual(run_d, {83})
        self.assertEqual(data["frames"][0]["duration"], 100)
        code, chk = run("check", os.path.join(self.out, "s.json"))
        self.assertEqual(code, 0, chk)
        self.assertGreaterEqual(chk["min_gap_px"], 4)  # padding 2 + 2 x extrude 1

    def test_grid_is_hframes_compatible(self):
        code, res, data, img = self.pack("--layout", "grid", "--padding", "0", "--extrude", "0")
        self.assertEqual(code, 0, res)
        self.assertTrue(res["hframes_compatible"])
        self.assertEqual(img.shape[:2], (3 * 32, 6 * 24))  # one row per tag, 6 columns
        jump0 = data["frames"][data["meta"]["frameTags"][2]["from"]]["frame"]
        self.assertEqual((jump0["x"], jump0["y"]), (0, 64))
        code, g = run("godot", os.path.join(self.out, "s.json"), "--res-dir", "res://art/hero",
                      "--parent", "/Main/Hero", "--pixel-art")
        self.assertEqual(code, 0, g)
        self.assertEqual(g["mode"], "hframes")
        props = {s["params"]["property"]: s["params"]["value"] for s in g["steps"]
                 if s["tool"] == "node_set_property"}
        self.assertEqual((props["hframes"], props["vframes"]), (6, 3))
        self.assertEqual(props["offset"], {"x": -12, "y": -32})  # feet pivot, centered off
        self.assertEqual(props["texture_filter"], 1)
        self.assertEqual(props["texture"], "res://art/hero/s.png")
        tracks = [s["params"]["params"] for s in g["steps"] if s["tool"] == "animation_manage"
                  and s["params"]["op"] == "add_property_track"]
        jump = [t for t in tracks if t["animation_name"] == "jump"][0]
        self.assertEqual(jump["track_path"], "Sprite:frame")
        self.assertEqual([k["value"] for k in jump["keyframes"]], [12, 13])
        self.assertEqual(jump["interpolation"], "nearest")

    def test_godot_region_offsets_and_pingpong(self):
        self.pack("--trim", "--pingpong", "idle", "--once", "jump")
        data_path = os.path.join(self.out, "s.json")
        code, g = run("godot", data_path, "--res-dir", "res://art/hero", "--parent", "Main/Hero")
        self.assertEqual(code, 0, g)
        self.assertEqual(g["mode"], "region")
        anims = {a["name"]: a for a in g["animations"]}
        self.assertEqual(anims["idle"]["frames"], 6)  # 0 1 2 3 2 1
        self.assertTrue(anims["idle"]["loop"])
        self.assertFalse(anims["jump"]["loop"])
        self.assertAlmostEqual(anims["run"]["length_s"], 0.6)
        create = [s["params"] for s in g["steps"] if s["tool"] == "animation_create"]
        self.assertEqual({c["name"]: c["loop_mode"] for c in create},
                         {"idle": "linear", "run": "linear", "jump": "none"})
        tracks = {(s["params"]["params"]["animation_name"], s["params"]["params"]["track_path"]):
                  s["params"]["params"]["keyframes"] for s in g["steps"]
                  if s["tool"] == "animation_manage" and s["params"]["op"] == "add_property_track"}
        with open(data_path, encoding="utf-8") as fh:
            data = json.load(fh)
        f0 = data["frames"][4]  # run_0
        rr = tracks[("run", "Sprite:region_rect")][0]["value"]
        self.assertEqual(rr, {"position": {"x": f0["frame"]["x"], "y": f0["frame"]["y"]},
                              "size": {"x": f0["frame"]["w"], "y": f0["frame"]["h"]}})
        off = tracks[("run", "Sprite:offset")][0]["value"]
        self.assertEqual(off, {"x": f0["spriteSourceSize"]["x"] - 12,
                               "y": f0["spriteSourceSize"]["y"] - 32})
        times = [k["time"] for k in tracks[("idle", "Sprite:region_rect")]]
        self.assertEqual(times, [0.0, 0.1, 0.2, 0.3, 0.4, 0.5])

    def test_godot_frames_setup_atlas_margins(self):
        self.pack("--trim", "--dedupe")
        code, g = run("godot", os.path.join(self.out, "s.json"), "--res-dir", "res://art/hero/",
                      "--parent", "Main", "--setup", "frames")
        self.assertEqual(code, 0, g)
        atlas = [s["params"]["params"] for s in g["steps"] if s["tool"] == "resource_manage"
                 and s["params"]["params"]["type"] == "AtlasTexture"]
        self.assertEqual(len(atlas), 12)
        first = atlas[0]["properties"]
        self.assertEqual(first["atlas"], "res://art/hero/s.png")
        m = first["margin"]
        self.assertEqual(m["size"]["x"] + first["region"]["size"]["x"], 24)  # canvas restored
        self.assertEqual(m["size"]["y"] + first["region"]["size"]["y"], 32)
        sf = {a["name"]: a for a in g["spriteframes"]}
        self.assertEqual(sf["run"]["fps"], 10.0)
        self.assertEqual([f["duration"] for f in sf["run"]["frames"]], [1.0] * 6)
        self.assertTrue(all(f["texture"].endswith(".tres") for f in sf["idle"]["frames"]))
        props = {s["params"]["property"]: s["params"]["value"] for s in g["steps"]
                 if s["tool"] == "node_set_property"}
        self.assertEqual(props["offset"], {"x": -12, "y": -32})
        self.assertIn("no op that adds SpriteFrames frames", " ".join(g["notes"]))

    def test_dedupe_shares_pixels(self):
        a = np.zeros((16, 16, 4), np.uint8)
        a[4:12, 4:12] = (10, 20, 30, 255)
        for i in range(3):
            Image.fromarray(a, "RGBA").save(os.path.join(self.root, f"hold_{i}.png"))
        png, data = os.path.join(self.out, "d.png"), os.path.join(self.out, "d.json")
        code, res = run("pack", os.path.join(self.root, "hold_*.png"), "--out", png, "--data",
                        data, "--dedupe", "--trim")
        self.assertEqual(code, 0, res)
        self.assertEqual((res["frames"], res["unique_frames"]), (3, 1))
        code, chk = run("check", data)
        self.assertEqual(code, 0, chk)
        self.assertEqual(chk["distinct_rects"], 1)

    def test_no_frames_fails(self):
        code, res = run("pack", os.path.join(self.root, "nothing_*.png"), "--out",
                        os.path.join(self.out, "x.png"), "--data", os.path.join(self.out, "x.json"))
        self.assertEqual(code, 1)
        self.assertEqual(res["verdict"], "fail")


class Check(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-check-")
        Image.fromarray(np.zeros((64, 64, 4), np.uint8), "RGBA").save(
            os.path.join(self.root, "a.png"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, frames, tags, **meta):
        data = {"frames": frames, "meta": {"image": "a.png", "size": {"w": 64, "h": 64},
                                           "scale": "1", "frameTags": tags, **meta}}
        path = os.path.join(self.root, "a.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return path

    @staticmethod
    def frame(x, y, w=16, h=16, d=100, **kw):
        f = {"filename": f"f{x}_{y}", "frame": {"x": x, "y": y, "w": w, "h": h}, "rotated": False,
             "trimmed": False, "spriteSourceSize": {"x": 0, "y": 0, "w": w, "h": h},
             "sourceSize": {"w": w, "h": h}, "duration": d}
        f.update(kw)
        return f

    def test_valid_aseprite_hash(self):
        data = {"frames": {"a 0.aseprite": self.frame(0, 0), "a 1.aseprite": self.frame(18, 0)},
                "meta": {"image": "a.png", "size": {"w": 64, "h": 64},
                         "frameTags": [{"name": "walk", "from": 0, "to": 1,
                                        "direction": "forward"}]}}
        path = os.path.join(self.root, "h.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        code, res = run("check", path, "--padding", "2")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["min_gap_px"], 2)
        code, res = run("check", path, "--padding", "3")
        self.assertEqual(code, 1)
        self.assertIn("gap", " ".join(res["problems"]))

    def test_catches_broken_sheets(self):
        frames = [self.frame(0, 0), self.frame(8, 8), self.frame(56, 56),
                  self.frame(30, 0, d=0, rotated=True)]
        tags = [{"name": "run", "from": 0, "to": 1, "direction": "forward"},
                {"name": "run", "from": 2, "to": 9, "direction": "sideways"}]
        code, res = run("check", self.write(frames, tags))
        self.assertEqual(code, 1)
        text = " ".join(res["problems"])
        for needle in ("overlapping", "outside", "rotated", "duration", "appears 2 times",
                       "range 2..9", "direction"):
            self.assertIn(needle, text)

    def test_tag_order_and_size_limit(self):
        frames = [self.frame(0, 0), self.frame(20, 0)]
        tags = [{"name": "b", "from": 1, "to": 1}, {"name": "a", "from": 0, "to": 0}]
        code, res = run("check", self.write(frames, tags))
        self.assertEqual(code, 0, res)
        self.assertIn("out of timeline order", " ".join(res["warnings"]))
        code, res = run("check", self.write(frames, tags), "--max-size", "32")
        self.assertEqual(code, 1)
        self.assertIn("--max-size", " ".join(res["problems"]))

    def test_texturepacker_without_durations_or_tags(self):
        frames = [self.frame(0, 0, pivot={"x": 0.5, "y": 1.0}),
                  self.frame(20, 0, pivot={"x": 0.5, "y": 1.0})]
        for f in frames:
            del f["duration"]
        path = self.write(frames, [])
        code, res = run("check", path)
        self.assertEqual(code, 0, res)
        self.assertIn("without duration", " ".join(res["warnings"]))
        code, g = run("godot", path, "--res-dir", "res://x", "--parent", "M", "--fps", "12")
        self.assertEqual(code, 0, g)
        self.assertEqual(g["animations"][0]["name"], "default")
        self.assertEqual(g["animations"][0]["fps"], 12.0)
        self.assertEqual(g["animations"][0]["frames"], 2)

    def test_godot_refuses_failing_sheet(self):
        frames = [self.frame(0, 0), self.frame(8, 8)]
        code, res = run("godot", self.write(frames, []), "--res-dir", "res://x", "--parent", "M")
        self.assertEqual(code, 1)
        self.assertNotIn("steps", res)


class MaxRectsPacking(unittest.TestCase):
    def test_random_rects_no_overlap_and_dense(self):
        rng = random.Random(11)
        sizes = [(rng.randint(4, 40), rng.randint(4, 40)) for _ in range(120)]
        pos, w, h = sheet.pack_rects(sizes, 4096, 4096)
        rects = [(x, y, s[0], s[1]) for (x, y), s in zip(pos, sizes)]
        for i, a in enumerate(rects):
            self.assertTrue(a[0] + a[2] <= w and a[1] + a[3] <= h)
            for b in rects[i + 1:]:
                self.assertFalse(sheet.overlaps(a, b), (a, b))
        fill = sum(s[0] * s[1] for s in sizes) / float(w * h)
        self.assertGreater(fill, 0.75)
        self.assertLess(max(w, h) / min(w, h), 2.0)  # squarest candidate preferred

    def test_pot_and_too_big(self):
        pos, w, h = sheet.pack_rects([(30, 30)] * 4, 4096, 4096, pot=True)
        self.assertEqual((w, h), (64, 64))
        self.assertIsNone(sheet.pack_rects([(100, 10)], 64, 64))

    def test_scene_path_undoes_git_bash(self):
        self.assertEqual(sheet.scene_path("C:/Program Files/Git/Main/Hero"), "/Main/Hero")
        self.assertEqual(sheet.scene_path("Main/Hero/"), "/Main/Hero")


if __name__ == "__main__":
    unittest.main()
