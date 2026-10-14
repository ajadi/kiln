"""Validate exported procedural layouts (stdlib only) — run it over many seeds, not one.

  python procgen_check.py production/procgen/layouts/*.json
  python procgen_check.py "layouts/**/*.json" --min-path 6 --max-path 14 --max-step 2
                          --max-dead-end-ratio 0.4 --strict-dead-ends --out production/procgen/check.json

Layout JSON, one file per seed, written by the generator:

  room graph  {"seed": 1234, "type": "graph",
               "rooms": [{"id": "r0", "tags": ["start"]},
                         {"id": "r1", "difficulty": 2, "key": "red"},
                         {"id": "r2", "tags": ["exit"], "difficulty": 4},
                         {"id": "r3", "tags": ["reward"]}],
               "edges": [{"a": "r0", "b": "r1"}, {"a": "r1", "b": "r2", "lock": "red"},
                         {"a": "r1", "b": "r3", "oneway": true, "length": 2}]}
     tags: start (exactly one), exit (one or more), goal/boss (must be reachable), reward,
     secret, shortcut (a dead end that pays off); "key" on a room, "lock" on an edge (keys are
     kept once picked up); "oneway" allows a -> b only; "length" weights the critical path.

  grid        {"seed": 1234, "type": "grid", "diagonal": false, "legend": {"~": "floor"},
               "cells": ["#########",
                         "#@..a#..#",
                         "#....A.>#",
                         "#########"]}
     default legend: '#' wall, ' ' void, '.' floor, '@' start, '>' exit, '$' goal, a-z key,
     A-Z door opened by the same letter; legend values wall|void|floor|start|exit|goal|key:<id>|
     door:<id>. Moves are 4-neighbour (8 with "diagonal", no corner cutting).

Per layout: one start; every exit, goal and key reachable from the start, collecting keys on the
way; no lock whose key cannot be reached; no softlock (graph: every reachable state can still
reach an exit, one-way edges included); critical path (start to the nearest exit, key detours
included) inside --min-path/--max-path (rooms for graphs, cells for grids); dead-end ratio (graph:
degree-1 rooms other than start/exit) and dead ends that pay off; unreachable rooms or floor cells;
difficulty along the critical path (no step up larger than --max-step; the last third not easier
than the first). Prints JSON with "verdict" and every failing seed; exit code 1 on fail.
"""

import argparse
import glob as globlib
import heapq
import json
import os
import statistics
import sys
from collections import deque

PAYOFF = {"reward", "secret", "shortcut", "goal", "boss"}
MAX_STATES = 3_000_000


# ---------------------------------------------------------------- generic state search

def search(start_state, neighbours, is_goal):
    """Dijkstra over (node, keymask) states: (dist, prev, goal_state or None, capped)."""
    dist, prev = {start_state: 0}, {start_state: None}
    heap, best, capped = [(0, 0, start_state)], None, False
    counter = 0
    while heap:
        d, _, state = heapq.heappop(heap)
        if d > dist.get(state, float("inf")):
            continue
        if best is None and is_goal(state):
            best = state
        for nxt, w in neighbours(state):
            nd = d + w
            if nd < dist.get(nxt, float("inf")):
                if len(dist) >= MAX_STATES and nxt not in dist:
                    capped = True
                    continue
                dist[nxt], prev[nxt] = nd, state
                counter += 1
                heapq.heappush(heap, (nd, counter, nxt))
    return dist, prev, best, capped


def path_to(prev, state):
    out = []
    while state is not None:
        out.append(state)
        state = prev[state]
    return out[::-1]


def summary_problem(res, text):
    res["problems"].append(text)


# ---------------------------------------------------------------- graph layouts

