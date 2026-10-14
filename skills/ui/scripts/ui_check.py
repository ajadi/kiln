"""UI acceptance measurements from the running game. Pillow + numpy.

  python ui_check.py layout elements.json --viewport 1920x1080 [--safe 0.9] [--min-target 24]
  python ui_check.py text capture.png elements.json --viewport 1920x1080 [--profile pc|console]
  python ui_check.py focus trace.json [--elements elements.json] [--expect-wrap]
  python ui_check.py focus-diff focused.png unfocused.png --rect 820,500,280,48 [--min-contrast 3]
  python ui_check.py colours "#d23c3c" "#3cb44b" "#4363d8" [--names enemy,ally,goal] [--min-de 20]
  python ui_check.py simulate capture.png [--out-dir production/captures/T12/cvd]

elements.json  the reply of Godot AI `game_manage get_ui_elements` (or {"elements": [...]} / a
               list) - each element has path, type, visible, disabled, text and global_rect
               {position{x,y}, size{x,y}}; rect may also be [x,y,w,h] or {x,y,w|width,h|height}
               (Unity/Unreal dumps). Coordinates are the viewport's logical pixels (--viewport).
layout   content elements (interactive or with text) inside the viewport and inside the
         title-safe rect (--safe 0.9 = SMPTE ST 2046-1 title safe; or --safe-rect x,y,w,h from
         the platform safe area); pointer targets at least --min-target px tall and wide at
         1080p-equivalent (WCAG 2.5.8: 24); interactive rects overlapping each other fail; text
         rects overlapping each other are warnings.
text     per visible element with text, on the capture: ink/background split (Otsu), body height
         of the tallest line (XAG 101: lowest descender to highest ascender) and WCAG contrast of
         the glyph core against the worst background around it (XAG 102). Thresholds are at
         1080p and scale with capture height: pc 18 px / large 36 px, console 26 / 52; contrast
         4.5:1, 3:1 for large text. Use test strings with ascenders and descenders ("Hgjpqy").
focus    trace = list of {"input": action|null, "focus": node path|""} recorded while stepping
         ui_* actions; fails on no initial focus, focus lost, focus on a hidden/disabled control
         and interactive elements never reached; moves that do not change focus are warnings
         (failures with --expect-wrap, XAG 112 wrap-around).
focus-diff  one control captured focused and unfocused (same frame otherwise): the changed
         pixels must cover a >= --min-px thick perimeter and change by >= --min-contrast
         (WCAG 2.2 SC 2.4.13); a tint-only focus state fails. Run it per focusable type
         (button, slider, tab, toggle) - each needs its own visible ring.
colours  coded colours stay distinct under protanopia, deuteranopia and tritanopia (Machado et
         al. 2009 severity 1.0, linear sRGB): pairwise CIE76 delta E >= --min-de (working 20).
simulate writes protan/deutan/tritan versions of a capture for side-by-side review.
Output: JSON with a verdict per check; exit code 1 if any fails.
"""

import argparse
import itertools
import json
import os
import re
import sys

import numpy as np
from PIL import Image

INTERACTIVE = {"Button", "CheckBox", "CheckButton", "OptionButton", "MenuButton", "LinkButton",
               "TextureButton", "ColorPickerButton", "HSlider", "VSlider", "SpinBox", "LineEdit",
               "TextEdit", "ItemList", "TabBar", "Tree", "Toggle", "Slider", "Dropdown",
               "TMP_Dropdown", "TMP_InputField", "InputField", "Scrollbar", "TextField",
               "DropdownField", "SliderInt", "ComboBoxString", "EditableTextBox",
               "MultiLineEditableTextBox"}

MACHADO = {  # Machado, Oliveira & Fernandes 2009, severity 1.0 (as tabulated in colorspacious)
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216],
               [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413],
               [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602],
               [0.004733, 0.691367, 0.303900]],
}
PROFILES = {"pc": (18, 36), "console": (26, 52)}


# ---------------------------------------------------------------- input

