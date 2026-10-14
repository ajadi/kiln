---
name: weather
description: Weather as one system — one weather state (type, intensity, wind, temperature, visibility, wetness, snow cover) published as global shader parameters and read by everything; transitions with durations, hysteresis and minimum dwell, seeded schedules, forecasts and regional weather maps; wet surfaces and puddles with drying, rain in a camera-local particle volume with roof occlusion and splashes, snow cover accumulation and melt, wind tied to vegetation, particles, cloth and gameplay, fog density from visibility (Koschmieder) per engine, lightning within photosensitivity limits and thunder delay, clouds and sky coupling, weather audio layers, effects on traction, climbing, cold, fire, AI perception and stealth, readability, budgets including iGPUs, save state, pitfalls, Godot/Unity/Unreal setup and acceptance checks with numbers via weather_check.py. Use when designing, building, tuning or reviewing rain, snow, wind, fog, storms, lightning, wetness, weather transitions or forecasts, or anything the weather should change.
user-invocable: false
---

# Weather

Weather is one state that everything reads, not a set of effects that each decide it is raining.
Write the state and presets first, publish them on one bus, prove the numbers with
`${CLAUDE_SKILL_DIR}/scripts/weather_check.py` (stdlib Python, Bash). Presets, shader snippets,
controller, lightning, audio and game references: `${CLAUDE_SKILL_DIR}/references/recipes.md`;
engines: `${CLAUDE_SKILL_DIR}/references/engines.md`. (working) = tune it; [U] = unconfirmed.

## 1. One state, one bus

1. **State** (data asset, saved): `type` (clear, overcast, rain, storm, snow, fog, sand),
   `intensity` 0–1, `wind` (m/s at 10 m) + gust signal, `temperature` °C, `visibility` m, cloud
   `coverage`, `precipitation`, and accumulators `wetness`, `puddles`, `snow` that lag the sky.
   Type picks a preset; intensity blends clear → preset.
2. **One controller** steps it at 2–10 Hz (working), interpolates per frame and publishes **global
   shader parameters** — the single bus: Godot `global uniform`, Unity `Shader.SetGlobal*`, Unreal
   one Material Parameter Collection (≤ 1024 scalars + 1024 vectors, ≤ 2 per material). Names go
   in `memory/registries.md`.
3. **Gameplay reads the controller, never the shaders** (reading globals back stalls rendering).
4. **Regions**: a low-res weather map (Horizon Zero Dawn: R coverage, G precipitation, B cloud type,
   custom-painted for cutscenes) or biome volumes biasing presets; borders blend over 10–30 s.

## 2. Transitions, hysteresis, forecast

1. Every channel blends over a duration; clouds and fog lead, rain follows, accumulators lag.
   Smoothstep peaks at 1.5× the linear rate; an exponential approach reaches 95% at 3τ
   (`predict transition`, measured by `smooth`).
2. **Hysteresis**: switch on and off at different values (thunder on ≥ 0.7, off ≤ 0.5; rain above
   +1 °C, snow below −1 °C — working); the band exceeds the driver's noise and every state has a
   minimum dwell, so nothing flickers at a threshold.
3. **Dwell**: The Long Dark 2–12 h per state, faster changes on hard modes; Minecraft rain 10–20
   min, clear 10–150 min, raining 15.8% of the time (`predict schedule`); BotW regions every 4 h.
4. **Forecast** = the seeded schedule generated ahead, shown on the HUD (Stardew Valley's TV shows
   tomorrow; Death Stranding 2 routes around timefall); seed + game time reproduce it after a
   load. Scripted overrides push a state with a blend time and pop back; the schedule runs on.

## 3. Wet surfaces

1. Lagarde (Remember Me): porous darkening `f = lerp(1, 0.2, porosity)`, `albedo *= lerp(1, f,
   wet)`; gloss `lerp(1, gloss, lerp(1, f, 0.5·wet))` — roughness falls toward water; metals and
   smooth parts are not porous; water F0 0.02 vs 0.04 skipped as invisible.
2. **Puddles**: accumulated water against a cavity/height mask on flat, exposed ground — thin
   water smooths normals, a full puddle is flat with water F0, sharp reflections and ripples.
   Wetting runs 3–5× faster than drying; puddles fill and drain slowest (Remember Me presets).
3. **Drying**: real wet asphalt takes > 30 min; games dry surfaces in ~1 min, puddles slower; heat,
   sun and wind speed it up (`kiln:elements-materials`; `predict wetness`, measured by `wetness`).
   Characters carry their own wet value (1 below the water line) and drip 30–60 s after (working).

## 4. Rain

1. **Particles in a camera-local box**: count = density × volume, lifetime = height / fall speed
   (2–9 m/s), emission = count / lifetime (`predict rain`). Real rain at 10 mm/h holds ~3200
   drops/m³, ~250 over 1 mm; render 0.2–2 streaks/m³ near (working), screen layers beyond
   (Remember Me: 4 on a camera cone). Intensity scales the emission ratio, not the maximum.
