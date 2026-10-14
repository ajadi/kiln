"""Blind A/B against a bar ("gauntlet"): judge our capture vs a reference without knowing which
is which, one lens per round, one gap per verdict.

  python ab.py prepare <round_dir> --ours <ours.png> --bar <reference.png>
      copies both, normalised to the same size/format, as A.png and B.png in random order;
      the key goes to <round_dir>/.key.json — do not open it before the verdict.
  (write <round_dir>/verdict.md with lines `WINNER: A|B|TIE` and `GAP: <one sentence>`)
  python ab.py reveal <round_dir> [--ledger <gauntlet_dir>/LEDGER.md]
      refuses until verdict.md has WINNER and GAP; then prints which side was ours, appends a
      ledger row and writes outcome.json.
"""

import argparse
import datetime
import json
import os
import random
import re
import sys

from PIL import Image


def normalise(src, dst, size):
    img = Image.open(src).convert("RGB")
    img.thumbnail(size, Image.LANCZOS)
    canvas = Image.new("RGB", size, (0, 0, 0))
    canvas.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
    canvas.save(dst, "PNG")
    return img.width / img.height


def prepare(round_dir, ours, bar):
    os.makedirs(round_dir, exist_ok=True)
    size = (1280, 720)
    sides = ["ours", "bar"]
    random.shuffle(sides)
    srcs = {"ours": ours, "bar": bar}
    aspects = {}
    for label, side in zip(("A", "B"), sides):
        aspects[label] = normalise(srcs[side], os.path.join(round_dir, f"{label}.png"), size)
    with open(os.path.join(round_dir, ".key.json"), "w", encoding="utf-8") as fh:
        json.dump({"A": sides[0], "B": sides[1]}, fh)
    if abs(aspects["A"] - aspects["B"]) > 0.05:
        print("WARNING: aspect ratios differ — framing may give the sides away; recapture to match")
    print(f"prepared {round_dir}/A.png and B.png — judge them, then write verdict.md")


def reveal(round_dir, ledger):
    verdict_path = os.path.join(round_dir, "verdict.md")
    try:
        verdict = open(verdict_path, encoding="utf-8").read()
    except OSError:
        sys.exit("no verdict.md yet — judge first")
    winner = re.search(r"^WINNER:\s*(A|B|TIE)\b", verdict, re.M)
    gap = re.search(r"^GAP:\s*(.+)$", verdict, re.M)
    if not winner or not gap:
        sys.exit("verdict.md needs `WINNER: A|B|TIE` and `GAP: ...` lines")
    with open(os.path.join(round_dir, ".key.json"), encoding="utf-8") as fh:
        key = json.load(fh)
    w = winner.group(1)
    result = "tie" if w == "TIE" else ("ours" if key[w] == "ours" else "bar")
    outcome = {"round": os.path.basename(round_dir.rstrip("/\\")), "key": key, "winner": w,
               "result": result, "gap": gap.group(1).strip(),
               "date": datetime.date.today().isoformat()}
    with open(os.path.join(round_dir, "outcome.json"), "w", encoding="utf-8") as fh:
        json.dump(outcome, fh, indent=2, ensure_ascii=False)
    with open(verdict_path, "a", encoding="utf-8") as fh:
        fh.write(f"\nREVEAL: A={key['A']} B={key['B']} → {result}\n")
    if ledger:
        new = not os.path.exists(ledger)
        with open(ledger, "a", encoding="utf-8") as fh:
            if new:
                fh.write("| round | date | winner | gap |\n|---|---|---|---|\n")
            fh.write(f"| {outcome['round']} | {outcome['date']} | {result} | {outcome['gap']} |\n")
    print(json.dumps(outcome, ensure_ascii=False))
    if result == "ours":
        print("NOTE: ours won — check you did not recognise it (framing, UI, watermark); if the "
              "bar was weak, raise the bar instead of celebrating")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare"); p.add_argument("round_dir")
    p.add_argument("--ours", required=True); p.add_argument("--bar", required=True)
    r = sub.add_parser("reveal"); r.add_argument("round_dir"); r.add_argument("--ledger")
    a = ap.parse_args()
    if a.cmd == "prepare":
        prepare(a.round_dir, a.ours, a.bar)
    else:
        reveal(a.round_dir, a.ledger)
