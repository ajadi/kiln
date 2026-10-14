# Weather recipes

Details behind this folder's SKILL.md: presets, the bus, a controller sketch, shader snippets, the
lightning envelope, the audio matrix and gameplay modifiers. Numbers marked (working) are
starting points to tune in a gym; [U] means no source confirmed them. Engine-specific setup is in
`engines.md`.

## 1. Presets (working)

Visibility comes from the definitions in the skill (fog < 1 km, mist 1–2 km, haze 2–5 km, NWS
heavy snow ≤ ¼ mile ≈ 400 m, light snow > ⅝ mile ≈ 1 km, dust storm 200 m–1 km, severe < 200 m).
Rain visibilities are working values [U]. σ = 3.912 / V (`predict fog`).

| State | Intensity | V (m) | σ (1/m) | Wind m/s (Beaufort) | Cloud cover | Streaks /m³ near | Wet 0→0.8 | Thunder |
|---|---|---|---|---|---|---|---|---|
| Clear | 0 | 30 000 | 0.00013 | 0–3 (0–2) | 0–0.3 | 0 | — | no |
| Overcast | 0 | 10 000 | 0.00039 | 2–6 (2–4) | 0.7–0.9 | 0 | — | no |
| Light rain | 0.33 | 5 000 | 0.00078 | 2–6 | 0.8 | 0.2 | 120 s | no |
| Heavy rain | 0.66–1 | 1 000 | 0.0039 | 5–10 (3–5) | 1.0 | 1.0 | 30 s | rare |
| Storm | 1 | 800 | 0.0049 | 10–20 (6–8) | 1.0 | 1.5 | 20 s | yes |
| Fog | 0 | 200 | 0.0196 | 0–2 | any | 0 | slow dew | no |
| Light snow | 0.33 | 1 500 | 0.0026 | 0–5 | 0.9 | 0.3 flakes | — | no |
| Blizzard | 1 | 100–400 | 0.039–0.0098 | 15+ (7+) | 1.0 | 3 flakes | — | no |
| Sand/dust storm | 1 | 200 | 0.0196 | 12+ (6+) | 0.3 | dust sheets | — | no |

Drying (working): surfaces 0.8 → 0.1 in 60–90 s after rain (Lagarde: "about 1 minute"), puddles
3–5 min, faster in sun and wind. Lagarde's Remember Me presets (light / moderate / heavy): rain
intensity 0.33 / 0.66 / 1.0, splashes 20 / 40 / 60, wet level speed in 0.6 / 0.75 / 1.0 and out
0.2, puddle flood speed in 0.1 / 0.3 / 0.7 and out 0.05, heightmap flood in 0.2 / 0.5 / 0.85 and
out 0.1, fog amount 0.15 / 0.4 / 1.0 (units of the speeds [U]; the ratios are the lesson: wetting
is 3–5× faster than drying, puddles drain far slower than they fill).

## 2. The bus (global parameters)

| Name (working) | Type | Range | Written by | Read by |
|---|---|---|---|---|
| `weather_rain` | float | 0–1 | controller | rain shaders, ripples, streak opacity |
| `weather_wetness` | float | 0–1 | controller (accumulator) | every lit surface shader |
| `weather_puddles` | float | 0–1 | controller (accumulator) | ground shaders |
| `weather_snow` | float | 0–1, cover = tanh(depth / 0.1 m) (FSM) | controller (depth, density) | surface shaders, foliage |
| `weather_wind` | vec4 | xyz m/s, w gust 0–1 | controller | vegetation, particles, clouds |
| `weather_time` | float | wrapped s | controller | ripples, wind phase |
| `weather_rain_occlusion` | sampler2D | heights | occlusion rig | wetness, splashes, snow mask |
| `weather_occlusion_rect` | vec4 | xz origin, xz size | occlusion rig | same |
| `weather_clouds` | vec4 | x coverage, y darkness, z type, w drift phase | controller | cloud layer, sky (sky skill), cloud shadows |
| `weather_lightning` | float | 0–1 | lightning envelope | sky, clouds, emissive |

