---
name: asset-pipeline
description: Blender-to-engine asset contract — units, axes, origins, naming, damageable part layout, collision proxies, PBR texture packing, texel density, budgets, export settings, and per-engine import rules (Godot glTF here; Unity and Unreal in their engine skills). Use when modeling, texturing, exporting or importing any 3D asset, or when reviewing whether an asset is game-ready.
user-invocable: false
---

# Asset pipeline: Blender → engine

The contract lets an asset made by one agent drop into a scene built by another without hand
fixes. Deviations are allowed when the task says so; record them in `memory/pipeline.md` so the
next agent does not "fix" them back. Engine-specific import rules: the Godot section below; Unity
and Unreal in `engine-unity` / `engine-unreal`.

## Where things live

| Path | Content |
|---|---|
| `art/source/<asset>.blend` (+ `art/source/<asset>/parts.py`) | editable Blender source and its build script |
| `ref/` | reference sheets (read-only inputs) |
| `art/library/<source>/<id>/` | free library assets as downloaded, with `provenance.json` (`asset-libraries` skill); they follow this contract like any other asset |
| `art/generated/<asset>/` | generated assets with `provenance.json` (`image-to-model`, `api-generators`) |
| engine asset folder (`assets/models/<category>/` in Godot) | exported runtime files |
| `memory/pipeline.md` | budgets, texel density, deviations, part tables |

## Blender side (all engines)

- Scene Metric, Unit Scale 1.0 (exporters ignore Unit Scale; keep it 1.0 and model in metres).
- Characters, mechs, vehicles face **-Y in Blender**. Apply rotation and scale on every exported
  object; no negative scale. Unapplied scale breaks physics shapes, IK lengths and texel density.
- Origins: characters/mechs at ground level between the feet; props at their resting base; doors
  and hinged parts at the hinge; detachable parts at the attachment point.
- Names `snake_case` ASCII; engine scenes and code reference them — renaming later breaks them.
  File/asset prefixes per engine convention (Godot/Kiln default: `SM_`, `SK_`, `M_`, `T_<asset>_<map>`).
- Materials: Principled BSDF + Image Texture + Normal Map nodes only; bake everything procedural
  (glTF and FBX carry no node networks; no UDIMs). Backface culling set as intended.
