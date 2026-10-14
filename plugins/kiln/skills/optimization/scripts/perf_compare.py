"""Compare two frame-time recordings (before / after one change) and say whether it helped.

  python perf_compare.py <before> <after> [--key frame_ms] [--skip 0] [--min-samples 120]
         [--min-ms 0.1] [--min-pct 2] [--hitch-ms 50] [--hitch-tol 0]
         [--expect no-regress|improve]

Inputs (milliseconds; values <= 0 are dropped):
  - the acceptance recorder dump (recorder.gd): {"frame_ms": [...], "samples": {...}} — --key is
    a top-level list or a list under "samples" (e.g. a gpu_ms probe);
  - JSON Lines (Unity/Unreal probes): one object per line, --key read from each line;
  - CSV with a header (Unreal csvprofile): column --key, e.g. --key FrameTime.
recorder.gd (format kiln-probe/2) records frame_ms as the real time between rendered frames,
measured in _process, and gpu_ms from the RenderingServer measure APIs — compare GPU time with
--key gpu_ms.

Metrics per recording: mean, p50, p95, p99, max (ms); p1_fps = 1000 / p99; low1 = time-weighted
1% low (sort frame times slowest first, add them up until they reach 1% of the run time; that
frame's time is low1_ms, 1000 / it is low1_fps); hitches = frames > 2x the rolling median of the
last 31 frames or > --hitch-ms.

A delta is significant only when it exceeds max(--min-ms, --min-pct % of before, noise); noise is
the larger split-half difference (first half vs second half) of the metric in either recording.
Primary metrics (lower is better): p50_ms, p95_ms, p99_ms, low1_ms.
  change = regressed  if any primary metric is significantly worse or hitches rise by more than
                      --hitch-tol;
           improved   if any primary metric is significantly better and nothing regressed;
           unchanged  otherwise.
  verdict = pass/fail for --expect: no-regress (default) passes unless regressed; improve passes
            only if improved. Too few samples (< --min-samples after --skip) fails.
Prints one JSON object; exit code 1 when the verdict is fail.
"""

import argparse
import csv
import json
import math
import os
import statistics
import sys

PRIMARY = ("p50_ms", "p95_ms", "p99_ms", "low1_ms")


def load_series(path, key):
    """Frame times in ms from a recorder dump, JSON Lines or CSV file."""
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    values = None
    if path.lower().endswith(".csv"):
        rows = csv.DictReader(text.splitlines())
        column = next((c for c in (rows.fieldnames or []) if c.strip().lower() == key.lower()),
                      None)
        if column is None:
            raise ValueError(f"{path}: no column '{key}' (have {rows.fieldnames})")
        values = [row[column] for row in rows if (row.get(column) or "").strip()]
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            if isinstance(data.get(key), list):
                values = data[key]
            elif isinstance(data.get("samples"), dict) and isinstance(data["samples"].get(key), list):
                values = data["samples"][key]
            else:
                raise ValueError(f"{path}: no list '{key}' at top level or under 'samples'")
        elif isinstance(data, list):
            values = data
        else:  # JSON Lines
            values = []
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict) and key in obj:
                    values.append(obj[key])
            if not values:
                raise ValueError(f"{path}: no '{key}' values in JSON Lines")
    out = []
    for v in values:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f) and f > 0:
            out.append(f)
    return out


def percentile(sorted_ms, q):
    """Linear interpolation between closest ranks (numpy's default)."""
    if not sorted_ms:
        return None
    pos = (len(sorted_ms) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_ms) - 1)
    return sorted_ms[lo] + (sorted_ms[hi] - sorted_ms[lo]) * (pos - lo)


def low1_ms(ms):
    """Time-weighted 1% low: the frame at which the slowest frames reach 1% of run time."""
    budget = 0.01 * sum(ms)
    acc = 0.0
    for v in sorted(ms, reverse=True):
        acc += v
        if acc >= budget:
            return v
    return max(ms)


