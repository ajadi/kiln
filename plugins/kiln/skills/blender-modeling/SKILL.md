---
name: blender-modeling
description: How to model high-quality game assets in the user's open Blender through the Blender Lab MCP — reference preparation and a measured model sheet, anchor-first part graph, a persistent per-part build script, hard-surface techniques in bpy/bmesh, a normalised multi-view review loop with numbers and yes/no checklists, contact and mesh QA scripts, round budgets with revert, UVs, materials and baking, context hygiene, and the failure modes LLM-made models show. Use for any modeling, remodeling or model review task.
user-invocable: false
---

# Modeling in Blender through the MCP

Models built by writing code fail in predictable ways: proportions drift from the reference,
parts float or pass through each other, generic primitives stand in for specific shapes, shading
breaks, details scatter. Research on code-driven 3D modeling (see Kiln's design notes for
sources) agrees on what fixes it: **a measured plan, parts built anchor-first with computed
positions, a multi-view critique after every part that sees numbers as well as pictures,
scripted geometry checks, and a small fixed number of refinement rounds.** A script that runs
without errors is not progress; only a reviewed view is.

Scripts in `${CLAUDE_SKILL_DIR}/scripts/` — read the file, set the parameters at the top, send
the content with `execute_blender_code`; results come back in `result`:

| Script | Use |
|---|---|
| `crop_ref.py` | normal Python (Bash): grid overlay to read coordinates, tight crops of each view |
| `ref_setup.py` | cropped views as scaled image empties for orthographic modeling |
| `parts_kit.py` | helpers to prepend: `bbox_world`, `describe` (numbers for critique), `place_on` (seat a part on its parent's face), `bevel_and_weight`, `keep_previous` (revert copy) |
| `set_view.py` | normalised review view (front/back/left/right/top/bottom/iso), returns the camera pose |
| `contact_check.py` | gap / contact / crossing for every pair that must touch |
| `silhouette_shot.py` | ortho flat silhouette of the targets at a stated px/m + sidecar JSON (camera recorded); read-only roles may run it |
| `silhouette_measure.py` | normal Python (Bash): `deltoid`, `contour`, `chord-angle`, `width`, `gap`, `holes` on a silhouette shot — one metric definition for builder and reviewer |
| `card_atlas.py` | normal Python (Bash): hair/beard card atlas (`make`: tiles + mass strip, colour dilated under alpha) and `check` (light edge texels, fill colour) |
| `mesh_qa.py` | mesh health per object, per-part bounding boxes, connected groups (floating parts), crossing pairs; on the joined set: back faces seen from 8 azimuths and daylight (background enclosed by the front/side/back silhouette, with its z range) — these catch holes and garment gaps inside one joined mesh |

## 0. Ground rules for code through the MCP

- One part or one operation per `execute_blender_code` call. Capture the object you create —
  names collide and get `.001` suffixes.
- Set mode, active object and selection explicitly before operators; they change them as a side
  effect. Data/bmesh API for precise geometry; operators for standard actions. Write bmesh edits
  back (`bmesh.update_edit_mesh` / `bm.to_mesh`) or they are silently lost.
- Look up anything version-specific before using it (`search_api_docs`, `get_python_api_docs`):
  most script failures in benchmarks are Blender 4.x → 5.x API mismatches — renamed Principled
  BSDF sockets, enums, removed auto smooth (now "Smooth by Angle" / `shade_smooth_by_angle`).
  For node sockets, read `node.inputs.keys()` instead of assuming names.
- Return numbers in `result`, not prints. Save the `.blend` after each finished part.
- Blender is shared: start each call with `assert bpy.data.filepath.endswith("<asset>.blend")`
  (re-open it if another session left a different file open) and never save over another
  agent's file. Keep calls under ~150 s (a long bake times out while Blender keeps working; chunk
  it and keep results in `bpy.app.driver_namespace`).
- If the user has edited a part by hand, that part's geometry in the `.blend` is the source of
  truth: never rebuild it from script without asking.

## 1. Plan before geometry: reference, model sheet, part graph

No reference for a part you must design (a helmet the sheet lacks, a gear unit the user only
described): block out **three** structurally different options under deliberately different
constraints (e.g. compact and hugging the body / mechanical and exposed / strongest silhouette),
render each from the views that matter, and let the art-director pick with a reason; keep the
others in the captures. Three tweaks of one idea are not three options.

1. Crop each view of the sheet (`crop_ref.py --grid`, then tight crops: lowest point on the
   bottom edge, highest on the top). Read small details from the `_zoom` crops.
