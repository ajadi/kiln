# Kiln joint topology check — run through the Blender Lab MCP (execute_blender_code) on the quad
# source mesh of a deforming character or creature, before triangulation, export and rigging.
# Paste this file, set MESH and ARMATURE (the rig, or a proxy armature placed at the joints);
# the report is returned in `result`.
#
# A joint bends well when closed edge loops ring it across the bend. Per joint (elbow, knee,
# wrist, ankle, neck, shoulder, hip, found from bone names; JOINTS overrides) it finds the limb
# radius r, the band around the joint (|offset along the child bone| <= r, 1.5 r at shoulders and
# hips), walks quad edge loops from band edges that run around the limb, and counts loops that
# close, cover >= 330 degrees around the limb, tilt <= 30 degrees from the bend plane and sit at
# 0.5-1.6 r. Reported per joint: loops, their offsets, max tilt, broken rings (walks that end at a
# pole), poles in the band, the non-quad share of the band.
# Thresholds (UNVERIFIED starting points, research 2026-10-19):
#   elbow, knee       game_low >= 2 loops; game_mid / hero >= 3 with one within 0.35 r of the joint
#   wrist, ankle, neck >= 2 loops
#   shoulder, hip     >= 2 loops around the limb root (>= 3 for game_mid / hero)
#   every joint       no pole in an elbow or knee band, no broken ring, tilt <= 30;
#                     game_mid / hero: non-quad share <= 0.10
# CLASS by triangles: game_low < 5k, game_mid 5-30k, hero > 30k. The bend test (joint_bend.py)
# is the real gate: a mesh that fails these numbers but passes the bend test is fine for a game;
# these numbers say where to fix. Quadriflow is not a final topology for a deforming mesh.

import bpy
import bmesh
import math
import re
from mathutils import Vector

MESH = ""
ARMATURE = ""
JOINTS = []        # overrides: [{"name": "elbow_l", "head": (x, y, z), "axis": (x, y, z), "kind": "elbow"}]
CLASS = ""         # game_low | game_mid | hero; "" = by triangle count

KINDS = {"forearm": "elbow", "lowerarm": "elbow", "shin": "knee", "calf": "knee", "leg": "knee",
         "lowerleg": "knee", "hand": "wrist", "foot": "ankle", "head": "neck",
         "arm": "shoulder", "upperarm": "shoulder", "thigh": "hip", "upleg": "hip",
         "upperleg": "hip"}


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


def _joints(mesh_obj):
    if JOINTS:
        size = max((max(v.co[i] for v in mesh_obj.data.vertices) - min(v.co[i] for v in mesh_obj.data.vertices))
                   for i in range(3))
        return [{"name": j["name"], "head": Vector(j["head"]), "axis": Vector(j["axis"]).normalized(),
                 "kind": j.get("kind", "elbow"), "segments": None, "length": 0.4 * size}
                for j in JOINTS]
    arm = bpy.data.objects[ARMATURE]
    out = []
    for b in arm.data.bones:
        if not b.use_deform or not b.parent or "twist" in b.name.lower():
            continue
        side, key = _side_and_key(b.name)
        kind = KINDS.get(key)
        if not kind:
            continue
        mw = arm.matrix_world
        head, tail = mw @ b.head_local, mw @ b.tail_local
        ph, pt = mw @ b.parent.head_local, mw @ b.parent.tail_local
        out.append({"name": f"{kind}{side}", "head": head, "axis": (tail - head).normalized(),
                    "kind": kind, "segments": ((ph, pt), (head, tail)),
                    "length": max((tail - head).length, (pt - ph).length)})
    return out


def _seg_dist(p, a, b):
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / (ab.dot(ab) or 1)))
    return (p - (a + ab * t)).length


def _radial(p, j, d):
    v = p - j
    return (v - d * v.dot(d)).length


def _bone_segments():
    if not ARMATURE:
        return []
    arm = bpy.data.objects[ARMATURE]
    mw = arm.matrix_world
    return [(b.name, mw @ b.head_local, mw @ b.tail_local) for b in arm.data.bones if b.use_deform]


def _next_edge(edge, vert):
    """The edge across `vert` that continues an edge loop (quad grid, valence 4)."""
    if len(vert.link_edges) != 4 or any(len(f.verts) != 4 for f in vert.link_faces):
        return None
    faces = set(edge.link_faces)
    for e in vert.link_edges:
        if e is not edge and not (set(e.link_faces) & faces):
            return e
    return None


def _walk(seed):
    """Edges of the loop through `seed`; (edges, closed, ended_at_pole)."""
    edges, pole = [seed], False
    for start in seed.verts:
        e, v = seed, start
        for _ in range(4096):
            if e.is_boundary:
                break
            n = _next_edge(e, v)
            if n is None:
                pole = pole or len(v.link_edges) != 4
                break
            if n is seed:
                return edges, True, False
            edges.append(n)
            v = n.other_vert(v)
            e = n
    return edges, False, pole


def _plane_normal(points):
    """Centroid and normal (smallest-variance direction) of a point loop."""
    c = sum(points, Vector()) / len(points)
    cov = [[sum((p - c)[i] * (p - c)[k] for p in points) for k in range(3)] for i in range(3)]
    shift = cov[0][0] + cov[1][1] + cov[2][2]
    n = Vector((0.31, 0.57, 0.76))
    for _ in range(60):          # power iteration on (trace * I - cov): its top eigenvector
        n = Vector([shift * n[i] - sum(cov[i][k] * n[k] for k in range(3)) for i in range(3)])
        if n.length == 0:
            return c, Vector((0, 0, 1))
        n.normalize()
    return c, n


