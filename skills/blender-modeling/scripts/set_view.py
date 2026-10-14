# Kiln review view — run through the Blender Lab MCP (execute_blender_code), then take
# get_screenshot_of_area_as_image(area_ui_type="VIEW_3D"). Changes only the viewport (no cameras
# or objects are added), so it is safe to use between modeling steps.
#
# VIEW: front | back | left | right | top | bottom | iso_front_right | iso_back_left
# MODE: "shape"    — solid, studio light, cavity on: reads form and bevels
#       "parts"    — solid, random colour per object: reads part split and gaps
#       "wire"     — solid + wireframe overlay: reads topology density
#       "normals"  — face orientation overlay: red faces are back faces (flipped normals)
#       "material" — material preview
# FRAME: object names to frame ([] = everything visible); ORTHO: orthographic for side views.

import bpy
from math import radians
from mathutils import Euler, Vector

VIEW = "front"
MODE = "shape"
FRAME = []
ORTHO = True
SHOW_REFS = True     # show reference image empties (they only appear in matching ortho views)

ROT = {
    "front": (90, 0, 0), "back": (90, 0, 180), "right": (90, 0, 90), "left": (90, 0, -90),
    "top": (0, 0, 0), "bottom": (180, 0, 0),
    "iso_front_right": (65, 0, 35), "iso_back_left": (65, 0, 215),
}

area = space = None
for window in bpy.context.window_manager.windows:
    for a in window.screen.areas:
        if a.type == 'VIEW_3D':
            area, space = a, a.spaces.active
            break
    if area:
        break
if area is None:
    raise RuntimeError("No 3D viewport is open in Blender")

objs = [bpy.data.objects[n] for n in FRAME if n in bpy.data.objects] or \
    [o for o in bpy.context.view_layer.objects if o.type in {'MESH', 'CURVE'} and o.visible_get()]
points = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
if points:
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    center, size = (lo + hi) / 2, max((hi - lo).length, 0.1)
else:
    center, size = Vector((0, 0, 0)), 2.0

r3d = space.region_3d
r3d.view_rotation = Euler([radians(a) for a in ROT[VIEW]], 'XYZ').to_quaternion()
r3d.view_location = center
r3d.view_distance = size * 1.25
r3d.view_perspective = 'ORTHO' if ORTHO and not VIEW.startswith("iso") else 'PERSP'

# Normalised screenshots: nothing selected, overlays only where the mode needs them.
for o in bpy.context.view_layer.objects:
    if o.select_get():
        o.select_set(False)
shading, overlay = space.shading, space.overlay
# reference empties are overlay elements and only show in axis-aligned ortho views
overlay.show_overlays = MODE in {"wire", "normals"} or (SHOW_REFS and not VIEW.startswith("iso"))
shading.type = 'MATERIAL' if MODE == "material" else 'SOLID'
if shading.type == 'SOLID':
    shading.light = 'STUDIO'
    shading.color_type = 'RANDOM' if MODE == "parts" else 'MATERIAL'
    shading.show_cavity = MODE in {"shape", "parts"}
    shading.cavity_type = 'BOTH'
overlay.show_wireframes = MODE == "wire"
overlay.show_face_orientation = MODE == "normals"
space.show_object_viewport_empty = SHOW_REFS
area.tag_redraw()

active = bpy.context.view_layer.objects.active
result = {
    # camera pose in words for the critique: which side is seen, from how far
    "view": VIEW, "mode": MODE, "orthographic": r3d.view_perspective == 'ORTHO',
    "rotation_deg": ROT[VIEW], "center": [round(v, 3) for v in center],
    "view_distance_m": round(r3d.view_distance, 3), "subject_size_m": round(size, 3),
    "framed": [o.name for o in objs][:20],
    "warning": None if not active or active.mode == 'OBJECT'
    else f"{active.name} is in {active.mode} mode; switch to Object mode for review shots",
}
