"""Runs controls-camera feel_windows.gd in a real headless Godot (skipped without one) against a
tiny platformer character whose coyote time and jump buffer come from feel_constants.gd: the
probe must measure the windows the constants promise, catch a controller that ignores coyote
time, and report input latency with its jitter."""

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

SKILLS = os.path.join(HERE, "..", "plugins", "kiln", "skills")

PLAYER = '''extends CharacterBody2D
var feel: Resource
var use_coyote := true
var coyote_left := 0.0
var buffer_left := 0.0

func _physics_process(delta: float) -> void:
	if is_on_floor():
		coyote_left = feel.coyote_time if use_coyote else 0.0
	else:
		coyote_left -= delta
	if Input.is_action_just_pressed(&"jump"):
		buffer_left = feel.jump_buffer
	else:
		buffer_left -= delta
	velocity.y += 900.0 * delta
	if buffer_left > 0.0 and (is_on_floor() or coyote_left > 0.0):
		velocity.y = -300.0
		buffer_left = 0.0
		coyote_left = 0.0
	velocity.x = Input.get_axis(&"move_left", &"move_right") * 100.0
	move_and_slide()
'''

PROBE = '''extends "res://probe_base.gd"
const Feel = preload("res://feel_windows.gd")
var hero: CharacterBody2D
var world: Node2D

func _box(parent: Node, pos: Vector2, size: Vector2) -> void:
	var body := StaticBody2D.new()  # kiln:runtime-node test fixture
	var shape := CollisionShape2D.new()  # kiln:runtime-node test fixture
	var rect := RectangleShape2D.new()
	rect.size = size
	shape.shape = rect
	body.add_child(shape)
	body.position = pos
	parent.add_child(body)

func _world(at: Vector2) -> void:
	for a in [&"move_left", &"move_right", &"jump"]:
		release(a)
	if world:
		world.queue_free()
		await ticks(1)
	world = Node2D.new()  # kiln:runtime-node test fixture
	root.add_child(world)
	_box(world, Vector2(100, 110), Vector2(200, 20))       # ledge: top y=100, right edge x=200
	_box(world, Vector2(300, 600), Vector2(1200, 20))      # far floor
	hero = CharacterBody2D.new()  # kiln:runtime-node test fixture
	hero.set_script(load("res://player.gd"))
	hero.feel = load("res://feel_constants.gd").new()
	hero.use_coyote = USE_COYOTE
	var hs := CollisionShape2D.new()  # kiln:runtime-node test fixture
	var hr := RectangleShape2D.new()
	hr.size = Vector2(10, 10)
	hs.shape = hr
	hero.add_child(hs)
	hero.position = at
	world.add_child(hero)
	await ticks(2)

func _ledge() -> void:
	await _world(Vector2(185, 95))
	press(&"move_right")

func _drop() -> void:
	await _world(Vector2(100, 30))

func _stand() -> void:
	await _world(Vector2(100, 95))

func _run() -> void:
	for a in [&"move_left", &"move_right", &"jump"]:
		InputMap.add_action(a)
	var fw = Feel.new(self)
	var feel: Resource = load("res://feel_constants.gd").new()
	var jumped := func(): return hero.velocity.y < -100.0
	var coyote: int = await fw.window_after(_ledge, func(): return not hero.is_on_floor(), &"jump", jumped)
	check("coyote", coyote, "~", fw.frames(feel.coyote_time), "feel_constants.gd", 1)
	var buffer: int = await fw.window_before(_drop, func(): return hero.is_on_floor(), &"jump", jumped)
	check("buffer", buffer, "~", fw.frames(feel.jump_buffer), "feel_constants.gd", 1)
	var lat: Dictionary = await fw.latency(_stand, &"move_right", func(): return hero.velocity.x > 0.0, 12)
	check("latency_max", lat["max"], "<=", feel.max_input_latency_frames, "feel_constants.gd")
	check("latency_jitter", lat["jitter"], "<=", feel.max_input_jitter_frames, "feel_constants.gd")
	note("coyote %d buffer %d latency %s" % [coyote, buffer, str(lat["samples"])])
	finish()
'''


