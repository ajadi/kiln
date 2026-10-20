"""Runs playtest explorer.gd and input_replay.gd in a real headless Godot (skipped without one):
the explorer covers a small top-down maze and the report shows coverage of its reachable cells;
the same recorded input played twice gives the same state hashes, and a changed controller
diverges at a named frame. Also explore_report.py on synthetic runs."""

import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from test_probe_base import GODOT  # noqa: E402

PLAYTEST = os.path.join(HERE, "..", "plugins", "kiln", "skills", "playtest", "scripts")
REPORT = os.path.join(PLAYTEST, "explore_report.py")
MAZE = ["#########",
        "#...#...#",
        "#.#.#.#.#",
        "#.#...#.#",
        "#.#####.#",
        "#.......#",
        "#########"]

WORLD = '''
var hero: CharacterBody2D
const MAZE = %s
const CELL = 32.0

func _build(speed: float) -> void:
	for a in [&"move_left", &"move_right", &"move_up", &"move_down"]:
		if not InputMap.has_action(a):
			InputMap.add_action(a)
	var world := Node2D.new()  # kiln:runtime-node test fixture
	root.add_child(world)
	for y in MAZE.size():
		for x in MAZE[y].length():
			if MAZE[y][x] == "#":
				var wall := StaticBody2D.new()  # kiln:runtime-node test fixture
				var cs := CollisionShape2D.new()  # kiln:runtime-node test fixture
				var r := RectangleShape2D.new()
				r.size = Vector2(CELL, CELL)
				cs.shape = r
				wall.add_child(cs)
				wall.position = Vector2(x + 0.5, y + 0.5) * CELL
				world.add_child(wall)
	hero = CharacterBody2D.new()  # kiln:runtime-node test fixture
	hero.motion_mode = CharacterBody2D.MOTION_MODE_FLOATING
	var hs := CollisionShape2D.new()  # kiln:runtime-node test fixture
	var c := CircleShape2D.new()
	c.radius = 9.0
	hs.shape = c
	hero.add_child(hs)
	hero.position = Vector2(1.5, 1.5) * CELL
	hero.set_meta("speed", speed)
	world.add_child(hero)
	var mover := Node.new()  # kiln:runtime-node test fixture
	mover.set_script(load("res://mover.gd"))
	mover.hero = hero
	world.add_child(mover)
''' % json.dumps(MAZE)

MOVER = '''extends Node
var hero: CharacterBody2D
func _physics_process(_d: float) -> void:
	hero.velocity = Input.get_vector(&"move_left", &"move_right", &"move_up", &"move_down") * float(hero.get_meta("speed"))
	hero.move_and_slide()
'''

EXPLORE = '''extends "res://autoplay_base.gd"
''' + WORLD + '''
func _setup() -> void:
	_build(140.0)

func _play() -> void:
	var ex = load("res://explorer.gd").new(self, func(): return hero.global_position,
		{Vector2.LEFT: &"move_left", Vector2.RIGHT: &"move_right", Vector2.UP: &"move_up", Vector2.DOWN: &"move_down"}, CELL)
	await ex.explore(120.0)
	ex.save(out_dir.path_join("explore.json"))
'''

REPLAY = '''extends SceneTree
''' + WORLD + '''
func _initialize() -> void:
	Input.use_accumulated_input = false
	var speed := float(OS.get_environment("KILN_SPEED"))
	_build(speed)
	_go.call_deferred()

func _go() -> void:
	var rp = load("res://input_replay.gd").new()  # kiln:runtime-node test tool
	rp.actions = PackedStringArray(["move_left", "move_right", "move_up", "move_down"])
	rp.track = [func(): return hero.global_position]
	root.add_child(rp)
	var mode := OS.get_environment("KILN_MODE")
	var path := OS.get_environment("KILN_REPLAY")
	if mode == "record":
		rp.record()
		for step in [[&"move_down", 70], [&"move_right", 40], [&"move_up", 30], [&"move_right", 25]]:
			Input.action_press(step[0])
			for i in step[1]:
				await physics_frame
			Input.action_release(step[0])
		rp.stop()
		rp.save(path)
	else:
		rp.load_file(path)
		rp.play()
		await rp.finished
	print("KILN:" + JSON.stringify({"divergence": rp.first_divergence(), "hashes": rp.hashes.size(),
		"pos": [hero.global_position.x, hero.global_position.y]}))
	quit()
'''


