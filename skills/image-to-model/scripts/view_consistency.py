"""Check that several views of one object agree before they go into a multi-view generator.

Normal Python (Pillow + numpy), run with Bash.

  python view_consistency.py --front f.png --back b.png --left l.png --right r.png --diff captures/vc/
  python view_consistency.py --left l.png --right r.png          # one opposite pair is enough

Views drawn one by one by a 2D image model get lengths slightly wrong in each view (wheelbase,
roof line, turret), and a generator that fuses the views averages or doubles the conflict.
Under a turntable at eye level, opposite views have mirrored silhouettes whatever the shape:
back = mirror(front), right = mirror(left). Per opposite pair the second view is mirrored, both
are cropped to their silhouette and scaled to one size, and the outlines are compared:
  aspect_delta      relative difference of width/height
  top_disagree      share of columns whose top outline differs by more than 2 % of the height
  bottom_disagree   the same for the bottom outline (wheels, feet, tracks)
  side_disagree     share of rows whose left or right outline differs by more than 2 %
  iou               for information only: a 4 % wheelbase error still scores 0.985
Across all views, `row_delta` compares the heights of the strongest width changes (beltline,
shoulders, hem); a weak signal, reported only.
Verdict (PROTOTYPE thresholds from synthetic silhouettes; calibrate on renders of an accepted
model and on the same renders with one part moved by 3 %):
  pass   |aspect_delta| <= 0.02 and every disagree <= 0.05
  fail   |aspect_delta| > 0.03 or any disagree > 0.08    -> use one image instead
  warn   in between: show the diff images to the art-director
Exit code 1 on fail. Inputs need alpha (cut the background out first: prep_image.py).
--diff writes one image per pair: first view only red, mirrored second only blue, both white.
"""

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

CUT = 128
SIZE = 512
TOL = 0.02
PASS = {"aspect": 0.02, "disagree": 0.05}
FAIL = {"aspect": 0.03, "disagree": 0.08}


def mask_of(path):
    img = Image.open(path).convert("RGBA")
    alpha = np.asarray(img)[..., 3]
    if not (alpha < 255).any():
        raise SystemExit(json.dumps({"error": f"{path} has no transparency; cut the background "
                                     "out first (prep_image.py prep)"}))
    return alpha >= CUT


