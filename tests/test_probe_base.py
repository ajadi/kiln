"""Runs plugins/kiln/skills/acceptance/scripts/probe_base.gd in a real headless Godot.

Skipped when no Godot 4.6+ console binary is found (KILN_GODOT, PATH, or ~/tools/Godot/). g2 rows 30, 143, 151: no shared probe base, results landed in the wrong task folder,
and a probe with a script error hung the console until the tool timeout.
"""

import glob
import json
import os
import shutil
import subprocess
import tempfile
import unittest

BASE = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "acceptance",
                    "scripts", "probe_base.gd")


def find_godot():
    env = os.environ.get("KILN_GODOT")
    if env and os.path.isfile(env):
        return env
    for name in ("godot", "godot4"):
        hit = shutil.which(name)
        if hit:
            return hit
    hits = sorted(glob.glob(os.path.expanduser("~/tools/Godot/*/Godot_*_console.exe")))
    return hits[-1] if hits else None


GODOT = find_godot()

PASSING = '''extends "res://tests/probes/probe_base.gd"
func _run() -> void:
	var t0 := Engine.get_physics_frames()
	await ticks(30)
	check("ticks-1", Engine.get_physics_frames() - t0, ">=", 30, "ticks() waits physics frames")
	press("ui_accept")
	await ticks(1)
	check("input-1", Input.is_action_pressed("ui_accept"), "==", true, "press()")
	check("vec-1", Vector3(1, 2, 3), "==", Vector3(1, 2, 3))
'''

FAILING = '''extends "res://tests/probes/probe_base.gd"
func _run() -> void:
	await ticks(2)
	check("speed-1", 2.0, ">=", 3.5, "GAME.md")
'''

CRASHING = '''extends "res://tests/probes/probe_base.gd"
func _run() -> void:
	await ticks(2)
	var n: Node = null
	n.queue_free()
	check("never", 1, "==", 1)
'''

HANGING = '''extends "res://tests/probes/probe_base.gd"
signal never_fires
func _run() -> void:
	await never_fires
'''

MESH_FIT = '''extends "res://tests/probes/probe_base.gd"
func _run() -> void:
	var fit = load("res://tests/probes/mesh_fit.gd").new()
	var sk := Skeleton3D.new()  # kiln:runtime-node test fixture
	sk.add_bone("Root")
	sk.add_bone("LegL")
	sk.set_bone_parent(1, 0)
	root.add_child(sk)
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(0, 0, 0), Vector3(1, 0, 0), Vector3(0, 1, 0)])
	arr[Mesh.ARRAY_BONES] = PackedInt32Array([1,0,0,0, 1,0,0,0, 0,0,0,0])
	arr[Mesh.ARRAY_WEIGHTS] = PackedFloat32Array([1,0,0,0, 1,0,0,0, 1,0,0,0])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	var skin := Skin.new()
	skin.add_named_bind("Root", Transform3D.IDENTITY)
	skin.add_named_bind("LegL", Transform3D.IDENTITY)
	var mi := MeshInstance3D.new()  # kiln:runtime-node test fixture
	mi.mesh = mesh
	mi.skin = skin
	sk.add_child(mi)
	sk.set_bone_pose_position(1, Vector3(0, -0.07, 0))   # the leg sinks 7 cm
	await ticks(2)
	var legs: PackedInt32Array = fit.verts_on(mi, sk, "Leg", 0.5)
	check("legs", legs.size(), "==", 2, "two vertices weighted to LegL")
	var pts: PackedVector3Array = fit.skin_points(mi, sk)
	check("sink", fit.lowest(pts).y, "~", -0.07, "bone pose moves its vertices", 0.001)
	check("rest", pts[2].y, "~", 1.0, "root vertex unmoved", 0.001)
	var c: float = fit.capsule_clearance(pts, Vector3(0, -1, 0), Vector3(0, -0.5, 0), 0.1)
	check("capsule", c, "~", 0.33, "distance to a capsule below", 0.01)
'''


@unittest.skipUnless(GODOT, "no Godot console binary found (set KILN_GODOT)")
class ProbeBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-probe-")
        with open(os.path.join(self.root, "project.godot"), "w", encoding="utf-8") as fh:
            fh.write('config_version=5\n\n[application]\n\nconfig/name="probe"\n')
        os.makedirs(os.path.join(self.root, "tests", "probes"))
        shutil.copy(BASE, os.path.join(self.root, "tests", "probes", "probe_base.gd"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def probe(self, name, body, *user_args, timeout=120):
        with open(os.path.join(self.root, "tests", "probes", name + ".gd"), "w",
                  encoding="utf-8") as fh:
            fh.write(body)
        cmd = [GODOT, "--headless", "--fixed-fps", "60", "--path", self.root, "-s",
               f"res://tests/probes/{name}.gd"]
        if user_args:
            cmd += ["--", *user_args]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def result(self, *parts):
        with open(os.path.join(self.root, *parts), encoding="utf-8") as fh:
            return json.load(fh)

    def test_pass_writes_the_task_folder(self):
        p = self.probe("probe_ok", PASSING, "--task", "TASK-019")
        res = self.result("production", "captures", "TASK-019", "probe_ok.json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(res["verdict"], "PASS", res)
        self.assertEqual([r["id"] for r in res["rows"]], ["ticks-1", "input-1", "vec-1"])
        self.assertTrue(res["headless"])

    def test_mesh_fit_skins_on_the_cpu(self):
        # g2 row 149: the dummy renderer does not skin; garment and floor fits need a CPU skinner.
        shutil.copy(os.path.join(os.path.dirname(BASE), "mesh_fit.gd"),
                    os.path.join(self.root, "tests", "probes", "mesh_fit.gd"))
        p = self.probe("probe_fit", MESH_FIT)
        res = self.result(".kiln", "tmp", "probe_fit.json")
        self.assertEqual(p.returncode, 0, json.dumps(res) + p.stdout + p.stderr)

    def test_fail_exits_1_into_kiln_tmp(self):
        p = self.probe("probe_bad", FAILING)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(self.result(".kiln", "tmp", "probe_bad.json")["verdict"], "FAIL")

    def test_script_error_is_not_assessed_not_a_hang(self):
        p = self.probe("probe_crash", CRASHING, timeout=60)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        res = self.result(".kiln", "tmp", "probe_crash.json")
        self.assertEqual(res["verdict"], "NOT ASSESSED")
        self.assertTrue(any("no check rows" in n for n in res["notes"]), res)

    def test_a_wait_that_never_ends_hits_the_watchdog(self):
        p = self.probe("probe_hang", HANGING, "--watchdog", "3", timeout=60)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        res = self.result(".kiln", "tmp", "probe_hang.json")
        self.assertTrue(any("watchdog" in n for n in res["notes"]), res)


if __name__ == "__main__":
    unittest.main()
