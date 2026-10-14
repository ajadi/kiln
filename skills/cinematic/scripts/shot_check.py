"""Cinematic checks with numbers: shot-list continuity and subtitle timing. Stdlib only.

  python shot_check.py shots <shots.json>
  python shot_check.py subs <file.srt> --fps 24 [--cps 20] [--max-line 40] [--max-lines 2]
                             [--min-frames 20] [--gap-frames 2] [--max-s 7]

shots   reads {"fps": 24, "up": "y"|"z", "subjects": {"name": [x, y, z]}, "shots": [{"id",
        "start", "end" (seconds), "camera": {"pos": [x, y, z]}, "subject": name, "axis":
        [name, name], "focal_mm"?, "cross_line"?: reason}]} - camera and subject positions
        measured in the engine or Blender at the shot's first frame. Fails on:
        - a gap or overlap between consecutive shots larger than one frame;
        - the 180-degree line: consecutive shots with the same axis whose cameras sit on
          opposite sides of it (ground plane), unless the later shot has "cross_line" with
          the reason (a move across the line on screen, a neutral shot first);
        - the 30-degree rule: consecutive shots on the same subject whose camera directions
          differ by less than 30 degrees around it while the focal length changes by less
          than 1.5x (a jump cut).
        Reports mean and shortest/longest shot length.
subs    SubRip file: reading speed <= --cps characters per second (Netflix adults 20, children
        17), <= --max-line characters per line and <= --max-lines lines (Xbox Accessibility
        Guideline 104: 40 and 2), duration >= --min-frames (Netflix: 20 frames), gap between
        cues >= --gap-frames (2); longer than --max-s seconds is a warning.
Output: JSON with "verdict" and "problems"; exit 1 on fail.
"""

import argparse
import json
import math
import re
import sys


def ground(p, up):
    return (p[0], p[2]) if up == "y" else (p[0], p[1])


def side(a, b, c):
    """Sign of the camera c relative to the line a-b on the ground plane."""
    cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (cross > 0) - (cross < 0)


def angle_between(u, v):
    d = math.degrees(math.atan2(v[1], v[0]) - math.atan2(u[1], u[0]))
    return abs((d + 180) % 360 - 180)


def check_shots(path):
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    fps, up = spec.get("fps", 24), spec.get("up", "y")
    subjects = {k: ground(v, up) for k, v in spec.get("subjects", {}).items()}
    shots = sorted(spec["shots"], key=lambda s: s["start"])
    problems, warnings = [], []
    for prev, cur in zip(shots, shots[1:]):
        pair = f"shot {prev['id']} -> {cur['id']}"
        delta = cur["start"] - prev["end"]
        if abs(delta) > 1.0 / fps + 1e-9:
            problems.append(f"{pair}: {'gap' if delta > 0 else 'overlap'} of "
                            f"{abs(delta):.3f} s ({abs(delta) * fps:.1f} frames) in the timeline")
        pc, cc = ground(prev["camera"]["pos"], up), ground(cur["camera"]["pos"], up)
        axis = cur.get("axis")
        if axis and axis == prev.get("axis") and all(n in subjects for n in axis):
            a, b = subjects[axis[0]], subjects[axis[1]]
            if side(a, b, pc) * side(a, b, cc) < 0 and not cur.get("cross_line"):
                problems.append(f"{pair}: crosses the 180-degree line {axis[0]}-{axis[1]} "
                                "(screen direction flips); move the camera back or add "
                                "\"cross_line\" with the reason")
        subj = cur.get("subject")
        if subj and subj == prev.get("subject") and subj in subjects:
            s = subjects[subj]
            turn = angle_between((pc[0] - s[0], pc[1] - s[1]), (cc[0] - s[0], cc[1] - s[1]))
            f1, f2 = prev.get("focal_mm"), cur.get("focal_mm")
            size_change = f1 and f2 and max(f1, f2) / min(f1, f2) >= 1.5
            if turn < 30 and not size_change:
                problems.append(f"{pair}: same subject {subj}, camera turns {turn:.1f} degrees "
                                "(under 30) without a clear change of shot size - a jump cut")
    lengths = [s["end"] - s["start"] for s in shots]
    for s, n in zip(shots, lengths):
        if n <= 0:
            problems.append(f"shot {s['id']}: ends before it starts")
    return {"verdict": "fail" if problems else "pass", "problems": problems,
            "warnings": warnings, "shots": len(shots),
            "mean_shot_s": round(sum(lengths) / len(lengths), 3) if lengths else 0,
            "shortest_s": min(lengths, default=0), "longest_s": max(lengths, default=0)}


TIME = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d{1,3})")


def seconds(text):
    h, m, s, ms = TIME.match(text.strip()).groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def read_srt(path):
    with open(path, encoding="utf-8-sig") as fh:
        blocks = re.split(r"\n\s*\n", fh.read().replace("\r\n", "\n").strip())
    cues = []
    for block in blocks:
        lines = block.split("\n")
        at = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if at is None:
            continue
        a, b = lines[at].split("-->")
        cues.append((seconds(a), seconds(b), [l for l in lines[at + 1:] if l.strip()]))
    return cues


def check_subs(a):
    cues = read_srt(a.file)
    problems, warnings = [], []
    for i, (start, end, lines) in enumerate(cues, 1):
        dur = end - start
        chars = sum(len(l.strip()) for l in lines)
        if dur > 0 and chars / dur > a.cps:
            problems.append(f"cue {i}: {chars / dur:.1f} chars/s > {a.cps}")
        if dur * a.fps < a.min_frames - 1e-6:
            problems.append(f"cue {i}: {dur * a.fps:.0f} frames on screen < {a.min_frames} frames")
        if dur > a.max_s:
            warnings.append(f"cue {i}: {dur:.1f} s on screen > {a.max_s} s")
        if len(lines) > a.max_lines:
            problems.append(f"cue {i}: {len(lines)} lines > {a.max_lines}")
        longest = max((len(l.strip()) for l in lines), default=0)
        if longest > a.max_line:
            problems.append(f"cue {i}: {longest} chars per line > {a.max_line}")
        if i > 1:
            gap = start - cues[i - 2][1]
            if gap * a.fps < a.gap_frames - 1e-6:
                problems.append(f"cue {i}: gap to the previous cue {gap * a.fps:.1f} frames "
                                f"< {a.gap_frames}")
    return {"verdict": "fail" if problems else "pass", "problems": problems,
            "warnings": warnings, "cues": len(cues)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shots"); s.add_argument("file")
    t = sub.add_parser("subs"); t.add_argument("file")
    t.add_argument("--fps", type=float, default=24); t.add_argument("--cps", type=float, default=20)
    t.add_argument("--max-line", type=int, default=40); t.add_argument("--max-lines", type=int, default=2)
    t.add_argument("--min-frames", type=float, default=20)
    t.add_argument("--gap-frames", type=float, default=2); t.add_argument("--max-s", type=float, default=7)
    a = ap.parse_args()
    res = check_shots(a.file) if a.cmd == "shots" else check_subs(a)
    print(json.dumps(res, indent=1))
    sys.exit(1 if res["verdict"] == "fail" else 0)


if __name__ == "__main__":
    main()
