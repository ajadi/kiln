"""Visual regression: baseline frames per scene, compare new captures, name what changed.
numpy + Pillow.

  python frames.py baseline cap/plaza_ref.png cap/plaza_gate.png --scene plaza
  python frames.py compare cap/*.png --scene plaza [--min-ssim 0.97] [--min-share 0.002] [--out diff/]
  python frames.py accept cap/plaza_ref.png --scene plaza --why "TASK-034 adds the bank sign"
  python frames.py anim --on "cap/rain_on/*.png" --off "cap/rain_off/*.png" [--box x,y,w,h]
         [--tol 4] [--min-add 0.001]
  python frames.py ramp --change "cap/fade/*.png" --steady "cap/held/*.png" [--box x,y,w,h]
         [--decorrelated 0.5]
  python frames.py review cap/*.png --scene plaza --out production/captures/T12/review
  python frames.py verdict production/captures/T12/review/review.json --a a.json --b b.json

review   the frames that differ from their baseline only, each changed region as one image
         (baseline | new | changed pixels, cropped with context, enlarged) with REVIEW.md: fixed
         questions (intended? broken? which glitch class? evidence) and review.json to answer.
         A vision model judges captured frames like these; it never plays the game.
         A frame that fails without a region (size changed, SSIM only) is one whole-frame
         item; no image or a frame without a baseline is NOT ASSESSED (exit 2).
verdict  two reviewers' answers (each their own copy of review.json, made without seeing the
         other): a glitch both see is FAIL, both clean and intended is PASS, clean but nobody
         asked for it is UNINTENDED, a split is DISPUTED - settled by engine data, not a third
         opinion. Exit 1 unless PASS.

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
A capture without a baseline, or no capture at all, is NOT ASSESSED. Output: JSON; exit 1 if
any image fails, 2 if one is not assessed and none fails.

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


GLITCHES = ["missing or extra object", "clipping or intersection", "floating object",
            "stretched, missing or wrong texture", "z-fighting or flicker",
            "wrong colour or lighting", "UI overlap or text cut off", "pose or animation error",
            "camera inside geometry", "other"]


def review(a):
    """A review pack of only the frames that differ from the baseline: per changed region the
    baseline, the new frame and the difference side by side, cropped with context and enlarged,
    plus fixed questions. A vision model (or a person) judges captured frames, never plays: VLMs
    finish under 1 % of real-time game benchmarks, and they miss small regressions unless shown
    exactly where to look (research 2026-10-19)."""
    os.makedirs(a.out, exist_ok=True)
    results = [compare_one(p, a.scene, a) for p in expand(a.images)]
    items = []
    for res, path in zip(results, expand(a.images)):
        if res["verdict"] != "FAIL":
            continue
        new = Image.open(path).convert("RGB")
        old = Image.open(os.path.join(BASE, a.scene, os.path.basename(path))).convert("RGB")
        if not res.get("regions"):
            # a size change or an SSIM-only failure has no region: the whole frame is the item
            # (bug hunt 2026-10-20: these frames were dropped and the review said PASS)
            h = min(256, old.height, new.height) or 1
            crops = [im.resize((max(1, round(im.width * h / im.height)), h)) for im in (old, new)]
            sheet = Image.new("RGB", (crops[0].width + crops[1].width + 4, h + 18), (30, 30, 30))
            draw = ImageDraw.Draw(sheet)
            for c, label, x in ((crops[0], "baseline", 0), (crops[1], "new", crops[0].width + 4)):
                sheet.paste(c, (x, 18))
                draw.text((x + 2, 2), label, fill=(230, 230, 230))
            name = f"{os.path.splitext(res['image'])[0]}_whole.png"
            sheet.save(os.path.join(a.out, name))
            items.append({"id": f"{res['image']}#whole", "image": res["image"],
                          "bbox": [0, 0, new.width, new.height], "share": 1.0, "pack": name,
                          "problems": res.get("problems", []),
                          "answer": {"intended": None, "glitch": None, "class": None,
                                     "evidence": ""}})
            continue
        diff_mask = np.abs(box(gray(path), 1) - box(gray(os.path.join(BASE, a.scene,
                                                                      os.path.basename(path))), 1)) > a.tol
        for i, reg in enumerate(res["regions"][:a.max_regions]):
            x, y, w, h = reg["bbox"]
            pad = max(16, max(w, h) // 4)
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(new.width, x + w + pad), min(new.height, y + h + pad)
            crops = [old.crop((x0, y0, x1, y1)), new.crop((x0, y0, x1, y1))]
            dm = np.asarray(new.crop((x0, y0, x1, y1))).copy()
            dm[diff_mask[y0:y1, x0:x1]] = (255, 0, 255)
            crops.append(Image.fromarray(dm))
            k = max(1, min(8, 256 // max(1, y1 - y0)))
            cw, ch = (x1 - x0) * k, (y1 - y0) * k
            sheet = Image.new("RGB", (cw * 3 + 8, ch + 18), (30, 30, 30))
            draw = ImageDraw.Draw(sheet)
            for j, (c, label) in enumerate(zip(crops, ("baseline", "new", "changed"))):
                sheet.paste(c.resize((cw, ch), Image.NEAREST), (j * (cw + 4), 18))
                draw.text((j * (cw + 4) + 2, 2), label, fill=(230, 230, 230))
            name = f"{os.path.splitext(res['image'])[0]}_r{i}.png"
            sheet.save(os.path.join(a.out, name))
            items.append({"id": f"{res['image']}#{i}", "image": res["image"], "bbox": reg["bbox"],
                          "share": reg["share"], "pack": name,
                          "answer": {"intended": None, "glitch": None, "class": None,
                                     "evidence": ""}})
    lines = [f"# Visual review: {a.scene}", "",
             "Each pack shows the baseline, the new capture and the changed pixels (magenta). "
             "For every item answer in your own copy of review.json, without seeing the other "
             "reviewer's answers:", "",
             "1. `intended`: is this change what the task asked for? (true / false)",
             "2. `glitch`: is anything here broken? (true / false)",
             f"3. `class`: if broken, one of: {', '.join(GLITCHES)}",
             "4. `evidence`: what you see, in one line (where, what).", "",
             "Then `frames.py verdict review.json --a <yours> --b <the other reviewer's>`. A "
             "glitch both reviewers see fails; a disagreement is DISPUTED until engine data "
             "(an overlap query, a position, a measured contrast) settles it.", ""]
    lines += [f"- {it['id']}: `{it['pack']}` region {it['bbox']} ({it['share']:.2%} of the frame)"
              for it in items] or ["- no frame differs from its baseline: nothing to review"]
    with open(os.path.join(a.out, "REVIEW.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(a.out, "review.json"), "w", encoding="utf-8") as fh:
        json.dump({"scene": a.scene, "items": items}, fh, indent=1)
    unchanged = sum(1 for r in results if r["verdict"] == "PASS")
    missing = [r["image"] for r in results if r["verdict"] == "NOT ASSESSED"]
    verdict = "REVIEW" if items else ("NOT ASSESSED" if missing or not results else "PASS")
    return {"scene": a.scene, "frames": len(results), "unchanged": unchanged,
            "items_to_review": len(items), "not_assessed": missing,
            "out": a.out.replace("\\", "/"), "verdict": verdict}, \
        2 if verdict == "NOT ASSESSED" else 0


def verdict(a):
    """Two independent reviews of one pack: agreement decides, disagreement is DISPUTED."""
    def load(path):
        with open(path, encoding="utf-8") as fh:
            return {it["id"]: it.get("answer") or {} for it in json.load(fh)["items"]}
    with open(a.review, encoding="utf-8") as fh:
        ids = [it["id"] for it in json.load(fh)["items"]]
    ra, rb = load(a.a), load(a.b)
    out, worst = [], "PASS"
    for i in ids:
        x, y = ra.get(i, {}), rb.get(i, {})
        if x.get("glitch") is None or y.get("glitch") is None:
            state = "UNANSWERED"
        elif x["glitch"] and y["glitch"]:
            state = "FAIL"
        elif not x["glitch"] and not y["glitch"]:
            state = "PASS" if x.get("intended") and y.get("intended") else "UNINTENDED"
        else:
            state = "DISPUTED"
        out.append({"id": i, "verdict": state, "a": x, "b": y})
        rank = {"PASS": 0, "UNINTENDED": 1, "DISPUTED": 2, "UNANSWERED": 2, "FAIL": 3}
        if rank[state] > rank[worst]:
            worst = state
    return {"items": out, "verdict": worst,
            "next": {"PASS": "accept the intended changes (frames.py accept --why)",
                     "UNINTENDED": "a change nobody asked for: find its cause before accepting",
                     "DISPUTED": "settle it with engine data, not a third opinion",
                     "UNANSWERED": "both reviewers answer every item",
                     "FAIL": "send the glitch to the owning role with the pack"}[worst]}, \
        0 if worst == "PASS" else 1


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
    v = sub.add_parser("review")
    v.add_argument("images", nargs="+")
    v.add_argument("--scene", required=True)
    v.add_argument("--out", required=True)
    v.add_argument("--min-ssim", type=float, default=0.97)
    v.add_argument("--min-share", type=float, default=0.002)
    v.add_argument("--tol", type=float, default=12.0)
    v.add_argument("--max-regions", type=int, default=6)
    d = sub.add_parser("verdict")
    d.add_argument("review")
    d.add_argument("--a", required=True)
    d.add_argument("--b", required=True)
    a = ap.parse_args()
    if a.cmd in ("anim", "ramp", "review", "verdict"):
        res, code = {"anim": anim, "ramp": ramp, "review": review, "verdict": verdict}[a.cmd](a)
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
        # no image, or one without a baseline, is not a pass (bug hunt 2026-10-20)
        unknown = not results or any(r["verdict"] == "NOT ASSESSED" for r in results)
        overall = "FAIL" if failed else ("NOT ASSESSED" if unknown else "PASS")
        res, code = {"scene": a.scene, "results": results, "verdict": overall}, \
            {"FAIL": 1, "NOT ASSESSED": 2, "PASS": 0}[overall]
    print(json.dumps(res, indent=1))
    sys.exit(code)


if __name__ == "__main__":
    main()
