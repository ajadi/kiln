"""Measure a character silhouette from silhouette_shot.py (PNG + sidecar JSON). Pillow + numpy;
runs outside Blender, so builder and reviewer use one tool, one definition per metric, on the same
capture (g2 rows 64, 76, 87, 88).

  python silhouette_measure.py contour front.png --side max --z 1.10 1.50
  python silhouette_measure.py deltoid front.png --side max --fit 1.15 1.24 --peak 1.30 1.40 --top 1.45
  python silhouette_measure.py chord-angle front.png --a 0.20 0.32 --b 0.06 0.16
  python silhouette_measure.py width front.png --z 1.40
  python silhouette_measure.py gap front.png --z 0.95 1.25
  python silhouette_measure.py holes front.png [--min-px 6]

World units are metres from the sidecar (px/m, the world point at the image centre, which world
axis runs left to right). z is height; h is the horizontal world coordinate of the view.

contour      outer contour of one side (--side max = the larger h, e.g. the character's left in
             the front view): h per row between --z limits.
deltoid      the shoulder-arm contour read as anatomy, not as a tube: fit a line to the outer
             contour over --fit (upper arm below the deltoid insertion), then report
               deviation_cm  largest distance of the contour outside that line within --peak
                             (deltoid convexity; ~0 = a straight tube, g2 merchants -1.4..0 cm),
               corner_deg    largest change of contour direction between consecutive 2 cm
                             contour steps from the bottom of --fit up to --top (a corner at the
                             shoulder point reads as a ball joint),
               peak_z_m      height of the largest deviation.
chord-angle  the angle between two chords of the top contour (highest z per column) over h
             ranges --a and --b, e.g. the raised arm's top line and the trapezius chord (the "V
             angle": defined here once, so builder and reviewer get the same number).
width        silhouette width at height --z (e.g. bideltoid at shoulder height) and the minimum
             width of a part between --z0 and --z1 (`--min-between`), e.g. the wrist.
gap          per row, background runs enclosed left and right by the figure (between arm and
             torso, between the thighs); reports the smallest gap and where it closes (0 = contact).
holes        background regions fully enclosed by the figure: see-through slits at wrists, necks,
             ankles, a garment ending above a boot. Each with its z range and size.
Output: JSON; exit 0 (metrics are reported, thresholds belong to the review table).
"""

import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image


def load(png):
    side = os.path.splitext(png)[0] + ".json"
    with open(side, encoding="utf-8") as fh:
        meta = json.load(fh)
    a = np.asarray(Image.open(png).convert("L"))
    mask = a < 128                              # figure is black on white
    h, w = mask.shape
    ppm = float(meta["px_per_m"])
    ch, cz = meta["center_world"]
    sign = meta.get("h_sign", 1)
    hs = ch + sign * (np.arange(w) + 0.5 - w / 2) / ppm
    zs = cz + (h / 2 - np.arange(h) - 0.5) / ppm
    return mask, hs, zs, ppm, meta


def contour(mask, hs, zs, side, z0, z1):
    pick = np.argmax if side == "max" else np.argmin
    out_z, out_h = [], []
    for r in range(mask.shape[0]):
        if not (z0 <= zs[r] <= z1) or not mask[r].any():
            continue
        cols = np.nonzero(mask[r])[0]
        vals = hs[cols]
        out_z.append(float(zs[r]))
        out_h.append(float(vals[pick(vals)]))
    order = np.argsort(out_z)
    return np.array(out_z)[order], np.array(out_h)[order]


