"""2D map image -> deduplicated tileset + Tiled JSON map. Pillow + numpy, run with Bash.

  python tiles.py extract <map.png> --tile 16 [--tile-height 16] [--flips] [--tolerance 0]
         [--columns 16] --out <folder>

extract  cuts the image into a grid of tiles, keeps one copy of each distinct tile and writes
         <out>/tileset.png (the unique tiles, row by row), <out>/map.tmj (Tiled JSON, orthogonal,
         one tile layer "ground", the tileset embedded with firstgid 1) and prints a JSON report.
         --flips   a tile that is a mirrored copy of a kept one (horizontal, vertical or both = 180
                   degrees) is stored once and placed with Tiled's flip flags (GID bit 31 = H,
                   bit 30 = V), as Tiled, Godot's Tiled importers and LDtk read them.
         --tolerance N  tiles whose channels differ by at most N (0-255) count as the same tile:
                   JPEG or resized references are never pixel-exact (try 4-8).
         The image must be a whole number of tiles; otherwise nothing is written.
Output: JSON with "verdict", "unique", "cells", "reuse" (cells per unique tile); exit 1 on fail.
"""

import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image

FLIP_H, FLIP_V = 0x80000000, 0x40000000


def cut(img, tw, th):
    rows, cols = img.shape[0] // th, img.shape[1] // tw
    return [[img[r * th:(r + 1) * th, c * tw:(c + 1) * tw] for c in range(cols)]
            for r in range(rows)], cols, rows


def variants(t, flips):
    """(tile as stored, flag) pairs a kept tile can be placed as."""
    out = [(t, 0)]
    if flips:
        out += [(t[:, ::-1], FLIP_H), (t[::-1, :], FLIP_V), (t[::-1, ::-1], FLIP_H | FLIP_V)]
    return out


def same(a, b, tolerance):
    if tolerance <= 0:
        return np.array_equal(a, b)
    return int(np.abs(a.astype(np.int16) - b.astype(np.int16)).max()) <= tolerance


def extract(a):
    img = np.asarray(Image.open(a.image).convert("RGBA"))
    tw, th = a.tile, a.tile_height or a.tile
    h, w = img.shape[:2]
    if w % tw or h % th:
        return {"verdict": "fail", "problems": [
            f"{w}x{h} is not a whole number of {tw}x{th} tiles (crop or rescale the reference "
            "to the tile grid first)"]}, 1
    grid, cols, rows = cut(img, tw, th)
    unique, exact, data = [], {}, []
    for row in grid:
        for t in row:
            gid = None
            if a.tolerance <= 0 and t.tobytes() in exact:
                gid = exact[t.tobytes()]
            else:
                for i, kept in enumerate(unique):
                    flag = next((f for v, f in variants(kept, a.flips) if same(t, v, a.tolerance)),
                                None)
                    if flag is not None:
                        gid = (i + 1) | flag
                        break
            if gid is None:
                unique.append(t)
                gid = len(unique)
                for v, f in variants(t, a.flips):
                    exact.setdefault(np.ascontiguousarray(v).tobytes(), gid | f)
            data.append(gid)
    columns = a.columns or max(1, math.ceil(math.sqrt(len(unique))))
    sheet_rows = math.ceil(len(unique) / columns)
    sheet = np.zeros((sheet_rows * th, columns * tw, 4), np.uint8)
    for i, t in enumerate(unique):
        r, c = divmod(i, columns)
        sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = t
    os.makedirs(a.out, exist_ok=True)
    Image.fromarray(sheet, "RGBA").save(os.path.join(a.out, "tileset.png"))
    tmj = {"type": "map", "version": "1.10", "tiledversion": "1.12.2",
           "orientation": "orthogonal", "renderorder": "right-down", "infinite": False,
           "width": cols, "height": rows, "tilewidth": tw, "tileheight": th,
           "nextlayerid": 2, "nextobjectid": 1,
           "layers": [{"id": 1, "name": "ground", "type": "tilelayer", "x": 0, "y": 0,
                       "width": cols, "height": rows, "opacity": 1, "visible": True,
                       "data": data}],
           "tilesets": [{"firstgid": 1, "name": "tileset", "image": "tileset.png",
                         "imagewidth": columns * tw, "imageheight": sheet_rows * th,
                         "tilewidth": tw, "tileheight": th, "tilecount": len(unique),
                         "columns": columns, "margin": 0, "spacing": 0}]}
    with open(os.path.join(a.out, "map.tmj"), "w", encoding="utf-8") as fh:
        json.dump(tmj, fh)
    return {"verdict": "pass", "unique": len(unique), "cells": len(data),
            "reuse": round(len(data) / len(unique), 2), "map": [cols, rows], "tile": [tw, th],
            "flipped_cells": sum(1 for g in data if g & (FLIP_H | FLIP_V)),
            "files": [os.path.join(a.out, "tileset.png"), os.path.join(a.out, "map.tmj")]}, 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("image")
    e.add_argument("--tile", type=int, required=True)
    e.add_argument("--tile-height", type=int)
    e.add_argument("--flips", action="store_true")
    e.add_argument("--tolerance", type=int, default=0)
    e.add_argument("--columns", type=int)
    e.add_argument("--out", required=True)
    a = ap.parse_args()
    res, code = extract(a)
    print(json.dumps(res, indent=1))
    sys.exit(code)


if __name__ == "__main__":
    main()
