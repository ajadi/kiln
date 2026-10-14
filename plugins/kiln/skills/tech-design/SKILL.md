---
name: tech-design
description: How to decide HOW to build something before building it — tech design notes, option matrices (quality, cost, risk, performance, editor-editability, reversibility), risk registers, spikes with measurable pass/kill criteria, and a catalogue of proven approaches for locomotion and IK, destruction, multi-part damage, enemy AI and navigation, visibility/fog, weapons, FPS arms and performance architecture (Godot 4.6/4.7 class names; engine skills map them to Unity/Unreal). Use before any non-trivial system and whenever the team is unsure which approach to take.
user-invocable: false
---

# Technical design

Pick the cheapest option that meets the quality bar and can be reversed; spend novelty only where
it shows on screen. Know the data and the budgets (ms per frame, entity counts) before choosing a
technique. Write the note before the code — short, per feature.

## Tech design note — `design/tech/<id>-<feature>.md` (≤ 2 pages)

```
# TDN-<id>: <feature>      Status: draft|review|accepted|superseded   Date · engine version
1. Problem & player goal — what "good" looks like, observable in game (link design/task).
2. Constraints — engine/renderer/physics, scenes editable in the editor, assets via MCP,
   performance budget (ms, counts), deadline.
3. Non-goals.
4. Options (2–4) — table: Quality | Cost | Risk | Perf | Editor-editability | Reversibility |
   engine classes/addons | evidence (links).
5. Recommendation — why, and what we give up.
6. Risks — risk | likelihood | impact | owner | mitigation | trigger to revisit.
7. Spike — one question; timebox; gym scene; MEASURABLE pass/fail
   (e.g. "foot slip ≤ 10 mm at 1–6 m/s", "40 debris bodies ≤ 2 ms physics"); kill criterion.
8. Data & authoring — which nodes/resources the user edits by hand; editor previews (@tool).
9. Verification — what the acceptance roles will measure.
10. Decision log / revisit triggers.
```

Skip the note when the solution is obvious; write a decision record (`memory/decisions.md`) for
choices that are hard to reverse. The highest-ranked risks become spikes; a spike answers one
question and may kill the feature cheaply.

## Catalogue of approaches (recommended defaults in bold)

### Locomotion
| Option | Notes |
|---|---|
| **Keyframed in-place cycles + speed-synced playback + foot IK** | humans and bipedal mechs; editable AnimationTree; TwoBoneIK3D per leg from a ray hit + pelvis offset |
| Root motion drives the body | feet never slide; less responsive; good for heavy mech starts/stops/turns |
| **Procedural stepping** (per-leg ray targets, step on distance, gait groups, body from foot plane) | spiders, multi-legged, climbing; tune with exported params + @tool previews; TwoBoneIK3D (2-segment) or FABRIK3D/CCDIK3D (3-segment) |
| Motion matching | humanoids with large mocap sets only (third-party in Godot); not for mechs |
Wall climbing: `up_direction` = surface normal (or floating motion mode + custom gravity),
forward + down probe rays for edges, per-surface gravity areas. Spike: foot slip ≤ 10 mm in
motion; a spider crossing a 90° edge without jitter.

### Destruction
| Option | Notes |
|---|---|
| **Pre-fractured meshes + swap-on-break + damage-state meshes + authored support graph** | art-directed, pieces are nodes; Cell Fracture in Blender via MCP; regional async nav re-bake from collision shapes |
| Runtime Voronoi/slicing | CPU spikes, capping/UV problems |
| Runtime CSG | fine for holes/breaches; regenerates mesh and collider each change |
| Voxel world (Teardown-like) | engine-level effort; not feasible in stock engines |

### Multi-part damage
**Per-part hurtboxes (on a hitbox layer, under bone attachments) with a Part node + data
resource (HP, armour, mount HP, multiplier, parent part); explicit `core_transfer` only.** Detach
= hide part, spawn pooled debris body at its transform; notify AI to drop abilities. Death:
physical bones (bipeds) or prepared rigid segments (spiders). Avoid permanently physics-driven
limbs (unstable, costly).

### Enemy AI
| Option | Notes |
|---|---|
| FSM / HSM | predictable, simple |
| **Behaviour trees + HSM (LimboAI in Godot 4.6+), utility scoring inside tasks** | visual editor and debugger; editable |
| Utility AI | good at choosing among options; tuning effort |
| GOAP | emergent, hard to debug |
Navigation: one navigation map per agent size; wall routes as authored paths joined by
NavigationLink3D (agent code performs the traversal); perception = vision cone + budgeted LOS
rays + hearing events with radius + last-known position; attack tokens; cover scored by line of
fire from threats and allies.

### Visibility and atmosphere
Fog of war (top-down) = visibility render-texture mask + shader; in an FPS model AI knowledge
(last-known positions) instead. Atmosphere: **volumetric fog + local fog volumes** for large slow
haze, quad sprites for close smoke.

### Weapons
**Hitscan** (direct ray queries in the physics tick) for bullets; **simulated projectiles**
(manager steps position, ray from previous to current) for rockets/slow rounds; rigid-body
projectiles only for bouncing grenades. Spread patterns in resources; recoil = camera spring +
visual kick; trauma-based rotational shake; pooled tracers, decals and particles.

### FPS arms
**Keyed actions (reload, melee, equip) + procedural sway/bob/recoil springs**; AnimationTree with
state machine, blend spaces, one-shots, filtered blends; aim/look-at modifiers; two-bone IK for
hand-on-weapon.

### Physics domains
Each has its own skill with a method-choice table, costs and an exact-answer check script — load
the one the feature touches before comparing approaches, and ask the physics-expert (or the
anatomy-expert for bodies) for numbers: `rigid-body-physics` (bodies, joints, destruction),
`elements-materials` (heat, fire, water, electricity on materials), `fields-forces` (gravity, orbits,
wind, magnets, beams, large worlds), `fluids-granular` (water, buoyancy, sand, smoke, wind-blown sand and snow),
`soft-bodies` (cloth, ropes, spring bones), `vehicles` (tyres, suspension, handling), `flight` (jetpacks, gliders, aircraft, rotors, fuel weight), `traversal`
(parkour, climbing, hanging, crawling, falls, load, seated and driving poses), `riding` (mounts and
riders), `doors` (doors, curtains, vehicle entry), `weather` (one weather state, rain, snow cover,
fog, lightning), `sky` (sun, moon, stars, day/night and the game clock).

### Performance architecture
**Nodes first for editability; pooling and LOD rules from day one**: pools for enemies, debris,
effects, decals; MultiMesh for casings and rubble; visibility ranges (HLOD) + mesh LOD + occlusion
culling; a collision layer matrix (debris never collides with debris); AI LOD (lower tick rate
with distance, offscreen animation paused); physics interpolation; server APIs only where the
profiler proves node overhead. Budgets written into each note.

## Review of an existing approach

Ask: does it meet the observable goal (measured)? Is the scene still editable by hand? What does
it cost per frame at the worst moment? What happens on the edge cases (slopes, corners, many
enemies, destruction mid-action)? Is it reversible if wrong?
