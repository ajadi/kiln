# Kiln LOD shots — run through the Blender Lab MCP (execute_blender_code) after lod_build.py.
# For every LOD level i >= 1 renders LOD0 and LOD_i at the size where the level switches in
# (the object's bounding diameter covers kiln_lod_screen x SCREEN_H pixels), supersampled, from
# AZIMUTHS around the object at the game camera's ELEV_DEG (+ a top view with TOP), studio-lit
# with material colours on a transparent film: alpha is the silhouette, RGB the shading. Writes
# OUT/lod_shots.json for lod_check.py (outside Blender). Restores every setting it touches.

import bpy
import json
import math
import os
import re
from mathutils import Vector

COLLECTION = "asset"
OUT = "//.kiln/tmp/lod"          # '//' = next to the .blend
SCREEN_H = 1080
SUPERSAMPLE = 4
MAX_PX = 4096
AZIMUTHS = 8
ELEV_DEG = 15.0
TOP = False

LOD = re.compile(r"^(.*?)_LOD(\d+)$", re.I)


def _levels():
    coll = bpy.data.collections.get(COLLECTION)
    objs = coll.all_objects if coll else bpy.context.scene.objects
    out = {}
    for o in objs:
        m = LOD.match(o.name)
        if o.type == 'MESH' and m:
            out.setdefault(int(m.group(2)), []).append(o)
    return out


levels = _levels()
if len(levels) < 2:
    raise RuntimeError("no LOD levels: run lod_build.py first")
lod0 = levels[0]
pts = [o.matrix_world @ Vector(c) for o in lod0 for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, D = (lo + hi) / 2, (hi - lo).length
out_dir = bpy.path.abspath(OUT)
os.makedirs(out_dir, exist_ok=True)

sc = bpy.context.scene
sh = sc.display.shading
keep = dict(engine=sc.render.engine, rx=sc.render.resolution_x, ry=sc.render.resolution_y,
            pct=sc.render.resolution_percentage, fp=sc.render.filepath, aa=sc.display.render_aa,
            vt=sc.view_settings.view_transform, cam=sc.camera, film=sc.render.film_transparent)
ksh = (sh.light, sh.color_type, sh.show_cavity, sh.show_shadows, sh.show_object_outline)
hidden = {o.name: o.hide_render for o in sc.objects if o.type in {'MESH', 'CURVE'}}
cam = bpy.data.objects.new("kiln_lod_cam", bpy.data.cameras.new("kiln_lod_cam"))
sc.collection.objects.link(cam)
views = [(360.0 * k / AZIMUTHS, ELEV_DEG) for k in range(AZIMUTHS)] + ([(0.0, 89.0)] if TOP else [])
report = {"format": "kiln-lod-shots/1", "screen_h": SCREEN_H, "diameter_m": D, "levels": []}
try:
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.display.render_aa = 'OFF'
    sc.view_settings.view_transform = 'Standard'
    sh.light, sh.color_type = 'STUDIO', 'MATERIAL'
    sh.show_cavity = sh.show_shadows = sh.show_object_outline = False
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = D * 1.1
    cam.data.clip_start, cam.data.clip_end = 0.01, D * 8 + 2
    sc.camera = cam
    for level in sorted(k for k in levels if k > 0):
        screen = float(levels[level][0].get("kiln_lod_screen", 0.5))
        px = min(MAX_PX, max(64, int(round(screen * SCREEN_H * SUPERSAMPLE * 1.1))))
        sc.render.resolution_x = sc.render.resolution_y = px
        entry = {"level": level, "screen": screen, "px": px,
                 "px_per_game_px": px / (screen * SCREEN_H * 1.1), "views": []}
        for az, el in views:
            a, e = math.radians(az), math.radians(el)
            direction = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
            cam.location = center + direction * (D * 3 + 1)
            cam.rotation_euler = (-direction).to_track_quat('-Z', 'Y').to_euler()
            files = {}
            for which, objs in (("lod0", lod0), ("lod", levels[level])):
                names = {o.name for o in objs}
                for o in sc.objects:
                    if o.type in {'MESH', 'CURVE'}:
                        o.hide_render = o.name not in names
                name = f"lod{level}_{which}_az{int(round(az)):03d}_el{int(round(el)):02d}.png"
                sc.render.filepath = os.path.join(out_dir, name)
                bpy.ops.render.render(write_still=True)
                files[which] = name
            entry["views"].append({"azimuth": az, "elevation": el, **files})
        report["levels"].append(entry)
finally:
    sc.render.engine = keep["engine"]
    sc.render.resolution_x, sc.render.resolution_y = keep["rx"], keep["ry"]
    sc.render.resolution_percentage = keep["pct"]
    sc.render.filepath = keep["fp"]
    sc.render.film_transparent = keep["film"]
    sc.display.render_aa = keep["aa"]
    sc.view_settings.view_transform = keep["vt"]
    sc.camera = keep["cam"]
    sh.light, sh.color_type, sh.show_cavity, sh.show_shadows, sh.show_object_outline = ksh
    for n, hr in hidden.items():
        if n in bpy.data.objects:
            bpy.data.objects[n].hide_render = hr
    data = cam.data
    bpy.data.objects.remove(cam)
    bpy.data.cameras.remove(data)

with open(os.path.join(out_dir, "lod_shots.json"), "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=1)
result = {"out": out_dir, "levels": [{k: v for k, v in lv.items() if k != "views"}
                                     for lv in report["levels"]],
          "next": "python lod_check.py <asset.glb> --shots " + out_dir}
