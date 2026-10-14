# Kiln parts kit — helper functions for part-by-part modeling through the Blender Lab MCP.
# Prepend this file's content to an execute_blender_code call (or to the asset's parts script)
# and use the helpers; they compute positions from measured geometry instead of guesses.

import bpy
from mathutils import Vector


def bbox_world(obj):
    """World-space (min, max, center, size) of an object's evaluated bounding box."""
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi, (lo + hi) / 2, hi - lo


def describe(objs):
    """Numbers for critique: per-part world bbox, centre and size in metres."""
    out = {}
    for o in objs:
        lo, hi, c, s = bbox_world(o)
        out[o.name] = {"min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi],
                       "center": [round(v, 4) for v in c], "size": [round(v, 4) for v in s]}
    return out


_SIDES = {"+X": (0, 1), "-X": (0, -1), "+Y": (1, 1), "-Y": (1, -1), "+Z": (2, 1), "-Z": (2, -1)}


def place_on(child, parent, side="+Z", inset=0.0, align=(0.5, 0.5)):
    """Seat `child` against the `side` face of `parent`'s bounding box.

    inset > 0 pushes the child into the parent by that many metres (for inserted parts);
    align gives the child's position across the face as fractions of the parent's extent
    on the two other axes (0.5 = centred). Moves the child only (bounding-box contact) and
    returns the translation applied. Curved or angled faces need contact_check.py afterwards.
    """
    bpy.context.view_layer.update()
    axis, sign = _SIDES[side]
    plo, phi, _, psize = bbox_world(parent)
    clo, chi, ccen, _ = bbox_world(child)
    delta = Vector((0.0, 0.0, 0.0))
    face = phi[axis] if sign > 0 else plo[axis]
    child_face = clo[axis] if sign > 0 else chi[axis]
    delta[axis] = face - child_face - sign * inset
    others = [i for i in range(3) if i != axis]
    for i, frac in zip(others, align):
        target = plo[i] + psize[i] * frac
        delta[i] = target - ccen[i]
    mw = child.matrix_world.copy()
    mw.translation += delta
    child.matrix_world = mw
    bpy.context.view_layer.update()
    return [round(v, 4) for v in delta]


def bevel_and_weight(obj, width=0.005, segments=2, angle_deg=30.0):
    """Hard-surface edge treatment: angle-limited bevel with hardened normals + weighted normals."""
    from math import radians
    bev = obj.modifiers.get("kiln_bevel") or obj.modifiers.new("kiln_bevel", 'BEVEL')
    bev.width = width
    bev.segments = segments
    bev.limit_method = 'ANGLE'
    bev.angle_limit = radians(angle_deg)
    bev.harden_normals = True
    bev.miter_outer = 'MITER_ARC'
    wn = obj.modifiers.get("kiln_wnormal") or obj.modifiers.new("kiln_wnormal", 'WEIGHTED_NORMAL')
    wn.keep_sharp = True
    if hasattr(obj.data, "shade_smooth"):   # Blender 4.1+
        obj.data.shade_smooth()
    else:
        for poly in obj.data.polygons:
            poly.use_smooth = True
    return [m.name for m in obj.modifiers]


def keep_previous(obj, collection="_wip_prev"):
    """Store a hidden copy of a part before reworking it, so a worse attempt can be reverted."""
    coll = bpy.data.collections.get(collection)
    if coll is None:
        coll = bpy.data.collections.new(collection)
        bpy.context.scene.collection.children.link(coll)
    coll.hide_render = True
    coll.hide_viewport = True
    old = bpy.data.objects.get(obj.name + "__prev")
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.name = obj.name + "__prev"
    coll.objects.link(copy)
    return copy.name
