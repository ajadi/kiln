"""Crop views out of a reference sheet (normal Python + Pillow, not Blender).

Usage:
  python crop_ref.py <sheet.png> <out_dir> front=x0,y0,x1,y1 right=x0,y0,x1,y1 ...
  python crop_ref.py <sheet.png> <out_dir> --grid 8        # writes a grid overlay to read coords
  python crop_ref.py <sheet.png> <out_dir> --auto front,back,left   # flat-backdrop sheets

Boxes are in pixels of the original sheet. Look at the sheet first (with --grid to read
coordinates), choose a tight box per view: subject's lowest point on the bottom edge, highest
point on the top edge. Also writes <view>_zoom.png at 2x for reading small details.
"""

import os
import sys

from PIL import Image, ImageDraw


def grid(sheet, out_dir, cells):
    img = Image.open(sheet).convert("RGB")
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for i in range(1, cells):
        x, y = w * i // cells, h * i // cells
        draw.line([(x, 0), (x, h)], fill=(255, 0, 0), width=1)
        draw.line([(0, y), (w, y)], fill=(255, 0, 0), width=1)
        draw.text((x + 2, 2), str(x), fill=(255, 0, 0))
        draw.text((2, y + 2), str(y), fill=(255, 0, 0))
    path = os.path.join(out_dir, "sheet_grid.png")
    img.save(path)
    print(path, img.size)


def crop(sheet, out_dir, specs):
    img = Image.open(sheet)
    for spec in specs:
        view, box = spec.split("=", 1)
        x0, y0, x1, y1 = (int(v) for v in box.split(","))
        part = img.crop((x0, y0, x1, y1))
        path = os.path.join(out_dir, f"{view}.png")
        part.save(path)
        part.resize((part.width * 2, part.height * 2), Image.LANCZOS).save(
            os.path.join(out_dir, f"{view}_zoom.png"))
        print(view, path, part.size, "aspect h/w = %.3f" % (part.height / part.width))


def runs(flags, max_gap):
    """[start, end) runs of True, bridging gaps of up to max_gap False values."""
    out, start, last = [], None, None
    for i, on in enumerate(flags):
        if on:
            if start is None:
                start = i
            elif i - last - 1 > max_gap:
                out.append((start, last + 1))
                start = i
            last = i
    if start is not None:
        out.append((start, last + 1))
    return out


def auto_boxes(sheet, expect=None, min_gap=3, min_height=0.3, threshold=28.0):
    """Tight boxes of the views on a flat-backdrop sheet, left to right. Labels under a view
    are dropped (the tallest row run in each column span is the figure). With `expect`, views
    that touch (T-pose hands) are split at the emptiest column of the widest span."""
    import numpy as np
    rgb = np.asarray(Image.open(sheet).convert("RGB")).astype(float)
    border = np.concatenate([rgb[:4].reshape(-1, 3), rgb[-4:].reshape(-1, 3),
                             rgb[:, :4].reshape(-1, 3), rgb[:, -4:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    fg = np.sqrt(((rgb - bg) ** 2).sum(axis=-1)) > threshold
    h = fg.shape[0]
    tall = fg.sum(axis=0) > 0
    spans = [s for s in runs(tall, min_gap) if fg[:, s[0]:s[1]].any(axis=1).sum() >= min_height * h]
    while expect and len(spans) < expect:
        x0, x1 = max(spans, key=lambda s: s[1] - s[0])
        lo, hi = x0 + (x1 - x0) // 5, x1 - (x1 - x0) // 5
        cut = lo + int(np.argmin(fg[:, lo:hi].sum(axis=0)))
        i = spans.index((x0, x1))
        spans[i:i + 1] = [(x0, cut), (cut + 1, x1)]
    boxes = []
    for x0, x1 in spans:
        rows = runs(fg[:, x0:x1].any(axis=1), 6)
        y0, y1 = max(rows, key=lambda r: r[1] - r[0])
        if (y1 - y0) < min_height * h:
            continue
        cols = runs(fg[y0:y1, x0:x1].any(axis=0), min_gap)
        boxes.append((x0 + cols[0][0], y0, x0 + cols[-1][1], y1))
    return boxes


if __name__ == "__main__":
    sheet_path, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    if len(sys.argv) > 3 and sys.argv[3] == "--grid":
        grid(sheet_path, out, int(sys.argv[4]) if len(sys.argv) > 4 else 8)
    elif len(sys.argv) > 3 and sys.argv[3] == "--auto":
        # python crop_ref.py <sheet> <out_dir> --auto [front,back,left]  (flat backdrop only)
        found = auto_boxes(sheet_path, expect=len(sys.argv[4].split(",")) if len(sys.argv) > 4 else None)
        names = sys.argv[4].split(",") if len(sys.argv) > 4 else [f"view{i + 1}" for i in
                                                                  range(len(found))]
        if len(names) != len(found):
            sys.exit(f"found {len(found)} views {found}, but {len(names)} names were given")
        crop(sheet_path, out, [f"{n}={','.join(map(str, b))}" for n, b in zip(names, found)])
    else:
        crop(sheet_path, out, sys.argv[3:])
