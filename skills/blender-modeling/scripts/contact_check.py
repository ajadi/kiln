# Kiln contact check — run through the Blender Lab MCP (execute_blender_code).
# For each (child, parent) pair in PAIRS: the smallest distance from the child's surface to the
# parent's surface, and whether the two meshes interpenetrate. Use it for every interface that
# must touch: armour plate on frame, leg segment in joint, part on its mount, prop on the floor.
#
# Verdicts: "contact" (gap <= TOL, no crossing faces), "gap" (daylight between them),
# "crossing" (faces intersect: flush contact can produce a few crossing pairs, many pairs mean
# the parts pass through each other — look close-up; acceptable only for deliberate inserts
# such as a pin in a socket).

import bpy
import bmesh
from mathutils.bvhtree import BVHTree

PAIRS = [("child_object", "parent_object")]
TOL = 0.001          # metres
MAX_SAMPLE = 6000


def _tree(obj, depsgraph):
    bm = bmesh.new()
    bm.from_object(obj, depsgraph)
    bm.transform(obj.matrix_world)
    verts = [v.co.copy() for v in bm.verts]
    polys = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    return BVHTree.FromPolygons(verts, polys), verts


depsgraph = bpy.context.evaluated_depsgraph_get()
out = []
for child_name, parent_name in PAIRS:
    child, parent = bpy.data.objects.get(child_name), bpy.data.objects.get(parent_name)
    if not child or not parent:
        out.append({"pair": [child_name, parent_name], "error": "object not found"})
        continue
    child_tree, child_verts = _tree(child, depsgraph)
    parent_tree, _ = _tree(parent, depsgraph)
    step = max(1, len(child_verts) // MAX_SAMPLE)
    best, best_at = None, None
    for co in child_verts[::step]:
        hit = parent_tree.find_nearest(co)
        if hit[3] is not None and (best is None or hit[3] < best):
            best, best_at = hit[3], co
    crossing = len(child_tree.overlap(parent_tree))
    verdict = "crossing" if crossing else ("contact" if best is not None and best <= TOL else "gap")
    out.append({
        "pair": [child_name, parent_name],
        "verdict": verdict,
        "crossing_face_pairs": crossing,
        "min_gap_m": None if best is None else round(best, 5),
        "closest_point": None if best_at is None else [round(c, 4) for c in best_at],
    })

result = {"contacts": out}