- Textures: base colour/emission sRGB; ORM and normal maps Non-Color; normal maps baked OpenGL
  (+Y, Blender's default) — Unreal needs DirectX (-Y): flip green on import there.
- Shape keys: exporting with modifiers applied drops shape keys — apply modifiers on a copy.

## Damageable and destructible assets

- One object per damageable part (armour plate, weapon, sensor, limb segment, panel), never
  joined, unique names `part_<zone>_<name>`, origin at the joint/attachment point.
- Each part gets its own simple collision proxy (convex or primitive), so a hit is attributed to
  exactly one part.
- Parts that follow the skeleton: rigid-skinned 100% to one bone or parented to the bone (Godot
  imports bone-parented objects as BoneAttachment3D).
- Per-part data (HP, armour, mount HP, attach bone) as Blender Custom Properties — exported as
  glTF extras (`export_extras=True`), read in engine as metadata — and mirrored in
  `memory/pipeline.md`.
- Damaged variants `part_<...>_dmg` (hidden) and an interior/stump mesh `part_<...>_stump`.
- Destructible props: pre-fractured pieces (Cell Fracture extension through the MCP), interior
  faces with their own material.

## Texel density and budgets (defaults; override in memory/pipeline.md)

| Surface | Texel density |
|---|---|
| First-person reachable surfaces (walls, props the player walks up to) | 1024 px/m (10.24 px/cm) |
| Characters and mechs seen at combat range | 512 px/m |
| Unreachable backdrops | 256 px/m |

| Class | Triangles LOD0 | Materials |
|---|---|---|
| Hero / heavy mech / boss | 30k–60k (HUNT: Showdown publishes 35–70k for main characters, 25–45k bosses) | ≤ 4 |
| Medium mech | 15k–30k (working) | ≤ 3 |
| Light mech | 6k–15k (working) | ≤ 2 |
| Large prop | 5k–15k (working) | ≤ 2 |
| Small prop | 0.5k–3k (working) | 1 |

Power-of-two textures; 2048 max for hero assets unless the task allows more.

## LOD chain

Every engine switches levels by screen size, not distance, and calls about 1 px of error
lossless (Godot's automatic LOD threshold, Nanite, Simplygon). Decide per asset class
(the tech-designer, from the budget):

| Case | LODs |
|---|---|
| LOD0 under 256 triangles | none: a cull distance (Godot `visibility_range_end`, Unity Culled, Unreal cull distance) |
| LOD0 under ~1,000 triangles | no authored chain: the engine's automatic LOD (Godot `meshes/generate_lods`) or one level and a cull |
| small detail parts (bolts, rivets, cables) | not their own LODs: joined into the parent and dropped at the first level where they are under 2 px |
| Unreal with Nanite | none: export LOD0, check the fallback mesh |
| foliage, aggregates, many loose pieces | 1-2 mesh levels, then a billboard or impostor (Godot: a visibility range swapping to a Sprite3D) |
| never seen small (first-person weapon, cockpit) | none |
| everything else | an authored chain |

1. blender-modeling `lod_build.py`: levels at ~50 % of the previous level's triangles (a level
   must cut at least 25 %), the chain stops under 1,000 triangles or a switch size of 0.02.
   `collapse` for organic and generated meshes (protect the face, hands and joints with a vertex
   group), `planar` for flat hard-surface panels, or the asset's `parts.py` recipe with fewer
   segments and bevels. LOD1-2 keep LOD0's UVs and materials; far levels use one material
   (shading cost does not drop with triangles). Skinned levels keep the armature.
2. The switch size per level comes from its error, not a guess: e = two-sided Hausdorff distance
   to LOD0, s = p · D / (e · H) (D bounding diameter, H screen height, p = 1 px, 2-4 in a
   performance profile). It is stored on each level as `kiln_lod_screen`, `kiln_lod_error_m`,
   `kiln_lod_diameter_m` and travels as glTF extras (`export_extras=True`).
3. `lod_shots.py` in Blender, then `python ${extensionPath}${/}skills${/}asset-pipeline/scripts/lod_check.py <asset.glb>
   --shots <dir>`: triangle ratio, chain length, silhouette outline distance at the switch
   size (p95 ≤ 1 px, max ≤ 2 px), mean boundary shift, shading and triangle size (warn until
   calibrated), materials per level. `asset_budget.py` counts LOD0 only and checks
   `"lod_ratio": 0.5` when the budget sets it.
4. Naming `<mesh>_LOD<n>` under one parent. Engine import:

| Engine | Route |
|---|---|
| Godot | glb with the extras; engine-godot `kiln_lod_ranges.gd` as the file's import script turns the levels into visibility ranges (distance from s and the camera FOV, 5 % margins, fade off); `meshes/generate_lods=false` for that file so automatic LODs are not stacked on authored ones |
| Unity | FBX with `_LOD<n>` names → LOD Group; transition heights = s per level; not together with Mesh LOD |
| Unreal | Nanite on → LOD0 only. Otherwise import LOD0, then "Import LOD Level N" per level file, screen size = s per level |

glTF `MSFT_lod` is read by none of the three engines; do not rely on it.

## Series: one style across many assets

A set of assets that must read as one family (a faction's vehicles, a dungeon kit, the enemy
roster) is a **series**; art tasks name it with a `series: <name>` line. The first member the
art-director approves becomes the anchor in `art/anchors/<series>/`: the glb, a lineup render,
`style.json`, a style sheet of 5-8 written principles (TF2's form: "high-frequency detail
omitted", "bevels 2 cm on every outer edge", ...) and the anchor's `parts.py` helpers (bevel
widths, segment counts, panel and bolt modules) that followers import instead of re-inventing.

- `python ${extensionPath}${/}skills${/}asset-pipeline/scripts/style_anchor.py extract <anchor.glb> --views <views dir>
  --out art/anchors/<series>/style.json` once; views are `silhouette_shot.py` renders at one fixed
  object height plus a flat-lit colour render per view.
- Each follower: `style_anchor.py check art/anchors/<series>/style.json <member.glb> --views
  <dir>` compares style statistics, never the silhouette (members are meant to differ in
  shape): triangle and texel density, edge sharpness (bevels), part sizes, flat-surface share,
  material count, palette (CIEDE2000), values, silhouette solidity. A hard metric fails the gate;
  soft ones go to the art-director, whose **lineup** of the member next to the anchor (same
  scale, light and camera) decides.
- Tolerances are starting values: after two approved followers, `calibrate` widens them to the
  spread the art-director accepted.

## Export (through the Blender MCP, in the connected Blender)

glTF/GLB for Godot (and Unity with glTFast); FBX settings for Unity/Unreal are in their engine
skills. Export through the MCP and import the file — do not rely on an engine's direct `.blend`
import (it runs Blender in the background on every machine, with different defaults).

```python
bpy.ops.export_scene.gltf(
    filepath=OUT, export_format='GLB', use_selection=True,
    export_apply=True,            # False if the mesh has shape keys (they would be dropped)
    export_yup=True, export_texcoords=True, export_normals=True, export_tangents=True,
    export_materials='EXPORT', export_animations=True, export_animation_mode='ACTIONS',
    export_skins=True, export_def_bones=True, export_extras=True,
    export_draco_mesh_compression_enable=False)   # Godot reads neither Draco nor meshopt
```

Animation: actions named by the clip contract (animation skill); Blender fps equal to the engine
import fps (Godot `animation/fps` default 30).

- **Occlusion (glTF core) needs the exporter's own group**: create `glTF Material Output` with
  the add-on's helper, never by hand — `from io_scene_gltf2.blender.com.material_helpers import
  create_settings_group, get_gltf_node_name` (Blender 5.2; the node editor's Add menu item does
  the same). A hand-made group with only an Occlusion socket makes Blender's own glTF importer
  crash (`KeyError: 'Iridescence Factor'`) when a glb is imported back into that file: the
  importer reuses the group by name and expects all five sockets (Occlusion, Thickness,
  Dispersion, Iridescence Factor, Iridescence Thickness Minimum). Validate an export from its JSON
  chunk (read the glb header and JSON) or import it into a fresh file (g2 row 59).
- A Principled BSDF + ORM setup prints "More than one shader node tex image used for a texture"
  on every export; the glb is still correct (base colour, metallic-roughness, occlusion, normal
  present — check the JSON). One vertex-colour attribute is written as `COLOR_0` and `COLOR_1`;
  harmless (row 69).
- **Shared atlases and glb**: every glb embeds its own copy of each image and Godot extracts them
  per file, so 12 crowd looks as 12 glbs load 12 copies of "one" atlas. Options, cheapest VRAM
  first: one glb per atlas group holding all looks that share it (g2: one glb per base body with
  its 3 looks); `.gltf` + external PNGs that every file references (Godot imports each PNG once);
  extract materials in Godot and point every glb's surfaces at one material
  (`import_edit.py --sub "materials::<name>::use_external/..."`). Say which in
  `memory/pipeline.md` (row 101).
- **A Blender camera matching a Godot frustum camera** (reference frames, landmark checks): with
  Godot `projection = FRUSTUM`, `size` (frustum height at `near` for keep-height), `frustum_offset`
  and `near`: `sensor_fit = 'HORIZONTAL'`, `lens = sensor_width / 2 / (size / 2 / near * aspect)`,
  `shift_x = offset.x / (size * aspect)`, `shift_y = offset.y / (size * aspect)`; rotation =
  `M @ R_godot` with `M = [[1,0,0],[0,0,-1],[0,1,0]]` (Godot Y-up to Blender Z-up; a tscn
  `Transform3D` lists the basis by rows). Measured in g2: one landmark within 0.2 % of the frame,
  another 2 % of the frame height off — check `keep_aspect` before trusting it (row 68).

## Godot import (4.6/4.7)

- glTF: +Y up, front +Z = `Vector3.MODEL_FRONT` (`FORWARD` is -Z). `look_at(target, up,
  use_model_front=true)` points the model's front; with the default false, -Z points at the target.
- Name suffixes (after `-`, `_` or `$`, case-insensitive, trailing `.001` digits ignored):
  `-col`, `-convcol`, `-colonly`, `-convcolonly`, `-rigid`, `-navmesh`, `-occ`, `-occonly`,
  `-noimp`, `-vehicle`, `-wheel`, material `-alpha`, `-vcol`; animations `loop`/`cycle`. Empties
  named `-colonly` become Box/Sphere/WorldBoundary/SeparationRay shapes by display type.
- Collision: primitives or convex for anything dynamic; trimesh (`-col`) only on static bodies —
  it does not work with CharacterBody or RigidBody. Never scale collision shapes. Physics layer
  and mask per mesh in Advanced Import Settings or an import script.
- ORM packed R=AO, G=roughness, B=metallic works unchanged; OpenGL normal maps.
- `meshes/generate_lods` and `create_shadow_meshes` default on (check skinned meshes for LOD
  glitches); `meshes/light_baking = Static Lightmaps` only for static level geometry (generates
  UV2; `lightmap_texel_size` default 0.2).
- **Editable without losing work on reimport**: never edit the imported scene; wrap it — a
  gameplay `.tscn` whose root is the gameplay node and which instances the `.glb`, or an
  inherited scene for overrides. Extract materials to `.tres` (Advanced Import → Extract
  Materials) so reimports keep them. Repeatable fixes go into an `EditorScenePostImport` script.
  Agents set these options with engine-godot `scripts/import_edit.py` (`materials/extract`,
  `use_external`, per-node `mesh_instance/cast_shadow`, `import_script/path`) and reimport —
  engine-godot `references/import-settings.md`.
- Every imported mesh casts shadows by default (g2: a ground decal, water, glass and flames cast
  shadows; shadows were about 65 % of all primitives). Name such nodes with a suffix (`_decal`,
  `_water`, `_glass`, `_fx`) in Blender and switch `cast_shadow` off per node in the import
  options, or with a post-import script that matches the suffixes.
- Version control: commit `*.import` and `*.uid` files, ignore `.godot/`; Git LFS for `.glb`,
  `.blend`, textures before the first commit; keep `gltf/naming_version` per file.

## Definition of done for an asset

1. Source `.blend` saved; transforms applied; names, parts and proxies follow the contract.
2. Exported, imported by the engine with zero import errors in the log.
3. Seen in the engine: scale (compare with a 1.8 m capsule), facing, materials, collision proxies
   (visible collision shapes on), parts as separate nodes.
4. Compared with the reference by the art-director when the task has one.
5. Within budget: `python ${extensionPath}${/}skills${/}asset-pipeline/scripts/asset_budget.py "assets/**/*.glb"
   --budgets production/budgets.json` (triangles per instance, draw calls, materials, bones,
   largest texture, VRAM with mips; images count once per glb, so a "shared" atlas in many glbs
   shows its real cost). The tech-designer writes `production/budgets.json` from the performance
   budget (globs per asset class, `*` last).
6. LOD: `lod_check.py` passed, or the reason the asset has no authored chain (the table in
   "LOD chain").
7. A series member: `style_anchor.py check` against its anchor and the art-director's lineup.
8. Numbers (triangles, materials, texture sizes, texel density) in the handoff.
