"""Compare the light/dark pattern of a model render with its reference, band by band.

Normal Python (Pillow + numpy), run with Bash.

  python value_bands.py front_prep.png r10_front_shape.png --bands 16 --xlim 0.13 \
         --image captures/r10_front_values.png

A silhouette can match while the surface reads wrong: one white tube where the reference shows
separate plates over a dark undersuit, no dark joints, no recesses. This measures that. Both
images need alpha (the reference cut out, the render with a transparent film and its materials
or viewport colours on). Each is cropped to its silhouette, scaled to the reference height and
centred on its bbox; then, inside the silhouette, every pixel is light or dark by an Otsu
threshold on luminance computed per image (so a viewport render and a painted sheet compare
fairly; override with --light-ref / --light-model).

Per horizontal band (fraction f of the height from the top) it reports the light fraction of the
reference and of the model and flags bands whose difference exceeds --tol. --xlim keeps only
pixels within that fraction of the height from the centre line (e.g. 0.13 drops A-pose arms).
--image writes both masks side by side (light white, dark grey, flagged bands marked red).
Prints one JSON object; exit code 1 when a band is flagged.
"""

import argparse
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

CUT = 128


def load(path):
    img = np.asarray(Image.open(path).convert("RGBA")).astype(float)
    mask = img[..., 3] >= CUT
    if mask.all() or not mask.any():
        raise ValueError(f"{path}: needs a transparent background around the object")
    ys, xs = np.nonzero(mask)
    box = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
    lum = 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
    return lum, mask, box


def otsu(values):
    hist, edges = np.histogram(values, bins=256, range=(0, 256))
    total = hist.sum()
    if not total:
        return 128.0
    centres = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    m0 = np.cumsum(hist * centres)
    w1 = total - w0
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (m0[-1] * w0 / total - m0) ** 2 / (w0 * w1)
    between[~np.isfinite(between)] = 0
    return float(centres[int(np.argmax(between))])


def normalise(lum, mask, box, height):
    x0, y0, x1, y1 = box
    scale = height / (y1 - y0)
    size = (max(1, round((x1 - x0) * scale)), height)
    m = Image.fromarray((mask[y0:y1, x0:x1] * 255).astype(np.uint8)).resize(size, Image.NEAREST)
    lu = Image.fromarray(np.clip(lum[y0:y1, x0:x1], 0, 255).astype(np.uint8)).resize(
        size, Image.BILINEAR)
    return np.asarray(lu).astype(float), np.asarray(m) >= CUT


def light_fraction(light, mask, f0, f1, xlim):
    h, w = mask.shape
    ya, yb = int(f0 * h), max(int(f0 * h) + 1, int(f1 * h))
    keep = mask[ya:yb].copy()
    if xlim:
        cx = w / 2
        half = xlim * h
        cols = np.arange(w)
        keep &= (np.abs(cols - cx) <= half)[None, :]
    n = int(keep.sum())
    return (float((light[ya:yb] & keep).sum()) / n if n else None), n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("reference")
    ap.add_argument("render")
    ap.add_argument("--bands", type=int, default=12)
    ap.add_argument("--from", dest="f_from", type=float, default=0.0)
    ap.add_argument("--to", dest="f_to", type=float, default=1.0)
    ap.add_argument("--xlim", type=float, default=0.0, help="max |x - centre| as a fraction of H")
    ap.add_argument("--tol", type=float, default=0.12, help="max light-fraction difference")
    ap.add_argument("--min-pixels", type=int, default=200)
    ap.add_argument("--light-ref", type=float)
    ap.add_argument("--light-model", type=float)
    ap.add_argument("--image")
    args = ap.parse_args(argv)
    try:
        ref_lum, ref_mask, ref_box = load(args.reference)
        mod_lum, mod_mask, mod_box = load(args.render)
    except (OSError, ValueError) as exc:
        print(json.dumps({"metric": "value_bands", "error": str(exc), "verdict": "fail"}))
        return 1
    height = ref_box[3] - ref_box[1]
    ref_l, ref_m = normalise(ref_lum, ref_mask, ref_box, height)
    mod_l, mod_m = normalise(mod_lum, mod_mask, mod_box, height)
    t_ref = args.light_ref if args.light_ref is not None else otsu(ref_l[ref_m])
    t_mod = args.light_model if args.light_model is not None else otsu(mod_l[mod_m])
    ref_light, mod_light = (ref_l >= t_ref) & ref_m, (mod_l >= t_mod) & mod_m

    edges = np.linspace(args.f_from, args.f_to, args.bands + 1)
    bands, flagged = [], []
    for f0, f1 in zip(edges[:-1], edges[1:]):
        a, na = light_fraction(ref_light, ref_m, f0, f1, args.xlim)
        b, nb = light_fraction(mod_light, mod_m, f0, f1, args.xlim)
        row = {"f": [round(f0, 3), round(f1, 3)], "ref": None if a is None else round(a, 3),
               "model": None if b is None else round(b, 3)}
        if a is not None and b is not None and min(na, nb) >= args.min_pixels:
            row["delta"] = round(b - a, 3)
            if abs(b - a) > args.tol:
                flagged.append(row["f"])
                row["flag"] = "model lighter" if b > a else "model darker"
        bands.append(row)
    whole_a, _ = light_fraction(ref_light, ref_m, args.f_from, args.f_to, args.xlim)
    whole_b, _ = light_fraction(mod_light, mod_m, args.f_from, args.f_to, args.xlim)

    if args.image:
        def paint(light, mask):
            out = np.zeros(mask.shape + (3,), np.uint8)
            out[mask] = (70, 70, 70)
            out[light] = (235, 235, 235)
            return Image.fromarray(out)
        a_img, b_img = paint(ref_light, ref_m), paint(mod_light, mod_m)
        sheet = Image.new("RGB", (a_img.width + b_img.width + 12, height), (0, 0, 0))
        sheet.paste(a_img, (0, 0))
        sheet.paste(b_img, (a_img.width + 12, 0))
        draw = ImageDraw.Draw(sheet)
        for f0, f1 in flagged:
            y0, y1 = int(f0 * height), int(f1 * height)
            draw.rectangle([0, y0, sheet.width - 1, y1 - 1], outline=(255, 40, 40), width=2)
        sheet.save(args.image)

    result = {"metric": "value_bands", "files": [args.reference, args.render],
              "threshold": {"ref": round(t_ref, 1), "model": round(t_mod, 1)},
              "xlim": args.xlim, "light_fraction": {
                  "ref": None if whole_a is None else round(whole_a, 3),
                  "model": None if whole_b is None else round(whole_b, 3)},
              "bands": bands, "flagged": flagged,
              "verdict": "fail" if flagged else "pass"}
    print(json.dumps(result))
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
