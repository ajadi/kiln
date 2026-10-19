"""Tests for the LOD chain: asset-pipeline lod_check.py on synthetic glbs and shots (no Blender),
and blender-modeling lod_build.py + lod_shots.py end to end in a background Blender (skipped
without one): the built chain halves, leaves sub-pixel parts out, carries its switch sizes as
glTF extras, and passes lod_check.py."""

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from glb_util import box, cylinder, sphere, write_glb  # noqa: E402
from test_mesh_qa import BLENDER  # noqa: E402
from test_probe_base import GODOT  # noqa: E402

SCRIPTS = os.path.join(HERE, "..", "plugins", "kiln", "skills")
CHECK = os.path.join(SCRIPTS, "asset-pipeline", "scripts", "lod_check.py")
BUILD = os.path.join(SCRIPTS, "blender-modeling", "scripts", "lod_build.py")
SHOTS = os.path.join(SCRIPTS, "blender-modeling", "scripts", "lod_shots.py")
BUDGET = os.path.join(SCRIPTS, "asset-pipeline", "scripts", "asset_budget.py")


def with_extras(path, screens, diameter=None):
    """Add kiln_lod_screen extras to the LOD nodes of a glb written by glb_util."""
    data = open(path, "rb").read()
    n = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + n])
    for node in gltf["nodes"]:
        for lv, s in screens.items():
            if node.get("name", "").endswith(f"_LOD{lv}"):
                node["extras"] = {"kiln_lod_screen": s, "kiln_lod_error_m": 0.001,
                                  **({"kiln_lod_diameter_m": diameter} if diameter else {})}
    js = json.dumps(gltf).encode()
    js += b" " * (-len(js) % 4)
    rest = data[20 + n:]
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + rest
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)


def disc(path, radius, size=400):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([size / 2 - radius, size / 2 - radius, size / 2 + radius,
                                 size / 2 + radius], fill=(180, 180, 180, 255))
    img.save(path)


class LodCheck(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="kiln-lod-")

    def check(self, *args):
        p = subprocess.run([sys.executable, "-B", CHECK, *args], capture_output=True, text=True,
                           timeout=120)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            self.fail(p.stdout + p.stderr)

    def chain(self, name, parts, materials=None):
        path = os.path.join(self.d, name + ".glb")
        write_glb(path, [{"name": f"rock_LOD{i}", "tris": t,
                          **({"material": materials[i]} if materials else {})}
                         for i, t in enumerate(parts)],
                  [{"name": f"m{i}"} for i in range(3)] if materials else None, parent="rock")
        return path

    def test_a_halving_chain_passes_and_a_weak_level_fails(self):
        good = self.chain("good", [sphere(32, 64), sphere(22, 46), sphere(16, 32)])
        code, out = self.check(good)
        self.assertEqual(code, 0, out)
        self.assertEqual([lv["level"] for lv in out["levels"]], [0, 1, 2])
        weak = self.chain("weak", [sphere(32, 64), sphere(30, 62)])
        code, out = self.check(weak)
        self.assertEqual((code, out["levels"][1]["checks"]["G1_triangles"]["verdict"]), (1, "fail"))

    def test_more_materials_on_a_far_level_fails(self):
        path = self.chain("mats", [sphere(32, 64), sphere(16, 32)], materials=[0, 1])
        code, out = self.check(path)
        self.assertEqual(out["levels"][1]["checks"]["G8_materials"]["verdict"], "pass")
        path = os.path.join(self.d, "mats2.glb")
        write_glb(path, [{"name": "rock_LOD0", "tris": sphere(32, 64), "material": 0},
                         {"name": "rock_LOD1", "tris": sphere(16, 32), "material": 1},
                         {"name": "rock_LOD1", "tris": box(0.2, 0.2, 0.2), "material": 2}],
                  [{"name": f"m{i}"} for i in range(3)], parent="rock")
        code, out = self.check(path)
        self.assertEqual((code, out["levels"][1]["checks"]["G8_materials"]["verdict"]), (1, "fail"))

    def test_contour_distance_in_game_pixels(self):
        path = self.chain("shots", [sphere(32, 64), sphere(16, 32)])
        with_extras(path, {1: 0.1})
        shots = os.path.join(self.d, "shots")
        os.makedirs(shots)
        # supersample 4: a 2-render-pixel radius change is 0.5 game px, an 8-pixel one 2 px
        for name, r in (("a0.png", 150), ("a1.png", 148), ("b0.png", 150), ("b1.png", 142)):
            disc(os.path.join(shots, name), r)
        for second, verdict in (("a1.png", "pass"), ("b1.png", "fail")):
            with open(os.path.join(shots, "lod_shots.json"), "w", encoding="utf-8") as fh:
                json.dump({"levels": [{"level": 1, "screen": 0.1, "px_per_game_px": 4.0,
                                       "views": [{"azimuth": 0, "elevation": 15,
                                                  "lod0": second[0] + "0.png", "lod": second}]}]}, fh)
            code, out = self.check(path, "--shots", shots)
            self.assertEqual(out["levels"][1]["checks"]["G4_contour"]["verdict"], verdict, out)
        code, out = self.check(path, "--shots", shots, "--profile", "performance")
        self.assertEqual(out["levels"][1]["checks"]["G4_contour"]["verdict"], "pass")

    def test_asset_budget_counts_lod0_and_checks_the_ratio(self):
        path = self.chain("budget", [sphere(32, 64), sphere(30, 62)])
        budgets = os.path.join(self.d, "budgets.json")
        with open(budgets, "w", encoding="utf-8") as fh:
            json.dump({"*": {"lod_ratio": 0.5}}, fh)
        p = subprocess.run([sys.executable, "-B", BUDGET, path, "--budgets", budgets],
                           capture_output=True, text=True, timeout=60)
        out = json.loads(p.stdout)["assets"][0]
        self.assertEqual(out["triangles"], len(sphere(32, 64)))
        self.assertTrue(any("lod_ratio" in x for x in out["problems"]), out)


