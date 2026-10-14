---
name: sprites
description: Make 2D game art from an image or a description, without having to make a game - a character or prop sprite sheet with animations and directions (pre-rendered from a Blender model, or drawn), or a 2D map and its tileset cut from a reference image - delivered as PNG + Aseprite-compatible JSON or a Tiled map, with checks and licences. Works in asset mode (kind=assets) and in game projects. Use when the user asks for sprites, a sprite sheet, a tileset or a 2D map.
disable-model-invocation: true
argument-hint: "<image paths and/or what to make>"
---

# /kiln:sprites

Knowledge: `art-2d` (methods, palettes, frame counts, sheets), `image-to-model` and
`animation` for the pre-rendered route, `procgen` for generated maps.

1. **What is wanted, one question.** Sprite sheet or map. Sheet: which animations (idle, walk,
   run, attack, hit, death ...), directions (side; top-down 4 or 8; isometric 8), frame size
   (16 / 32 / 48 / 64 px; ➡️ from the style), pixel art or smooth. Map: tile size (➡️ measured
   from the reference's repeating pattern), whether to cut the reference itself or make new
   maps in its style. Images into `ref/<asset>/` with `ref/manifest.csv` rows.
2. **Task.** `tasks/TASK-NNN.md` (`type: animation` for a sheet, `type: art` for a map; role
   `artist-2d`, or `modeler` + `animator` for a pre-rendered sheet), backlog line, gates table
   from `pipeline.py gates --suggest`.
3. **Sheet routes** (art-2d §1 picks by style):
   - **Pre-rendered from 3D** (default when the user gives one image of a character or prop and
     wants several directions): the model comes first (the `/kiln:model` steps), rigged and
     animated (`kiln:animator`), then rendered in Blender through the MCP with an orthographic
     camera per direction (45° steps; side view 0°, top-down 90°, isometric 30° or true
     isometric 35.264° elevation), at the frame counts of art-2d §5. Pixel art: render at 2-4 ×
     the target size, downscale with nearest neighbour, reduce to the palette, add the 1 px
     outline if the style has one.
   - **Drawn**: frame by frame per art-2d §5; image models only when `model_generators` allows
     it and the model's licence allows commercial use (art-2d, licence gate).
   - **Image-to-video, then frames**: last resort (open video models need ≥ 24 GB, the subject
     drifts between frames, every frame needs cleanup); only with the user's yes.
   Then `sheet.py pack` (Aseprite-compatible JSON, tags, durations, pivot at the feet),
   `sheet.py check`, `sprite_qa.py` (palette, mixels, silhouettes, contrast, clusters).
4. **Map route.** Reference cut: `tiles.py extract <map.png> --tile <px> --flips [--tolerance
   4-8 for JPEG or resized images] --out out/<asset>/` → `tileset.png` + `map.tmj` (Tiled
   JSON; opens in Tiled 1.12, imports into Godot, Unity and LDtk). Report the reuse number: a
   high unique count means the reference is off the tile grid (crop or rescale first) or
   painted, not tiled. New maps in the reference's style: the tileset above plus adjacency, then
   `procgen` (Wave Function Collapse, overlapping N=3 from the sample, or tiled with rules),
   validated over many seeds.
5. **Gates.** `kiln:art-director` against the reference and the style; `kiln:verifier` closes.
   Numbers in the task file: frames per animation, canvas, palette size, sheet size; for a map,
   unique tiles, reuse, map size.
6. **Deliver** into `out/<asset>/` (asset mode) or the task's paths: the sheet PNG + JSON (or
   tileset + `.tmj`), a preview GIF per animation, `README.md` (frame size, directions,
   animations with frame counts and fps, pivot, palette, how it was made, model and licence if
   generated), the licence row in `production/LICENSES.md`. In a game project add it to the
   engine (`sheet.py godot` prints the editor calls).
7. **Report** in the user's language with a preview and the numbers.
