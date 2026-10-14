"""Fidelity to a reference image, in numbers: values, light pools, tones, palette, per region.
numpy + Pillow.

  python ref_compare.py report --ref ref/plaza.png --ours cap/plaza.png
         [--scale 2] [--region lamp:100,80,40,30 ...] [--points window:45,55;grass:10,110]
  python ref_compare.py side --ref ... --ours ... --region house:30,40,40,40 --out cap/side
  python ref_compare.py lowfreq | tones | palette --ref ... --ours ...

Coordinates are reference pixels; --scale is our capture's pixels per reference pixel (default:
our width / the reference's width). Our capture is resampled onto the reference for the numbers.
side     each region magnified (nearest, >= 4x) from both images, side by side, rulers every 10
         reference pixels: scale, layout and line read off the same grid.
lowfreq  values and light pools: the mean linear luminance per grid cell (--grid 8 cells across),
         ours / reference; FAIL when a cell is off by more than --ratio (1.25, about a third of
         a photographic stop) either way. The worst cells are listed.
tones    colours at given points: in a small patch (--patch 3 px radius) the colours at the 10th,
         50th and 90th luminance percentiles, CIE76 delta E (Lab); FAIL above --max-de (10).
palette  the reference's main colours (k-means in Lab, --colours 8): the share of our pixels
         within --max-de of one of them (FAIL below --min-near 0.8), reference colours we
         barely use (missing ramps) and our main colours far from all of them (unused/foreign).
report   all of it, plus each --region ranked by mismatch (brightness ratio and palette
         distance), worst first. Verdict FAIL if values, palette or tones fail.
Output: JSON; exit 1 on FAIL.
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw


def rgb(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)


def linear(a):
    c = a / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luminance(a):
    lin = linear(a)
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def lab(a):
    """sRGB 0..255 (..., 3) -> CIE L*a*b* (D65)."""
    lin = linear(a)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def pair(a):
    ref = rgb(a.ref)
    ours_img = Image.open(a.ours).convert("RGB")
    scale = a.scale or ours_img.width / ref.shape[1]
    ours = np.asarray(ours_img.resize((ref.shape[1], ref.shape[0]), Image.BOX), dtype=np.float64)
    return ref, ours, ours_img, scale


def parse_regions(specs):
    out = []
    for spec in specs or []:
        name, _, box = spec.partition(":")
        x, y, w, h = (int(v) for v in box.split(","))
        out.append((name, x, y, w, h))
    return out


def parse_points(spec):
    out = []
    for item in (spec or "").split(";"):
        if item.strip():
            name, _, xy = item.partition(":")
            x, y = (int(v) for v in xy.split(","))
            out.append((name.strip(), x, y))
    return out


def lowfreq(ref, ours, a):
    h, w = ref.shape[:2]
    cols = a.grid
    rows = max(1, round(cols * h / w))
    ly, lo = luminance(ref), luminance(ours)
    cells, off = [], []
    for r in range(rows):
        for c in range(cols):
            ys, ye = r * h // rows, (r + 1) * h // rows
            xs, xe = c * w // cols, (c + 1) * w // cols
            mr, mo = ly[ys:ye, xs:xe].mean(), lo[ys:ye, xs:xe].mean()
            ratio = float((mo + 1e-4) / (mr + 1e-4))
            cell = {"cell": [c, r], "box": [xs, ys, xe - xs, ye - ys], "ratio": round(ratio, 3)}
            cells.append(cell)
            if not (1 / a.ratio <= ratio <= a.ratio):
                off.append(cell)
    off.sort(key=lambda c: -abs(np.log(c["ratio"])))
    return {"verdict": "FAIL" if off else "PASS", "threshold": a.ratio, "grid": [cols, rows],
            "cells_off": len(off), "worst": off[:6],
            "map": [[c["ratio"] for c in cells[r * cols:(r + 1) * cols]] for r in range(rows)]}


def percentile_colours(patch):
    flat = patch.reshape(-1, 3)
    order = np.argsort(luminance(flat))
    return [flat[order[min(len(order) - 1, int(q * (len(order) - 1)))]] for q in (0.1, 0.5, 0.9)]


def tones(ref, ours, a):
    rows, worst = [], 0.0
    for name, x, y in parse_points(a.points):
        r = a.patch
        pr = ref[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
        po = ours[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1]
        if not pr.size:
            rows.append({"name": name, "verdict": "NOT ASSESSED", "note": "outside the image"})
            continue
        des = [float(np.linalg.norm(lab(c1) - lab(c2)))
               for c1, c2 in zip(percentile_colours(pr), percentile_colours(po))]
        de = max(des)
        worst = max(worst, de)
        rows.append({"name": name, "at": [x, y], "delta_e": round(de, 2),
                     "p10_p50_p90_delta_e": [round(d, 2) for d in des],
                     "ref_median": [int(v) for v in percentile_colours(pr)[1]],
                     "ours_median": [int(v) for v in percentile_colours(po)[1]],
                     "verdict": "PASS" if de <= a.max_de else "FAIL"})
    failed = any(r["verdict"] == "FAIL" for r in rows)
    return {"verdict": "FAIL" if failed else ("PASS" if rows else "NOT ASSESSED"),
            "threshold": a.max_de, "points": rows, "worst_delta_e": round(worst, 2)}


def kmeans(points, k, iters=20):
    """Lab points (n, 3) -> (centres (k, 3), shares (k,)); deterministic seeding by lightness."""
    order = np.argsort(points[:, 0])
    centres = points[order[np.linspace(0, len(points) - 1, k).astype(int)]].copy()
    for _ in range(iters):
        label = np.argmin(((points[:, None, :] - centres[None]) ** 2).sum(-1), axis=1)
        for j in range(k):
            if (label == j).any():
                centres[j] = points[label == j].mean(axis=0)
    label = np.argmin(((points[:, None, :] - centres[None]) ** 2).sum(-1), axis=1)
    shares = np.bincount(label, minlength=k) / len(points)
    keep = shares > 0
    return centres[keep], shares[keep]


def sample(img, n=20000):
    flat = lab(img.reshape(-1, 3))
    step = max(1, len(flat) // n)
    return flat[::step]


def palette(ref, ours, a):
    pr, po = sample(ref), sample(ours)
    centres, shares = kmeans(pr, a.colours)
    dist = np.sqrt(((po[:, None, :] - centres[None]) ** 2).sum(-1))
    nearest, dmin = dist.argmin(axis=1), dist.min(axis=1)
    near_share = float((dmin <= a.max_de).mean())
    use = np.bincount(nearest[dmin <= a.max_de], minlength=len(centres)) / len(po)
    missing = [{"lab": [round(float(v), 1) for v in centres[j]], "ref_share": round(float(shares[j]), 3),
                "our_share": round(float(use[j]), 3)}
               for j in range(len(centres)) if shares[j] >= 0.02 and use[j] < 0.25 * shares[j]]
    oc, osh = kmeans(po, a.colours)
    far = np.sqrt(((oc[:, None, :] - centres[None]) ** 2).sum(-1)).min(axis=1)
    foreign = [{"lab": [round(float(v), 1) for v in oc[j]], "our_share": round(float(osh[j]), 3),
                "delta_e_to_ref": round(float(far[j]), 1)}
               for j in range(len(oc)) if osh[j] >= 0.02 and far[j] > a.max_de]
    ok = near_share >= a.min_near and not missing
    return {"verdict": "PASS" if ok else "FAIL", "near_share": round(near_share, 3),
            "threshold": a.min_near, "max_de": a.max_de, "missing": missing, "foreign": foreign,
            "ref_palette": [{"lab": [round(float(v), 1) for v in c], "share": round(float(s), 3)}
                            for c, s in zip(centres, shares)]}


def regions(ref, ours, a):
    out = []
    for name, x, y, w, h in parse_regions(a.region):
        r, o = ref[y:y + h, x:x + w], ours[y:y + h, x:x + w]
        if not r.size:
            continue
        ratio = float((luminance(o).mean() + 1e-4) / (luminance(r).mean() + 1e-4))
        centres, _ = kmeans(sample(r, 4000), min(4, a.colours))
        po = sample(o, 4000)
        dmin = np.sqrt(((po[:, None, :] - centres[None]) ** 2).sum(-1)).min(axis=1)
        near = float((dmin <= a.max_de).mean())
        score = abs(float(np.log(ratio))) + (1 - near)
        out.append({"name": name, "box": [x, y, w, h], "brightness_ratio": round(ratio, 3),
                    "palette_near_share": round(near, 3), "mismatch": round(score, 3)})
    return sorted(out, key=lambda r: -r["mismatch"])


def side(ref, ours_img, scale, a):
    os.makedirs(a.out, exist_ok=True)
    files = []
    ref_img = Image.fromarray(ref.astype(np.uint8))
    for name, x, y, w, h in parse_regions(a.region):
        mag = max(4, 320 // max(w, h))
        size = (w * mag, h * mag)
        rc = ref_img.crop((x, y, x + w, y + h)).resize(size, Image.NEAREST)
        oc = ours_img.crop((round(x * scale), round(y * scale), round((x + w) * scale),
                            round((y + h) * scale))).resize(size, Image.NEAREST)
        pad, gap = 14, 12
        canvas = Image.new("RGB", (2 * size[0] + gap + 2 * pad, size[1] + 2 * pad), (24, 24, 24))
        draw = ImageDraw.Draw(canvas)
        for i, crop in enumerate((rc, oc)):
            ox = pad + i * (size[0] + gap)
            canvas.paste(crop, (ox, pad))
            for t in range(0, w + 1, 10):          # rulers every 10 reference pixels
                draw.line([(ox + t * mag, pad - 6), (ox + t * mag, pad - 1)], fill=(230, 230, 230))
            for t in range(0, h + 1, 10):
                draw.line([(ox - 6, pad + t * mag), (ox - 1, pad + t * mag)], fill=(230, 230, 230))
        path = os.path.join(a.out, f"{name}_side.png")
        canvas.save(path)
        files.append(path)
    return {"verdict": "PASS" if files else "NOT ASSESSED", "files": files, "scale": scale}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("report", "side", "lowfreq", "tones", "palette"):
        p = sub.add_parser(name)
        p.add_argument("--ref", required=True)
        p.add_argument("--ours", required=True)
        p.add_argument("--scale", type=float, help="our pixels per reference pixel")
        p.add_argument("--region", action="append", help="name:x,y,w,h in reference pixels")
        p.add_argument("--points", help="name:x,y;name:x,y in reference pixels")
        p.add_argument("--grid", type=int, default=8)
        p.add_argument("--ratio", type=float, default=1.25)
        p.add_argument("--patch", type=int, default=3)
        p.add_argument("--max-de", type=float, default=10.0)
        p.add_argument("--colours", type=int, default=8)
        p.add_argument("--min-near", type=float, default=0.8)
        p.add_argument("--out", default=os.path.join("production", "captures", "ref_compare"))
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    ref, ours, ours_img, scale = pair(a)
    if a.cmd == "side":
        res = side(ref, ours_img, scale, a)
    elif a.cmd == "lowfreq":
        res = lowfreq(ref, ours, a)
    elif a.cmd == "tones":
        res = tones(ref, ours, a)
    elif a.cmd == "palette":
        res = palette(ref, ours, a)
    else:
        res = {"scale": round(scale, 4), "values": lowfreq(ref, ours, a),
               "palette": palette(ref, ours, a), "tones": tones(ref, ours, a),
               "regions": regions(ref, ours, a)}
        failed = any(res[k]["verdict"] == "FAIL" for k in ("values", "palette", "tones"))
        res["verdict"] = "FAIL" if failed else "PASS"
    print(json.dumps(res, indent=1))
    sys.exit(1 if res.get("verdict") == "FAIL" else 0)


if __name__ == "__main__":
    main()
