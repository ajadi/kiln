# Sprite sheets

Script: `${extensionPath}${/}skills${/}art-2d/scripts/sheet.py` — `pack` (frames → sheet + Aseprite json-array data),
`check` (validate any Aseprite / TexturePacker / sheet.py data file), `godot` (the Godot AI MCP
calls that build the animation in the open editor). The script prepares files only; nodes,
resources and clips are created in the editor through the MCP (scene_first).

## 1. Grid or packed

| | grid | packed |
|---|---|---|
| layout | uniform cells, one row per tag (sheet.py) | MaxRects best-short-side-fit (Jylänki 2010) |
| engine use | Sprite2D `hframes`/`vframes` + `frame`; SpriteFrames "Add frames from a Sprite Sheet"; Unity Grid By Cell Size/Count | needs the data file: regions per frame (Sprite2D `region_rect`, AtlasTexture, Unity sprite rects) |
| waste | large when frame sizes differ | small; TexturePacker calls MaxRects "currently the best packing algorithm for rectangles" |
| use for | pixel-art characters with one canvas per animation, hand-made sheets | many frames, trimmed frames, VFX, UI atlases |

No rotation: Godot regions and AtlasTexture cannot rotate, Aseprite always writes
`rotated: false`; turn rotation off in TexturePacker / Unity Sprite Atlas for these sheets.
`pack --layout grid --padding 0 --extrude 0` (no `--trim`) is hframes-compatible
(`meta.kiln.hframes_compatible`).

## 2. Bleeding: padding and extrude

- Linear filtering, mipmaps, scaling and sub-pixel positions sample texels outside the frame.
  Padding = transparent gap between frames; extrude = the frame's edge pixels repeated outward
  (size unchanged). TexturePacker recommends shape padding ≥ 2 for OpenGL; Unity Sprite Atlas
  padding defaults to 4; Aseprite `--shape-padding`, `--border-padding`, `--inner-padding`,
  `--extrude`.
- Gate (`sheet.py check`): smallest gap between frame rects ≥ padding + 2 × extrude, and the
  extrude ring equals the edge pixels.
- Pixel art drawn with nearest filtering, no mipmaps, at integer positions does not bleed:
  padding 1, extrude 0–1 is enough. Tiles still need extrude 1 (seams at fractional camera speeds,
  art-2d §4).
- Godot can also clip to the region: Sprite2D `region_filter_clip_enabled`, AtlasTexture
  `filter_clip`.

## 3. Trim and pivots

- Trim drops transparent borders. `spriteSourceSize` records where the crop sat inside the
  original canvas, `sourceSize` is the canvas. A pivot is defined on the canvas, so trimming never
  moves it — if the engine setup uses these fields.
- sheet.py writes a per-frame `pivot` normalised to `sourceSize` (TexturePacker's field; default
  `bottom` = feet, art-2d §5). Aseprite stores pivots only on slices (`meta.slices[].keys[].pivot`).
- Godot, Sprite2D + AnimationPlayer: `centered = false`, `offset = (sss.x − pivot.x,
  sss.y − pivot.y)` per frame (an `offset` track when it varies). Integer offsets keep pixel art
  on the grid; `centered = true` puts odd-sized frames on half pixels.
- Godot, AnimatedSprite2D: AtlasTexture `margin = (sss.x, sss.y, W − w, H − h)` restores the
  canvas size (the drawn texture becomes W × H with the crop at its old place — how the
  TexturePacker importer handles trimmed sprites), so one node `offset = −pivot` serves all frames.
- Unity: a pivot per sprite in the Sprite Editor (Custom Pivot), or from the importer.
- Keep one canvas size per animation; `check` warns when it changes inside a tag.

## 4. Texture size and power of two

- Godot: "Using power-of-two texture sizes is recommended, but is not required"; mobile and web
  "usually can't display textures larger than 4096×4096". Godot `Image` caps a texture at
  16384² pixels (`MAX_PIXELS`). Desktop D3D11-class GPUs handle 16384; OpenGL ES 3.0 / WebGL 2
  only guarantee 2048 (spec minimum `MAX_TEXTURE_SIZE`).
- `--max-size` defaults to 4096 in `pack` and `check`; raise it only for desktop-only projects.
- POT matters only for some compressed formats or engines that compress externally
  (TexturePacker: the engine "may require textures to have power-of-two sizes"); use `--pot` only
  when the target needs it. Pixel art stays uncompressed (Lossless / Compression None).

## 5. Pixel-art import

- Godot 4: filtering is no longer an import option — "texture filter and repeat modes are set in
  the CanvasItem properties in 2D (with a project setting acting as a default)": node
  `texture_filter = 1` (TEXTURE_FILTER_NEAREST) or the project default Nearest (art-2d §7). 2D
  imports default to Lossless and no mipmaps; leave them.
- Unity: Texture Type Sprite, Sprite Mode Multiple, Filter Mode Point (no filter), Compression
  None, Max Size ≥ the sheet's longest side (otherwise Unity downsizes it and the art blurs),
  Pixels Per Unit = tile size.

