"""Hair / beard / brow card atlas: generate it, and check an existing one. numpy + Pillow; runs
outside Blender (load the PNGs into the cards material afterwards).

  python card_atlas.py make --out art/source/npc/tex --tag goran --dark 1a1410 --base 3b2a20 \
      --light 8a7060 --root 0e0a08 [--light-frac 0.08] [--seed 0] [--size 1024]
  python card_atlas.py check art/source/npc/tex/T_goran_cards_albedo.png [--max-light-edge 0.01]

make   writes T_<tag>_cards_albedo.png (RGBA, straight alpha), _normal.png and _orm.png.
       Layout (size S): four strand tiles side by side in the top 3/4 (S/4 x 3S/4 each: 0 soft lock,
       1 straight dense, 2 wavy for beards, 3 wisp with short staggered tips) and a "mass strip"
       across the bottom 1/4: periodic in u (runs around the head), v from the shell's boundary
       (ragged strands) to its interior (opaque). UVs: tile k spans u in [k/4, (k+1)/4] and v in
       [1/4, 1] (v = 1 root ... tip toward 1/4); the strip spans v in [0, 1/4]; keep a 3 texel inset.
       Strands: clumped (sub-clumps converge mid-length), tapered alpha tips with staggered ends,
       ragged roots, root-to-tip value ramp, a share `--light-frac` of lighter strands (grey in a
       dark beard), and every texel's colour - also under alpha 0 - dilated from the nearest
       strand, so mip-maps never pull in a white or grey fill.
check  the bug that turned a black beard silver at distance and drew white dashes along every
       strand (g2 rows 57, 115): semi-transparent texels lighter than the strands' p99 value, and
       the fill colour under alpha 0. Fails when the share of light edge texels > --max-light-edge
       or the transparent fill is far from the strand colours.

Ported from the g2 project's hairkit.py (TASK-020 rework 2), the recipe that passed its 5-view,
two-shot and 3 m checks on five characters. The mesh side (mass shells, clump ribbons, staggered
rows, brows) is in the skill's references/characters.md.
Output: JSON; exit 1 when `check` fails.
"""

import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image

KINDS = [
    dict(n=44, spread=0.88, root=0.80, amp=5.0, cyc=0.55, w0=6.5, tip=(0.70, 1.0), clumps=3, seed=3),
    dict(n=48, spread=0.86, root=0.86, amp=2.0, cyc=0.35, w0=6.0, tip=(0.78, 1.0), clumps=2, seed=5),
    dict(n=40, spread=0.90, root=0.78, amp=8.0, cyc=1.10, w0=6.5, tip=(0.64, 1.0), clumps=3, seed=8),
    dict(n=26, spread=0.90, root=0.75, amp=4.0, cyc=0.50, w0=5.5, tip=(0.40, 1.0), clumps=2, seed=11),
]


