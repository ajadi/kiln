"""Turn generated "pixel art" into real pixel art: find the pixel grid, one colour per cell, a
small palette, hard alpha. Pillow + numpy.

  python pixelfix.py snap gen/hero_ai.png --out art/sprites/hero.png [--colors 8]
         [--palette art/palette.hex] [--scale auto|N] [--preview 4]
  python pixelfix.py grid gen/hero_ai.png              # only report the detected grid

Image models draw pixel art at a large size with soft edges, blocks of uneven size, extra
colours and grey fringes (research 2026-10-19: a practitioner's 6-colour keyframes came back with
30-60 colours). snap:
  1 grid    the block size and offset per axis: the one where colour steps between neighbouring
            columns (rows) line up on the block borders far better than inside the blocks
            (--scale N skips the search)
  2 cells   one colour per block - the most common colour of its opaque pixels; a block is
            transparent when most of its pixels are
  3 palette --palette (.hex, .gpl or a palette PNG: every colour mapped to its nearest) or
            --colors N (k-means, seeded on the most distinct colours, no dithering)
  4 alpha   0 or 255 only
Writes the sprite at its true size (and a nearest-neighbour preview at --preview x). Then
sprite_qa.py palette / alpha / clusters, and a contact sheet of all frames at game speed.
Report JSON: grid, size, colours before and after; exit 1 when no grid is found.
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image


def step_energy(img, axis, threshold=40):
    """How many rows (columns) have a clear colour or alpha step between neighbouring columns
    (rows): counts, not magnitudes, so a strong outline does not outweigh the colour borders
    inside the sprite."""
    rgb = img[..., :3].astype(int)
    a = img[..., 3].astype(int)
    d = np.abs(np.diff(rgb, axis=axis)).sum(axis=-1) + np.abs(np.diff(a, axis=axis))
    if axis == 0:
        d = d.T                                    # rows of steps along the axis we measure
    # a soft (blurred) edge spreads one step over two or three positions: keep its peak only
    left = np.pad(d, ((0, 0), (1, 0)))[:, :-1]
    right = np.pad(d, ((0, 0), (0, 1)))[:, 1:]
    peak = (d > threshold) & (d >= left) & (d > right)
    return peak.sum(axis=0).astype(float)          # one value per border position


def find_grid(energy, max_scale=64):
    """(scale, offset, excess): the grid whose borders hold the most step energy beyond what
    the same number of random positions would hold. A divisor of the true block size also
    catches every border but adds empty lines; a multiple misses half of them - both score
    lower. Soft edges are reduced to their peak step first (step_energy)."""
    n = len(energy)
    total = energy.sum()
    best = (1, 0, 0.0)
    if total <= 0:
        return best
    for s in range(2, min(max_scale, (n + 1) // 2) + 1):
        for o in range(s):
            near = np.zeros(n, bool)
            near[np.arange((o - 1) % s, n, s)] = True
            excess = energy[near].sum() / total - near.mean()
            if excess > best[2]:
                best = (s, o, excess)
    return best


def load_palette(path):
    if path.lower().endswith(".png"):
        img = np.asarray(Image.open(path).convert("RGB")).reshape(-1, 3)
        return np.unique(img, axis=0)
    cols = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.strip().split()
            if path.lower().endswith(".gpl"):
                if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                    cols.append([int(p) for p in parts[:3]])
            elif parts:
                h = parts[0].lstrip("#")
                if len(h) >= 6:
                    cols.append([int(h[i:i + 2], 16) for i in (0, 2, 4)])
    return np.array(cols)


def spans(size, scale, offset):
    """Block (start, end) pairs along one axis; a partial block at either end narrower than half
    a block is margin, not a pixel."""
    cuts = sorted({0, size} | set(range(offset % scale, size, scale)))
    return [(a, b) for a, b in zip(cuts, cuts[1:]) if b - a >= scale / 2]


def cell_colours(img, sx, ox, sy, oy):
    h, w = img.shape[:2]
    xspans, yspans = spans(w, sx, ox), spans(h, sy, oy)
    out = np.zeros((len(yspans), len(xspans), 4), np.uint8)
    for j, (y0, y1) in enumerate(yspans):
        for i, (x0, x1) in enumerate(xspans):
            block = img[y0:y1, x0:x1].reshape(-1, 4)
            opaque = block[block[:, 3] >= 128]
            if len(opaque) * 2 < len(block):
                continue
            q = (opaque[:, :3] // 8).astype(int)
            keys, counts = np.unique(q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2], return_counts=True)
            top = keys[counts.argmax()]
            mask = (q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]) == top
            out[j, i, :3] = opaque[mask, :3].mean(axis=0).round().astype(np.uint8)
            out[j, i, 3] = 255
    # a partial block at the edge that came out empty is margin around the art, not a pixel
    if yspans and yspans[-1][1] - yspans[-1][0] < sy and not out[-1, :, 3].any():
        out = out[:-1]
    if yspans and yspans[0][1] - yspans[0][0] < sy and not out[0, :, 3].any():
        out = out[1:]
    if xspans and xspans[-1][1] - xspans[-1][0] < sx and not out[:, -1, 3].any():
        out = out[:, :-1]
    if xspans and xspans[0][1] - xspans[0][0] < sx and not out[:, 0, 3].any():
        out = out[:, 1:]
    return out


def kmeans(cols, k, iterations=30):
    """k colour centres, seeded deterministically: the most common colour, then each next seed
    the colour farthest from the seeds so far (a small palette keeps its distinct hues)."""
    uniq, counts = np.unique((cols // 8).astype(int), axis=0, return_counts=True)
    centres = [uniq[counts.argmax()] * 8.0 + 4]
    while len(centres) < min(k, len(uniq)):
        d = np.min([((cols - c) ** 2).sum(1) for c in centres], axis=0)
        centres.append(cols[d.argmax()])
    centres = np.array(centres, float)
    for _ in range(iterations):
        idx = ((cols[:, None, :] - centres[None]) ** 2).sum(-1).argmin(1)
        moved = np.array([cols[idx == i].mean(0) if (idx == i).any() else centres[i]
                          for i in range(len(centres))])
        if np.allclose(moved, centres):
            break
        centres = moved
    return centres


def colours_in(img):
    px = img.reshape(-1, 4)
    px = px[px[:, 3] > 0]
    return len(np.unique(px[:, :3], axis=0))


def cmd_grid(a, img):
    sx, ox, cx = (a.scale, 0, 0.0) if a.scale else find_grid(step_energy(img, 1))
    sy, oy, cy = (a.scale, 0, 0.0) if a.scale else find_grid(step_energy(img, 0))
    return {"scale": [int(sx), int(sy)], "offset": [int(ox), int(oy)],
            "excess": [round(float(cx), 3), round(float(cy), 3)],
            "found": bool(sx > 1 and sy > 1 and (a.scale or min(cx, cy) >= 0.1))}


def cmd_snap(a, img):
    g = cmd_grid(a, img)
    if not g["found"]:
        return {"grid": g, "verdict": "fail",
                "problem": "no pixel grid found: not upscaled pixel art (or give --scale)"}, 1
    (sx, sy), (ox, oy) = g["scale"], g["offset"]
    cells = cell_colours(img, sx, ox, sy, oy)
    before = colours_in(img)
    if a.palette:
        pal = load_palette(a.palette)
        flat = cells[..., :3].reshape(-1, 1, 3).astype(int)
        idx = ((flat - pal[None, :, :]) ** 2).sum(-1).argmin(-1)
        cells[..., :3] = pal[idx].reshape(cells.shape[:2] + (3,))
    elif a.colors:
        opaque = cells[..., 3] >= 128
        cols = cells[..., :3][opaque].astype(float)
        if len(cols):
            centres = kmeans(cols, a.colors)
            idx = ((cols[:, None, :] - centres[None]) ** 2).sum(-1).argmin(1)
            cells[..., :3][opaque] = centres[idx].round().astype(np.uint8)
    cells[..., 3] = np.where(cells[..., 3] >= 128, 255, 0)
    cells[cells[..., 3] == 0] = 0
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    Image.fromarray(cells).save(a.out)
    out = {"grid": g, "size": [cells.shape[1], cells.shape[0]], "colours_before": before,
           "colours_after": colours_in(cells), "out": a.out.replace("\\", "/"), "verdict": "pass"}
    if a.preview:
        prev = os.path.splitext(a.out)[0] + f"_x{a.preview}.png"
        Image.fromarray(cells).resize((cells.shape[1] * a.preview, cells.shape[0] * a.preview),
                                      Image.NEAREST).save(prev)
        out["preview"] = prev.replace("\\", "/")
    return out, 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("snap", "grid"):
        p = sub.add_parser(name)
        p.add_argument("image")
        p.add_argument("--scale", type=int, default=0)
        if name == "snap":
            p.add_argument("--out", required=True)
            p.add_argument("--colors", type=int, default=0)
            p.add_argument("--palette")
            p.add_argument("--preview", type=int, default=0)
    a = ap.parse_args(argv)
    img = np.asarray(Image.open(a.image).convert("RGBA"))
    if a.cmd == "grid":
        out, code = cmd_grid(a, img), 0
    else:
        out, code = cmd_snap(a, img)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(out, indent=1))
    return code


if __name__ == "__main__":
    sys.exit(main())
