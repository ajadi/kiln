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
5. Numbers (triangles, materials, texture sizes, texel density) in the handoff.