2. Write the **model sheet** in the task file — short lines, no prose:
   - real size in metres (design spec, or derived from a scale figure on the sheet — say which);
   - **part graph**, anchor first: for each part its parent, attachment point/face, direction,
     and approximate bounding box in metres; named per the asset-pipeline contract;
   - key proportion ratios measured in pixels on the crops ("leg / total height = 0.46");
   - limbs in 3D: a limb that points toward the camera in one view is foreshortened there —
     sheets often show arms angled forward, not a true T-pose. Measure each segment's offset in
     two views (front: sideways and up/down; side: forward/back), take the length as
     √(x² + y² + z²) and build it in that direction. Humans and humanoids: compare with the
     human-biomechanics proportions (arm span ≈ H; upper arm / forearm / hand 0.186 / 0.146 /
     0.108 H). A ratio more than ~10 % off is a measuring or foreshortening error until a second
     view shows it is the design; then write it in the sheet as a deliberate stylisation;
   - contact list (pairs that must touch) — these become `contact_check.py` pairs;
   - palette sampled from the crops with PIL (`getpixel` on flat areas), materials, wear,
     emissive parts;
   - 2–5 yes/no acceptance checks per major part ("cockpit visor wraps 180° around the front?",
     "three toes per foot, toe tips touch the ground?").
3. `ref_setup.py` with the real height: the views appear behind the geometry in matching ortho
   views, base on z = 0. For a perspective concept painting instead of an orthographic sheet,
   create a temporary camera in `_refs` matching the painting's angle and focal length and
   compare through it; delete it when done.

## 2. One persistent parts script

Keep the asset's construction code in `art/source/<asset>/parts.py`: one function per part,
named dimension parameters at the top, comments naming each part, a fixed random seed, shared
helpers from `parts_kit.py`. To change a part, edit its function and re-run only that function
through `execute_blender_code` (replacing the old object). Never regenerate the whole script —
agents that rewrite from scratch lose parts and drift. The `.blend` stays the deliverable; the
script is the recipe that makes rework precise. Reusable pieces (bevelled panel, piston, bolt
row, vent) become helpers in the script instead of being rebuilt each time.

## 3. Stages and round budgets

| Stage | What | Review rounds (max) |
|---|---|---|
| Blockout | every major part as a simple volume at true size and position, anchor first | 2 |
| Primary forms | real shapes part by part, positions computed with `place_on` from the parent | 3 per assembly |
| Contacts | `contact_check.py` on the assembly's contact list; fix gaps and crossings | until clean |
| Secondary & detail | panels, recesses, joints, pistons, cables; then vents, bolts, lights as validated modules repeated by array | 2 |
| Edges & shading | bevels, weighted normals (§4) | 1 |
| UV & materials | §6 | 2 |

Finish geometry before materials — early mistakes carry into every later stage. Stop a stage
early when all its yes/no checks pass. Before reworking a part, `keep_previous(part)`; if the
next review is worse, restore the previous copy. At each milestone save a checkpoint copy
(`bpy.ops.wm.save_as_mainfile(filepath=".kiln/tmp/checkpoints/<asset>_<stage>.blend", copy=True)`).
For one or two key parts that keep failing (a head, a cockpit), build 2–3 variants side by side
and pick by direct comparison with the reference instead of nudging one version.

## 4. Hard-surface techniques that work through code

- Primitives sized from the part graph, shaped with bmesh: extrude, inset (panels), bevel
  selected edges, bridge edge loops, loop cuts for control. Symmetric parts as one half with a
  Mirror modifier (clipping on).
- Edges that catch light: `bevel_and_weight(obj, width, segments=2–3, angle_deg≈30)` — bevel
  width scaled to the part (2–10 mm on a mech), hardened normals, Weighted Normal, smooth
  shading. If the reference shows crisp planar edges or a low-poly style, keep edges hard.
  Bevels and smoothing never hide weak construction.
- Booleans for cut-outs and sockets (`cut_*` cutters), then merge by distance, dissolve
  degenerate geometry, recalculate normals, and check mode `wire` for long thin triangles.
- Solidify for plates and shells (real thickness, 1–3 cm on a mech).
- Curves for cables and hoses (`bevel_depth`, converted to mesh at the end); pipes with bends as
  one continuous mesh of bridged rings, not overlapping cylinders.
- Pistons and joints: cylinder in sleeve, origin at the pivot, so rigging and detachment work.
- Quads on visible curved or deforming surfaces; triangles/n-gons on flat static faces are fine.
- Organic forms are the weak spot of scripted modeling: box-model a Subdivision cage with
  mirror, keep it simple, and say in the handoff when a sculpt pass or another source is needed.
  Armoured characters: model the armour as hard-surface pieces over a simple body.

## 5. Review loop — after every part and before every handoff

1. **Normalised shots** with `set_view.py` (Object mode, nothing selected, overlays only when
   needed): `front`, `right`, `back` (ortho, refs visible), `iso_front_right`, `iso_back_left`;
   after major assemblies also `top` and `bottom`; plus close-ups of joints and contacts.
   Modes: `shape` for form, `parts` for part split and gaps, `wire` for topology, `normals` for
   flipped faces. Screenshot with `get_screenshot_of_area_as_image` (modest
   `size_limit_in_bytes`; a tighter second shot for small details instead of guessing).
