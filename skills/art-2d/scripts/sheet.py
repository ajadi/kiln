"""Sprite sheets: pack frames, validate a sheet, print the Godot setup. Pillow + numpy, run with Bash.

  python sheet.py pack "art/hero/*.png" --out art/hero/hero.png --data art/hero/hero.json
         [--layout grid|packed] [--padding 1] [--extrude 1] [--border 0] [--trim] [--columns N]
         [--fps 10] [--tag-fps run=12,idle=6] [--once attack,death] [--pingpong idle]
         [--pivot bottom|center|x,y] [--max-size 4096] [--pot] [--dedupe]
  python sheet.py check art/hero/hero.json [--padding 1] [--extrude 1] [--max-size 4096]
  python sheet.py godot art/hero/hero.json --res-dir res://art/hero --parent Main/Hero
         [--setup player|frames] [--node Sprite] [--player AnimationPlayer] [--pixel-art]
  python sheet.py preview "art/hero/*.png" --out production/captures/T12/hero [--fps 10]
         [--tag-fps run=12] [--scale 4]      # a GIF per tag at game speed + a numbered contact sheet

pack   frames named <tag>_<index>.png or <tag>-<index>.png, or one folder per tag (frames in name
       order), become animations. Writes the sheet PNG and an Aseprite-compatible json-array data
       file: frames[] {filename, frame, rotated, trimmed, spriteSourceSize, sourceSize, duration,
       pivot}, meta {app, version, image, format, size, scale, frameTags[], kiln{}}.
       grid   = one row per tag; with --padding 0 --extrude 0 and no --trim it is hframes/vframes
                compatible. packed = MaxRects best-short-side-fit (Jylanki 2010), no rotation.
       --trim crops transparent borders; spriteSourceSize keeps where the crop sat in its canvas
       and pivot (normalised to sourceSize, default bottom = feet) survives the crop.
check  bounds, overlaps, gaps vs padding (+2*extrude), extrude pixels, trim fields, rotation,
       tag ranges/names/order/direction, durations, canvas per tag, texture size. Also reads
       Aseprite / TexturePacker json-array or json-hash files.
godot  prints the Godot AI MCP calls (tool, params) that build the animation in the open editor:
       setup player (default) = Sprite2D + AnimationPlayer (frame or region_rect + offset tracks,
       hitboxes keyable on the same clip); setup frames = AtlasTexture resources + SpriteFrames
       values for AnimatedSprite2D. This script writes nothing into the project.
Glob patterns are expanded by the script (quote them on Windows). Output: JSON with "verdict";
exit code 1 on fail.
"""

import argparse
import glob
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter

import numpy as np
from PIL import Image

IMG_EXT = (".png", ".bmp", ".gif", ".tga", ".webp")
FRAME_RE = re.compile(r"^(?P<tag>.+?)[_-](?P<idx>\d+)$")
DIRECTIONS = ("forward", "reverse", "pingpong", "pingpong_reverse")


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def emit(result, ok=None):
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, indent=1))
    if ok is None:
        ok = result.get("verdict") != "fail"
    sys.exit(0 if ok else 1)


# ---------------------------------------------------------------- inputs

def expand_inputs(inputs):
    """-> list of (tag, index, path, filename). Globs, files and folders (one per tag)."""
    items = []
    for arg in inputs:
        paths = sorted(glob.glob(arg), key=natural_key) if any(c in arg for c in "*?[") else [arg]
        if not paths:
            raise SystemExit(f"no files match {arg}")
        for p in paths:
            if os.path.isdir(p):
                items += folder_frames(p)
            elif p.lower().endswith(IMG_EXT):
                if not os.path.isfile(p):
                    raise SystemExit(f"not found: {p}")
                stem = os.path.splitext(os.path.basename(p))[0]
                m = FRAME_RE.match(stem)
                tag, idx = (m["tag"], int(m["idx"])) if m else (stem, 0)
                items.append((tag, idx, p, os.path.basename(p)))
    return items


def folder_frames(folder):
    items = []
    names = sorted(os.listdir(folder), key=natural_key)
    files = [n for n in names if n.lower().endswith(IMG_EXT)
             and os.path.isfile(os.path.join(folder, n))]
    tag = os.path.basename(os.path.normpath(folder))
    for i, n in enumerate(files):
        items.append((tag, i, os.path.join(folder, n), f"{tag}/{n}"))
    for n in names:
        sub = os.path.join(folder, n)
        if os.path.isdir(sub):
            items += folder_frames(sub)
    return items


def group_frames(items):
    order, tags = [], {}
    for tag, idx, path, fname in items:
        if tag not in tags:
            tags[tag] = {}
            order.append(tag)
        if idx in tags[tag]:
            raise SystemExit(f"duplicate frame {tag} #{idx}: {tags[tag][idx][0]} and {path}")
        tags[tag][idx] = (path, fname)
    return [(t, [tags[t][i] for i in sorted(tags[t])]) for t in order]


def parse_map(text, cast=float):
    out = {}
    for part in filter(None, (text or "").split(",")):
        k, _, v = part.partition("=")
        out[k.strip()] = cast(v)
    return out


def parse_pivot(spec, w, h):
    if spec in (None, "", "bottom"):
        return w // 2, h
    if spec == "center":
        return w // 2, h // 2
    x, y = (int(v) for v in spec.split(","))
    return x, y


