# Kiln deformation check — run through the Blender Lab MCP (execute_blender_code) after rigging
# (by hand or by an auto-rigger) and before any clip. Paste this file, set MESH (and BONES when
# the bone names are unusual); the report is returned in `result`.
#
# Poses the rig into stress poses from the human-biomechanics range-of-motion table and measures
# the skinned mesh as the engine would draw it: linear blend skinning, Preserve Volume off (most
# game paths; set PRESERVE_VOLUME only when the engine skins with dual quaternions).
#   weights        every vertex weighted, at most INFLUENCES bones, sums near 1, no stray weight
#                  from a bone farther than 0.25 of the body height
#   joint_centre   centroid of the joint's blended ring vs the bone head: <= 15 % of the limb
#   volume         mean distance of the ring to the joint, posed / rest: 0.85-1.15 at 90 degrees,
#                  >= 0.75 at 130 (elbow, knee, hip)
#   candy_wrapper  forearm twisted +-80 degrees: smallest mean radius along the forearm, posed /
#                  rest >= 0.80 (below: forearm twist bones at 1/3 and 2/3)
#   shoulder       abduction 90 and 160: shoulder-top distance to the upper-arm axis >= 0.85
#   edge_stretch   joint-band edges, 95th percentile of posed / rest - 1 <= 0.35 (stretch only:
#                  the inner crease compresses in any bend; stretched texels are the artefact)
#   overlaps       faces crossing other faces outside the bent joint's band: none
#   mesh_volume    closed meshes: total volume within 3 %
# Thresholds are working values (research 2026-10-19, UNVERIFIED): record what approved rigs
# measure in memory/pipeline.md. Fixes, in order: joint placement, edge loops (three at elbows
# and knees), weight smoothing, twist bones, corrective bones, corrective shape keys.
# The pose is reset to rest and every setting restored afterwards.

import bpy
import bmesh
import math
import re
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

MESH = ""                  # the skinned mesh object; "" = the only mesh with an Armature modifier
BONES = {}                 # role -> bone name overrides, e.g. {"forearm_l": "lowerarm_l"}
INFLUENCES = 4             # the engine's bone influences per vertex
PRESERVE_VOLUME = False
FORWARD = Vector((0, -1, 0))   # the character faces -Y in Blender (asset-pipeline)
UP = Vector((0, 0, 1))

ROLE_KEYS = {"upper_arm": {"arm", "upperarm"}, "forearm": {"forearm", "lowerarm"},
             "hand": {"hand"}, "thigh": {"thigh", "upleg", "upperleg"},
             "shin": {"shin", "calf", "leg", "lowerleg"}, "foot": {"foot"},
             "clavicle": {"clavicle", "shoulder"}}


def _mesh():
    if MESH:
        return bpy.data.objects[MESH]
    found = [o for o in bpy.context.scene.objects if o.type == 'MESH' and
             any(m.type == 'ARMATURE' and m.object for m in o.modifiers)]
    if len(found) != 1:
        raise RuntimeError(f"set MESH: {len(found)} meshes with an Armature modifier")
    return found[0]


def _side_and_key(name):
    n = name.split(":")[-1].lower()
    n = re.sub(r"^(def|org|mch)[-_]", "", n)
    n = re.sub(r"[._]\d+$", "", n)
    side = None
    for pat, s in ((r"^left|^l[._-]|[._-]l$|[._-]left$", "l"), (r"^right|^r[._-]|[._-]r$|[._-]right$", "r")):
        if re.search(pat, n):
            side = s
            n = re.sub(pat, "", n)
            break
    return side, re.sub(r"[^a-z]", "", n)


def _roles(arm):
    roles = {}
    for b in arm.data.bones:
        if not b.use_deform or "twist" in b.name.lower():
            continue
        side, key = _side_and_key(b.name)
        if key.startswith("spine") and "spine" not in roles:
            roles["spine"] = b.name
        for role, keys in ROLE_KEYS.items():
            if key in keys and side:
                roles.setdefault(f"{role}_{side}", b.name)
    roles.update(BONES)
    return roles


def _reset(arm):
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def _world_head_dir(arm, name):
    pb = arm.pose.bones[name]
    h, t = arm.matrix_world @ pb.head, arm.matrix_world @ pb.tail
    return h, (t - h).normalized()


