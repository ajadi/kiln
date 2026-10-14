"""Readability checks on game screenshots for qa-readability. Pillow + numpy, run with Bash.

  python readability.py contrast shot.png --a 410,220,60,90 --b 380,190,120,150 [--min 3]
  python readability.py contrast shot.png --mask enemy_mask.png [--ring 15] [--min 4.5] [--parts 3]
  python readability.py contrast --hex-a 3a6ea5 --hex-b 8c7a5b [--min 3]     (palette pair)
  python readability.py cvd --hex-a d62728 --hex-b 2ca02c [--type all]
  python readability.py mask with_enemy.png without_enemy.png --out enemy_mask.png [--tol 12]
         [--largest] [--fill]
  python readability.py cvd shot.png --mask enemy_mask.png [--type all] [--model machado]
         [--min 3] [--min-de 0] [--out review/]
  python readability.py squint shot.png --target 410,220,60,90 [--sigma px] [--ring 15]
         [--levels 4] [--out review/]
  python readability.py saliency shot.png [--target x,y,w,h | --mask m.png] [--top 3]
         [--border px] [--out review/]
  python readability.py squint shot.png --target ... --expect same   (decoration must not pop)

Regions: boxes are x,y,w,h in screenshot pixels (contact_sheet.py contrast takes x0,y0,x1,y1).
--a/--b compare two regions; when --b encloses --a, --b minus --a is used (a ring). --mask (white
or opaque = target; `mask` builds one from shots with and without the enemy) compares the target
with a --ring px band around it (10-20 px local background).
contrast  WCAG ratio (Y1 + 0.05)/(Y2 + 0.05) of mean linear luminance; thresholds from the lighting
          skill: >= 3:1 enemy vs background, >= 4.5:1 weak point vs surrounding surface.
cvd       simulates protan/deutan/tritan colour-vision deficiency at full severity in linear RGB
          (Machado, Oliveira & Fernandes 2009; --model brettel = Brettel 1997 as in libDaltonLens,
          better for tritan) and re-measures contrast plus CIELAB dE76 of the region means in each
          simulation. Pass: every vision >= --min, or >= --min-de when that is set (colour cues).
squint    separable Gaussian blur (sigma default 1% of width) of luminance, posterised into
          --levels equal L* bands between the image's p1 and p99; pass when the target and its
          surround land in different bands. Reports the blurred contrast too.
saliency  spectral residual saliency (Hou & Zhang 2007: 64 px wide, 3x3 mean on log amplitude,
          squared, Gaussian sigma 2.5); peaks by non-maximum suppression. With a target: its peak
          rank (pass if <= --top), percentile and saliency vs the 3 x mean object threshold.
--out DIR writes simulated / blurred / banded / saliency images for the reviewer to look at.
Glob patterns are expanded by the script. Output: JSON with "verdict"; exit code 1 on fail.
"""

import argparse
import glob
import json
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw

# Machado, Oliveira & Fernandes 2009, precomputed matrices, severity 1.0 (linear RGB)
MACHADO = {
    "protan": [[0.152286, 1.052583, -0.204868],
               [0.114503, 0.786281, 0.099216],
               [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968],
               [0.280085, 0.672501, 0.047413],
               [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779],
               [-0.078411, 0.930809, 0.147602],
               [0.004733, 0.691367, 0.303900]],
}
# Brettel, Vienot & Mollon 1997 in linear sRGB, parameters from libDaltonLens (Unlicense):
# (matrix for one half-plane, matrix for the other, separation plane normal)
BRETTEL = {
    "protan": ([[0.14980, 1.19548, -0.34528], [0.10764, 0.84864, 0.04372],
                [0.00384, -0.00540, 1.00156]],
               [[0.14570, 1.16172, -0.30742], [0.10816, 0.85291, 0.03892],
                [0.00386, -0.00524, 1.00139]],
               [0.00048, 0.00393, -0.00441]),
    "deutan": ([[0.36477, 0.86381, -0.22858], [0.26294, 0.64245, 0.09462],
                [-0.02006, 0.02728, 0.99278]],
               [[0.37298, 0.88166, -0.25464], [0.25954, 0.63506, 0.10540],
                [-0.01980, 0.02784, 0.99196]],
               [-0.00281, -0.00611, 0.00892]),
    "tritan": ([[1.01277, 0.13548, -0.14826], [-0.01243, 0.86812, 0.14431],
                [0.07589, 0.80500, 0.11911]],
               [[0.93678, 0.18979, -0.12657], [0.06154, 0.81526, 0.12320],
                [-0.37562, 1.12767, 0.24796]],
               [0.03901, -0.02788, -0.01113]),
}
Y_WEIGHTS = np.array([0.2126, 0.7152, 0.0722])
XYZ = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
WHITE = np.array([0.95047, 1.0, 1.08883])


