# Import settings (Godot 4.7)

The Godot AI MCP (4.3.0) has no op for import options, and the guard keeps `.import` files away
from Write/Edit. The sanctioned route is `scripts/import_edit.py`, then a reimport through the MCP:

```
python <skill>/scripts/import_edit.py get assets/npc/npc.glb.import
python <skill>/scripts/import_edit.py set assets/npc/npc.glb.import --param materials/extract=2
mcp: filesystem_manage op=reimport params={"paths": ["res://assets/npc/npc.glb"]}
```

`set` rewrites only the lines it changes, refuses a `_subresources` value it cannot parse, and
bumps the source file's mtime: `reimport` and `scan` skip a source whose own mtime did not change,
so editing only the `.import` does nothing without that (g2 row 93). Option names below are from
`editor/import/3d/resource_importer_scene.cpp` and `modules/vorbis/resource_importer_ogg_vorbis.cpp`
at tag 4.7.2-stable.

## Recipes

| Need | Command |
|---|---|
| Music loop + beat grid (AudioStreamInteractive / Synchronized) | `--param loop=true --param bpm=96 --param beat_count=64 --param bar_beats=4` on the `.ogg.import` (also `loop_offset` in seconds) |
| Loop a clip of a glb | `--sub "animations::<clip>::settings/loop_mode=1"` (0 none, 1 linear, 2 ping-pong) |
| Save a clip to its own file | `--sub "animations::<clip>::save_to_file/enabled=true" --sub 'animations::<clip>::save_to_file/path="res://anim/walk.res"'` |
| Import a clip-only glb as an AnimationLibrary (shared library for many players) | `--importer animation_library` (Import As → Animation Library), then the clip loop modes as above |
| Extract materials to editable files | `--param materials/extract=1` (once) or `=2` (extract and overwrite on every reimport); `materials/extract_format` 0 `.tres`, 1 `.res`, 2 `.material`; `materials/extract_path` a folder |
| Use one existing material for a surface | `--sub "materials::<name>::use_external/enabled=true" --sub 'materials::<name>::use_external/path="res://materials/hair.tres"'` |
| No shadow from decals, water, glass, flames | `--sub "nodes::PATH:<node path>::mesh_instance/cast_shadow=0"` per node (0 off, 1 on, 2 double-sided, 3 shadows only). Node paths come from the imported scene tree; ask the modeler to name such nodes with a suffix (`_decal`, `_water`, `_glass`) so the list is mechanical. |
| Rule for every node by name | `--param 'import_script/path="res://tools/import/post_import.gd"'`: an `EditorScenePostImport` script (`_post_import(scene)`) that walks the tree and sets `cast_shadow`, materials or metadata by name suffix |
| Authored LOD chain (`<mesh>_LOD<n>`, asset-pipeline "LOD chain") | copy `scripts/kiln_lod_ranges.gd` to `res://tools/import/`, set `FOVY_DEG` to the game camera's FOV, then `--param 'import_script/path="res://tools/import/kiln_lod_ranges.gd"' --param meshes/generate_lods=false`: the levels become visibility ranges from their `kiln_lod_screen` extras (glTF extras arrive as the node's `extras` metadata; checked on 4.7.2). One import script per file: merge its logic into an existing one instead of replacing it |

## Facts that cost time in g2

- Textures that a glb embeds are extracted next to it once and not overwritten on reimport: after
  a re-export with new textures, copy the source PNGs over the extracted ones (or delete them)
  before reimporting (row 93).
- Nodes edited inside an instanced glb (material override, `visible`, `cast_shadow`) are not saved
  with the parent scene unless "editable children" is on, which the MCP cannot toggle. Put such
  per-node choices in the import options above (rows 29, 61, 106, 132).
- `filesystem_manage reimport` of a `.csv` translation reports success but leaves the
  `.translation` files as they were; run `scan` (row 120).
- In a run-once `@tool` script, call `EditorInterface.get_resource_filesystem().reimport_files()`
  directly. From `call_deferred` it printed 4184 "Do not use progress dialog while flushing the
  message queue" errors (row 107). Keep such a script only for what `import_edit.py` refuses
  (values such as `Vector3(...)` inside `_subresources`): attach it to a scratch node with an
  exported `run` flag through the MCP, set the flag, then remove the node.
- Changing the importer type (`--importer`) makes the editor write new `[remap]` paths on the
  reimport; commit the `.import` after the reimport, not before.