def load_elements(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for key in ("data", "result"):
        if isinstance(data, dict) and key in data and isinstance(data[key], (dict, list)):
            data = data[key]
    items = data.get("elements", data.get("nodes", [])) if isinstance(data, dict) else data
    out = []
    for e in items:
        r = rect_of(e)
        if r is None:
            continue
        out.append({"path": str(e.get("path") or e.get("name") or ""), "type": e.get("type", ""),
                    "visible": e.get("visible", True), "disabled": e.get("disabled", False),
                    "text": e.get("text") or "", "rect": r,
                    "interactive": e.get("interactive", is_interactive(e.get("type", ""))),
                    "focusable": e.get("focusable", True)})
    return out


def rect_of(e):
    r = e.get("global_rect", e.get("rect"))
    if r is None and "x" in e:
        r = e
    if isinstance(r, (list, tuple)) and len(r) == 4:
        return [float(v) for v in r]
    if isinstance(r, dict):
        if "position" in r:
            return [float(r["position"]["x"]), float(r["position"]["y"]),
                    float(r["size"]["x"]), float(r["size"]["y"])]
        if "x" in r:
            return [float(r["x"]), float(r["y"]), float(r.get("w", r.get("width", 0))),
                    float(r.get("h", r.get("height", 0)))]
    return None


def is_interactive(t):
    return t in INTERACTIVE or "Button" in t or "Slider" in t


def wh(s):
    m = re.fullmatch(r"(\d+)[xX,](\d+)", s)
    if not m:
        raise argparse.ArgumentTypeError("expected WIDTHxHEIGHT")
    return int(m.group(1)), int(m.group(2))


def ancestor(a, b):
    return a == b or b.startswith(a.rstrip("/") + "/") or a.startswith(b.rstrip("/") + "/")


def overlap(a, b):
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


# ---------------------------------------------------------------- layout

def check_layout(elements, viewport, safe, safe_rect, min_target, tol=1.0):
    vw, vh = viewport
    if safe_rect:
        sx, sy, sw, sh = safe_rect
    else:
        inset = (1.0 - safe) / 2.0
        sx, sy, sw, sh = vw * inset, vh * inset, vw * safe, vh * safe
    content = [e for e in elements if e["visible"] and (e["interactive"] or e["text"].strip())]
    off, unsafe, small, collapsed = [], [], [], []
    for e in content:
        x, y, w, h = e["rect"]
        item = {"path": e["path"], "type": e["type"], "rect": [round(v, 1) for v in e["rect"]]}
        if w < 1 or h < 1:
            collapsed.append(item)
            continue
        if x < -tol or y < -tol or x + w > vw + tol or y + h > vh + tol:
            off.append(item)
        elif x < sx - tol or y < sy - tol or x + w > sx + sw + tol or y + h > sy + sh + tol:
            unsafe.append(item)
        if e["interactive"] and not e["disabled"]:
            side = min(w, h) * 1080.0 / vh
            if side < min_target:
                small.append({**item, "min_side_1080p": round(side, 1)})
    inter = [e for e in content if e["interactive"]]
    texts = [e for e in content if not e["interactive"]]
    hits, warn = [], []
    for a, b in itertools.combinations(inter, 2):
        if not ancestor(a["path"], b["path"]) and overlap(a["rect"], b["rect"]) > 1.0:
            hits.append([a["path"], b["path"]])
    for a, b in itertools.combinations(texts, 2):
        if not ancestor(a["path"], b["path"]) and overlap(a["rect"], b["rect"]) > 1.0:
            warn.append([a["path"], b["path"]])
    problems = len(off) + len(unsafe) + len(small) + len(collapsed) + len(hits)
    return {"check": "layout", "viewport": [vw, vh],
            "safe_rect": [round(v, 1) for v in (sx, sy, sw, sh)], "content_elements": len(content),
            "offscreen": off, "outside_safe_area": unsafe, "small_targets": small,
            "collapsed": collapsed, "overlapping_interactive": hits, "overlapping_text": warn,
            "verdict": "fail" if problems else "pass"}


# ---------------------------------------------------------------- text

def srgb_to_linear(arr):
    a = arr.astype(np.float64) / 255.0
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def luminance(rgb):
    lin = srgb_to_linear(rgb)
    return 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]


def otsu(gray):
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    w0 = np.cumsum(hist)
    mu = np.cumsum(hist * np.arange(256))
    w1 = total - w0
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mu[-1] * w0 / total - mu) ** 2 / (w0 * w1 / total)
    between[~np.isfinite(between)] = 0
    return int(np.argmax(between))


