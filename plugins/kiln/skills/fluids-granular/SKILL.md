---
name: fluids-granular
description: Water, buoyancy, waves, flowing liquids, sand, snow, mud and smoke for games — choosing the method by need and hardware (visual-only surfaces, Gerstner and FFT waves, heightfield shallow water with virtual pipes, particle fluids SPH/PBF/FLIP, grid smoke, cellular automata, heightfield sand with angle of repose, deformable mud), buoyancy with sample points that match the visual waves, drag and damping, conservation and CFL limits; wind, sand and snow (saltation thresholds, sand and snow flux, windward erosion and lee deposition, dunes and ripples, tracks filled by wind, sandstorms and particle budgets, snowfall, settling, footprint depth by load, blowing snow, drifts and cornices, avalanche release and runout, melt) with time compression per process; iGPU budgets, exact test cases checked by fluid_check.py, pitfalls and Godot/Unity/Unreal setup. Use when designing, building or reviewing anything with water, floating objects, boats, liquids, sand, dunes, snow, footprints, drifts, avalanches, sandstorms, mud, gas or smoke.
user-invocable: false
---

# Fluids and granular matter

Most shipped games fake most of their water: a rendered surface, a wave function the CPU can
also evaluate, and buoyancy at a handful of sample points. Real simulation is reserved for small,
visible, interactive pieces. Pick the cheapest method that supports the gameplay, prove it with
`${CLAUDE_SKILL_DIR}/scripts/fluid_check.py` (stdlib Python, Bash). Values marked (working) are
starting points.

## 1. Choose the method (tech-design decides)

| Need | Method | Cost | Shipped example |
|---|---|---|---|
| Lakes, rivers that look right | shader surface + flow map + normal-map waves | GPU only | Uncharted 3/4 (flow field + wave particles, no fluid sim), Journey (sand is rendering only) |
| Open sea with boats | Gerstner (few waves) or FFT spectrum, CPU evaluates the same function for buoyancy | GPU + small CPU | Sea of Thieves, Atlas, Just Cause |
| Water that flows, floods, fills | heightfield shallow water, virtual pipes (Mei et al.) | 256² ≈ 1.3 ms on an old GPU | Sea of Thieves on-deck water, From Dust |
| Splashes, pouring, small pools | particles: SPH, PBF, FLIP | heavy; small counts on iGPU | FleX demos; Godot SPH addon |
| Smoke, gas | 2-D/3-D grid (Stam stable fluids) or particles | grid cost; dissipative | Niagara Fluids (2-D for games) |
| Sand, snow piles, erosion | heightfield relaxation to the angle of repose | cheap | thermal erosion tools |
| Wind-blown sand and snow, tracks, drifts, storms, avalanches | §7 | §7 | Batman: Arkham Origins, Journey |
| Mud, deformable ground | separate physics and render heightmaps, wheels "draw" into a mask | CPU + GPU | Spintires/MudRunner (16 m blocks, 128² mud texels only where mud is) |
| 2-D pixel worlds | cellular automaton | chunked + threaded | Noita (64×64 chunks, dirty rects, 4-pass checkerboard) |

On an Intel UHD 630 (~400 GFLOPS, ~1/8 of a GTX 680) scaled estimates are ~8–16k PBF particles
in 4–8 ms (UNVERIFIED) and a 256² pipe-model grid in ~1–2 ms; Godot compute needs Forward+ or
Mobile, not Compatibility.

## 2. Buoyancy and floating

1. Archimedes: F = ρ_f·g·V_submerged; at rest the submerged fraction is ρ_body/ρ_fluid (pine 500
   → half; ice 917 → 92% in fresh water, 89.5% in sea water; steel sinks). Fresh water 1000,
   sea water ~1025 kg/m³.
2. Per sample point (hull points, pontoons): each sample is a water column with force
   ρ·g·area·depth below the local surface, applied at the point (Atlas, Unreal pontoons: ≥ 4 for
   a stable object).
3. **The query must match the visuals**: evaluate the same wave function on the CPU from shared
   parameters and absolute time; with choppy (horizontally displaced) waves, find the height at a
   world point with a few fixed-point steps `D = displacement(P − D)` (Atlas; Unity's sample uses
   8 iterations). GPU readback lags frames — use it only where lag is invisible.