def project(d):
    with open(os.path.join(d, "project.godot"), "w", encoding="utf-8") as fh:
        fh.write('config_version=5\n\n[application]\nconfig/name="explore"\n')
    for name in ("autoplay_base.gd", "explorer.gd", "input_replay.gd"):
        shutil.copy(os.path.join(PLAYTEST, name), d)
    for name, text in (("mover.gd", MOVER), ("explore.gd", EXPLORE), ("replay.gd", REPLAY)):
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(text)


class ExploreReport(unittest.TestCase):
    def test_report_merges_runs_and_gates_coverage(self):
        d = tempfile.mkdtemp(prefix="kiln-exr-")
        for i, cells in enumerate(([[1, 1], [1, 2], [2, 1]], [[1, 1], [3, 1], [3, 2]])):
            run = os.path.join(d, f"run_{i}")
            os.makedirs(run)
            with open(os.path.join(run, "explore.json"), "w", encoding="utf-8") as fh:
                json.dump({"cell": 32, "visits": {f"{x},{y}": 5 for x, y in cells},
                           "stuck": {"1,1": 3}}, fh)
        maze = os.path.join(d, "maze.json")
        with open(maze, "w", encoding="utf-8") as fh:
            json.dump({"type": "grid", "cells": MAZE}, fh)
        p = subprocess.run([sys.executable, "-B", REPORT, os.path.join(d, "run_*", "explore.json"),
                            "--out", d, "--reachable", maze, "--max-stuck-share", "0.5"],
                           capture_output=True, text=True, timeout=60)
        out = json.loads(p.stdout)
        self.assertEqual(out["cells_visited"], 5)
        self.assertLess(out["coverage"], 0.5)
        self.assertEqual(p.returncode, 1)                      # coverage gate
        self.assertTrue(os.path.isfile(out["heatmap"]))


@unittest.skipUnless(GODOT, "no Godot found (set KILN_GODOT)")
class GodotExplorer(unittest.TestCase):
    def test_explorer_covers_the_maze(self):
        d = tempfile.mkdtemp(prefix="kiln-explore-")
        project(d)
        out = os.path.join(d, "run").replace("\\", "/")
        p = subprocess.run([GODOT, "--headless", "--fixed-fps", "60", "--path", d, "-s",
                            "res://explore.gd", "--", "--seed", "3", "--out", out,
                            "--shots-every", "0", "--stuck-s", "600"],
                           capture_output=True, text=True, timeout=600)
        path = os.path.join(out, "explore.json")
        self.assertTrue(os.path.isfile(path), p.stdout[-2000:] + p.stderr[-2000:])
        maze = os.path.join(d, "maze.json")
        with open(maze, "w", encoding="utf-8") as fh:
            json.dump({"type": "grid", "cells": MAZE}, fh)
        r = subprocess.run([sys.executable, "-B", REPORT, path, "--out", out, "--reachable", maze,
                            "--min-coverage", "0.9"], capture_output=True, text=True, timeout=60)
        rep = json.loads(r.stdout)
        self.assertGreaterEqual(rep["coverage"], 0.9, rep)

    def test_replay_repeats_and_names_the_divergence(self):
        d = tempfile.mkdtemp(prefix="kiln-replay-")
        project(d)
        rec = os.path.join(d, "rec.json").replace("\\", "/")

        def go(mode, speed):
            env = dict(os.environ, KILN_MODE=mode, KILN_SPEED=str(speed), KILN_REPLAY=rec)
            p = subprocess.run([GODOT, "--headless", "--fixed-fps", "60", "--path", d, "-s",
                                "res://replay.gd"], capture_output=True, text=True, timeout=300,
                               env=env)
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("KILN:")), None)
            self.assertIsNotNone(line, p.stdout[-1500:] + p.stderr[-1500:])
            return json.loads(line[5:])

        recorded = go("record", 140)
        first = go("play", 140)
        second = go("play", 140)
        self.assertEqual(first["divergence"], -1, first)
        self.assertEqual(second["divergence"], -1, second)
        self.assertEqual(first["pos"], recorded["pos"])
        changed = go("play", 120)                               # a slower controller
        self.assertGreaterEqual(changed["divergence"], 0, changed)


JUMP_GAME = '''extends Node
var y := 0.0
var vy := 0.0
var jumped_at := -1
var x := 0.0
func _physics_process(delta: float) -> void:
	if Input.is_action_just_pressed(&"jump"):
		vy = 5.0
		if jumped_at < 0:
			jumped_at = Engine.get_physics_frames()
	x += Input.get_action_strength(&"right") * delta
	y += vy * delta
	vy -= 9.8 * delta
	if y < 0.0:
		y = 0.0
		vy = 0.0
'''

