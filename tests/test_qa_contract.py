"""Tests for the scene QA contract (qa_contract.gd + qa_contract.py), with a real headless Godot
4.6+ (skipped without one: set KILN_GODOT). A throwaway project: a HUD panel with a label, a
torch with its fire, and a figure whose joints move either as an animation or as one piece."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_probe_base import GODOT

HERE = os.path.dirname(__file__)
SCRIPTS = os.path.join(HERE, "..", "plugins", "kiln", "skills", "acceptance", "scripts")

PROJECT = """config_version=5

[application]
config/name="qa-fixture"
"""

MAIN_GD = """extends Node2D
var mode := "alive"
var fire_offset := Vector2.ZERO
var t := 0.0

func _process(delta: float) -> void:
	t += delta
	var ph := TAU * t
	if mode == "alive":
		$Hero/Hand.position = Vector2(30 + 12 * sin(ph), -60)
		$Hero/Foot.position = Vector2(8, -2 + 6 * max(0.0, sin(ph)))
		$Hero/Head.position = Vector2(0, -150 + 2 * sin(2 * ph))
	else:
		$Hero.rotation = 0.2 * sin(ph)
		$Hero.position = Vector2(300 + 40 * t, 400)
	$Torch/Fire.global_position = $Torch/Tip.global_position + fire_offset
"""

SCENE = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://main.gd" id="1"]

[node name="Main" type="Node2D"]
script = ExtResource("1")

[node name="HUD" type="Panel" parent="."]
offset_left = 100.0
offset_top = 60.0
offset_right = 300.0
offset_bottom = 100.0

[node name="Gold" type="Label" parent="HUD"]
offset_left = 8.0
offset_top = 8.0
text = "0"

[node name="Hero" type="Node2D" parent="."]
position = Vector2(300, 400)

[node name="Hips" type="Node2D" parent="Hero"]
position = Vector2(0, -90)

[node name="Hand" type="Node2D" parent="Hero"]
position = Vector2(30, -60)

[node name="Foot" type="Node2D" parent="Hero"]
position = Vector2(8, -2)

[node name="Head" type="Node2D" parent="Hero"]
position = Vector2(0, -150)

[node name="Torch" type="Node2D" parent="."]
position = Vector2(600, 300)

[node name="Tip" type="Node2D" parent="Torch"]
position = Vector2(0, -40)

[node name="Fire" type="Node2D" parent="Torch"]
"""

CONTRACT = """extends "res://tests/qa/qa_contract.gd"

func scene_path() -> String:
	return "res://main.tscn"

func states() -> Array:
	var joints := {"hips": "Hero/Hips", "hand": "Hero/Hand", "foot": "Hero/Foot", "head": "Hero/Head"}
	return [
		{"name": "hud_short", "kind": "ui", "apply": func(s): s.get_node("HUD/Gold").text = "12"},
		{"name": "hud_longest", "kind": "ui",
		 "apply": func(s): s.get_node("HUD/Gold").text = "Gold: 999 999 999 999 999 999 999"},
		{"name": "hud_unsafe", "kind": "ui",
		 "apply": func(s): s.get_node("HUD").position = Vector2(4, 4)},
		{"name": "apply_error", "kind": "ui",
		 "apply": func(s): s.get_node("NoSuchNode").text = "x"},
		{"name": "torch_fire", "kind": "anchor", "frames": 20, "tolerance": 2.0,
		 "track": {"emitter": "Torch/Fire", "holder": "Torch/Tip"}},
		{"name": "torch_fire_broken", "kind": "anchor", "frames": 20, "tolerance": 2.0,
		 "apply": func(s): s.fire_offset = Vector2(0, 25),
		 "track": {"emitter": "Torch/Fire", "holder": "Torch/Tip"}},
		{"name": "idle_loop", "kind": "loop", "frames": 60, "root": "hips", "dims": 2,
		 "height": 150, "track": joints},
		{"name": "idle_loop_sprite", "kind": "loop", "frames": 60, "root": "hips", "dims": 2,
		 "height": 150, "apply": func(s): s.mode = "rigid", "track": joints},
	]
"""


@unittest.skipUnless(GODOT, "no Godot console binary found (set KILN_GODOT)")
class QaContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proj = tempfile.mkdtemp(prefix="kiln-qa-")
        files = {"project.godot": PROJECT, "main.gd": MAIN_GD, "main.tscn": SCENE,
                 "tests/qa/main_qa.gd": CONTRACT}
        for rel, text in files.items():
            path = os.path.join(cls.proj, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        os.makedirs(os.path.join(cls.proj, "tests", "probes"), exist_ok=True)
        shutil.copy(os.path.join(SCRIPTS, "probe_base.gd"), os.path.join(cls.proj, "tests", "probes"))
        shutil.copy(os.path.join(SCRIPTS, "qa_contract.gd"), os.path.join(cls.proj, "tests", "qa"))
        subprocess.run([GODOT, "--headless", "--path", cls.proj, "--import"], capture_output=True,
                       timeout=300)
        p = subprocess.run([sys.executable, "-B", os.path.join(SCRIPTS, "qa_contract.py"), "run",
                            "--contract", "res://tests/qa/main_qa.gd", "--project", cls.proj,
                            "--godot", GODOT], capture_output=True, text=True, timeout=600)
        cls.code = p.returncode
        cls.res = json.loads(p.stdout)
        cls.states = {s["name"]: s for s in cls.res.get("states", [])}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.proj, ignore_errors=True)

    def test_one_command_one_report(self):
        self.assertEqual(self.code, 1, self.res)            # the broken states fail the run
        self.assertEqual(self.res["verdict"], "FAIL")
        self.assertTrue(os.path.isfile(os.path.join(self.res["run"], "report.json")))
        self.assertEqual(sorted(self.res["failed"]),
                         ["hud_longest", "hud_unsafe", "idle_loop_sprite", "torch_fire_broken"])

    def test_ui_overflow(self):
        self.assertEqual(self.states["hud_short"]["verdict"], "PASS", self.states["hud_short"])
        bad = self.states["hud_longest"]
        self.assertIn("outside its container", " ".join(bad["problems"]))

    def test_ui_check_layout_fails_a_state(self):
        # bug hunt 2026-10-20: ui_check answers "fail" in lower case; the compare never matched
        bad = self.states["hud_unsafe"]
        self.assertEqual(bad["ui_check"], "fail", bad)
        self.assertIn("outside_safe_area", " ".join(bad["problems"]))

    def test_a_state_whose_setup_errors_is_not_assessed(self):
        self.assertEqual(self.states["apply_error"]["verdict"], "NOT ASSESSED",
                         self.states["apply_error"])

    def test_emitter_anchor(self):
        self.assertEqual(self.states["torch_fire"]["verdict"], "PASS", self.states["torch_fire"])
        self.assertGreater(self.states["torch_fire_broken"]["max_distance"], 20)

    def test_loops_through_analyze_rigid(self):
        self.assertEqual(self.states["idle_loop"]["verdict"], "PASS", self.states["idle_loop"])
        self.assertIn("rigid", self.states["idle_loop_sprite"]["problem"])


if __name__ == "__main__":
    unittest.main()
