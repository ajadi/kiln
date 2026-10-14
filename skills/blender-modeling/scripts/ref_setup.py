# Kiln reference setup — run through the Blender Lab MCP (execute_blender_code).
# Places cropped reference views as image empties in a "_refs" collection (hidden from renders,
# never exported), scaled so the subject's real height matches HEIGHT_M and its feet/base sit on
# z = 0. Each image shows only in its matching orthographic view, behind the geometry, so
# modeling over it in front/side ortho views pins proportions.
#
# Crop each view out of the reference sheet first (scripts/crop_ref.py, run with normal Python),
# so that each image is tightly framed: subject's base on the bottom edge, top on the top edge.

import bpy
from math import radians

HEIGHT_M = 3.0      # real height of the subject (from the design spec or the sheet's scale)
VIEWS = {           # view -> absolute path of the cropped image
    "front": r"C:\path\to\.kiln\tmp\refs\front.png",
    # "right": r"...\right.png",
    # "back": r"...\back.png",
    # "top": r"...\top.png",
}
OPACITY = 0.45

ROT = {"front": (90, 0, 0), "back": (90, 0, 180), "right": (90, 0, 90), "left": (90, 0, -90),
       "top": (0, 0, 0)}

coll = bpy.data.collections.get("_refs")
if coll is None:
    coll = bpy.data.collections.new("_refs")
    bpy.context.scene.collection.children.link(coll)
coll.hide_render = True

made = []
for view, path in VIEWS.items():
    img = bpy.data.images.load(path, check_existing=True)
    w, h = img.size
    name = f"ref_{view}"
    obj = bpy.data.objects.get(name) or bpy.data.objects.new(name, None)
    if obj.name not in coll.objects:
        coll.objects.link(obj)
    obj.empty_display_type = 'IMAGE'
    obj.data = img
    # Image empties are sized by their larger side; scale so the image height == HEIGHT_M.
    obj.empty_display_size = HEIGHT_M * max(w, h) / h
    obj.empty_image_offset = (-0.5, 0.0) if view != "top" else (-0.5, -0.5)
    obj.rotation_euler = [radians(a) for a in ROT[view]]
    obj.location = (0.0, 0.0, 0.0)
    obj.empty_image_depth = 'BACK'
    obj.empty_image_side = 'FRONT'
    obj.use_empty_image_alpha = True
    obj.color[3] = OPACITY
    obj.show_empty_image_orthographic = True
    obj.show_empty_image_perspective = False
    obj.show_empty_image_only_axis_aligned = True
    obj.hide_select = True
    made.append({"name": name, "pixels": [w, h]})

result = {"refs": made, "height_m": HEIGHT_M}
