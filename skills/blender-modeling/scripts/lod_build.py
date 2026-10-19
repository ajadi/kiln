# Kiln LOD chain builder — run through the Blender Lab MCP (execute_blender_code).
# Paste this file's content, set the parameters below; the report is returned in `result`.
#
# Builds <name>_LOD1.._LODn copies of the LOD0 objects (each renamed <name>_LOD0), every level
# about RATIO of the previous level's triangles, and measures what each level costs on screen:
#   e_max / e_p95   two-sided sampled Hausdorff distance to LOD0 (metres)
#   screen          the switch size s = PIXELS * D / (e_max * SCREEN_H): the level may be shown
#                   once the object's bounding sphere covers less than s of the screen height
#                   (D = LOD0 bounding diameter; 1 px of error is what Godot, Nanite and
#                   Simplygon call lossless). Stored on every level object as custom properties
#                   kiln_lod_screen, kiln_lod_error_m, kiln_lod_diameter_m (glTF extras when
#                   exported with export_extras=True) for the engine import.
# Parts smaller than PART_MIN_PX at a level's switch size are left out of that level.
# Rules (asset-pipeline "LOD chain"): LOD0 under 256 triangles -> no LODs (cull with a
# distance); under MIN_TRIS -> no authored chain (the engine's automatic LOD); a level that
# cuts less than 25 % is not kept; the chain stops below MIN_TRIS or below MIN_SCREEN.
# All levels stay under one parent (an Empty named after the collection is made when the LOD0
# objects have none). Running it again rebuilds the levels from LOD0.

import bpy
import bmesh
import math
import random
import re
from mathutils.bvhtree import BVHTree

TARGETS = []               # LOD0 object names; [] = every mesh in COLLECTION
COLLECTION = "asset"
LEVELS = 3                 # most levels to build after LOD0
RATIO = 0.5                # triangles of a level / the previous level
METHOD = "collapse"        # collapse (organic, generated) | planar (flat hard-surface panels)
PLANAR_ANGLE_DEG = 5.0
PROTECT_GROUP = ""         # vertex group decimated less (face, hands, joints)
PIXELS = 1.0               # screen error tolerance; 2-4 in a performance profile
SCREEN_H = 1080            # target vertical resolution (GAME.md)
MIN_TRIS = 1000
MIN_SCREEN = 0.02
PART_MIN_PX = 2.0
SAMPLES = 20000            # surface points per side for the Hausdorff distance

LOD = re.compile(r"^(.*?)_LOD(\d+)$", re.I)


def _lod0():
    if TARGETS:
        objs = [bpy.data.objects[n] for n in TARGETS if n in bpy.data.objects]
    else:
        coll = bpy.data.collections.get(COLLECTION)
        objs = list(coll.all_objects) if coll else list(bpy.context.scene.objects)
    out = []
    for o in objs:
        m = LOD.match(o.name)
        if o.type == 'MESH' and not (m and int(m.group(2)) > 0) and \
                not o.name.endswith(("-colonly", "-convcolonly")):
            out.append(o)
    return out


def _tris(objs, depsgraph):
    n = 0
    for o in objs:
        ev = o.evaluated_get(depsgraph)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        n += len(me.loop_triangles)
        ev.to_mesh_clear()
    return n


def _world_bm(objs, depsgraph):
    bm = bmesh.new()
    for o in objs:
        part = bmesh.new()
        part.from_object(o, depsgraph)
        part.transform(o.matrix_world)
        me = bpy.data.meshes.new("kiln_tmp")
        part.to_mesh(me)
        part.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    return bm


def _samples(bm, n, rng):
    pts = [v.co.copy() for v in bm.verts] + [f.calc_center_median() for f in bm.faces]
    return pts if len(pts) <= n else rng.sample(pts, n)


def _hausdorff(bm_a, bm_b):
    rng = random.Random(0)
    ta, tb = BVHTree.FromBMesh(bm_a), BVHTree.FromBMesh(bm_b)
    d = []
    for pts, tree in ((_samples(bm_a, SAMPLES, rng), tb), (_samples(bm_b, SAMPLES, rng), ta)):
        for p in pts:
            hit = tree.find_nearest(p)
            d.append(hit[3] if hit[0] is not None else 0.0)
    d.sort()
    return d[-1] if d else 0.0, d[int(0.95 * (len(d) - 1))] if d else 0.0


def _diameter(objs):
    from mathutils import Vector
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return (hi - lo).length


def _remove_levels(bases):
    for o in list(bpy.data.objects):
        m = LOD.match(o.name)
        if m and int(m.group(2)) > 0 and m.group(1) in bases:
            data = o.data
            bpy.data.objects.remove(o)
            if data and data.users == 0:
                bpy.data.meshes.remove(data)


