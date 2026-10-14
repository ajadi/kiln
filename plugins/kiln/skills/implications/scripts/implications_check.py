"""Check a task file's implications section (Python 3.12+, stdlib only).

  python implications_check.py tasks/TASK-019.md [--max-ripple 12] [--require]

Reads `## implications` and its `### <thing> (category: <category>)` blocks of `- key: value`
lines. Every thing needs the core keys (job, states, home, interfaces, empty, transitions, ripple,
premortem) plus its category's keys (handheld: grip, carry; wearable: region, left_behind;
consumable: container, after_use; vehicle-part: mount, removed; environment: signifier,
persistence; ability: source, unavailable), each with content or "n/a — <reason>" ("n/a" alone
fails). Also: premortem lists >= 2 risks; ripple stays within --max-ripple entries (scope guard);
interfaces name the host-side assets ("host" in the line, or n/a with a reason).
With --require the file must contain the section (use it when the task adds a new thing).
Prints {"verdict", "things": [...], "problems": [...]}; exit 1 on FAIL, 2 on bad input.
"""

import argparse
import json
import re
import sys

CORE = ["job", "states", "home", "interfaces", "empty", "transitions", "ripple", "premortem"]
CATEGORY = {
    "handheld": ["grip", "carry"],
    "wearable": ["region", "left_behind"],
    "consumable": ["container", "after_use"],
    "vehicle-part": ["mount", "removed"],
    "environment": ["signifier", "persistence"],
    "ability": ["source", "unavailable"],
}
HEAD = re.compile(r"^###\s+(.+?)\s*\(category:\s*([a-z-]+)\s*\)\s*$")
ITEM = re.compile(r"^-\s*([a-z_]+)\s*:\s*(.*)$")


def section(text):
    m = re.search(r"^##\s+implications\s*$", text, re.M | re.I)
    if not m:
        return None
    rest = text[m.end():]
    nxt = re.search(r"^##\s+\S", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


def parse(body):
    things, cur = [], None
    for line in body.splitlines():
        h = HEAD.match(line.strip())
        if h:
            cur = {"name": h.group(1), "category": h.group(2), "keys": {}}
            things.append(cur)
            continue
        if line.strip().startswith("###"):
            cur = {"name": line.strip("# ").strip(), "category": None, "keys": {}}
            things.append(cur)
            continue
        it = ITEM.match(line.strip())
        if it and cur is not None:
            cur["keys"][it.group(1)] = it.group(2).strip()
    return things


def check(thing, max_ripple):
    problems = []
    name = thing["name"]
    cat = thing["category"]
    if cat not in CATEGORY:
        problems.append(f"{name}: category '{cat}' unknown (use one of {', '.join(CATEGORY)})")
        needed = CORE
    else:
        needed = CORE + CATEGORY[cat]
    for key in needed:
        value = thing["keys"].get(key)
        if not value:
            problems.append(f"{name}: missing '{key}'")
        elif re.fullmatch(r"n/?a\.?", value.strip(), re.I):
            problems.append(f"{name}: '{key}' is n/a without a reason")
    pm = thing["keys"].get("premortem", "")
    if pm and len([p for p in re.split(r"[;\n]|\d\)", pm) if p.strip()]) < 2:
        problems.append(f"{name}: premortem needs at least 2 risks")
    rp = thing["keys"].get("ripple", "")
    if rp and len([r for r in re.split(r"[;,]", rp) if r.strip()]) > max_ripple:
        problems.append(f"{name}: ripple has more than {max_ripple} entries (scope: two rings, "
                        "only what the player sees or what blocks other work)")
    itf = thing["keys"].get("interfaces", "")
    if itf and "host" not in itf.lower() and not itf.lower().startswith("n/a"):
        problems.append(f"{name}: interfaces don't name the host-side assets ('host assets: ...')")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("task")
    ap.add_argument("--max-ripple", type=int, default=12)
    ap.add_argument("--require", action="store_true")
    a = ap.parse_args(argv)
    try:
        with open(a.task, encoding="utf-8-sig") as fh:
            text = fh.read()
    except OSError as exc:
        print(json.dumps({"verdict": "ERROR", "reason": str(exc)}))
        return 2
    body = section(text)
    if body is None:
        verdict = "FAIL" if a.require else "NOT ASSESSED"
        print(json.dumps({"verdict": verdict, "things": [],
                          "problems": ["no '## implications' section"]}))
        return 1 if a.require else 0
    things = parse(body)
    problems = []
    if not things:
        problems.append("implications section has no '### <thing> (category: ...)' block")
    for t in things:
        problems.extend(check(t, a.max_ripple))
    verdict = "FAIL" if problems else "PASS"
    print(json.dumps({"verdict": verdict,
                      "things": [{"name": t["name"], "category": t["category"],
                                  "keys": sorted(t["keys"])} for t in things],
                      "problems": problems}, ensure_ascii=False))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