# ---------------------------------------------------------------- colour

def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0


def to_linear(srgb):
    return np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)


def to_srgb(lin):
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)


def luminance(lin):
    return lin @ Y_WEIGHTS


def lstar(y):
    y = np.asarray(y, dtype=np.float64)
    f = np.where(y > (6 / 29) ** 3, np.cbrt(y), y / (3 * (6 / 29) ** 2) + 4 / 29)
    return 116 * f - 16


def lab(lin_rgb):
    xyz = (XYZ @ np.asarray(lin_rgb, dtype=np.float64)) / WHITE
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def ratio(y1, y2):
    hi, lo = max(y1, y2), min(y1, y2)
    return (hi + 0.05) / (lo + 0.05)


def simulate(lin, kind, model="machado"):
    if kind == "normal":
        return lin
    if model == "brettel":
        m1, m2, n = (np.array(v) for v in BRETTEL[kind])
        side = (lin @ n) >= 0
        out = np.where(side[..., None], lin @ m1.T, lin @ m2.T)
    else:
        out = lin @ np.array(MACHADO[kind]).T
    return np.clip(out, 0.0, 1.0)


# ---------------------------------------------------------------- regions

def parse_box(text, shape):
    x, y, w, h = (int(round(float(v))) for v in text.split(","))
    m = np.zeros(shape[:2], bool)
    m[max(0, y):max(0, y + h), max(0, x):max(0, x + w)] = True
    if not m.any():
        raise SystemExit(f"box {text} is outside the {shape[1]}x{shape[0]} image")
    return m


def load_mask(path, shape):
    img = Image.open(path)
    if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info:
        a = np.asarray(img.convert("RGBA"))[..., 3]
        m = a > 127 if a.min() < 255 else np.asarray(img.convert("L")) > 127
    else:
        m = np.asarray(img.convert("L")) > 127
    if m.shape != tuple(shape[:2]):
        raise SystemExit(f"mask {path} is {m.shape[1]}x{m.shape[0]}, image is "
                         f"{shape[1]}x{shape[0]}")
    if not m.any():
        raise SystemExit(f"mask {path} is empty")
    return m


def dilate(mask, r):
    """Square dilation by r px with an integral image."""
    if r <= 0:
        return mask.copy()
    p = np.pad(mask.astype(np.int32), r)
    ii = np.zeros((p.shape[0] + 1, p.shape[1] + 1), np.int64)
    ii[1:, 1:] = p.cumsum(0).cumsum(1)
    k = 2 * r + 1
    s = ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]
    return s > 0


def regions(args, shape):
    """-> (target mask, background mask, description)."""
    if getattr(args, "mask", None):
        t = load_mask(args.mask, shape)
        bg = dilate(t, args.ring) & ~t
        return t, bg, {"target": f"mask {args.mask}", "background": f"{args.ring}px ring"}
    box_a = getattr(args, "a", None) or getattr(args, "target", None)
    if not box_a:
        raise SystemExit("give --mask, or --a and --b, or --target")
    t = parse_box(box_a, shape)
    box_b = getattr(args, "b", None)
    if box_b:
        bg = parse_box(box_b, shape)
        if (bg & t).sum() == t.sum() and bg.sum() > t.sum():
            bg &= ~t
        return t, bg, {"target": box_a, "background": box_b}
    bg = dilate(t, args.ring) & ~t
    return t, bg, {"target": box_a, "background": f"{args.ring}px ring"}


