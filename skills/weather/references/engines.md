# Weather per engine

Setup behind §14 of this folder's SKILL.md. Every node, resource, material and project setting is
created and changed through the engine MCP named in the engine profile, in the open editor
(scene-first); scripts only drive values. Items marked (working) are recipes to prove in a gym.

## Godot 4.6/4.7

**Controller and data.**
- `Weather` autoload script; presets as a `Resource` class (`class_name WeatherPreset`, `@export`
  fields for every channel) saved as `data/weather/<state>.tres`; the schedule seed and the
  current state are a separate resource the save system writes.
- Shader globals: Project Settings → Shader Globals (`project_manage`). They must exist before a
  shader using them is saved, or it fails to compile. Types include float, vec4 and sampler2D
  (`RenderingServer.GLOBAL_VAR_TYPE_SAMPLER2D`). Set with
  `RenderingServer.global_shader_parameter_set(name, value)` — cheap, no sync; never call
  `global_shader_parameter_get` in play (stalls the render thread).
- Per-object values (character wetness): `instance uniform` + `set_instance_shader_parameter`
  (≤ 16 per shader, no textures; one value per MultiMeshInstance3D).
- Shader `TIME` wraps at `rendering/limits/time/time_rollover_secs` (3600 s): publish
  `weather_time` from the controller with periods that divide the wrap.

**Rain rig (a prepared scene `fx/weather/rain_rig.tscn`, instanced once, follows the camera).**
- `GPUParticles3D` with `local_coords = false` (drops stay in the world while the rig moves),
  ParticleProcessMaterial `emission_shape = EMISSION_SHAPE_BOX` (`emission_box_extents` are half
  sizes), direction (0, −1, 0), spread 0–5°, initial velocity = fall speed, gravity ≈ 0,
  `particle_flag_align_y` on so streaks follow velocity (working).
- `amount` = the maximum from `predict rain` (allocated and paid for even when unused);
  `amount_ratio` = intensity (no restart; changing `amount` restarts the system);
  `preprocess` ≈ lifetime so rain is already falling when it starts; `visibility_aabb` covers the
  box plus one second of motion — collisions and attractors work only inside it.
- `GPUParticlesCollisionHeightField3D` in the rig: `size` = the box, `resolution` 512 or 1024,
  `update_mode = UPDATE_MODE_WHEN_MOVED` (`ALWAYS` is costly), `follow_camera_enabled = true`,
  `heightfield_mask` = roof and terrain layers. A heightfield stops drops on roofs (right for
  vertical rain) but has no overhangs and tells surface shaders nothing.
- ParticleProcessMaterial `collision_mode = COLLISION_HIDE_ON_CONTACT` and `sub_emitter_mode =
  SUB_EMITTER_AT_COLLISION` with a small splash `GPUParticles3D` as `sub_emitter`
  (`sub_emitter_amount_at_collision` 1–3); `collision_base_size` for floating or sunk hits.
- Draw pass: a thin QuadMesh (about 0.01 × 0.4 m, working), unshaded alpha material, fog and
  shadows off on the streak material.
- Snow: the same rig with slower fall (≈ 1 m/s), turbulence on (`turbulence_enabled`, noise
  strength and scale), larger lifetime, collision RIGID with high friction or HIDE_ON_CONTACT.

**Rain occlusion map (working).**
- `SubViewport` (256–512², `use_hdr_2d = true` for a float target, `render_target_update_mode`
  ALWAYS or toggled by the controller when the camera moved > 1–2 m) with an orthographic
  `Camera3D` looking straight down from above the scene, `cull_mask` = occluder layers, its own
  `Environment` (no fog, linear tonemap).
- A 2 × 2 QuadMesh in front of that camera on its own layer with a spatial shader: `render_mode
  unshaded, depth_test_disabled`; `POSITION = vec4(VERTEX.xy, 1.0, 1.0);` in `vertex()`; in
  `fragment()` read `hint_depth_texture`, unproject with
  `INV_PROJECTION_MATRIX * vec4(SCREEN_UV * 2.0 - 1.0, depth, 1.0)` and write
  `camera_height + view.z` (world height of the top occluder) to `ALBEDO`.
- Publish `get_texture()` as `weather_rain_occlusion` and the camera's xz rectangle as
  `weather_occlusion_rect`. Tilt the camera with the wind for slanted rain. For static levels,
  bake the same render once in the editor to an image and use it outside the dynamic window.
- Gameplay shelter tests (is the player dry?) use a ray or shape cast up at 2–5 Hz, not the map.

**Fog and sky.**
- `WorldEnvironment` → `Environment`: `fog_enabled`, `fog_mode = FOG_MODE_EXPONENTIAL`,
  `fog_density = σ` (fog amount is `1 − exp(−d·density)`), `fog_height` / `fog_height_density`
  for valley fog (amount `1 − exp(min(0, (y − fog_height)·height_density))` from the fragment's
  height only, not the path length; the larger of the two amounts wins), `fog_sky_affect`,
  `fog_aerial_perspective` (needs a sky background). Depth mode (`FOG_MODE_DEPTH`, begin/end/curve)
  is artistic, not physical.
- Volumetric fog (Forward+ only): `volumetric_fog_enabled`, `volumetric_fog_density = σ` (Beer's
  law per froxel slice), `volumetric_fog_length` 64 m by default — beyond it only the regular fog
  shows, so keep both; `volumetric_fog_albedo` near white for mist, darker for smoke; anisotropy
  0.2. FogVolume nodes (box, ellipsoid, cone, cylinder, world) with a FogMaterial: positive
  density adds local fog, negative density removes it inside buildings; cost follows screen size.
