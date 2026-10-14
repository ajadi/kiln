"""Fingerprint what an acceptance round judged, and check it at the next round. Stdlib only.

  python accepted.py snapshot [--probes "tests/probes/**/probe_qa_*"] [--scenes scenes/plaza.tscn ...]
                              [--out tests/probes/.accepted.json]
  python accepted.py check [tests/probes/.accepted.json]

snapshot  at the end of an acceptance round: sha256 and row count (check( / assert calls) of every
          acceptor probe, plus sha256 of the scenes the rows depend on (the level fingerprint).
check     at the start of the next round (and at the end of a long one): which acceptor probes
          changed, were added or removed, with their row counts before and after, and which
          scenes changed. Exit 1 when anything changed: the builder's change to an acceptor probe
          must be shown and reviewed (a probe row may have been weakened into a tautology), and a
          changed scene means rows that guard one of its features must be re-checked or given a
          synthetic copy of that feature on a test floor.

Acceptor probes are untracked while a task is open, so `git diff` has nothing to compare; this
file is the baseline (g2 rows 72, 92). Output: JSON; exit 0 unchanged, 1 changed, 2 no snapshot.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys

DEFAULT_OUT = "tests/probes/.accepted.json"
ROW = re.compile(r"\b(check|assert|expect)\s*\(")


def digest(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def rows(path):
    with open(path, encoding="utf-8", errors="ignore") as fh:
        return len(ROW.findall(fh.read()))


def norm(path):
    return os.path.relpath(path).replace("\\", "/")


def snapshot(args):
    probes = {}
    for pattern in args.probes:
        for path in sorted(glob.glob(pattern, recursive=True)):
            if os.path.isfile(path):
                probes[norm(path)] = {"sha256": digest(path), "rows": rows(path)}
    scenes = {norm(p): {"sha256": digest(p)} for p in args.scenes or [] if os.path.isfile(p)}
    missing = [p for p in args.scenes or [] if not os.path.isfile(p)]
    data = {"probes": probes, "scenes": scenes, "patterns": args.probes}
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    return {**data, "file": args.out, "missing_scenes": missing}, 0


def check(args):
    try:
        with open(args.file, encoding="utf-8") as fh:
            old = json.load(fh)
    except OSError:
        return {"problems": [f"no snapshot {args.file}: run `accepted.py snapshot` at the end "
                             "of the acceptance round"]}, 2
    now = {}
    for pattern in old.get("patterns", []):
        for path in sorted(glob.glob(pattern, recursive=True)):
            if os.path.isfile(path):
                now[norm(path)] = {"sha256": digest(path), "rows": rows(path)}
    changed, removed = [], []
    for path, was in old["probes"].items():
        cur = now.get(path)
        if cur is None:
            removed.append(path)
        elif cur["sha256"] != was["sha256"]:
            changed.append({"path": path, "rows": [was["rows"], cur["rows"]]})
    added = sorted(set(now) - set(old["probes"]))
    for path, was in old.get("scenes", {}).items():
        if not os.path.isfile(path):
            removed.append(path)
        elif digest(path) != was["sha256"]:
            changed.append({"path": path, "kind": "scene"})
    problems = []
    if changed or removed or added:
        problems.append("acceptor probes or judged scenes changed since the last round: review "
                        "each probe diff for weakened rows (fewer rows, wider thresholds, an "
                        "expected value read from the implementation) and re-run rows that "
                        "depend on a changed scene")
    return {"changed": changed, "added": added, "removed": removed, "problems": problems,
            "verdict": "fail" if problems else "pass"}, 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--probes", nargs="+", default=["tests/probes/**/probe_qa_*"])
    s.add_argument("--scenes", nargs="*", default=[])
    s.add_argument("--out", default=DEFAULT_OUT)
    c = sub.add_parser("check")
    c.add_argument("file", nargs="?", default=DEFAULT_OUT)
    args = ap.parse_args()
    res, code = (snapshot if args.cmd == "snapshot" else check)(args)
    print(json.dumps(res, indent=1))
    sys.exit(code)


if __name__ == "__main__":
    main()
