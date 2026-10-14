"""Subtitle and caption timing/layout checks. Python stdlib only.

  python subtitle_check.py data/subtitles/*.srt
  python subtitle_check.py data/subtitles/intro.vtt --max-chars 42 --max-cps 17
  python subtitle_check.py data/subtitles/barks.csv --speakers-need-labels

Inputs: .srt, .vtt, or .csv/.json cues with start, end (seconds or HH:MM:SS.mmm), text and an
optional speaker column/field (glob patterns are expanded here).
Per cue (defaults from XAG 104 and the Netflix timed-text guide):
  lines        <= --max-lines (2)
  line width   <= --max-chars (40) display characters (East Asian wide = 2)
  duration     >= --min-dur (0.833 s = 5/6 s) and <= --max-dur (7 s)
  reading rate <= --max-cps (20 chars/s adults; use 17 for children); words/min reported (BBC
               160-180 wpm)
  overlap      a cue starting before the previous one ends
  all caps     dialogue lines in ALL CAPS (sound captions in [] or () and speaker labels exempt)
  speaker      with a speaker field: a cue whose speaker differs from the previous cue, or who
               has not been labelled for --relabel-after s (90; XAG says 1-2 min), must start with
               a label (NAME: / [NAME] / (NAME)); --no-label-speakers lists exempt speakers
               (e.g. a lone narrator)
Output: JSON with "verdict" (pass|fail), counts and the failing cues; exit code 1 on fail.
"""

import argparse
import csv
import glob
import json
import os
import re
import sys
import unicodedata

TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
TAGS = re.compile(r"<[^>]+>|\{\\[^}]*\}")
LABEL = re.compile(r"^\s*(?:-\s*)?(?:\[[^\]]+\]|\([^)]+\)|[^\s:][^:]{0,30}:)\s*")
CAPTION = re.compile(r"^\s*[\[(][^\])]*[\])]\s*$")


def seconds(v):
    v = str(v).strip()
    m = TIME.fullmatch(v)
    if m:
        h, mi, s, ms = m.groups()
        return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0
    return float(v)


def width(s):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in "WF"
               else 1 for c in s)


def parse_timed(text):
    cues, block = [], []
    for line in text.splitlines() + [""]:
        if line.strip():
            block.append(line.rstrip())
            continue
        if not block:
            continue
        t = next((i for i, l in enumerate(block) if "-->" in l), None)
        if t is not None:
            a, b = block[t].split("-->", 1)
            cues.append({"start": seconds(a.strip()), "end": seconds(b.strip().split()[0]),
                         "speaker": None, "text": "\n".join(block[t + 1:])})
        block = []
    return cues


def parse_table(path):
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)
        rows = rows.get("cues", rows) if isinstance(rows, dict) else rows
    else:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    return [{"start": seconds(r["start"]), "end": seconds(r["end"]),
             "speaker": (r.get("speaker") or "").strip() or None,
             "text": str(r.get("text", "")).replace("\\n", "\n")} for r in rows]


def check(path, cues, a):
    fails, warns, last_label, prev = [], [], {}, None
    total_chars = total_time = 0.0
    for n, c in enumerate(cues, 1):
        text = TAGS.sub("", c["text"]).strip()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        dur = c["end"] - c["start"]
        chars = sum(len(l) for l in lines)
        words = len(text.split())
        cps = chars / dur if dur > 0 else float("inf")
        issues = []
        if len(lines) > a.max_lines:
            issues.append(f"{len(lines)} lines > {a.max_lines}")
        wide = [width(l) for l in lines]
        if wide and max(wide) > a.max_chars:
            issues.append(f"line of {max(wide)} chars > {a.max_chars}")
        if dur < a.min_dur:
            issues.append(f"duration {dur:.2f} s < {a.min_dur}")
        if dur > a.max_dur:
            issues.append(f"duration {dur:.2f} s > {a.max_dur}")
        if cps > a.max_cps:
            issues.append(f"{cps:.1f} chars/s > {a.max_cps}")
        if prev is not None and c["start"] < prev["end"] - 0.001:
            issues.append("overlaps previous cue")
        for l in lines:
            body = LABEL.sub("", l)
            letters = [ch for ch in body if ch.isalpha()]
            if not CAPTION.match(body) and len(letters) >= 8 and all(ch.isupper() for ch in letters):
                issues.append("ALL CAPS dialogue")
                break
        spk = c.get("speaker")
        if spk and spk not in a.no_label_speakers:
            due = prev is None or prev.get("speaker") != spk or \
                c["start"] - last_label.get(spk, -1e9) > a.relabel_after
            if LABEL.match(lines[0] if lines else ""):
                last_label[spk] = c["start"]
            elif due and a.speakers_need_labels:
                issues.append(f"speaker '{spk}' not labelled")
            elif due:
                warns.append({"cue": n, "issue": f"speaker '{spk}' not labelled"})
        total_chars += chars
        total_time += max(dur, 0)
        if issues:
            fails.append({"cue": n, "start": round(c["start"], 3), "text": text[:80],
                          "cps": round(cps, 1), "wpm": round(words / dur * 60) if dur > 0 else None,
                          "issues": issues})
        prev = c
    return {"file": path, "cues": len(cues), "failing": len(fails),
            "mean_cps": round(total_chars / total_time, 1) if total_time else None,
            "failures": fails[:a.max_items], "warnings": warns[:a.max_items],
            "verdict": "fail" if fails or not cues else "pass"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+")
    p.add_argument("--max-lines", type=int, default=2)
    p.add_argument("--max-chars", type=int, default=40)
    p.add_argument("--min-dur", type=float, default=5 / 6)
    p.add_argument("--max-dur", type=float, default=7.0)
    p.add_argument("--max-cps", type=float, default=20.0)
    p.add_argument("--relabel-after", type=float, default=90.0)
    p.add_argument("--speakers-need-labels", action="store_true",
                   help="unlabelled speaker changes fail instead of warn")
    p.add_argument("--no-label-speakers", default="", help="comma list of exempt speakers")
    p.add_argument("--max-items", type=int, default=100)
    a = p.parse_args(argv)
    a.no_label_speakers = {s.strip() for s in a.no_label_speakers.split(",") if s.strip()}
    paths = []
    for f in a.files:
        hits = sorted(glob.glob(f, recursive=True)) if any(ch in f for ch in "*?[") else [f]
        paths += hits or [f]
    results = []
    for path in paths:
        if not os.path.isfile(path):
            results.append({"file": path, "verdict": "fail", "error": "not found"})
            continue
        try:
            if path.lower().endswith((".csv", ".json")):
                cues = parse_table(path)
            else:
                with open(path, encoding="utf-8-sig") as fh:
                    cues = parse_timed(fh.read())
            results.append(check(path, cues, a))
        except (ValueError, KeyError) as exc:
            results.append({"file": path, "verdict": "fail", "error": f"parse error: {exc}"})
    out = {"verdict": "pass" if all(r["verdict"] == "pass" for r in results) else "fail",
           "files": results}
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(out, indent=1, ensure_ascii=False))
    sys.exit(0 if out["verdict"] == "pass" else 1)


if __name__ == "__main__":
    main()
