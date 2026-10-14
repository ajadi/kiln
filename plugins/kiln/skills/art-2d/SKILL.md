---
name: art-2d
description: Making 2D game art and animation that hold up - choosing a production method by style (pixel art, vector, painterly, pre-rendered from Blender), resolution and integer scaling, palettes and ramps, sprite sizes and silhouettes, tilesets and terrain autotiling, parallax, frame-by-frame and skeletal 2D animation with frame counts and stride matching, 2D lights, normal maps and CanvasItem shaders, engine render settings (Godot, Unity), AI image models behind a licence gate, and objective checks (palette, alpha, mixels, silhouettes, contrast, frame baselines). Use for any sprite, tile, 2D animation or 2D look task, and whenever manifest.md says dimension=2d.
user-invocable: false
---

# 2D art and animation

Checks: `${CLAUDE_SKILL_DIR}/scripts/sprite_qa.py` (Pillow + numpy, Bash) — `palette`, `alpha`,
`mixels`, `silhouettes`, `contrast`, `clusters`, `frames`. Movement numbers for 2D games are in
`${CLAUDE_SKILL_DIR}/../pipeline/references/feel-numbers.md` (§ 2D movement); 2D level layout in
the level-design skill.

## 1. Choose the production method by style

| Style | Method | Tools (licence) |
|---|---|---|
| pixel art, characters ≤ 32 px | placed by hand pixel by pixel through code with a locked palette | Pillow indexed `P` mode; Aseprite CLI (proprietary, the user owns a copy) or Pixelorama (MIT) / LibreSprite (GPL) |
| pixel art, many frames or large sprites | **pre-render** a 3D model from Blender through the MCP → quantise to the palette → clean up by hand | Blender ortho camera, toon shading (Shader to RGB + constant ColorRamp), outlines (Freestyle / inverted hull / Grease Pencil Line Art), film filter 0, Normal pass for 2D lights; Pillow `quantize(palette=..., dither=Image.Dither.NONE)` |
| vector / flat | SVG written as code, rendered to PNG at the target size | resvg (Apache-2.0), CairoSVG (LGPL), Inkscape CLI; animate with Skeleton2D + Polygon2D |
| painterly | Blender painterly materials + Grease Pencil Line Art, or AI images (policy) with a style LoRA | weakest area — say so in the plan and get the art bible approved on a sample first |
| tiles, procedural layouts | blob tiles assembled from quarter pieces; WFC for layouts | Python + Pillow |

Aseprite batch: `aseprite -b in.aseprite --sheet out.png --sheet-type packed --data out.json --format json-array --list-tags --split-layers --extrude --shape-padding 1 --trim`
(`--script` + `--script-param` for Lua). Aseprite MCP servers exist (diivi/aseprite-mcp MIT) —
an extra integration needs the user's approval, like any MCP.

AI image models only when `model_generators` allows: FLUX.1-schnell, FLUX.2-klein-4B and
Qwen-Image (Apache-2.0), SDXL (OpenRAIL++); **not** FLUX.1-dev / FLUX.2-dev (non-commercial).
Consistency needs a LoRA, IP-Adapter or ControlNet; pixel art from AI still needs palette
quantisation and hand cleanup. AI output is not copyrightable in the US and Steam requires an AI
disclosure — record provenance per file.

## 2. Resolution and scale (pixel art)

- One base resolution, integer-scaled to the screen: 320×180 ×6, 384×216 ×5, 480×270 ×4,
  640×360 ×3 for 1080p (Celeste 320×180 with 8 px tiles; Godot pixel art 256×224–640×480,
  baseline 640×360).
- One pixel size everywhere: no scaled sprites, no rotated pixel art (rotate by pre-drawn
  frames or RotSprite), no sub-pixel positions on screen. UI may use its own layer.

## 3. Palette and readability

- 16–64 colours per game; ramps of 4–9 swatches, hue shifting ~+20° toward light, darker ramps
  toward cool. Alpha only 0 or 255. Outlines in the darkest colour of the sprite's ramp, not
  pure black. Store the palette as `art/palette.hex`.
- Silhouette test: every character and enemy type reads as a solid black shape; different types
  differ in silhouette (`sprite_qa.py silhouettes`), not only in colour. Gameplay sprites vs
  background ≥ 3:1 contrast; background values compressed, gameplay layer the strongest values.
- Three palettes can apply to one asset: the **project** palette (the art bible), the **asset**
  palette (the colours this sprite uses) and a **hardware** palette when the look imitates a
  console (Mega Drive: 3 bits per channel, 512 colours, 15 + transparent per sprite line).
  When they disagree, snap to the hardware grid, keep the nearest bible colour, and report the
  distance per colour: `sprite_qa.py palette <png> --bits 3 --palette <bible.hex>` lists
  `distances` (RGB 0–441; g2 reported these by hand); `--max-distance` makes it a gate.
- 2D textures in a 3D game (a rug, a poster, a decal sprite): keep the palette next to the asset
  (`art/source/<asset>/palette.hex`, the project bible stays `art/palette.hex` or the art bible's
  swatch list), and keep two files: a **flat design chart** (one colour per cluster, the pixel
  art itself) and the **shaded albedo** the engine uses (knots, weave, lighting baked in).
  `mixels` and `clusters` run on the chart; on the shaded albedo every block breaks.
- Sprite sizes: platformer 16–32 px tall at 320×180, 32–64 px at 640×360; top-down 16×16 tiles
  with 16×24 or 16×32 characters; brawler 64–128 px.

## 4. Tiles and layers

- Tile sizes 8, 16 or 32 px. Terrain autotiling: 16-tile marching squares (corners) or the
  47-tile blob (48 with empty) for corners + sides; Godot terrain modes Match Corners and Sides /
  Corners / Sides. Pad each tile 1 px (extrude) against seams.