def crop(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def resized(mask, width, height):
    img = Image.fromarray((mask * 255).astype(np.uint8)).resize((width, height), Image.NEAREST)
    return np.asarray(img) >= CUT


def outlines(mask):
    """Top and bottom row per column, left and right column per row, as fractions of the height;
    NaN where the column or row is empty."""
    h, w = mask.shape
    cols, rows = mask.any(axis=0), mask.any(axis=1)
    top = np.where(cols, mask.argmax(axis=0), np.nan) / h
    bottom = np.where(cols, h - 1 - mask[::-1].argmax(axis=0), np.nan) / h
    left = np.where(rows, mask.argmax(axis=1), np.nan) / h
    right = np.where(rows, w - 1 - mask[:, ::-1].argmax(axis=1), np.nan) / h
    return top, bottom, left, right


def share_over(a, b, tol=TOL):
    """Share of positions where the outlines differ by more than tol (one empty counts)."""
    one_empty = np.isnan(a) != np.isnan(b)
    both = ~np.isnan(a) & ~np.isnan(b)
    bad = one_empty | (both & (np.abs(np.nan_to_num(a) - np.nan_to_num(b)) > tol))
    used = one_empty | both
    return float(bad.sum() / used.sum()) if used.any() else 0.0


def profile_disagreement(a, b, tol=TOL):
    """Outline agreement of two silhouettes after cropping both and scaling to one size."""
    ca, cb = crop(a), crop(b)
    if ca is None or cb is None:
        return None
    aspect_a, aspect_b = ca.shape[1] / ca.shape[0], cb.shape[1] / cb.shape[0]
    width = max(8, round(SIZE * (aspect_a + aspect_b) / 2))
    ra, rb = resized(ca, width, SIZE), resized(cb, width, SIZE)
    ta, ba, la, rta = outlines(ra)
    tb, bb, lb, rtb = outlines(rb)
    union = np.logical_or(ra, rb).sum()
    return {"aspect_delta": round(aspect_b / aspect_a - 1, 4),
            "top_disagree": round(share_over(ta, tb, tol), 4),
            "bottom_disagree": round(share_over(ba, bb, tol), 4),
            "side_disagree": round(max(share_over(la, lb, tol), share_over(rta, rtb, tol)), 4),
            "iou": round(float(np.logical_and(ra, rb).sum() / union) if union else 0.0, 4),
            "_masks": (ra, rb)}


def verdict(m):
    worst = max(m["top_disagree"], m["bottom_disagree"], m["side_disagree"])
    if abs(m["aspect_delta"]) > FAIL["aspect"] or worst > FAIL["disagree"]:
        return "fail"
    if abs(m["aspect_delta"]) <= PASS["aspect"] and worst <= PASS["disagree"]:
        return "pass"
    return "warn"


def breakpoints(mask, n=3):
    """Normalised heights of the n strongest changes in silhouette width (beltline, shoulders)."""
    c = crop(mask)
    width = resized(c, max(8, round(SIZE * c.shape[1] / c.shape[0])), SIZE).sum(axis=1).astype(float)
    smooth = np.convolve(width, np.ones(9) / 9, mode="same")
    change = np.abs(np.diff(smooth))
    change[:12] = change[-12:] = 0
    rows = []
    for i in np.argsort(change)[::-1]:
        if all(abs(i - r) > 16 for r in rows):
            rows.append(int(i))
        if len(rows) == n:
            break
    return sorted(r / SIZE for r in rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    for view in ("front", "back", "left", "right"):
        ap.add_argument("--" + view)
    ap.add_argument("--diff", help="folder for one diff image per pair")
    a = ap.parse_args(argv)
    views = {v: getattr(a, v) for v in ("front", "back", "left", "right") if getattr(a, v)}
    pairs = [(x, y) for x, y in (("front", "back"), ("left", "right")) if x in views and y in views]
    if not pairs:
        ap.error("give at least one opposite pair: --front and --back, or --left and --right")
    masks = {v: mask_of(p) for v, p in views.items()}
    results = []
    for x, y in pairs:
        m = profile_disagreement(masks[x], masks[y][:, ::-1])
        if m is None:
            results.append({"pair": f"{x}/{y}", "verdict": "fail", "error": "empty silhouette"})
            continue
        ra, rb = m.pop("_masks")
        m.update(pair=f"{x}/{y}", verdict=verdict(m))
        if a.diff:
            os.makedirs(a.diff, exist_ok=True)
            out = np.zeros(ra.shape + (3,), np.uint8)
            out[ra & ~rb] = (230, 40, 40)
            out[~ra & rb] = (40, 90, 230)
            out[ra & rb] = (255, 255, 255)
            m["diff"] = os.path.join(a.diff, f"{x}_{y}_diff.png").replace("\\", "/")
            Image.fromarray(out).save(m["diff"])
        results.append(m)
    rows = {v: breakpoints(mk) for v, mk in masks.items() if crop(mk) is not None}
    row_delta = 0.0
    if len(rows) > 1:
        ref = rows[next(iter(rows))]
        row_delta = max(max(abs(p - q) for p, q in zip(ref, r)) for r in rows.values() if len(r) == len(ref))
    order = {"pass": 0, "warn": 1, "fail": 2}
    overall = max((r["verdict"] for r in results), key=order.get)
    advice = {"pass": "the views agree: multi-view input is allowed",
              "warn": "borderline: show the diff images to the art-director before a multi-view run",
              "fail": "the views disagree: use one image (front, or a low 3/4 view for hard surface)"}
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"pairs": results, "row_delta": round(row_delta, 4),
                      "verdict": overall, "advice": advice[overall]}, indent=1))
    return 1 if overall == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
