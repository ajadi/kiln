"""Tests for engine-godot godot_lint.py (Godot 3 API in GDScript, broken text scenes) and the
guard rule built on it. Research 2026-10-19: agents write Godot 3 APIs and mangle .tscn files;
a scene linter stopped the mangling. A scene the linter fails must also fail to load in a real
Godot (checked when one is found)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
SCRIPTS = os.path.join(HERE, "..", "plugins", "kiln", "skills", "engine-godot", "scripts")
sys.path.insert(0, SCRIPTS)
import godot_lint  # noqa: E402
from test_guard import make_project, mcp, run_guard, write  # noqa: E402
from test_probe_base import GODOT  # noqa: E402

LINT = os.path.join(SCRIPTS, "godot_lint.py")

GOOD_GD = '''extends CharacterBody3D
## Moves with @export speed; Transform3D, await and typed signals are Godot 4.
signal landed(height: float)
@export var speed: float = 5.0
@onready var anim: AnimationPlayer = $AnimationPlayer
var log_text := "yield( is a Godot 3 word"   # strings and comments are not code: yield(x)

func _physics_process(delta: float) -> void:
	velocity.x = speed
	move_and_slide()
	if is_on_floor():
		landed.emit(global_position.y)
	var t := Transform3D.IDENTITY
	await get_tree().process_frame
'''

BAD_GD = '''extends KinematicBody
export var speed = 5.0
onready var anim = $AnimationPlayer
func _ready():
	yield(get_tree(), "idle_frame")
	var s = preload("res://a.tscn").instance()
	connect("body_entered", self, "_on_enter")
	velocity = move_and_slide(velocity, Vector3.UP)
	var p = PoolStringArray()
	if p.empty(): print(deg2rad(90))
'''

SCENE = '''[gd_scene format=3 uid="uid://b4g5qwlvw3qr4"]

[ext_resource type="Script" uid="uid://x1" path="res://player.gd" id="1_a"]

[sub_resource type="CapsuleShape3D" id="Shape_1"]

[node name="Player" type="CharacterBody3D" unique_id=5 node_paths=PackedStringArray("collision_shape", "camera_rig")]
script = ExtResource("1_a")

[node name="Shape" type="CollisionShape3D" parent="."]
shape = SubResource("Shape_1")

[node name="CameraRig" type="Node3D" parent="."]

[node name="Pivot" type="Node3D" parent="CameraRig"]

[connection signal="ready" from="CameraRig/Pivot" to="." method="_on_ready"]
'''


class GodotLint(unittest.TestCase):
    def test_good_godot4_script_is_clean(self):
        self.assertEqual(godot_lint.lint_gdscript(GOOD_GD), [])

    def test_godot3_forms_are_named_with_their_godot4_form(self):
        found = {h["found"].split("(")[0].strip(". ") for h in godot_lint.lint_gdscript(BAD_GD)
                 if h["severity"] == "error"}
        for word in ("extends KinematicBody", "export var", "onready var", "yield", "instance",
                     "move_and_slide", "PoolStringArray", "empty", "deg2rad"):
            self.assertTrue(any(word in f for f in found), (word, found))
        self.assertTrue(any("connect" in h["found"] for h in godot_lint.lint_gdscript(BAD_GD)))

    def test_emit_signal_is_style_and_a_marker_allows(self):
        hits = godot_lint.lint_gdscript('emit_signal("hit", 3)\nvar q = Quat() # kiln:godot3-ok\n')
        self.assertEqual([h["severity"] for h in hits], ["style"])

    def test_scene_with_node_paths_header_is_clean(self):
        d = tempfile.mkdtemp(prefix="kiln-gl-")
        open(os.path.join(d, "player.gd"), "w").close()
        problems, uid = godot_lint.lint_scene(SCENE, "p.tscn", d)
        self.assertEqual([p for p in problems if p["severity"] == "error"], [], problems)
        self.assertEqual(uid, "uid://b4g5qwlvw3qr4")

    def test_broken_scenes(self):
        cases = {
            "parent": SCENE.replace('parent="CameraRig"]', 'parent="Rig"]'),
            "siblings": SCENE.replace('[node name="CameraRig"', '[node name="Shape"'),
            "extresource": SCENE.replace('script = ExtResource("1_a")', 'script = ExtResource("9_z")'),
            "format": SCENE.replace("format=3", "format=2"),
            "connection": SCENE.replace('from="CameraRig/Pivot"', 'from="Nope"'),
            "order": SCENE + '\n[sub_resource type="BoxShape3D" id="Late"]\n',
        }
        for name, text in cases.items():
            problems, _ = godot_lint.lint_scene(text, "p.tscn", None)
            self.assertTrue(any(p["severity"] == "error" for p in problems), (name, problems))

    def test_cli_reports_duplicate_uids(self):
        d = tempfile.mkdtemp(prefix="kiln-gl-")
        for name in ("a.tscn", "b.tscn"):
            with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                fh.write('[gd_scene format=3 uid="uid://same"]\n\n[node name="R" type="Node"]\n')
        p = subprocess.run([sys.executable, "-B", LINT, "--root", d], capture_output=True, text=True)
        out = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1)
        self.assertIn("uid://same", json.dumps(out["report"]))

    def test_guard_refuses_godot3_scripts(self):
        root = make_project("godot")
        call = mcp("mcp__godot-ai__script_create", "gameplay-dev", path="res://scripts/p.gd",
                   content=BAD_GD)
        got, reason = run_guard(root, call)
        self.assertEqual(got, "DENY", reason)
        self.assertIn("Godot 3 API", reason)
        self.assertIn("instantiate()", reason)
        ok = mcp("mcp__godot-ai__script_create", "gameplay-dev", path="res://scripts/p.gd",
                 content=GOOD_GD)
        self.assertEqual(run_guard(root, ok)[0], "ALLOW")
        patch = mcp("mcp__godot-ai__script_patch", "gameplay-dev", path="res://scripts/p.gd",
                    old_text="x", new_text="\tyield(get_tree(), \"idle_frame\")\n")
        self.assertEqual(run_guard(root, patch)[0], "DENY")
        probe = write(os.path.join(root, "tests", "probes", "p.gd"), "verifier",
                      content="extends SceneTree\nfunc _init():\n\tyield(self, 'x')\n")
        self.assertEqual(run_guard(root, probe)[0], "DENY")

    @unittest.skipUnless(GODOT, "no Godot found (set KILN_GODOT)")
    def test_godot_also_rejects_what_the_linter_fails(self):
        d = tempfile.mkdtemp(prefix="kiln-glg-")
        with open(os.path.join(d, "project.godot"), "w", encoding="utf-8") as fh:
            fh.write('config_version=5\n\n[application]\nconfig/name="lint"\n')
        broken = SCENE.replace('parent="CameraRig"]', 'parent="Rig"]').replace(
            'script = ExtResource("1_a")\n', "").replace(
            '[ext_resource type="Script" uid="uid://x1" path="res://player.gd" id="1_a"]\n', "")
        good = SCENE.replace('script = ExtResource("1_a")\n', "").replace(
            '[ext_resource type="Script" uid="uid://x1" path="res://player.gd" id="1_a"]\n', "")
        for name, text in (("good.tscn", good), ("broken.tscn", broken)):
            with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        with open(os.path.join(d, "load.gd"), "w", encoding="utf-8") as fh:
            fh.write('extends SceneTree\nfunc _init():\n'
                     '\tfor n in ["good", "broken"]:\n'
                     '\t\tvar s = load("res://%s.tscn" % n)\n'
                     '\t\tvar node = s.instantiate() if s else null\n'
                     '\t\tvar ok = node != null and node.get_node_or_null("CameraRig/Pivot") != null\n'
                     '\t\tprint("KILN:%s:%s" % [n, ok])\n'
                     '\tquit()\n')
        p = subprocess.run([GODOT, "--headless", "--path", d, "--script", "res://load.gd"],
                           capture_output=True, text=True, timeout=120)
        self.assertIn("KILN:good:true", p.stdout, p.stdout[-1500:] + p.stderr[-1500:])
        self.assertIn("KILN:broken:false", p.stdout)
        problems, _ = godot_lint.lint_scene(broken, "broken.tscn", d)
        self.assertTrue(any("parent" in x["problem"] for x in problems))


if __name__ == "__main__":
    unittest.main()
