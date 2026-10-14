---
name: image-to-model
description: Building a game-ready 3D model from 1-3 images (photos, concept art, sketches) - choosing between modeling by hand from the images, image-to-3D generation and a hybrid, gated by the manifest model_generators policy and model licences; photo and matting preparation, camera matching, generator options (local open-weight and paid APIs) with licence traps, cleanup/retopo/bake/de-light in Blender through the MCP, silhouette-IoU evaluation against the input views, provenance. Load it when a modeling task's reference is photos or fewer than a full orthographic sheet.
user-invocable: false
---

# Model from 1–3 images

Scripts in `${extensionPath}${/}skills${/}image-to-model/scripts/` (normal Python with Pillow + numpy, run with Bash):

| Script | Use |
|---|---|
| `prep_image.py inspect` | size, alpha, EXIF focal length (35 mm eq.), clipped highlights, crushed shadows, warnings |
| `prep_image.py prep` | cut-out (alpha or rembg `birefnet-general`), crop, square canvas at `--fill`, one common scale for all views |
| `silhouette_iou.py` | fitted silhouette IoU, aspect drift and a red/blue diff image: render vs reference |
| `value_bands.py` | light/dark pattern per height band inside the silhouette (plates vs dark undersuit, joints, recesses, soles): render vs reference, flagged bands and a mask image |

Modeling itself follows the blender-modeling skill; the output meets the asset-pipeline contract.

## 1. Choose the route first

Read `model_generators` in `manifest.md` (`off` | `local` | `remote` | `api`; agents never change
it — ask the user through the handoff). `remote` = open-weight models (e.g. TRELLIS.2 MIT,
Step1X-3D Apache) on a rented GPU through the gpu-server skill's `gpu_job.py` — spend cap per
run, provenance, the server stopped after the job; pick the GPU by the model's VRAM. No generator
installed yet → `tools_check.py offers` (tools skill): compare, recommend, install on the yes. Then choose
by asset type:

| Asset | Route |
|---|---|
| hard-surface, mechs, anything with damageable parts, joints, exact dimensions | **B: model by hand** from the images; a generated mesh may serve only as a proportion reference |
| organic prop, rock, food, cloth, statue, foliage clump | **A: generate → clean up** (if allowed), else B |
| character or creature that deforms | **C: hybrid** — generated sculpt as reference/bake source, hand retopology with deformation loops, then rig; B if generators are off |
| poor, occluded or off-axis photos | B, using any generated blockout only for proportions |
| stylised concept art | A only if it shows a clean ¾ or front view; otherwise B |

Generated meshes are fused (fingers, held weapons, legs), soft-edged, have nothing inside, invent
the back, and bake lighting into the albedo. Never ship one without §4 and §5.

## 2. Prepare the images

1. `prep_image.py inspect` every image; fix or report its warnings. Good input: overcast light or
   a lightbox, no hard shadows or specular blowouts (a polariser helps), white balance from a grey
   card, exposure not clipped, the object whole and unoccluded, ≥1024 px on the short side.
2. Photos: shot from a distance with a long lens (≥50 mm eq.) — generators assume a narrow field
   of view. Several views: same distance, focal length and eye-level height, 90° turntable steps
   (front first). Test once with an asymmetric marker whether a tool's "left" is the object's or
   the camera's.
3. `prep_image.py prep` all views together (common scale; RGBA output so the generator's own
   background remover — often non-commercial — is skipped). Matting: rembg with
   `-m birefnet-general` (MIT) only; the rembg default `bria-rmbg` is CC BY-NC.
4. Real size: from the design spec, a known object in the photo, or a measurement — write it in
   the model sheet with its source. Proportions are measured on the prepped images in pixels.

Reference files stay outside the game's content folders (Godot: add `.gdignore`); record source,
licence and date of every image in `ref/manifest.csv`; prepped images go to
`art/source/<asset>/ref_prepped/`.

## 3. Route B: model by hand from images