def cmd_contour(a, m):
    mask, hs, zs, ppm, meta = m
    z, h = contour(mask, hs, zs, a.side, a.z[0], a.z[1])
    step = max(1, len(z) // 60)
    return {"metric": "contour", "side": a.side,
            "points": [[round(float(zz), 4), round(float(hh), 4)] for zz, hh in
                       zip(z[::step], h[::step])]}


def cmd_deltoid(a, m):
    mask, hs, zs, ppm, meta = m
    z, h = contour(mask, hs, zs, a.side, a.fit[0], a.top)
    sel = (z >= a.fit[0]) & (z <= a.fit[1])
    if sel.sum() < 3:
        return {"metric": "deltoid", "error": "no contour inside --fit"}
    b, c = np.polyfit(z[sel], h[sel], 1)
    out = 1.0 if a.side == "max" else -1.0
    dev = out * (h - (c + b * z)) * math.cos(math.atan(abs(b)))
    pk = (z >= a.peak[0]) & (z <= a.peak[1])
    i = int(np.argmax(np.where(pk, dev, -np.inf)))
    # direction change per 2 cm of contour length
    pts = np.stack([h, z], 1)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    grid = np.arange(0, s[-1], 0.02)
    gh, gz = np.interp(grid, s, h), np.interp(grid, s, z)
    ang = np.degrees(np.arctan2(np.diff(gz), np.diff(gh)))
    turn = np.abs((np.diff(ang) + 180) % 360 - 180) if len(ang) > 1 else np.array([0.0])
    j = int(np.argmax(turn))
    return {"metric": "deltoid", "side": a.side, "fit_line_slope": round(float(b), 4),
            "deviation_cm": round(float(dev[i]) * 100, 2), "peak_z_m": round(float(z[i]), 4),
            "corner_deg": round(float(turn[j]), 1),
            "corner_z_m": round(float(gz[min(j + 1, len(gz) - 1)]), 4),
            "definition": "deviation: contour outside the --fit line within --peak; corner: max "
                          "direction change between 2 cm contour steps"}


def top_contour(mask, hs, zs):
    out_h, out_z = [], []
    for col in range(mask.shape[1]):
        rows = np.nonzero(mask[:, col])[0]
        if len(rows):
            out_h.append(float(hs[col]))
            out_z.append(float(zs[rows.min()]))
    order = np.argsort(out_h)
    return np.array(out_h)[order], np.array(out_z)[order]


def cmd_chord_angle(a, m):
    mask, hs, zs, ppm, meta = m
    h, z = top_contour(mask, hs, zs)

    def chord(lo, hi):
        sel = (h >= min(lo, hi)) & (h <= max(lo, hi))
        if sel.sum() < 2:
            raise SystemExit(f"no top contour between {lo} and {hi}")
        b, _ = np.polyfit(h[sel], z[sel], 1)
        return math.degrees(math.atan(b))

    ta, tb = chord(*a.a), chord(*a.b)
    # angle of the V opening upward between the two lines
    v = 180.0 - abs(ta - tb)
    return {"metric": "chord_angle", "line_a_deg": round(ta, 1), "line_b_deg": round(tb, 1),
            "v_angle_deg": round(v, 1),
            "definition": "180 - |slope angle a - slope angle b| of least-squares chords of the "
                          "top contour over the two h ranges"}


def cmd_width(a, m):
    mask, hs, zs, ppm, meta = m
    out = {"metric": "width"}
    if a.z is not None:
        r = int(np.argmin(np.abs(zs - a.z)))
        cols = np.nonzero(mask[r])[0]
        out["width_m"] = round(float(np.ptp(hs[cols]) + 1 / ppm), 4) if len(cols) else 0.0
        out["z_m"] = round(float(zs[r]), 4)
    if a.min_between:
        z0, z1 = a.min_between
        best = None
        for r in np.nonzero((zs >= z0) & (zs <= z1))[0]:
            n = int(mask[r].sum())
            if n and (best is None or n < best[0]):
                best = (n, zs[r])
        if best:
            out["min_width_m"] = round(best[0] / ppm, 4)
            out["min_width_z_m"] = round(float(best[1]), 4)
    return out


def cmd_gap(a, m):
    mask, hs, zs, ppm, meta = m
    rows = []
    for r in np.nonzero((zs >= a.z[0]) & (zs <= a.z[1]))[0]:
        cols = np.nonzero(mask[r])[0]
        if len(cols) < 2:
            continue
        runs = np.diff(cols) - 1
        inner = runs[runs > 0]
        rows.append((float(zs[r]), int(inner.min()) if len(inner) else 0))
    if not rows:
        return {"metric": "gap", "error": "no figure rows in range"}
    closed = [z for z, g in rows if g == 0]
    smallest = min(rows, key=lambda t: t[1])
    return {"metric": "gap", "min_gap_m": round(smallest[1] / ppm, 4),
            "min_gap_z_m": round(smallest[0], 4),
            "contact_rows": len(closed),
            "contact_z_range_m": [round(min(closed), 4), round(max(closed), 4)] if closed else None}


def cmd_holes(a, m):
    mask, hs, zs, ppm, meta = m
    h, w = mask.shape
    outside = np.zeros_like(mask)
    stack = [(r, c) for r in range(h) for c in (0, w - 1)] + \
            [(r, c) for c in range(w) for r in (0, h - 1)]
    while stack:
        r, c = stack.pop()
        if outside[r, c] or mask[r, c]:
            continue
        outside[r, c] = True
        for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if 0 <= nr < h and 0 <= nc < w and not outside[nr, nc] and not mask[nr, nc]:
                stack.append((nr, nc))
    enclosed = ~mask & ~outside
    seen = np.zeros_like(mask)
    holes = []
    for r, c in np.argwhere(enclosed):
        if seen[r, c]:
            continue
        comp, stack = [], [(r, c)]
        seen[r, c] = True
        while stack:
            cr, cc = stack.pop()
            comp.append((cr, cc))
            for nr, nc in ((cr + 1, cc), (cr - 1, cc), (cr, cc + 1), (cr, cc - 1)):
                if 0 <= nr < h and 0 <= nc < w and enclosed[nr, nc] and not seen[nr, nc]:
                    seen[nr, nc] = True
                    stack.append((nr, nc))
        if len(comp) < a.min_px:
            continue
        rr = [p[0] for p in comp]
        cc = [p[1] for p in comp]
        holes.append({"pixels": len(comp),
                      "z_range_m": [round(float(zs[max(rr)]) - 0.5 / ppm, 4),
                                    round(float(zs[min(rr)]) + 0.5 / ppm, 4)],
                      "h_range_m": [round(float(min(hs[min(cc)], hs[max(cc)])), 4),
                                    round(float(max(hs[min(cc)], hs[max(cc)])), 4)]})
    holes.sort(key=lambda x: -x["pixels"])
    return {"metric": "holes", "count": len(holes), "holes": holes}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("contour"); p.add_argument("png")
    p.add_argument("--side", choices=("max", "min"), default="max")
    p.add_argument("--z", type=float, nargs=2, required=True)
    p = sub.add_parser("deltoid"); p.add_argument("png")
    p.add_argument("--side", choices=("max", "min"), default="max")
    p.add_argument("--fit", type=float, nargs=2, required=True)
    p.add_argument("--peak", type=float, nargs=2, required=True)
    p.add_argument("--top", type=float, required=True)
    p = sub.add_parser("chord-angle"); p.add_argument("png")
    p.add_argument("--a", type=float, nargs=2, required=True)
    p.add_argument("--b", type=float, nargs=2, required=True)
    p = sub.add_parser("width"); p.add_argument("png")
    p.add_argument("--z", type=float)
    p.add_argument("--min-between", type=float, nargs=2)
    p = sub.add_parser("gap"); p.add_argument("png")
    p.add_argument("--z", type=float, nargs=2, required=True)
    p = sub.add_parser("holes"); p.add_argument("png")
    p.add_argument("--min-px", type=int, default=6)
    a = ap.parse_args()
    m = load(a.png)
    fn = {"contour": cmd_contour, "deltoid": cmd_deltoid, "chord-angle": cmd_chord_angle,
          "width": cmd_width, "gap": cmd_gap, "holes": cmd_holes}[a.cmd]
    res = fn(a, m)
    res.update({"file": a.png, "view": m[4].get("view"), "px_per_m": m[3]})
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