def trim_box(rgba):
    ys, xs = np.nonzero(rgba[..., 3] > 0)
    if len(xs) == 0:
        return 0, 0, 1, 1  # fully transparent frame: keep a 1x1 sample (as Aseprite does)
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)


# ---------------------------------------------------------------- MaxRects (Jylanki 2010)

class MaxRects:
    """Free-rectangle list; best short side fit, ties by best long side fit; no rotation."""

    def __init__(self, w, h):
        self.free = [(0, 0, w, h)]

    def find(self, w, h):
        best = None
        for fx, fy, fw, fh in self.free:
            if fw >= w and fh >= h:
                lh, lv = fw - w, fh - h
                score = (min(lh, lv), max(lh, lv), fy, fx)
                if best is None or score < best[0]:
                    best = (score, fx, fy)
        return None if best is None else (best[1], best[2])

    def place(self, x, y, w, h):
        kept, new = [], []
        for fx, fy, fw, fh in self.free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                kept.append((fx, fy, fw, fh))
                continue
            if x > fx:
                new.append((fx, fy, x - fx, fh))
            if x + w < fx + fw:
                new.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy:
                new.append((fx, fy, fw, y - fy))
            if y + h < fy + fh:
                new.append((fx, y + h, fw, fy + fh - y - h))
        # kept rects were already maximal; a split piece can only be inside another rect
        new = list(dict.fromkeys(new))

        def inside(a, b):
            return b[0] <= a[0] and b[1] <= a[1] and a[0] + a[2] <= b[0] + b[2] and \
                a[1] + a[3] <= b[1] + b[3]
        self.free = kept + [a for i, a in enumerate(new)
                            if not any(inside(a, b) for b in kept)
                            and not any(j != i and inside(a, b) for j, b in enumerate(new))]


ORDERS = (lambda s: (-s[0] * s[1], -max(s), -min(s)),
          lambda s: (-max(s), -min(s)),
          lambda s: (-s[1], -s[0]))


def pack_rects(sizes, limit_w, limit_h, pot=False):
    """sizes: inflated (w, h). Returns (positions, used_w, used_h) of the smallest bin found."""
    if not sizes:
        return [], 0, 0
    maxw, maxh = max(s[0] for s in sizes), max(s[1] for s in sizes)
    if maxw > limit_w or maxh > limit_h:
        return None
    area = sum(w * h for w, h in sizes)
    if pot:
        widths = [1 << k for k in range(0, 15) if maxw <= (1 << k) <= limit_w]
    else:
        lo, hi = maxw, min(limit_w, max(maxw, int(math.ceil(math.sqrt(area) * 2))))
        widths = sorted({lo, hi, min(hi, max(lo, int(math.ceil(math.sqrt(area)))))} |
                        {int(v) for v in np.linspace(lo, hi, 16)})
    best = None
    for width in widths:
        for key in ORDERS:
            order = sorted(range(len(sizes)), key=lambda i: key(sizes[i]))
            bins = MaxRects(width, limit_h)
            pos = [None] * len(sizes)
            for i in order:
                spot = bins.find(*sizes[i])
                if spot is None:
                    break
                bins.place(spot[0], spot[1], *sizes[i])
                pos[i] = spot
            else:
                uw = max(p[0] + s[0] for p, s in zip(pos, sizes))
                uh = max(p[1] + s[1] for p, s in zip(pos, sizes))
                if pot:
                    uw, uh = next_pow2(uw), next_pow2(uh)
                    if uh > limit_h:
                        continue
                score = (max(uw, uh), uw * uh)  # squarest first, then smallest area
                if best is None or score < best[0]:
                    best = (score, pos, uw, uh)
    return None if best is None else (best[1], best[2], best[3])


def next_pow2(v):
    return 1 << max(0, int(v - 1).bit_length())


# ---------------------------------------------------------------- pack

