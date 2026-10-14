"""Contact sheets and value checks for captures (before/after, variants, frame sequences).

  python contact_sheet.py sheet <out.png> <img> [<img> ...] [--cols 4] [--labels a,b,c] [--gray]
  python contact_sheet.py values <img> [<img> ...]
      luminance stats per image: mean, p5, p50, p95, share of crushed (<0.03) and clipped
      (>0.97) pixels — for the grayscale/value check of look-dev and lighting.
  python contact_sheet.py contrast <img> <x0,y0,x1,y1> <x0,y0,x1,y1>
      luminance contrast ratio (WCAG formula) between two regions, e.g. enemy vs background.
"""

import sys

import numpy as np
from PIL import Image, ImageDraw, ImageOps


def luminance(img):
    arr = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    lin = np.where(arr <= 0.04045, arr / 12.92, ((arr + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]


def sheet(out, paths, cols, labels, gray):
    imgs = [Image.open(p).convert("RGB") for p in paths]
    if gray:
        imgs = [ImageOps.grayscale(i).convert("RGB") for i in imgs]
    w = 640
    imgs = [i.resize((w, int(i.height * w / i.width))) for i in imgs]
    h = max(i.height for i in imgs) + 24
    rows = (len(imgs) + cols - 1) // cols
    canvas = Image.new("RGB", (w * min(cols, len(imgs)), h * rows), (20, 20, 20))
    draw = ImageDraw.Draw(canvas)
    for n, img in enumerate(imgs):
        x, y = (n % cols) * w, (n // cols) * h
        canvas.paste(img, (x, y + 24))
        draw.text((x + 6, y + 5), labels[n] if n < len(labels) else paths[n], fill=(230, 230, 230))
    canvas.save(out)
    print("sheet", out, canvas.size)


def values(paths):
    for p in paths:
        lum = luminance(Image.open(p))
        print(f"{p}: mean {lum.mean():.3f}  p5 {np.percentile(lum, 5):.3f}  "
              f"p50 {np.percentile(lum, 50):.3f}  p95 {np.percentile(lum, 95):.3f}  "
              f"crushed {100 * (lum < 0.03).mean():.1f}%  clipped {100 * (lum > 0.97).mean():.1f}%")


def contrast(path, box_a, box_b):
    lum = luminance(Image.open(path))

    def region(box):
        x0, y0, x1, y1 = (int(v) for v in box.split(","))
        return float(lum[y0:y1, x0:x1].mean())
    la, lb = region(box_a), region(box_b)
    hi, lo = max(la, lb), min(la, lb)
    print(f"L_a {la:.4f}  L_b {lb:.4f}  contrast ratio {(hi + 0.05) / (lo + 0.05):.2f}:1")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "sheet":
        cols = int(args[args.index("--cols") + 1]) if "--cols" in args else 4
        labels = args[args.index("--labels") + 1].split(",") if "--labels" in args else []
        gray = "--gray" in args
        files = [a for i, a in enumerate(args[1:], 1)
                 if not a.startswith("--") and args[i - 1] not in ("--cols", "--labels")]
        sheet(args[0], files, cols, labels, gray)
    elif cmd == "values":
        values(args)
    elif cmd == "contrast":
        contrast(args[0], args[1], args[2])
