"""Runs plugins/kiln/skills/animation/scripts/deform_check.py in a background Blender (skipped
without one) on a stick-figure rig of tubes with Mixamo bone names (the names Meshy's auto-rig
uses): smooth joint weights give a blended ring and a measurable volume ratio; hard weights have
no ring and fail; a plain forearm twist shows the candy-wrapper."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from test_mesh_qa import BLENDER  # noqa: E402

SCRIPT = os.path.join(HERE, "..", "plugins", "kiln", "skills", "animation", "scripts",
                      "deform_check.py")

DRIVER = r'''
import bpy, bmesh, json, math, sys
from mathutils import Vector
args = sys.argv[sys.argv.index("--") + 1:]
script, out, blend = args[0], args[1], float(args[2])
bpy.ops.wm.read_factory_settings(use_empty=True)
# T-pose stick figure facing -Y: shoulders at z 1.4, hips at z 0.9
J = {"Hips": ((0, 0, 0.9), (0, 0, 1.1)), "Spine": ((0, 0, 1.1), (0, 0, 1.4)),
     "LeftArm": ((0.15, 0, 1.4), (0.45, 0, 1.4)), "LeftForeArm": ((0.45, 0, 1.4), (0.72, 0, 1.4)),
     "LeftHand": ((0.72, 0, 1.4), (0.8, 0, 1.4)),
     "RightArm": ((-0.15, 0, 1.4), (-0.45, 0, 1.4)), "RightForeArm": ((-0.45, 0, 1.4), (-0.72, 0, 1.4)),
     "RightHand": ((-0.72, 0, 1.4), (-0.8, 0, 1.4)),
     "LeftUpLeg": ((0.1, 0, 0.9), (0.1, 0, 0.5)), "LeftLeg": ((0.1, 0, 0.5), (0.1, 0, 0.08)),
     "LeftFoot": ((0.1, 0, 0.08), (0.1, -0.12, 0.02)),
     "RightUpLeg": ((-0.1, 0, 0.9), (-0.1, 0, 0.5)), "RightLeg": ((-0.1, 0, 0.5), (-0.1, 0, 0.08)),
     "RightFoot": ((-0.1, 0, 0.08), (-0.1, -0.12, 0.02))}
P = {"Spine": "Hips", "LeftArm": "Spine", "LeftForeArm": "LeftArm", "LeftHand": "LeftForeArm",
     "RightArm": "Spine", "RightForeArm": "RightArm", "RightHand": "RightForeArm",
     "LeftUpLeg": "Hips", "LeftLeg": "LeftUpLeg", "LeftFoot": "LeftLeg",
     "RightUpLeg": "Hips", "RightLeg": "RightUpLeg", "RightFoot": "RightLeg"}
ad = bpy.data.armatures.new("rig")
arm = bpy.data.objects.new("rig", ad)
bpy.context.scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
for n, (h, t) in J.items():
    b = ad.edit_bones.new(n)
    b.head, b.tail = h, t
for n, p in P.items():
    ad.edit_bones[n].parent = ad.edit_bones[p]
bpy.ops.object.mode_set(mode="OBJECT")
# tubes: (first bone, second bone, start, end, radius); rings every 1 cm
LIMBS = [("LeftArm", "LeftForeArm", (0.15, 0, 1.4), (0.72, 0, 1.4), 0.04),
         ("RightArm", "RightForeArm", (-0.15, 0, 1.4), (-0.72, 0, 1.4), 0.04),
         ("LeftUpLeg", "LeftLeg", (0.1, 0, 0.9), (0.1, 0, 0.08), 0.06),
         ("RightUpLeg", "RightLeg", (-0.1, 0, 0.9), (-0.1, 0, 0.08), 0.06)]
bm = bmesh.new()
weights = []
for a, b, s, e, r in LIMBS:
    s, e = Vector(s), Vector(e)
    d = (e - s).normalized()
    side = d.cross(Vector((0, 1, 0))) if abs(d.y) < 0.9 else Vector((1, 0, 0))
    if side.length < 1e-6:
        side = Vector((1, 0, 0))
    side.normalize()
    up = d.cross(side)
    joint = Vector(J[b][0])
    n = int((e - s).length / 0.01)
    rings = []
    for i in range(n + 1):
        c = s + (e - s) * (i / n)
        ring = []
        for k in range(16):
            ang = 2 * math.pi * k / 16
            v = bm.verts.new(c + (side * math.cos(ang) + up * math.sin(ang)) * r)
            x = (c - joint).dot(d)
            wb = 1.0 if x > blend else 0.0 if x < -blend else (0.5 + 0.5 * x / blend if blend else (1.0 if x >= 0 else 0.0))
            weights.append({a: 1 - wb, b: wb})
            ring.append(v)
        rings.append(ring)
    for i in range(n):
        for k in range(16):
            bm.faces.new((rings[i][k], rings[i][(k + 1) % 16], rings[i + 1][(k + 1) % 16], rings[i + 1][k]))
me = bpy.data.meshes.new("body")
bm.to_mesh(me)
body = bpy.data.objects.new("body", me)
bpy.context.scene.collection.objects.link(body)
for n in J:
    body.vertex_groups.new(name=n)
for i, w in enumerate(weights):
    for g, val in w.items():
        if val > 0:
            body.vertex_groups[g].add([i], val, "REPLACE")
mod = body.modifiers.new("Armature", "ARMATURE")
mod.object = arm
ns = {}
exec(compile(open(script, encoding="utf-8").read(), script, "exec"), ns)
json.dump(ns["result"], open(out, "w"), default=str)
'''


@unittest.skipUnless(BLENDER, "no Blender found (set KILN_BLENDER)")
class DeformCheck(unittest.TestCase):
    def run_case(self, blend):
        d = tempfile.mkdtemp(prefix="kiln-deform-")
        driver = os.path.join(d, "driver.py")
        with open(driver, "w", encoding="utf-8") as fh:
            fh.write(DRIVER)
        out = os.path.join(d, "out.json")
        p = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", driver, "--",
                            os.path.abspath(SCRIPT), out, str(blend)],
                           capture_output=True, text=True, timeout=600)
        self.assertTrue(os.path.isfile(out), p.stdout[-3000:] + p.stderr[-3000:])
        with open(out, encoding="utf-8") as fh:
            return json.load(fh)

    def pose(self, res, name):
        return next(p for p in res["poses"] if p["pose"] == name)

    def test_smooth_weights_blend_and_twist_shows_candy_wrapper(self):
        res = self.run_case(0.06)
        for role in ("upper_arm_l", "forearm_l", "thigh_l", "shin_l", "upper_arm_r", "spine"):
            self.assertIn(role, res["roles"], res["roles"])          # Mixamo names recognised
        self.assertEqual(res["weights"]["verdict"], "pass", res["weights"])
        elbow = self.pose(res, "elbow_l_90")["checks"]
        self.assertIn("volume", elbow, elbow)
        self.assertGreater(elbow["volume"]["ratio"], 0.6)
        self.assertLess(elbow["volume"]["ratio"], 1.2)
        knee = self.pose(res, "knee_l_90")["checks"]
        self.assertIn("volume", knee, knee)
        twist = self.pose(res, "forearm_l_twist+80")["checks"]["candy_wrapper"]
        self.assertEqual(twist["verdict"], "fail", twist)              # plain LBS twist collapses
        self.assertIn("twist bones", twist["fix"])

    def test_hard_weights_have_no_blended_ring(self):
        res = self.run_case(0.0)
        ring = self.pose(res, "elbow_l_90")["checks"]["ring"]
        self.assertEqual(ring["verdict"], "fail", ring)
        self.assertEqual(res["verdict"], "fail")


if __name__ == "__main__":
    unittest.main()
