"""Tests for art-2d autotile.py (47-tile blob sets built from five source tiles, seams checked) and
godot_terrain.gd (the set as a Godot terrain: a real headless Godot paints a shape with
set_cells_terrain_connect and must pick, for every cell, the tile whose mask matches its
neighbours; skipped without Godot)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from test_probe_base import GODOT  # noqa: E402

SCRIPTS = os.path.join(HERE, "..", "plugins", "kiln", "skills", "art-2d", "scripts")
AUTOTILE = os.path.join(SCRIPTS, "autotile.py")
T = 16
GRASS, EDGE = (70, 160, 60, 255), (60, 40, 20, 255)


def sources(path):
    """isolated, vertical, horizontal, inner, fill - grass with a 2-px dirt rim where the terrain
    ends (all five tile with each other, as a hand-drawn set would)."""
    strip = np.zeros((T, 5 * T, 4), np.uint8)
    for i in range(5):
        tile = np.zeros((T, T, 4), np.uint8)
        tile[:] = GRASS
        tile[::2, ::2, 1] = 150                            # a tileable texture
        if i in (0, 1):
            tile[:, :2] = EDGE
            tile[:, -2:] = EDGE
        if i in (0, 2):
            tile[:2, :] = EDGE
            tile[-2:, :] = EDGE
        if i == 3:
            for ys in (slice(0, 2), slice(T - 2, T)):
                for xs in (slice(0, 2), slice(T - 2, T)):
                    tile[ys, xs] = EDGE
        strip[:, i * T:(i + 1) * T] = tile
    Image.fromarray(strip).save(path)


def run(*args):
    p = subprocess.run([sys.executable, "-B", AUTOTILE, *args], capture_output=True, text=True,
                       timeout=120)
    return p.returncode, json.loads(p.stdout)


class Autotile(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="kiln-auto-")
        self.src = os.path.join(self.d, "src.png")
        sources(self.src)
        self.out = os.path.join(self.d, "grass")
        code, out = run("build", self.src, "--tile", str(T), "--out", self.out)
        self.assertEqual((code, out["tiles"]), (0, 47), out)

    def test_built_set_has_47_masks_and_clean_seams(self):
        code, out = run("check", os.path.join(self.out, "atlas.png"), "--map",
                        os.path.join(self.out, "terrain.json"))
        self.assertEqual((code, out["verdict"]), (0, "pass"), out)
        self.assertGreater(out["seams_checked"], 50)

    def test_a_misplaced_tile_breaks_seams(self):
        path = os.path.join(self.out, "terrain.json")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        fill = next(t for t in data["tiles"] if all(t[b] for b in data["bits"]))
        lone = next(t for t in data["tiles"] if not any(t[b] for b in data["bits"]))
        fill["atlas"], lone["atlas"] = lone["atlas"], fill["atlas"]   # the map points wrong
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        code, out = run("check", os.path.join(self.out, "atlas.png"), "--map", path)
        self.assertEqual(code, 1, out)
        self.assertGreater(out["seams_broken"], 0)

    def test_bad_source_strip_is_refused(self):
        code, out = run("build", os.path.join(self.out, "atlas.png"), "--tile", "15", "--out",
                        os.path.join(self.d, "x"))
        self.assertEqual(code, 1)

    @unittest.skipUnless(GODOT, "no Godot found (set KILN_GODOT)")
    def test_godot_terrain_picks_the_matching_tile(self):
        proj = os.path.join(self.d, "proj")
        os.makedirs(proj)
        with open(os.path.join(proj, "project.godot"), "w", encoding="utf-8") as fh:
            fh.write('config_version=5\n\n[application]\nconfig/name="terrain"\n')
        for name in ("atlas.png", "terrain.json"):
            shutil.copy(os.path.join(self.out, name), proj)
        shutil.copy(os.path.join(SCRIPTS, "godot_terrain.gd"), proj)
        shape = ["#######.",
                 "#.#####.",
                 "#######.",
                 "..####..",
                 "..#..###",
                 "..####.."]
        cells = [[x, y] for y, row in enumerate(shape) for x, ch in enumerate(row) if ch == "#"]
        with open(os.path.join(proj, "check.gd"), "w", encoding="utf-8") as fh:
            fh.write('extends SceneTree\n'
                     'func _init():\n'
                     '\tvar T = load("res://godot_terrain.gd")\n'
                     '\tvar ts: TileSet = T.build("res://atlas.png", "res://terrain.json", "grass")\n'
                     '\tvar layer := TileMapLayer.new()\n'
                     '\tlayer.tile_set = ts\n'
                     '\troot.add_child(layer)\n'
                     '\tvar cells: Array[Vector2i] = []\n'
                     f'\tfor c in {json.dumps(cells)}:\n'
                     '\t\tcells.append(Vector2i(c[0], c[1]))\n'
                     '\tlayer.set_cells_terrain_connect(cells, 0, 0)\n'
                     '\tvar out := {}\n'
                     '\tfor c in cells:\n'
                     '\t\tvar a := layer.get_cell_atlas_coords(c)\n'
                     '\t\tout["%d,%d" % [c.x, c.y]] = [a.x, a.y]\n'
                     '\tprint("KILN:" + JSON.stringify(out))\n'
                     '\tquit()\n')
        p = subprocess.run([GODOT, "--headless", "--path", proj, "--script", "res://check.gd"],
                           capture_output=True, text=True, timeout=120)
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("KILN:")), None)
        self.assertIsNotNone(line, p.stdout[-1500:] + p.stderr[-1500:])
        picked = json.loads(line[5:])
        with open(os.path.join(self.out, "terrain.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        by_mask = {tuple(t[b] for b in data["bits"]): tuple(t["atlas"]) for t in data["tiles"]}
        filled = {(x, y) for x, y in cells}
        offsets = {"n": (0, -1), "ne": (1, -1), "e": (1, 0), "se": (1, 1), "s": (0, 1),
                   "sw": (-1, 1), "w": (-1, 0), "nw": (-1, -1)}
        wrong = []
        for x, y in cells:
            m = {b: int((x + dx, y + dy) in filled) for b, (dx, dy) in offsets.items()}
            for corner, a, b in (("ne", "n", "e"), ("se", "s", "e"), ("sw", "s", "w"),
                                 ("nw", "n", "w")):
                if not (m[a] and m[b]):
                    m[corner] = 0
            want = by_mask[tuple(m[b] for b in data["bits"])]
            if tuple(picked[f"{x},{y}"]) != want:
                wrong.append((x, y, picked[f"{x},{y}"], want))
        self.assertEqual(wrong, [])


if __name__ == "__main__":
    unittest.main()
