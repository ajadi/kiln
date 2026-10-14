"""Runs plugins/kiln/skills/blender-modeling/scripts/mesh_qa.py in a background Blender.

Skipped when no Blender 4.2+ is found (KILN_BLENDER, PATH, Program Files). g2 rows 89, 100: a
back-face hole on a statue's neck showed in one quarter view only, and trouser legs ending 10 cm
above the boots (joined into one mesh) passed every check.
"""

import glob
import json
import os
import shutil
import subprocess
import tempfile
import unittest

QA = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                  "blender-modeling", "scripts", "mesh_qa.py")


def find_blender():
    env = os.environ.get("KILN_BLENDER")
    if env and os.path.isfile(env):
        return env
    hit = shutil.which("blender")
    if hit:
        return hit
    hits = sorted(glob.glob("C:/Program Files/Blender Foundation/Blender */blender.exe"))
    return hits[-1] if hits else None


BLENDER = find_blender()

DRIVER = r'''
import bpy, json, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
coll = bpy.data.collections.new("asset")
bpy.context.scene.collection.children.link(coll)
case = sys.argv[sys.argv.index("--") + 1]
out = sys.argv[sys.argv.index("--") + 2]
qa = sys.argv[sys.argv.index("--") + 3]

def add(op, **kw):
    op(**kw)
    obj = bpy.context.active_object
    for c in obj.users_collection:
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj

if case == "clean":
    add(bpy.ops.mesh.primitive_cube_add, size=1.0, location=(0, 0, 0.5))
elif case == "flipped":
    cube = add(bpy.ops.mesh.primitive_cube_add, size=1.0, location=(0, 0, 0.5))
    import bmesh
    bm = bmesh.new(); bm.from_mesh(cube.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[0]], context="FACES")   # open one side: inside shows
    bm.to_mesh(cube.data); bm.free()
elif case == "gap":
    # trouser leg (upper box) ends 10 cm above the boot (lower box), both inside one wide
    # backdrop frame so the gap is enclosed in the front silhouette; joined into one object
    a = add(bpy.ops.mesh.primitive_cube_add, size=1.0, location=(0, 0, 1.3), scale=(0.3, 0.3, 0.5))
    b = add(bpy.ops.mesh.primitive_cube_add, size=1.0, location=(0, 0, 0.475), scale=(0.3, 0.3, 0.95))
    for x in (-0.25, 0.25):
        add(bpy.ops.mesh.primitive_cube_add, size=1.0, location=(x, 0, 0.8), scale=(0.2, 0.2, 1.6))
    bpy.ops.object.select_all(action="DESELECT")
    for o in coll.objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.join()

src = open(qa, encoding="utf-8").read()
ns = {}
exec(compile(src, qa, "exec"), ns)
json.dump(ns["result"], open(out, "w"), default=str)
'''


@unittest.skipUnless(BLENDER, "no Blender found (set KILN_BLENDER)")
class MeshQa(unittest.TestCase):
    def run_case(self, case):
        tmp = tempfile.mkdtemp(prefix="kiln-meshqa-")
        driver = os.path.join(tmp, "driver.py")
        with open(driver, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        out = os.path.join(tmp, "out.json")
        p = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", driver, "--", case,
                            out, os.path.abspath(QA)], capture_output=True, text=True,
                           timeout=300)
        self.assertTrue(os.path.isfile(out), p.stdout[-2000:] + p.stderr[-2000:])
        with open(out, encoding="utf-8") as fh:
            return json.load(fh)

    def test_clean_cube(self):
        res = self.run_case("clean")
        self.assertEqual(res["backfaces"]["views_with_backfaces"], [], res["backfaces"])
        self.assertEqual(res["daylight"]["holes"], [], res["daylight"])

    def test_open_side_shows_back_faces(self):
        res = self.run_case("flipped")
        self.assertGreater(len(res["backfaces"]["views_with_backfaces"]), 0, res["backfaces"])
        self.assertIn("backfaces", " ".join(res["set_problems"]))

    def test_gap_between_joined_parts_is_daylight(self):
        res = self.run_case("gap")
        holes = res["daylight"]["holes"]
        self.assertTrue(holes, res["daylight"])
        z0, z1 = holes[0]["z_range_m"]
        self.assertAlmostEqual(z0, 0.95, delta=0.03)
        self.assertAlmostEqual(z1, 1.05, delta=0.03)


if __name__ == "__main__":
    unittest.main()
