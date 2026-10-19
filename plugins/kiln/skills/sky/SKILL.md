---
name: sky
description: Sun, moon and stars and the day/night cycle for games — realism level (real ephemeris by latitude and date vs a stylised arc), NOAA solar position (elevation, azimuth, sunrise, sunset, day length by latitude and season), twilights, moon phase, position and moonlight, star rotation about the celestial pole, game time compression, sleeping and skipping time, light intensity and colour-temperature curves, exposure, night readability, low-sun shadow cost, swapping sun and moon as the one shadow-casting light, sky models and their update cost, coupling with weather and clouds, saving and syncing the clock, pitfalls, Godot/Unity/Unreal setup, acceptance checks with numbers via sky_check.py. Use when designing, building, tuning or reviewing a sky, a day/night cycle, a game clock, sun or moon lights, or anything that changes with the time of day.
user-invocable: false
---

# Sky

The sky is a clock with lights attached. One game clock (game seconds since a start date) drives
the sun, moon, stars, light curves and everything that reacts to the time of day; each is a pure
function of the clock, never a timer of its own. Check numbers with
`${CLAUDE_SKILL_DIR}/scripts/sky_check.py` (stdlib Python, Bash). Exposure workflow and readability
measurement: `kiln:lighting`; clouds, fog, rain and cloud shadowing of the sun: `kiln:weather`.
Formulas to port: `${CLAUDE_SKILL_DIR}/references/formulas.md`; tables (day length, twilight, lux,
EV, colour, moon, shadow length, games): `${CLAUDE_SKILL_DIR}/references/numbers.md`; engine setup:
`${CLAUDE_SKILL_DIR}/references/engines.md`. Values marked (working) are starting points.

## 1. Choose the realism level

| Level | Sun path | Use when |
|---|---|---|
| Real ephemeris | NOAA by latitude, longitude, date, time zone (`--model noaa`) | a real place, seasons, sims (Unreal's Sun Position Calculator) |
| Tilted arc | fixed declination, constant speed, noon at 12:00 (`--model arc --lat <tilt> --decl <d>`) | most open worlds: readable, tunable |
| Flat arc | overhead east to west (`--model arc --lat 0`) | toy and block worlds (Minecraft: sun overhead at noon, moon at midnight) |
| Fixed time per level | no cycle | linear games, baked light |

- A stylised arc is honest; a "real place" must then be right (±0.5°, `sun` check). Seasons:
  change declination per game day (±23.44°), or keep it fixed and say so in the design.
- Latitude sets the mood: at the equator civil twilight lasts 21 min and the noon sun is steep; at
  60°N day length swings 5.9–18.9 h and in June the sun only dips to −6.6° (white nights).

## 2. Sun position (NOAA)

`predict sun` runs the NOAA calculator chain (Meeus, ~0.01°; within 0.006° of JPL Horizons in 8
cases): Julian centuries → sun's longitude → declination δ and equation of time (−14.1 min about
11 Feb, +16.5 min about 3 Nov); true solar time `tst = local_min + eqtime + 4·lon − 60·tz`, hour
angle `ha = tst/4 − 180`; `sin el = sin φ sin δ + cos φ cos δ cos ha`, azimuth clockwise from north.
Rise/set: sun centre at −0.833° (refraction 34′ + radius 16′), `cos H0 = (sin h0 − sin φ sin δ)/
(cos φ cos δ)`, |cos H0| > 1 = polar day or night, day length `2·H0/15` h. Noon elevation
`90 − |φ − δ|`, lowest sun `|φ + δ| − 90`. The short series (`--model fourier`) is within 0.45°; a
one-cosine declination up to ~2° off. Drive the light from the direction vector (`toward_sun` per
engine frame), not Euler angles — pitch/yaw flips near the zenith.

## 3. Twilight and the shape of the day

| Phase | Sun centre | Light |
|---|---|---|
| Golden hour (working) | +6° to −0.833° | direct sun on the ground ≤ ~1,200 lx, 1850–2500 K |
| Civil twilight | −0.833° to −6° | sky only, 3.4 lx at −6°; bright stars appear |
| Nautical / blue hour | −6° to −12° (blue hour −4° to −8°) | horizon fades |
| Astronomical | −12° to −18° | full star field below −18° |

Civil twilight lasts 21–23 min at the equator, 29–38 min at 45°N, 42–107 min at 60°N (`predict
twilight`). Games shorten nights — Minecraft 10 min day, 50 s sunset, 8 min 20 s night, 50 s
sunrise; Valheim 21/9 min; RDR2 reportedly ~2× — via `--night-speed`, not inside light curves.

