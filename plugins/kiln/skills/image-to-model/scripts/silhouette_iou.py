"""Compare the silhouette of a model render with the reference image it was built from.

Normal Python (Pillow + numpy), run with Bash.

  python silhouette_iou.py front_prep.png front_render.png --min 0.90 --diff captures/front_diff.png
  python silhouette_iou.py --pairs front_prep.png:front_r.png side_prep.png:side_r.png --min 0.85

Both images need alpha (render with a transparent film background). The render silhouette is
fitted to the reference by bounding box (scale to the same height, centre on the same point), so
framing differences do not count — proportions and shape do. Reports, per pair:
  iou           fitted silhouette IoU (shape agreement)
  raw_iou       IoU without fitting (framing check for matched cameras)
  aspect_delta  relative difference of bbox height/width (proportion drift)
  verdict       pass if iou >= --min and |aspect_delta| <= --max-aspect
The --diff image paints reference-only pixels red, render-only blue, shared white — read it to see
where the model is too thin, too wide or missing a part. Thresholds are starting points: calibrate
them on a model the art-director accepted.
"""

import argparse
import json
import sys

import numpy as np
from PIL import Image

CUT = 128


def mask_of(path):
    img = Image.open(path).convert("RGBA")
    alpha = np.asarray(img)[..., 3]
    if not (alpha < 255).any():
        raise SystemExit(json.dumps({"error": f"{path} has no transparency; render with a "
                                     "transparent film / cut the reference out first"}))
    return alpha >= CUT


def bbox(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def fit(mask, ref_box, shape):
    """Scale and move mask so its bbox height and centre match ref_box, on a canvas of shape."""
    box = bbox(mask)
    x0, y0, x1, y1 = box
    rx0, ry0, rx1, ry1 = ref_box
    scale = (ry1 - ry0) / (y1 - y0)
    crop = Image.fromarray((mask[y0:y1, x0:x1] * 255).astype(np.uint8))
    nw, nh = max(1, round((x1 - x0) * scale)), max(1, round((y1 - y0) * scale))
    crop = crop.resize((nw, nh), Image.NEAREST)
    canvas = Image.new("L", (shape[1], shape[0]), 0)
    cx, cy = (rx0 + rx1) / 2, (ry0 + ry1) / 2
    canvas.paste(crop, (round(cx - nw / 2), round(cy - nh / 2)))
    return np.asarray(canvas) >= CUT


def iou(a, b):
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 0.0


def compare(ref_path, render_path, min_iou, max_aspect, diff_path=None):
    ref = mask_of(ref_path)
    ren = mask_of(render_path)
    if ren.shape != ref.shape:
        img = Image.fromarray((ren * 255).astype(np.uint8)).resize(
            (ref.shape[1], ref.shape[0]), Image.NEAREST)
        ren = np.asarray(img) >= CUT
    rb, nb = bbox(ref), bbox(ren)
    if rb is None or nb is None:
        return {"ref": ref_path, "render": render_path, "verdict": "fail",
                "error": "empty silhouette"}
    fitted = fit(ren, rb, ref.shape)
    ref_aspect = (rb[3] - rb[1]) / (rb[2] - rb[0])
    ren_aspect = (nb[3] - nb[1]) / (nb[2] - nb[0])
    aspect_delta = ren_aspect / ref_aspect - 1
    score = iou(ref, fitted)
    if diff_path:
        out = np.zeros(ref.shape + (3,), np.uint8)
        out[ref & ~fitted] = (230, 40, 40)
        out[~ref & fitted] = (40, 90, 230)
        out[ref & fitted] = (255, 255, 255)
        Image.fromarray(out).save(diff_path)
    ok = score >= min_iou and abs(aspect_delta) <= max_aspect
    return {"ref": ref_path, "render": render_path, "iou": round(score, 4),
            "raw_iou": round(iou(ref, ren), 4), "aspect_delta": round(float(aspect_delta), 4),
            "ref_only_px": int((ref & ~fitted).sum()), "render_only_px": int((~ref & fitted).sum()),
            "threshold": min_iou, "verdict": "pass" if ok else "fail", "diff": diff_path}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ref", nargs="?")
    parser.add_argument("render", nargs="?")
    parser.add_argument("--pairs", nargs="*", default=[], help="ref.png:render.png ...")
    parser.add_argument("--min", type=float, default=0.90)
    parser.add_argument("--max-aspect", type=float, default=0.05)
    parser.add_argument("--diff", default=None, help="diff image (single pair only)")
    args = parser.parse_args(argv)
    pairs = [p.rsplit(":", 1) for p in args.pairs]
    if args.ref and args.render:
        pairs.insert(0, [args.ref, args.render])
    if not pairs:
        parser.error("give ref and render, or --pairs")
    results = [compare(r, n, args.min, args.max_aspect, args.diff if len(pairs) == 1 else None)
               for r, n in pairs]
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(results if len(results) > 1 else results[0], indent=1))
    sys.exit(0 if all(r["verdict"] == "pass" for r in results) else 1)


if __name__ == "__main__":
    main()
