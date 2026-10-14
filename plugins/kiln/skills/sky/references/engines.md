# Sky setup per engine

Build the nodes in the open editor through the engine MCP (scene-first); a script only advances the
clock and sets properties on those nodes from curves exposed in the inspector.

## Godot 4.6/4.7

**Scene**: `WorldEnvironment` (Environment: background Sky, ambient and reflections from Sky,
tonemap per `kiln:lighting`) → `Sky` with a sky material; `DirectionalLight3D` "Sun" (shadows on)
and "Moon" (shadows off until handover); a `SkyClock` node whose exported fields are start date,
latitude, longitude, tz, scale, night speed, model and `Curve`/`Gradient` resources over sun
elevation (energy, colour, ambient energy, fog colour and density, exposure target). Sky3D (MIT, Godot
4.3+) is a ready add-on with sun, moon, stars and game time.

**Sky material**

| Material | What it gives | Limits |
|---|---|---|
| `ProceduralSkyMaterial` | gradient sky and ground, sun discs for up to 4 DirectionalLight3Ds, `sky_cover` texture with `sky_cover_modulate` (alpha fades stars by day) | cover texture does not rotate |
| `PhysicalSkyMaterial` | Preetham scattering (Rayleigh, Mie, turbidity), one sun from the first DirectionalLight3D, `night_sky` texture | weak at sunset and high turbidity; night texture does not rotate |
| `PanoramaSkyMaterial` | an HDRI | static; blend two only with a shader |
| Sky shader (`shader_type sky`) | anything: `LIGHT0..3_DIRECTION/ENERGY/COLOR/SIZE`, `EYEDIR`, stars rotated by a uniform matrix, moon disc with phase, clouds from `kiln:weather` | you own the look and the cost |

**Radiance** (`Sky.process_mode`, docs 4.7): AUTOMATIC picks REALTIME if the shader uses `TIME` or
`POSITION`, INCREMENTAL if it uses `LIGHT_*` or custom uniforms, otherwise QUALITY. QUALITY should
not be used for a sky that changes at runtime. INCREMENTAL spreads each update over
`roughness_layers` frames (reflections lag a fast change). REALTIME uses fast filtering and needs
`radiance_size` 256 (the default); sizes 512 and above cause trouble on some hardware. Keep `TIME`
out of the sky shader; drive the sky with uniforms changed when the sun has moved ≥ 0.1° (working).

**Lights**: `sky_mode` LIGHT_AND_SKY (default), LIGHT_ONLY (lights the scene, no disc), SKY_ONLY
(disc only, no scene light — a moon disc while the moon light is off). Physical light units
(Project Settings → Rendering → Lights and Shadows → Use Physical Light Units, restart the
editor) add `light_intensity_lux` (sun ~100,000 lx, moonlit ground ~0.1 lx in the docs) and
`light_temperature` in kelvin (1850 K at sunrise, 5500–6000 K clear sun, 6500 K overcast), the
Environment background intensity in nits and `CameraAttributesPhysical` (auto-exposure EV100
min -8, max 10 by default). Without physical units drive `light_energy` and `light_color` from
the curves.

**Shadows** (`DirectionalLight3D` defaults): `directional_shadow_mode` 4 splits,
`directional_shadow_max_distance` 100 m, `directional_shadow_fade_start` 0.8,
`directional_shadow_pancake_size` 20, `shadow_bias` 0.1, `shadow_normal_bias` 2.0 — raise normal
bias first. `light_angular_distance` > 0 softens distant shadows and costs. Every extra
shadow-casting directional light lowers shadow resolution: one caster at a time.

**GI and fog**: SDFGI (Forward+) follows the moving sun but takes ~25 frames to converge, so an
instant light swap shows a lag; VoxelGI is real-time for interiors; LightmapGI cannot follow the
sun — bake indirect only for spaces whose light does not change, keep the sun in Dynamic bake mode.
ReflectionProbe "Always" is much more expensive than "Once". Volumetric fog reprojects over time:
fast light changes ghost; keep handover fades ≥ 1 s (working) or set
`light_volumetric_fog_energy` 0 on the light that is fading out.

**Probes for the recorder**: `sun.global_transform.basis.z` (toward the sun), same for the moon,
the clock in game hours, `sun.light_energy`, `moon.light_energy`, `sun.shadow_enabled`,
`moon.shadow_enabled`, mean screen luminance, and a star direction computed with the same rotation
the sky shader uses.

## Unity 6

**HDRP**: Volume → Visual Environment, sky type Physically Based Sky (Bruneton 2008 + Hillaire
2020). Update Mode OnChanged / OnDemand / Realtime (with a period); changing the time of day costs
no extra performance per the docs. Space section: emission texture and rotation for stars. Sun:
Directional Light in lux (the docs set the sun to 130,000 lx for PBSky); Celestial Body section:
Angular Diameter, Shading (Emission for a sun, Reflect Sun Light for a moon lit by the sun, Manual
with Phase and Phase Rotation), Earthshine, Surface Color texture, Flare. Exposure: Volume →
Exposure, automatic with EV100 limits. Clouds: Volumetric Clouds / Cloud Layer (`kiln:weather`).

**URP**: Procedural skybox (sun size, atmosphere thickness, sky tint, exposure; the disc follows
the Lighting window's Sun Source / `RenderSettings.sun`) or a custom skybox shader with stars.
Ambient and reflections do not follow a changing sky by themselves: call
`DynamicGI.UpdateEnvironment()` at a cadence (it stalls where async readback is unavailable), and
use realtime reflection probes with time slicing. Light colour temperature needs
`GraphicsSettings.lightsUseLinearIntensity` and `lightsUseColorTemperature`.

**Baked GI**: Adaptive Probe Volumes support Lighting Scenarios (bake day, dusk, night) and
Scenario Blending at runtime (`BlendLightingScenario`); only indirect light changes — direct light
stays scripted. Sky occlusion is the alternative for a continuously moving sky.

**Recorder**: `-sun.transform.forward` is the direction toward the sun (Unity frame: x east,
y up, z north; `--frame unity`).

## Unreal 5.6–5.8

**Actors**: Sky Atmosphere (LUT-based, Hillaire 2020; `r.SkyAtmosphere.*` scalability),
Directional Light "Sun" with Atmosphere Sun Light index 0 and "Moon" with index 1 (the second
light gets no multiple scattering), Sky Light with Real Time Capture, Exponential Height Fog,
Volumetric Cloud (`kiln:weather`), a sky sphere or sky material for stars and the moon disc rotated
by a material parameter collection fed from the clock.

**Sun Position Calculator** plugin: `BP_SunPosition` takes latitude, longitude, time zone, north
offset, date and time; the docs name no algorithm — check it with `sky_check.py sun` before trusting
it for a real place.

**Cost**: Sky Light real-time capture is time-sliced — a 128² cubemap on PS4 costs 1.465 ms in one
frame or at most 0.20 ms per frame over 9 frames; the RecaptureSky node takes 120 ms or more, never
per frame. Virtual Shadow Maps: any movement or rotation of a light invalidates all its cached
pages, so a continuously moving sun redraws its whole shadow every frame; moving lights use
`r.Shadow.Virtual.ResolutionLodBiasDirectionalMoving`. Lumen follows the sun (dynamic GI).

**Exposure**: Post Process Volume auto exposure with EV100 minimum and maximum; author a night
exposure range rather than one range for 20 stops.

**Recorder**: the light shines along its actor forward (X); toward the sun = -forward
(`--frame unreal`: x north, y east, z up).