## 4. Moon

- Phase, game method: `age = (t − new-moon epoch) mod 29.530589 d`, lit fraction
  `(1 − cos(2π·age/29.53))/2`, up to ~17 h off the true phase. `predict moon` (low-precision
  ephemeris): phases within ~30 min of Espenak, lit fraction ±0.01, position ±0.15° of Horizons.
- Position: a stylised moon rides the sun's arc at hour angle `ha_sun − phase°` — full moon opposite
  the sun (rises at sunset), first quarter 90° east (rises about noon); it rises ~50.5 min later
  each day. Never a full moon high at noon or a crescent at midnight.
- Light: full moon 0.05–0.3 lx; it falls much faster than the lit area (Krisciunas & Schaefer 1991):
  half-lit gives 9% of full, a thin crescent under 1%; starlight + airglow 0.002 lx. Earthshine
  faintly lights a crescent's dark side — a cheap shader term.

## 5. Stars

- One turn per sidereal day, 86164.0905 s (23 h 56 min 4 s): 15.041°/h, rising 3 min 56 s earlier
  each night. Lock to the solar day (`--period-h 24`) only if the game never spans seasons.
- Rotate the dome about the celestial pole: axis toward north (south below the equator) at
  elevation |latitude|; facing the pole the sky turns counter-clockwise in the north. Orient a real
  star map by local sidereal time (`predict stars --date --time --lon`). Fade stars by sun
  elevation, not clock hour: bright ones from −6°, the full field by −12…−18° (working).

## 6. Game time, sleep, save, multiplayer

- Clock: int64 or float64 game seconds; float32 loses 1 s steps after 2^24 s = 194 game days.
- Shipped scales: Minecraft 72× (20 min day), BotW 60× (24 min), GTA V/RDR2 ~30× (~48 min), Skyrim
  timescale 20 (72 min), Stardew ~86× (14 min for 06:00–02:00), Animal Crossing real time. 20–48 real
  minutes per game day is the common range (working). At 72× the sun moves 0.3°/s and shadows crawl.
- Sleep or wait: fade out, jump the clock, recompute everything from it, fade in (1–3 s, working);
  timed effects read the same clock (Skyrim); multiplayer skips need the required share asleep
  (Minecraft `playersSleepingPercentage`).
- Save the clock and start date only; derive the sky on load (`kiln:save-system`). Multiplayer: the
  server owns (game time, scale, server timestamp), sends it on join and on every skip or scale
  change; clients extrapolate and slew corrections over ~1 s (working).

## 7. Light across the day

1. Drive sun energy and colour, sky/ambient energy, fog colour and the exposure target as curves
   over **sun elevation** (−18°…90°) and the weather state, not clock hours — latitude and season
   then need no re-tuning. `predict light` gives the physical baseline per elevation.
2. Real light spans 20 stops (100,000 lx noon, 0.1 lx full moon); a fully adapted night looks like
   grey day. Author a display night key and clamp exposure per period (`kiln:lighting`).
3. Colour: 1850–3000 K below 5°, 4500–6500 K above 30° (working bands); overcast ~6500 K and flat.
   At low sun the sky gives about half the light or more — ambient must not fade with the sun.
   Night: moonlight cool and desaturated (physically slightly redder than daylight; the blue is the
   Purkinje effect); film day-for-night underexposes ~2 stops, grades blue, keeps practicals warm.

## 8. Night readability

- Night is still gameplay: run the lighting skill's checks with exposure locked at night — enemy vs
  background ≥ 3:1 at combat range, no gameplay view with median L* < 15.
- Keep a floor: no-moon nights get sky/airglow ambient so silhouettes read (Minecraft's sky light
  never drops below 4 of 15); pitch black only when darkness is the mechanic, and then give the
  player a light. Signals read by shape and emissive, not hue — colour fades in dim light. Say what
  night changes: hostile spawns (Minecraft), sleeping camps and the Blood Moon (BotW).

## 9. Shadows and the one directional light

- One shadow caster (each extra shadowed directional light splits the shadow map): at dusk fade the
  sun to 0 over the last degrees and swap the shadow flag with hysteresis — key (sun + moon) ≥ ½ the
  night key, two casters ≤ 0.5 s, no switch back within 5 s (`handover` check).
- Low sun: a 2 m object casts 22.9 m of shadow at 5°, 114.6 m at 1° — past the default 100 m shadow
  distance, smeared across texels, with acne on surfaces nearly parallel to the light. Fade sun
  shadows and energy out below ~3–5° (working); raise normal bias as the sun sinks, before depth bias.