JUMP_MAIN = '''extends SceneTree
var game
var rp
func _initialize() -> void:
	Input.use_accumulated_input = false
	InputMap.add_action(&"jump")
	InputMap.add_action(&"right")
	_go.call_deferred()

func _fresh() -> void:
	if game:
		game.free()
	game = load("res://jump_game.gd").new()  # kiln:runtime-node test fixture
	root.add_child(game)

func _go() -> void:
	_fresh()
	rp = load("res://input_replay.gd").new()  # kiln:runtime-node test tool
	rp.actions = PackedStringArray(["jump", "right"])
	rp.hash_every = 1
	rp.track = [func(): return game.y, func(): return game.x]
	root.add_child(rp)
	await process_frame
	rp.record()
	var f0 := Engine.get_physics_frames()
	await create_timer(0.5).timeout            # a scripted session, like autoplay hold()
	Input.action_press(&"jump")
	Input.action_press(&"right", 0.3)
	await create_timer(0.2).timeout
	Input.action_release(&"jump")
	Input.action_press(&"right", 1.0)          # the stick pushed further while held
	await create_timer(0.3).timeout
	Input.action_release(&"right")
	await create_timer(0.3).timeout
	rp.stop()
	var rec_jump: int = game.jumped_at - f0
	var rec_x: float = game.x
	rp.save("res://rec_jump.json")
	_fresh()
	await process_frame
	rp.load_file("res://rec_jump.json")
	var f1 := Engine.get_physics_frames()
	rp.play()
	await rp.finished
	print("KILN:" + JSON.stringify({"rec_jump": rec_jump, "play_jump": game.jumped_at - f1,
		"rec_x": rec_x, "play_x": game.x, "divergence": rp.first_divergence()}))
	quit()
'''


@unittest.skipUnless(GODOT, "no Godot found (set KILN_GODOT)")
class ReplayTiming(unittest.TestCase):
    def test_a_timer_driven_session_replays_on_the_same_frames(self):
        # bug hunt 2026-10-20: a press made inside a tick reached is_action_just_pressed one tick
        # late, so a replay diverged from its own recording; analog strength changes while held
        # were not recorded
        d = tempfile.mkdtemp(prefix="kiln-replayj-")
        project(d)
        for name, text in (("jump_game.gd", JUMP_GAME), ("jump_main.gd", JUMP_MAIN)):
            with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        p = subprocess.run([GODOT, "--headless", "--fixed-fps", "60", "--path", d, "-s",
                            "res://jump_main.gd"], capture_output=True, text=True, timeout=300)
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("KILN:")), None)
        self.assertIsNotNone(line, p.stdout[-1500:] + p.stderr[-1500:])
        out = json.loads(line[5:])
        self.assertEqual(out["play_jump"], out["rec_jump"], out)
        self.assertAlmostEqual(out["play_x"], out["rec_x"], places=4, msg=out)
        self.assertEqual(out["divergence"], -1, out)


if __name__ == "__main__":
    unittest.main()


class ExploreCoverage(unittest.TestCase):
    def test_void_and_legend_walls_are_not_reachable_cells(self):
        # bug hunt 2026-10-20: every cell but # and ^ counted, so void around a room cut coverage
        d = tempfile.mkdtemp(prefix="kiln-exc-")
        run = os.path.join(d, "run_0")
        os.makedirs(run)
        with open(os.path.join(run, "explore.json"), "w", encoding="utf-8") as fh:
            json.dump({"cell": 32, "visits": {"4,1": 9, "5,1": 4, "6,1": 2}, "stuck": {}}, fh)
        layout = os.path.join(d, "room.json")
        with open(layout, "w", encoding="utf-8") as fh:
            json.dump({"type": "grid", "legend": {"X": "wall"},
                       "cells": ["   #####   ", "   #@.>#XX ", "   #####   "]}, fh)
        p = subprocess.run([sys.executable, "-B", REPORT, os.path.join(run, "explore.json"),
                            "--out", d, "--reachable", layout, "--min-coverage", "0.99"],
                           capture_output=True, text=True, timeout=60)
        out = json.loads(p.stdout)
        self.assertEqual((p.returncode, out["coverage"]), (0, 1.0), out)
