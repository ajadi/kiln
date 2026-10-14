---
name: soft-bodies
description: Cloth, ropes, cables, chains, hoses, hair, tails, spring bones and squishy bodies for games — choosing a method (Verlet with constraints, PBD, XPBD, shape matching, spring bones, bone chains), substeps vs iterations, long-range attachments against stretch, bending, collision and self-collision cost, pinning to animated bones without jitter, teleports, budgets, the exact pendulum/catenary/spring answers and stretch, energy and settle checks in soft_check.py, and what Godot's SoftBody3D under Jolt really builds (from its source), SpringBoneSimulator3D, Unity Cloth and Magica Cloth, Unreal Chaos Cloth, Cable and AnimDynamics. Use when designing, building or reviewing capes, flags, clothing, ropes, cables, hair, tails, jiggle or anything that bends and swings.
user-invocable: false
---

# Soft bodies, cloth and ropes

Real cloth and rope barely stretch; game solvers stretch when they run out of iterations. Most of
the craft is spending a fixed budget on substeps and the right constraints, and pinning the
simulation to animated characters without jitter. Prove each setup with
`${CLAUDE_SKILL_DIR}/scripts/soft_check.py` (stdlib Python, Bash). Values marked (working) are
starting points.

## 1. Choose the method

| Need | Method | Notes |
|---|---|---|
| Hair strands, tails, ponytails, antennas, loose straps, earrings | spring bones on the skeleton | cheapest, animator-tunable; Godot SpringBoneSimulator3D, Unreal AnimDynamics / Kawaii Physics, Unity Magica BoneSpring |
| Capes, skirts, flags, banners, sails | particle cloth (PBD/XPBD) on a mesh, pinned to bones | substeps + long-range attachments; self-collision only if visible |
| Ropes, cables, chains, hoses | particle chain (Verlet/XPBD) with distance constraints | wraps around colliders (Naughty Dog's Uncharted 4 / TLOU2 rope); Source engine ropes are Verlet nodes at a fixed step |
| Bridges, hanging platforms the player stands on | rigid bodies + joints, or kinematic with a solved curve | gameplay-critical: stable and predictable beats soft |
| Jelly, tyres, flesh jiggle | shape matching or tetrahedral XPBD; jiggle bones for flesh | cheap jiggle bones cover most characters |
| Designed swinging (web-swing, grapple) | pendulum maths + designed forces | Spider-Man started from a textbook pendulum, then added forces for feel |

## 2. Solvers in one page

1. **Verlet + constraints** (Jakobsen, Hitman): velocity implicit in the last two positions,
   constraints relaxed 1–10 times, collisions by projecting points out; "for most cloth one
   iteration is necessary".
2. **PBD** (Müller 2006): unconditionally stable, but stiffness depends on the iteration count
   (residual (1 − k)^n) and the time step — a PBD stiffness is not a material value.
3. **XPBD** (Macklin 2016): compliance α (inverse stiffness, α̃ = α/Δt²) makes stiffness physical
   once the solve converges; with too few iterations it still looks stretchy.
4. **Substeps beat iterations** (Macklin 2019 "Small Steps"): n substeps × 1 iteration beats
   1 step × n iterations at similar cost (150k-particle cloth: 30 iterations 12.4 ms and stretchy,
   30 substeps 13.5 ms and far stiffer). A 2 m hanging chain released sideways: 1×10 stretches
   4.1%, 10×1 0.5%, 50×1 0.01%.
5. **Long-range attachments (tethers/LRA)**: a one-sided max distance from each free particle to its
   pin; kills sag-stretch for a fraction of the cost of iterations (1500-vertex dress ~0.9 ms on one
   core). They help far less when pinned only at corners — stress concentrates there.
6. **Bending**: a distance constraint across one vertex (cheap, weak when flat) or a dihedral
   constraint (stronger, costlier).
7. **Explicit springs explode** when ω·Δt ≥ 2 (`predict spring` gives dt_max = 2/ω): k 10⁴ N/m on
   10 g needs Δt < 2 ms; at 60 Hz it blows up in a second. Use PBD/XPBD or substeps instead.

## 3. Numbers

- Real fabrics hardly stretch under their own weight; aim for < 1% strain at rest, ≤ 2–5% peak in
  fast motion (`strain --max 0.02`, working). Steel wire rope ~0.24% elastic at working load;
  nylon rope 4–6% bedding-in stretch.
- Fabric weight (approximate): chiffon 40–70 g/m², poplin 120–150, T-shirt 160–190, denim 200–400+,
  canvas > 300; 1 m² of 150 g/m² on a 32×32 grid = 0.15 g per vertex.
- Pendulum T₀ = 2π√(L/g) (1 m: 2.006 s; 2 m: 2.837 s); exact T = T₀/AGM(1, cos(θ₀/2)): +0.19% at
  10°, +1.74% at 30°, +18% at 90° (`predict pendulum`, `period`).
- Catenary y = a·cosh(x/a), L = 2a·sinh(S/(2a)): a 12 m chain over a 10 m span has a = 4.695 m,
  sag 2.923 m, end slope 52°; the parabola estimate is 6% low (`predict catenary`, `sag`).
- Spring-mass f = √(k/m)/(2π), damping ratio ζ = c/(2√(km)).
- Budgets: ~5 ms of total physics per frame (LRA paper); a 1500-vertex garment ~1 ms per core;
  NvCloth-style solvers run 120–300 iterations per second (240 = 4 per 60 Hz frame); self-collision
  is "a significant amount of the overall simulation time"; GPU cloth was >10× faster for Ubisoft.

## 4. Collision, pinning, teleports

1. Tunnelling limit v_max ≈ r·n_sub/Δt (2 cm particles at 60 Hz: 1.2 m/s with 1 substep, 6 m/s
   with 5) — substeps, not CCD, are the usual fix; CCD roughly doubles cost.
2. Cloth collides with simple proxies (spheres, capsules, two-sphere tapered capsules) on the
   character's bones — never the render mesh.
3. Pinned to animated bones: simulate in the character's local space and scale down inherited
   inertia (Chaos velocity scales, Unity world velocity/acceleration scale, PhysX local frame) —
   otherwise every run cycle whips the cape. Free vertices lagging the pinned ones in Godot is an
   open issue (#107061).
4. Teleports and cuts reset the simulation (Unreal `ForceClothNextUpdateTeleportAndReset`,
   Unity `Cloth.ClearTransformMotion`, Godot: re-pin or reset the body).
5. Fixed time step plus substeps; never feed a variable frame time into cloth.
6. **Baked skirts on a shared rig** (no runtime cloth): drive 8 two-segment columns around the hem
   at bake time with a clearance solver — per frame, push each column out of the leg capsules
   (thigh and shin, swing leg included), let it hang under gravity, keep it above the floor, and
   rate-limit its motion between frames; a seated mode lays the front panel along the thighs and
   drops it from the knees. Failure modes seen in g2: 4 columns tore the hem at the diagonals;
   leg weights instead of columns turned the skirt into trousers; the hem cut 15–29 mm into the
   swing thigh and 4 cm under the floor in a run without the solver (animation reads-wrong 11).

## 5. Lab gyms

| Check | Gym | Command | PASS |
|---|---|---|---|
| Pendulum | weight on a 1 m and 2 m rope released at 30° | `period --expected` (from `predict pendulum`) | within 3% (1% for gameplay ropes) |
| Hanging rope | rope of known length between two posts | `sag` | sag within 5% of the catenary |
| Cloth stretch | cape pinned on a running, jumping character; flag in strong wind | `strain --max 0.02` | max edge strain ≤ 2% (p95 ≤ 1%) |
| Energy | release the rope/cloth and let it swing | `energy` | never rises after release |
| Settle | character stops; cloth comes to rest | `settle --below 0.05 --max-s 10` | at rest within 10 s |
| Collision | cape against legs in a sprint; rope over a beam | penetration count from an overlap probe | none visible |
| Budget | all simulated characters in the heaviest scene | optimization skill | within the physics budget |

## 6. Review checklist

- [ ] Cheapest method per piece (spring bones before cloth before soft bodies).
- [ ] Substeps preferred over iterations; LRA/tethers on capes and ropes; bending where folds show.
- [ ] Collision proxies on the bones; self-collision only where visible and budgeted.
- [ ] Local-space simulation and reduced inertia for anything pinned to an animated character.
- [ ] Teleport/reset wired to respawns and cuts; fixed step.
- [ ] Explicit springs checked against dt_max = 2/ω.
- [ ] Lab gyms pass; cost measured on the target machine.

## 7. Engine notes

**Godot 4.6/4.7**
- **SoftBody3D under Jolt** (the default physics for new 3D projects since 4.6; recommended over
  GodotPhysics3D for soft bodies). From `modules/jolt_physics/objects/jolt_soft_body_3d.cpp`:
  `simulation_precision` becomes Jolt's iteration count and each iteration is an XPBD substep
  (dt/precision); `linear_stiffness` k maps to compliance Δt_sub²·(1/k − 1)·(w₁ + w₂), so k = 1 is
  perfectly stiff edges; **no bending constraints and no long-range attachments are created**,
  though Jolt supports both — capes from SoftBody3D sag and crumple; vertices at the same position
  are merged and mass is spread evenly; pinned vertices get zero inverse mass. Jolt soft bodies
  collide with rigid bodies, not with each other. Defaults: precision 5 (keep ≥ 5 or it collapses),
  total_mass 1, linear_stiffness 0.5, damping 0.01; `drag_coefficient` unused. Pin with
  `set_point_pinned(index, true, attachment_path)` (pin to a BoneAttachment3D, set
  `parent_collision_ignore`). Physics interpolation does not apply to soft bodies — raise the tick
  rate for smoothness. Area3D wind reaches Jolt soft bodies from 4.7 (PR #114198). Open issues:
  lag behind pins (#107061), damping differs from GodotPhysics (#105987), pinned indices vs merged
  vertices (#26611), stretch at speed (#80738), blend shapes (#113308).
- **SpringBoneSimulator3D** (4.4+, a SkeletonModifier3D from VRMSpringBone): stiffness (default 1.0),
  drag (0.4), radius (0.02), gravity (a speed, default 0), rotation axis, `center_from`;
  SpringBoneCollision3D colliders; no branched chains; do not scale it. Built in the editor on the
  character's skeleton (scene-first).
- **Ropes**: RigidBody3D chain + PinJoint3D stretches under fast motion; a Verlet rope in script
  (e.g. MIT "Verlet Rope 4 .NET", 4.4+) or a bone chain with SpringBoneSimulator3D is steadier.
- Ragdolls: PhysicalBoneSimulator3D (4.3+), rigid-body-physics skill.

**Unity 6** — Cloth component: skinned meshes only, one-way coupling, sphere/capsule/conic-capsule
colliders, tethers, solver frequency, world velocity/acceleration scale, continuous collision,
virtual particles; self/inter-collision costly; `ClearTransformMotion()` on teleports. Magica
Cloth 2 (paid; BoneCloth, MeshCloth, BoneSpring).

**Unreal 5.6–5.8** — Chaos Cloth: Panel Cloth Editor (5.3+, Dataflow, optional XPBD, level-set
collision); iteration count, max iterations and subdivision (substeps); local-space simulation;
tether stiffness/scale (LRA); linear/angular velocity scales; CCD; self-collision thickness. Cable
component: Verlet particles, iterations set stiffness, world collision experimental and costly.
AnimDynamics (no collision, limits only; avoid world space with teleports), RigidBody anim node
(Physics Asset), Kawaii Physics (AnimGraph node; 5.8 support UNVERIFIED).
