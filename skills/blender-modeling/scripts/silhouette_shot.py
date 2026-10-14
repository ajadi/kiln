# Kiln review view — silhouette shot. Run through the Blender Lab MCP (execute_blender_code).
# Renders an orthographic, flat black-on-white silhouette (Workbench, no anti-aliasing) of the
# given objects or collection from one axis view, at a stated pixels-per-metre, and writes a
# sidecar JSON next to the PNG with everything a measurement needs (view, px/m, world point at the
# image centre, which world axis runs left-to-right). Restores every render, shading and
# visibility setting it touches. Measure the PNG with silhouette_measure.py (outside Blender).
#
# Why: review renders that did not record their camera were measured at 947 px/m while they were
# 568 px/m (g2 row 78); builder and reviewer used different metrics on different captures (row 88).

import bpy
import json
import math
import os
from mathutils import Euler, Vector

TARGETS = []                 # object names; [] = every mesh in COLLECTION
COLLECTION = "asset"
VIEW = "front"               # front | back | left | right
PX_PER_M = 1000.0            # 1000 px/m = 1 mm per pixel
CENTER = None                # world (x, y, z) at the image centre; None = centre of the targets
SIZE_M = None                # (width, height) of the frame in metres; None = targets + 5 %
OUT = "//.kiln/tmp/sil/front.png"   # '//' = next to the .blend

ROT = {"front": (90, 0, 0), "back": (90, 0, 180), "left": (90, 0, -90), "right": (90, 0, 90)}
# world axis that runs left -> right in the image, per view (Blender: front looks along +Y)
H_AXIS = {"front": (0, 1), "back": (0, -1), "left": (1, -1), "right": (1, 1)}  # (axis, sign)


def _targets():
    if TARGETS:
        return [bpy.data.objects[n] for n in TARGETS if n in bpy.data.objects]
    coll = bpy.data.collections.get(COLLECTION)
    objs = coll.all_objects if coll else bpy.context.scene.objects
    return [o for o in objs if o.type in {'MESH', 'CURVE'}]


objs = _targets()
if not objs:
    raise RuntimeError("no target objects")
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center = Vector(CENTER) if CENTER else (lo + hi) / 2
axis, sign = H_AXIS[VIEW]
if SIZE_M:
    fw, fh = SIZE_M
else:
    fw, fh = (hi[axis] - lo[axis]) * 1.05 + 0.02, (hi.z - lo.z) * 1.05 + 0.02
w, h = max(16, int(round(fw * PX_PER_M))), max(16, int(round(fh * PX_PER_M)))

sc = bpy.context.scene
sh = sc.display.shading
keep = dict(engine=sc.render.engine, rx=sc.render.resolution_x, ry=sc.render.resolution_y,
            pct=sc.render.resolution_percentage, fp=sc.render.filepath,
            aa=sc.display.render_aa, vt=sc.view_settings.view_transform, cam=sc.camera,
            film=sc.render.film_transparent)
ksh = (sh.light, sh.color_type, sh.show_cavity, sh.show_shadows, sh.show_object_outline,
       tuple(sh.single_color), sh.background_type, tuple(sh.background_color))
hidden = {o.name: o.hide_render for o in sc.objects if o.type in {'MESH', 'CURVE'}}
names = {o.name for o in objs}
cam = bpy.data.objects.new("kiln_sil_cam", bpy.data.cameras.new("kiln_sil_cam"))
sc.collection.objects.link(cam)
path = bpy.path.abspath(OUT)
try:
    for o in sc.objects:
        if o.type in {'MESH', 'CURVE'}:
            o.hide_render = o.name not in names
    cam.data.type = 'ORTHO'
    cam.data.sensor_fit = 'HORIZONTAL' if w >= h else 'VERTICAL'
    cam.data.ortho_scale = max(w, h) / PX_PER_M
    cam.rotation_euler = Euler([math.radians(a) for a in ROT[VIEW]], 'XYZ')
    fwd = cam.rotation_euler.to_matrix() @ Vector((0, 0, -1))
    cam.location = center - fwd * (max((hi - lo).length, 1.0) * 2 + 1)
    cam.data.clip_start, cam.data.clip_end = 0.01, max((hi - lo).length, 1.0) * 6 + 2
    sc.camera = cam
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sc.render.film_transparent = False
    sc.display.render_aa = 'OFF'
    sc.view_settings.view_transform = 'Standard'
    sh.light, sh.color_type = 'FLAT', 'SINGLE'
    sh.show_cavity = sh.show_shadows = sh.show_object_outline = False
    sh.single_color = (0, 0, 0)
    sh.background_type = 'VIEWPORT'
    sh.background_color = (1, 1, 1)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
finally:
    sc.render.engine = keep["engine"]
    sc.render.resolution_x, sc.render.resolution_y = keep["rx"], keep["ry"]
    sc.render.resolution_percentage = keep["pct"]
    sc.render.filepath = keep["fp"]
    sc.render.film_transparent = keep["film"]
    sc.display.render_aa = keep["aa"]
    sc.view_settings.view_transform = keep["vt"]
    sc.camera = keep["cam"]
    (sh.light, sh.color_type, sh.show_cavity, sh.show_shadows, sh.show_object_outline, col,
     sh.background_type, bg) = ksh
    sh.single_color, sh.background_color = col, bg
    for n, hr in hidden.items():
        if n in bpy.data.objects:
            bpy.data.objects[n].hide_render = hr
    data = cam.data
    bpy.data.objects.remove(cam)
    bpy.data.cameras.remove(data)

sidecar = {"format": "kiln-silhouette/1", "image": os.path.basename(path), "view": VIEW,
           "px_per_m": PX_PER_M, "width": w, "height": h,
           "center_world": [round(center[axis], 5), round(center.z, 5)],
           "h_axis": "xyz"[axis], "h_sign": sign, "targets": sorted(names)}
with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as fh:
    json.dump(sidecar, fh, indent=1)
result = {"png": path, **sidecar}
