"""Objective checks for 2D game art. Normal Python (Pillow + numpy), run with Bash.

  python sprite_qa.py palette art/sprites/*.png --palette art/palette.hex [--max-colors 32]
  python sprite_qa.py alpha art/sprites/*.png
  python sprite_qa.py mixels production/captures/T12/run.png --scale 3
  python sprite_qa.py silhouettes art/enemies/grunt.png art/enemies/brute.png --max-iou 0.75
  python sprite_qa.py palette art/rug/chart.png --bits 3 --palette art/palette.hex [--max-distance 40]
  python sprite_qa.py contrast art/hero.png --bg production/captures/T12/level1_bg.png --min 3
         [--gate edge|worst|mean]
  python sprite_qa.py clusters art/sprites/*.png [--max-orphans 0] [--max-gaps 0]
  python sprite_qa.py frames art/hero/run_*.png --baseline-tol 1

palette      colours used vs the project palette (.hex one colour per line, .gpl, or a palette
             PNG); out-of-palette pixels must be 0, colour count within --max-colors
alpha        pixel art uses only alpha 0 or 255; counts semi-transparent pixels; a fully opaque image
             with a grey checkerboard painted round the edges fails (fake transparency)
mixels       an in-game capture at integer scale k must consist of k x k single-colour blocks;
             searches the grid offset, reports the fraction of broken blocks (mixed pixel sizes,
             sub-pixel positions, rotation or filtering show up here)
silhouettes  pairwise silhouette IoU after fitting to the same height: different enemy types must
             read differently in silhouette alone
             --bits N: every colour on an N-bit-per-channel hardware grid (+-1); with --palette
             also each colour's nearest palette colour and RGB distance (--max-distance gate)
contrast     WCAG contrast against the background: gate `edge` (default) = the silhouette edge
             pixels (the outline), `worst` = every colour region with >= 2% of the pixels, `mean`
             = the whole sprite's mean luminance; all three are reported
clusters     orphan pixels (no 8-neighbour of the same colour) and outline gaps (edge pixels that
             are not the most common edge colour: the fill leaking through the outline)
frames       animation frames: same canvas size, and the lowest opaque row (the feet) on the same
             baseline within --baseline-tol px for grounded animations
Output: JSON with a verdict per check; exit code 1 if any fails.
"""

import argparse
import glob
import itertools
import json
import sys

import numpy as np
from PIL import Image



def expand(patterns):
    """Expand glob patterns here: Windows shells pass them through unexpanded."""
    out = []
    for p in patterns:
        hits = sorted(glob.glob(p, recursive=True)) if any(c in p for c in "*?[") else [p]
        out.extend(hits or [p])
    return out

def rgba(path):
    return np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8)


def load_palette(path):
    if path.lower().endswith((".png", ".gif", ".bmp")):
        px = rgba(path).reshape(-1, 4)
        return {tuple(int(v) for v in p[:3]) for p in px if p[3] > 0}
    colours = set()
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith(("#", ";", "GIMP", "Name:", "Columns:")) and \
                    not (s.startswith("#") and len(s) in (7, 9)):
                continue
            if s.startswith("#") or (len(s) in (6, 8) and all(c in "0123456789abcdefABCDEF"
                                                              for c in s)):
                h = s.lstrip("#")
                colours.add(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)))
            else:
                parts = s.split()
                if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                    colours.add(tuple(int(p) for p in parts[:3]))
    return colours


def hexc(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c)


def on_grid(c, bits):
    """True if every channel is a level of a `bits`-per-channel hardware palette (±1 for the
    rounding of 255 / (2^bits - 1) steps; e.g. Mega Drive 3 bits: 0, 36, 73, ..., 255)."""
    top = (1 << bits) - 1
    return all(abs(v - round(round(v * top / 255) * 255 / top)) <= 1 for v in c)