def ss(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def strand_layer(W, H, rs, lanes, k, cols, light_frac, wrap=False, base_fill=None, ramp=0.45,
                 contrast=1.0):
    """Strands into (H, W) arrays; row 0 = tip side (tiles) / boundary side (strip)."""
    x = (np.arange(W, dtype=np.float32) + 0.5)[None, :]
    yv = (np.arange(H, dtype=np.float32) + 0.5)[:, None] / H
    t = 1.0 - yv
    cover = np.zeros((H, W), np.float32)
    hgt = np.zeros((H, W), np.float32)
    rgb = np.ones((H, W, 3), np.float32) * np.array(cols["dark"], np.float32)
    tone_map = np.zeros((H, W), np.float32)
    n = len(lanes)
    spacing = (W if wrap else W * k["spread"]) / n
    cl_c = rs.uniform(-0.6, 0.6, size=max(k.get("clumps", 1), 1)) * \
        (W * k["spread"] * 0.5 if not wrap else 0)
    for i, lane in enumerate(lanes):
        amp = k["amp"] * rs.uniform(0.5, 1.3)
        ph = rs.uniform(0, 2 * np.pi)
        cyc = k["cyc"] * rs.uniform(0.75, 1.25)
        t_end = rs.uniform(*k["tip"])
        if not wrap:
            t_end *= 1.0 - 0.35 * abs(lane) ** 2          # edge strands shorter: no card outline
            sp = (k["root"] + (1.0 - k["root"]) * ss(0.0, 0.8, t)) * (W * k["spread"] * 0.5)
            x0 = W * 0.5 + lane * sp
            cc = W * 0.5 + cl_c[i % len(cl_c)]
            pull = 0.38 * ss(0.15, 0.85, t) * ss(1.0, 0.85, t)   # sub-clumps converge
            xc = x0 + (cc - x0) * pull + amp * np.sin(2 * np.pi * cyc * t + ph) * \
                (0.2 + 0.8 * ss(0, 0.5, t))
        else:
            xc = lane + amp * np.sin(2 * np.pi * cyc * t + ph) * ss(0.0, 0.6, t)
        wr = rs.uniform(0.75, 1.25) * k["w0"] * (spacing / 8.0) ** 0.5
        taper = (1.0 - ss(0.30 * t_end, t_end, t)) ** 0.85
        wid = np.maximum(wr * taper * (1.25 - 0.25 * ss(0.0, 0.3, t)), 0.0)
        d = np.abs(x - xc)
        if wrap:
            d = np.minimum(d, W - d)
        fade = 1.0 - ss(0.88 * t_end, t_end, t)
        if not wrap:                                       # ragged roots
            t0 = rs.uniform(0.0, 0.16)
            fade = fade * ss(t0, t0 + 0.07, t)
        cv = np.clip((wid * 0.5 - d) / 1.1 + 0.5, 0.0, 1.0) * fade * (t <= t_end)
        prof = np.sqrt(np.clip(1.0 - (d / (wid * 0.5 + 1e-6)) ** 2, 0.0, 1.0))
        h = cv * prof * rs.uniform(0.85, 1.15)
        win = h > hgt
        hgt = np.where(win, h, hgt)
        tone = rs.uniform(0.0, 1.0)
        light = rs.uniform(0, 1) < light_frac
        c = np.array(cols["base"], np.float32)
        if light:
            c = c + (np.array(cols["light"], np.float32) - c) * rs.uniform(0.55, 0.95)
        else:
            c = c + (np.array(cols["dark"], np.float32) - c) * max(0.0, 0.45 - tone) * 1.6 * contrast
            c = c + (np.array(cols["light"], np.float32) - c) * max(0.0, tone - 0.70) * 1.2 * contrast
            c = c * rs.uniform(1 - 0.07 * contrast, 1 + 0.07 * contrast)
        rgb = np.where(win[..., None], c[None, None, :], rgb)
        tone_map = np.where(win, 1.0 if light else 0.0, tone_map)
        cover = np.maximum(cover, cv)
    if base_fill is not None:                              # opaque interior band
        bf = base_fill(t, x)
        hole = bf > cover
        mix = np.array(cols["base"], np.float32) * 0.55 + np.array(cols["dark"], np.float32) * 0.45
        rgb = np.where(hole[..., None], mix[None, None, :], rgb)
        cover = np.maximum(cover, bf)
    rk = (1.0 - ss(0.0, 0.32, t))[..., None] * (1.0 - 0.6 * tone_map[..., None])
    tk = ss(0.55, 1.0, t)[..., None]
    rgb = rgb + (np.array(cols["root"], np.float32) - rgb) * rk * ramp
    rgb = rgb + (np.array(cols["light"], np.float32) - rgb) * tk * 0.30
    fib = 0.5 + 0.5 * np.sin(x * 2.1 + 5.0 * np.sin(yv * 7.0 + x * 0.04))
    rgb = rgb * (0.94 + 0.10 * fib[..., None]) * (0.82 + 0.18 * np.clip(hgt * 1.3, 0, 1)[..., None])
    ao = (0.50 + 0.50 * ss(0.0, 0.65, t)) * (0.80 + 0.20 * np.clip(hgt * 1.4, 0, 1))
    rough = 0.72 - 0.10 * np.clip(hgt, 0, 1) + 0.05 * (1 - fib)
    return np.clip(rgb, 0, 1), cover, hgt + 0.05 * fib * cover, ao, rough


def tile(kind, cols, seed0, light_frac, tw, th):
    k = KINDS[kind]
    rs = np.random.RandomState(k["seed"] * 7 + seed0)
    n = k["n"]
    lanes = [((i + 0.5) / n * 2 - 1) + rs.uniform(-0.4, 0.4) / n * 2 for i in range(n)]
    lanes = [math.copysign(abs(v) ** 1.25, v) for v in lanes]
    return strand_layer(tw, th, rs, lanes, k, cols, light_frac)


def strip(cols, seed0, light_frac, w, h):
    rs = np.random.RandomState(97 + seed0)
    n = max(8, int(220 * w / 1024))
    lanes = [(i + rs.uniform(-0.45, 0.45)) * w / n for i in range(n)]
    k = dict(amp=3.5, cyc=0.6, w0=7.0, tip=(0.50, 1.0), spread=1.0, root=1.0)
    return strand_layer(w, h, rs, lanes, k, cols, light_frac * 0.4, wrap=True,
                        base_fill=lambda t, x: ss(0.62, 0.30, t) * np.ones_like(x),
                        ramp=0.12, contrast=0.5)


def dilate(rgb, cov, it):
    """Spread strand colours into transparent texels (nearest strand), it steps of 1 px."""
    cov = cov.copy()
    for _ in range(it):
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rc = np.roll(cov, (dy, dx), (0, 1))
            take = rc & ~cov
            if take.any():
                rr = np.roll(rgb, (dy, dx), (0, 1))
                rgb[take] = rr[take]
                cov = cov | take
    if not cov.all():                                      # far texels: the darkest strand colour
        rgb[~cov] = rgb[cov].min(axis=0) if cov.any() else rgb[~cov]
    return rgb


def hexc(text):
    h = text.lstrip("#")
    return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


def make(a):
    S = a.size
    tw, th, sh = S // 4, S * 3 // 4, S // 4
    cols = {k: hexc(getattr(a, k)) for k in ("dark", "base", "light", "root")}
    albedo = np.zeros((S, S, 4), np.float32)
    albedo[..., :3] = cols["dark"]
    height = np.zeros((S, S), np.float32)
    ao = np.ones((S, S), np.float32)
    rough = np.full((S, S), 0.8, np.float32)
    for kind in range(4):
        rgb, cov, hgt, o, r = tile(kind, cols, a.seed, a.light_frac, tw, th)
        sl = (slice(0, th), slice(kind * tw, (kind + 1) * tw))   # image rows: top = v 1
        albedo[sl + (slice(0, 3),)] = rgb[::-1]
        albedo[sl + (3,)] = cov[::-1]
        height[sl], ao[sl], rough[sl] = hgt[::-1], o[::-1], r[::-1]
    rgb, cov, hgt, o, r = strip(cols, a.seed, a.light_frac, S, sh)
    sl = (slice(th, S), slice(0, S))
    albedo[sl + (slice(0, 3),)] = rgb[::-1]
    albedo[sl + (3,)] = cov[::-1]
    height[sl], ao[sl], rough[sl] = hgt[::-1], o[::-1], r[::-1]
    albedo[..., :3] = dilate(albedo[..., :3].copy(), albedo[..., 3] > 0.02, 12)
    nx, ny = -np.gradient(height, axis=1) * 3.0, np.gradient(height, axis=0) * 3.0
    ln = np.sqrt(nx * nx + ny * ny + 1.0)
    normal = np.stack([nx / ln * 0.5 + 0.5, ny / ln * 0.5 + 0.5, 1.0 / ln * 0.5 + 0.5], 2)
    orm = np.stack([ao, rough, np.zeros_like(ao)], 2)
    os.makedirs(a.out, exist_ok=True)
    out = {}
    for kind, arr, mode in (("albedo", albedo, "RGBA"), ("normal", normal, "RGB"),
                            ("orm", orm, "RGB")):
        path = os.path.join(a.out, f"T_{a.tag}_cards_{kind}.png")
        Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), mode).save(path)
        out[kind] = path
    return {"files": out, "size": S, "layout": {"tiles": "4 x (S/4 x 3S/4), v 0.25..1",
                                                "mass_strip": "S x S/4, v 0..0.25"}}, 0