def _rotate(arm, name, rot_world):
    """Rotate a pose bone about its head by a world-space rotation (3x3)."""
    pb = arm.pose.bones[name]
    a3 = arm.matrix_world.to_3x3().normalized()
    r = (a3.inverted() @ rot_world @ a3).to_4x4()
    h = pb.head.copy()
    pb.matrix = Matrix.Translation(h) @ r @ Matrix.Translation(-h) @ pb.matrix
    bpy.context.view_layer.update()


def _aim(arm, name, target_dir):
    _, d = _world_head_dir(arm, name)
    _rotate(arm, name, d.rotation_difference(target_dir.normalized()).to_matrix())


def _bend(arm, name, toward, degrees):
    """Swing a bone by `degrees` from its current direction toward `toward`."""
    _, d = _world_head_dir(arm, name)
    axis = d.cross(toward)
    if axis.length < 1e-6:
        return
    _rotate(arm, name, Matrix.Rotation(math.radians(degrees), 3, axis.normalized()))


def _twist(arm, name, degrees):
    _, d = _world_head_dir(arm, name)
    _rotate(arm, name, Matrix.Rotation(math.radians(degrees), 3, d))


def _positions(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    pts = [obj.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return pts


def _weights(obj, deform):
    names = {g.index: g.name for g in obj.vertex_groups}
    out = []
    for v in obj.data.vertices:
        out.append({names[g.group]: g.weight for g in v.groups
                    if names.get(g.group) in deform and g.weight > 0})
    return out


def _ring(weights, a, b):
    return [i for i, w in enumerate(weights) if 0.3 <= w.get(a, 0) <= 0.7 and 0.3 <= w.get(b, 0) <= 0.7]


def _band(weights, a, b):
    return {i for i, w in enumerate(weights) if 0.1 <= w.get(a, 0) + w.get(b, 0) and
            (0.1 <= w.get(a, 0) <= 0.9 or 0.1 <= w.get(b, 0) <= 0.9)}


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _dist_to_axis(p, h, d):
    v = p - h
    return (v - d * v.dot(d)).length


def _volume(obj, pts):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    if any(not e.is_manifold for e in bm.edges):
        bm.free()
        return None
    bm.verts.ensure_lookup_table()
    for v in bm.verts:
        v.co = pts[v.index]
    vol = abs(bm.calc_volume(signed=True))
    bm.free()
    return vol


def _overlaps(obj, pts, allowed):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    for v in bm.verts:
        v.co = pts[v.index]
    bm.faces.ensure_lookup_table()
    tree = BVHTree.FromBMesh(bm)
    faces = [set(v.index for v in f.verts) for f in bm.faces]
    bad = 0
    for i, j in tree.overlap(tree):
        if i >= j or faces[i] & faces[j]:
            continue
        if faces[i] <= allowed or faces[j] <= allowed:
            continue
        bad += 1
    bm.free()
    return bad


def check():
    obj = _mesh()
    mod = next(m for m in obj.modifiers if m.type == 'ARMATURE' and m.object)
    arm = mod.object
    keep_pv, keep_pose = mod.use_deform_preserve_volume, arm.data.pose_position
    deform = {b.name for b in arm.data.bones if b.use_deform}
    roles = _roles(arm)
    weights = _weights(obj, deform)
    out = {"mesh": obj.name, "armature": arm.name, "roles": roles, "poses": [], "problems": []}
    try:
        mod.use_deform_preserve_volume = PRESERVE_VOLUME
        arm.data.pose_position = 'POSE'
        _reset(arm)
        rest = _positions(obj)
        zs = [p.z for p in rest]
        height = (max(zs) - min(zs)) or 1.0
        # weight hygiene
        unweighted = sum(1 for w in weights if not w)
        over = sum(1 for w in weights if len(w) > INFLUENCES)
        off_sum = sum(1 for w in weights if w and abs(sum(w.values()) - 1) > 0.001)
        stray = 0
        for i, w in enumerate(weights):
            for bone, val in w.items():
                h, d = _world_head_dir(arm, bone)
                seg = (arm.matrix_world @ arm.pose.bones[bone].tail - h).length
                v = rest[i] - h
                t = max(0.0, min(seg, v.dot(d)))
                if val > 0.01 and (v - d * t).length > 0.25 * height:
                    stray += 1
                    break
        out["weights"] = {"vertices": len(weights), "unweighted": unweighted,
                          f"over_{INFLUENCES}_influences": over, "sum_not_1": off_sum,
                          "stray": stray,
                          "verdict": "fail" if unweighted or over or stray else
                          ("warn" if off_sum else "pass")}
        vol0 = _volume(obj, rest)
        poses = []
        for s in ("l", "r"):
            side = Vector((1 if s == "l" else -1, 0, 0))
            ua, fa, th, sh = (roles.get(f"{r}_{s}") for r in ("upper_arm", "forearm", "thigh", "shin"))
            if ua and fa:
                poses += [(f"elbow_{s}_90", fa, ua, lambda a=fa: _bend(arm, a, FORWARD, 90), 90),
                          (f"elbow_{s}_130", fa, ua, lambda a=fa: _bend(arm, a, FORWARD, 130), 130),
                          (f"forearm_{s}_twist+80", fa, ua, lambda a=fa: _twist(arm, a, 80), "twist"),
                          (f"forearm_{s}_twist-80", fa, ua, lambda a=fa: _twist(arm, a, -80), "twist")]
                for deg in (90, 160):
                    target = Vector((side.x * math.sin(math.radians(deg)), 0, -math.cos(math.radians(deg))))
                    poses.append((f"shoulder_{s}_abduction_{deg}", ua, roles.get(f"clavicle_{s}"),
                                  lambda a=ua, t=target: _aim(arm, a, t), "shoulder"))
                poses.append((f"shoulder_{s}_flexion_150", ua, roles.get(f"clavicle_{s}"),
                              lambda a=ua: _aim(arm, a, Vector((0, -0.5, 0.866))), "shoulder"))
            if th and sh:
                poses += [(f"knee_{s}_90", sh, th, lambda a=sh: _bend(arm, a, -FORWARD, 90), 90),
                          (f"knee_{s}_130", sh, th, lambda a=sh: _bend(arm, a, -FORWARD, 130), 130),
                          (f"hip_{s}_flexion_90", th, roles.get("spine"),
                           lambda a=th: _aim(arm, a, FORWARD), 90)]
                target = Vector((side.x * math.sin(math.radians(40)), 0, -math.cos(math.radians(40))))
                poses.append((f"hip_{s}_abduction_40", th, roles.get("spine"),
                              lambda a=th, t=target: _aim(arm, a, t), "abduction"))
        if roles.get("spine"):
            poses.append(("spine_twist_30", roles["spine"], None,
                          lambda: _twist(arm, roles["spine"], 30), "twist_spine"))
        for name, child, _role_parent, apply, kind in poses:
            _reset(arm)
            bone_parent = arm.data.bones[child].parent
            parent = bone_parent.name if bone_parent and bone_parent.name in deform else None
            head0, dir0 = _world_head_dir(arm, child)
            ring = _ring(weights, child, parent) if parent else []
            band = _band(weights, child, parent) if parent else set()
            apply()
            posed = _positions(obj)
            head1, dir1 = _world_head_dir(arm, child)
            row = {"pose": name, "checks": {}}
            if parent and (isinstance(kind, int) or kind in ("shoulder", "abduction")):
                if not ring:
                    row["checks"]["ring"] = {"verdict": "fail", "why": f"no vertices blended "
                                             f"0.3-0.7 between {parent} and {child}: the joint "
                                             "will crease like a hinge (smooth the weights)"}
                else:
                    r0 = _mean([(rest[i] - head0).length for i in ring])
                    r1 = _mean([(posed[i] - head1).length for i in ring])
                    ratio = r1 / r0 if r0 else 0
                    lo = 0.75 if kind == 130 else 0.85
                    hi = 1.15 if isinstance(kind, int) and kind <= 90 else 9.9
                    row["checks"]["volume"] = {"ratio": round(ratio, 3), "range": [lo, hi],
                                               "verdict": "pass" if lo <= ratio <= hi else "fail"}
                    centre = sum((rest[i] for i in ring), Vector()) / len(ring)
                    off = (centre - head0).length / (2 * r0) if r0 else 0
                    row["checks"]["joint_centre"] = {"offset_of_limb": round(off, 3), "limit": 0.15,
                                                     "verdict": "pass" if off <= 0.15 else "warn"}
            if kind == "twist":
                seg = [i for i, w in enumerate(weights) if w.get(child, 0) >= 0.3]
                tail0 = arm.matrix_world @ arm.data.bones[child].tail_local
                length = (tail0 - head0).length or 1
                bins0, bins1 = {}, {}
                for i in seg:
                    t = (rest[i] - head0).dot(dir0) / length
                    if 0 <= t <= 1:
                        k = min(9, int(t * 10))
                        bins0.setdefault(k, []).append(_dist_to_axis(rest[i], head0, dir0))
                        bins1.setdefault(k, []).append(_dist_to_axis(posed[i], head1, dir1))
                ratios = [_mean(bins1[k]) / _mean(bins0[k]) for k in bins0 if _mean(bins0[k]) > 0]
                worst = min(ratios) if ratios else 0
                row["checks"]["candy_wrapper"] = {"min_ratio": round(worst, 3), "limit": 0.8,
                                                  "verdict": "pass" if worst >= 0.8 else "fail",
                                                  **({} if worst >= 0.8 else
                                                     {"fix": "forearm twist bones at 1/3 and 2/3"})}
            if kind == "shoulder":
                tail0 = arm.matrix_world @ arm.data.bones[child].tail_local
                length = (tail0 - head0).length or 1
                top = [i for i, w in enumerate(weights) if w.get(child, 0) > 0.2 and
                       0 <= (rest[i] - head0).dot(dir0) <= 0.25 * length and
                       (rest[i] - head0).dot(UP) > 0]
                if top:
                    r0 = _mean([_dist_to_axis(rest[i], head0, dir0) for i in top])
                    r1 = _mean([_dist_to_axis(posed[i], head1, dir1) for i in top])
                    ratio = r1 / r0 if r0 else 0
                    row["checks"]["shoulder"] = {"ratio": round(ratio, 3), "limit": 0.85,
                                                 "verdict": "pass" if ratio >= 0.85 else "fail"}
            if band:
                strains = []
                for e in obj.data.edges:
                    a, b = e.vertices
                    if a in band or b in band:
                        l0 = (rest[a] - rest[b]).length
                        if l0 > 0:
                            strains.append(max(0.0, (posed[a] - posed[b]).length / l0 - 1))
                strains.sort()
                p95 = strains[int(0.95 * (len(strains) - 1))] if strains else 0
                row["checks"]["edge_stretch"] = {"p95": round(p95, 3), "limit": 0.35,
                                                "verdict": "pass" if p95 <= 0.35 else "fail"}
            crossing = _overlaps(obj, posed, band)
            row["checks"]["overlaps"] = {"faces": crossing,
                                         "verdict": "pass" if crossing == 0 else "fail"}
            if vol0:
                v1 = _volume(obj, posed)
                change = abs(v1 / vol0 - 1)
                row["checks"]["mesh_volume"] = {"change": round(change, 4), "limit": 0.03,
                                                "verdict": "pass" if change <= 0.03 else "fail"}
            out["poses"].append(row)
        for row in out["poses"]:
            for name, c in row["checks"].items():
                if c["verdict"] == "fail":
                    out["problems"].append(f"{row['pose']}: {name} {c}")
        if out["weights"]["verdict"] == "fail":
            out["problems"].insert(0, f"weights: {out['weights']}")
        missing = [r for r in ("upper_arm_l", "forearm_l", "thigh_l", "shin_l") if r not in roles]
        if missing:
            out["problems"].append(f"bones not recognised: {missing}; set BONES")
    finally:
        _reset(arm)
        mod.use_deform_preserve_volume = keep_pv
        arm.data.pose_position = keep_pose
    out["verdict"] = "fail" if out["problems"] else "pass"
    out["fix_order"] = ["joint placement", "edge loops (three at elbows and knees)",
                        "weight smoothing", "twist bones", "corrective bones",
                        "corrective shape keys (only where the engine path supports them)"]
    return out


result = check()