DRIVER = r'''
import bpy, json, sys
args = sys.argv[sys.argv.index("--") + 1:]
build, shots, outdir = args
bpy.ops.wm.read_factory_settings(use_empty=True)
coll = bpy.data.collections.new("asset")
bpy.context.scene.collection.children.link(coll)
def add(op, **kw):
    op(**kw)
    obj = bpy.context.active_object
    for c in obj.users_collection:
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj
rock = add(bpy.ops.mesh.primitive_uv_sphere_add, segments=64, ring_count=32, radius=0.5, location=(0, 0, 0.5))
rock.name = "rock"
bolt = add(bpy.ops.mesh.primitive_cube_add, size=0.003, location=(0.0, -0.5, 0.5))
bolt.name = "bolt"
ns = {}
exec(compile(open(build, encoding="utf-8").read(), build, "exec"), ns)
built = ns["result"]
src = open(shots, encoding="utf-8").read().replace('OUT = "//.kiln/tmp/lod"', "OUT = " + repr(outdir + "/shots"))
ns = {}
exec(compile(src, shots, "exec"), ns)
bpy.ops.export_scene.gltf(filepath=outdir + "/rock.glb", export_format="GLB", export_extras=True,
                          use_selection=False, export_apply=True)
json.dump({"build": built, "shots": ns["result"],
           "names": sorted(o.name for o in coll.all_objects)}, open(outdir + "/out.json", "w"), default=str)
'''