2. **Occlusion map**: a top-down depth render along the rain direction — Remember Me: 256² over
   20 × 20 m (7.8 cm/texel) ahead of the camera, 0.2–0.32 ms. It masks drops, splashes, wetness,
   ripples and camera droplets. Particle heightfield collision stops drops on roofs but tells
   surface shaders nothing; a vertical mask leaks under overhangs in side wind — tilt it.
3. **Splashes, ripples**: 20 / 40 / 60 splashes for light / moderate / heavy; footstep splashes
   nearly free; one tiling 256² ripple map, 4 layers switched on at intensity 0, 0.25, 0.5, 0.75.
   Camera droplets only outdoors. Slant = atan(wind / fall speed): 5 on 8 m/s = 32°.

## 5. Snow cover

1. Amounts and mechanics come from `kiln:fluids-granular`: new snow 50–70 kg/m³ in calm, damp
   100–200, settled 200–300, wind-packed 350–400 (Cuffey & Paterson), game default 100, settling
   with τ ≈ 200 h (FSM); 2.54 cm/h for 6 h = 15.2 cm; melt 3.1 h for 10 kg/m² at 300 W/m²
   (`fluid_check.py predict snowfall|settle|melt`). Prints, drifts, avalanches live there too.
2. The controller keeps depth and density and publishes cover = tanh(depth / 0.1 m) (FSM). Mask:
   smoothstep of `dot(N_world, up)` against `1 − cover` with noise, zero under the occlusion map
   (no snow on ceilings); albedo 0.8 fresh → 0.5 aged; melt sun-facing and warm surfaces first,
   refreeze below 0 °C with hysteresis.

## 6. Wind

1. One vector + a gust signal (Ghost of Tsushima: fixed direction, Perlin-noise magnitude, local
   "vorticles", a Guiding Wind toward the goal). Beaufort v = 0.836·B^1.5 m/s: force 3 (3.4–5.4
   m/s) twigs move, 5 (8–10.7) small trees sway, 7 (13.9–17.1) whole trees move and walking is
   hard, 8 (17.2–20.7) twigs break; gusts ~1.5× the mean (working) (`predict wind`).