- A moving sun re-rasterises its shadow map every frame: edges shimmer, worst at high time scales.
  Soft filtering + TAA, or rotate in small steps (0.05–0.25°, working) — compare both in the gym.
  Unreal Virtual Shadow Maps: any light movement invalidates all of that light's cached pages.
  Dusk is usually the costliest hour (long shadows, fog, lights on).

## 10. Sky models and cost

- Gradient/procedural skies are cheapest; Preetham (Godot `PhysicalSkyMaterial`) is weak at sunset
  and in haze (Hosek–Wilkie 2012 fixes that); LUT atmospheres (Bruneton 2008, Hillaire 2020: Unreal
  Sky Atmosphere, HDRP Physically Based Sky) handle any sun height at a fixed cost. A night sky
  also needs rotating stars, a moon disc with its phase and a sky colour floor.
- Reflections and ambient come from a radiance map rebuilt when the sky changes. In Godot `TIME` in a
  sky shader forces REALTIME updates every frame (radiance 256); light/uniform changes update
  INCREMENTALLY over several frames. Update sky uniforms when the sun moved ≥ 0.1° (working).
- Weather (`kiln:weather`) passes cloud coverage, cloud darkness, sun occlusion and fog; the sky
  multiplies sun energy by (1 − occlusion), blends toward the overcast colour and keeps the exposure
  target continuous.

## 11. Pitfalls

- Lights switched at 0° (pop); curves keyed by clock hour jumping at 24→0 or at a season change;
  both lights casting shadows, or neither, or the swap flickering at its threshold.
- Wrong north (a constant azimuth error); local time, UTC, DST and solar time mixed up; noon
  assumed at 12:00 in a real sky (it drifts ±16 min plus the longitude offset).
- Full moon at noon; stars turning about the vertical or the wrong way; radiance rebuilt every
  frame; SDFGI and volumetric fog lagging an instant light swap.
- Night reading as a black screen on TVs, or so bright it reads as overcast day.

## 12. Engine notes (details in references/engines.md)

**Godot 4.6/4.7**: Procedural sky (4 suns, `sky_cover` stars) or Physical (one sun, `night_sky`) or
a sky shader (rotating stars, moon phase); `Sky.process_mode`/`radiance_size`; DirectionalLight3D
`sky_mode` SKY_ONLY for a disc without scene light; physical light units for `light_intensity_lux`
and `light_temperature`; Sky3D (MIT) add-on. **Unity 6**: HDRP Physically Based Sky, Celestial Body
(moon phase, earthshine); URP Procedural skybox + `DynamicGI.UpdateEnvironment()` at a cadence; APV
Lighting Scenarios. **Unreal 5.6–5.8**: Sky Atmosphere with sun (index 0) and moon (index 1),
time-sliced Sky Light capture, Sun Position Calculator (verify with `sky_check.py sun`), VSM cost.

## 13. Acceptance checks

Gym: scrubbable clock; the recorder (`kiln:acceptance`) logs clock, sun/moon directions, energies,
shadow flags, mean screen luminance and a star marker direction.

| Check | Command | PASS |
|---|---|---|
| Sun path over a day | `sun <dump> --dir sun_dir --clock clock --lat --lon --date --tz` (stylised: `--model arc --decl --noon`) | worst sample ≤ 0.5° |
| Rise, set, twilight | light events vs `predict twilight` | within 1 game minute |
| Moon | `sun <dump> --body moon ...`; phase vs `predict moon` | ≤ 1°; phase within ±1 day |
| Stars | `stars <dump> --star star_dir --clock clock --lat` | rate within 0.1%, declination spread ≤ 0.5° |
| Clock and skips | `clock <dump> --clock clock --scale 72 [--night-speed 2]` | within 2%, no backward steps |
| Light curves | `curve <dump> --value sun_energy --clock clock --max-rate <design>` | no step above the design rate |
| Exposure | `curve <dump> --value luma --per real-s --mode stops --max-rate 0.5` | ≤ 0.5 EV/s outside sleep fades (working) |
| Handover | `handover <dump> --sun sun_e --moon moon_e --sun-shadow s --moon-shadow m` | key ≥ ½ night key; ≤ 0.5 s two casters; no flicker within 5 s |
| Night readability | lighting skill contrast at new and full moon, exposure locked | enemy ≥ 3:1; median L* ≥ 15 |
| Frame cost | GPU ms each game hour over a day (qa-performance) | worst hour within budget |
| Save/load | save at dusk, load | clock and sun direction equal (≤ 1 game s) |
