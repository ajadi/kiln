# Kiln mesh QA — run through the Blender Lab MCP (execute_blender_code).
# Paste this file's content, then set TARGETS (object names, or [] for every mesh in the
# collection named COLLECTION). The report is returned in `result`.
#
# Reports per object: triangles, n-gons, non-manifold / boundary / wire edges, loose verts,
# zero-area faces, duplicate verts, inside-out normals (closed meshes), unapplied or negative
# scale, origin height vs. lowest point, dimensions in metres; and for the set as a whole:
# connected groups of touching parts (anything outside the main group is floating), pairs
# whose faces cross, back faces visible from 8 azimuths (holes, flipped normals) and daylight:
# background enclosed by the front / side / back silhouettes of the joined set (a gap between a
# garment and a boot, a strap off the chest), with its height range. Ray casting, no render.

import bpy
import bmesh
import math
from mathutils.bvhtree import BVHTree

TARGETS = []               # e.g. ["part_torso", "part_leg_l_upper"]
COLLECTION = "asset"       # used when TARGETS is empty
CONTACT_TOL = 0.002        # metres: a part farther than this from every other part is floating
MAX_SAMPLE = 4000          # vertices sampled per object for distance checks


def _objects():
    if TARGETS:
        return [bpy.data.objects[n] for n in TARGETS if n in bpy.data.objects]
    coll = bpy.data.collections.get(COLLECTION)
    objs = coll.all_objects if coll else bpy.context.scene.objects
    return [o for o in objs if o.type == 'MESH' and not o.name.endswith(("-colonly", "-convcolonly"))]


def _world_bmesh(obj, depsgraph):
    bm = bmesh.new()
    bm.from_object(obj, depsgraph)          # evaluated: modifiers applied
    bm.transform(obj.matrix_world)
    bm.normal_update()
    return bm


