"""Scope contract: what the milestone promises, counted from the project, never lowered silently.

  python scope.py check [production/SCOPE.md]

SCOPE.md lines:
  - [ ] combat arenas: 4 — count: glob:scenes/levels/arenas/*.tscn
  - [ ] enemy types: 3 — count: grep:^class_name\\s+\\w+Enemy\\b@scripts/**/*.gd
  - [ ] weapons: 3 — count: glob:data/weapons/*.tres
  - [ ] boss fight playable — manual          (ticked by hand when evidence exists)
  - [x] ... — BLOCKED: <reason>          (allowed: an explicit, visible exception)

Counters: glob:<pattern> (matching files), grep:<regex>@<glob> (matches across files),
lines:<regex>@<file> (matching lines in one file). A baseline of line names is kept in
.kiln/scope-baseline.json: removing or renaming a promised line is reported, so scope can only
be cut in the open (with a decision recorded), not by deleting the line.
Exit code 0 only when every line is met or BLOCKED.
"""

import glob as globlib
import json
import os
import re
import sys

CHECKBOX = re.compile(r"^\s*- \[([ x])\]\s*(.+)$")


def parse(line):
    """(checked, name, target, counter, manual, blocked) for a promise line, else None.
    Fields after the name are separated by ' — ': 'count: <spec>', 'manual', 'BLOCKED: why'."""
    m = CHECKBOX.match(line)
    if not m:
        return None
    parts = [p.strip() for p in re.split(r"\s+—\s+", m.group(2).strip())]
    nm = re.match(r"^(.+?):\s*(\d+)$", parts[0])
    name, target = (nm.group(1).strip(), int(nm.group(2))) if nm else (parts[0], None)
    counter, manual, blocked = None, False, False
    for part in parts[1:]:
        if part.startswith("count:"):
            counter = part[len("count:"):].strip()
        elif part == "manual":
            manual = True
        elif part.startswith("BLOCKED:"):
            blocked = True
    return m.group(1) == "x", name, target, counter, manual, blocked


def count(spec):
    kind, _, arg = spec.partition(":")
    if kind == "glob":
        return len(globlib.glob(arg, recursive=True))
    if kind in ("grep", "lines"):
        regex, _, target = arg.rpartition("@")
        files = globlib.glob(target, recursive=True)
        total = 0
        for path in files:
            try:
                text = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            total += len(re.findall(regex, text, re.M))
        return total
    raise ValueError(f"unknown counter {spec}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return
    path = sys.argv[2] if len(sys.argv) > 2 else os.path.join("production", "SCOPE.md")
    if not os.path.isfile(path):
        sys.exit(f"{path} not found — write the scope contract first (pipeline template SCOPE.md)")
    text = open(path, encoding="utf-8").read()
    names, ok_all, out_lines = [], True, []
    for line in text.splitlines():
        parsed = parse(line)
        if not parsed:
            out_lines.append(line)
            continue
        checked, name, target, counter, manual, blocked = parsed
        names.append(name)
        if counter and target is not None:
            have = count(counter)
            met = have >= target
            status = f"{have}/{target}"
        elif counter:
            met, status = False, "count without a number after the name ('name: N')"
        else:
            met, status = checked, "manual — tick it when the evidence is in a task file"
        if not met and not blocked:
            ok_all = False
        mark = "x" if met or blocked else " "
        print(f"[{'OK' if met else ('BLOCKED' if blocked else '  ')}] {name}: {status}")
        out_lines.append(re.sub(r"^(\s*- \[)[ x](\])", r"\1" + mark + r"\2", line))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out_lines) + "\n")
    base_path = os.path.join(".kiln", "scope-baseline.json")
    os.makedirs(".kiln", exist_ok=True)
    try:
        baseline = json.load(open(base_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        baseline = []
    missing = [n for n in baseline if n not in names]
    if missing:
        ok_all = False
        print("REMOVED OR RENAMED PROMISES (record a decision, then update the baseline by "
              "re-adding or marking BLOCKED):", "; ".join(missing))
    json.dump(sorted(set(baseline) | set(names)), open(base_path, "w", encoding="utf-8"), indent=1)
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