Keep the list in `memory/registries.md`. Godot globals cost one entry in the uniform buffer each;
a vec4 packs four floats.

## 3. Controller sketch (engine-neutral)

```
state: type, intensity, wind, gust, temperature, visibility, coverage, precipitation
accumulators: wetness, puddles, snow
transition: from_preset, to_preset, elapsed, duration, shape
schedule: seed, entries [(start_game_time, type, intensity, duration)], cursor
overrides: stack of (preset, blend_s)

step(dt):                                    # 2-10 Hz, fixed step
    advance schedule: when game_time >= next.start and dwell >= min_dwell -> begin transition
    elapsed += dt; u = shape(elapsed / duration)       # linear, smoothstep or 1 - exp(-t/tau)
    blend every channel from_preset -> to_preset by u (clouds/fog lead by ~20 %, rain lags)
    exposed_rain = precipitation * (temperature > 1 C)  # rain; snow when < -1 C, hysteresis
    wetness += (exposed_rain > 0 ? wet_rate * exposed_rain * (1 - wetness)
                                 : -dry_rate * wetness * drying_factor) * dt
    puddles likewise with their own rates
    snow: depth += new-snow rate * dt at 100 kg/m3; density settles toward 300 cold / 500
          melting (tau ~200 h); melt by energy — numbers and checks in fluids-granular
          (fluid_check.py predict snowfall | settle | melt); publish cover = tanh(depth / 0.1)
    sub-effects: switch on at on_threshold, off at off_threshold, each with min dwell
per frame: interpolate published values, set globals, drive particles (amount_ratio),
           fog, lights, audio parameters
forecast(n): replay the seeded RNG from the cursor without changing state
save(): everything above except per-frame interpolation
```

Rain/snow by temperature with hysteresis: rain above +1 °C, snow below −1 °C, keep the current
type in between (working).

## 4. Shader snippets (Godot shading language; port the math elsewhere)

Wet surface after Lagarde ("Water drop 3b"); Godot works in roughness, Lagarde in gloss:

```glsl
global uniform float weather_wetness;
global uniform float weather_puddles;
uniform float porosity : hint_range(0.0, 1.0) = 0.6;

void apply_wet(inout vec3 albedo, inout float roughness, inout float specular,
               float metallic, float wet) {
    float p = porosity * (1.0 - metallic);           // metals and smooth parts are not porous
    float f = mix(1.0, 0.2, p);                      // full wet porous albedo x0.2..x1
    albedo *= mix(1.0, f, wet);
    float gloss = 1.0 - roughness;
    gloss = mix(1.0, gloss, mix(1.0, f, 0.5 * wet)); // Lagarde: boost limited by 0.5 * wet
    roughness = 1.0 - gloss;
}
```

Non-porous surfaces get no gloss from this formula (f = 1); they gain it from the water layer:

```glsl
// cavity: 0 high, 1 deepest (height or vertex colour); flat: smoothstep(0.9, 0.98, n_world.y)
float puddle = smoothstep(0.0, 0.4, weather_puddles - (1.0 - cavity)) * flat * exposed;
NORMAL_MAP = mix(NORMAL_MAP, vec3(0.5, 0.5, 1.0), puddle);   // flat water
roughness = mix(roughness, 0.02, puddle);
specular = mix(specular, 0.25, puddle);   // Godot SPECULAR 0.5 = F0 0.04; water F0 0.02
```

Ripples (Remember Me): one tiling ripple normal texture; layer i turns on from intensity i·0.25:
`vec4 on = clamp(weather_rain * 4.0 - vec4(0.0, 1.0, 2.0, 3.0), 0.0, 1.0);` with time multipliers
(1.0, 0.85, 0.93, 1.13), offsets (0, 0.2, 0.45, 0.7) and time scale 1.6; show ripples only where
`puddle > 0` or the drench layer is thick.

Exposure from the occlusion map (heights of the highest occluder per texel, world metres):