Follow blender-modeling §1–§7 with these changes for photos:

- A photo is a perspective view, not an orthographic sheet. Put a camera in `_refs` matching the
  photo: sensor 36 mm and the EXIF 35 mm-equivalent focal length (or estimate it from converging
  lines), camera height at eye level; set the photo as the camera background; compare through
  that camera. Measure ratios only along lines parallel to the image plane.
- One image: the hidden side is a design decision — choose the mechanically plausible option,
  mirror where the object is symmetric, and list every invented part in the handoff.
- Two or three images: model against all of them; a part is right only when it matches in every
  view where it is visible.

## 4. Route A/C: generate, then make it game-ready

**Generation runs as a separate process, never as a Blender add-on or another Blender MCP.**
Environments live outside the project (`<venvs>/<tool>`: machine.json `tools_root`/venvs, else
`~/.local/share/kiln/venvs`). Output goes to
`art/generated/<asset>/` with `provenance.json`: tool, version, weights licence, seed, settings,
input file hashes, date. Steam asks for disclosure of AI-generated content; AI output is not
copyrightable in the US — tell the user which assets came from generators.

| Option | Input | Licence / limits | When |
|---|---|---|---|
| Pixal3D (TencentARC, built on TRELLIS.2) | 1 image, or N posed views (`transforms.json`, first view = front) | MIT; inherits TRELLIS.2 deps; `--low_vram` | best local fidelity and PBR, multi-view |
| TRELLIS.2-4B (Microsoft) | 1 image | MIT + DINOv3 licence; ≥24 GB, Linux (Windows via ComfyUI-Trellis2) | local, PBR, up to 1536³ |
| TripoSG | 1 image | MIT; 8 GB; shape only | small GPU: shape, then texture by projection in Blender |
| Direct3D-S2 / Hi3DGen | 1 image | MIT; shape only | sharp hard-surface blockouts |
| Step1X-3D | 1 image | Apache-2.0; 27 GB | watertight shape + texture |
| SF3D / SPAR3D (Stability) | 1 image | Stability Community: free under $1M revenue | fast, de-lit albedo, lower fidelity |
| TripoSR (VAST / Stability) | 1 image | MIT code and weights; CPU works (~40 s model + ~40 s mesh at 256³; PyMCubes wheel when torchmcubes will not compile) | no CUDA GPU: rough shape with vertex colours, clean-up expected |
| PartCrafter / OmniPart | image (+ 2D part mask) | MIT | separate part meshes (OmniPart textured) |
| Tripo API | 1 image or front/left/back/right | paid plan for commercial use (free tier non-commercial); ≈$0.20–0.30 per model | cheapest API; segmentation, low-poly |
| Meshy API | 1–4 images, no poses | paid plan (free tier outputs are CC BY) | multi-image without poses |
| Rodin (Hyper3D) | multi-image | paid; API on Business plan; ≈$0.40–1.50 per model | high-quality fallback |

Framing the input: single-image generators read the frame as the object's extent. A tight crop of
a face comes back as a flat relief mask (live TripoSR run: 0.09 m deep, no back of the skull); the
same head cropped with neck, hair, ears and collar, ~0.85 fill on a square canvas, came back as a
closed bust. Feed the whole object with its natural context and a margin, then cut the extra away
in Blender. Check left/right against an asymmetric mark (a mole, a decal) after import.

`local` allows the open-weight rows; `api` also allows the paid APIs (the user supplies the key
in an environment variable, never in the project).

Licence traps — refuse these for a commercial game:
- **Hunyuan3D open weights** (2.0/2.1/2mv/Part): licence excludes the EU, UK and South Korea and
  covers the *output* — a game sold worldwide cannot use them.
