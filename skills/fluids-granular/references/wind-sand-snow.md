# Wind, sand and snow — numbers, algorithms, games, engines

Detail for SKILL.md §7. Sources and what is still unverified: the research notes for this skill (kept in Kiln's development repository).
Every formula with a `predict` or check name is computed by `scripts/fluid_check.py`; the worked
numbers at the end are its tests. Values marked (working) are starting points, (calc) are our
own arithmetic, UNVERIFIED had no source.

## 1. Wind near the ground

- **Friction velocity u\*** drives transport, not the wind you read at head height. Log law:
  U(z) = (u\*/κ)·ln(z/z0), κ = 0.40. Roughness z0: snow and desert 0.1–5 mm (working default
  1 mm; the FSM snow model uses 10 mm for snow-covered ground). At z0 = 1 mm, U10 = 23.0·u\*.

| u\* (m/s) | 0.19 | 0.23 | 0.30 | 0.40 | 0.50 | 0.60 |
|---|---|---|---|---|---|---|
| 10 m wind, z0 1 mm (m/s) | 4.3 | 5.3 | 6.9 | 9.2 | 11.5 | 13.8 |
| 10 m wind, z0 0.1 mm (m/s) | 5.4 | 6.6 | 8.6 | 11.5 | 14.4 | 17.3 |

- Field practice for sand uses a 10 m threshold of 12 kn = 6.2 m/s; drift potential
  DP ∝ U²·(U − Ut)·t summed over the wind record; RDP/DP (net over total) measures how
  one-directional the wind is — barchan fields 1009/1034, star-dune fields 95/686 (Kok 2012).
- One wind for the whole game: the weather skill owns the global wind vector and gusts; this
  skill converts it to u\* where sand or snow moves.

## 2. Sand transport

**Thresholds** (Bagnold): u\*t = A·√((ρp − ρa)/ρa·g·d), A = 0.10 to lift grains (fluid
threshold), 0.082 to keep saltation going (impact threshold). The threshold is lowest at
~75–100 µm; finer grains are cohesive and need more. Quartz ρp = 2650, air ρa = 1.225 kg/m³.

| Grain d | u\*ft | u\*it | 10 m wind to start / keep (z0 1 mm) |
|---|---|---|---|
| 0.15 mm (fine) | 0.178 | 0.146 | 4.1 / 3.4 m/s |
| 0.25 mm (medium, typical dune) | 0.230 | 0.189 | 5.3 / 4.3 m/s |
| 0.35 mm | 0.272 | 0.223 | 6.3 / 5.1 m/s |

Use both: start transport when u\* ≥ u\*ft, stop it only when u\* < u\*it. Without that
hysteresis a gusty wind makes sand flicker on and off at the threshold.

**Flux models** (Q in kg per metre of width per second; Kok et al. 2012, Table 2.1):

| Model | Q | Notes |
|---|---|---|
| Bagnold 1941 | C·(ρa/g)·√(d/250 µm)·u\*³ | C 1.5 uniform, 1.8 natural, 2.8 poorly sorted; no threshold term |
| Kawamura 1951 | 2.78·(ρa/g)·u\*³·(1 − r)·(1 + r)², r = u\*it/u\* | White's version uses 2.61 |
| Lettau & Lettau 1978 | 6.7·(ρa/g)·√(d/250 µm)·u\*²·(u\* − u\*it) | |
| Pomeroy & Gray 1990 (snow) | 0.68·ρa·(u\*t/(u\*·g))·(u\*² − u\*t²) | saltation only |

- 0.25 mm sand at u\* 0.4: 0.0144 / 0.0254 / 0.0283 kg/m/s — the models differ ~2×; pick one
  and state it. Bagnold at u\* 0.3 / 0.5 / 0.6: 0.0061 / 0.028 / 0.049.
- Volume flux q = Q/ρb, bulk density ρb = ρp·(1 − porosity) ≈ 1590 kg/m³ (porosity 0.4,
  working). u\* 0.4: q = 9.0e-6 m²/s, 52 kg per metre per hour, 286 m² per year if it never
  stopped, ~29 m²/yr when the wind is above threshold 10% of the time (calc).
- Most saltating mass moves in the lowest centimetres (snow: ~90% below 3 cm at 10 m/s, Kind
  1981) — keep "creeping" ground particles low and put tall dust only in strong winds.

## 3. Dunes and ripples

- **Types** by wind regime and sand supply: barchan (one wind, little sand, horns downwind);
  transverse (one wind, plenty of sand); linear/seif (two alternating winds, crest along the net
  transport); star (many directions, up to hundreds of metres tall). In Werner's model dunes turn
  from transverse to linear when two reversing winds are more than ~45° oblique.
- **Profile**: windward (stoss) side ~10–15°, slip face at the angle of repose 30–35° (dry sand
  34°). The flow separates at the brink and leaves a recirculation bubble on the lee — grains
  that cross the crest fall out there. That is why erosion is windward and deposition leeward.
- **Speed**: mass conservation at the crest gives c = q/H. Barchans move 30–100 m/yr; q 100 m²/yr
  and H 3 m → 33 m/yr, H 10 m → 10 m/yr (`predict dune`). Scaling for barchans: c ≈ 50·Q0/W,
  volume ≈ 0.017·W³, turnover time ≈ 0.02·W²/Q0 (W the width, Q0 the bulk flux): small dunes
  turn over in 10–100 years, giant ones in 10³–10⁵. Small dunes are faster, catch up with big
  ones and merge or calve — expect that in any working simulation (Werner).
- **Minimum size**: saturation length L_sat ≈ 2·d·ρp/ρa (1.1 m for 0.25 mm sand), minimum dune
  width ≈ 12·L_sat ≈ 13 m (simulations). Anything smaller is a ripple or a pile, not a dune.
- **Ripples**: 7–14 cm apart, ripple index (wavelength/height) 12–50, ~15 typical → 0.5–0.9 cm
  high; crests lie across the local wind and form far faster than dunes, so they show the
  current wind direction (`predict ripple`). In games: a ripple normal map aligned to the global
  wind, re-blended over a few game minutes when the wind turns (working).

**Werner (1995) slab model** — cheap, grid-based, makes barchans, transverse, linear and star
dunes:
1. Square lattice, height = number of slabs per cell, edges wrap around.
2. Pick a random cell; if it has sand, lift one slab and move it l cells downwind.
3. Deposit with p_s = 0.6 on sand, p_ns = 0.4 on bare ground; otherwise hop another l cells.
4. Cells in the shadow zone (below a 15° line behind a crest) always catch the slab.
5. Enforce the angle of repose (30°): a deposit rolls down the steepest slope; an erosion that
   oversteepens triggers cascades upslope.
6. Time unit = as many polls as there are cells.
- Parameters: slab aspect 1/3, l = 5, 1000² lattice; barchans at 3 slabs per cell on average,
  crescentic ridges at 15. Linear dunes: two wind vectors about 70° either side of the net
  direction, switched every 40 units (signs reconstructed from the scan). Star dunes: four
  rotating winds of length 5, switched every 80 units.
- Units (`predict werner`, calc): flux per time unit = slab·l·dx/p_s (full sand cover, no
  shadow) = 2.78 m² for 1 m cells — one unit ≈ 35 real days at 29 m²/yr. With whole slabs the 30°
  rule allows floor(tan 30°/aspect) slabs per cell: at aspect 1/3 that is 1 slab (18.4°), so
  pick aspect ≤ 0.289 (2 slabs = 30°) if slip faces must reach 30°.
- A GPU implementation of the related Desertscapes model (2024) ran 1000 steps of a 512² grid in
  0.46 s on an RTX 4080 (shadowing ramps in from 10° to 15°; repose tan 33°–45° by vegetation).

**Heightfield transport for games** (continuous version, flux form, (working)):
1. Per cell compute local u\*: the global wind, sped up on windward slopes and zeroed in the lee
   shadow (below a 10–15° line from the upwind crest).
2. Where u\* ≥ threshold (with the start/stop hysteresis) erode q·dt/dx from the cell, capped by
   the sand available (bedrock cells give nothing).
3. Carry it a hop length downwind (bilinear splat, 1–5 cells); deposit with a probability or
   fraction that is higher on sand than on rock, always in shadow.
4. Relax every cell to the angle of repose (SKILL.md §6 thermal erosion, 8 neighbours).
5. Exner: the height change is minus the divergence of the volume flux, so total volume changes
   only through the domain edges — wrap the edges or state the sources and sinks.
Fixed step at its own tick (2–10 Hz), never per frame. Check with `lee` (two exports a known
time apart) and `conserve`.

## 4. Tracks and prints in sand

- Fill time t = L·D/(q·trap): L the print's length along the wind, D its depth, trap the
  fraction of grains blown in that stay (1 = all, the fastest case). A 28 × 10 × 3 cm print fills
  in ≥ 37 / 15 / 8 min at u\* 0.3 / 0.4 / 0.5 (`predict fill`). The fill starts at the upwind wall;
  the downwind wall erodes a little. Below the threshold prints stay forever.
- Wet sand (repose ~45°) holds sharp prints; dry sand slumps to 34° walls at once — a dry print
  is a soft dent, a wet one has crisp edges.
- Sumner, O'Brien & Hodgins: a deformable ground model for prints in sand, mud and snow
  controlled by five parameters — compress under the foot, push material to the rim, relax to a
  slope limit; the basis for cheap deform-and-relax in a heightfield.

## 5. Sandstorms and blizzards

- Visibility categories: dust storm 200 m–1 km, severe < 200 m (Kok); Hong Kong's sandstorm
  < 1000 m; NWS heavy snow ≤ 400 m (¼ mile). Extinction σ = 3.912/V (2% contrast); Godot
  exponential fog uses fog = 1 − exp(−d·fog_density), so fog_density = σ: 1000 / 200 / 50 m →
  0.0039 / 0.0196 / 0.078 per m (`predict storm`). Other engines: check the fog curve in a gym
  (weather skill).
- **Particle budget** (calc): camera-facing sprites of size s at density n (per m³) in a sphere
  of radius R with a near fade at r₀ give, on average, n·s²·(R − r₀) layers of overdraw along
  every view ray; with per-sprite opacity α they add extinction α·n·s². 2000 one-metre sprites in
  a 30 m sphere: 0.5 layers; the same count as 4 m sheets: 8 layers. Keep ≤ 2 layers on an iGPU
  and ≤ 4 on a mid dGPU (working); push the bulk of the extinction into fog and use particles for
  the near field: fast streaks at ankle-to-knee height, a few large soft sheets for gusts.
- Gameplay: BotW's Gerudo sandstorms turn the map to static and block teleporting; statues point
  the way through; one storm lifts 21:00–04:00. Dune: Awakening has frequent sandstorms and a
  weekly Coriolis storm that reshapes the Deep Desert map — a discrete state swap hidden by a
  storm instead of continuous dune motion. Always leave a direction cue (landmarks, wind-aligned
  streaks, sound panning).
- Journey's sand is rendering only (GDC 2013, three years of work): a secondhand reconstruction
  lists diffuse, grain normals, rim light, "ocean" specular, glitter and ripples blended from
  four textures.

## 6. Snowfall, cover and settling

| Snow (Cuffey & Paterson 2010) | Density kg/m³ |
|---|---|
| New snow, calm, just fallen | 50–70 |
| Damp new snow | 100–200 |
| Settled snow | 200–300 |
| Wind-packed | 350–400 |
| Firn | 400–830 |
| Very wet snow and firn | 700–800 |
| Glacier ice | 830–923 |

- Game default for new snow 100 kg/m³ (FSM; the 10:1 snow-to-water rule assumes it and is poor
  as a general rule). Water equivalent SWE (kg/m² = mm) = depth × ρ.
- Rates: moderate ~2.5 cm/h, heavy ≥ 5 cm/h (informal); NWS heavy snow = 10 cm in 12 h or 15 cm
  in 24 h; visibility for a given water rate varies 3–10× between storms (`predict snowfall`).
- **Settling** (FSM 1.0): dρ/dt = (ρmax − ρ)/τ, exact step ρ ← ρmax + (ρ − ρmax)·exp(−dt/τ),
  ρmax 300 cold / 500 melting, τ = 200 h; depth falls with SWE kept (`predict settle`). Overburden
  compaction at depth is ignored — fine for games.
- Cover fraction for blending the snow material: f = tanh(h/0.1 m) — 76% at 10 cm, 96% at 20 cm
  (FSM). Albedo 0.8 fresh → 0.5 aged (decay τ 1000 h cold, 100 h melting) — old snow looks greyer.
- Thermal conductivity λ = 2.24·(ρ/917)² W/m·K (FSM) — fresh snow insulates (elements-materials
  skill for heat).
- Snow on objects: mask by world normal·up with a contrast ramp and normal-map breakup, times a
  global snow amount; sheltered surfaces (under roofs, overhangs) need the weather skill's
  occlusion mask.

## 7. Prints and compaction in snow

- CRREL (Richmond 1995, wheels): sinkage z = h·(1 − ρ0/ρf), h the loose snow depth over a firm
  base, ρ0 its density, ρf the final density — 500 kg/m³ for contact pressure ≤ 210 kPa, 550
  above, 600 above 350, 650 above 700 kPa; a newer wheel fit ρf = 519 + 2.3·p (kPa) matched
  100–250 kPa tyres better. Measured ruts: 8–21 cm in 15–24 cm of 200 kg/m³ snow at 102–123 kPa.
  Snow does not compact past ~500–550 kg/m³ under traffic (critical density).
- People: 80 kg on a 0.03 m² boot = 26 kPa static; on a snowshoe ~4 kPa. Measured in 0.8–1.1 m
  deep natural snow (Hokkaido, 9 people, 63.5 kg mean): boots 11.8 ± 6.2 cm, kanjiki 7.0 ± 3.3,
  snowshoes 5.7 ± 2.2 cm; effort 6.5 METs in boots vs 5.4 in snowshoes and 4.0 on packed snow;
  heart rate rose with print depth (rs 0.71). Deep soft snow stops a boot at a compaction bulb —
  the full-depth formula over-predicts there; cap it per snow type (`predict footprint --cap`).
- Skis: penetration ≈ 42.4/ρ30 m (ρ30 the density at 30 cm depth, Jamieson & Johnston 1998).
- Game rules (working): print depth from `predict footprint` drives the foot IK offset, the
  trail texture and a speed or stamina factor; prints in snow already denser than ρf stay shallow
  (wind crust, packed trails) — players read packed paths as easy routes (RDR2 horse vs foot).

## 8. Blowing snow, drifts, cornices

- Thresholds at 10 m: fresh cold snow 4–5 m/s, dry snow 7.7 m/s, wet snow 9.9 m/s (Li & Pomeroy,
  Canadian prairies); u\*t from < 0.1 m/s for light dry snow to > 0.4 m/s for old hardened snow
  (Liston 1993). The threshold rises sharply with age, warmth and wetness — tie it to the snow's
  age or density in the game (working).
- Drift behind a 50% porous fence of height H (Tabler 1980): lee drift 30H long, 1.2H deep,
  19.3H² cross-section, tail slope ~6%; upwind drift 12H long, 0.5H deep; drifted snow density
  376 + 158·log10(depth m) kg/m³ (436 at 2.4 m). A 2 m fence holds ~34 t per metre — 39 days at
  0.01 kg/m/s (`predict drift`). Early on the lee drift has a steep slip face, a small cornice.
  Use it as the shape for any barrier, wall or ridge drift (working for solid barriers).
- Cornices: wind carries snow over a crest and it builds out horizontally over the lee; a
  collapse can break back behind the visible edge; sun weakens them and falling cornices trigger
  avalanches. In games put the break line behind the lip (distance working) and telegraph it.
- Sastrugi: hardened drifts carved by later winds into ridges parallel to the wind, anvil points
  upwind; small wind ridges ~10 mm high — orient the snow normal map by the wind that made them.

## 9. Avalanches

- Slab avalanches (a cohesive slab on a weak layer, often buried surface hoar or depth hoar)
  cause ~90% of deaths; loose-snow avalanches start at a point and fan out.
- Angles: start zones 30–45°, tracks 20–30°, runout below 20°; human-triggered slabs peak at
  ~38° (most common 36–38°). Speeds: powder > 300 km/h, wet 10–40 km/h. Triggers: heavy snowfall
  and wind loading, sun, rain, skiers, snowmobiles, explosives. Loud sound is too weak.
- **Stability index** (Föhn 1987; Jamieson & Johnston 1998): slab shear stress on the weak layer
  τ = ρ·g·h·sin ψ·cos ψ (h vertical slab thickness); S = strength/τ for natural release,
  S' = strength/(τ + Δτ) with a skier, Δτ ≈ 0.14/h kPa at 38° (line load 500 N/m). S < 1 released
  in the field data, S > 1.5 did not, 1–1.5 transitional. Measured weak-layer strengths 0.6–2.6
  kPa. For other slopes `predict avalanche --skier` scales 0.14/h by Föhn's elastic formula
  (calc; the formula's own peak gives 0.155/h at 38°).
- **Runout** (Lied & Bakkehøi 1980, 111 Norwegian paths): α = 0.97·β − 1.4°, SD 3.5°, R 0.88; α
  is the angle from the release point to the farthest runout, β from the release point to where
  the slope first falls to 10°. β 28°, 500 m drop: α 25.8°, reach 1036 m, 1222 m at α − 1 SD.
  An eight-parameter fit narrows the SD to 2.3°.
- **Game recipe** (working, not a published technique): snowpack grid with depth, density and a
  weak-layer flag per cell → release check where slope is in the band, a weak layer exists and
  load is added (fresh snow, wind drift, the player, an explosion), using S → the slab above the
  trigger fractures (crown line across the slope) → it flows as a heightfield (thermal-erosion
  style transfer with a low repose angle) plus GPU particles for the powder cloud → it stops
  below 20° or at the α line and leaves denser debris (~350–500 kg/m³, working). Test: `release`
  trials on a 25–50° ramp, `runout` on a known profile.

## 10. Melt

- Energy: SWE × (334 kJ/kg + 2.09 kJ/kg·K × degrees below zero). 10 cm of 100 kg/m³ snow =
  10 kg/m² = 3.34 MJ/m²: 9.3 h at 100 W/m², 3.1 h at 300, 0.93 h at 1 kW/m² (`predict melt`).
- Melting snow densifies toward 500 kg/m³ (FSM) — depth drops faster than SWE.
- Heat sources (sun, fire, lava, heaters), heat compression and phase plateaus: the
  elements-materials skill. Water from melt: SKILL.md §4 flowing water.

## 11. Time compression

| Process | Real time | Typical game time | K |
|---|---|---|---|
| Sand print fills, u\* 0.4 | ≥ 15 min | 30–60 s | 15–30 |
| Snow boot print fills, u\* 0.4, u\*t 0.2 | ≥ 34 min | 1–2 min | 17–35 |
| 15 cm snowfall at 2.5 cm/h | 6 h | 6–15 min | 24–60 |
| 10 cm fresh snow melts at 300 W/m² | 3.1 h | 2–5 min | 37–90 |
| Fresh snow settles 100 → 226 kg/m³ | 200 h | one game day | ~10³ |
| 2 m fence drift fills at 0.01 kg/m/s | 39 days | 5 min | ~11 000 |
| 3 m barchan moves 1 m (q 100 m²/yr) | 11 days | 1 min | ~16 000 |
| Small dunes re-orient | 10–100 years | between visits | state swap |

1. One K per layer. A single K breaks something: at the dune K a print fills in a frame; at the
   print K the dunes never move.
2. The player-scale layer (prints, snowfall, melt, small drifts) runs on the world clock: if a
   game day is 24 min (K = 60), use 60 so "it snowed all night" gives a night's depth.
3. The landform layer (dunes, big drifts, cornice growth) runs at its own large K where nobody
   watches grains, or as discrete state swaps off-screen, at load or behind a storm (Dune:
   Awakening).
4. Compressing means multiplying the flux (or dt) by K; check stability again: the per-step
   height change must stay below a fraction of a cell (repose relaxation absorbs the rest).
5. Write each K, its layer and its real-time anchor into the tech-design note; `predict
   dune|fill|drift|snowfall|melt --game-s` prints K.

## 12. Games that did it

- **Batman: Arkham Origins** (GDC 2014): objects that touch snow are rendered white from below
  the surface by an ankle-high orthographic camera, blurred with a 4-tap Poisson filter and
  accumulated between two textures; subtracting a small value per frame refills the snow.
  Heightmap min(512, ¼ of the surface size), 2 MB on consoles, 2–4 MB on PC, under 1 ms GPU on
  PS3/360 with 2 surfaces updated per frame; relief mapping on consoles, DX11 tessellation on PC.
- **Rise of the Tomb Raider** (SIGGRAPH 2015, GPU Pro 7): deformation independent of the snow
  mesh, compute shaders plus hardware tessellation; trails push snow up at the sides and fill in
  during snowstorms; scales to many NPCs and animals (resolution and cost UNVERIFIED).
- **Assassin's Creed III**: DX11 tessellation smooths footprints on PC; earlier approaches
  raycast or modified the terrain mesh.
- **Horizon Zero Dawn: The Frozen Wilds**: snow compresses into trails, only in the DLC area; the
  PC port first lacked it (patch 1.03 fixed a deformation bug).
- **Red Dead Redemption 2**: persistent deformation that differs on foot and on horseback
  (internals UNVERIFIED).
- **Journey**, **Breath of the Wild**, **Dune: Awakening**: §5.

## 13. Engine notes

**Godot 4.6/4.7**
- Global wind, snow amount and fog come from the weather skill's controller (global shader
  parameters via `RenderingServer.global_shader_parameter_set`); never add a second wind.
- Trails: a SubViewport with an orthographic Camera3D under the surface looking up, `cull_mask`
  on a "deformers" layer (foot and wheel proxies that write height); accumulate with a ping-pong
  of two viewports and a refill shader (subtract a small value per second), or a compute shader
  on the RenderingDevice (Forward+/Mobile only) exposed as `Texture2DRD`. Re-centre on the
  player in whole texels and offset the UVs, or prints swim.
- Godot 4 has no tessellation shaders: displace in `vertex()` on a dense clipmap mesh near the
  player, or fake depth in `fragment()` (parallax). Collision stays on the base terrain:
  CharacterBody3D walks on it, the feet sink by IK offset from the print depth, HeightMapShape3D
  updates only in chunks where depth matters to gameplay (deep drifts).
- Storm particles: GPUParticles3D following the camera; collide with
  GPUParticlesCollisionHeightField3D (`follow_camera_enabled`, resolution 256–8192, default 1024,
  update when moved — no overhangs, GPU particles only, collision mode on the process material);
  change intensity with `amount_ratio` (changing `amount` restarts). Fog: Environment exponential
  fog `fog_density` = 3.912/V; local storms with FogVolume (needs volumetric fog, Forward+; cost
  grows with screen size).
- Grids in GDScript: the measured diffusion cost is ~130 ns per cell (elements-materials skill);
  a transport step is ~2–4× that (working) — 64² at 5–10 Hz in GDScript, larger in compute.

**Unity 6** — trails in a RenderTexture (orthographic camera or compute) sampled by the terrain
shader; GPU terrain edits with `TerrainData.CopyActiveRenderTextureToHeightmap` (heights 0–0.5 in
the texture) and `TerrainHeightmapSyncControl` (None / HeightOnly / HeightAndLod) — sync to the
CPU (collision) rarely and per region. Storm particles in VFX Graph (compute, no GLES; Collide
with Depth Buffer for fast particles); global wind and snow amount as global shader properties
from the weather system. Fog density: Exponential mode density = σ (Unity's exponential fog
curve; weather skill `predict fog`); URP volumetric fog and HDRP mappings in the weather skill.

**Unreal 5.6–5.8** — trails via a render target written each frame (Draw Material to Render
Target or Niagara) feeding Runtime Virtual Texture displacement or Virtual Heightfield Mesh
(visual only; Landscape is not editable at runtime, collision separate); storms with Niagara
(GPU) plus Exponential Height Fog and volumetric fog; global wind and snow amount in a Material
Parameter Collection owned by the weather system.

## 14. Budgets (iGPU first)

- Trail texture 512² R16F × 2 (ping-pong) = 1 MB; Batman's 2–4 MB and < 1 ms on PS3/360 are an
  upper bound for an iGPU today (working).
- Transport grid: 64² in GDScript (~0.5–2 ms per step, working), 128² compute at 2–10 Hz on an
  Intel UHD 630 class iGPU (~3.5 ms per step, scaled by FLOPS from the RTX 4080 Desertscapes
  number — UNVERIFIED); spread steps over frames.
- Particles: `predict storm` overdraw ≤ 2 layers on an iGPU (working); measure the heaviest storm
  with the optimization skill.
- Collision: only where depth changes gameplay (deep drifts, avalanche debris), in chunks,
  rarely.

## 15. Pitfalls

1. One time-compression factor for every process (§11).
2. Transport per rendered frame — frame-rate dependent; use a fixed sim tick.
3. Bagnold's flux without a threshold — sand creeps in calm air. Zero below u\*it; start at u\*ft.
4. Erosion without repose relaxation (spikes) or deposition without lee shadows (no slip face,
   symmetric dunes).
5. Volume lost at the edges or by clamping — the desert slowly vanishes; flux form, stated edges,
   `conserve`.
6. Trail texture not re-centred in whole texels — prints swim or vanish as the camera moves.
7. Snow under roofs and inside caves — no shelter mask (weather skill).
8. Print depth ignoring density — fresh powder printing as shallow as a packed trail.
9. Footprints written into physics collision every frame — hitches.
10. Avalanches on any slope or from shouting — breaks the real 30–45° reading players learn;
    a deliberate lie must be telegraphed and consistent.
11. Storm as plain fog with no direction cue — the player is lost, not challenged.
12. Big sprites at the camera — overdraw explodes on iGPUs; near fade and the overdraw formula.
13. Ripple and sastrugi textures that disagree with the wind direction.

## 16. Worked numbers (the tests)

- 0.25 mm sand: u\*ft 0.2303, u\*it 0.1888 m/s; 10 m wind 5.302 / 4.348 m/s (z0 1 mm), 6.628 m/s
  to start at z0 0.1 mm.
- u\* 0.4: Bagnold 0.014386, Kawamura 0.025417, Lettau 0.028268 kg/m/s; q 9.0474e-6 m²/s;
  51.79 kg/m/h; doubling u\* → 8× Bagnold.
- Dune H 3 m, q 100 m²/yr: 33.333 m/yr; W 300 m: barchan 16.667 m/yr, turnover 18 yr; minimum
  width 12.98 m; 1 m in 60 game s → K 15 778.8.
- Werner, 1 m cells, aspect 1/3, l 5, p_s 0.6: 2.7778 m² per unit, 34.986 days per unit at
  29 m²/yr, 1 whole slab per step (18.43°).
- Print 0.28 × 0.03 m, u\* 0.4 sand: 928.4 s; snow boot print 0.3 × 0.1 m at u\* 0.4, u\*t 0.2:
  Q 0.0050947 kg/m/s, 2060.9 s.
- Dry snow, 12 m/s: u\*t 0.3344, u\* 0.5212, Q 0.008705 kg/m/s.
- Fence 2 m: 60 m × 2.4 m, 77.2 m², 436.1 kg/m³, 33 664.9 kg/m, 38.96 days at 0.01 kg/m/s.
- Snowfall 2.54 cm/h × 6 h: 15.24 cm, 15.24 mm SWE, 6.1 cm at 250 kg/m³.
- Settling 200 h: 226.42 kg/m³ cold, 352.85 melting; 30 cm → 13.25 cm; 250 kg/m³ after 277.26 h.
- Boot 80 kg / 0.03 m²: 26.16 kPa; 30 cm of 100 kg/m³ → 24 cm (24.82 cm with the wheel fit).
- Slab 0.5 m, 200 kg/m³, 38°: τ 0.4759 kPa, S 2.101, S' 1.323; β 28°, 500 m: α 25.76°, reach
  1036.1 m (1221.6 m at −1 SD).
- Melt 10 kg/m² at 300 W/m²: 3.088 h; from −10 °C 11 815 s.
- Storm V 200 m: σ 0.01956; 2000 × 1 m sprites in 30 m (near 1 m): 0.5128 layers.