```glsl
global uniform sampler2D weather_rain_occlusion : filter_linear, repeat_disable;
global uniform vec4 weather_occlusion_rect;      // xy = world xz origin, zw = world xz size
float rain_exposure(vec3 p) {                    // 1 = open sky above p
    vec2 uv = (p.xz - weather_occlusion_rect.xy) / weather_occlusion_rect.zw;
    if (any(lessThan(uv, vec2(0.0))) || any(greaterThan(uv, vec2(1.0)))) return 1.0;
    float top = texture(weather_rain_occlusion, uv).r;
    return smoothstep(top - 0.15, top - 0.05, p.y);   // soft edge, small bias (working)
}
```

Outside the map's rectangle return the static baked exposure (vertex colour or a level-wide
top-down height baked once in the editor) instead of 1, or far roofs leak.

Snow cover:

```glsl
global uniform float weather_snow;                            // cover = tanh(depth / 0.1 m)
float snow_cover(vec3 n_world, float noise, float exposed) {
    float facing = n_world.y + (noise - 0.5) * 0.2;           // breakup
    return exposed * smoothstep(1.0 - weather_snow - 0.1, 1.0 - weather_snow + 0.1, facing);
}
// albedo 0.8 fresh -> 0.5 aged (FSM, via fluids-granular; check exposure), roughness ~0.6
// (working); raise vertices by cover * depth only where the mesh has the density for it
```

Per-object wetness for characters and props: Godot `instance uniform float wet;` set with
`set_instance_shader_parameter("wet", w)` (≤ 16 instance uniforms per shader, no textures); the
shader uses `max(weather_wetness * exposed, wet)`.

## 5. Wet characters (working)

- A wet value per character: rises at the rain wet rate × exposure (ray or capsule test up,
  2–5 Hz), set to 1 below the water line (a height mask in the shader from the swim depth),
  dries 2–3× slower than surfaces, faster near fire.
- Cloth darkens and gains gloss through the same `apply_wet`; skin gains gloss only; hair gains
  gloss and clumps (a separate hair material parameter).
- Drips: a small particle emitter on hems, sleeves and hair tips while wet > 0.3; 30–60 s after
  leaving the rain or water.
- Wet footsteps and a slight squelch layer while boots are wet (audio).

## 6. Lightning envelope (working)

- Burst: 1–3 pulses at 0, 0.06–0.08, 0.13–0.16 s; each pulse rises in 1 frame and decays over
  50–80 ms; then ≥ 1 s of quiet before the next burst (photosensitivity; `predict flash`).
- Drive `weather_lightning` (sky and cloud emission ×(1 + k·pulse)) and one directional light
  from the strike's direction; shadows off for the flash light, volumetric fog energy 0.
- Bolt mesh or sprite only for cloud-to-ground strikes (~25% of flashes) within ~5 km; the rest
  light clouds from inside.
- Thunder: schedule at d / c after the first pulse; level and brightness fall with distance (a
  low-pass on far thunder, working); no thunder beyond ~16 km.
- Strike targets for gameplay: the tallest, most isolated object within the storm cell; metal
  gear raises the chance (BotW); telegraph with sparks and a sound 2–3 s before (working).
- Reduce flashing on: one pulse, ≤ 10% luminance change, sky only.

## 7. Audio matrix

| Layer | Source | Driven by | Indoors |
|---|---|---|---|
| Far wash | stereo loop or procedural noise bed | intensity: level and a low-pass that opens with intensity | low-passed, quieter |
| Mid patter | loop | intensity | low-passed |
| Near drops | grains/one-shots around the listener | intensity × exposure, surface type (leaves, metal, stone, water) | replaced by the roof layer |
| Roof / drum | loop per roof material | intensity | only under a roof |
| Drips, gutters | positional emitters at edges | intensity, continues 30–60 s after rain | yes |
| Wind bed | loop | wind speed | low-passed |
| Gusts | loop or one-shots | gust signal (same as vegetation) | low-passed |
| Thunder | one-shots, distance sets delay, level, filter | strike distance | low-passed |
| Snow | wind dominates; footsteps crunch; quiet bed | intensity, wind | — |