def dilate(mask, r):
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def measure_text(rgb, ink_side=None):
    """Body height (px) of the tallest ink line and WCAG contrast of ink core vs worst bg."""
    gray = np.clip(rgb.astype(np.float64) @ [0.299, 0.587, 0.114], 0, 255).astype(np.uint8)
    if gray.std() < 2.0:
        return 0, 1.0, None
    t = otsu(gray)
    light = gray > t
    ink = light if (ink_side == "light" or (ink_side is None and light.mean() < 0.5)) else ~light
    side = "light" if ink is light else "dark"
    rows = ink.sum(axis=1)
    on = rows >= max(1, 0.05 * rows.max())
    runs, start = [], None
    for y, v in enumerate(list(on) + [False]):
        if v and start is None:
            start = y
        elif not v and start is not None:
            runs.append([start, y])
            start = None
    if not runs:
        return 0, 1.0, side
    # Full text lines never merge with each other; small runs (i-dots, accents, a lone
    # descender) join the nearest full line when the gap is small.
    big_h = max(b - a for a, b in runs)
    lines = [list(r) for r in runs if r[1] - r[0] > 0.35 * big_h]
    gap = max(1, round(0.25 * big_h))
    for a, b in runs:
        if b - a > 0.35 * big_h:
            continue
        near = min(lines, key=lambda ln: min(abs(a - ln[1]), abs(ln[0] - b)))
        if min(abs(a - near[1]), abs(near[0] - b)) <= gap:
            near[0], near[1] = min(near[0], a), max(near[1], b)
    height = max(b - a for a, b in lines)
    y = luminance(rgb)
    bg = ~dilate(ink, 2)
    if not bg.any():
        bg = ~ink
    if side == "light":
        y_ink, y_bg = np.percentile(y[ink], 75), np.percentile(y[bg], 95)
    else:
        y_ink, y_bg = np.percentile(y[ink], 25), np.percentile(y[bg], 5)
    hi, lo = max(y_ink, y_bg), min(y_ink, y_bg)
    return int(height), float((hi + 0.05) / (lo + 0.05)), side


def check_text(capture, elements, viewport, profile, min_px, large_px, min_contrast, inset,
               ink_side):
    img = np.asarray(Image.open(capture).convert("RGB"))
    ih, iw = img.shape[:2]
    vw, vh = viewport or (iw, ih)
    sx, sy = iw / vw, ih / vh
    base_min, base_large = PROFILES[profile]
    need = (min_px or base_min) * ih / 1080.0
    large = (large_px or base_large) * ih / 1080.0
    rows, failed = [], 0
    for e in elements:
        if not e["visible"] or not e["text"].strip():
            continue
        x, y, w, h = e["rect"]
        x0, y0 = int(round(x * sx)) + inset, int(round(y * sy)) + inset
        x1, y1 = int(round((x + w) * sx)) - inset, int(round((y + h) * sy)) - inset
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(iw, x1), min(ih, y1)
        item = {"path": e["path"], "text": e["text"][:40]}
        if x1 - x0 < 3 or y1 - y0 < 3:
            rows.append({**item, "verdict": "fail", "reason": "rect off capture or too small"})
            failed += 1
            continue
        height, contrast, side = measure_text(img[y0:y1, x0:x1], ink_side)
        want_c = 3.0 if height >= large else min_contrast
        ok = height >= need and contrast >= want_c
        failed += not ok
        rows.append({**item, "body_px": height, "body_px_1080p": round(height * 1080.0 / ih, 1),
                     "min_px": round(need, 1), "contrast": round(contrast, 2),
                     "min_contrast": want_c, "ink": side, "verdict": "pass" if ok else "fail"})
    return {"check": "text", "capture": capture, "profile": profile, "elements": rows,
            "verdict": "fail" if failed else "pass"}