@unittest.skipUnless(GODOT, "no Godot found (set KILN_GODOT)")
class FeelWindows(unittest.TestCase):
    def run_probe(self, use_coyote):
        d = tempfile.mkdtemp(prefix="kiln-feel-")
        with open(os.path.join(d, "project.godot"), "w", encoding="utf-8") as fh:
            fh.write('config_version=5\n\n[application]\nconfig/name="feel"\n')
        shutil.copy(os.path.join(SKILLS, "acceptance", "scripts", "probe_base.gd"), d)
        for name in ("feel_windows.gd", "feel_constants.gd"):
            shutil.copy(os.path.join(SKILLS, "controls-camera", "scripts", name), d)
        with open(os.path.join(d, "player.gd"), "w", encoding="utf-8") as fh:
            fh.write(PLAYER)
        with open(os.path.join(d, "probe_feel.gd"), "w", encoding="utf-8") as fh:
            fh.write(PROBE.replace("USE_COYOTE", "true" if use_coyote else "false"))
        out = os.path.join(d, "out")
        env = dict(os.environ, KILN_PROBE_DIR=out)
        p = subprocess.run([GODOT, "--headless", "--fixed-fps", "60", "--path", d, "-s",
                            "res://probe_feel.gd"], capture_output=True, text=True, timeout=300,
                           env=env)
        files = glob.glob(os.path.join(out, "*.json"))
        self.assertTrue(files, p.stdout[-2000:] + p.stderr[-2000:])
        with open(files[0], encoding="utf-8") as fh:
            return json.load(fh)

    def test_windows_match_the_constants_and_latency_is_steady(self):
        res = self.run_probe(True)
        rows = {r["id"]: r for r in res["rows"]}
        self.assertEqual(res["verdict"], "PASS", res)
        self.assertEqual(rows["latency_jitter"]["value"], 0, res)

    def test_a_controller_without_coyote_time_fails(self):
        res = self.run_probe(False)
        rows = {r["id"]: r for r in res["rows"]}
        self.assertEqual(rows["coyote"]["verdict"], "FAIL", res)
        self.assertEqual(rows["buffer"]["verdict"], "PASS", res)


COUNTER_PLAYER = '''extends CharacterBody2D
var C := 0
var B := 0
var air := 0
var buf := -1

func _physics_process(delta: float) -> void:
	if is_on_floor():
		air = 0
	else:
		air += 1
	if Input.is_action_just_pressed(&"jump"):
		buf = 0
	elif buf >= 0:
		buf += 1
	velocity.y += 900.0 * delta
	var pressed_ok := buf == 0 or (buf > 0 and buf <= B)
	var ground_ok := is_on_floor() or (air >= 1 and air <= C)
	if pressed_ok and ground_ok:
		velocity.y = -300.0
		buf = -1
		air = 999
	velocity.x = Input.get_axis(&"move_left", &"move_right") * 100.0
	move_and_slide()
'''


@unittest.skipUnless(GODOT, "no Godot found (set KILN_GODOT)")
class ExactWindows(unittest.TestCase):
    """Bug hunt 2026-10-20: a press made inside a tick reaches is_action_just_pressed one tick
    late, so coyote read C-1 and buffer B+2 and the +-1 tolerance hid it. A controller that
    counts frames must read exactly its C and B."""

    def test_frame_counter_controllers_read_exactly(self):
        for c, b in ((0, 0), (3, 3), (6, 5)):
            probe = PROBE.replace('hero.set_script(load("res://player.gd"))',
                                  f'hero.set_script(load("res://player.gd"))\n\thero.C = {c}\n'
                                  f'\thero.B = {b}')
            probe = probe.replace("\thero.feel = load(\"res://feel_constants.gd\").new()\n", "")
            probe = probe.replace("\thero.use_coyote = USE_COYOTE\n", "")
            probe = probe.replace(
                'check("coyote", coyote, "~", fw.frames(feel.coyote_time), "feel_constants.gd", 1)',
                f'check("coyote", coyote, "==", {c}, "C")')
            probe = probe.replace(
                'check("buffer", buffer, "~", fw.frames(feel.jump_buffer), "feel_constants.gd", 1)',
                f'check("buffer", buffer, "==", {b}, "B")')
            d = tempfile.mkdtemp(prefix="kiln-feelx-")
            with open(os.path.join(d, "project.godot"), "w", encoding="utf-8") as fh:
                fh.write('config_version=5\n\n[application]\nconfig/name="feel"\n')
            shutil.copy(os.path.join(SKILLS, "acceptance", "scripts", "probe_base.gd"), d)
            for name in ("feel_windows.gd", "feel_constants.gd"):
                shutil.copy(os.path.join(SKILLS, "controls-camera", "scripts", name), d)
            with open(os.path.join(d, "player.gd"), "w", encoding="utf-8") as fh:
                fh.write(COUNTER_PLAYER)
            with open(os.path.join(d, "probe_feel.gd"), "w", encoding="utf-8") as fh:
                fh.write(probe)
            out = os.path.join(d, "out")
            p = subprocess.run([GODOT, "--headless", "--fixed-fps", "60", "--path", d, "-s",
                                "res://probe_feel.gd"], capture_output=True, text=True,
                               timeout=300, env=dict(os.environ, KILN_PROBE_DIR=out))
            files = glob.glob(os.path.join(out, "*.json"))
            self.assertTrue(files, p.stdout[-2000:] + p.stderr[-2000:])
            with open(files[0], encoding="utf-8") as fh:
                res = json.load(fh)
            rows = {r["id"]: r for r in res["rows"]}
            self.assertEqual((rows["coyote"]["value"], rows["buffer"]["value"]), (c, b), res)


if __name__ == "__main__":
    unittest.main()
