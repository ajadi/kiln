"""Visual regression: baseline frames per scene, compare new captures, name what changed.
numpy + Pillow.

  python frames.py baseline cap/plaza_ref.png cap/plaza_gate.png --scene plaza
  python frames.py compare cap/*.png --scene plaza [--min-ssim 0.97] [--min-share 0.002] [--out diff/]
  python frames.py accept cap/plaza_ref.png --scene plaza --why "TASK-034 adds the bank sign"

Baselines live in production/baselines/<scene>/ (committed): one PNG per fixed camera, named by
the camera. Capture them from the same placed cameras every time (Godot: a Camera3D per view,
`editor_screenshot source=cinematic`; windowed runs for frustum cameras), same resolution, same
time of day and weather, effects that move frozen or off.
compare  per image: SSIM of the luminance (7x7 windows) and the changed regions - pixels whose
         luminance differs by more than --tol after a 3x3 blur, grouped into boxes; a region
         larger than --min-share of the frame or SSIM under --min-ssim fails. --out writes
         <name>_diff.png (changed pixels in magenta over the new frame, boxes outlined).
accept   makes the new capture the baseline and appends the reason to HISTORY.md: an intended
         change is accepted on purpose, never by re-running baseline over it silently.
A capture without a baseline is NOT ASSESSED. Output: JSON; exit 1 if any image fails.
"""

import argparse
import datetime
import glob
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw

BASE = os.path.join("production", "baselines")


def gray(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
    return a @ np.array([0.299, 0.587, 0.114])


def box(img, r):
    """Mean over a (2r+1)^2 window with an integral image (edges padded)."""
    p = np.pad(img, r, mode="edge")
    ii = np.zeros((p.shape[0] + 1, p.shape[1] + 1))
    ii[1:, 1:] = p.cumsum(0).cumsum(1)
    k = 2 * r + 1
    return (ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]) / (k * k)


def ssim(a, b):
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    ma, mb = box(a, 3), box(b, 3)
    va, vb = box(a * a, 3) - ma * ma, box(b * b, 3) - mb * mb
    cov = box(a * b, 3) - ma * mb
    s = ((2 * ma * mb + c1) * (2 * cov + c2)) / ((ma * ma + mb * mb + c1) * (va + vb + c2))
    return float(s.mean())


def regions(mask):
    """Boxes [x, y, w, h, pixels] of 8-connected changed areas, largest first."""
    seen = np.zeros_like(mask)
    out = []
    h, w = mask.shape
    for y, x in np.argwhere(mask):
        if seen[y, x]:
            continue
        stack, ys, xs = [(y, x)], [], []
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            ys.append(cy)
            xs.append(cx)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
        out.append([int(min(xs)), int(min(ys)), int(max(xs) - min(xs) + 1),
                    int(max(ys) - min(ys) + 1), len(ys)])
    return sorted(out, key=lambda r: -r[4])


def compare_one(path, scene, a):
    ref = os.path.join(BASE, scene, os.path.basename(path))
    name = os.path.basename(path)
    if not os.path.isfile(ref):
        return {"image": name, "verdict": "NOT ASSESSED",
                "problems": [f"no baseline {ref}: run frames.py baseline first"]}
    g_new, g_old = gray(path), gray(ref)
    if g_new.shape != g_old.shape:
        return {"image": name, "verdict": "FAIL", "problems": [
            f"size changed {g_old.shape[1]}x{g_old.shape[0]} -> {g_new.shape[1]}x"
            f"{g_new.shape[0]}: capture at the baseline's resolution"]}
    score = ssim(g_new, g_old)
    diff = np.abs(box(g_new, 1) - box(g_old, 1)) > a.tol
    regs = [r for r in regions(diff) if r[4] >= 4]
    total = g_new.size
    big = [r for r in regs if r[4] / total >= a.min_share]
    problems = []
    if score < a.min_ssim:
        problems.append(f"SSIM {score:.3f} < {a.min_ssim}")
    if big:
        problems.append(f"{len(big)} changed region(s), largest at x={big[0][0]} y={big[0][1]} "
                        f"{big[0][2]}x{big[0][3]} px ({big[0][4] / total:.1%} of the frame)")
    res = {"image": name, "ssim": round(score, 4),
           "regions": [{"bbox": r[:4], "share": round(r[4] / total, 4)} for r in big[:10]],
           "problems": problems, "verdict": "FAIL" if problems else "PASS"}
    if a.out and (big or problems):
        os.makedirs(a.out, exist_ok=True)
        img = Image.open(path).convert("RGB")
        arr = np.asarray(img).copy()
        arr[diff] = (255, 0, 255)
        img = Image.fromarray(arr)
        d = ImageDraw.Draw(img)
        for x, y, w, h, _ in big:
            d.rectangle([x - 2, y - 2, x + w + 1, y + h + 1], outline=(0, 255, 255), width=2)
        res["diff_image"] = os.path.join(a.out, os.path.splitext(name)[0] + "_diff.png")
        img.save(res["diff_image"])
    return res


def expand(patterns):
    out = []
    for p in patterns:
        hits = sorted(glob.glob(p)) if any(c in p for c in "*?[") else [p]
        out += hits
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("baseline", "compare", "accept"):
        s = sub.add_parser(name)
        s.add_argument("images", nargs="+")
        s.add_argument("--scene", required=True)
        if name == "compare":
            s.add_argument("--min-ssim", type=float, default=0.97)
            s.add_argument("--min-share", type=float, default=0.002)
            s.add_argument("--tol", type=float, default=12.0, help="luminance step 0..255")
            s.add_argument("--out")
        if name == "accept":
            s.add_argument("--why", required=True)
    a = ap.parse_args()
    images = expand(a.images)
    folder = os.path.join(BASE, a.scene)
    if a.cmd in ("baseline", "accept"):
        os.makedirs(folder, exist_ok=True)
        for path in images:
            shutil.copyfile(path, os.path.join(folder, os.path.basename(path)))
        if a.cmd == "accept":
            with open(os.path.join(folder, "HISTORY.md"), "a", encoding="utf-8") as fh:
                fh.write(f"- {datetime.date.today()} {', '.join(os.path.basename(p) for p in images)}"
                         f": {a.why}\n")
        res, code = {"scene": a.scene, "baseline": [os.path.basename(p) for p in images]}, 0
    else:
        results = [compare_one(p, a.scene, a) for p in images]
        failed = any(r["verdict"] == "FAIL" for r in results)
        res, code = {"scene": a.scene, "results": results,
                     "verdict": "FAIL" if failed else "PASS"}, 1 if failed else 0
    print(json.dumps(res, indent=1))
    sys.exit(code)


if __name__ == "__main__":
    main()
