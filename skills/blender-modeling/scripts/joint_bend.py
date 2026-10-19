# Kiln joint bend test — run through the Blender Lab MCP (execute_blender_code) on a deforming
# mesh before (or right after) rigging. Paste this file, set MESH and ARMATURE (the rig, or a
# proxy armature placed at the joints); the report is returned in `result`.
#
# The proof behind joint_topology.py's numbers: a temporary copy of the mesh is bound to the
# armature (automatic weights, or the mesh's own weights with USE_WEIGHTS), each joint is bent
# with linear blend skinning (Preserve Volume off, as game engines draw it) - elbows and knees to
# 90 and 120 degrees of flexion, shoulders and hips to 90 degrees of abduction - and measured:
#   area      smallest cross-section across the joint band (slices at -r .. r), posed / rest:
#             >= 0.75 at 90 degrees, >= 0.60 at 120
#   crossing  faces of the band that pass through other faces at 90 degrees: none (warn)
#   stretch   largest edge length ratio in the band: <= 1.5 (warn)
# Only the area fails the test: crossings in the inner crease and stretched small edges on the
# outer side also show on good meshes, so they warn until calibrated on approved assets.
# Thresholds are UNVERIFIED working values (research 2026-10-19). A mesh that passes here is fine
# for a game even when joint_topology.py counts fewer loops. The copy is deleted and the pose
# reset afterwards; the mesh itself is not changed.

import bpy
import bmesh
import math
import re
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

MESH = ""
ARMATURE = ""
USE_WEIGHTS = False        # True: the mesh's own vertex groups instead of automatic weights
FORWARD = Vector((0, -1, 0))
UP = Vector((0, 0, 1))
SLICES = (-1.0, -0.55, -0.1, 0.1, 0.55, 1.0)   # offsets along the limb in units of its radius;
# not 0: a slice through the joint itself lies in the loop placed there and cuts nothing

KINDS = {"forearm": "elbow", "lowerarm": "elbow", "shin": "knee", "calf": "knee", "leg": "knee",
         "lowerleg": "knee", "arm": "shoulder", "upperarm": "shoulder", "thigh": "hip",
         "upleg": "hip", "upperleg": "hip"}


def _side_and_key(name):
    n = name.split(":")[-1].lower()
    n = re.sub(r"^(def|org|mch)[-_]", "", n)
    n = re.sub(r"[._]\d+$", "", n)
    side = ""
    for pat, s in ((r"^left|^l[._-]|[._-]l$|[._-]left$", "_l"), (r"^right|^r[._-]|[._-]r$|[._-]right$", "_r")):
        if re.search(pat, n):
            side = s
            n = re.sub(pat, "", n)
            break
    return side, re.sub(r"[^a-z]", "", n)


def _reset(arm):
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def _head_dir(arm, name):
    pb = arm.pose.bones[name]
    h, t = arm.matrix_world @ pb.head, arm.matrix_world @ pb.tail
    return h, (t - h).normalized()


def _bend(arm, name, toward, degrees):
    pb = arm.pose.bones[name]
    _, d = _head_dir(arm, name)
    axis = d.cross(toward)
    if axis.length < 1e-6:
        return
    a3 = arm.matrix_world.to_3x3().normalized()
    rot = (a3.inverted() @ Matrix.Rotation(math.radians(degrees), 3, axis.normalized()) @ a3).to_4x4()
    h = pb.head.copy()
    pb.matrix = Matrix.Translation(h) @ rot @ Matrix.Translation(-h) @ pb.matrix
    bpy.context.view_layer.update()


def _posed_bm(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    bm.from_object(obj, dg)
    bm.transform(obj.matrix_world)
    bm.verts.ensure_lookup_table()
    return bm


def _section(bm, co, no, reach):
    """Area of the cut through `co` (normal `no`), from the cut points within `reach` of `co`."""
    cut = bm.copy()
    res = bmesh.ops.bisect_plane(cut, geom=cut.verts[:] + cut.edges[:] + cut.faces[:], dist=1e-7,
                                 plane_co=co, plane_no=no)
    pts = [v.co.copy() for v in res["geom_cut"] if isinstance(v, bmesh.types.BMVert)
           and (v.co - co).length <= reach]
    cut.free()
    if len(pts) < 3:
        return 0.0
    c = sum(pts, Vector()) / len(pts)
    u = no.orthogonal().normalized()
    w = no.cross(u)
    ring = sorted(((p - c).dot(u), (p - c).dot(w)) for p in pts)
    ring.sort(key=lambda q: math.atan2(q[1], q[0]))
    return 0.5 * abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1])))


def _slices(arm, child, parent, r):
    j, dc = _head_dir(arm, child)
    _, dp = _head_dir(arm, parent)
    out = []
    for t in SLICES:
        if t < 0:
            out.append((j + dp * (t * r), dp))
        else:
            out.append((j + dc * (t * r), dc))
    return out