4. **Jitter**: per-sample forces are noisy, worse at low tick rates (Atlas's server ran < 10 Hz).
   Fix with more samples plus damping, or fit a plane to the samples and spring the body toward it
   (Atlas). Add linear and quadratic damping; cap the buoyant force.
5. Heave period of a floating box ω = √(ρ_f·g·A/m) = √(g/draft) (1 m pine cube: 1.42 s) — real
   bodies bob slower because of added mass (a sphere carries half its displaced mass extra).
6. Drag in water F = ½ρv²·Cd·A (sphere 0.47, flat plate 1.28) — 800× air density, so water drag
   dominates quickly.

## 3. Waves

- Dispersion ω² = g·k·tanh(k·h): deep water (h > λ/2) c = √(gλ/2π), group speed c/2; shallow water
  (h < λ/20) c = √(gh). λ 10 m deep: T 2.53 s, c 3.95 m/s (`predict wave`, `wave`).
- Gerstner (GPU Gems 1): 4 geometric waves + ~15 normal-map waves, wavelengths 0.5–2× the median;
  keep Σ Qᵢ·ωᵢ·Aᵢ ≤ 1 or the surface loops above the crests (cusp at k·a = 1, H/λ = 1/π); real
  waves break near H/λ ≈ 0.142.
- FFT (Tessendorf): Phillips spectrum, periodic tiles; split into frequency bands to hide tiling
  (Atlas). A spectral ocean depends only on time and spectrum — deterministic across clients.

## 4. Flowing water (heightfield)

1. Virtual pipes: per-cell outflow f += dt·A·g·Δh/l clamped ≥ 0, scaled by
   K = min(1, d·lx·ly / (Σf·dt)) so no cell goes negative — flux form conserves volume to rounding.
2. Stability (CFL): (u + √(g·h))·dt/dx ≤ 1; dx 0.25 m at 1 m depth → dt ≤ 80 ms (`predict cfl`).
   Ten Minute Physics #20 caps wave speed at 0.5·dx/dt.
3. Reference answers: communicating vessels settle at one level whatever their shapes
   (`levels`); Torricelli v = √(2gh) (×0.65 for a real round hole), drain time (A/a)·√(2H/g);
   dam break (Ritter) front 2√(g·h₀), depth at the dam 4/9·h₀ — measure the front at a depth
   threshold (1% of h₀), the dry tip always lags (`predict efflux|dambreak`).
4. Volume drift budget: conservative schemes hold total volume to ~1e-4 relative over 10 min at
   60 Hz in float32 (`conserve --tol 1e-4`, working).

## 5. Particle fluids

- SPH (Müller 2003): poly6 kernel for density, spiky for pressure; PBF (Macklin & Müller 2013):
  incompressibility as position constraints, artificial pressure, vorticity confinement, XSPH
  viscosity; FLIP for less dissipation. Godot asset "3D SPH Fluid Simulation" (MIT, 4.6): 40k
  particles by default on the main RenderingDevice, writes a MultiMesh, collides with a baked SDF,
  non-SI parameters, no rigid-body coupling — test on the target GPU before relying on it.
- Surface reconstruction (marching cubes) can cost more than the simulation; screen-space fluid
  rendering is the cheap alternative.

## 6. Sand, snow, soil

1. Angle of repose: dry sand 34°, wet sand 45°, saturated sand 15–30°, crushed gravel 45°, natural
   gravel 25–30°, snow 38°, flour 45°, soil 30–45°; tan θ ≈ static friction for cohesionless grains.
2. Heightfield relaxation (thermal erosion): move material to lower neighbours only where the
   slope exceeds tan θ, a fraction < 1 of the excess per step, outflow scaled like the pipe model;
   settles in hundreds of iterations, conserves volume to rounding. 4 neighbours make diamond
   piles — use 8 with √2·dx diagonals for round ones (`repose`).
3. Particle sand needs friction applied at position level (FleX) or piles creep and collapse.
4. Deformable ground: write deformation into a mask/heightmap (Spintires wheels draw into a render
   target); collision must be updated separately and in chunks — runtime heightmap collider
   updates are expensive (Godot HeightMapShape3D; Terrain3D has dynamic collision around the
   camera).

## 7. Wind, sand and snow

Wind moves sand and snow only above a threshold, the flux grows with the cube of the wind, and
what it builds lives on time scales from minutes (a print fills) to centuries (a dune field).
Numbers, algorithms, games and engine detail: `${CLAUDE_SKILL_DIR}/references/wind-sand-snow.md`.
The weather skill owns the global wind, precipitation, wetness and the visibility controller;
heat for melting is in the elements-materials skill.

| Need | Method | Cost | Shipped example |
|---|---|---|---|
| Dunes and snowfields that look right | authored terrain + shader: wind-aligned ripple normals, glitter, sastrugi | GPU only | Journey (sand is rendering) |
| Tracks that fill or fade | trail texture (orthographic camera from below, or compute), refilled per second | < 1 ms, 2–4 MB per surface | Batman: Arkham Origins, Rise of the Tomb Raider |
| Snow cover that rises and melts | one depth value + cover blend tanh(h/0.1 m) + normal and shelter masks | GPU only | — |
| Drifts, buried objects, local erosion | heightfield transport near the player: hops, lee shadows, repose relaxation | 64² GDScript or 128² compute at 2–10 Hz | Desertscapes (512² 0.46 ms/step, RTX 4080) |
| Dune fields that move | Werner slab model offline or at a huge K; swap states behind a storm | offline | Dune: Awakening (weekly storm reshapes the map) |
| Sandstorm, blizzard | fog extinction + camera-following GPU particles | overdraw-bound | BotW Gerudo sandstorm |
| Avalanche | release check → heightfield flow + powder particles, stop at the α line | event | — |

1. **Threshold with hysteresis.** u\*t = A·√((ρp − ρa)/ρa·g·d), A 0.10 to start, 0.082 to keep
   going: 0.25 mm sand 0.23 / 0.19 m/s, a 10 m wind of 5.3 / 4.3 m/s (log law
   U = u\*/0.4·ln(z/z0), z0 1 mm). Start at the first, stop below the second, or gusty sand
   flickers (`predict saltation`). Snow at 10 m: fresh cold 4–5 m/s, dry 7.7, wet 9.9, rising as
   it ages (`predict blowsnow`).
2. **Flux ∝ u\*³.** Bagnold, Kawamura and Lettau differ ~2× (u\* 0.4: 0.014–0.028 kg/m/s, ~52–100 kg
   per metre per hour); doubling u\* gives 8× the flux; zero below the impact threshold —
   Bagnold's formula alone has none. Snow: Pomeroy & Gray (`predict sandflux|blowsnow`).
3. **Erode windward, deposit leeward.** The gentle windward slope (10–15°) speeds the wind up;
   it cannot reach the lee shadow below a 15° line from the crest; relax to the angle of repose
   (34°) so a slip face forms; flux form conserves volume. Dunes move c = q/H — small dunes
   overtake big ones; nothing under ~13 m wide is a dune (`predict dune|werner`, `lee` check).
   Ripples: 7–14 cm apart, height ≈ wavelength/15, crests across the local wind — align ripple
   textures with the global wind (`predict ripple`).
4. **Tracks fill** in t = L·D/(q·trap) (L along the wind, D deep, trap = share of grains that
   stay): a 28 × 3 cm sand print at u\* 0.4 takes ≥ 15 min, a 30 × 10 cm boot print in dry snow
   ≥ 34 min. Fill from the upwind wall; never dig a print out again (`predict fill`, `fill`).
5. **Storms.** Extinction σ = 3.912/visibility (Godot exponential `fog_density` = σ): sandstorm
   < 1 km, severe < 200 m. Put most of it in fog; particles of size s at density n in a sphere of
   radius R add n·s²·(R − near) layers of overdraw — ≤ 2 on an iGPU (working) (`predict storm`).
   Keep a direction cue: BotW's sandstorm turns the map to static and statues show the way.
6. **Snow.** New snow 50–70 kg/m³ in calm, damp 100–200, settled 200–300, wind-packed 350–400;
   game default 100. Depth = rate × time (moderate 2.5 cm/h; NWS heavy 10 cm in 12 h); water
   equivalent = depth × ρ; settling ρ → 300 cold / 500 melting with τ 200 h, depth falling with
   water kept (`predict snowfall|settle`, `accum`).
7. **Prints by load.** To a firm base z = h·(1 − ρ0/ρf), ρf 500 kg/m³ below 210 kPa (CRREL): an
   80 kg person (26 kPa) in 30 cm of fresh snow sinks 24 cm. Deep soft snow stops at a compaction
   bulb — measured boots 11.8 ± 6.2 cm, snowshoes 5.7 ± 2.2 cm in ~1 m snow — cap it per snow
   type (`predict footprint`). Print depth drives foot IK, the trail and a speed or stamina factor
   (boots 6.5 METs vs 4.0 on packed snow).
8. **Drifts and cornices.** Behind a 50 % porous fence of height H: 30H long, 1.2H deep, 19.3H²
   (Tabler) — 34 t per metre for a 2 m fence, weeks of blowing (`predict drift`). Cornices build
   out over the lee and break back behind the visible lip — telegraph it.
9. **Avalanches.** Slabs release on 30–45° (human triggers peak near 38°), run on 20–30°, stop
   below 20°. Release when weak-layer strength < ρ·g·h·sin ψ·cos ψ (+ 0.14/h kPa for a skier):
   S < 1 releases, > 1.5 holds. Runout α = 0.97β − 1.4° (SD 3.5°) gives the stop line (`predict
   avalanche`, `release`, `runout`). Noise does not trigger avalanches — a design that says so
   must telegraph it and stay consistent.
10. **Melt.** t = water equivalent × 334 kJ/kg / net power — 10 cm of fresh snow melts in 3.1 h
    at 300 W/m² (`predict melt`); heat sources and their compression: elements-materials skill.
11. **Compress time per layer, not once.** A sand print fills in 15 min, a 2 m drift in ~40 days,
    a 3 m dune moves 1 m in 11 days, a dune field re-forms in decades. Run the player-scale layer
    (prints, snowfall, melt) on the world clock (K 10–100, the same as the day cycle) and the
    landform layer at K 10⁴–10⁶ where nobody watches grains, or as state swaps off-screen and
    behind storms. Write each K into the tech-design note (`--game-s` prints it).
12. **Budgets (iGPU).** Trail texture 512² ×2 ≈ 1 MB, < 1 ms; transport grid 64² in GDScript or
    128² compute at 2–10 Hz; storm overdraw ≤ 2 layers (working); collision only where depth
    changes play, in chunks. **Pitfalls**: one K for everything; transport per frame; flux with no
    threshold; no repose relaxation (spikes) or no lee shadow (no slip face); trail texture not
    re-centred in whole texels (prints swim); snow under roofs; prints that ignore density;
    avalanches on any slope; storms with no direction cue; big sprites at the camera.

## 8. Smoke and gas

Stam's stable fluids: semi-Lagrangian advection + implicit diffusion, unconditionally stable but
dissipative (fine for games); 2-D slices or low-res 3-D grids; Niagara Fluids recommends 2-D for
games and baking 3-D to flipbooks. Most game smoke is particles with curl noise — simulate only
what the player pushes through.

## 9. Lab gyms

| Check | Gym | Command | PASS |
|---|---|---|---|
| Floating | cubes of ρ 500 and 917 dropped in still water | `float --fraction` | draft within 5% of a cube's height, bobbing ≤ 2% after 5 s |
| Wave match | buoy riding the visual waves | `wave --wavelength [--depth]` | period within 5% of dispersion |
| Vessels | two connected tanks, uneven start | `levels` | final levels within 2 cm |
| Conservation | closed basin, 10 min | `conserve --tol 1e-4` | drift ≤ 1e-4 |
| Stability | design dx, dt, depth, speed | `predict cfl` | stable |
| Sand | pour a pile | `repose --angle` | p99 slope within ±3° of the material's angle |
| Wind threshold | wind ramped up then down over flat sand | `predict saltation` vs the logged start/stop u\* | starts within 10% of u\*ft, stops within 10% of u\*it; no start below u\*ft, no stop above u\*it (working) |
| Print fill | one print, steady wind, stated K | `fill --expect-s` from `predict fill` ÷ K | fill time within 25%; never deepens again |
| Lee deposition | a dune heightfield exported twice under a steady wind | `lee --wind [--speed --dt-s]` | ≥ 70% of deposition downwind of the crest and of erosion upwind; volume ≤ 0.1%; lee ≤ 37°; moves downwind (speed within 30% of K·q/H) |
| Snowfall | open plot, steady snowfall, stated K | `accum --rate --k` | depth rate within 15% |
| Print depth | walk across 10 / 30 cm of fresh and packed snow | foot probe vs `predict footprint` | within 20% or the stated cap (working) |
| Avalanche release | slab ramp 25–50° in 5° steps, same load | `release --band` | no release outside the band; S < 1 releases, S > 1.5 never |
| Runout | avalanche on a profile of known β | `runout --beta` | α within 2 SD (±7°) |
| Storm | heaviest storm on the target iGPU | `predict storm` + optimization skill | overdraw ≤ 2 layers (working), frame budget held |
| Budget | heaviest water scene on the target machine | optimization skill | within the frame budget |

## 10. Review checklist

- [ ] Method per need chosen in tech-design, with its cost on the target GPU (iGPU counts!).
- [ ] One wave function shared by the shader and the CPU query; choppy waves inverted.
- [ ] Buoyancy samples ≥ 4 per body, damping, force cap; no jitter at the shipped tick rate.
- [ ] Flux-form water conserves volume; CFL respected; front measured at a depth threshold.
- [ ] Sand relaxes to its angle and settles (transfer fraction < 1, motion epsilon).
- [ ] Particles collide only where the engine supports it (Godot GPUParticles3D: Box/Sphere/SDF/
      HeightField collision nodes, never physics bodies).
- [ ] Wind transport: u\* from the one global wind, start/stop hysteresis, flux zero below the
      impact threshold, fixed sim tick, flux form, lee shadows and repose relaxation.
- [ ] One time-compression factor K per layer (prints and snowfall on the world clock, landforms
      slow or swapped), each with its real-time anchor in the tech-design note.
- [ ] Snow density by age; print depth from load and density with a deep-snow cap; trail texture
      re-centred in whole texels; shelter respected.
- [ ] Avalanches only in the release band, stop by the α line, telegraphed.
- [ ] Storm visibility from σ = 3.912/V with a direction cue; particle overdraw within budget.
- [ ] Lab gyms pass.

## 11. Engine notes

**Godot 4.6/4.7** — buoyancy in `RigidBody3D._integrate_forces` with `apply_force(force,
position)` where **position is an offset from the body origin in global axes, not a world
point**; Area3D gives gravity/damping overrides only, no buoyancy. Compute shaders: Forward+/
Mobile only, `sync` 2–3 frames after `submit`, split long dispatches (Windows TDR). Water surface
in a spatial shader (Gerstner in `vertex()`), the same function in GDScript for queries.
HeightMapShape3D: vertices 1 unit apart (scale otherwise), NaN makes holes, updates cost — chunk
them. GPUParticles3D collide with GPUParticlesCollision* nodes only; attractors affect GPU
particles only. Addons (check licence and version before use): WaterBox (MIT, per-point Marker3D
buoyancy, flat water), FloatableBody (MIT), godot4-oceanfft (MIT, compute FFT, early),
3D SPH Fluid Simulation (MIT, 4.6). Wind, sand and snow: trails in a SubViewport (orthographic
camera under the surface, `cull_mask` on a deformers layer, ping-pong refill) or a compute shader
shown through `Texture2DRD`; no tessellation shaders in Godot 4 — displace a dense mesh near the
player in `vertex()` or use parallax; storm particles collide with
GPUParticlesCollisionHeightField3D (`follow_camera_enabled`, no overhangs); exponential fog
`fog_density` = 3.912/V, FogVolume for local storms (volumetric fog, Forward+).

**Unity 6** — HDRP Water System: enable script interactions, `WaterSurface.
ProjectPointOnWaterSurface` (or `FillWaterSearchData` + a Burst search job for many points; the
FitToWaterSurface sample uses error 0.01 and 8 iterations); default GPU readback lags a few
frames, CPU simulation is exact but costs CPU. URP has no built-in water (Boat Attack demo:
Gerstner + Jobs buoyancy). Trails in a RenderTexture; GPU terrain edits with
`TerrainData.CopyActiveRenderTextureToHeightmap` (heights 0–0.5) and a CPU sync
(`TerrainHeightmapSyncControl`) only per region and rarely; storms in VFX Graph.

**Unreal 5.6–5.8** — Water plugin (experimental path): Water Body actors, Gerstner waves only
built in, Buoyancy component with sphere pontoons (≥ 4), coefficients, damping, max force, drag,
river forces; mesh must be the root with physics on (`r.Water.DebugBuoyancy 1`). Niagara Fluids
(Beta): 2-D/3-D gas, liquid, shallow water templates — 2-D for games. Landscape isn't editable at
runtime; deformable ground is runtime virtual textures + displacement or Virtual Heightfield Mesh
(visual only — collision separately) — the route for snow and sand trails too; storms with Niagara
plus Exponential Height Fog; global wind and snow amount in a Material Parameter Collection owned
by the weather system.