2. Everything reads the same vector: vegetation (`kiln:shaders`), rain, particles, cloth
   (`kiln:soft-bodies`), clouds, audio gusts, fire, smoke. Forces on bodies: `kiln:fields-forces`
   (Just Cause 4: wind is "moderate and cosmetic over large areas, or strong and physical in
   small volumes").

## 7. Fog and visibility

1. Koschmieder: σ = 3.912 / V (2% contrast); the WMO optical range uses 5% (2.996 / V). Fog < 1 km,
   mist 1–2 km, haze 2–5 km; heavy snow ≤ ~400 m (NWS ¼ mile); dust storm 200 m–1 km, severe
   < 200 m. Each preset sets one V; precipitation does not add a second fog.
2. Engines (`predict fog`): Godot fog is `1 − exp(−d·fog_density)`, so `fog_density` = σ;
   `volumetric_fog_density` is σ too but only to `volumetric_fog_length` (64 m default) — keep
   both; Unity Exponential density = σ, Exponential Squared 1.978 / V; HDRP Fog Attenuation
   Distance = 1 / σ; Unreal Fog Density is unitless — calibrate it with `visibility`.

## 8. Lightning and thunder

1. A flash is 3–4 return strokes (up to 30) 40–50 ms apart, median 0.52 s; ~25% reach the ground.
   Strikes hit tall, isolated, pointed things; a game may lie if it telegraphs (BotW: metal gear
   sparks, then draws the strike). Flash lights: shadows off, volumetric fog energy 0.
2. Thunder delay = d / c, c = 331.3·√(1 + T/273.15) (343 m/s at 20 °C, ~3 s per km); heard to
   ~16 km (NWS: about 10 miles); rumbles up to 30+ s; far thunder quieter and duller
   (`predict thunder`). Engines do not delay sound by distance — schedule it.
3. **Photosensitivity** (`kiln:accessibility`): ≤ 3 flashes in any 1 s over ≥ 20% of the screen. A
   real 4-stroke flicker fails: ≤ 3 pulses per burst and ≥ 1 s from a burst's last pulse to the
   next (`predict flash`, measured by `flashes`); "reduce flashing" = one soft pulse < 10% change.

## 9. Clouds, sky, audio

1. **Clouds belong to weather** (coverage, type, darkness, drift with the wind) and lead the rain:
   Horizon Zero Dawn's precipitation turns the map to cumulonimbus at 70% coverage before rain,
   clouds to 35 km in ~2 ms on PS4. `kiln:sky` owns sun, moon, time of day, atmosphere and exposure
   and reads cloud coverage and fog from the bus; re-run `kiln:lighting` metrics per preset.
2. **Audio** (`kiln:procedural-audio`): layers by intensity — far wash, mid patter, near drops per
   surface from the occlusion map; wind bed + gust layer on the gust signal; thunder delayed by
   distance. Indoors the rain is low-passed plus a roof layer, crossfaded 0.5–1 s (working).

## 10. Gameplay

- **Traction**: μ dry asphalt 0.8–0.9, wet 0.5–0.7, packed snow 0.2, ice 0.1 (`kiln:vehicles`);
  slips on foot (`kiln:traversal`). **Climbing**: BotW slips in rain; Tears of the Kingdom's Froggy
  set and sticky elixirs counter it — gear answers weather.
- **Cold**: wind chill 13.12 + 0.6215T − 11.37V^0.16 + 0.3965T·V^0.16 (V km/h): −20 °C in 30 km/h
  feels −33 (`predict wind --temp`); The Long Dark ties weather to speed, vision, warmth and
  clothing. **Fire**: rain puts out exposed fires (BotW), blocks spread (Minecraft).
- **AI** (`kiln:game-ai`): sight ≤ ln(C₀ / 0.02) / σ for a target of contrast C₀ (0.3 at V 400 m →
  277 m); hearing radius × 10^(−ΔdB/20) under rain noise (+6 dB halves it) (`predict perception`).
  Same rules for player and enemies (MGSV sandstorms blind both sides; its rain on hearing [U]).
  Death Stranding's timefall ages cargo containers; shelters repair them.

## 11. Readability, budgets, save

- **Readability**: lighting checks pass in every preset at full intensity (enemy ≥ 3:1 at combat
  range); combat spaces keep V ≥ 2× the engagement range, faint streaks near the screen centre
  (working); captions for storm cues that matter.
- **Budgets**: Remember Me's rain core: 2.8 ms of 3 ms at 30 fps (PS3/360). Targets (working):
  rain ≤ 1.5 ms desktop, ≤ 3 ms iGPU at 1080p; ≤ 20k streaks desktop, ≤ 5k iGPU; occlusion map
  256–512²; 2D clouds and no volumetric fog on iGPU; controller < 0.1 ms CPU (`kiln:optimization`).
- **Save** (`kiln:save-system`): type, intensity, transition (from, to, elapsed, duration), wind,
  temperature, accumulators, schedule seed and cursor, overrides — applied at once on load.

## 12. Pitfalls

- Own "is raining" flags per system; snapping presets and borders; undelayed thunder; 4-stroke
  flicker; fog hiding enemies; rain indoors; snow on ceilings; wetness that never dries; two winds;
  weather missing from saves. Godot: collisions only inside `visibility_aabb`; `local_coords` on
  turns rain with the camera; changing `amount` restarts; `TIME` wraps at 3600 s.

## 13. Acceptance (gyms via `kiln:gym`, probes via `kiln:acceptance`)

| Check | Gym / probe | Command | PASS |
|---|---|---|---|
| Transitions | clear → storm → clear: intensity, fog σ, sun energy, wind | `smooth --probe name=limit --state` | intensity ≤ 0.05/s; fog σ and light energy ≤ 25% of their range per s (working); no state run < 5 s |
| Wetness | rain 60 s, then dry; ground probe | `wetness` | 0.8 within 60 s of rain; 0.1 inside the design dry window; no dip while raining |
| Shelter | roof, open ground, side wind | `shelter --inside / --splashes --roof` | sheltered wetness ≤ 0.05; 0 splashes under the roof |
| Visibility | black cards at 25–400 m per preset | `visibility --visibility V` | within 15% of the preset V |
| Lightning | 60 s storm, luminance per frame | `flashes` | ≤ 3 flashes in any 1 s |
| Thunder | strikes at 0.5, 2, 8 km | delay vs `predict thunder` | within 0.1 s; silent beyond audible range |
| Readability | enemy at combat range per preset | lighting contrast | ≥ 3:1 |
| Budget, save | heaviest storm on the target machine; save mid-transition | optimization skill; state diff | within the targets; same state after load |

## 14. Engine notes

**Godot 4.6/4.7** — Shader Globals (incl. sampler2D); rain rig = GPUParticles3D following the
camera + GPUParticlesCollisionHeightField3D (follow camera, update when moved) + splash
sub-emitter AT_COLLISION; occlusion from an orthographic Camera3D in a SubViewport; FogVolume with
negative density indoors; clouds as a quarter-res layer in the sky shader. **Unity 6** —
`Shader.SetGlobal*`; VFX Graph "Collide with Depth Buffer"; HDRP Volumetric Clouds; WindZone moves
trees and particles only. **Unreal 5.6–5.8** — MPC bus; Niagara scene-depth collision; Exponential
Height Fog, Local Fog Volumes, Volumetric Cloud; no built-in weather controller.
