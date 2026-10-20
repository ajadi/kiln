"""Coverage and stuck heatmaps from explorer bot runs (playtest explorer.gd). numpy + Pillow.

  python explore_report.py production/autoplay/<night>/run_*/explore.json --out production/autoplay/<night>
         [--reachable production/procgen/level1.json] [--min-coverage 0.9] [--max-stuck-share 0.05]

Merges the runs (one seed each) into one top-down grid: visits per cell (how often the bot stood
there) and stuck events per cell (steps that did not move the player). Writes heatmap.png (grey
= visited, brighter = more often; red = stuck, stronger = more stuck events; black = never) and
prints JSON: cells visited, stuck cells, the worst stuck cells (snags to look at), and, with
--reachable (a procgen_check grid or platformer layout of the same level, one character per
cell), coverage = visited / reachable cells and the reachable cells never visited.
Gate: coverage >= --min-coverage when --reachable is given; no cell holding more than
--max-stuck-share of all steps. Exit 1 on a fail.
"""

import argparse
import glob
import json
import os
import sys

import numpy as np
from PIL import Image


def cells(d):
    return {tuple(int(v) for v in k.split(",")): n for k, n in d.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--reachable")
    ap.add_argument("--min-coverage", type=float, default=0.9)
    ap.add_argument("--max-stuck-share", type=float, default=0.05)
    ap.add_argument("--scale", type=int, default=8)
    a = ap.parse_args(argv)
    files = sorted({f for p in a.runs for f in glob.glob(p)})
    visits, stuck, steps = {}, {}, 0
    for f in files:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        for c, n in cells(data["visits"]).items():
            visits[c] = visits.get(c, 0) + n
            steps += n
        for c, n in cells(data["stuck"]).items():
            stuck[c] = stuck.get(c, 0) + n
    problems = []
    if not visits:
        problems.append("no explorer runs with visits")
        print(json.dumps({"problems": problems, "verdict": "fail"}))
        return 1
    xs = [c[0] for c in visits] + [c[0] for c in stuck]
    ys = [c[1] for c in visits] + [c[1] for c in stuck]
    reach = set()
    if a.reachable:
        with open(a.reachable, encoding="utf-8") as fh:
            layout = json.load(fh)
        for y, row in enumerate(layout.get("cells") or []):
            for x, ch in enumerate(row):
                if ch not in "#^":
                    reach.add((x, y))
        xs += [c[0] for c in reach]
        ys += [c[1] for c in reach]
    x0, y0 = min(xs), min(ys)
    w, h = max(xs) - x0 + 1, max(ys) - y0 + 1
    img = np.zeros((h, w, 3), np.uint8)
    top = max(visits.values())
    for (x, y), n in visits.items():
        g = int(60 + 195 * np.log1p(n) / np.log1p(top))
        img[y - y0, x - x0] = (g, g, g)
    top_s = max(stuck.values()) if stuck else 1
    for (x, y), n in stuck.items():
        r = int(120 + 135 * n / top_s)
        img[y - y0, x - x0] = (r, 30, 30)
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "heatmap.png")
    Image.fromarray(img).resize((w * a.scale, h * a.scale), Image.NEAREST).save(path)
    worst = sorted(stuck.items(), key=lambda kv: -kv[1])[:10]
    out = {"runs": len(files), "cells_visited": len(visits), "stuck_cells": len(stuck),
           "worst_stuck": [{"cell": list(c), "events": n, "share": round(n / max(steps, 1), 4)}
                           for c, n in worst],
           "heatmap": path.replace("\\", "/")}
    if worst and worst[0][1] / max(steps, 1) > a.max_stuck_share:
        problems.append(f"cell {list(worst[0][0])} holds {worst[0][1]} stuck events "
                        f"({worst[0][1] / steps:.1%} of all steps > {a.max_stuck_share:.0%}): a snag")
    if reach:
        seen = set(visits) & reach
        cov = len(seen) / len(reach)
        out["coverage"] = round(cov, 4)
        out["never_visited"] = [list(c) for c in sorted(reach - set(visits))][:40]
        if cov < a.min_coverage:
            problems.append(f"coverage {cov:.1%} < {a.min_coverage:.0%} of the reachable cells")
    out.update(problems=problems, verdict="fail" if problems else "pass")
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