def check_palette(paths, palette_path, max_colors, bits=0, max_distance=None):
    pal = load_palette(palette_path) if palette_path else None
    results = []
    for path in paths:
        px = rgba(path).reshape(-1, 4)
        opaque = px[px[:, 3] > 0][:, :3]
        used = {tuple(int(v) for v in c) for c in np.unique(opaque, axis=0)} if len(opaque) else set()
        problems = []
        out_px = 0
        extra = {}
        if bits:
            off = sorted(c for c in used if not on_grid(c, bits))
            extra["off_grid_colors"] = len(off)
            if off:
                problems.append(f"{len(off)} colours are not on the {bits}-bit-per-channel "
                                f"hardware grid (e.g. {', '.join(hexc(c) for c in off[:5])}): "
                                "snap them")
        if pal is not None:
            # Distance of each used colour to its nearest palette colour (RGB, 0..441): the
            # number to report when a hardware palette forces colours off the art bible.
            pal_arr = np.array(sorted(pal), float)
            dists = []
            for c in sorted(used):
                d = np.sqrt(((pal_arr - np.array(c, float)) ** 2).sum(1))
                i = int(d.argmin())
                dists.append({"color": hexc(c), "nearest": hexc(pal_arr[i]),
                              "distance": round(float(d[i]), 1)})
            extra["distances"] = dists
        if pal is not None and max_distance is not None:
            far = [d for d in extra["distances"] if d["distance"] > max_distance]
            if far:
                problems.append(f"{len(far)} colours further than {max_distance} from the "
                                f"palette (e.g. {far[0]['color']} -> {far[0]['nearest']} "
                                f"{far[0]['distance']})")
        elif pal is not None:
            outside = used - pal
            if outside:
                mask = np.array([tuple(int(v) for v in c) in outside for c in opaque])
                out_px = int(mask.sum())
                sample = ["#%02x%02x%02x" % c for c in list(outside)[:5]]
                problems.append(f"{out_px} px in {len(outside)} colours outside the palette "
                                f"(e.g. {', '.join(sample)})")
        if max_colors and len(used) > max_colors:
            problems.append(f"{len(used)} colours > {max_colors}")
        results.append({"file": path, "colours": len(used), "out_of_palette_px": out_px,
                        **extra, "problems": problems, "verdict": "fail" if problems else "pass"})
    return results