depsgraph = bpy.context.evaluated_depsgraph_get()
report, trees, samples = {}, {}, {}
for obj in _objects():
    bm = _world_bmesh(obj, depsgraph)
    faces = list(bm.faces)
    closed = all(e.is_manifold for e in bm.edges) and len(faces) > 0
    doubles = bmesh.ops.find_doubles(bm, verts=bm.verts, dist=1e-5)["targetmap"]
    zs = [v.co.z for v in bm.verts] or [0.0]
    info = {
        "tris": sum(len(f.verts) - 2 for f in faces),
        "ngons": sum(1 for f in faces if len(f.verts) > 4),
        "non_manifold_edges": sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary),
        "boundary_edges": sum(1 for e in bm.edges if e.is_boundary),
        "wire_edges": sum(1 for e in bm.edges if e.is_wire),
        "loose_verts": sum(1 for v in bm.verts if not v.link_edges),
        "zero_area_faces": sum(1 for f in faces if f.calc_area() < 1e-8),
        "duplicate_verts": len(doubles),
        "inside_out": bool(closed and bm.calc_volume(signed=True) < 0),
        "scale": [round(s, 4) for s in obj.scale],
        "unapplied_scale": any(abs(s - 1.0) > 1e-4 for s in obj.scale),
        "negative_scale": any(s < 0 for s in obj.scale),
        "dimensions_m": [round(d, 4) for d in obj.dimensions],
        "bbox_world_min": [round(min(v.co[i] for v in bm.verts), 4) for i in range(3)]
        if bm.verts else None,
        "bbox_world_max": [round(max(v.co[i] for v in bm.verts), 4) for i in range(3)]
        if bm.verts else None,
        "origin_above_lowest_point_m": round(obj.matrix_world.translation.z - min(zs), 4),
        "materials": [s.material.name if s.material else None for s in obj.material_slots],
        "uv_layers": [uv.name for uv in obj.data.uv_layers],
    }
    report[obj.name] = info
    verts = [v.co.copy() for v in bm.verts]
    polys = [[v.index for v in f.verts] for f in faces]
    if polys:
        trees[obj.name] = BVHTree.FromPolygons(verts, polys)
        step = max(1, len(verts) // MAX_SAMPLE)
        samples[obj.name] = verts[::step]
    bm.free()

def _bbox(points):
    xs, ys, zs = zip(*((p.x, p.y, p.z) for p in points))
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def _near(box_a, box_b, tol):
    (a0, a1), (b0, b1) = box_a, box_b
    return all(a0[i] - tol <= b1[i] and b0[i] - tol <= a1[i] for i in range(3))


def _touching(a, b):
    for co in samples[a]:
        hit = trees[b].find_nearest(co)
        if hit[3] is not None and hit[3] <= CONTACT_TOL:
            return True
    return False


names = list(trees)
boxes = {n: _bbox(samples[n]) for n in names if samples[n]}
parent = {n: n for n in names}


def _root(n):
    while parent[n] != n:
        parent[n] = parent[parent[n]]
        n = parent[n]
    return n


intersecting = []
for i, a in enumerate(names):
    for b in names[i + 1:]:
        if a not in boxes or b not in boxes or not _near(boxes[a], boxes[b], CONTACT_TOL):
            continue
        pairs = len(trees[a].overlap(trees[b]))
        if pairs:
            intersecting.append([a, b, pairs])
        if pairs or _touching(a, b) or _touching(b, a):
            parent[_root(a)] = _root(b)

groups = {}
for n in names:
    groups.setdefault(_root(n), []).append(n)
groups = sorted(groups.values(), key=lambda g: -sum(report[n]["tris"] for n in g))

# ---------------------------------------------------------------- views by ray casting
# Work on the joined set (one BVH of every target), so problems inside one joined mesh show:
# back faces visible from outside (holes, flipped normals; g2: a crescent on a statue's neck seen
# in one quarter view only) and daylight - background enclosed by the silhouette (g2: trouser
# legs ending 10 cm above the boots, a strap standing 1 cm off the chest).
from mathutils import Vector

RAY_RES = 200              # rays across the larger extent of each view
BACKFACE_AZIMUTHS = 8      # views around Z, every 45 degrees
MIN_HOLE_PX = 4            # enclosed background smaller than this is ignored (aliasing)

all_verts, all_polys = [], []
for obj in _objects():
    bm = _world_bmesh(obj, depsgraph)
    base = len(all_verts)
    all_verts += [v.co.copy() for v in bm.verts]
    all_polys += [[base + v.index for v in f.verts] for f in bm.faces]
    bm.free()


def _view_grid(direction):
    """(origins, step, u, v) of an orthographic ray grid looking along `direction`."""
    d = direction.normalized()
    up = Vector((0, 0, 1)) if abs(d.z) < 0.99 else Vector((0, 1, 0))
    u = d.cross(up).normalized()
    v = u.cross(d).normalized()
    pu = [p.dot(u) for p in all_verts]
    pv = [p.dot(v) for p in all_verts]
    pd = [p.dot(d) for p in all_verts]
    u0, u1, v0, v1 = min(pu), max(pu), min(pv), max(pv)
    step = max(u1 - u0, v1 - v0) / RAY_RES
    u0, u1, v0, v1 = u0 - 3 * step, u1 + 3 * step, v0 - 3 * step, v1 + 3 * step
    nu, nv = int((u1 - u0) / step) + 1, int((v1 - v0) / step) + 1
    back = min(pd) - 1.0
    return d, u, v, u0, v0, step, nu, nv, back


def _cast(tree, direction):
    d, u, v, u0, v0, step, nu, nv, back = _view_grid(direction)
    hits = []
    for j in range(nv):
        row = []
        for i in range(nu):
            o = u * (u0 + i * step) + v * (v0 + j * step) + d * back
            loc, normal, _idx, _dist = tree.ray_cast(o, d)
            row.append(None if loc is None else (loc, normal.dot(d) > 1e-6))
        hits.append(row)
    return hits, (d, u, v, u0, v0, step)


backfaces, daylight = [], []
if all_polys:
    joined = BVHTree.FromPolygons(all_verts, all_polys)
    for k in range(BACKFACE_AZIMUTHS):
        az = 2 * math.pi * k / BACKFACE_AZIMUTHS
        hits, _ = _cast(joined, Vector((math.sin(az), math.cos(az), 0)))
        nv, nu = len(hits), len(hits[0])
        # rays grazing the silhouette edge can report the far face: count only pixels whose
        # four neighbours also hit the surface
        flagged = [hits[j][i][0] for j in range(1, nv - 1) for i in range(1, nu - 1)
                   if hits[j][i] and hits[j][i][1] and all(
                       hits[j + dj][i + di] for dj, di in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
        if flagged:
            backfaces.append({"azimuth_deg": round(math.degrees(az)), "pixels": len(flagged),
                              "sample_world": [round(c, 3) for c in flagged[0]]})
    for name, direction in (("front", Vector((0, 1, 0))), ("side", Vector((-1, 0, 0))),
                            ("back", Vector((0, -1, 0)))):
        hits, (d, u, v, u0, v0, step) = _cast(joined, direction)
        nv, nu = len(hits), len(hits[0])
        outside = [[False] * nu for _ in range(nv)]
        stack = [(j, i) for j in range(nv) for i in (0, nu - 1)] + \
                [(j, i) for i in range(nu) for j in (0, nv - 1)]
        while stack:
            j, i = stack.pop()
            if outside[j][i] or hits[j][i] is not None:
                continue
            outside[j][i] = True
            for nj, ni in ((j + 1, i), (j - 1, i), (j, i + 1), (j, i - 1)):
                if 0 <= nj < nv and 0 <= ni < nu and not outside[nj][ni]:
                    stack.append((nj, ni))
        seen = [[False] * nu for _ in range(nv)]
        for j in range(nv):
            for i in range(nu):
                if hits[j][i] is not None or outside[j][i] or seen[j][i]:
                    continue
                comp, stack = [], [(j, i)]
                seen[j][i] = True
                while stack:
                    cj, ci = stack.pop()
                    comp.append((cj, ci))
                    for nj, ni in ((cj + 1, ci), (cj - 1, ci), (cj, ci + 1), (cj, ci - 1)):
                        if 0 <= nj < nv and 0 <= ni < nu and not seen[nj][ni] and \
                                hits[nj][ni] is None and not outside[nj][ni]:
                            seen[nj][ni] = True
                            stack.append((nj, ni))
                if len(comp) < MIN_HOLE_PX:
                    continue
                vs = [v0 + cj * step for cj, _ in comp]
                us = [u0 + ci * step for _, ci in comp]
                daylight.append({"view": name, "pixels": len(comp),
                                 "z_range_m": [round(min(vs) - step / 2, 3),
                                               round(max(vs) + step / 2, 3)],
                                 "across_range_m": [round(min(us), 3), round(max(us), 3)],
                                 "px_size_m": round(step, 4)})

set_problems = []
if backfaces:
    set_problems.append(f"backfaces visible from {len(backfaces)} of {BACKFACE_AZIMUTHS} "
                        "azimuths (a hole in the surface or flipped normals): look at "
                        f"{backfaces[0]['sample_world']}")
if daylight:
    set_problems.append(f"{len(daylight)} enclosed gaps in the silhouettes (daylight between "
                        f"parts): {daylight[0]['view']} view, z {daylight[0]['z_range_m']}")

result = {
    "objects": report,
    "backfaces": {"views_with_backfaces": backfaces, "azimuths": BACKFACE_AZIMUTHS},
    # enclosed background in front / side / back silhouettes; intended openings (a ring, a
    # handle) show here too - judge each hole by its place
    "daylight": {"holes": daylight},
    "set_problems": set_problems,
    # connected groups of touching parts; everything after the first group is detached from
    # the main body (floating) unless it is meant to be a separate asset
    "connected_groups": groups,
    "floating_parts": [n for g in groups[1:] for n in g],
    # [a, b, crossing face pairs]: flush contact can register a few pairs; many pairs mean the
    # parts pass through each other — check close-up, acceptable only for deliberate inserts
    "crossing_pairs": intersecting,
    "problems": sorted({
        name for name, i in report.items()
        if i["non_manifold_edges"] or i["loose_verts"] or i["zero_area_faces"]
        or i["duplicate_verts"] or i["inside_out"] or i["unapplied_scale"] or i["negative_scale"]
    }),
}