def hitches(ms, hitch_ms):
    count = 0
    for i, v in enumerate(ms):
        window = ms[max(0, i - 30):i + 1]
        if v > 2.0 * statistics.median(window) or v > hitch_ms:
            count += 1
    return count


def metrics(ms):
    s = sorted(ms)
    p99 = percentile(s, 99)
    low = low1_ms(ms)
    return {
        "mean_ms": statistics.fmean(ms),
        "p50_ms": percentile(s, 50),
        "p95_ms": percentile(s, 95),
        "p99_ms": p99,
        "low1_ms": low,
        "max_ms": s[-1],
        "p1_fps": 1000.0 / p99,
        "low1_fps": 1000.0 / low,
    }


def split_noise(ms):
    half = len(ms) // 2
    a, b = metrics(ms[:half]), metrics(ms[half:])
    return {k: abs(a[k] - b[k]) for k in PRIMARY}


def r(x, nd=3):
    return None if x is None else round(x, nd)


def compare(before, after, args):
    problems = []
    for name, ms in (("before", before), ("after", after)):
        if len(ms) < args.min_samples:
            problems.append(f"{name}: {len(ms)} samples < {args.min_samples}")
    if problems:
        return {"change": "insufficient", "problems": problems, "verdict": "fail"}

    mb, ma = metrics(before), metrics(after)
    nb, na = split_noise(before), split_noise(after)
    hb, ha = hitches(before, args.hitch_ms), hitches(after, args.hitch_ms)
    deltas, worse, better = {}, [], []
    for k in PRIMARY:
        delta = ma[k] - mb[k]
        threshold = max(args.min_ms, mb[k] * args.min_pct / 100.0, nb[k], na[k])
        significant = abs(delta) > threshold
        direction = "same" if not significant else ("worse" if delta > 0 else "better")
        if direction == "worse":
            worse.append(k)
        elif direction == "better":
            better.append(k)
        deltas[k] = {"before": r(mb[k]), "after": r(ma[k]), "delta": r(delta),
                     "pct": r(100.0 * delta / mb[k], 1), "threshold": r(threshold),
                     "direction": direction}
    if worse:
        problems.append("worse beyond noise: " + ", ".join(worse))
    if ha > hb + args.hitch_tol:
        problems.append(f"hitches {hb} -> {ha}")
    change = "regressed" if problems else ("improved" if better else "unchanged")
    ok = change != "regressed" if args.expect == "no-regress" else change == "improved"
    if args.expect == "improve" and change == "unchanged":
        problems.append("no primary metric improved beyond noise")
    return {
        "before": {**{k: r(v) for k, v in mb.items()}, "samples": len(before), "hitches": hb},
        "after": {**{k: r(v) for k, v in ma.items()}, "samples": len(after), "hitches": ha},
        "deltas": deltas,
        "change": change,
        "problems": problems,
        "verdict": "pass" if ok else "fail",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--key", default="frame_ms")
    ap.add_argument("--skip", type=int, default=0, help="warm-up samples dropped from each run")
    ap.add_argument("--min-samples", type=int, default=120)
    ap.add_argument("--min-ms", type=float, default=0.1)
    ap.add_argument("--min-pct", type=float, default=2.0)
    ap.add_argument("--hitch-ms", type=float, default=50.0)
    ap.add_argument("--hitch-tol", type=int, default=0)
    ap.add_argument("--expect", choices=("no-regress", "improve"), default="no-regress")
    args = ap.parse_args(argv)
    try:
        before = load_series(args.before, args.key)[args.skip:]
        after = load_series(args.after, args.key)[args.skip:]
    except (OSError, ValueError) as exc:
        print(json.dumps({"metric": "frame_compare", "error": str(exc), "verdict": "fail"}))
        return 1
    result = {"metric": "frame_compare", "key": args.key, "expect": args.expect,
              "files": [os.path.basename(args.before), os.path.basename(args.after)],
              **compare(before, after, args)}
    print(json.dumps(result))
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