def cmd_pack(a):
    try:
        groups = group_frames(expand_inputs(a.frames))
    except SystemExit as e:
        emit({"problems": [str(e)], "verdict": "fail"})
    if not groups:
        emit({"problems": ["no frames found"], "verdict": "fail"})
    tag_fps = parse_map(a.tag_fps)
    once = set(filter(None, (a.once or "").split(",")))
    pingpong = set(filter(None, (a.pingpong or "").split(",")))
    pad, ext, border = a.padding, a.extrude, a.border
    warnings, problems = [], []
    if a.layout == "grid" and a.dedupe:
        warnings.append("--dedupe ignored for grid layout (every frame keeps its cell)")
    if a.layout == "packed" and a.columns:
        warnings.append("--columns ignored for packed layout")

    frames, uniques, ukey = [], [], {}
    for tag, entries in groups:
        sizes = set()
        for path, fname in entries:
            img = np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8)
            h, w = img.shape[:2]
            sizes.add((w, h))
            box = trim_box(img) if a.trim else (0, 0, w, h)
            crop = img[box[1]:box[1] + box[3], box[0]:box[0] + box[2]]
            if a.layout == "packed" and a.dedupe:
                k = (crop.shape, hashlib.sha1(crop.tobytes()).hexdigest())
            else:
                k = len(uniques)
            if k not in ukey:
                ukey[k] = len(uniques)
                uniques.append(crop)
            px, py = parse_pivot(a.pivot, w, h)
            fps = tag_fps.get(tag, a.fps)
            frames.append({"tag": tag, "filename": fname, "u": ukey[k], "box": box,
                           "src": (w, h), "pivot": (px / w, py / h),
                           "duration": max(1, int(round(1000.0 / fps)))})
        if len(sizes) > 1:
            warnings.append(f"tag {tag}: frame canvases differ {sorted(sizes)} - use one fixed "
                            "canvas per animation so the pivot does not jump")

    # layout -> top-left of each unique image's inner (non-extruded) rect
    places = [None] * len(uniques)
    cell = (max(u.shape[1] for u in uniques), max(u.shape[0] for u in uniques))
    columns = 0
    if a.layout == "grid":
        pitch_x, pitch_y = cell[0] + 2 * ext + pad, cell[1] + 2 * ext + pad
        longest = max(len(e) for _, e in groups)
        columns = a.columns or longest
        fit = max(1, (a.max_size - 2 * border + pad) // pitch_x)
        if columns > fit:
            warnings.append(f"columns {columns} reduced to {fit} to fit --max-size {a.max_size}")
            columns = fit
        row, i = 0, 0
        for tag, entries in groups:
            for n in range(len(entries)):
                if n and n % columns == 0:
                    row += 1
                places[frames[i]["u"]] = (border + (n % columns) * pitch_x + ext,
                                          border + row * pitch_y + ext)
                i += 1
            row += 1
        width = 2 * border + columns * pitch_x - pad
        height = 2 * border + row * pitch_y - pad
        if a.pot:
            width, height = next_pow2(width), next_pow2(height)
    else:
        sizes = [(u.shape[1] + 2 * ext + pad, u.shape[0] + 2 * ext + pad) for u in uniques]
        limit = a.max_size - 2 * border + pad
        res = pack_rects(sizes, limit, limit, a.pot)
        if res is None:
            emit({"problems": [f"frames do not fit in {a.max_size}x{a.max_size} (raise "
                               "--max-size, reduce padding or split the sheet)"],
                  "verdict": "fail"})
        pos, uw, uh = res
        places = [(border + p[0] + ext, border + p[1] + ext) for p in pos]
        width, height = uw - pad + 2 * border, uh - pad + 2 * border
        if a.pot:
            width, height = next_pow2(width), next_pow2(height)
    if width > a.max_size or height > a.max_size:
        problems.append(f"sheet {width}x{height} exceeds --max-size {a.max_size}")

    sheet = np.zeros((height, width, 4), np.uint8)
    for u, (x, y) in zip(uniques, places):
        block = np.pad(u, ((ext, ext), (ext, ext), (0, 0)), mode="edge") if ext else u
        sheet[y - ext:y - ext + block.shape[0], x - ext:x - ext + block.shape[1]] = block

    out_dir = os.path.dirname(os.path.abspath(a.data))
    image_rel = os.path.relpath(os.path.abspath(a.out), out_dir).replace("\\", "/")
    data_frames, tags_meta, start = [], [], 0
    for tag, entries in groups:
        for f in frames[start:start + len(entries)]:
            x, y = places[f["u"]]
            bx, by, bw, bh = f["box"]
            sw, sh = f["src"]
            data_frames.append({
                "filename": f["filename"],
                "frame": {"x": x, "y": y, "w": bw, "h": bh},
                "rotated": False,
                "trimmed": (bx, by, bw, bh) != (0, 0, sw, sh),
                "spriteSourceSize": {"x": bx, "y": by, "w": bw, "h": bh},
                "sourceSize": {"w": sw, "h": sh},
                "duration": f["duration"],
                "pivot": {"x": round(f["pivot"][0], 6), "y": round(f["pivot"][1], 6)}})
        t = {"name": tag, "from": start, "to": start + len(entries) - 1,
             "direction": "pingpong" if tag in pingpong else "forward"}
        if tag in once:
            t["repeat"] = "1"
        tags_meta.append(t)
        start += len(entries)
    hcompat = (a.layout == "grid" and pad == 0 and ext == 0 and border == 0
               and width == columns * cell[0] and height % cell[1] == 0
               and all(not df["trimmed"] and df["frame"]["w"] == cell[0]
                       and df["frame"]["h"] == cell[1] for df in data_frames))
    data = {"frames": data_frames, "meta": {
        "app": "kiln art-2d sheet.py", "version": "1", "image": image_rel, "format": "RGBA8888",
        "size": {"w": width, "h": height}, "scale": "1", "frameTags": tags_meta,
        "kiln": {"layout": a.layout, "padding": pad, "extrude": ext, "border": border,
                 "columns": columns, "cell": {"w": cell[0], "h": cell[1]}, "trim": a.trim,
                 "pivot": a.pivot or "bottom", "pot": a.pot, "dedupe": a.dedupe,
                 "hframes_compatible": hcompat}}}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)
    Image.fromarray(sheet, "RGBA").save(a.out)
    with open(a.data, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    used = sum(u.shape[0] * u.shape[1] for u in uniques)
    if max(width, height) > 4096 and a.max_size > 4096:
        warnings.append("sheet larger than 4096 px: mobile/web GPUs usually cannot show it")
    emit({"image": a.out, "data": a.data, "size": [width, height], "layout": a.layout,
          "frames": len(frames), "unique_frames": len(uniques),
          "tags": [{"name": t["name"], "frames": t["to"] - t["from"] + 1,
                    "fps": nice_fps(frames[t["from"]]["duration"]),
                    "direction": t["direction"], "repeat": t.get("repeat")} for t in tags_meta],
          "fill_ratio": round(used / float(width * height), 3),
          "hframes_compatible": hcompat, "warnings": warnings, "problems": problems,
          "verdict": "fail" if problems else "pass"})


# ---------------------------------------------------------------- check

def load_sheet(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    frames = data.get("frames", [])
    if isinstance(frames, dict):  # json-hash
        frames = [dict(v, filename=k) for k, v in frames.items()]
    return frames, data.get("meta", {})


def rect(f):
    r = f.get("frame", {})
    return int(r.get("x", 0)), int(r.get("y", 0)), int(r.get("w", 0)), int(r.get("h", 0))


def gap(a, b):
    dx = max(0, b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]))
    dy = max(0, b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]))
    return max(dx, dy)


