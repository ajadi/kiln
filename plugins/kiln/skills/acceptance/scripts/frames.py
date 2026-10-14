"""Visual regression: baseline frames per scene, compare new captures, name what changed.
numpy + Pillow.

  python frames.py baseline cap/plaza_ref.png cap/plaza_gate.png --scene plaza
  python frames.py compare cap/*.png --scene plaza [--min-ssim 0.97] [--min-share 0.002] [--out diff/]
  python frames.py accept cap/plaza_ref.png --scene plaza --why "TASK-034 adds the bank sign"
  python frames.py anim --on "cap/rain_on/*.png" --off "cap/rain_off/*.png" [--box x,y,w,h]
         [--tol 4] [--min-add 0.001]
  python frames.py ramp --change "cap/fade/*.png" --steady "cap/held/*.png" [--box x,y,w,h]
         [--decorrelated 0.5]

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

anim     is an effect moving at all? Two sequences of the same frames, consecutive frames one
         step apart (1/60 s or the engine's fixed step): effect ON and effect OFF. Per frame pair
         the share of (box) pixels whose luminance changes by more than --tol; FAIL when ON adds
         less than --min-add over OFF: the effect is drawn but frozen (its time is never set).
ramp     does a state change sweep instead of easing? Frames during a state change (weather
         fading in, day to night) and the same frames with the state held. Per frame pair the
         mean luminance change (3x3 blur against capture noise). The held run gives two marks:
         consecutive frames (p95) and unrelated frames a third of the run apart (median). FAIL
         when the change's consecutive frames (p95) are past --decorrelated of the way from the
         first mark to the second: they differ like unrelated frames, so the effect jumps -
         typically a phase computed as rate(state) x absolute time instead of integrated over
         time. NOT ASSESSED when the held frames barely change across the run.
Sequences are globs sorted by name; fewer than 2 frames is NOT ASSESSED.
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


def _sequence(pattern, crop):
    paths = expand([pattern])
    if len(paths) < 2:
        return None
    frames = [gray(p) for p in paths]
    if crop:
        x, y, w, h = crop
        frames = [f[y:y + h, x:x + w] for f in frames]
    return frames


def _pairs(frames, fn):
    return np.array([fn(a, b) for a, b in zip(frames, frames[1:])])


def anim(a):
    crop = [int(v) for v in a.box.split(",")] if a.box else None
    on, off = _sequence(a.on, crop), _sequence(a.off, crop)
    if on is None or off is None:
        return {"check": "anim", "verdict": "NOT ASSESSED", "box": crop,
                "note": "needs >= 2 frames in both --on and --off"}, 0
    changed = lambda x, y: float((np.abs(x - y) > a.tol).mean())  # noqa: E731
    share_on, share_off = float(_pairs(on, changed).mean()), float(_pairs(off, changed).mean())
    added = share_on - share_off
    ok = added >= a.min_add
    return {"check": "anim", "verdict": "PASS" if ok else "FAIL", "box": crop,
            "changed_share_on": round(share_on, 5), "changed_share_off": round(share_off, 5),
            "added": round(added, 5), "threshold": a.min_add, "frames": [len(on), len(off)],
            "problem": None if ok else
            f"frozen: the effect adds {added:.4%} changed pixels per frame (< {a.min_add:.2%}); "
            "it is drawn but does not move - is its time / phase input ever advanced?"}, \
        0 if ok else 1


def ramp(a):
    crop = [int(v) for v in a.box.split(",")] if a.box else None
    change, steady = _sequence(a.change, crop), _sequence(a.steady, crop)
    if change is None or steady is None:
        return {"check": "ramp", "verdict": "NOT ASSESSED", "box": crop,
                "note": "needs >= 2 frames in both --change and --steady"}, 0
    moved = lambda x, y: float(np.abs(box(x, 1) - box(y, 1)).mean())  # noqa: E731
    p_change = float(np.percentile(_pairs(change, moved), 95))
    near = float(np.percentile(_pairs(steady, moved), 95))
    gap = max(2, len(steady) // 3)
    far = float(np.median([moved(steady[i], steady[i + gap]) for i in range(len(steady) - gap)]
                          or [near]))
    out = {"check": "ramp", "box": crop, "change_p95": round(p_change, 3),
           "held_consecutive_p95": round(near, 3), "held_unrelated": round(far, 3),
           "threshold": a.decorrelated, "frames": [len(change), len(steady)]}
    if far < 1.2 * near + 0.25:
        return dict(out, verdict="NOT ASSESSED", note="the held frames barely change across the "
                    "run: record a longer held run, or a moving part of the effect"), 0
    limit = near + a.decorrelated * (far - near)
    ok = p_change <= limit
    out.update(verdict="PASS" if ok else "FAIL", limit=round(limit, 3),
               problem=None if ok else
               f"sweeps: during the state change consecutive frames differ by {p_change:.2f} "
               f"(held: {near:.2f} between neighbours, {far:.2f} between unrelated frames) - "
               "they are as unrelated as frames far apart; a phase computed as rate(state) x "
               "absolute time jumps when the rate changes: integrate it (phase += rate * dt)")
    return out, 0 if ok else 1


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
    m = sub.add_parser("anim")
    m.add_argument("--on", required=True)
    m.add_argument("--off", required=True)
    m.add_argument("--box", help="x,y,w,h in pixels")
    m.add_argument("--tol", type=float, default=4.0, help="luminance step 0..255")
    m.add_argument("--min-add", type=float, default=0.001, help="share of box pixels")
    r = sub.add_parser("ramp")
    r.add_argument("--change", required=True)
    r.add_argument("--steady", required=True)
    r.add_argument("--box", help="x,y,w,h in pixels")
    r.add_argument("--decorrelated", type=float, default=0.5,
                   help="0..1: how far toward unrelated frames a consecutive pair may go")
    a = ap.parse_args()
    if a.cmd in ("anim", "ramp"):
        res, code = (anim if a.cmd == "anim" else ramp)(a)
        print(json.dumps(res, indent=1))
        sys.exit(code)
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
