"""Prepare 1-3 reference images (photos or concept art) for modeling or image-to-3D generation.

Normal Python (Pillow + numpy), run with Bash — not through Blender.

  python prep_image.py prep front.jpg side.jpg --out-dir art/source/mech/ref_prepped --size 1024 --fill 0.88
  python prep_image.py prep photo.jpg --rembg ~/.local/share/kiln/venvs/img/Scripts/rembg.exe
  python prep_image.py prep front.png side.png --bg #fefefe   # views cropped from a flat sheet
  python prep_image.py inspect photo.jpg

prep    cut the object out (existing alpha, or rembg with the MIT birefnet-general model), crop to
        the alpha box, pad to a square canvas with the object filling --fill of the long side,
        resize to --size, save RGBA PNG. Several images are scaled by ONE common factor so their
        relative size stays true (multi-view generators never rescale views).
inspect report size, alpha, EXIF focal length (35 mm equivalent), clipped highlights and crushed
        shadows — the things that end up baked into a generated albedo.
Output: one JSON object on stdout.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import deque

import numpy as np
from PIL import ExifTags, Image

ALPHA_CUT = 128



def expand(patterns):
    """Expand glob patterns here: Windows shells pass them through unexpanded."""
    out = []
    for p in patterns:
        hits = sorted(glob.glob(p, recursive=True)) if any(c in p for c in "*?[") else [p]
        out.extend(hits or [p])
    return out

def exif_focal(img):
    try:
        exif = img.getexif()
        sub = exif.get_ifd(0x8769) if hasattr(exif, "get_ifd") else {}
        tags = {ExifTags.TAGS.get(key, key): value for key, value in {**exif, **sub}.items()}
        f35 = tags.get("FocalLengthIn35mmFilm")
        focal = tags.get("FocalLength")
        return {"focal_35mm": float(f35) if f35 else None,
                "focal_mm": float(focal) if focal else None}
    except Exception:  # EXIF is optional and often broken
        return {"focal_35mm": None, "focal_mm": None}


def inspect(path):
    img = Image.open(path)
    info = {"path": path, "size": list(img.size), "mode": img.mode, **exif_focal(img)}
    rgba = np.asarray(img.convert("RGBA"), dtype=np.uint8)
    alpha = rgba[..., 3]
    has_alpha = bool((alpha < 255).any())
    flat = flat_background(rgba[..., :3]) if not has_alpha else None
    if has_alpha:
        mask = alpha >= ALPHA_CUT
    elif flat is not None:
        mask = foreground_mask(rgba[..., :3], flat)
        info["flat_background"] = "#%02x%02x%02x" % tuple(int(v) for v in flat)
    else:
        mask = np.ones(alpha.shape, bool)
    rgb = rgba[..., :3][mask]
    info["has_alpha"] = has_alpha
    info["coverage"] = round(float(mask.mean()), 4)
    if rgb.size:
        info["clipped_highlights"] = round(float((rgb.min(axis=1) >= 250).mean()), 4)
        info["crushed_shadows"] = round(float((rgb.max(axis=1) <= 5).mean()), 4)
    warnings = []
    if min(img.size) < 768:
        warnings.append("short side under 768 px: fine detail will be invented")
    if info.get("clipped_highlights", 0) > 0.02:
        warnings.append("over 2% clipped highlights: specular will bake into the albedo")
    if info.get("crushed_shadows", 0) > 0.05:
        warnings.append("over 5% crushed shadows: shading will bake into the albedo")
    if info["focal_35mm"] and info["focal_35mm"] < 35:
        warnings.append("wide lens (<35 mm eq.): perspective distortion; reshoot from further "
                        "away with a longer lens if proportions matter")
    if has_alpha:
        soft = ((alpha > 10) & (alpha < 245)).sum() / max(1, (alpha > 10).sum())
        info["soft_edge_fraction"] = round(float(soft), 4)
    info["warnings"] = warnings
    return info


def flat_background(rgb, tolerance=12.0, share=0.9):
    """Median border colour if the image sits on a flat backdrop (concept sheets, renders on
    white or grey), else None. The subject may touch the border (a T-pose hand), so the test is
    that most border pixels sit near the median, not that all of them do."""
    border = np.concatenate([rgb[:4].reshape(-1, 3), rgb[-4:].reshape(-1, 3),
                             rgb[:, :4].reshape(-1, 3), rgb[:, -4:].reshape(-1, 3)]).astype(float)
    median = np.median(border, axis=0)
    close = np.sqrt(((border - median) ** 2).sum(axis=1)) <= tolerance
    return median if close.mean() >= share else None


def foreground_mask(rgb, bg, threshold=28.0):
    """Everything not connected to the border through backdrop-coloured pixels. A plain colour
    threshold would punch holes where white armour highlights match a white backdrop."""
    near = np.sqrt(((rgb.astype(float) - bg) ** 2).sum(axis=-1)) <= threshold
    h, w = near.shape
    background = np.zeros_like(near)
    queue = deque()
    for y in range(h):
        for x in (0, w - 1):
            if near[y, x] and not background[y, x]:
                background[y, x] = True
                queue.append((y, x))
    for x in range(w):
        for y in (0, h - 1):
            if near[y, x] and not background[y, x]:
                background[y, x] = True
                queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and near[ny, nx] and not background[ny, nx]:
                background[ny, nx] = True
                queue.append((ny, nx))
    dist = np.sqrt(((rgb.astype(float) - bg) ** 2).sum(axis=-1))
    # backdrop seen through a gap closed by a contact shadow (between the legs): a large
    # enclosed region of almost exactly the backdrop colour; armour highlights are small or
    # not that uniform
    seen = background.copy()
    for y0, x0 in zip(*np.nonzero(near & ~background)):
        if seen[y0, x0]:
            continue
        region, queue = [(y0, x0)], deque([(y0, x0)])
        seen[y0, x0] = True
        while queue:
            y, x = queue.popleft()
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and near[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    region.append((ny, nx))
                    queue.append((ny, nx))
        ys, xs = np.array(region).T
        if len(region) >= 0.001 * h * w and dist[ys, xs].mean() <= 4:
            background[ys, xs] = True
    fg = ~background
    # soft contact shadow under the feet: light and colourless, in the bottom 4% of the subject,
    # and below the lowest non-shadow pixel of its column (so white toe caps above a dark sole
    # stay)
    rows = np.nonzero(fg.any(axis=1))[0]
    if len(rows):
        top, bottom = rows.min(), rows.max()
        y0 = int(bottom - 0.04 * (bottom - top))
        px = rgb[y0:bottom + 1].astype(int)
        shadow = (px.max(axis=-1) - px.min(axis=-1) < 10) & (px.mean(axis=-1) > 200)
        solid = fg[y0:bottom + 1] & ~shadow
        for x in range(w):
            ys = np.nonzero(solid[:, x])[0]
            start = ys.max() + 1 if len(ys) else 0
            fg[y0 + start:bottom + 1, x] &= ~shadow[start:, x]
    return fg


def matte(path, rembg, bg_hex=None):
    """Return an RGBA image: existing alpha, a flat-backdrop cut-out, or rembg
    birefnet-general (MIT) output."""
    img = Image.open(path).convert("RGBA")
    if (np.asarray(img)[..., 3] < 255).any():
        return img, "existing alpha"
    rgb = np.asarray(img)[..., :3]
    bg = (np.array([int(bg_hex.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4)], float)
          if bg_hex else flat_background(rgb))
    if bg is not None:
        alpha = (foreground_mask(rgb, bg) * 255).astype(np.uint8)
        out = np.dstack([rgb, alpha])
        return Image.fromarray(out, "RGBA"), "flat backdrop %s" % "#%02x%02x%02x" % tuple(
            int(v) for v in bg)
    exe = shutil.which(rembg) if rembg else shutil.which("rembg")
    if not exe:
        raise SystemExit(json.dumps({"error": f"{path} has no alpha and rembg was not found. "
                                     "Install rembg in a user-level venv and pass --rembg, or "
                                     "cut the object out by hand."}))
    out = os.path.join(tempfile.mkdtemp(prefix="kiln-matte-"), "m.png")
    # never the rembg default model (bria-rmbg is CC BY-NC); birefnet-general is MIT
    subprocess.run([exe, "i", "-m", "birefnet-general", path, out], check=True,
                   capture_output=True, timeout=600)
    return Image.open(out).convert("RGBA"), "rembg birefnet-general"


def prep(paths, out_dir, size, fill, rembg, bg_hex=None):
    os.makedirs(out_dir, exist_ok=True)
    cut = []
    for path in paths:
        img, how = matte(path, rembg, bg_hex)
        alpha = np.asarray(img)[..., 3]
        ys, xs = np.nonzero(alpha >= ALPHA_CUT)
        if not len(xs):
            raise SystemExit(json.dumps({"error": f"{path}: empty alpha after matting"}))
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        cut.append((path, img.crop(box), how, box))
    longest = max(max(c.size) for _, c, _, _ in cut)
    scale = fill * size / longest  # one factor for every view
    results = []
    for path, crop, how, box in cut:
        w, h = crop.size
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(crop.resize((nw, nh), Image.LANCZOS), ((size - nw) // 2, (size - nh) // 2))
        name = os.path.splitext(os.path.basename(path))[0] + "_prep.png"
        out = os.path.join(out_dir, name)
        canvas.save(out)
        results.append({"source": path, "out": out, "matte": how, "source_box": list(box),
                        "object_px": [nw, nh], "aspect_h_over_w": round(h / w, 4)})
    return {"size": size, "fill": fill, "scale": round(scale, 6), "images": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prep")
    p.add_argument("images", nargs="+")
    p.add_argument("--out-dir", default="ref_prepped")
    p.add_argument("--size", type=int, default=1024)
    p.add_argument("--fill", type=float, default=0.88)
    p.add_argument("--rembg", default=None)
    p.add_argument("--bg", default=None, help="backdrop colour #rrggbb when views were cropped "
                   "tight from a sheet (the subject touches the crop edges)")
    i = sub.add_parser("inspect")
    i.add_argument("images", nargs="+")
    args = parser.parse_args(argv)
    if hasattr(args, "images"):
        args.images = expand(args.images)
    if args.cmd == "prep":
        result = prep(args.images, args.out_dir, args.size, args.fill, args.rembg, args.bg)
        result["inspect"] = [inspect(path) for path in args.images]
    else:
        result = [inspect(path) for path in args.images]
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