def check(a):
    img = np.asarray(Image.open(a.png).convert("RGBA"), dtype=np.float32) / 255.0
    rgb, alpha = img[..., :3], img[..., 3]
    value = rgb.max(axis=2)
    strands = alpha > 0.9
    if not strands.any():
        return {"problems": ["no opaque strand texels"], "verdict": "fail"}, 1
    p99 = float(np.percentile(value[strands], 99))
    edge = (alpha > 0.02) & (alpha < 0.9)
    light_edge = float((value[edge] > p99 + 0.02).mean()) if edge.any() else 0.0
    fill = alpha <= 0.02
    fill_gap = float(np.percentile(value[fill], 95) - p99) if fill.any() else 0.0
    problems = []
    if light_edge > a.max_light_edge:
        problems.append(f"{light_edge:.1%} of semi-transparent texels are lighter than the "
                        "strands (white/grey fringe: dilate the strand colour into them)")
    if fill_gap > 0.05:
        problems.append(f"the colour under alpha 0 is lighter than the strands by "
                        f"{fill_gap:.2f}: mip-maps will grey the hair at distance")
    return {"strand_value_p99": round(p99, 3), "light_edge_share": round(light_edge, 4),
            "fill_vs_strand": round(fill_gap, 3), "problems": problems,
            "verdict": "fail" if problems else "pass"}, 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--out", required=True)
    m.add_argument("--tag", required=True)
    for key, default in (("dark", "1a1410"), ("base", "3b2a20"), ("light", "8a7060"),
                         ("root", "0e0a08")):
        m.add_argument(f"--{key}", default=default)
    m.add_argument("--light-frac", type=float, default=0.08)
    m.add_argument("--seed", type=int, default=0)
    m.add_argument("--size", type=int, default=1024)
    c = sub.add_parser("check")
    c.add_argument("png")
    c.add_argument("--max-light-edge", type=float, default=0.01)
    a = ap.parse_args()
    res, code = (make if a.cmd == "make" else check)(a)
    print(json.dumps(res, indent=1))
    sys.exit(code)


if __name__ == "__main__":
    main()
