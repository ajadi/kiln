# 2D effects

Details behind the destruction-vfx skill "2D effects". Effects are prepared scenes built in the
editor through the engine MCP; sprite sheets are packed and checked with the art-2d skill
(`sheet.py pack` / `check`, `references/sprite-sheets.md`). 2D light basics: art-2d skill §6.
Values marked (working) are starting points; numbers in brackets point to the sources at the end.

## 1. Choose the emitter (Godot 4.6/4.7)

| Need | Use | Notes |
|---|---|---|
| Many particles, big bursts, trails, collision | GPUParticles2D + ParticleProcessMaterial | collides with LightOccluder2D only (spheres; tune `collision_base_size`), not physics bodies; one `sub_emitter` per system and the target stops emitting on its own; trails via `trail_sections` [1] |
| Few particles, web/low-end, GPU-bound scenes | CPUParticles2D | near feature parity, slower with many particles, no new features planned; convert with the toolbar Convert to GPUParticles2D/CPUParticles2D [2] |
| Hand-drawn effect (slash, explosion, muzzle flash) | AnimatedSprite2D (SpriteFrames) or Sprite2D + AnimationPlayer `frame` track | hitboxes and sound on the same clip (art-2d §5) |
| Drawn frames on many particles (smoke puffs, debris) | particles + CanvasItemMaterial `particles_animation` | `particles_anim_h_frames` / `_v_frames`; `anim_speed` 1 plays the sheet once over the lifetime (2 = twice, enable `particles_anim_loop`) [3][4] |

Defaults to change: GPUParticles2D `fixed_fps` 30 (CPUParticles2D 0), `interpolate` on,
`visibility_rect` 200×200 px — generate it (Particles → Generate Visibility Rect) or effects pop
off-screen; `local_coords` off (particles stay in the world when the emitter moves) [1][2].
`emit_particle()` exists only on GPUParticles2D and only in Forward+ and Mobile [1]; under
Compatibility or with CPUParticles2D, pool small one-shot emitters instead. Deterministic
captures: `use_fixed_seed` + `seed`, `restart(true)` keeps the seed [1].

## 2. Pixel-art rules

| Rule | How |
|---|---|
| Palette-locked | every colour from `art/palette.hex`; particle colour ramps use palette entries with constant interpolation; no additive blending (it produces off-palette colours) unless a palette LUT pass re-quantises the screen |
| Hard alpha | alpha 0 or 1: fade by stepping down the palette ramp, shrinking frames or a dither/threshold dissolve (canvas_item shader `if (COLOR.a < 0.5) discard;`), never a smooth alpha ramp |
| Frame rate | 8–12 fps (on twos/threes, art-2d §5): particles `fixed_fps` 8–12 with `interpolate` off so they step [1]; flipbook particle `lifetime` = frames ÷ fps with `anim_speed` 1 |
| Frame counts (working) | hit spark 3–4, muzzle flash 2–3, small explosion 6–10, large explosion 10–16, smoke puff 6–8, dust 4–6, slash 3–5 |
| Particle size | 1–3 px squares or tiny drawn sprites; size steps by whole pixels (pre-drawn frames, not `scale_amount` curves) |
| No sub-pixel motion | stretch mode `viewport` (engine-godot §2D) renders at the base resolution, so every particle lands on the pixel grid; no scaled or rotated pixel sprites (pre-draw rotations) |
| Explosion layers | 1 dark contrast frame (makes the next frames read brighter) → 2 white flash, optional shrapnel lines → 3 sharp blast, sharp angles, no noise → 4+ fade: fire fades quickly, smoke slowly; at least 4 frames; centre brighter and hotter; flying bits after the blast; several small explosions for a long one [5] |
| Impact | remove in-betweens between rest and target for a stronger hit; pause one frame before impact, only for big hits, never long [6] |

## 3. Recipes (starting values, working)

| Effect | Structure |
|---|---|
| Hit spark | drawn 3–4-frame star at 12 fps (≤ 100 ms after hit-stop), oriented to the reflection; or 3–6 particles 1–2 px, life 0.1–0.25 s, 60–180 px/s in a 40° cone, palette white → yellow → orange |
| Enemy hit | sprite white flash 1–2 frames (shaders skill hit flash, 0 or 1 in pixel art) + spark + 1-frame freeze for heavy hits |
| Muzzle flash | 2–3 frames at 12–15 fps, drawn on the barrel socket; optional Light2D below |
| Explosion | layers per §2, 6–16 frames at 10–12 fps; 4–10 debris particles with gravity; dust ring 4–6 frames |
| Screen flash | full-screen ColorRect on a CanvasLayer for 1–2 frames (16–33 ms), ≤ 30–50% opacity in HD art; in pixel art swap to a brighter palette LUT for 1 frame instead of blending; obey the accessibility skill flash limits and its "reduce flashing" option |
| Light2D flash | PointLight2D energy 0 → peak in 1 frame → 0 within 100–150 ms; shadows off (PCF13 only on a few lights); small `texture_scale` — cost grows with lit pixels [7]; at most ~15–16 lights affect one CanvasItem [8]. Additive sprites are much cheaper for short bursts [7]; pixel art: quantise the light into bands (art-2d §6) |

