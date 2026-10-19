"""Runs blender-modeling joint_topology.py and joint_bend.py in a background Blender (skipped
without one) on an arm tube: rings every centimetre close loops around the elbow; rings 12 cm
apart leave none in the elbow band; the same dense tube triangulated has no quad loops at all.
The bend test binds a copy with automatic weights and measures the elbow's cross-sections."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from test_mesh_qa import BLENDER  # noqa: E402

SCRIPTS = os.path.join(HERE, "..", "plugins", "kiln", "skills", "blender-modeling", "scripts")
TOPO = os.path.join(SCRIPTS, "joint_topology.py")
BEND = os.path.join(SCRIPTS, "joint_bend.py")

DRIVER = r'''
import bpy, bmesh, json, math, sys
from mathutils import Vector
args = sys.argv[sys.argv.index("--") + 1:]
topo, bend, out, spacing, tri = args[0], args[1], args[2], float(args[3]), args[4] == "1"
bpy.ops.wm.read_factory_settings(use_empty=True)
ad = bpy.data.armatures.new("rig")
arm = bpy.data.objects.new("rig", ad)
bpy.context.scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
bones = {"Spine": ((0, 0, 1.1), (0, 0, 1.4)), "LeftArm": ((0.15, 0, 1.4), (0.45, 0, 1.4)),
         "LeftForeArm": ((0.45, 0, 1.4), (0.72, 0, 1.4)), "LeftHand": ((0.72, 0, 1.4), (0.8, 0, 1.4))}
for n, (h, t) in bones.items():
    b = ad.edit_bones.new(n)
    b.head, b.tail = h, t
ad.edit_bones["LeftArm"].parent = ad.edit_bones["Spine"]
ad.edit_bones["LeftForeArm"].parent = ad.edit_bones["LeftArm"]
ad.edit_bones["LeftHand"].parent = ad.edit_bones["LeftForeArm"]
bpy.ops.object.mode_set(mode="OBJECT")
bm = bmesh.new()
xs = [0.15]
while xs[-1] + spacing < 0.8 - 1e-9:
    xs.append(round(xs[-1] + spacing, 5))
xs.append(0.8)
rings = []
for x in xs:
    rings.append([bm.verts.new((x, 0.04 * math.cos(2 * math.pi * k / 16), 1.4 + 0.04 * math.sin(2 * math.pi * k / 16)))
                  for k in range(16)])
for i in range(len(rings) - 1):
    for k in range(16):
        bm.faces.new((rings[i][k], rings[i][(k + 1) % 16], rings[i + 1][(k + 1) % 16], rings[i + 1][k]))
for ring in (rings[0], rings[-1]):
    bm.faces.new(ring)
if tri:
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
me = bpy.data.meshes.new("arm")
bm.to_mesh(me)
obj = bpy.data.objects.new("arm", me)
bpy.context.scene.collection.objects.link(obj)
res = {}
for key, path in (("topology", topo), ("bend", bend)):
    src = open(path, encoding="utf-8").read().replace('MESH = ""', 'MESH = "arm"', 1).replace('ARMATURE = ""', 'ARMATURE = "rig"', 1)
    ns = {}
    exec(compile(src, path, "exec"), ns)
    res[key] = ns["result"]
res["objects"] = sorted(o.name for o in bpy.data.objects)
json.dump(res, open(out, "w"), default=str)
'''


@unittest.skipUnless(BLENDER, "no Blender found (set KILN_BLENDER)")
class JointTopology(unittest.TestCase):
    def run_case(self, spacing, tri=False):
        d = tempfile.mkdtemp(prefix="kiln-joint-")
        driver = os.path.join(d, "driver.py")
        with open(driver, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        out = os.path.join(d, "out.json")
        p = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", driver, "--",
                            os.path.abspath(TOPO), os.path.abspath(BEND), out, str(spacing),
                            "1" if tri else "0"], capture_output=True, text=True, timeout=600)
        self.assertTrue(os.path.isfile(out), p.stdout[-3000:] + p.stderr[-3000:])
        with open(out, encoding="utf-8") as fh:
            return json.load(fh)

    def elbow(self, res):
        return next(j for j in res["topology"]["joints"] if j["joint"] == "elbow_l")

    def test_dense_rings_loop_the_elbow_and_bend(self):
        res = self.run_case(0.01)
        elbow = self.elbow(res)
        self.assertGreaterEqual(elbow["loops"], 3, elbow)
        self.assertEqual(elbow["poles_in_band"], 0, elbow)
        self.assertEqual(elbow["verdict"], "pass", elbow)
        bend = next(j for j in res["bend"]["joints"] if j["joint"] == "elbow_l")
        self.assertEqual([a["degrees"] for a in bend["angles"]], [90, 120])
        ninety = bend["angles"][0]["checks"]
        self.assertEqual(ninety["area"]["verdict"], "pass", bend)      # 0.83 measured
        self.assertLess(ninety["area"]["min_ratio"], 1.0, bend)
        self.assertNotIn("kiln_bend_copy", res["objects"])            # the copy is gone

    def test_sparse_rings_leave_the_elbow_without_loops(self):
        res = self.run_case(0.12)
        elbow = self.elbow(res)
        self.assertLess(elbow["loops"], 2, elbow)
        self.assertEqual(elbow["verdict"], "fail")
        bend = next(j for j in res["bend"]["joints"] if j["joint"] == "elbow_l")
        self.assertEqual(bend["angles"][0]["checks"]["area"]["verdict"], "fail", bend)  # 0.71

    def test_triangles_have_no_quad_loops(self):
        elbow = self.elbow(self.run_case(0.01, tri=True))
        self.assertEqual(elbow["loops"], 0, elbow)
        self.assertEqual(elbow["non_quad_share"], 1.0)
        self.assertEqual(elbow["verdict"], "fail")


if __name__ == "__main__":
    unittest.main()