def bend_test():
    obj = bpy.data.objects[MESH] if MESH else bpy.context.active_object
    arm = bpy.data.objects[ARMATURE]
    joints = []
    for b in arm.data.bones:
        side, key = _side_and_key(b.name)
        if b.use_deform and b.parent and key in KINDS and "twist" not in b.name.lower():
            joints.append((KINDS[key] + side, b.name, b.parent.name))
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.name = "kiln_bend_copy"
    bpy.context.scene.collection.objects.link(copy)
    copy.modifiers.clear()
    copy.parent = None
    copy.matrix_world = obj.matrix_world.copy()
    out = {"mesh": obj.name, "armature": arm.name,
           "weights": "own" if USE_WEIGHTS else "automatic", "joints": [], "problems": []}
    keep_pose = arm.data.pose_position
    try:
        arm.data.pose_position = 'POSE'
        _reset(arm)
        if USE_WEIGHTS:
            mod = copy.modifiers.new("Armature", 'ARMATURE')
            mod.object = arm
        else:
            copy.vertex_groups.clear()
            for o in bpy.context.selected_objects:
                o.select_set(False)
            copy.select_set(True)
            arm.select_set(True)
            bpy.context.view_layer.objects.active = arm
            bpy.ops.object.parent_set(type='ARMATURE_AUTO')
            mod = next(m for m in copy.modifiers if m.type == 'ARMATURE')
        mod.use_deform_preserve_volume = False
        rest_bm = _posed_bm(copy)
        rest_edges = {tuple(sorted(v.index for v in e.verts)): e.calc_length() for e in rest_bm.edges}
        for name, child, parent in joints:
            _reset(arm)
            j, d = _head_dir(arm, child)
            length = (arm.data.bones[child].tail_local - arm.data.bones[child].head_local).length
            near = [v.co for v in rest_bm.verts if abs((v.co - j).dot(d)) <= 0.1 * length]
            radial = sorted(((p - j) - d * (p - j).dot(d)).length for p in near) or [0.05]
            r = radial[len(radial) // 2]
            band = {v.index for v in rest_bm.verts
                    if abs((v.co - j).dot(d)) <= 2 * r and ((v.co - j) - d * (v.co - j).dot(d)).length <= 2 * r}
            rest_area = [_section(rest_bm, co, no, 2 * r) for co, no in _slices(arm, child, parent, r)]
            kind = name.split("_")[0]
            if kind in ("elbow", "knee"):
                toward = FORWARD if kind == "elbow" else -FORWARD
                steps = [(90, toward), (120, toward)]
            elif kind == "shoulder":
                steps = [(90, UP)]
            else:
                steps = [(90, Vector((1 if j.x >= 0 else -1, 0, 0)))]
            row = {"joint": name, "bone": child, "radius_m": round(r, 4), "angles": []}
            for deg, toward in steps:
                _reset(arm)
                _bend(arm, child, toward, deg)
                bm = _posed_bm(copy)
                areas = [_section(bm, co, no, 2 * r) for co, no in _slices(arm, child, parent, r)]
                ratios = [a / b for a, b in zip(areas, rest_area) if b > 0]
                worst = min(ratios) if ratios else 0.0
                limit = 0.75 if deg <= 90 else 0.60
                stretch = max((e.calc_length() / rest_edges[k] for e in bm.edges
                               for k in [tuple(sorted(v.index for v in e.verts))]
                               if k[0] in band and rest_edges.get(k)), default=1.0)
                bm.faces.ensure_lookup_table()
                faces = [set(v.index for v in f.verts) for f in bm.faces]
                tree = BVHTree.FromBMesh(bm)
                crossing = sum(1 for a, b in tree.overlap(tree)
                               if a < b and not faces[a] & faces[b] and (faces[a] & band or faces[b] & band))
                bm.free()
                checks = {"area": {"min_ratio": round(worst, 3), "limit": limit,
                                   "verdict": "pass" if worst >= limit else "fail"},
                          "stretch": {"max": round(stretch, 3), "limit": 1.5,
                                      "verdict": "pass" if stretch <= 1.5 else "warn"}}
                if deg <= 90:
                    checks["crossing"] = {"faces": crossing,
                                          "verdict": "pass" if crossing == 0 else "warn"}
                row["angles"].append({"degrees": deg, "checks": checks})
                out["problems"] += [f"{name} {deg}: {k} {c}" for k, c in checks.items()
                                    if c["verdict"] == "fail"]
            out["joints"].append(row)
        rest_bm.free()
    finally:
        _reset(arm)
        arm.data.pose_position = keep_pose
        data = copy.data
        bpy.data.objects.remove(copy)
        bpy.data.meshes.remove(data)
    if not out["joints"]:
        out["problems"].append("no joints recognised from the bone names")
    out["verdict"] = "fail" if out["problems"] else "pass"
    return out


result = bend_test()