def check_graph(layout, args, res):
    rooms = {str(r["id"]): r for r in layout.get("rooms") or []}
    if len(rooms) != len(layout.get("rooms") or []):
        summary_problem(res, "duplicate room ids")
    tags = {rid: set(r.get("tags") or []) for rid, r in rooms.items()}
    starts = [rid for rid, t in tags.items() if "start" in t]
    exits = {rid for rid, t in tags.items() if "exit" in t}
    goals = {rid for rid, t in tags.items() if t & {"goal", "boss"}}
    key_of = {rid: str(r["key"]) for rid, r in rooms.items() if r.get("key") is not None}
    key_ids = sorted(set(key_of.values()))
    bit = {k: 1 << i for i, k in enumerate(key_ids)}
    out = {rid: [] for rid in rooms}
    undirected = {rid: set() for rid in rooms}
    locks = set()
    for e in layout.get("edges") or []:
        a, b = str(e.get("a")), str(e.get("b"))
        if a not in rooms or b not in rooms:
            summary_problem(res, f"edge {a}-{b} names a missing room")
            continue
        lock = None if e.get("lock") is None else str(e["lock"])
        if lock is not None:
            locks.add(lock)
            if lock not in bit:
                summary_problem(res, f"edge {a}-{b} locked by '{lock}' but no room holds that "
                                "key")
        w = float(e.get("length", 1))
        out[a].append((b, lock, w))
        if not e.get("oneway"):
            out[b].append((a, lock, w))
        undirected[a].add(b)
        undirected[b].add(a)
    if len(starts) != 1:
        summary_problem(res, f"{len(starts)} start rooms (exactly one needed)")
        return
    if not exits:
        summary_problem(res, "no exit room")
        return
    start = starts[0]

    def gain(rid, mask):
        return mask | bit.get(key_of.get(rid), 0)

    def neighbours(state):
        rid, mask = state
        for nxt, lock, w in out[rid]:
            if lock is None or (lock in bit and mask & bit[lock]):
                yield (nxt, gain(nxt, mask)), w

    init = (start, gain(start, 0))
    dist, prev, best, capped = search(init, neighbours, lambda s: s[0] in exits)
    if capped:
        res["warnings"].append(f"state space capped at {MAX_STATES}; results partial")
    reached = {rid for rid, _ in dist}
    reached_keys = {key_of[r] for r in reached if r in key_of}
    for rid in sorted(exits | goals):
        if rid not in reached:
            summary_problem(res, f"{'exit' if rid in exits else 'goal'} {rid} unreachable")
    for rid, key in sorted(key_of.items()):
        if rid not in reached:
            summary_problem(res, f"key '{key}' in room {rid} unreachable (behind its own lock?)")
    for lock in sorted(locks - reached_keys):
        if lock in bit:
            res["warnings"].append(f"lock '{lock}' can never open")
    for key in sorted(set(key_ids) - locks):
        res["warnings"].append(f"key '{key}' opens nothing")
    orphans = sorted(set(rooms) - reached)
    if orphans:
        summary_problem(res, f"{len(orphans)} unreachable rooms: {', '.join(orphans[:8])}")
    # softlocks: reachable states from which no exit state can be reached
    back = {}
    for state in dist:
        for nxt, _ in neighbours(state):
            back.setdefault(nxt, []).append(state)
    good = deque(s for s in dist if s[0] in exits)
    alive = set(good)
    while good:
        for p in back.get(good.popleft(), []):
            if p not in alive:
                alive.add(p)
                good.append(p)
    dead = [s for s in dist if s not in alive]
    if dead and not capped and best is not None:
        rid, mask = min(dead, key=lambda s: dist[s])
        held = [k for k in key_ids if mask & bit[k]]
        summary_problem(res, f"softlock: {len(dead)} reachable states cannot reach an exit, "
                             f"e.g. room {rid} holding keys {held or 'none'} (one-way edge?)")
    if best is not None:
        rooms_path = [s[0] for s in path_to(prev, best)]
        res["critical_path"] = len(rooms_path)
        res["critical_path_length"] = round(dist[best], 3)
        res["critical_path_rooms"] = rooms_path
        seen, order = set(), []
        for rid in rooms_path:
            if rid not in seen:
                seen.add(rid)
                order.append(rid)
        diffs = [float(rooms[r]["difficulty"]) for r in order
                 if rooms[r].get("difficulty") is not None]
        res["difficulty_along_path"] = diffs
        if len(diffs) >= 2:
            jumps = [b - a for a, b in zip(diffs, diffs[1:])]
            if max(jumps) > args.max_step:
                i = jumps.index(max(jumps))
                summary_problem(res, f"difficulty jumps +{max(jumps):g} between critical-path "
                                     f"rooms {i + 1} and {i + 2} (max +{args.max_step:g})")
        if len(diffs) >= 3:
            third = max(1, len(diffs) // 3)
            if statistics.mean(diffs[-third:]) < statistics.mean(diffs[:third]):
                summary_problem(res, "difficulty falls along the critical path (last third "
                                     "easier than the first)")
    degree = {rid: len(n) for rid, n in undirected.items()}
    dead_ends = [rid for rid, d in degree.items() if d == 1 and not tags[rid] & {"start", "exit"}]
    empty = [rid for rid in dead_ends if not tags[rid] & PAYOFF and rid not in key_of]
    edges = sum(degree.values()) // 2
    components = count_components(undirected)
    res.update(rooms=len(rooms), dead_ends=len(dead_ends),
               dead_end_ratio=round(len(dead_ends) / len(rooms), 3) if rooms else 0.0,
               empty_dead_ends=empty, loops=edges - len(rooms) + components)
    if args.max_dead_end_ratio is not None and res["dead_end_ratio"] > args.max_dead_end_ratio:
        summary_problem(res, f"dead-end ratio {res['dead_end_ratio']} > "
                             f"{args.max_dead_end_ratio}")
    if empty:
        text = f"{len(empty)} dead ends with no reward/key/secret/shortcut: {', '.join(empty[:8])}"
        (res["problems"] if args.strict_dead_ends else res["warnings"]).append(text)


def count_components(adj):
    seen, n = set(), 0
    for node in adj:
        if node in seen:
            continue
        n += 1
        stack = [node]
        seen.add(node)
        while stack:
            for nxt in adj[stack.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
    return n


# ---------------------------------------------------------------- grid layouts

def default_role(ch):
    fixed = {"#": "wall", " ": "void", ".": "floor", "@": "start", ">": "exit", "$": "goal"}
    if ch in fixed:
        return fixed[ch]
    if "a" <= ch <= "z":
        return f"key:{ch}"
    if "A" <= ch <= "Z":
        return f"door:{ch.lower()}"
    return None


def check_grid(layout, args, res):
    rows = [str(r) for r in layout.get("cells") or []]
    width = max((len(r) for r in rows), default=0)
    rows = [r.ljust(width) for r in rows]
    legend = {str(k): str(v) for k, v in (layout.get("legend") or {}).items()}
    roles, unknown = {}, set()
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            role = legend.get(ch) or default_role(ch)
            if role is None:
                unknown.add(ch)
                role = "wall"
            roles[(x, y)] = role
    if unknown:
        summary_problem(res, f"characters not in the legend: {''.join(sorted(unknown))!r}")
    starts = [c for c, r in roles.items() if r == "start"]
    exits = {c for c, r in roles.items() if r == "exit"}
    goals = {c for c, r in roles.items() if r == "goal"}
    keys = {c: r.split(":", 1)[1] for c, r in roles.items() if r.startswith("key:")}
    doors = {c: r.split(":", 1)[1] for c, r in roles.items() if r.startswith("door:")}
    key_ids = sorted(set(keys.values()))
    bit = {k: 1 << i for i, k in enumerate(key_ids)}
    for lock in sorted(set(doors.values()) - set(key_ids)):
        summary_problem(res, f"door '{lock}' has no key in the layout")
    if len(starts) != 1:
        summary_problem(res, f"{len(starts)} start cells (exactly one needed)")
        return
    if not exits:
        summary_problem(res, "no exit cell")
        return
    solid = {"wall", "void"}

    def open_cell(c):
        return c in roles and roles[c] not in solid

    def free(c):
        return open_cell(c) and c not in doors

    steps = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    if layout.get("diagonal"):
        steps += [(1, 1), (1, -1), (-1, 1), (-1, -1)]

    def neighbours(state):
        (x, y), mask = state
        for dx, dy in steps:
            c = (x + dx, y + dy)
            if not open_cell(c):
                continue
            if dx and dy and not (free((x + dx, y)) and free((x, y + dy))):
                continue  # no corner cutting
            if c in doors and not mask & bit.get(doors[c], 0):
                continue
            yield (c, mask | bit.get(keys.get(c), 0)), 1

    start = starts[0]
    init = (start, bit.get(keys.get(start), 0))
    dist, prev, best, capped = search(init, neighbours, lambda s: s[0] in exits)
    if capped:
        res["warnings"].append(f"state space capped at {MAX_STATES}; results partial")
    reached = {c for c, _ in dist}
    for c in sorted(exits | goals):
        if c not in reached:
            summary_problem(res, f"{roles[c]} at x={c[0]} y={c[1]} unreachable")
    for c, key in sorted(keys.items()):
        if c not in reached:
            summary_problem(res, f"key '{key}' at x={c[0]} y={c[1]} unreachable")
    floor = [c for c in roles if free(c)]
    lost = [c for c in floor if c not in reached]
    share = round(len(lost) / len(floor), 4) if floor else 0.0
    res["unreachable_floor_ratio"] = share
    if share > args.max_unreachable:
        c = lost[0]
        summary_problem(res, f"{len(lost)} floor cells unreachable ({share:.1%}), e.g. x={c[0]} "
                             f"y={c[1]} — fill the pockets or connect them")
    if best is not None:
        res["critical_path"] = int(dist[best]) + 1
    tips = [c for c in roles if open_cell(c) and roles[c] == "floor"
            and sum(open_cell((c[0] + dx, c[1] + dy)) for dx, dy in steps[:4]) == 1]
    res.update(open_cells=sum(1 for c in roles if open_cell(c)), dead_end_tips=len(tips))
    if args.max_dead_end_tips is not None and len(tips) > args.max_dead_end_tips:
        summary_problem(res, f"{len(tips)} dead-end corridor tips > {args.max_dead_end_tips}")


# ---------------------------------------------------------------- driver

def check_file(path, args):
    res = {"file": path.replace("\\", "/"), "problems": [], "warnings": []}
    try:
        with open(path, encoding="utf-8-sig") as fh:
            layout = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        summary_problem(res, f"unreadable: {exc}")
        res["verdict"] = "fail"
        return res
    if not isinstance(layout, dict):
        summary_problem(res, "layout must be a JSON object")
        res["verdict"] = "fail"
        return res
    res["seed"] = layout.get("seed")
    if res["seed"] is None:
        res["warnings"].append("no seed recorded — a failure cannot be replayed")
    kind = layout.get("type") or ("grid" if "cells" in layout else "graph")
    res["type"] = kind
    if kind == "grid":
        check_grid(layout, args, res)
    elif kind == "graph":
        check_graph(layout, args, res)
    else:
        summary_problem(res, f"unknown layout type {kind!r}")
    path_len = res.get("critical_path")
    if path_len is not None:
        if args.min_path is not None and path_len < args.min_path:
            summary_problem(res, f"critical path {path_len} < {args.min_path:g}")
        if args.max_path is not None and path_len > args.max_path:
            summary_problem(res, f"critical path {path_len} > {args.max_path:g}")
    res["verdict"] = "fail" if res["problems"] else "pass"
    return res


def spread(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {"min": min(values), "median": statistics.median(values), "max": max(values)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("layouts", nargs="+", help="layout JSON files or globs")
    parser.add_argument("--min-path", type=float, default=None)
    parser.add_argument("--max-path", type=float, default=None)
    parser.add_argument("--max-step", type=float, default=2.0,
                        help="largest difficulty step up between critical-path rooms")
    parser.add_argument("--max-dead-end-ratio", type=float, default=0.4)
    parser.add_argument("--strict-dead-ends", action="store_true",
                        help="dead ends without a payoff fail instead of warn")
    parser.add_argument("--max-unreachable", type=float, default=0.0,
                        help="grid: allowed share of unreachable floor cells")
    parser.add_argument("--max-dead-end-tips", type=int, default=None)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    parser.add_argument("--out", default=None, help="also write the JSON report here")
    args = parser.parse_args(argv)
    files = sorted({p for pattern in args.layouts
                    for p in (globlib.glob(pattern, recursive=True) or
                              ([pattern] if os.path.exists(pattern) else []))
                    if os.path.isfile(p)})
    results = [check_file(f, args) for f in files]
    passed = sum(r["verdict"] == "pass" for r in results)
    rate = passed / len(results) if results else 0.0
    problems = [] if results else ["no layout files found"]
    if results and rate < args.min_pass_rate:
        problems.append(f"{len(results) - passed} of {len(results)} layouts fail "
                        f"(pass rate {rate:.1%} < {args.min_pass_rate:.0%})")
    report = {"layouts": len(results), "passed": passed, "pass_rate": round(rate, 4),
              "critical_path": spread([r.get("critical_path") for r in results]),
              "dead_end_ratio": spread([r.get("dead_end_ratio") for r in results]),
              "loops": spread([r.get("loops") for r in results]),
              "failing": [{"file": r["file"], "seed": r.get("seed"), "problems": r["problems"]}
                          for r in results if r["verdict"] == "fail"][:50],
              "results": results if len(results) <= 20 else
              [r for r in results if r["verdict"] == "fail"][:20],
              "problems": problems, "verdict": "fail" if problems else "pass"}
    text = json.dumps(report, indent=1, ensure_ascii=False)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