def painted_checkerboard(img):
    """Cell size of a grey checkerboard painted where a transparent background should be (image
    models asked for transparency sometimes paint one: research 2026-10-19), or 0."""
    h, w = img.shape[:2]
    b = max(4, min(h, w) // 12)
    band = np.zeros((h, w), bool)
    band[:b], band[-b:], band[:, :b], band[:, -b:] = True, True, True, True
    rgb = img[..., :3].astype(int)
    grey = (rgb.max(-1) - rgb.min(-1)) < 16
    if grey[band].mean() < 0.85:
        return 0
    lum = rgb.mean(-1)
    lo, hi = np.percentile(lum[band], 5), np.percentile(lum[band], 95)
    if hi - lo < 12:
        return 0
    bright = lum > (lo + hi) / 2
    ys, xs = np.nonzero(band)
    for p in (4, 5, 6, 8, 10, 12, 16, 20, 24, 32):
        for ox in range(p):
            for oy in (0, p // 2):
                pattern = (((xs + ox) // p + (ys + oy) // p) % 2).astype(bool)
                agree = (pattern == bright[ys, xs]).mean()
                if agree > 0.92 or agree < 0.08:
                    return p
    return 0


def check_alpha(paths):
    results = []
    for path in paths:
        img = rgba(path)
        a = img[..., 3]
        semi = int(((a > 0) & (a < 255)).sum())
        problems = [f"{semi} semi-transparent px (pixel art: alpha 0 or 255)"] if semi else []
        fake = painted_checkerboard(img) if (a == 255).all() else 0
        if fake:
            problems.append(f"no transparency: a {fake}-px grey checkerboard is painted where the "
                            "background should be transparent (an image model's fake "
                            "transparency) - cut the background out and check alpha in code")
        results.append({"file": path, "semi_transparent_px": semi, "painted_checkerboard": fake,
                        "verdict": "fail" if problems else "pass", "problems": problems})
    return results


def check_mixels(path, scale, max_broken):
    img = rgba(path)[..., :3].astype(np.int32)
    best = None
    for oy, ox in itertools.product(range(scale), range(scale)):
        h = (img.shape[0] - oy) // scale * scale
        w = (img.shape[1] - ox) // scale * scale
        if h <= 0 or w <= 0:
            continue
        blocks = img[oy:oy + h, ox:ox + w].reshape(h // scale, scale, w // scale, scale, 3)
        spread = (blocks.max(axis=(1, 3)) - blocks.min(axis=(1, 3))).max(axis=-1)
        broken = float((spread > 2).mean())  # tolerance for capture compression noise
        if best is None or broken < best[0]:
            best = (broken, ox, oy)
    broken, ox, oy = best
    problems = []
    if broken > max_broken:
        problems.append(f"{broken:.2%} of {scale}x{scale} blocks are not single-colour: mixed "
                        "pixel sizes, sub-pixel positions, rotation or texture filtering")
    return [{"file": path, "scale": scale, "grid_offset": [ox, oy],
             "broken_block_fraction": round(broken, 4), "threshold": max_broken,
             "problems": problems, "verdict": "fail" if problems else "pass"}]


def fitted_mask(path, height=128):
    a = rgba(path)[..., 3] >= 128
    ys, xs = np.nonzero(a)
    crop = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = crop.shape
    nw = max(1, round(w * height / h))
    img = Image.fromarray((crop * 255).astype(np.uint8)).resize((nw, height), Image.NEAREST)
    return np.asarray(img) >= 128


def check_silhouettes(paths, max_iou):
    masks = {p: fitted_mask(p) for p in paths}
    pairs, problems = [], []
    for a, b in itertools.combinations(paths, 2):
        ma, mb = masks[a], masks[b]
        width = max(ma.shape[1], mb.shape[1])
        pa = np.zeros((128, width), bool)
        pb = np.zeros((128, width), bool)
        pa[:, (width - ma.shape[1]) // 2:(width - ma.shape[1]) // 2 + ma.shape[1]] = ma
        pb[:, (width - mb.shape[1]) // 2:(width - mb.shape[1]) // 2 + mb.shape[1]] = mb
        iou = float((pa & pb).sum() / max(1, (pa | pb).sum()))
        pairs.append({"a": a, "b": b, "iou": round(iou, 3)})
        if iou > max_iou:
            problems.append(f"{a} and {b} silhouettes overlap {iou:.2f} > {max_iou}: "
                            "the types will be confused at a glance")
    return [{"pairs": pairs, "threshold": max_iou, "problems": problems,
             "verdict": "fail" if problems else "pass"}]


def luminance(rgb):
    c = rgb / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c @ np.array([0.2126, 0.7152, 0.0722])


def edge_mask(alpha):
    """Opaque pixels with a transparent 4-neighbour or on the canvas border: the silhouette edge
    (an outline when the sprite has one)."""
    a = alpha > 0
    p = np.pad(a, 1, constant_values=False)
    inner = p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return a & ~inner


def contrast_of(y1, y2):
    hi, lo = max(y1, y2), min(y1, y2)
    return float((hi + 0.05) / (lo + 0.05))


def check_contrast(path, bg, minimum, gate="edge", min_share=0.02):
    img = rgba(path)
    px = img.reshape(-1, 4)
    opaque = px[px[:, 3] > 0][:, :3]
    fg = luminance(opaque.astype(float)).mean()
    if bg.startswith("#"):
        h = bg.lstrip("#")
        back = luminance(np.array([[int(h[i:i + 2], 16) for i in (0, 2, 4)]], float))[0]
    else:
        bpx = rgba(bg).reshape(-1, 4)
        back = luminance(bpx[bpx[:, 3] > 0][:, :3].astype(float)).mean()
    edge = edge_mask(img[..., 3])
    edge_y = luminance(img[edge][:, :3].astype(float)).mean()
    colours, counts = np.unique(opaque, axis=0, return_counts=True)
    regions = []
    for c, n in sorted(zip(colours.tolist(), counts.tolist()), key=lambda cn: -cn[1]):
        share = n / len(opaque)
        if share >= min_share:
            r = contrast_of(luminance(np.array([c], float))[0], back)
            regions.append({"color": hexc(c), "share": round(share, 3), "contrast": round(r, 2)})
    mean_r, edge_r = contrast_of(fg, back), contrast_of(edge_y, back)
    problems = []
    if gate == "mean" and mean_r < minimum:
        problems.append(f"mean contrast {mean_r:.2f}:1 < {minimum}:1")
    elif gate == "edge" and edge_r < minimum:
        problems.append(f"silhouette edge contrast {edge_r:.2f}:1 < {minimum}:1: the sprite "
                        "does not separate from this background (outline or value)")
    elif gate == "worst":
        bad = [r for r in regions if r["contrast"] < minimum]
        if bad:
            problems.append(f"region {bad[0]['color']} ({bad[0]['share']:.0%}) contrast "
                            f"{bad[0]['contrast']}:1 < {minimum}:1" +
                            (f" (+{len(bad) - 1} more)" if len(bad) > 1 else ""))
    return [{"file": path, "bg": bg, "gate": gate, "contrast": round(mean_r, 2),
             "edge_contrast": round(edge_r, 2), "regions": regions, "threshold": minimum,
             "problems": problems, "verdict": "fail" if problems else "pass"}]


def check_clusters(path, max_orphans, max_gaps):
    """Pixel-cluster cleanliness: orphans (an opaque pixel with no 8-neighbour of its colour) and
    outline gaps (silhouette-edge pixels that are not the outline colour, i.e. the fill leaks
    through the outline). The outline colour is the most common edge colour."""
    img = rgba(path)
    rgb = img[..., :3].astype(np.int32)
    key = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]
    opaque = img[..., 3] > 0
    key = np.where(opaque, key, -1)
    p = np.pad(key, 1, constant_values=-2)
    same = np.zeros(key.shape, bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                same |= p[1 + dy:1 + dy + key.shape[0], 1 + dx:1 + dx + key.shape[1]] == key
    orphans = opaque & ~same
    edge = edge_mask(img[..., 3])
    gaps, outline = 0, None
    if edge.any():
        vals, counts = np.unique(key[edge], return_counts=True)
        outline = int(vals[counts.argmax()])
        gaps = int((edge & (key != outline)).sum())
    problems = []
    n_orph = int(orphans.sum())
    if n_orph > max_orphans:
        ys, xs = np.nonzero(orphans)
        problems.append(f"{n_orph} orphan pixels (e.g. x={xs[0]}, y={ys[0]}): single pixels of "
                        "a colour read as noise")
    if gaps > max_gaps:
        problems.append(f"{gaps} silhouette-edge pixels are not the outline colour "
                        f"{hexc(((outline >> 16) & 255, (outline >> 8) & 255, outline & 255))}: "
                        "the fill leaks through the outline")
    return [{"file": path, "orphans": n_orph, "outline_gaps": gaps,
             "outline_color": None if outline is None else hexc(
                 ((outline >> 16) & 255, (outline >> 8) & 255, outline & 255)),
             "problems": problems, "verdict": "fail" if problems else "pass"}]


def check_frames(paths, tol):
    sizes, baselines = set(), []
    for path in paths:
        a = rgba(path)[..., 3]
        sizes.add(a.shape)
        rows = np.nonzero(a.max(axis=1) > 0)[0]
        baselines.append(int(rows.max()) if len(rows) else -1)
    problems = []
    if len(sizes) > 1:
        problems.append(f"frame canvases differ: {sorted(sizes)} (use one fixed canvas per "
                        "animation so the pivot does not jump)")
    spread = max(baselines) - min(baselines) if baselines else 0
    if spread > tol:
        problems.append(f"feet baseline moves {spread} px across frames (> {tol}); fine for "
                        "jumps, wrong for grounded cycles")
    return [{"frames": len(paths), "baselines": baselines, "problems": problems,
             "verdict": "fail" if problems else "pass"}]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("palette")
    p.add_argument("files", nargs="+")
    p.add_argument("--palette", default=None)
    p.add_argument("--max-colors", type=int, default=64)
    p.add_argument("--bits", type=int, default=0,
                   help="hardware palette bits per channel (Mega Drive 3); 0 = no grid check")
    p.add_argument("--max-distance", type=float, default=None,
                   help="with --palette: allowed RGB distance to the nearest palette colour")
    a = sub.add_parser("alpha")
    a.add_argument("files", nargs="+")
    m = sub.add_parser("mixels")
    m.add_argument("file")
    m.add_argument("--scale", type=int, required=True)
    m.add_argument("--max-broken", type=float, default=0.002)
    s = sub.add_parser("silhouettes")
    s.add_argument("files", nargs="+")
    s.add_argument("--max-iou", type=float, default=0.75)
    c = sub.add_parser("contrast")
    c.add_argument("file")
    c.add_argument("--bg", required=True, help="background image or #rrggbb")
    c.add_argument("--min", type=float, default=3.0)
    c.add_argument("--gate", choices=("edge", "worst", "mean"), default="edge",
                   help="edge: silhouette edge vs background; worst: every colour region")
    k = sub.add_parser("clusters")
    k.add_argument("files", nargs="+")
    k.add_argument("--max-orphans", type=int, default=0)
    k.add_argument("--max-gaps", type=int, default=0)
    f = sub.add_parser("frames")
    f.add_argument("files", nargs="+")
    f.add_argument("--baseline-tol", type=int, default=1)
    args = parser.parse_args(argv)
    if hasattr(args, "files"):
        args.files = expand(args.files)
    if args.cmd == "palette":
        results = check_palette(args.files, args.palette, args.max_colors, args.bits,
                                args.max_distance)
    elif args.cmd == "alpha":
        results = check_alpha(args.files)
    elif args.cmd == "mixels":
        results = check_mixels(args.file, args.scale, args.max_broken)
    elif args.cmd == "silhouettes":
        results = check_silhouettes(args.files, args.max_iou)
    elif args.cmd == "contrast":
        results = check_contrast(args.file, args.bg, args.min, args.gate)
    elif args.cmd == "clusters":
        results = [r for f in args.files for r in check_clusters(f, args.max_orphans,
                                                                 args.max_gaps)]
    else:
        results = check_frames(args.files, args.baseline_tol)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(results if len(results) > 1 else results[0], indent=1))
    sys.exit(0 if all(r["verdict"] == "pass" for r in results) else 1)


if __name__ == "__main__":
    main()