def _copy_level(src, base, level, depsgraph):
    obj = src.copy()
    obj.data = src.data.copy()
    obj.name = f"{base}_LOD{level}"
    obj.data.name = obj.name
    for c in src.users_collection:
        c.objects.link(obj)
    obj.modifiers.clear()
    if METHOD == "planar":
        dm = obj.modifiers.new("kiln_lod", 'DECIMATE')
        dm.decimate_type = 'DISSOLVE'
        dm.angle_limit = math.radians(PLANAR_ANGLE_DEG)
        dm.delimit = {'NORMAL', 'MATERIAL', 'SEAM', 'SHARP', 'UV'}
        obj.modifiers.new("kiln_tri", 'TRIANGULATE')
    else:
        dm = obj.modifiers.new("kiln_lod", 'DECIMATE')
        dm.decimate_type = 'COLLAPSE'
        dm.ratio = RATIO
        dm.use_collapse_triangulate = True
        if PROTECT_GROUP and PROTECT_GROUP in obj.vertex_groups:
            dm.vertex_group = PROTECT_GROUP
            dm.invert_vertex_group = True
    wn = obj.modifiers.new("kiln_wn", 'WEIGHTED_NORMAL')
    wn.keep_sharp = True
    depsgraph.update()
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = bpy.data.meshes.new_from_object(ev)
    old = obj.data
    obj.modifiers.clear()
    obj.data = mesh
    mesh.name = obj.name
    if old.users == 0:
        bpy.data.meshes.remove(old)
    return obj


def build():
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lod0 = _lod0()
    if not lod0:
        raise RuntimeError("no LOD0 mesh objects")
    tris0 = _tris(lod0, depsgraph)
    if tris0 < 256:
        return {"lod0_tris": tris0, "levels": [], "skipped": "under 256 triangles: no LODs, "
                "cull with a distance (Godot visibility_range_end)"}
    if tris0 < MIN_TRIS:
        return {"lod0_tris": tris0, "levels": [], "skipped": f"under {MIN_TRIS} triangles: no "
                "authored chain, keep the engine's automatic LOD"}
    bases = []
    for o in lod0:
        m = LOD.match(o.name)
        base = m.group(1) if m else o.name
        if not m:
            o.name = f"{base}_LOD0"
        bases.append(base)
    _remove_levels(set(bases))
    parents = {o.parent for o in lod0}
    if parents == {None}:
        root = bpy.data.objects.get(COLLECTION) or bpy.data.objects.new(COLLECTION, None)
        if root.name not in bpy.context.scene.objects:
            (lod0[0].users_collection[0] if lod0[0].users_collection else
             bpy.context.scene.collection).objects.link(root)
        for o in lod0:
            mw = o.matrix_world.copy()
            o.parent = root
            o.matrix_world = mw
    D = _diameter(lod0)
    bm0 = _world_bm(lod0, depsgraph)
    for o in lod0:
        o["kiln_lod_screen"], o["kiln_lod_error_m"], o["kiln_lod_diameter_m"] = 1.0, 0.0, D
    levels, prev, prev_tris = [], list(zip(bases, lod0)), tris0
    note = ""
    for level in range(1, LEVELS + 1):
        made = [(b, _copy_level(src, b, level, depsgraph)) for b, src in prev]
        depsgraph = bpy.context.evaluated_depsgraph_get()
        dropped = []
        for _ in range(2):                                  # drop sub-pixel parts, measure again
            bm = _world_bm([o for _, o in made], depsgraph)
            e_max, e_p95 = _hausdorff(bm0, bm)
            bm.free()
            screen = min(1.0, PIXELS * D / (e_max * SCREEN_H)) if e_max > 0 else 1.0
            small = [(b, o) for b, o in made if len(made) - len(dropped) > 1 and
                     _diameter([o]) / D * screen * SCREEN_H < PART_MIN_PX]
            if not small:
                break
            for b, o in small:
                dropped.append(o.name)
                made.remove((b, o))
                data = o.data
                bpy.data.objects.remove(o)
                bpy.data.meshes.remove(data)
        tris = _tris([o for _, o in made], depsgraph)
        if tris > 0.75 * prev_tris:
            for _, o in made:
                data = o.data
                bpy.data.objects.remove(o)
                bpy.data.meshes.remove(data)
            note = f"level {level} cut less than 25 % ({tris} of {prev_tris}): not kept"
            break
        for _, o in made:
            o["kiln_lod_screen"], o["kiln_lod_error_m"], o["kiln_lod_diameter_m"] = \
                round(screen, 5), round(e_max, 6), D
        mats = {s.material.name for _, o in made for s in o.material_slots if s.material}
        levels.append({"level": level, "tris": tris, "ratio": round(tris / prev_tris, 3),
                       "materials": len(mats), "e_max_m": round(e_max, 6),
                       "e_p95_m": round(e_p95, 6), "screen": round(screen, 5),
                       "switch_px": round(screen * SCREEN_H, 1), "dropped_parts": dropped})
        prev, prev_tris = made, tris
        if tris < MIN_TRIS or screen < MIN_SCREEN:
            note = f"chain ends at level {level} (under {MIN_TRIS} triangles or screen < {MIN_SCREEN})"
            break
    bm0.free()
    return {"lod0_tris": tris0, "diameter_m": round(D, 4), "pixels": PIXELS,
            "screen_h": SCREEN_H, "method": METHOD, "levels": levels, "note": note,
            "next": "lod_shots.py, export with export_extras=True, then lod_check.py"}


result = build()
