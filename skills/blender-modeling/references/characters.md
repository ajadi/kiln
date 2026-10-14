# Characters, statues and organic figures

From five humans on one base, a dwarf and a raised-arm statue in the g2 project (report rows in
brackets). The user caught the same shoulder fault three times while the yes/no checklist kept
passing; numbers on silhouettes found it at once. Read this before any human, creature or statue.

## 1. Measure, do not tick boxes

- Every character review set includes **orthographic silhouettes at a stated px/m** from
  `scripts/silhouette_shot.py` (front, back, left, right; the sidecar JSON records the camera), plus
  3/4 front, 3/4 back and top views of every joint and one gameplay-camera shot [42, 60, 78, 91].
- Builder and reviewer run the **same** `scripts/silhouette_measure.py` on the **same** capture, and
  every review target names the metric, the reference segment and the view ("deltoid deviation_cm
  over fit 1.15-1.24, front, >= 1.0") [87, 88]. When an acceptor measured a defect, the builder
  re-measures it the same way before handing off [76].
- A yes/no check ("slope from the neck, no cap above the line") cannot see a tube arm: the outer
  contour from the shoulder point to the elbow was a straight line on all five merchants
  (`deltoid` deviation −1.4..0 cm) [64, 76].

| Read | Measure (`silhouette_measure.py`) | Working target |
|---|---|---|
| Arm reads as a tube plugged into a ball | `deltoid` on the front and back views | deviation ≥ +1 cm over the upper-arm line; corner ≤ 25° per 2 cm at the shoulder point |
| Puffed sleeve cap above the shoulder line | `contour` of the shoulder: no point of the cap above the trapezius line | 0 points above |
| See-through wrist, neck or ankle join; garment ending above a boot | `holes` on front/side/back (and `mesh_qa.py` daylight on the joined set) | 0 enclosed holes that are not designed openings |
| Arm glued to the belly in the rest pose | `gap` between arm and torso over the upper-arm height | contact only at the armpit |
| Wrist slit / pinched wrist | `width --min-between` over the forearm | ≥ the reference wrist width |
| Raised-arm V between arm and trapezius | `chord-angle` of the top contour (arm top line vs trapezius chord) | ≥ 140° |
| Bideltoid | `width --z <shoulder height>` | within the male/female norm of the model sheet |

- Silhouette IoU on the A-pose does not separate humans that share a skeleton (the arms dominate:
  12 crowd looks scored 0.78–0.90 against some merchant). Compare silhouettes on the idle pose or
  with the arms masked, and add a value check per band at 128 px (head / torso / legs mean value;
  image-to-model `value_bands.py`) so "differ on 2+ axes" is measured, not argued [99].

## 2. Shoulders, before any garment

- Build the shoulder girdle as anatomy first: clavicle and trapezius slope from the neck, the
  deltoid cap over the arm root (front, side and rear heads), the armpit fold, and the arm leaving
  the torso at an angle. A garment follows the body: set-in sleeve seam just below the acromion,
  raglan, dropped or kimono/dolman cuts each drape differently over the cap; the armhole wraps the
  cap, it does not cut through it [42, 48, 60].
- Raised arm (abduction > 90°): the shoulders are no longer symmetric — the clavicle rises by
  about 0.025 × its length per 10° beyond rest, the trapezius slope flattens to ≤ 12°, the deltoid
  cap grows 10–20 % over the shaft, the V between arm top and trapezius stays ≥ 140°, and the
  elbow is not a ball [71].
- Statues and idle figures: pelvis tilt 3–4°, head offset from the axis, free knee 10–15°; the
  mannequin axis (head, neck, hem centre within 1 px, level belt) reads dead [71].
- Show the four shoulder views at the first WIP of the first character and get the anatomy-expert's
  glance then, not after all five characters [48].

## 3. Organic figures from a signed-distance model

For statues, creatures and any organic figure, build a bare anatomy field first, then cloth as
offsets [66]:

1. Primitives as signed distances (numpy, outside Blender): round cones and ellipsoids for neck,
   trapezius, deltoid, upper arm, chest, armpit; joined with a smooth minimum (blend radius per
   joint) — neck → trapezius → deltoid → arm, chest → deltoid. A two-bone IK places a raised arm.
2. Cloth as offset surfaces of the body field (smooth-max windows for openings).
3. Marching cubes (`skimage.measure.marching_cubes`) at ~6 mm, import into Blender through the MCP,
   decimate (31 k tris for the g2 statue), smart UV. numpy and scikit-image run in system Python, not
   in Blender's.
4. Measure the parameters on a projected silhouette of the field in numpy (seconds per pass, no
   bake) with the same metric definitions as `silhouette_measure.py` [87].

## 4. Garments over joints

- A vest that must wrap a shoulder cap: one sleeve loft whose cap profile is **solved** from a target
  front contour (per ring, a ray from the arm axis to the curve); push the torso garment onto the
  sleeve tube radially in the ring plane; cut the armhole at an armscye plane; then hug and re-cut a
  second time (the first cut leaves chords the sleeve pokes through); subdivide locally near the arm
  [114].
- bmesh `solidify` with a negative thickness went **outward** on inconsistent winding: orient faces
  first and measure the offset after solidify. A "deep inside" clip punches holes whose edges show
  on the sleeve [114].
- Limb paths: a 4-point Catmull-Rom with a 2 cm first segment overshoots at the joint, so distance
  along the arm runs backwards there (the old shoulder "ball" and a 2 cm wrist gap came from it).
  Use chord-length parameterisation or straight segments [77].
- Joined meshes hide gaps from per-object checks: run `mesh_qa.py` (daylight on the joined set) and
  `silhouette_measure.py holes` after joining [100].

## 5. Hair, beards, brows: cards that pass review

Solid mesh locks read as plastic (the user rejected an approved beard) [38]. Strand cards
improvised per character failed 6 of 6 reviews: stepped edges and skin gaps, a flat cardboard plate,
wire-like zig-zag strands, a saw-tooth cheek line, a solid black mass, sticker tufts [80]. The recipe
that passed (g2 hairkit, five characters) [90]:

| Failure | Fix |
|---|---|
| Cardboard plate / grey shelf | a **mass shell** on the scalp or jaw in the cards material, tinted to the hair colour; its v = geodesic distance from the shell boundary into the atlas mass strip, so every boundary (hairline, cheek line, nape, under the jaw) ends in ragged tapered strands; offset 0.6 mm at the boundary rising inside (no step) |
| Wire / zig-zag strands | clump paths integrated as one gentle arc (growth direction bent toward a fall vector), pushed out of the head with a BVH nearest-point test and Laplacian-smoothed — never re-project every row onto the surface; parallel-transport the ribbon frame (no twist flips); width ramps up from a narrow root that starts under the mass |
| Saw-tooth cheek line | staggered rows: ±30 % jitter of length, width, root height and spacing, alternating atlas tiles; a painted stubble band under the edge |
| Black solid mass | `--light-frac` lighter strands and a lifted base colour |
| Sticker tufts | hairline clumps sweep away from the face (a hug term pulls them onto the scalp) |
| Grey hair at distance, white dashes along strands | the atlas colour under alpha 0 and at strand edges = the strand's colour (dilated); `card_atlas.py check` (light edge texels 36 % → 0 % in g2) [57, 115] |

- Atlas: `scripts/card_atlas.py make` (tiles, mass strip, dilation, normal, ORM); `check` on any
  atlas before review; a distance render at 3 m before approval [57].
- Traps: lookup tables that clamp past their last entry let a beard region wrap round the back of
  the head (the "helmet" shelf) — bound regions explicitly; short cards (brows) that map the full
  tile land in its sparse tip zone and vanish — give them a v window in the dense mid-section [90].
- Porting to another character: atlas layout and colour sets are parameters; a 2-colour head stacks
  two atlases; mass shells offset by vertex normals fan out at a ring-grid pole (a 1 cm "chimney"
  on the crown) — re-project them onto the skull; a long beard needs a path with control points
  root → envelope → collar, pushed and smoothed [115].
- glTF/Godot: alpha MASK via a Math GREATER_THAN node (cutoff ~0.42), double-sided, 2 material
  slots on one mesh (skin, cards). `materials.clear()` after merging resets every face's
  `material_index` to 0, and `bmesh.to_mesh` clamps `material_index` to the existing slots — add
  slots before writing indices [38]. Godot ignores `KHR_materials_specular`: set
  `metallic_specular` ~0.1 on the cards material after import or strands look grey (engine-godot
  `references/mcp-and-editor.md`) [58].
- Review: 5 views + a two-shot + a 3 m shot, and the reads-wrong list above as checks [80, 90].

## 6. Review renders, the shared Blender, bakes

- A helper that toggles collections must not switch off the review lights: one "final" set
  rendered unlit with no error. Every lit review shot logs the number of lights that render and
  stops when it is 0 [77].
- Every review render records its camera (sidecar JSON: type, ortho scale or focal length, px/m
  at the subject plane, view name); `silhouette_shot.py` does it, and measuring scripts read it.
  A shot that kept a setting from the previous perspective shot was 568 px/m, not the 947 the
  render settings implied [78, 91].
- One Blender is shared between sessions and roles: start every modeling call by asserting
  `bpy.data.filepath` is the asset file you expect (re-open it if not), save the asset after every
  milestone, and never save over another agent's file. g2: a statue was built inside the
  merchants' open `npc.blend`, and their 40 meshes printed AO onto its bakes [84].
- Bake each asset alone: Cycles AO and normal bakes see every visible mesh — a plinth, the ground,
  a held prop or another asset prints dark bands. `hide_render` alone did not remove an object from
  the AO rays; moving it 500 m away did. Park everything else far away, bake, restore [85]. After
  moving overlapping looks apart for a bake and back, re-check `matrix_world` (it stayed stale until
  the depsgraph updated) [102].
- Long jobs: `execute_blender_code` times out (~5 min bake) while Blender keeps working and the
  result is lost. Chunk bakes to ≤ 150 s per call and keep results in `bpy.app.driver_namespace`
  for the next call to read [142].
- `bmesh.ops.create_icosphere(subdivisions=1)` is the 20-face icosahedron, not the UI's 80-face
  sphere; a lat-long sphere (8 × 5 = 64 tris) with radial custom normals
  (`mesh.normals_split_custom_set_from_vertices`) shades smooth at a third of the cost of
  subdivision 2 [86].

## 7. Review cost

- One hero-prop art round took 3–4 agent runs of ~1.5 h each. Spend the first review on the top 5
  deltas against the references before texturing; texture only an approved shape [16].
- The art director cannot frame a 36 cm prop in the Godot editor through the MCP; it judges from the
  modeler's renders, partly blind to in-engine lighting and scale. Give it in-engine cinematic
  captures from a placed Camera3D (engine-godot `references/mcp-and-editor.md`, Screenshots) next to
  the Blender renders [14].