2. **Numbers next to pictures**: `describe(parts)` from `parts_kit.py` (world boxes, centres,
   sizes), the camera pose `set_view.py` returns, and the model-sheet ratios recomputed from the
   model vs the reference ratios.
   Characters, statues and creatures: also the ortho silhouettes from `silhouette_shot.py` and
   the numbers from `silhouette_measure.py`; read `references/characters.md` before the first
   human or creature (shoulders, SDF figures, garments over joints, hair cards, bakes, the shared
   Blender).
3. **Checklist, not impressions**: answer the part's yes/no checks plus the standard ones —
   floating parts? surfaces passing through each other? broken or flipped surfaces? silhouette
   matches the reference in front and side? every ratio within ~5%? A general "looks good" is
   not an answer; models judging their own renders miss subtle differences.
4. **Fix** the failing items, then re-shoot the same views and confirm each fix against the
   previous shot. After the round budget, stop and report what still differs.

## 6. UVs, materials, textures

- UVs: seams on hard edges and hidden borders, or `uv.smart_project` (angle limit ~66°, island
  margin ~0.02) for hard-surface parts; `uv.pack_islands` with a margin. Uniform texel density
  (project value in `memory/pipeline.md`); visible hero parts up, hidden faces down.
- Principled BSDF: base colour from the sampled palette, metallic 0 or 1 for real materials,
  roughness varied per material (painted metal ~0.4–0.6, bare metal ~0.25–0.4, rubber ~0.8).
  Nothing ships in default grey.
- Wear (edge wear, dirt, scratches) as procedural masks, then **baked** to images (Cycles bake:
  base colour, roughness, normal, AO → packed ORM) — glTF and Godot do not carry node networks.
  Detail too small for geometry can be baked from a high-detail copy into the normal map.
- Emissive parts (eyes, lights) as emission with the reference colour.

## 7. QA before handoff

`mesh_qa.py` on the asset collection: no non-manifold edges except deliberate open plates, no
loose verts, zero-area faces, duplicates or inside-out meshes, scale applied, origin per
contract, one connected group (or exactly the groups the damage split intends), every crossing
pair explained. Put the numbers and the views you compared into the handoff.

**Worn and articulated gear** (armour, clothing, kits on a character) also needs a joint sweep
before handoff: pose each joint of the rig or a proxy skeleton until parts collide (elbow,
shoulder flexion and abduction, hip, knee, ankle, neck), write the stop angles into the handoff as
`{"stops": {...}}` and run the traversal skill's `traversal_check.py rom --moves <the character's
moves>`. Fix shortfalls in the model the way real armour did — relief cuts in joint pits, sliding
lames, fan wings on knees and elbows, a disc or gap at the armpit, thin padding at joints — not by
capping the animation (live: an elbow stop at 56° found only during animation needed a second
modeling pass). Host-side parts and empty states from the task's `## implications` are modeled in
the same pass.

## 8. Context hygiene on long jobs

Screenshots fill context fast, and late in a long session models start praising flawed output.
Keep the task file current (model sheet, checklist, open deltas, path of the latest checkpoint)
so nothing lives only in context. After roughly ten review rounds on one asset, or when you
notice yourself re-reading old shots, finish the current part, save, and hand off NEEDS_WORK
with the next steps — a fresh modeler continues from the task file and the saved `.blend`.

## Failure modes and the check that catches them

| Failure | Caught by | Fix |
|---|---|---|
| Proportions drift | ratio table vs reference | fix blockout before detail |
| Floating parts, daylight at joints | `contact_check.py`, `mesh_qa.py` groups, mode `parts` | `place_on` from the parent's measured face |
| Parts passing through each other | crossing pairs, joint close-ups | re-seat, or cut a socket |
| Generic primitive instead of the referenced shape | side-by-side ortho views vs crops | rebuild the part from its profile |
| Blobby / plastic look | mode `shape` with cavity | real bevels + weighted normals, sharper secondary forms |
| Shading artefacts, black faces | mode `normals`, `inside_out` | recalc normals, smooth by angle, weighted normal |
| Scattered, misaligned detail | iso views | one validated module, then array |
| Whole model rebuilt and changed | — | edit the part's function, re-run only that part |
| Rework made it worse | compare with previous shot | restore `__prev` copy or checkpoint |
| Everything one colour | material preview | sampled palette, roughness variation, baked wear |
| API error loop | `search_api_docs` | look up the 5.x signature; a fixed error is not a better shape |
| Scale/axis wrong in Godot | asset-pipeline import check | apply transforms, real units, -Y forward |