- Sky, sun, moon and time of day: the sky skill. Lightning: a DirectionalLight3D with
  `shadow_enabled` off and `light_volumetric_fog_energy` 0, driven by the controller's envelope.

**Clouds (weather owns them).** Godot has no built-in volumetric clouds. Default: a cloud layer
inside the sky shader (`shader_type sky`) reading `weather_clouds` and `weather_wind`, computed in
the quarter-resolution pass (`render_mode use_quarter_res_pass`, branch on
`AT_QUARTER_RES_PASS`). The radiance cubemap re-renders whenever a uniform changes, every frame
if the shader uses `TIME`, and when lights change: drive drift from a global the controller
updates, set Sky `process_mode` to realtime with a small `radiance_size` only if clouds must
light the scene every frame, and check the cost (working). Cloud shadows: a scrolling noise term
in surface shaders driven by the same globals (working). Volumetric cloud addons: check licence
and version before use [U].

**Wind.** A `vec4 weather_wind` global for vegetation and particle shaders (shaders skill vertex
wind); particles via ParticleProcessMaterial direction/velocity or turbulence set by the
controller; Area3D wind properties affect SoftBody3D only (Jolt from 4.7); rigid bodies get the
game's own drag (fields-forces).

**Audio.** Beds as `AudioStreamPlayer` on a `Weather` bus; an indoor bus with
`AudioEffectLowPassFilter` and the controller crossfading on shelter; `Area3D.audio_bus_override` +
`audio_bus_name` reroute `AudioStreamPlayer3D` sources inside an interior; thunder as
`AudioStreamPlayer3D` at the strike direction started after `d / c` (Godot does not delay sound by
distance), `attenuation_filter_cutoff_hz` / `attenuation_filter_db` for distant dullness.

## Unity 6

- **Bus**: `Shader.SetGlobalFloat / SetGlobalVector / SetGlobalTexture` from the controller;
  Shader Graph reads a global through a property with "Exposed" unchecked and the same reference
  name. Presets as ScriptableObjects (shared, read-only in builds; runtime state elsewhere).
- **Rain**: VFX Graph (compute; no GLES) parented to the camera, world-space simulation, "Collide
  with Depth Buffer" block in Update (main camera depth; an opaque output collides with its own
  depth — use a transparent output); Shuriken `ParticleSystem` with the Collision module for
  low-end. Splashes on collision events or a separate camera-front emitter.
- **Occlusion map**: an orthographic top-down camera with a culling mask rendering depth to a
  RenderTexture (or a URP renderer feature), set as a global texture with its rect (working).
- **Fog**: built-in and URP `RenderSettings.fog`, `fogMode = Exponential`, `fogDensity = σ`
  (Exponential Squared: 1.978 / V — the shader computes `exp(-(density·z)^2)`); URP has no
  built-in volumetric fog [U for 6.3+; third-party assets fill it]. HDRP Fog override: Fog
  Attenuation Distance = 1 / σ (63% of background light gone at that distance), Base Height,
  Maximum Height, Volumetric Fog with denoising; Local Volumetric Fog for patches.
- **Clouds**: HDRP Volumetric Clouds override (and Cloud Layer for 2D skies), driven from the
  controller's coverage; URP: a skybox/cloud-layer shader reading the globals or a third-party
  asset (check licence).
- **Wind**: `WindZone` (Directional or Spherical; Main, Turbulence, Pulse Magnitude, Pulse
  Frequency) moves Terrain trees and particle systems with External Forces only — not Terrain
  grass and not rigid bodies; `Cloth.externalAcceleration` / `randomAcceleration` for cloth.
- **Audio**: AudioMixer snapshots for indoor/outdoor (`TransitionTo(seconds)`), exposed mixer
  parameters for intensity, `AudioLowPassFilter`; thunder delayed by the script.

## Unreal 5.6–5.8

- **Bus**: one Material Parameter Collection `MPC_Weather` (≤ 1024 scalars + 1024 vectors; a
  material references ≤ 2 collections; adding parameters recompiles every material using it —
  add them early; renaming breaks Blueprint nodes). Set with "Set Scalar/Vector Parameter Value"
  (Blueprint) or `UKismetMaterialLibrary::SetScalarParameterValue` (C++). Collections hold no
  textures: materials sample the occlusion render target asset directly and read its rect from
  the MPC.
- **Controller**: a World Subsystem or manager actor; presets as Data Assets. No built-in weather
  controller; Ultra Dynamic Sky/Weather (Fab, paid) is common — check its licence before use.
- **Rain**: Niagara GPU system attached to the camera, world space; collision by Scene Depth
  (cheap, inaccurate, particles off-screen lose collision), Distance Fields (needs mesh distance
  fields; detail falls with distance) or GPU Ray Traces (experimental, DX12 + hardware ray
  tracing, one frame late).
- **Occlusion map**: a Scene Capture 2D, orthographic, top-down, capture source scene depth, into
  a render target updated when the camera moves (working).
- **Fog and clouds**: Exponential Height Fog (Fog Density and Height Falloff are unitless factors —
  calibrate with `visibility`; Volumetric Fog for lit fog), Local Fog Volumes (radial and height
  fog given as extinction at the centre; uniform scale only). Volumetric Cloud is weather's: its
  cloud material reads coverage and darkness from the MPC; Sky Atmosphere and the sun belong to
  the sky skill.
- **Wind**: WindDirectionalSource moves SpeedTree only; materials read MPC wind; Chaos Cloth has
  its own wind; Physics Fields push rigid bodies (fields-forces).
- **Audio**: MetaSounds with intensity parameters; Audio Volumes with interior settings (exterior
  volume and low-pass) for shelters; thunder delayed by the controller.
