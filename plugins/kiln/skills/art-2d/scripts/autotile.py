"""47-tile blob autotiles, built deterministically and checked seam by seam. Pillow + numpy.

  python autotile.py build <source.png> --tile 16 --out art/tiles/grass [--columns 8]
  python autotile.py check art/tiles/grass/atlas.png --map art/tiles/grass/terrain.json

No AI tool makes a correct 47-tile blob set (research 2026-10-19); this builds one from five
hand-made (or generated and cleaned) source tiles, side by side in one strip, each --tile px:
  1 isolated    the terrain with no neighbours (gives the four outer corners)
  2 vertical    a piece of a north-south strip (left and right edges)
  3 horizontal  a piece of an east-west strip (top and bottom edges)
  4 inner       surrounded on all four sides but not on the diagonals (the four inner corners)
  5 fill        surrounded on all eight sides
Every output tile is put together from four quarter tiles: each quarter (top-left, top-right,
bottom-left, bottom-right) is copied from the same quarter of the source that matches its two
sides and diagonal (both sides + diagonal: fill; both sides, no diagonal: inner; only the
vertical side: vertical; only the horizontal side: horizontal; neither: isolated). A corner
neighbour counts only when both sides next to it are terrain, which leaves 47 distinct masks.
build   writes <out>/atlas.png (47 tiles, --columns per row) and <out>/terrain.json: per tile its
        atlas cell and its 8 neighbour bits (n, ne, e, se, s, sw, w, nw), for Godot's
        TERRAIN_MODE_MATCH_CORNERS_AND_SIDES (godot_terrain.gd applies them through the run-once
        editor route) or any engine's 8-bit rule tile.
check   every pair of tiles that may sit side by side (east/west and north/south, by their
        masks) must continue across the shared edge: the colour step across it no larger than
        twice the steps beside it inside the tiles (+ --tolerance) on all but 1/8 of the rows,
        and the terrain outline in alpha continuing - the seam test that AI-made sets fail. Also: 47 distinct masks present, every tile the same size, no empty tile.
JSON report; exit 1 on fail.
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

BITS = ("n", "ne", "e", "se", "s", "sw", "w", "nw")
SOURCES = ("isolated", "vertical", "horizontal", "inner", "fill")


def canonical(mask):
    """Drop corner bits whose two sides are not both set (they cannot change the tile)."""
    m = dict(mask)
    for corner, a, b in (("ne", "n", "e"), ("se", "s", "e"), ("sw", "s", "w"), ("nw", "n", "w")):
        if not (m[a] and m[b]):
            m[corner] = 0
    return m


def all_masks():
    seen, out = set(), []
    for v in range(256):
        m = canonical({b: (v >> i) & 1 for i, b in enumerate(BITS)})
        key = tuple(m[b] for b in BITS)
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


def mask_at(grid, r, c):
    """The canonical mask of the cell at row r, column c of a terrain grid (1 = terrain)."""
    g = lambda dr, dc: grid[r + dr][c + dc]  # noqa: E731
    return canonical({"n": g(-1, 0), "ne": g(-1, 1), "e": g(0, 1), "se": g(1, 1),
                      "s": g(1, 0), "sw": g(1, -1), "w": g(0, -1), "nw": g(-1, -1)})


def neighbour_pairs():
    """Every (direction, mask of a, mask of b) two terrain tiles can show side by side, found by
    painting every 3x4 (east-west) and 4x3 (north-south) patch of terrain around them. Comparing
    canonical bits directly missed most pairs (bug hunt 2026-10-20: 47 of 169 east-west pairs),
    because a canonical corner reads 0 whenever one of its sides is 0."""
    key = lambda m: tuple(m[b] for b in BITS)  # noqa: E731
    pairs = set()
    for rows, cols, a, b, direction in ((3, 4, (1, 1), (1, 2), "east-west"),
                                        (4, 3, (1, 1), (2, 1), "north-south")):
        free = [(r, c) for r in range(rows) for c in range(cols) if (r, c) not in (a, b)]
        for v in range(1 << len(free)):
            grid = [[1] * cols for _ in range(rows)]
            for i, (r, c) in enumerate(free):
                grid[r][c] = (v >> i) & 1
            pairs.add((direction, key(mask_at(grid, *a)), key(mask_at(grid, *b))))
    return sorted(pairs)


def quarter_source(side_v, side_h, diag):
    if side_v and side_h:
        return "fill" if diag else "inner"
    if side_v:
        return "vertical"
    if side_h:
        return "horizontal"
    return "isolated"


def build_tile(src, mask, t):
    h = t // 2
    tile = np.zeros_like(src["fill"])
    quarters = {  # (rows, cols, vertical side, horizontal side, diagonal)
        "tl": (slice(0, h), slice(0, h), mask["n"], mask["w"], mask["nw"]),
        "tr": (slice(0, h), slice(h, t), mask["n"], mask["e"], mask["ne"]),
        "bl": (slice(h, t), slice(0, h), mask["s"], mask["w"], mask["sw"]),
        "br": (slice(h, t), slice(h, t), mask["s"], mask["e"], mask["se"]),
    }
    for rows, cols, v, hz, d in quarters.values():
        tile[rows, cols] = src[quarter_source(v, hz, d)][rows, cols]
    return tile


def cmd_build(a):
    img = np.asarray(Image.open(a.source).convert("RGBA"))
    t = a.tile
    if t % 2 or img.shape[0] != t or img.shape[1] < 5 * t:
        raise SystemExit(f"the source must be a strip of 5 tiles of {t} px (even), "
                         f"{' / '.join(SOURCES)}; got {img.shape[1]}x{img.shape[0]}")
    src = {name: img[:, i * t:(i + 1) * t] for i, name in enumerate(SOURCES)}
    masks = all_masks()
    cols = a.columns
    rows = -(-len(masks) // cols)
    atlas = np.zeros((rows * t, cols * t, 4), np.uint8)
    tiles = []
    for i, m in enumerate(masks):
        x, y = i % cols, i // cols
        atlas[y * t:(y + 1) * t, x * t:(x + 1) * t] = build_tile(src, m, t)
        tiles.append({"atlas": [x, y], **m})
    os.makedirs(a.out, exist_ok=True)
    Image.fromarray(atlas).save(os.path.join(a.out, "atlas.png"))
    data = {"format": "kiln-autotile/1", "tile": t, "columns": cols, "layout": "blob47",
            "bits": list(BITS), "tiles": tiles}
    with open(os.path.join(a.out, "terrain.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    return {"out": a.out.replace("\\", "/"), "tiles": len(tiles), "atlas": [cols * t, rows * t]}, 0


def cmd_check(a):
    with open(a.map, encoding="utf-8") as fh:
        data = json.load(fh)
    t = int(data["tile"])
    img = np.asarray(Image.open(a.atlas).convert("RGBA")).astype(int)
    tiles = []
    problems = []
    for entry in data["tiles"]:
        x, y = entry["atlas"]
        px = img[y * t:(y + 1) * t, x * t:(x + 1) * t]
        if px.shape[:2] != (t, t):
            problems.append(f"tile at {x},{y} lies outside the atlas")
            continue
        if not px[..., 3].any():
            problems.append(f"tile at {x},{y} is empty")
        tiles.append(({b: int(entry[b]) for b in BITS}, (x, y), px))
    keys = {tuple(m[b] for b in BITS) for m, _, _ in tiles}
    if len(keys) != len(tiles) or len(keys) != 47:
        problems.append(f"{len(keys)} distinct masks in {len(tiles)} tiles (a blob set has 47)")
    def broken(last2, first2):
        """A seam is broken when the step across it is clearly larger than the steps next to it
        inside the tiles (the texture or the edge line does not continue), or when the terrain
        outline in alpha does not continue (more than one row differs)."""
        across = np.abs(last2[1] - first2[0]).max(axis=-1)
        inside = np.maximum(np.abs(last2[1] - last2[0]).max(axis=-1),
                            np.abs(first2[1] - first2[0]).max(axis=-1))
        jumps = int((across > inside * 2 + a.tolerance).sum())
        alpha = int(((last2[1][:, 3] > 127) != (first2[0][:, 3] > 127)).sum())
        return jumps > max(1, len(across) // 8) or alpha > 1

    by_key = {tuple(m[b] for b in BITS): (c, p) for m, c, p in tiles}
    seams, bad = 0, []
    for direction, ka, kb in neighbour_pairs():
        if ka not in by_key or kb not in by_key:
            continue  # a mask missing from the set is reported above
        (ca, pa), (cb, pb) = by_key[ka], by_key[kb]
        seams += 1
        if direction == "east-west" and broken((pa[:, -2], pa[:, -1]), (pb[:, 0], pb[:, 1])):
            bad.append(f"{ca} | {cb} (east-west)")
        if direction == "north-south" and broken((pa[-2], pa[-1]), (pb[0], pb[1])):
            bad.append(f"{ca} / {cb} (north-south)")
    if bad:
        problems.append(f"{len(bad)} of {seams} seams do not match, e.g. {', '.join(bad[:5])}")
    verdict = "fail" if problems else "pass"
    return {"tiles": len(tiles), "seams_checked": seams, "seams_broken": len(bad),
            "problems": problems, "verdict": verdict}, 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("source")
    b.add_argument("--tile", type=int, required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--columns", type=int, default=8)
    c = sub.add_parser("check")
    c.add_argument("atlas")
    c.add_argument("--map", required=True)
    c.add_argument("--tolerance", type=int, default=24, help="extra step allowed across a seam (0-255)")
    a = ap.parse_args(argv)
    try:
        out, code = globals()["cmd_" + a.cmd](a)
    except SystemExit as e:
        if isinstance(e.code, int):
            raise
        print(json.dumps({"error": str(e.code), "verdict": "fail"}))
        return 1
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(out, indent=1))
    return code


if __name__ == "__main__":
    sys.exit(main())