- **nvdiffrast** (imported by TRELLIS.2's GLB texture bake): research/evaluation only. Bake the
  textures in Blender instead, or get a legal review.
- **BRIA RMBG-2.0** and the rembg default model: CC BY-NC — feed RGBA input instead.
- NVIDIA PartPacker / PartField and MASt3R/DUSt3R (pose estimation): non-commercial. For poses of
  off-axis photos use VGGT-1B-Commercial.

Then in Blender through the MCP (`execute_blender_code`, one step per call, numbers returned):

1. Import: `bpy.ops.import_scene.gltf(filepath=..., merge_vertices=True, import_webp_texture=True)`
   (TRELLIS.2 ships WebP textures; the default `False` drops them). Join, apply transforms.
2. Normalise: scale to the real size, origin at bottom centre, front facing −Y (exports to +Z for
   Godot's `MODEL_FRONT`; see the engine profile for Unity/Unreal axes).
3. Clean: merge by distance, delete small loose islands (floaters, internal shells), recalculate
   normals; check before `fill_holes` — it also closes openings you want; voxel remesh thin or
   non-manifold shells.
4. Symmetry: align the symmetry plane to X = 0, bisect, Mirror modifier; re-bake the texture from
   the mirrored high-poly.
5. Budget: static props — Decimate (Collapse); deforming meshes — voxel remesh, then
   `bpy.ops.object.quadriflow_remesh(target_faces=N, use_mesh_symmetry=True, use_preserve_sharp=True)`
   (fails on non-manifold input) or hand retopology for heroes.
6. UV: `uv.smart_project(angle_limit=1.15, island_margin=0.003)` + `uv.pack_islands(margin=0.004)`;
   hand seams for hero assets.
7. Bake high → low in Cycles (`use_selected_to_active=True`, cage extrusion 1–2% of size,
   margin 16): NORMAL (tangent, OpenGL; Unreal flips green), DIFFUSE with only COLOR,
   ROUGHNESS; metallic through an Emission route and EMIT.
8. De-light: bake AO from the high-poly and divide it out of the albedo (clamped), compress
   luminance above the 95th percentile; or re-texture with a PBR texturer. Check that surfaces
   meant to be uniform have low luminance variance.
9. Parts for damage: separate by loose parts/material or bisect at joint planes, **cap every cut**
   (generated meshes are hollow), origins at joints, names per the asset-pipeline contract.
10. Export per the asset-pipeline contract.

Typical artefacts → fix: blobby hard-surface bevels → regenerate at 1536 or rebuild by hand;
fused parts → A-pose / separated-limb input, or cut and rebuild; invented back → multi-view input
or mirror from the front; blurry back texture → re-project from camera-matched photos; garbled
text and logos → decals.

## 5. Evaluate against the input views

1. For every input view render the model through the matched camera (route B: the `_refs`
   camera; generated models: front camera on −Y, then a small search over azimuth ±15°, elevation
   and focal length maximising IoU) with `film_transparent = True` at the prepped image size.
   Save renders to `production/captures/<task>/`.
2. `silhouette_iou.py ref_prep.png render.png --min 0.90 --diff <path>` for the front view,
   `--min 0.85` for side/back views; read the diff image — red = model too thin or missing,
   blue = too wide or extra. Thresholds are starting points; calibrate on an accepted model.
   From primary forms on, also `value_bands.py ref_prep.png render.png --bands 16 --image <path>`
   for every view (render with the viewport colours or materials on): a matching silhouette can
   still be one white tube where the reference has separate plates, dark joints and soles.
   Live run: the cuirass, the back plate and the legs each failed a separate review round for
   this; one whole-body pass finds all three at once.
3. Checklist: proportions within ~5% of the measured ratios; symmetry right; plausible back; no
   lighting in the albedo; no texture seams; normal map without waves or cage misses; triangle
   count and texel density in budget; pivots right; scale checked against a reference capsule in
   the engine.
4. The art-director reviews; the builder does not grade its own model.

Handoff evidence: route and why, the policy value, each input view with its IoU and diff, the
invented-parts list, provenance file (generated assets), budgets with real numbers.