Procedural rain in Wwise (Audiokinetic): layers for high boiling, low boiling, stereo noise and
individual drops, with an intensity parameter changing filters and the low layer's level; drops
randomise rate, pitch, volume and pan. Indoor/outdoor crossfade 0.5–1 s at the shelter edge
(working). Captions for weather sounds that matter to play (approaching storm, close thunder).

## 8. Gameplay modifiers

| Effect | Driver | Number | Source / skill |
|---|---|---|---|
| Tyre grip | wetness, snow, ice | μ dry asphalt 0.8–0.9, wet 0.5–0.7, packed snow 0.2, ice 0.1 | vehicles |
| Walking slip | same | walking needs μ ≈ 0.2; ice 0.02–0.09 | traversal |
| Climbing | wetness | slip while wet (BotW); gear and elixirs counter (TotK Froggy set, sticky elixir) | traversal |
| Sight | σ | ln(C₀ / 0.02) / σ | Koschmieder, game-ai |
| Hearing | rain/wind noise rise ΔL dB | radius × 10^(−ΔL/20) | spherical spreading, game-ai |
| Cold | wind chill | 13.12 + 0.6215T − 11.37V^0.16 + 0.3965T·V^0.16 (V km/h) | North American/UK index (JAG/TI 2001) |
| Fire | rain | exposed fires go out (BotW); spread blocked (Minecraft) | elements-materials |
| Lightning | metal gear | telegraphed strike (BotW) | elements-materials |
| Cargo | timefall | containers age; shelters and spray repair (Death Stranding) | design |
| Stealth | sandstorm, fog | both sides see and hear less (MGSV sandstorms) | game-ai |

## 9. Game references

- Remember Me (Dontnod, Lagarde's "Water drop" series): rain core 2.8 ms in a 3 ms budget at 30
  fps on PS3/360, 720p; 256² occlusion depth over 20 × 20 m; 4 screen layers of drops on a
  camera-attached mesh; 20/40/60 splashes; one 256² ripple map.
- Horizon Zero Dawn (Schneider, SIGGRAPH 2015): weather map R coverage, G precipitation, B cloud
  type; precipitation → cumulonimbus at 70% coverage; clouds to 35 km; ~2 ms after temporal
  reprojection (1 of 16 pixels per frame) from ~20 ms.
- Ghost of Tsushima (Rockenbeck, GDC 2021): wind for thousands of cloth pieces, hundreds of
  thousands of particles, millions of grass blades; global wind constant in direction with
  Perlin-noise magnitude; vorticles (position, orientation, radius, direction) summed brute force
  up to hundreds; Guiding Wind points to the goal.
- The Long Dark: weather evolves (fog builds, wind dies down), states 2–12 h, harder modes change
  faster with more blizzards; weather affects speed, vision, warmth and clothing wetness.
- Minecraft Java: rain 12 000–24 000 ticks, clear 12 000–180 000, thunder 3 600–15 600, uniform;
  fire blocked by rain.
- Breath of the Wild / Tears of the Kingdom: regional weather every 4 in-game hours; current
  weather by the minimap; rain → slipping while climbing, fires out; metal draws lightning;
  TotK Froggy set prevents slipping.
- Stardew Valley: tomorrow's weather on the TV.
- Death Stranding (1 and 2): timefall ages containers; shelters repair; forecast-based routing.
- Red Dead Redemption 2: wet clothing, mud, persistent snow trails; its SIGGRAPH 2019 talk covers
  an integrated sky, cloud, fog and volumetrics pipeline (internals not read here [U]).
- The Last of Us Part II: character render targets for wetness and blood (SIGGRAPH 2020).
- Borderlands 4 (GDC): UE5 built-ins plus a custom render pass for weather on surfaces [U details].
- Diablo IV (GDC): dynamically accumulating puddles and snow-topped rocks in shaders [U details].