def bbox(mask):
    ys, xs = np.nonzero(mask)
    return [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1),
            int(ys.max() - ys.min() + 1)]


# ---------------------------------------------------------------- blur

def gaussian_kernel(sigma):
    r = max(1, int(math.ceil(3 * sigma)))
    x = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-x * x / (2 * sigma * sigma))
    return k / k.sum()


def blur(img, sigma):
    """Separable Gaussian, edge padding; img 2-D."""
    if sigma <= 0:
        return img.astype(np.float64)
    k = gaussian_kernel(sigma)
    r = len(k) // 2
    out = img.astype(np.float64)
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (r, r)
        p = np.pad(out, pad, mode="edge")
        n = out.shape[axis]
        acc = np.zeros_like(out)
        for i, w in enumerate(k):
            acc += w * (p[i:i + n] if axis == 0 else p[:, i:i + n])
        out = acc
    return out


def box3(img):
    p = np.pad(img, 1, mode="edge")
    h, w = img.shape
    return sum(p[i:i + h, j:j + w] for i in range(3) for j in range(3)) / 9.0


# ---------------------------------------------------------------- output helpers

def out_path(out_dir, image, kind):
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(image))[0]
    return os.path.join(out_dir, f"{stem}.{kind}.png")


def save_rgb(path, rgb01):
    Image.fromarray((np.clip(rgb01, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(path)


def outline(path, boxes, colour=(255, 0, 255)):
    img = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(img)
    for x, y, w, h in boxes:
        d.rectangle([x, y, x + w - 1, y + h - 1], outline=colour)
    img.save(path)


# ---------------------------------------------------------------- commands

def measure(lin, t, bg):
    y = luminance(lin)
    yt, yb = float(y[t].mean()), float(y[bg].mean())
    de = float(np.linalg.norm(lab(lin[t].mean(0)) - lab(lin[bg].mean(0))))
    return yt, yb, ratio(yt, yb), de


def parse_hex(text):
    h = text.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise SystemExit(f"colour {text}: expected RRGGBB hex")
    return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


def source(args, path):
    """(linear image, target mask, background mask, description) for a file or a hex pair."""
    if getattr(args, "hex_a", None):
        if not args.hex_b:
            raise SystemExit("--hex-a needs --hex-b")
        lin = to_linear(np.array([[parse_hex(args.hex_a), parse_hex(args.hex_b)]]))
        t = np.array([[True, False]])
        return lin, t, ~t, {"target": f"#{args.hex_a.lstrip('#')}",
                            "background": f"#{args.hex_b.lstrip('#')}"}
    lin = to_linear(load_rgb(path))
    t, bg, desc = regions(args, lin.shape)
    return lin, t, bg, desc


def reach_hint(yt, yb, need):
    """Which way the target can still reach `need`: brightening tops out at pure white."""
    if yt >= yb:
        return ""
    up = (1.0 + 0.05) / (yb + 0.05)
    down = (yb + 0.05) / 0.05
    if up < need <= down:
        return (f"; brightening the target cannot reach {need}:1 against this background "
                f"(white gives {up:.2f}:1) - darken the target or its silhouette edge instead "
                f"(up to {down:.1f}:1), or brighten less and darken the background")
    return ""


def cmd_contrast(args, path):
    lin, t, bg, desc = source(args, path)
    yt, yb, r, _ = measure(lin, t, bg)
    ok = r >= args.min
    problems = [] if ok else [f"contrast {r:.2f}:1 < {args.min}:1" + reach_hint(yt, yb, args.min)]
    res = {"file": path or "hex pair", **desc, "Y_target": round(yt, 4),
           "Y_background": round(yb, 4), "contrast": round(r, 2), "threshold": args.min}
    if getattr(args, "parts", 0) and not getattr(args, "hex_a", None):
        # Horizontal bands of the target (head / torso / legs for a figure), each against the
        # background ring rows it shares: a whole-mask mean hides a dark vest on a dark wall.
        ys = np.nonzero(t.any(axis=1))[0]
        edges = np.linspace(ys.min(), ys.max() + 1, args.parts + 1).astype(int)
        rows = np.arange(t.shape[0])[:, None]
        parts = []
        for i in range(args.parts):
            band = (rows >= edges[i]) & (rows < edges[i + 1])
            tb, bb = t & band, bg & band
            if not tb.any() or not bb.any():
                continue
            pyt, pyb, pr, _ = measure(lin, tb, bb)
            pok = pr >= args.min
            parts.append({"part": i + 1, "rows": [int(edges[i]), int(edges[i + 1])],
                          "contrast": round(pr, 2), "verdict": "pass" if pok else "fail"})
            if not pok:
                problems.append(f"part {i + 1}/{args.parts} (rows {edges[i]}-{edges[i + 1]}): "
                                f"contrast {pr:.2f}:1 < {args.min}:1" + reach_hint(pyt, pyb,
                                                                                   args.min))
        res["parts"] = parts
    res.update({"problems": problems, "verdict": "fail" if problems else "pass"})
    return res


def cmd_cvd(args, path):
    lin, t, bg, desc = source(args, path)
    kinds = ["protan", "deutan", "tritan"] if args.type == "all" else [args.type]
    rows, problems = [], []
    for kind in ["normal"] + kinds:
        sim = simulate(lin, kind, args.model)
        yt, yb, r, de = measure(sim, t, bg)
        ok = r >= args.min or (args.min_de > 0 and de >= args.min_de)
        if not ok:
            problems.append(f"{kind}: contrast {r:.2f}:1 < {args.min}:1"
                            + (f" and dE {de:.1f} < {args.min_de}" if args.min_de > 0 else ""))
        row = {"vision": kind, "contrast": round(r, 2), "delta_e": round(de, 1),
               "Y_target": round(yt, 4), "Y_background": round(yb, 4),
               "verdict": "pass" if ok else "fail"}
        if args.out and path and kind != "normal":
            row["image"] = out_path(args.out, path, f"cvd-{kind}")
            save_rgb(row["image"], to_srgb(sim))
        rows.append(row)
    notes = []
    if "tritan" in kinds and args.model == "machado":
        notes.append("Machado tritan is the least reliable; confirm with --model brettel")
    return {"file": path or "hex pair", **desc, "model": args.model, "threshold": args.min,
            "min_delta_e": args.min_de or None, "results": rows, "notes": notes,
            "problems": problems, "verdict": "fail" if problems else "pass"}


def cmd_squint(args, path):
    lin = to_linear(load_rgb(path))
    h, w = lin.shape[:2]
    sigma = args.sigma if args.sigma else max(1.0, 0.01 * w)
    t, bg, desc = regions(args, lin.shape)
    yb = blur(luminance(lin), sigma)
    lb = lstar(yb)
    lo, hi = np.percentile(lb, 1), np.percentile(lb, 99)
    edges = np.linspace(lo, hi, args.levels + 1)
    band_of = lambda v: int(np.clip(np.searchsorted(edges[1:-1], v, side="right"), 0,
                                    args.levels - 1))
    lt, lbg = float(lb[t].mean()), float(lb[bg].mean())
    bt, bb = band_of(lt), band_of(lbg)
    r = ratio(float(yb[t].mean()), float(yb[bg].mean()))
    same = getattr(args, "expect", "different") == "same"
    ok = (bt == bb) if same else (bt != bb)
    res = {"file": path, **desc, "sigma_px": round(sigma, 2), "levels": args.levels,
           "expect": "same" if same else "different",
           "band_edges_Lstar": [round(float(e), 1) for e in edges],
           "target": {"Lstar": round(lt, 1), "band": bt},
           "surround": {"Lstar": round(lbg, 1), "band": bb},
           "contrast_blurred": round(r, 2),
           "problems": [] if ok else [
               f"decoration lands in value band {bt}, its surround in {bb}: it pops out at a "
               "glance" if same else
               f"target and surround share value band {bt} of {args.levels} after blur sigma "
               f"{sigma:.1f}px: the read is lost at a glance"],
           "verdict": "pass" if ok else "fail"}
    if args.out:
        g = to_srgb(np.repeat(yb[..., None], 3, axis=2))
        res["image_blur"] = out_path(args.out, path, "squint")
        save_rgb(res["image_blur"], g)
        bands = np.clip(np.searchsorted(edges[1:-1], lb, side="right"), 0, args.levels - 1)
        res["image_bands"] = out_path(args.out, path, "squint-bands")
        save_rgb(res["image_bands"], np.repeat((bands / max(1, args.levels - 1))[..., None], 3, 2))
        outline(res["image_bands"], [bbox(t)])
    return res


def spectral_residual(gray):
    """Hou & Zhang 2007 on a 2-D 0..255 array already resized to 64 px wide -> map in [0, 1].
    log(|F| + 1) as in OpenCV's StaticSaliencySpectralResidual (plain log|F| explodes on exact
    spectral zeros of flat or periodic images)."""
    f = np.fft.fft2(gray)
    amp = np.log(np.abs(f) + 1.0)
    phase = np.angle(f)
    resid = amp - box3(amp)
    s = np.abs(np.fft.ifft2(np.exp(resid + 1j * phase))) ** 2
    s = blur(s, 2.5)
    s -= s.min()
    return s / s.max() if s.max() > 0 else s


def peaks(sal, n, radius):
    s = sal.copy()
    out = []
    for _ in range(n):
        y, x = np.unravel_index(int(np.argmax(s)), s.shape)
        if not np.isfinite(s[y, x]) or s[y, x] <= 0:
            break
        out.append((float(sal[y, x]), int(y), int(x)))
        s[max(0, y - radius):y + radius + 1, max(0, x - radius):x + radius + 1] = -np.inf
    return out


def blob(sal, y, x, thr):
    """4-connected region of sal >= thr containing (y, x) -> bbox in map px."""
    if sal[y, x] < thr:
        return x, y, 1, 1
    seen = np.zeros(sal.shape, bool)
    stack, xs, ys = [(y, x)], [], []
    seen[y, x] = True
    while stack:
        cy, cx = stack.pop()
        ys.append(cy)
        xs.append(cx)
        for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
            if 0 <= ny < sal.shape[0] and 0 <= nx < sal.shape[1] and not seen[ny, nx] \
                    and sal[ny, nx] >= thr:
                seen[ny, nx] = True
                stack.append((ny, nx))
    return min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1


def cmd_saliency(args, path):
    rgb = load_rgb(path)
    h, w = rgb.shape[:2]
    gray = rgb @ np.array([0.2989, 0.5870, 0.1140])
    mw = 64
    mh = max(1, int(round(h * mw / w)))
    small = np.asarray(Image.fromarray((gray * 255).astype(np.uint8)).resize(
        (mw, mh), Image.BILINEAR), dtype=np.float64)
    sal = spectral_residual(small)
    sx, sy = w / mw, h / mh
    radius = max(2, int(round(0.08 * mw)))
    # Spectral residual puts spurious peaks on the frame edges (FFT wrap-around; g2: 5 of 5 top
    # peaks on the border of busy 1080p frames, also after reflect padding): peaks within
    # --border px of the edge are not ranked.
    border = int(round(0.03 * w)) if args.border is None else max(0, args.border)
    bx, by = int(math.ceil(border / sx)), int(math.ceil(border / sy))
    ranked = sal.copy()
    if bx or by:
        ranked[:by, :] = ranked[mh - by:, :] = -np.inf
        ranked[:, :bx] = ranked[:, mw - bx:] = -np.inf
    pk = [(float(sal[y, x]), y, x) for _, y, x in peaks(ranked, max(args.top, 5), radius)]
    thr = 3 * float(sal.mean())
    to_img = lambda bx, by, bw, bh: [int(bx * sx), int(by * sy), int(math.ceil(bw * sx)),
                                     int(math.ceil(bh * sy))]
    peaks_out = [{"rank": i + 1, "x": int((x + 0.5) * sx), "y": int((y + 0.5) * sy),
                  "saliency": round(v, 3)} for i, (v, y, x) in enumerate(pk)]
    res = {"file": path, "map_size": [mw, mh], "border_px": border,
           "object_threshold": round(thr, 3),
           "peaks": peaks_out,
           "top_region": to_img(*blob(sal, pk[0][1], pk[0][2], thr)) if pk else None}
    target_box = None
    if args.mask or args.target:
        t, _, desc = regions(args, rgb.shape)
        target_box = bbox(t)
        ts = np.asarray(Image.fromarray(t.astype(np.uint8) * 255).resize(
            (mw, mh), Image.BOX)) > 0
        if not ts.any():
            cy = min(mh - 1, int((target_box[1] + target_box[3] / 2) / sy))
            cx = min(mw - 1, int((target_box[0] + target_box[2] / 2) / sx))
            ts[cy, cx] = True
        rank = next((i + 1 for i, (_, y, x) in enumerate(pk) if ts[y, x]), None)
        tmax = float(sal[ts].max())
        pct = float((sal <= tmax).mean() * 100)
        ok = rank is not None and rank <= args.top
        res.update({"target": desc["target"], "target_rank": rank, "top": args.top,
                    "target_peak": round(tmax, 3), "target_percentile": round(pct, 1),
                    "target_above_object_threshold": tmax >= thr,
                    "problems": [] if ok else [
                        f"target is {'not among the top ' + str(len(pk)) if rank is None else 'peak #' + str(rank)}"
                        f" saliency peaks (needs <= {args.top}); strongest pull at "
                        f"{res['top_region']}"],
                    "verdict": "pass" if ok else "fail"})
    else:
        res.update({"problems": [], "verdict": "report",
                    "notes": ["no --target/--mask: peaks reported only"]})
    if args.out:
        big = np.asarray(Image.fromarray((sal * 255).astype(np.uint8)).resize(
            (w, h), Image.BILINEAR))
        res["image"] = out_path(args.out, path, "saliency")
        img = Image.fromarray(np.repeat(big[..., None], 3, 2))
        d = ImageDraw.Draw(img)
        for p in peaks_out:
            r = max(4, int(radius * sx / 2))
            d.ellipse([p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r], outline=(255, 64, 0))
            d.text((p["x"] + r + 2, p["y"] - r), str(p["rank"]), fill=(255, 64, 0))
        if target_box:
            x, y, bw, bh = target_box
            d.rectangle([x, y, x + bw - 1, y + bh - 1], outline=(0, 200, 255))
        img.save(res["image"])
    return res


def flood(m, seeds):
    """4-connected flood fill of True pixels of m from seed (y, x) list -> bool mask."""
    out = np.zeros(m.shape, bool)
    stack = [s for s in seeds if m[s]]
    for s in stack:
        out[s] = True
    h, w = m.shape
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and m[ny, nx] and not out[ny, nx]:
                out[ny, nx] = True
                stack.append((ny, nx))
    return out


def largest_component(m):
    """The biggest 4-connected component (drops particles and stray diff specks)."""
    left, best = m.copy(), np.zeros(m.shape, bool)
    while left.any():
        y, x = np.argwhere(left)[0]
        comp = flood(left, [(int(y), int(x))])
        if comp.sum() > best.sum():
            best = comp
        left &= ~comp
    return best


def fill_holes(m):
    """Background pixels not reachable from the frame border become target."""
    h, w = m.shape
    edge = [(y, x) for y in (0, h - 1) for x in range(w)]
    edge += [(y, x) for x in (0, w - 1) for y in range(h)]
    outside = flood(~m, edge)
    return m | ~outside


def cmd_mask(args):
    a = np.asarray(Image.open(args.with_target).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(args.without_target).convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        return {"problems": [f"sizes differ {a.shape[1]}x{a.shape[0]} vs "
                             f"{b.shape[1]}x{b.shape[0]}"], "verdict": "fail"}
    m = np.abs(a - b).max(axis=2) > args.tol
    if not m.any():
        return {"pixels": 0, "problems": ["no pixel differs: the hide toggle had no visible "
                                          "effect (same frame? target off screen?)"],
                "verdict": "fail"}
    if args.largest:
        m = largest_component(m)
    if args.fill:
        m = fill_holes(m)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    Image.fromarray(m.astype(np.uint8) * 255, "L").save(args.out)
    share = float(m.mean())
    warn = []
    if share > 0.25:
        warn.append(f"{share:.0%} of the frame differs: animated background, particles or "
                    "camera motion between the shots - freeze them or use --a/--b boxes")
    return {"mask": args.out, "pixels": int(m.sum()), "bbox": bbox(m), "share": round(share, 4),
            "warnings": warn, "problems": [], "verdict": "pass"}


def expand(patterns):
    out = []
    for p in patterns:
        hits = sorted(glob.glob(p)) if re.search(r"[*?\[]", p) else [p]
        if not hits:
            raise SystemExit(f"no files match {p}")
        out += hits
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def region_args(p, pair=True):
        p.add_argument("images", nargs="*" if pair else "+")
        if pair:
            p.add_argument("--a", help="target box x,y,w,h")
            p.add_argument("--b", help="background box x,y,w,h")
            p.add_argument("--hex-a", help="target colour RRGGBB (no image needed)")
            p.add_argument("--hex-b", help="background colour RRGGBB")
        p.add_argument("--target", help="target box x,y,w,h (ring background)")
        p.add_argument("--mask", help="target mask PNG, same size as the image")
        p.add_argument("--ring", type=int, default=15, help="background ring width px")

    c = sub.add_parser("contrast")
    region_args(c)
    c.add_argument("--min", type=float, default=3.0)
    c.add_argument("--parts", type=int, default=0,
                   help="also check N horizontal bands of the target (3 = head/torso/legs)")
    v = sub.add_parser("cvd")
    region_args(v)
    v.add_argument("--type", choices=("protan", "deutan", "tritan", "all"), default="all")
    v.add_argument("--model", choices=("machado", "brettel"), default="machado")
    v.add_argument("--min", type=float, default=3.0)
    v.add_argument("--min-de", type=float, default=0.0, help="alternative pass: CIELAB dE76")
    v.add_argument("--out")
    s = sub.add_parser("squint")
    region_args(s, pair=False)
    s.add_argument("--sigma", type=float, default=0.0, help="px; default 1%% of width")
    s.add_argument("--levels", type=int, default=4)
    s.add_argument("--expect", choices=("different", "same"), default="different",
                   help="same: decoration that must not pop out")
    s.add_argument("--out")
    sa = sub.add_parser("saliency")
    region_args(sa, pair=False)
    sa.add_argument("--top", type=int, default=3)
    sa.add_argument("--border", type=int, default=None,
                    help="ignore peaks within N px of the frame edge (default 3%% of width)")
    sa.add_argument("--out")
    m = sub.add_parser("mask")
    m.add_argument("with_target")
    m.add_argument("without_target")
    m.add_argument("--out", required=True)
    m.add_argument("--tol", type=int, default=12, help="per-channel 8-bit difference")
    m.add_argument("--largest", action="store_true", help="keep the largest component only")
    m.add_argument("--fill", action="store_true", help="fill holes inside the mask")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        if args.cmd == "mask":
            results = [cmd_mask(args)]
        else:
            fn = {"contrast": cmd_contrast, "cvd": cmd_cvd, "squint": cmd_squint,
                  "saliency": cmd_saliency}[args.cmd]
            if getattr(args, "hex_a", None):
                results = [fn(args, None)]
            elif not args.images:
                raise SystemExit("give an image (or --hex-a/--hex-b)")
            else:
                results = [fn(args, p) for p in expand(args.images)]
    except SystemExit as e:
        if isinstance(e.code, str):
            results = [{"problems": [e.code], "verdict": "fail"}]
        else:
            raise
    print(json.dumps(results if len(results) > 1 else results[0], indent=1))
    sys.exit(0 if all(r["verdict"] != "fail" for r in results) else 1)


if __name__ == "__main__":
    main()