def overlaps(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def check_sheet(path, padding=None, extrude=None, max_size=4096):
    problems, warnings = [], []
    try:
        frames, meta = load_sheet(path)
    except (OSError, ValueError) as e:
        return {"file": path, "problems": [f"cannot read: {e}"], "warnings": [], "verdict": "fail"}
    kiln = meta.get("kiln", {})
    pad = padding if padding is not None else kiln.get("padding")
    ext = extrude if extrude is not None else kiln.get("extrude", 0)
    n = len(frames)
    if not n:
        problems.append("no frames")
    size = meta.get("size", {})
    sw, sh = int(size.get("w", 0)), int(size.get("h", 0))
    img = None
    img_path = os.path.join(os.path.dirname(os.path.abspath(path)), meta.get("image", ""))
    if meta.get("image") and os.path.isfile(img_path):
        img = np.asarray(Image.open(img_path).convert("RGBA"), dtype=np.uint8)
        if (sw, sh) != (img.shape[1], img.shape[0]):
            problems.append(f"meta.size {sw}x{sh} != image {img.shape[1]}x{img.shape[0]}")
        sw, sh = img.shape[1], img.shape[0]
    elif meta.get("image"):
        warnings.append(f"image {meta.get('image')} not found next to the data file; pixel "
                        "checks skipped")
    if not (sw and sh):
        problems.append("sheet size unknown (meta.size missing and no image)")
    if max(sw, sh) > max_size:
        problems.append(f"sheet {sw}x{sh} exceeds --max-size {max_size} (mobile/web: 4096; "
                        "desktop GPUs commonly 16384)")
    pot = sw > 0 and sh > 0 and sw & (sw - 1) == 0 and sh & (sh - 1) == 0

    rects, no_duration = [], 0
    for i, f in enumerate(frames):
        r = rect(f)
        rects.append(r)
        name = f.get("filename", f"#{i}")
        if r[2] <= 0 or r[3] <= 0:
            problems.append(f"{name}: empty frame rect {r}")
        if r[0] < 0 or r[1] < 0 or r[0] + r[2] > sw or r[1] + r[3] > sh:
            problems.append(f"{name}: frame {r} outside the {sw}x{sh} sheet")
        if f.get("rotated"):
            problems.append(f"{name}: rotated frame - Godot regions/AtlasTexture cannot rotate; "
                            "export without rotation")
        sss, src = f.get("spriteSourceSize"), f.get("sourceSize")
        if sss and src:
            if (sss["w"], sss["h"]) != r[2:]:
                problems.append(f"{name}: spriteSourceSize {sss['w']}x{sss['h']} != frame "
                                f"{r[2]}x{r[3]}")
            if sss["x"] < 0 or sss["y"] < 0 or sss["x"] + sss["w"] > src["w"] or \
                    sss["y"] + sss["h"] > src["h"]:
                problems.append(f"{name}: spriteSourceSize outside sourceSize")
            is_trim = (sss["x"], sss["y"], sss["w"], sss["h"]) != (0, 0, src["w"], src["h"])
            if "trimmed" in f and bool(f["trimmed"]) != is_trim:
                warnings.append(f"{name}: trimmed={f['trimmed']} but spriteSourceSize says "
                                f"{is_trim}")
        else:
            warnings.append(f"{name}: no spriteSourceSize/sourceSize - pivot cannot be restored")
        d = f.get("duration")
        if d is None:
            no_duration += 1
        elif not isinstance(d, (int, float)) or d <= 0:
            problems.append(f"{name}: duration {d!r} must be > 0 ms")
        elif d < 16:
            warnings.append(f"{name}: duration {d} ms is shorter than one 60 Hz frame")

    if no_duration:
        warnings.append(f"{no_duration} frames without duration (TexturePacker data): godot "
                        "uses --fps")
    distinct = sorted(set(rects))
    min_gap, bad = None, []
    order = sorted(range(len(distinct)), key=lambda i: distinct[i][0])
    for ii, i in enumerate(order):
        a = distinct[i]
        for j in order[ii + 1:]:
            b = distinct[j]
            if b[0] - (a[0] + a[2]) >= (min_gap if min_gap is not None else 1 << 30):
                break
            if overlaps(a, b):
                bad.append((a, b))
                continue
            g = gap(a, b)
            min_gap = g if min_gap is None else min(min_gap, g)
    if bad:
        problems.append(f"{len(bad)} overlapping frame pairs, e.g. {bad[0][0]} and {bad[0][1]}")
    need = None if pad is None else pad + 2 * (ext or 0)
    if need is not None and min_gap is not None and min_gap < need:
        problems.append(f"smallest gap between frames {min_gap} px < padding {pad} + 2 x extrude "
                        f"{ext} = {need} px: filtering will bleed neighbours")
    elif need is None and min_gap == 0:
        warnings.append("frames touch (gap 0): fine for nearest-filtered pixel art at integer "
                        "positions, bleeds with linear filtering or mipmaps")

    if img is not None and ext:
        broken = 0
        for x, y, w, h in distinct:
            if x - ext < 0 or y - ext < 0 or x + w + ext > sw or y + h + ext > sh:
                broken += 1
                continue
            ring = img[y - ext:y + h + ext, x - ext:x + w + ext]
            want = np.pad(img[y:y + h, x:x + w], ((ext, ext), (ext, ext), (0, 0)), mode="edge")
            broken += int(not np.array_equal(ring, want))
        if broken:
            problems.append(f"{broken} frames lack a {ext}px extrude ring of their edge pixels")

    tags_out = []
    tags = meta.get("frameTags")
    if not tags:
        warnings.append("no meta.frameTags: the whole sheet plays as one animation")
        tags = []
    names = Counter(t.get("name") for t in tags)
    for name, c in names.items():
        if c > 1:
            problems.append(f"tag {name!r} appears {c} times (animation names must be unique)")
    covered = set()
    last_from = -1
    for t in tags:
        fr, to = t.get("from"), t.get("to")
        name = t.get("name")
        direction = t.get("direction", "forward")
        if direction not in DIRECTIONS:
            problems.append(f"tag {name!r}: direction {direction!r} not in {DIRECTIONS}")
        rep = t.get("repeat")
        if rep is not None and not str(rep).isdigit():
            problems.append(f"tag {name!r}: repeat {rep!r} must be a number string")
        if not isinstance(fr, int) or not isinstance(to, int) or not 0 <= fr <= to < n:
            problems.append(f"tag {name!r}: range {fr}..{to} invalid for {n} frames")
            continue
        if fr < last_from:
            warnings.append(f"tag {name!r} starts at {fr}, before the previous tag: tags out of "
                            "timeline order")
        last_from = fr
        if covered & set(range(fr, to + 1)):
            warnings.append(f"tag {name!r} overlaps another tag")
        covered |= set(range(fr, to + 1))
        canv ={(frames[i].get("sourceSize", {}).get("w"), frames[i].get("sourceSize", {}).get("h"))
                for i in range(fr, to + 1)}
        if len(canv) > 1:
            warnings.append(f"tag {name!r}: canvas sizes differ {sorted(canv)} - pivot jumps")
        durs = [frames[i].get("duration") for i in range(fr, to + 1)]
        tags_out.append({"name": name, "from": fr, "to": to, "direction": direction,
                         "repeat": rep, "durations_ms": durs,
                         "length_ms": sum(d for d in durs if isinstance(d, (int, float)))})
    if tags and n:
        orphans = sorted(set(range(n)) - covered)
        if orphans:
            warnings.append(f"{len(orphans)} frames are in no tag (e.g. #{orphans[0]})")
    return {"file": path, "size": [sw, sh], "power_of_two": pot, "frames": n,
            "distinct_rects": len(distinct), "min_gap_px": min_gap, "required_gap_px": need,
            "tags": tags_out, "warnings": warnings, "problems": problems,
            "verdict": "fail" if problems else "pass"}


def cmd_check(a):
    paths = []
    for p in a.sheets:
        paths += sorted(glob.glob(p), key=natural_key) if any(c in p for c in "*?[") else [p]
    results = [check_sheet(p, a.padding, a.extrude, a.max_size) for p in paths]
    emit(results[0] if len(results) == 1 else results,
         all(r["verdict"] == "pass" for r in results))


# ---------------------------------------------------------------- godot

def nice_fps(ms):
    f = 1000.0 / ms
    r = round(f)
    return float(r) if r and round(1000.0 / r) == ms else round(f, 4)


def sequence(tag):
    fr, to = tag["from"], tag["to"]
    fwd = list(range(fr, to + 1))
    direction = tag.get("direction", "forward")
    if direction == "reverse":
        seq = fwd[::-1]
    elif direction in ("pingpong", "pingpong_reverse"):
        seq = fwd + fwd[-2:0:-1]
        if direction == "pingpong_reverse":
            seq = seq[len(fwd) - 1:] + seq[:len(fwd) - 1]
    else:
        seq = fwd
    rep = int(tag.get("repeat") or 0)
    return (seq * rep, False) if rep else (seq, True)


def scene_path(p):
    """'/Main/Hero' or 'Main/Hero'; undoes Git Bash turning '/Main' into 'C:/Program Files/Git/Main'."""
    p = p.replace("\\", "/")
    m = re.match(r"^[A-Za-z]:/(?:.*/)?Git(/.*)$", p)
    if m:
        p = m.group(1)
    return "/" + p.strip("/")


def vec(x, y):
    return {"x": x, "y": y}


def rect2(x, y, w, h):
    return {"position": vec(x, y), "size": vec(w, h)}


def cmd_godot(a):
    report = check_sheet(a.sheet, max_size=a.max_size)
    if report["verdict"] != "pass":
        emit({"sheet": a.sheet, "problems": ["sheet check failed - fix before building"] +
              report["problems"], "verdict": "fail"})
    frames, meta = load_sheet(a.sheet)
    if not a.res_dir.startswith("res://"):
        emit({"problems": ["--res-dir must be a res:// folder"], "verdict": "fail"})
    res_dir = a.res_dir.rstrip("/")
    texture = f"{res_dir}/{meta['image']}"
    sw, sh = report["size"]
    notes = []
    tags = meta.get("frameTags") or [{"name": "default", "from": 0, "to": len(frames) - 1}]

    def pivot_px(f):
        src = f.get("sourceSize") or {"w": f["frame"]["w"], "h": f["frame"]["h"]}
        if a.pivot:
            return parse_pivot(a.pivot, src["w"], src["h"])
        if "pivot" in f:
            return int(round(f["pivot"]["x"] * src["w"])), int(round(f["pivot"]["y"] * src["h"]))
        return src["w"] // 2, src["h"] // 2

    if not a.pivot and "pivot" not in frames[0]:
        notes.append("no pivot in the data: canvas centre assumed (pass --pivot bottom|x,y)")

    def offset(f):
        px, py = pivot_px(f)
        s = f.get("spriteSourceSize") or {"x": 0, "y": 0}
        return s["x"] - px, s["y"] - py

    anims = []
    for t in tags:
        seq, loop = sequence(t)
        durs = [int(frames[i].get("duration") or round(1000.0 / a.fps)) for i in seq]
        base = sorted(Counter(durs).items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        times, acc = [], 0
        for d in durs:
            times.append(round(acc / 1000.0, 6))
            acc += d
        anims.append({"name": t["name"], "seq": seq, "loop": loop, "durations_ms": durs,
                      "times": times, "length_s": round(acc / 1000.0, 6),
                      "fps": nice_fps(base), "relative": [round(d / base, 4) for d in durs]})
        if t.get("repeat") and int(t["repeat"]) > 1:
            notes.append(f"{t['name']}: repeat {t['repeat']} unrolled into one clip")

    parent = scene_path(a.parent)
    node = f"{parent}/{a.node}"
    steps = [{"tool": "filesystem_manage", "params": {"op": "scan", "params": {}},
              "why": "import the sheet PNG (2D defaults: Lossless, no mipmaps)"}]
    verify = []
    first = frames[0]["frame"]
    hcompat = (all(not f.get("trimmed") and f["frame"]["w"] == first["w"]
                   and f["frame"]["h"] == first["h"] for f in frames)
               and sw % first["w"] == 0 and sh % first["h"] == 0
               and all(f["frame"]["x"] % first["w"] == 0 and f["frame"]["y"] % first["h"] == 0
                       for f in frames))

    if a.setup == "player":
        mode = "hframes" if hcompat else "region"
        steps += [
            {"tool": "node_create", "params": {"type": "Sprite2D", "name": a.node,
                                               "parent_path": parent},
             "why": "skip if the node already exists (node_find)"},
            {"tool": "node_set_property", "params": {"path": node, "property": "texture",
                                                     "value": texture}},
            {"tool": "node_set_property", "params": {"path": node, "property": "centered",
                                                     "value": False},
             "why": "integer offsets put the pivot at the node origin without half pixels"}]
        offs = [offset(f) for f in frames]
        const_off = len(set(offs)) == 1
        if mode == "hframes":
            hf, vf = sw // first["w"], sh // first["h"]
            steps += [{"tool": "node_set_property", "params": {"path": node, "property": "hframes",
                                                               "value": hf}},
                      {"tool": "node_set_property", "params": {"path": node, "property": "vframes",
                                                               "value": vf}}]
        else:
            steps += [{"tool": "node_set_property", "params": {
                          "path": node, "property": "region_enabled", "value": True}},
                      {"tool": "node_set_property", "params": {
                          "path": node, "property": "region_filter_clip_enabled", "value": True}}]
        if const_off:
            steps.append({"tool": "node_set_property", "params": {
                "path": node, "property": "offset", "value": vec(*offs[0])}})
        if a.pixel_art:
            steps.append({"tool": "node_set_property", "params": {
                "path": node, "property": "texture_filter", "value": 1},
                "why": "TEXTURE_FILTER_NEAREST; or set the project default texture filter"})
        player = f"{parent}/{a.player}"
        steps.append({"tool": "animation_manage", "params": {
            "op": "player_create", "params": {"parent_path": parent, "name": a.player}},
            "why": "skip if it exists; track paths are relative to its root node (the parent)"})
        for an in anims:
            steps.append({"tool": "animation_create", "params": {
                "player_path": player, "name": an["name"], "length": an["length_s"],
                "loop_mode": "linear" if an["loop"] else "none", "overwrite": True}})
            if mode == "hframes":
                hf = sw // first["w"]
                keys = [{"time": t, "value": frames[i]["frame"]["y"] // first["h"] * hf
                         + frames[i]["frame"]["x"] // first["w"]}
                        for t, i in zip(an["times"], an["seq"])]
                tracks = [(f"{a.node}:frame", keys)]
            else:
                tracks = [(f"{a.node}:region_rect",
                           [{"time": t, "value": rect2(*rect(frames[i]))}
                            for t, i in zip(an["times"], an["seq"])])]
            if not const_off:
                tracks.append((f"{a.node}:offset",
                               [{"time": t, "value": vec(*offset(frames[i]))}
                                for t, i in zip(an["times"], an["seq"])]))
            for path, keys in tracks:
                steps.append({"tool": "animation_manage", "params": {
                    "op": "add_property_track", "params": {
                        "player_path": player, "animation_name": an["name"], "track_path": path,
                        "keyframes": keys, "interpolation": "nearest"}},
                    "why": "nearest = hold each key until the next (step)"})
            verify.append({"tool": "animation_manage", "params": {
                "op": "validate", "params": {"player_path": player,
                                             "animation_name": an["name"]}}})
        steps.append({"tool": "scene_save", "params": {}})
        verify += [{"tool": "animation_manage", "params": {"op": "list",
                                                           "params": {"player_path": player}},
                    "expect": {a2["name"]: a2["length_s"] for a2 in anims}},
                   {"tool": "animation_manage", "params": {"op": "play", "params": {
                       "player_path": player, "animation_name": anims[0]["name"]}},
                    "then": "editor_screenshot; feet stay on the same pixel row across frames"}]
        notes.append("hitboxes/effects: add their tracks to the same clips (art-2d s5)")
        out = {"setup": "player", "mode": mode, "node": node, "player": player}
    else:
        mode = "spriteframes"
        stem = os.path.splitext(os.path.basename(meta["image"]))[0]
        tex_of, made = {}, {}
        for i, f in enumerate(frames):
            src = f.get("sourceSize") or {"w": f["frame"]["w"], "h": f["frame"]["h"]}
            s = f.get("spriteSourceSize") or {"x": 0, "y": 0, "w": f["frame"]["w"],
                                               "h": f["frame"]["h"]}
            key = (rect(f), s["x"], s["y"], src["w"], src["h"])
            if key not in made:
                fname = re.sub(r"[^\w-]+", "_", os.path.splitext(f.get("filename", str(i)))[0])
                made[key] = f"{res_dir}/{stem}_{fname}.tres"
                steps.append({"tool": "resource_manage", "params": {
                    "op": "create", "params": {
                        "type": "AtlasTexture", "resource_path": made[key], "properties": {
                            "atlas": texture, "region": rect2(*rect(f)),
                            "margin": rect2(s["x"], s["y"], src["w"] - s["w"],
                                            src["h"] - s["h"]),
                            "filter_clip": True}}}})
            tex_of[i] = made[key]
        frames_res = f"{res_dir}/{stem}_frames.tres"
        px, py = pivot_px(frames[0])
        steps += [
            {"tool": "resource_manage", "params": {"op": "create", "params": {
                "type": "SpriteFrames", "resource_path": frames_res}}},
            {"tool": "node_create", "params": {"type": "AnimatedSprite2D", "name": a.node,
                                               "parent_path": parent}},
            {"tool": "node_set_property", "params": {"path": node, "property": "sprite_frames",
                                                     "value": frames_res}},
            {"tool": "node_set_property", "params": {"path": node, "property": "centered",
                                                     "value": False}},
            {"tool": "node_set_property", "params": {"path": node, "property": "offset",
                                                     "value": vec(-px, -py)}}]
        if a.pixel_art:
            steps.append({"tool": "node_set_property", "params": {
                "path": node, "property": "texture_filter", "value": 1}})
        steps.append({"tool": "scene_save", "params": {}})
        notes += [
            "AtlasTexture margin = (trim x, trim y, canvas w - trim w, canvas h - trim h) restores "
            "the untrimmed canvas, so one AnimatedSprite2D offset holds the pivot for every frame",
            "Godot AI 4.3.0 has no op that adds SpriteFrames frames: resource_manage passes the "
            "internal 'animations' array through untouched, so texture paths would load as null. "
            "Ask the user to fill the SpriteFrames panel from 'spriteframes' below (new "
            "animation, FPS, Loop, drag the .tres files in order, frame duration), or use setup "
            "player. Never write the .tres by hand."]
        verify.append({"tool": "editor_manage", "params": {"op": "game_eval", "params": {
            "code": "var sf = get_tree().current_scene.get_node('%s').sprite_frames; return "
                    "[sf.get_animation_names(), %s]" % (
                        node.split("/", 2)[-1] if node.count("/") > 1 else a.node,
                        ", ".join("sf.get_frame_count('%s'), sf.get_animation_speed('%s')"
                                  % (an["name"], an["name"]) for an in anims))}},
            "expect": {an["name"]: [len(an["seq"]), an["fps"]] for an in anims}})
        out = {"setup": "frames", "mode": mode, "node": node, "sprite_frames": frames_res,
               "spriteframes": [{"name": an["name"], "fps": an["fps"], "loop": an["loop"],
                                 "frames": [{"texture": tex_of[i], "duration": r}
                                            for i, r in zip(an["seq"], an["relative"])]}
                                for an in anims]}
    out.update({"sheet": a.sheet, "texture": texture,
                "animations": [{"name": an["name"], "frames": len(an["seq"]),
                                "length_s": an["length_s"], "loop": an["loop"],
                                "fps": an["fps"], "durations_ms": an["durations_ms"]}
                               for an in anims],
                "before": "scene_open the target scene first so the user sees it being built",
                "steps": steps, "verify": verify, "notes": notes,
                "warnings": report["warnings"], "verdict": "pass"})
    emit(out)


def cmd_preview(a):
    """Review frames the way the player sees them: one animated GIF per tag at its game speed
    (nearest-neighbour scale) and one contact sheet with every frame numbered - a stray shape on
    two of seven frames shows on the sheet, a pop or a slide only at speed."""
    try:
        groups = group_frames(expand_inputs(a.frames))
    except SystemExit as e:
        emit({"problems": [str(e)], "verdict": "fail"})
    if not groups:
        emit({"problems": ["no frames found"], "verdict": "fail"})
    from PIL import ImageDraw
    os.makedirs(a.out, exist_ok=True)
    tag_fps = parse_map(a.tag_fps)
    written, sheet_rows = [], []
    for tag, frames in groups:
        imgs = [Image.open(p).convert("RGBA") for p, _ in frames]
        w = max(i.width for i in imgs)
        h = max(i.height for i in imgs)
        scaled = []
        for im in imgs:
            canvas = Image.new("RGBA", (w, h), a.background + (255,))
            canvas.alpha_composite(im, ((w - im.width) // 2, h - im.height))
            scaled.append(canvas.resize((w * a.scale, h * a.scale), Image.NEAREST))
        fps = tag_fps.get(tag, a.fps)
        name = os.path.join(a.out, f"{tag or 'anim'}.gif")
        rgb = [s.convert("RGB") for s in scaled]
        rgb[0].save(name, save_all=True, append_images=rgb[1:], duration=int(round(1000 / fps)),
                    loop=0, disposal=2)
        written.append({"tag": tag, "frames": len(imgs), "fps": fps,
                        "gif_frame_ms": int(round(100 / fps)) * 10,   # GIF keeps 1/100 s
                        "gif": name.replace("\\", "/")})
        sheet_rows.append((tag, scaled))
    cell_w = max(s[0].width for _, s in sheet_rows)
    cell_h = max(s[0].height for _, s in sheet_rows) + 12
    cols = max(len(s) for _, s in sheet_rows)
    sheet = Image.new("RGB", (cols * (cell_w + 4) + 4, len(sheet_rows) * (cell_h + 4) + 4),
                      (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    for r, (tag, scaled) in enumerate(sheet_rows):
        for c, im in enumerate(scaled):
            x, y = 4 + c * (cell_w + 4), 4 + r * (cell_h + 4)
            sheet.paste(im.convert("RGB"), (x, y + 12))
            draw.text((x + 2, y), f"{tag} {c}", fill=(230, 230, 230))
    path = os.path.join(a.out, "contact_sheet.png")
    sheet.save(path)
    emit({"animations": written, "contact_sheet": path.replace("\\", "/"), "verdict": "pass",
          "next": "look at the GIFs at game speed and the sheet frame by frame"})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("preview")
    v.add_argument("frames", nargs="+", help="frame files, folders or glob patterns")
    v.add_argument("--out", required=True, help="folder for the GIFs and the contact sheet")
    v.add_argument("--fps", type=float, default=10.0)
    v.add_argument("--tag-fps", default="", help="per tag, e.g. run=12,idle=6")
    v.add_argument("--scale", type=int, default=4, help="nearest-neighbour zoom")
    v.add_argument("--background", default="60,60,70",
                   type=lambda s: tuple(int(x) for x in s.split(",")))
    p = sub.add_parser("pack")
    p.add_argument("frames", nargs="+", help="frame files, folders or glob patterns")
    p.add_argument("--out", required=True, help="sheet PNG")
    p.add_argument("--data", required=True, help="json-array data file")
    p.add_argument("--layout", choices=("grid", "packed"), default="packed")
    p.add_argument("--padding", type=int, default=1, help="transparent px between frames")
    p.add_argument("--extrude", type=int, default=1, help="edge pixels repeated around frames")
    p.add_argument("--border", type=int, default=0, help="transparent px around the sheet")
    p.add_argument("--trim", action="store_true")
    p.add_argument("--columns", type=int, default=0, help="grid: cells per row (wrap)")
    p.add_argument("--fps", type=float, default=10.0)
    p.add_argument("--tag-fps", default="", help="per tag, e.g. run=12,idle=6")
    p.add_argument("--once", default="", help="tags that play once (repeat 1)")
    p.add_argument("--pingpong", default="", help="tags with pingpong direction")
    p.add_argument("--pivot", default="bottom", help="bottom | center | x,y in canvas px")
    p.add_argument("--max-size", type=int, default=4096)
    p.add_argument("--pot", action="store_true", help="power-of-two sheet size")
    p.add_argument("--dedupe", action="store_true", help="packed: identical frames share pixels")
    c = sub.add_parser("check")
    c.add_argument("sheets", nargs="+")
    c.add_argument("--padding", type=int, default=None, help="required gap (default: meta.kiln)")
    c.add_argument("--extrude", type=int, default=None)
    c.add_argument("--max-size", type=int, default=4096)
    g = sub.add_parser("godot")
    g.add_argument("sheet")
    g.add_argument("--res-dir", required=True, help="res:// folder holding the sheet PNG")
    g.add_argument("--parent", required=True,
                   help="scene path of the parent node, e.g. Main/Hero (leading / optional)")
    g.add_argument("--setup", choices=("player", "frames"), default="player")
    g.add_argument("--node", default="Sprite")
    g.add_argument("--player", default="AnimationPlayer")
    g.add_argument("--pivot", default=None, help="override: bottom | center | x,y")
    g.add_argument("--pixel-art", action="store_true")
    g.add_argument("--fps", type=float, default=10.0, help="for frames without duration")
    g.add_argument("--max-size", type=int, default=4096)
    a = parser.parse_args(argv)
    {"pack": cmd_pack, "check": cmd_check, "godot": cmd_godot, "preview": cmd_preview}[a.cmd](a)


if __name__ == "__main__":
    main()