## 4. Pooling and stutter

- Pre-spawn every pool at load. Frequent cheap effects: one shared GPUParticles2D per type +
  `emit_particle()` at the hit point (Forward+/Mobile); otherwise a ring of one-shot emitters
  re-armed with `restart()`. AnimatedSprite2D pools return on `animation_finished`.
- 2D canvas pipelines are not precompiled: the first draw of a new material/blend combination
  compiles. Draw every effect once behind the loading screen; `PIPELINE_COMPILATIONS_CANVAS` must
  stay flat during play [9].
- One atlas for all effects (and one material per blend mode) keeps 2D batching intact (all
  renderers since 4.4) [10].

## 5. Unity 6 (URP 2D Renderer)

- Particle System (CPU): Texture Sheet Animation module, Grid or Sprites mode, Time Mode
  Lifetime / Speed / FPS — FPS 8–12 for pixel art [11]; Renderer module Sorting Layer and Order in
  Layer per effect; Pixel Perfect Camera (upscale render texture) keeps particles on the grid.
  Shared emitters: `ParticleSystem.Emit(EmitParams, count)`; pools: `ObjectPool<T>`.
- VFX Graph: renders in the URP 2D Renderer and sorts with sprites (since VFX Graph 12) on
  compute-capable devices only [12]; a whole instance sorts by its bounds centre — no per-particle
  sorting against sprites (Unity forum) — UNVERIFIED in official docs. One instance per effect
  type driven by `SendEvent` with a position attribute. Use the Particle System on WebGL/OpenGL
  ES targets.
- 2D lights: Optimize 2D lights / Light Batching Debugger in the URP manual; few blend styles.

## 6. Budgets (working; set per target in GAME.md)

Live 2D particles ≤ 2k mobile / 10k desktop; ≤ 40 per hit, ≤ 300 per explosion; ≤ 4 Light2D
flashes at once; effect atlases ≤ 2 per scene layer; 2D VFX GPU ≤ 1 ms in the worst fight
(Δ `gpu_ms` with perf_compare, optimization skill); full-screen flashes per accessibility limits.

## 7. Checks

| Check | Gate |
|---|---|
| `sprite_qa.py palette` on exported effect frames and on an in-game capture mid-effect | 0 out-of-palette pixels (pixel art) |
| `sprite_qa.py alpha` on the same | 0 semi-transparent pixels (pixel art) |
| `sprite_qa.py mixels <capture> --scale k` | ≤ 0.2% broken blocks |
| Sheet JSON durations (`sheet.py check`) | every frame 1000/fps ms; counts as in §2 |
| Contact sheet (fixed seed, seeking) | peak ≤ 100 ms, nothing pops at the end |
| Pool stress (fire + explosions for 10 s) | zero runtime instantiation; `PIPELINE_COMPILATIONS_CANVAS` flat |
| Flash | accessibility skill flash check passes with "reduce flashing" on and off |
| Cost | 10 effects vs baseline, Δ `gpu_ms` within budget |

## Sources

1. Godot docs, GPUParticles2D class reference (4.7) — docs.godotengine.org/en/stable/classes/class_gpuparticles2d.html
2. Godot docs, 2D particle systems; CPUParticles2D class reference — docs.godotengine.org/en/stable/tutorials/2d/particle_systems_2d.html
3. Godot docs, ParticleProcessMaterial (`anim_speed_*`) — …/classes/class_particleprocessmaterial.html
4. Godot docs, CanvasItemMaterial (`particles_animation`) — …/classes/class_canvasitemmaterial.html
5. Pedro Medeiros (Saint11), Pixel art tutorials — Explosions part 1 (GIF, 20 frames at 80 ms) — saint11.art/blog/pixel-art-tutorials/
6. Pedro Medeiros (Saint11), Pixel art tutorials — Impact — saint11.art/blog/pixel-art-tutorials/
7. Godot docs, 2D lights and shadows — …/tutorials/2d/2d_lights_and_shadows.html
8. godot-proposals discussion #9336 (2D lights per CanvasItem hard limit, ~15–16) — github.com/godotengine/godot-proposals/discussions/9336
9. Godot docs, Reducing stutter from shader (pipeline) compilations — …/tutorials/performance/pipeline_compilations.html
10. Godot 4.4 release notes, 2D batching — godotengine.org/releases/4.4/
11. Unity Manual, Texture Sheet Animation module — docs.unity3d.com/Manual/PartSysTexSheetAnimModule.html
12. Unity VFX Graph, What's new in version 12 (2D Renderer support) — docs.unity3d.com/Packages/com.unity.visualeffectgraph@14.0/manual/whats-new-12.html
