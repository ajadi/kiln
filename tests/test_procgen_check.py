"""Tests for plugins/kiln/skills/procgen/scripts/procgen_check.py (stdlib only)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "procgen",
                      "scripts", "procgen_check.py")


def layouts(**named):
    root = tempfile.mkdtemp(prefix="kiln-procgen-")
    for name, data in named.items():
        with open(os.path.join(root, name + ".json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    return root


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=60, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


def graph(rooms, edges, seed=1):
    return {"seed": seed, "type": "graph", "rooms": rooms, "edges": edges}


KEY_DUNGEON = graph(
    [{"id": "s", "tags": ["start"], "difficulty": 1}, {"id": "hall", "difficulty": 2},
     {"id": "vault", "key": "red", "difficulty": 2}, {"id": "boss", "tags": ["exit"],
                                                      "difficulty": 4},
     {"id": "chest", "tags": ["reward"]}],
    [{"a": "s", "b": "hall"}, {"a": "hall", "b": "vault"},
     {"a": "hall", "b": "boss", "lock": "red"}, {"a": "s", "b": "chest"}])


def one(root, *extra):
    code, rep = run(os.path.join(root, "*.json"), *extra)
    return code, rep, rep["results"][0]


class GraphLayouts(unittest.TestCase):
    def test_key_detour_counts_in_critical_path(self):
        code, rep, res = one(layouts(a=KEY_DUNGEON))
        self.assertEqual(code, 0, rep["failing"])
        self.assertEqual(res["critical_path_rooms"], ["s", "hall", "vault", "hall", "boss"])
        self.assertEqual(res["critical_path"], 5)
        self.assertEqual(res["dead_ends"], 2)  # vault (key) and chest (reward) both pay off
        self.assertEqual(res["empty_dead_ends"], [])
        self.assertEqual(res["loops"], 0)

    def test_key_behind_its_own_lock(self):
        bad = graph(KEY_DUNGEON["rooms"],
                    [{"a": "s", "b": "hall"}, {"a": "hall", "b": "vault", "lock": "red"},
                     {"a": "hall", "b": "boss", "lock": "red"}, {"a": "s", "b": "chest"}])
        code, rep, res = one(layouts(a=bad))
        self.assertEqual(code, 1)
        text = " ".join(res["problems"])
        self.assertIn("exit boss unreachable", text)
        self.assertIn("key 'red' in room vault unreachable", text)

    def test_one_way_drop_into_a_pit_is_a_softlock(self):
        pit = graph([{"id": "s", "tags": ["start"]}, {"id": "pit", "tags": ["reward"]},
                     {"id": "e", "tags": ["exit"]}],
                    [{"a": "s", "b": "e"}, {"a": "s", "b": "pit", "oneway": True}])
        code, _, res = one(layouts(a=pit))
        self.assertEqual(code, 1)
        self.assertIn("softlock", " ".join(res["problems"]))
        ok = graph(pit["rooms"], pit["edges"] + [{"a": "pit", "b": "e", "oneway": True}])
        code, _, res = one(layouts(a=ok))
        self.assertEqual(code, 0, res["problems"])

    def test_lock_without_key_orphans_and_missing_start(self):
        bad = graph([{"id": "s", "tags": ["start"]}, {"id": "e", "tags": ["exit"]},
                     {"id": "island"}], [{"a": "s", "b": "e", "lock": "blue"}])
        _, _, res = one(layouts(a=bad))
        text = " ".join(res["problems"])
        self.assertIn("locked by 'blue' but no room holds that key", text)
        self.assertIn("unreachable rooms: e, island", text)
        _, _, res = one(layouts(a=graph([{"id": "x"}], [])))
        self.assertIn("0 start rooms", " ".join(res["problems"]))

    def test_path_bounds_dead_ends_and_difficulty(self):
        spiky = graph([{"id": "s", "tags": ["start"], "difficulty": 1},
                       {"id": "a", "difficulty": 5}, {"id": "b", "difficulty": 2},
                       {"id": "c", "difficulty": 1}, {"id": "e", "tags": ["exit"],
                                                      "difficulty": 0},
                       {"id": "x"}, {"id": "y"}],
                      [{"a": "s", "b": "a"}, {"a": "a", "b": "b"}, {"a": "b", "b": "c"},
                       {"a": "c", "b": "e"}, {"a": "a", "b": "x"}, {"a": "b", "b": "y"}])
        code, _, res = one(layouts(a=spiky), "--max-path", "4", "--strict-dead-ends")
        self.assertEqual(code, 1)
        text = " ".join(res["problems"])
        self.assertIn("critical path 5 > 4", text)
        self.assertIn("difficulty jumps +4", text)
        self.assertIn("difficulty falls", text)
        self.assertIn("2 dead ends with no reward", text)
        _, _, res = one(layouts(a=spiky), "--max-dead-end-ratio", "0.2")
        self.assertIn("dead-end ratio 0.286 > 0.2", " ".join(res["problems"]))

    def test_loops_counted(self):
        ring = graph([{"id": "s", "tags": ["start"]}, {"id": "a"}, {"id": "b"},
                      {"id": "e", "tags": ["exit"]}],
                     [{"a": "s", "b": "a"}, {"a": "a", "b": "e"}, {"a": "s", "b": "b"},
                      {"a": "b", "b": "e"}])
        code, _, res = one(layouts(a=ring))
        self.assertEqual(code, 0)
        self.assertEqual(res["loops"], 1)
        self.assertEqual(res["dead_ends"], 0)


class GridLayouts(unittest.TestCase):
    def test_door_and_key(self):
        grid = {"seed": 9, "type": "grid", "cells": ["#########",
                                                     "#@..a#..#",
                                                     "#....A.>#",
                                                     "#########"]}
        code, _, res = one(layouts(a=grid))
        self.assertEqual(code, 0, res["problems"])
        self.assertEqual(res["critical_path"], 8)
        self.assertEqual(res["unreachable_floor_ratio"], 0.0)

    def test_missing_key_pockets_and_unknown_chars(self):
        grid = {"seed": 4, "type": "grid", "cells": ["##########",
                                                     "#@..#..B>#",
                                                     "#...#.?..#",
                                                     "##########"]}
        code, _, res = one(layouts(a=grid))
        self.assertEqual(code, 1)
        text = " ".join(res["problems"])
        self.assertIn("door 'b' has no key", text)
        self.assertIn("exit at x=8 y=1 unreachable", text)
        self.assertIn("floor cells unreachable", text)
        self.assertIn("'?'", text)

    def test_custom_legend_and_diagonal_corner_rule(self):
        grid = {"seed": 5, "type": "grid", "legend": {"~": "floor", "E": "exit"},
                "diagonal": True, "cells": ["#####",
                                            "#@#~#",
                                            "##~E#",
                                            "#####"]}
        code, _, res = one(layouts(a=grid))
        self.assertEqual(code, 1)  # @ to the diagonal ~ would cut two wall corners
        self.assertIn("exit", " ".join(res["problems"]))
        grid["cells"][1] = "#@~~#"
        code, _, res = one(layouts(a=grid))
        self.assertEqual(code, 0, res["problems"])


class Aggregate(unittest.TestCase):
    def test_many_seeds_and_failing_list(self):
        bad = graph([{"id": "s", "tags": ["start"]}, {"id": "e", "tags": ["exit"]}], [], seed=77)
        root = layouts(a=KEY_DUNGEON, b=dict(KEY_DUNGEON, seed=2), c=bad)
        code, rep = run(os.path.join(root, "*.json"))
        self.assertEqual(code, 1)
        self.assertEqual(rep["layouts"], 3)
        self.assertEqual(rep["passed"], 2)
        self.assertEqual([f["seed"] for f in rep["failing"]], [77])
        code, rep = run(os.path.join(root, "*.json"), "--min-pass-rate", "0.6")
        self.assertEqual(code, 0)
        self.assertEqual(rep["critical_path"]["max"], 5)

    def test_no_files_fails(self):
        code, rep = run(os.path.join(tempfile.mkdtemp(), "*.json"))
        self.assertEqual(code, 1)
        self.assertIn("no layout files", rep["problems"][0])

    def test_unreadable_layouts_fail_instead_of_crashing(self):
        root = tempfile.mkdtemp()
        for name, text in (("bad.json", "not json"), ("list.json", "[1, 2]")):
            with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        code, rep = run(os.path.join(root, "*.json"))
        self.assertEqual(code, 1)
        self.assertEqual(rep["passed"], 0)


if __name__ == "__main__":
    unittest.main()
