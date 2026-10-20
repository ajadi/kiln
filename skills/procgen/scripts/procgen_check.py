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
     door:<id>. Moves are 4-neighbour (8 with "diagonal", no corner cutting). "keys":
     "consumed" makes every door use up one key of its kind (then it stays open): spending a
     key on the wrong door is the classic softlock, and it is searched for.

  platformer  {"seed": 7, "type": "platformer", "jump": {"height": 3, "width": 4},
               "cells": ["#........>#", "#@...#####.", "####....###", ...]}
     side view, y down: '#' solid, '.' or ' ' air, '-' one-way platform, 'H' ladder, '^' hazard,
     '@' start, '>' exit, '$' goal (every one must be reachable), a-z key, A-Z door. The player
     walks, climbs, falls straight down and jumps up to jump.height tiles, then up to jump.width
     across (take both from the controller's feel constants). Optimistic model: a fail is a
     real dead level; a pass still needs the autoplay run. Softlock = a place reached by falling
     that the exit cannot be reached from (a pit deeper than the jump).

  sokoban     {"seed": 3, "type": "sokoban", "cells": ["#####", "#@$.#", "#####"]}
     standard push-box text; solved by search over pushes with dead squares pruned; past
     --max-states (default 300000) the result is "unknown" (a warning), not unsolvable.

  "return": true on any layout: the start must be reachable again from every goal and exit
  (hubs, fetch quests).

Per layout: one start; every exit, goal and key reachable from the start, collecting keys on the
way; no lock whose key cannot be reached; no softlock (every reachable state can still reach an
exit: one-way edges, consumed keys, pits); critical path (start to the nearest exit, key detours
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


def softlocked(dist, neighbours, is_exit):
    """Reachable states from which no exit state can be reached (a softlock: the player is stuck
    without dying - a pit too deep to jump out of, a key spent on the wrong door)."""
    back = {}
    for state in dist:
        for nxt, _ in neighbours(state):
            back.setdefault(nxt, []).append(state)
    good = deque(s for s in dist if is_exit(s))
    alive = set(good)
    while good:
        for p in back.get(good.popleft(), []):
            if p not in alive:
                alive.add(p)
                good.append(p)
    return [s for s in dist if s not in alive]


def check_return(dist, neighbours, is_goal, is_start, res):
    """Levels the player must leave again (hubs, fetch quests): from every reached goal or exit
    state the start must be reachable."""
    for g in [s for s in dist if is_goal(s)]:
        seen, todo = {g}, deque([g])
        found = is_start(g)
        while todo and not found:
            for nxt, _ in neighbours(todo.popleft()):
                if nxt not in seen:
                    seen.add(nxt)
                    if is_start(nxt):
                        found = True
                        break
                    todo.append(nxt)
        if not found:
            summary_problem(res, f"no way back to the start from {g[0]} (return: true)")
            return


# ---------------------------------------------------------------- platformer layouts

PLATFORMER_ROLES = {"#": "solid", ".": "air", " ": "air", "@": "start", ">": "exit", "$": "goal",
                    "H": "ladder", "^": "hazard", "-": "platform"}


def check_platformer(layout, args, res):
    """Side view, one tile per character, y down. The player stands on solid ground, a one-way
    platform (-) or a ladder (H); walks, climbs, falls straight down, and jumps up to `height`
    tiles and `width` tiles sideways (up, then across, then falls). Hazards (^) and falling off
    the map kill. The model is optimistic (it allows a little more than most controllers): a
    level it fails is unwinnable; one it passes still needs the autoplay run."""
    rows = [str(r) for r in layout.get("cells") or []]
    width = max((len(r) for r in rows), default=0)
    rows = [r.ljust(width) for r in rows]
    height = len(rows)
    jump = layout.get("jump") or {}
    jh, jw = int(jump.get("height", 3)), int(jump.get("width", 4))
    legend = {str(k): str(v) for k, v in (layout.get("legend") or {}).items()}
    role = {}
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            r = legend.get(ch) or PLATFORMER_ROLES.get(ch)
            if r is None and "a" <= ch <= "z":
                r = f"key:{ch}"
            elif r is None and "A" <= ch <= "Z":
                r = f"door:{ch.lower()}"
            role[(x, y)] = r or "solid"
    starts = [c for c, r in role.items() if r == "start"]
    exits = {c for c, r in role.items() if r == "exit"}
    goals = {c for c, r in role.items() if r == "goal"}
    keys = {c: r[4:] for c, r in role.items() if r.startswith("key:")}
    doors = {c: r[5:] for c, r in role.items() if r.startswith("door:")}
    bit = {k: 1 << i for i, k in enumerate(sorted(set(keys.values())))}
    if len(starts) != 1 or (not exits and not getattr(args, "coverage_only", False)):
        summary_problem(res, f"{len(starts)} start cells and {len(exits)} exits (one start, one or "
                             "more exits needed)")
        return

    def at(c):
        return role.get(c, "out")

    def passable(c, mask):
        r = at(c)
        if r in ("solid", "out"):
            return False
        if r.startswith("door:"):
            return bool(mask & bit.get(r[5:], 0))
        return True

    def support(c, mask):
        below = (c[0], c[1] + 1)
        return at(c) == "ladder" or at(below) in ("solid", "platform", "ladder") or \
            (at(below).startswith("door:") and not passable(below, mask))

    def fall_path(c, mask):
        """(where a player at c ends up standing or None, the cells passed on the way)."""
        path = []
        while True:
            path.append(c)
            if at(c) == "hazard" or at(c) == "out":
                return None, path
            if support(c, mask):
                return c, path
            c = (c[0], c[1] + 1)
            if c[1] >= height:
                return None, path
            if not passable(c, mask):
                return None, path

    def fall(c, mask):
        return fall_path(c, mask)[0]

    def pick(cells, mask):
        """Keys are picked up on every cell the move passes, mid-jump too (bug hunt 2026-10-20:
        only the landing cell counted, so a key hanging in the air was never collected)."""
        for c in cells:
            mask |= bit.get(keys.get(c), 0)
        return mask

    def neighbours(state):
        (x, y), mask = state
        out = set()
        for dx in (-1, 1):
            t = (x + dx, y)
            if passable(t, mask):
                land, path = fall_path(t, mask)
                if land:
                    out.add((land, pick(path, mask)))
        if at((x, y)) == "ladder" or at((x, y + 1)) == "ladder":
            for t in ((x, y - 1), (x, y + 1)):
                if passable(t, mask) and at(t) != "hazard":
                    land, path = (t, [t]) if at(t) == "ladder" else fall_path(t, mask)
                    if land:
                        out.add((land, pick(path, mask)))
        rise = []
        for h in range(1, jh + 1):
            col = (x, y - h)
            if not passable(col, mask) or at(col) == "hazard":
                break
            rise.append(col)
            for direction in (-1, 1):
                across = []
                for d in range(0, jw + 1):
                    t = (x + direction * d, y - h)
                    if not passable(t, mask) or at(t) == "hazard":
                        break
                    across.append(t)
                    land, path = fall_path(t, mask)
                    if land:
                        out.add((land, pick(rise + across + path, mask)))
        for land, got in out:
            if land != (x, y) or got != mask:
                yield (land, got), 1

    start = fall(starts[0], 0)
    if start is None:
        summary_problem(res, "the start has no ground under it")
        return
    init = (start, pick([start], 0))
    dist, prev, best, capped = search(init, neighbours, lambda s: s[0] in exits)

    def touched(target):
        """Standing states that reach `target` (exits, goals and keys may be off the ground)."""
        return any(s[0] == target or fall(target, s[1]) == s[0] for s in dist)

    for c in sorted(exits | goals):
        if not touched(c):
            summary_problem(res, f"{at(c)} at x={c[0]} y={c[1]} unreachable with a jump of "
                                 f"{jh} up / {jw} across")
    for c, k in sorted(keys.items()):
        if not touched(c):
            summary_problem(res, f"key '{k}' at x={c[0]} y={c[1]} unreachable")
    if best is not None and not capped:
        stuck = softlocked(dist, neighbours, lambda s: s[0] in exits)
        if stuck:
            c = min(stuck, key=lambda s: dist[s])[0]
            summary_problem(res, f"softlock: {len(stuck)} standing places from which the exit "
                                 f"cannot be reached, e.g. x={c[0]} y={c[1]} (a pit deeper than "
                                 f"the jump?)")
        if layout.get("return"):
            check_return(dist, neighbours, lambda s: s[0] in exits | goals,
                         lambda s: s[0] == start, res)
        res["critical_path"] = int(dist[best]) + 1
    res["standing_places"] = len({s[0] for s in dist})
    REACHED[id(res)] = {s[0] for s in dist}
    res["jump"] = {"height": jh, "width": jw}


# ---------------------------------------------------------------- push-box puzzles

def check_sokoban(layout, args, res):
    """Standard Sokoban text (# wall, @ player, $ box, . goal, * box on goal, + player on goal,
    space / - / _ floor). Solved by a breadth-first search over pushes with dead-square pruning
    (a box on a square from which no goal can be reached is never pushed there); --max-states
    bounds the search: past it the level is reported unknown, not unsolvable."""
    rows = [str(r).replace("-", " ").replace("_", " ") for r in layout.get("cells") or []]
    walls, goals, boxes, player = set(), set(), set(), None
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            c = (x, y)
            if ch == "#":
                walls.add(c)
            if ch in ".*+":
                goals.add(c)
            if ch in "$*":
                boxes.add(c)
            if ch in "@+":
                player = c
    if player is None or not boxes or len(boxes) != len(goals):
        summary_problem(res, f"{'no player, ' if player is None else ''}{len(boxes)} boxes and "
                             f"{len(goals)} goals (one player, as many goals as boxes)")
        return
    floor = set()
    todo = deque([player])
    while todo:
        c = todo.popleft()
        if c in floor or c in walls:
            continue
        floor.add(c)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            todo.append((c[0] + dx, c[1] + dy))
    dirs = ((1, 0), (-1, 0), (0, 1), (0, -1))
    live = set(goals)                       # squares from which a box can reach a goal (pulls)
    todo = deque(goals)
    while todo:
        c = todo.popleft()
        for dx, dy in dirs:
            b, p = (c[0] + dx, c[1] + dy), (c[0] + 2 * dx, c[1] + 2 * dy)
            if b in floor and p in floor and b not in live:
                live.add(b)
                todo.append(b)
    if any(b not in live for b in boxes):
        summary_problem(res, "a box starts on a dead square (it can never reach a goal)")
        return

    def reach(p, bx):
        seen, todo = {p}, [p]
        while todo:
            c = todo.pop()
            for dx, dy in dirs:
                n = (c[0] + dx, c[1] + dy)
                if n in floor and n not in bx and n not in seen:
                    seen.add(n)
                    todo.append(n)
        return seen

    limit = args.max_states
    start_area = reach(player, boxes)
    start = (min(start_area), frozenset(boxes))
    seen, todo, solved = {start: 0}, deque([(start, start_area)]), None
    if frozenset(boxes) == frozenset(goals):  # solved as laid out (bug hunt 2026-10-20: the
        solved = 0                            # check ran only after a push: "unsolvable")
    while todo and solved is None:
        (_, bx), area = todo.popleft()
        pushes = seen[(min(area), bx)]
        for b in bx:
            for dx, dy in dirs:
                stand, to = (b[0] - dx, b[1] - dy), (b[0] + dx, b[1] + dy)
                if stand not in area or to not in live or to in bx:
                    continue
                nb = frozenset(bx - {b} | {to})
                na = reach(b, nb)
                key = (min(na), nb)
                if key in seen:
                    continue
                seen[key] = pushes + 1
                if nb == frozenset(goals):
                    solved = pushes + 1
                    break
                if len(seen) >= limit:
                    break
                todo.append((key, na))
            if solved is not None or len(seen) >= limit:
                break
        if len(seen) >= limit:
            break
    res["states"] = len(seen)
    if solved is not None:
        res["solution_pushes"] = solved
        res["critical_path"] = solved
    elif len(seen) >= limit:
        res["warnings"].append(f"search stopped at {limit} states: solvability unknown "
                               "(raise --max-states or simplify)")
        res["unknown"] = True
    else:
        summary_problem(res, f"unsolvable: no push sequence puts every box on a goal "
                             f"({len(seen)} states searched)")


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
    if layout.get("return") and best is not None and not capped:
        check_return(dist, neighbours, lambda s: s[0] in exits | goals,
                     lambda s: s[0] == start, res)
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
    if not exits and not getattr(args, "coverage_only", False):
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
    consumed = layout.get("keys") == "consumed"
    if consumed:
        # a door uses up one key of its kind and then stays open: state = (cell, keys held per
        # kind, picked key cells, opened doors)
        key_cells = sorted(keys)
        door_cells = sorted(doors)
        kbit = {c: 1 << i for i, c in enumerate(key_cells)}
        dbit = {c: 1 << i for i, c in enumerate(door_cells)}

        def held(picked, opened, kind):
            have = sum(1 for c in key_cells if picked & kbit[c] and keys[c] == kind)
            spent = sum(1 for c in door_cells if opened & dbit[c] and doors[c] == kind)
            return have - spent

        def neighbours(state):  # noqa: F811 - the consumed-keys variant
            (x, y), picked, opened = state
            for dx, dy in steps:
                c = (x + dx, y + dy)
                if not open_cell(c):
                    continue
                if dx and dy and not (free((x + dx, y)) and free((x, y + dy))):
                    continue
                o = opened
                if c in doors and not opened & dbit[c]:
                    if held(picked, opened, doors[c]) <= 0:
                        continue
                    o = opened | dbit[c]
                yield (c, picked | kbit.get(c, 0), o), 1

        init = (start, kbit.get(start, 0), 0)
    else:
        init = (start, bit.get(keys.get(start), 0))
    dist, prev, best, capped = search(init, neighbours, lambda s: s[0] in exits)
    if capped:
        res["warnings"].append(f"state space capped at {MAX_STATES}; results partial")
    if best is not None and not capped:
        stuck = softlocked(dist, neighbours, lambda s: s[0] in exits)
        if stuck:
            c = min(stuck, key=lambda s: dist[s])[0]
            summary_problem(res, f"softlock: {len(stuck)} reachable states cannot reach an exit, "
                                 f"e.g. at x={c[0]} y={c[1]}" +
                                 (" (a key spent on the wrong door)" if consumed else ""))
        if layout.get("return"):
            check_return(dist, neighbours, lambda s: s[0] in exits | goals,
                         lambda s: s[0] == start, res)
    reached = {s[0] for s in dist}
    REACHED[id(res)] = reached
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

REACHED = {}  # id(result) -> the cells a grid or platformer search reached


def reachable_cells(layout, **options):
    """The cells a player can reach in a grid or platformer layout (standing places for a
    platformer), by the same search as the check; None for other layout types. Used by the
    playtest skill's explore_report.py for coverage."""
    defaults = dict(min_path=None, max_path=None, max_step=2.0, max_dead_end_ratio=1.0,
                    strict_dead_ends=False, max_unreachable=1.0, max_dead_end_tips=None,
                    max_states=300_000, coverage_only=True)
    defaults.update(options)
    args = argparse.Namespace(**defaults)
    res = {"problems": [], "warnings": []}
    kind = layout.get("type") or ("grid" if "cells" in layout else "graph")
    {"grid": check_grid, "platformer": check_platformer}.get(kind, lambda *x: None)(layout, args, res)
    return REACHED.pop(id(res), None)


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
    elif kind == "platformer":
        check_platformer(layout, args, res)
    elif kind == "sokoban":
        check_sokoban(layout, args, res)
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
    REACHED.pop(id(res), None)
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
    parser.add_argument("--max-states", type=int, default=300_000,
                        help="sokoban: states searched before the result is 'unknown'")
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