def check_focus_diff(focused, unfocused, rect, margin, min_contrast, min_px, tol):
    """Focus indicator visibility (WCAG 2.2 SC 2.4.13 Focus Appearance): the pixels that change
    between the focused and unfocused capture of one control cover at least a `min_px` thick
    perimeter of it, and change by at least `min_contrast` (relative luminance ratio)."""
    a = np.asarray(Image.open(focused).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(unfocused).convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        return {"check": "focus-diff", "verdict": "fail",
                "problems": ["captures differ in size"]}
    x, y, w, h = (int(round(float(v))) for v in rect.split(","))
    y0, y1 = max(0, y - margin), min(a.shape[0], y + h + margin)
    x0, x1 = max(0, x - margin), min(a.shape[1], x + w + margin)
    ca, cb = a[y0:y1, x0:x1], b[y0:y1, x0:x1]
    changed = np.abs(ca - cb).max(axis=2) > tol
    perimeter = 2 * (w + h)
    area = int(changed.sum())
    thickness = area / perimeter if perimeter else 0.0
    if area:
        ya = luminance(ca[changed].astype(np.float64)).mean()
        yb = luminance(cb[changed].astype(np.float64)).mean()
        contrast = (max(ya, yb) + 0.05) / (min(ya, yb) + 0.05)
    else:
        contrast = 1.0
    problems = []
    if thickness < min_px:
        problems.append(f"focus change covers {area} px = {thickness:.1f} px of the control's "
                        f"perimeter (needs >= {min_px}): give this control type its own ring")
    if contrast < min_contrast:
        problems.append(f"focused vs unfocused contrast {contrast:.2f}:1 < {min_contrast}:1: a "
                        "colour tint is not a focus indicator")
    return {"check": "focus-diff", "focused": focused, "unfocused": unfocused, "rect": rect,
            "changed_px": area, "thickness_px": round(thickness, 2),
            "contrast": round(float(contrast), 2), "problems": problems,
            "verdict": "fail" if problems else "pass"}


# ---------------------------------------------------------------- focus

def check_focus(trace_path, elements, expect_wrap):
    with open(trace_path, encoding="utf-8") as fh:
        data = json.load(fh)
    steps = data.get("steps", data) if isinstance(data, dict) else data
    lost, stuck, hidden = [], [], []
    visible = {e["path"] for e in elements if e["visible"] and not e["disabled"]} \
        if elements else None
    visited, prev = set(), None
    for i, s in enumerate(steps):
        f = s.get("focus") or ""
        if not f:
            lost.append(i)
        else:
            visited.add(f)
            if visible is not None and f not in visible:
                hidden.append({"step": i, "focus": f})
        if i and s.get("input") and f and f == prev:
            stuck.append({"step": i, "input": s.get("input"), "focus": f})
        prev = f
    initial = bool(steps) and bool(steps[0].get("focus"))
    unreachable = []
    if elements:
        unreachable = sorted(e["path"] for e in elements
                             if e["interactive"] and e["visible"] and not e["disabled"]
                             and e["focusable"] and e["path"] not in visited)
    failed = (not initial) or lost or hidden or unreachable or (expect_wrap and stuck)
    return {"check": "focus", "steps": len(steps), "initial_focus": initial,
            "focused_controls": len(visited), "focus_lost_at": lost,
            "focus_on_hidden_or_disabled": hidden, "unreachable": unreachable,
            "no_move": stuck, "verdict": "fail" if failed else "pass"}


# ---------------------------------------------------------------- colours

def hex_rgb(s):
    h = s.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise argparse.ArgumentTypeError(f"bad colour {s}")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def lab_from_linear(lin):
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def simulate_linear(lin, kind):
    return np.clip(lin @ np.array(MACHADO[kind]).T, 0.0, 1.0)


def check_colours(colours, names, min_de):
    lin = srgb_to_linear(np.array(colours, dtype=np.float64))
    names = names or [f"#{''.join(f'{v:02x}' for v in c)}" for c in colours]
    out, failed = {}, False
    for kind in ("normal", "protan", "deutan", "tritan"):
        v = lin if kind == "normal" else simulate_linear(lin, kind)
        lab = lab_from_linear(v)
        pairs = []
        for i, j in itertools.combinations(range(len(colours)), 2):
            de = float(np.linalg.norm(lab[i] - lab[j]))
            pairs.append({"pair": [names[i], names[j]], "delta_e": round(de, 1)})
        bad = [p for p in pairs if p["delta_e"] < min_de]
        failed |= bool(bad)
        out[kind] = {"min_delta_e": min((p["delta_e"] for p in pairs), default=None),
                     "too_close": bad}
    y = 0.2126 * lin[:, 0] + 0.7152 * lin[:, 1] + 0.0722 * lin[:, 2]
    lum = [{"pair": [names[i], names[j]],
            "contrast": round(float((max(y[i], y[j]) + 0.05) / (min(y[i], y[j]) + 0.05)), 2)}
           for i, j in itertools.combinations(range(len(colours)), 2)]
    return {"check": "colours", "min_de": min_de, "vision": out, "luminance_contrast": lum,
            "note": "colour must still not be the only channel (XAG 103): add shape/icon/text",
            "verdict": "fail" if failed else "pass"}


def simulate_image(path, out_dir):
    img = np.asarray(Image.open(path).convert("RGB"))
    lin = srgb_to_linear(img)
    out_dir = out_dir or os.path.dirname(os.path.abspath(path))
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    written = []
    for kind in ("protan", "deutan", "tritan"):
        v = simulate_linear(lin, kind)
        s = np.where(v <= 0.0031308, 12.92 * v, 1.055 * np.power(v, 1 / 2.4) - 0.055)
        dst = os.path.join(out_dir, f"{stem}_{kind}.png")
        Image.fromarray(np.clip(s * 255 + 0.5, 0, 255).astype(np.uint8)).save(dst)
        written.append(dst)
    return {"check": "simulate", "written": written}


# ---------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    lay = sub.add_parser("layout")
    lay.add_argument("elements")
    lay.add_argument("--viewport", type=wh, required=True)
    lay.add_argument("--safe", type=float, default=0.9)
    lay.add_argument("--safe-rect", default=None, help="x,y,w,h in viewport pixels")
    lay.add_argument("--min-target", type=float, default=24.0)
    tx = sub.add_parser("text")
    tx.add_argument("capture")
    tx.add_argument("elements")
    tx.add_argument("--viewport", type=wh, default=None)
    tx.add_argument("--profile", choices=sorted(PROFILES), default="pc")
    tx.add_argument("--min-px", type=float, default=None)
    tx.add_argument("--large-px", type=float, default=None)
    tx.add_argument("--min-contrast", type=float, default=4.5)
    tx.add_argument("--inset", type=int, default=2, help="px trimmed off each rect edge")
    tx.add_argument("--ink", choices=["light", "dark"], default=None)
    fo = sub.add_parser("focus")
    fo.add_argument("trace")
    fo.add_argument("--elements", default=None)
    fo.add_argument("--expect-wrap", action="store_true")
    fd = sub.add_parser("focus-diff")
    fd.add_argument("focused")
    fd.add_argument("unfocused")
    fd.add_argument("--rect", required=True, help="control rect x,y,w,h in capture pixels")
    fd.add_argument("--margin", type=int, default=8, help="px around the rect searched for a ring")
    fd.add_argument("--min-contrast", type=float, default=3.0)
    fd.add_argument("--min-px", type=float, default=2.0)
    fd.add_argument("--tol", type=int, default=8)
    co = sub.add_parser("colours")
    co.add_argument("colours", nargs="+", type=hex_rgb)
    co.add_argument("--names", default="")
    co.add_argument("--min-de", type=float, default=20.0)
    si = sub.add_parser("simulate")
    si.add_argument("capture")
    si.add_argument("--out-dir", default=None)
    args = parser.parse_args(argv)

    if args.cmd == "layout":
        safe_rect = [float(v) for v in args.safe_rect.split(",")] if args.safe_rect else None
        res = check_layout(load_elements(args.elements), args.viewport, args.safe, safe_rect,
                           args.min_target)
    elif args.cmd == "text":
        res = check_text(args.capture, load_elements(args.elements), args.viewport, args.profile,
                         args.min_px, args.large_px, args.min_contrast, args.inset, args.ink)
    elif args.cmd == "focus":
        els = load_elements(args.elements) if args.elements else None
        res = check_focus(args.trace, els, args.expect_wrap)
    elif args.cmd == "focus-diff":
        res = check_focus_diff(args.focused, args.unfocused, args.rect, args.margin,
                               args.min_contrast, args.min_px, args.tol)
    elif args.cmd == "colours":
        names = [n.strip() for n in args.names.split(",") if n.strip()]
        if names and len(names) != len(args.colours):
            parser.error("--names needs one name per colour")
        res = check_colours(args.colours, names, args.min_de)
    else:
        res = simulate_image(args.capture, args.out_dir)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))
    sys.exit(1 if res.get("verdict") == "fail" else 0)


if __name__ == "__main__":
    main()