- Separate layers: decoration, terrain with collision, hazards, foreground. Hazards share one
  visual language with an animated tell.
- Parallax scroll factors: far 0.1–0.25, mid 0.5, gameplay 1.0, foreground 1.2–1.5 (sparse,
  never hides gameplay).

## 5. Animation

- Frame-by-frame at 8–12 fps (on twos/threes). Typical counts: idle 4–8; walk/run 6–8; jump
  take-off 1–2, rise 1–2, apex 1–2, fall 1–2, land 2–3; attack wind-up 2–3, active 1–2,
  recovery 2–4; hit 2–3 + white flash; death 6–12; top-down 4 or 8 directions.
- **Stride matches speed:** distance per cycle = speed × frames / fps (90 px/s, 8 frames at
  12 fps → 60 px per cycle); planted feet move with the ground (≤ 1 px slide).
- One fixed canvas per animation with the pivot at the feet (`sprite_qa.py frames`).
- Hitboxes and effects keyed on the same timeline as the frames (Godot: AnimationPlayer tracks,
  not code timers). State priority: death > hit > attack > jump/fall > run > idle.
- Skeletal 2D (cut-out): Godot Skeleton2D + Bone2D + Polygon2D, Unity 2D Animation + PSD
  Importer; Spine runtimes need a Spine licence. Not for pixel art (it rotates pixels).

## 6. Light and shaders

- Godot: PointLight2D, DirectionalLight2D, LightOccluder2D; normal/specular through
  CanvasTexture; light `height` for normal-map response. Unity: URP 2D Renderer with 2D lights.
- Normal maps: from the Blender pre-render Normal pass (best), Laigter (GPL-3.0) or a Sobel
  filter. Pixel art: quantise light into bands so it stays crisp.
- CanvasItem shaders: outline, white hit flash, dissolve, palette swap via a LUT. Particles 1–3 px
  in palette colours for pixel art.

## 7. Engine settings

**Godot (recommended for 2D):** pixel art → stretch mode `viewport`, aspect keep/expand,
scale mode integer (4.2+), `rendering/textures/canvas_textures/default_texture_filter = Nearest`,
`rendering/2d/snap/snap_2d_transforms_to_pixel = true` (only this one; physics interpolation can
fight snapping — test). Imports: no mipmaps, lossless. TileMapLayer (TileMap is deprecated),
Parallax2D (4.3+), Y-sort for top-down.
**Unity:** URP 2D Renderer, Pixel Perfect Camera, Tilemap + Rule Tiles, Sprite Atlas, 2D
Animation + PSD Importer; sprites Filter Point, Compression None for pixel art.
**Unreal:** Paper2D is barely developed — use it only for 2.5D; recommend another engine for 2D.

## 8. Checks before handoff

| Check | Gate |
|---|---|
| `sprite_qa.py palette <sprites> --palette art/palette.hex` | 0 out-of-palette pixels, colours ≤ the bible's count |
| `sprite_qa.py alpha` (pixel art) | 0 semi-transparent pixels |
| `sprite_qa.py mixels <in-game capture> --scale k` | broken blocks ≤ 0.2%: integer scale, no rotation, no filtering |
| `sprite_qa.py silhouettes <enemy types>` | pairwise IoU ≤ 0.75 |
| `sprite_qa.py contrast <sprite> --bg <capture>` | silhouette edge (outline) ≥ 3:1 gameplay sprites, ≥ 4.5:1 weak points; `--gate worst` when every colour region must read (the mean of a blue sprite with a light outline read 2.46:1 while the outline gave 8.4:1) |
| `sprite_qa.py clusters <sprites>` | 0 orphan pixels, 0 outline gaps (fill leaking through the outline) |
| `sprite_qa.py frames <cycle frames>` | fixed canvas, baseline within 1 px for grounded cycles |
| in game | camera on whole pixels (no jitter), animation durations as specified, 0 tile-seam pixels while the camera moves at fractional speeds |

## Tile maps from a reference

`${CLAUDE_SKILL_DIR}/scripts/tiles.py extract <map.png> --tile <px> [--flips] [--tolerance N]
--out <folder>`: the image cut on the tile grid, one copy per distinct tile (mirrored copies
stored once with Tiled flip flags under `--flips`; `--tolerance` 4-8 for lossy images) →
`tileset.png` + `map.tmj` (Tiled JSON, orthogonal). Many unique tiles = off-grid or painted
reference. New maps in that style: the procgen skill (WFC).

## Sprite sheets

`${CLAUDE_SKILL_DIR}/scripts/sheet.py` prepares files; nodes and clips are built in the editor
through the MCP. Layouts, bleeding, pivots, engine setups, tool formats: `references/sprite-sheets.md`.
- `pack <frames|folders|globs> --out s.png --data s.json [--layout grid|packed] [--trim]`: frames
  `<tag>_<n>.png` / `<tag>-<n>.png` or a folder per tag → Aseprite json-array (frameTags, ms
  durations, trim offsets, pivot at the feet); packed = MaxRects; padding 1 + extrude 1 default.
- `check s.json` (Aseprite/TexturePacker files too): 0 overlaps, gap ≥ padding + 2 × extrude, no
  rotated frames, valid tags and durations, ≤ 4096 px.
- `godot s.json --res-dir res://… --parent Main/Hero [--pixel-art]`: the Godot AI calls for
  Sprite2D + AnimationPlayer (`frame` or `region_rect` + `offset` tracks, hitboxes on the same
  clip); `--setup frames` = AtlasTextures + SpriteFrames values (frames added in the panel).