@unittest.skipUnless(BLENDER, "no Blender found (set KILN_BLENDER)")
class LodBlender(unittest.TestCase):
    def test_build_shoot_export_check(self):
        d = tempfile.mkdtemp(prefix="kiln-lodb-").replace("\\", "/")
        driver = os.path.join(d, "driver.py")
        with open(driver, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        p = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", driver, "--",
                            os.path.abspath(BUILD), os.path.abspath(SHOTS), d],
                           capture_output=True, text=True, timeout=900)
        self.assertTrue(os.path.isfile(os.path.join(d, "out.json")), p.stdout[-3000:] + p.stderr[-3000:])
        with open(os.path.join(d, "out.json"), encoding="utf-8") as fh:
            res = json.load(fh)
        build = res["build"]
        self.assertIn("rock_LOD0", res["names"])
        self.assertGreaterEqual(len(build["levels"]), 1, build)
        first = build["levels"][0]
        self.assertLessEqual(first["ratio"], 0.55, build)
        self.assertGreater(first["screen"], 0, build)
        self.assertTrue(any("bolt" in n for lv in build["levels"] for n in lv["dropped_parts"]),
                        build)                                  # a 3 mm bolt is under 2 px at level 1
        screens = [lv["screen"] for lv in build["levels"]]
        self.assertEqual(screens, sorted(screens, reverse=True))
        p = subprocess.run([sys.executable, "-B", CHECK, os.path.join(d, "rock.glb"), "--shots",
                            os.path.join(d, "shots")], capture_output=True, text=True, timeout=600)
        out = json.loads(p.stdout)
        self.assertEqual(out["levels"][1]["screen"], first["screen"], out)   # extras survived
        self.assertEqual(out["levels"][1]["checks"]["G4_contour"]["verdict"], "pass", out)
        self.assertNotEqual(out["verdict"], "fail", out)


GODOT_SCRIPT = os.path.join(SCRIPTS, "engine-godot", "scripts", "kiln_lod_ranges.gd")
DUMP = '''extends SceneTree
func _init():
\tvar res = load("res://rock.glb")
\tif res == null:
\t\tprint("KILN:null")
\t\tquit(1)
\t\treturn
\tvar s = res.instantiate()
\tvar out = {}
\tfor n in s.find_children("*", "GeometryInstance3D", true, false):
\t\tout[n.name] = [n.visibility_range_begin, n.visibility_range_end, n.visibility_range_end_margin]
\tprint("KILN:", JSON.stringify(out))
\tquit()
'''


@unittest.skipUnless(GODOT, "no Godot found (set KILN_GODOT)")
class LodGodot(unittest.TestCase):
    def test_import_script_turns_extras_into_visibility_ranges(self):
        import shutil
        d = tempfile.mkdtemp(prefix="kiln-lodg-")
        path = os.path.join(d, "rock.glb")
        write_glb(path, [{"name": f"rock_LOD{i}", "tris": t} for i, t in
                         enumerate([sphere(32, 64), sphere(16, 32), sphere(8, 16)])], parent="rock")
        with_extras(path, {0: 1.0, 1: 0.5, 2: 0.2}, diameter=1.0)
        with open(os.path.join(d, "project.godot"), "w", encoding="utf-8") as fh:
            fh.write('config_version=5\n\n[application]\nconfig/name="lod"\n')
        with open(os.path.join(d, "rock.glb.import"), "w", encoding="utf-8") as fh:
            fh.write('[remap]\n\nimporter="scene"\n\n[params]\n\n'
                     'import_script/path="res://kiln_lod_ranges.gd"\nmeshes/generate_lods=false\n')
        with open(os.path.join(d, "dump.gd"), "w", encoding="utf-8") as fh:
            fh.write(DUMP)
        shutil.copy(GODOT_SCRIPT, d)
        subprocess.run([GODOT, "--headless", "--path", d, "--import"], capture_output=True,
                       text=True, timeout=300)
        p = subprocess.run([GODOT, "--headless", "--path", d, "--script", "res://dump.gd"],
                           capture_output=True, text=True, timeout=120)
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("KILN:")), None)
        self.assertIsNotNone(line, p.stdout[-2000:] + p.stderr[-2000:])
        ranges = json.loads(line[5:])
        # FOV 75, D = 1 m: LOD1 from 1 / (2 * 0.5 * tan 37.5) + 0.5 = 1.803 m, LOD2 from 3.758 m
        self.assertAlmostEqual(ranges["rock_LOD0"][1], 1.803, places=2)
        self.assertAlmostEqual(ranges["rock_LOD1"][0], 1.803, places=2)
        self.assertAlmostEqual(ranges["rock_LOD1"][1], 3.758, places=2)
        self.assertEqual(ranges["rock_LOD2"][1], 0.0)                 # the last level stays
        self.assertAlmostEqual(ranges["rock_LOD1"][2], 3.758 * 0.05, places=2)


if __name__ == "__main__":
    unittest.main()