## 6. Godot setups (`sheet.py godot --setup player|frames`)

| | Sprite2D + AnimationPlayer (`player`, default) | AnimatedSprite2D + SpriteFrames (`frames`) |
|---|---|---|
| data | `frame` track (grid sheet with hframes/vframes) or `region_rect` (+ `offset`) tracks | AtlasTexture per frame, SpriteFrames animations: FPS, loop, relative frame duration |
| timing | key times from the ms durations; clip length = sum | absolute duration = relative / (fps × speed); fps = 1000 / most common duration |
| hitboxes, sounds, effects | keyed on the same clip — required for attacks (art-2d §5) | separate timers or signals; not in sync by construction |
| through Godot AI 4.3.0 | fully: `node_create`, `node_set_property`, `animation_create`, `animation_manage add_property_track` (interpolation `nearest` = hold each key until the next, Godot source) | AtlasTextures and an empty SpriteFrames via `resource_manage create`; **no op adds frames** (`resource_manage` passes SpriteFrames' internal `animations` array through without loading textures) — the user fills the SpriteFrames panel from the printed values, the agent verifies by game eval |

- `godot` runs `check` first and refuses a failing sheet. It unrolls `pingpong` (0..n, n−1..1)
  and `repeat` > 1 into explicit frames, so playback matches Aseprite on every 4.x version
  (the 4.7 docs also list a SpriteFrames `LOOP_PINGPONG`).
- Godot's own SpriteFrames dialog "Add frames from a Sprite Sheet" slices grids only (H × V
  cells); packed or trimmed sheets need regions.
- Never hand-write `.tres`/`.tscn` for frames; editor-created resources keep UIDs and import data.
- Import plugins (extra integrations, need the user's approval): CodeAndWeb TexturePacker
  Importer (`.tpsheet` → AtlasTexture per sprite with trim margins, Godot 4.0+).

## 7. Unity and Unreal

- Unity Sprite Editor → Slice: Automatic (by transparency), Grid By Cell Size, Grid By Cell Count
  (with Offset and Padding for gaps), Isometric Grid. Packed sheets need their rects from the data
  file (TexturePacker's Unity importer, or the 2D Aseprite Importer package for `.aseprite` files
  — UNVERIFIED which Unity versions).
- Unity Sprite Atlas packs separate sprites at build time: Allow Rotation and Tight Packing are on
  by default (turn rotation off for UI), padding default 4. Animation clips key
  `SpriteRenderer.sprite`; sample rate = fps.
- Unreal Paper2D imports JSON sprite sheets (TexturePacker, Flash CS6) into a texture, sprites
  and a flipbook; flipbook keys hold a sprite for N frames at the flipbook's Frames Per Second.
  Kiln recommends another engine for 2D (art-2d §7).

## 8. Tool compatibility

| Tool (licence) | Export | Data file | Use with sheet.py |
|---|---|---|---|
| Aseprite (proprietary) | `--sheet-type horizontal\|vertical\|rows\|columns\|packed`, `--trim`, `--extrude`, `--shape-padding`, `--merge-duplicates`, `--split-tags` | `--format json-hash` (default) or `json-array`, `--list-tags`: frames {filename, frame, rotated, trimmed, spriteSourceSize, sourceSize, duration ms}; meta {image, size, scale, frameTags {name, from, to, direction forward\|reverse\|pingpong\|pingpong_reverse, repeat (string, only when > 0)}}. With `--extrude` the frame rect is the inner rect | `check`, `godot` directly (pass `--padding/--extrude` to `check`: Aseprite does not record them) |
| LibreSprite (GPL-2.0, Aseprite 1.1 fork) | same CLI, no `--extrude` | json-hash/array, frameTags without `repeat` | `check`, `godot` directly |
| Pixelorama (MIT) | spritesheet PNG by rows/columns | optional JSON is its project serialisation, not a sheet format | export frames as PNGs and `pack`, or slice a grid with hframes |
| TexturePacker (proprietary) | MaxRects, padding, extrude, trim / crop, POT / any size, rotation | JSON Array / Hash with the same frame fields + optional `pivot` | `check`, `godot` (rotation off) |
| sheet.py | grid / packed, padding, extrude, trim, dedupe | Aseprite json-array + `pivot` + `meta.kiln` (layout, padding, extrude, cell) | — |

## 9. Gates

| Check | Gate |
|---|---|
| `sheet.py check <data.json>` | 0 overlaps; gap ≥ padding + 2 × extrude; extrude ring intact; 0 rotated frames; unique tag names; valid ranges; durations > 0 ms; size ≤ `--max-size` |
| `sprite_qa.py frames` on the source frames | one canvas per animation, baseline within 1 px for grounded cycles |
| in the editor | every clip plays (`animation_manage play` + screenshot); feet stay on one pixel row; lengths match `godot` output `animations[].length_s` |