def check():
    obj = bpy.data.objects[MESH] if MESH else bpy.context.active_object
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    cls = CLASS or ("game_low" if tris < 5000 else "game_mid" if tris < 30000 else "hero")
    segs = _bone_segments()
    nearest = {}
    if segs:
        for v in bm.verts:
            nearest[v.index] = min(segs, key=lambda s: _seg_dist(v.co, s[1], s[2]))[0]
    out = {"mesh": obj.name, "triangles": tris, "class": cls, "joints": [], "problems": []}
    arm = bpy.data.objects[ARMATURE] if ARMATURE else None
    for j in _joints(obj):
        J, d, kind = j["head"], j["axis"], j["kind"]
        root = kind in ("shoulder", "hip")
        allowed = None
        if arm and j["segments"]:
            names = {n for n, h, t in segs if (h - J).length < 1e-4 or (t - J).length < 1e-4}
            allowed = names
        cand = [v for v in bm.verts if allowed is None or nearest.get(v.index) in allowed]
        r = None
        for _ in range(3):
            slab = 0.5 * r if r else 0.25 * j["length"]
            rad = sorted(_radial(v.co, J, d) for v in cand if abs((v.co - J).dot(d)) <= slab)
            if not rad:
                break
            r = rad[len(rad) // 2]
        if not r:
            out["joints"].append({"joint": j["name"], "verdict": "fail", "why": "no mesh around the joint"})
            continue
        half = (1.5 if root else 1.0) * r
        band = {v.index for v in cand if abs((v.co - J).dot(d)) <= half and _radial(v.co, J, d) <= 1.6 * r}
        band_faces = [f for f in bm.faces if all(v.index in band for v in f.verts)]
        seen, loops, broken = set(), [], 0
        for e in bm.edges:
            if e.index in seen or not all(v.index in band for v in e.verts):
                continue
            vec = (e.verts[1].co - e.verts[0].co)
            if vec.length == 0 or abs(vec.normalized().dot(d)) >= 0.5:
                continue
            edges, closed, pole = _walk(e)
            seen.update(x.index for x in edges)
            if not closed:
                broken += 1 if pole else 0
                continue
            pts = list({v.index: v.co for x in edges for v in x.verts}.values())
            c, n = _plane_normal(pts)
            tilt = math.degrees(math.acos(min(1.0, abs(n.dot(d)))))
            radius = sum(_radial(p, J, d) for p in pts) / len(pts)
            ref = d.orthogonal().normalized()
            ref2 = d.cross(ref)
            angs = sorted(math.degrees(math.atan2((p - J).dot(ref2), (p - J).dot(ref))) % 360 for p in pts)
            gaps = [b - a for a, b in zip(angs, angs[1:])] + [360 - angs[-1] + angs[0]]
            offset = (c - J).dot(d)
            if max(gaps) <= 30 and tilt <= 30 and 0.5 * r <= radius <= 1.6 * r and abs(offset) <= half:
                loops.append({"offset_r": round(offset / r, 3), "tilt": round(tilt, 1)})
        poles = sum(1 for i in band if len(bm.verts[i].link_edges) != 4 and not bm.verts[i].is_boundary)
        non_quad = sum(1 for f in band_faces if len(f.verts) != 4) / (len(band_faces) or 1)
        need = 2
        if kind in ("elbow", "knee", "shoulder", "hip") and cls != "game_low":
            need = 3
        problems = []
        if len(loops) < need:
            problems.append(f"{len(loops)} closed loops around the {kind}, need {need}")
        if kind in ("elbow", "knee") and cls != "game_low" and not any(abs(l["offset_r"]) <= 0.35 for l in loops):
            problems.append("no loop within 0.35 r of the joint")
        if kind in ("elbow", "knee") and poles:
            problems.append(f"{poles} poles in the {kind} band (move them to flat areas)")
        if broken:
            problems.append(f"{broken} rings end at a pole inside the band")
        if loops and max(l["tilt"] for l in loops) > 30:
            problems.append("a loop tilts more than 30 degrees")
        if cls != "game_low" and non_quad > 0.10:
            problems.append(f"non-quad share {non_quad:.2f} > 0.10")
        out["joints"].append({"joint": j["name"], "kind": kind, "radius_m": round(r, 4),
                              "loops": len(loops), "offsets_r": sorted(l["offset_r"] for l in loops),
                              "max_tilt": max((l["tilt"] for l in loops), default=None),
                              "broken_rings": broken, "poles_in_band": poles,
                              "non_quad_share": round(non_quad, 3), "need_loops": need,
                              "problems": problems, "verdict": "fail" if problems else "pass"})
        out["problems"] += [f"{j['name']}: {p}" for p in problems]
    bm.free()
    if not out["joints"]:
        out["problems"].append("no joints found: set ARMATURE (bone names) or JOINTS")
    out["verdict"] = "fail" if out["problems"] else "pass"
    out["next"] = "joint_bend.py is the real gate; these numbers say where to add or move loops"
    return out


result = check()
