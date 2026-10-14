---
name: destruction-vfx
description: Local damage models, part detachment, death collapse, destructible props and walls, and the real-time VFX that sell them — sparks, smoke, fire, explosions, missile trails, lasers, muzzle flashes, decals, debris — with timing recipes, value hierarchy, pooling, budgets and objective checks. Engine-neutral rules plus Godot 4.6/4.7 specifics (see the engine skill for Unity/Unreal equivalents). Use for damage, destruction, death, particles, decals or impact effects.
user-invocable: false
---

# Destruction and effects

## Damage model defaults (unless the design says otherwise)

1. **Damage is local.** A hit damages the part whose hurtbox it touched. Only an explicit,
   per-part `core_transfer` fraction passes damage on; shooting the hull never detaches limbs.
2. **A part detaches only because of its own state** — its HP reached zero or its mount's did.
   Destroying the core does not shed intact limbs.
3. **Losing a part changes behaviour**: a destroyed gun stops that weapon, a destroyed sensor
   degrades aim, a destroyed leg changes the gait or drops the body. Weak points are visible
   parts of the model (not UI markers), with their own HP and a behavioural consequence.
4. **Death is physical**: the machine powers down (lights off, servos stop, AI off) and the body
   settles on the ground — physical bones made in the editor, or a prepared wreck scene of
   rigid segments. Never frozen in its last pose.
5. **Detached parts are prepared scenes** (`part_<name>_debris`): on detach, hide the attached
   part and spawn its debris body from a pool at the current transform, with the velocity at the
   attachment point plus the hit impulse.
6. **Data-driven**: part HP, armour, multipliers, thresholds and consequences live in data
   resources so tuning needs no code change.

Unit-test the rules; the qa-damage acceptor checks them in the running game.

## Destructible props and structures

- Pre-fractured, art-directed: intact → damaged → destroyed variants; fracture pieces made in
  Blender (Cell Fracture extension, through the Blender MCP), 8–30 chunks with convex colliders,
  interior faces with their own material. No runtime mesh slicing.
- Cover the swap with a dust and debris burst in the same frame.
- Structures: an authored support graph (each chunk lists the chunks it rests on); on a break,
  flood-fill from ground anchors and drop unsupported chunks.
- Re-bake navigation for regions whose route changed.
- Small debris = GPU mesh particles with collision (Godot 4.7: `use_rotation_3d` lets chunks
  tumble); big chunks = pooled rigid bodies that freeze when asleep and are recycled off-screen.

## VFX principles

- Size and brightness match gameplay importance. If everything is important, nothing is.
- Value hierarchy, highest first: enemy threats (telegraphs, incoming lasers/missiles — one
  saturated hue reserved for them) → the player's own hit feedback (warm white-yellow) → ambient
  fire, smoke and dust (lower value and saturation). Ambient effects never out-value threats.
- Timing: anticipation → impact → dissipation; the main action is over within the first
  quarter of the effect's life; peak at or before 100 ms. "If it feels long, it is too long."
- Avoid 0% and 100% value/saturation; one dominant colour per effect.
- Smoke is lit. Muzzle flashes and impacts get the most brightness; embers recede.
- Restraint: after the player's own impacts the central 20% of the screen is not more than half
  covered for more than 300 ms; weak points stay visible.
- Flashing: ≤ 3 large flashes per second. Never encode information only in colour.

## Recipes (starting values — tune with contact sheets)

| Effect | Structure |
|---|---|
| Bullet impact on armour | flash billboard HDR ×4–6, 0.2 m, 0–33 ms · 12–20 sparks, life 0.15–0.35 s, 35° cone around the reflection vector, 6–14 m/s, gravity, ramp white ×6 → orange ×3 → red → alpha 0 · 2–3 lit puffs 0.4–0.8 s · decal hole 0.06–0.1 m with emissive rim fading 0.5–1 s. Concrete: no sparks; dust + 4–8 chip particles |
| Damaged part sparks | bursts of 4–8 every 0.3–1.5 s; rate rises with that part's own damage |
| Smoke from damaged part | 6–10 /s, life 2.5–4 s, 0.3 → 1.5 m, rising 1–2 m/s with damping, lit, albedo value 0.15–0.25, fade in 10% / out 40% of life, soft/proximity fade 0.5 m |
| Fire on a part | additive eroded-noise or flipbook, 12–20 /s, life 0.4–0.8 s, HDR orange ×2–4 → hands off to smoke · one light per fire cluster: range 2–4 m, energy 1.5–3, noise flicker ×0.75–1.25 at 6–10 Hz, no shadows, distance fade 20–30 m |
| Explosion | (mech death: 0.5–1.5 s anticipation of escalating sparks/smoke) · 0 ms light peak range 10–15 m → 0 by 150 ms · fireball 6–12 particles, full size by ~100 ms, to dark smoke by 60% life · 30–60 embers + 10–25 mesh debris with collision (0–600 ms) · ground dust ring (0–300 ms) · smoke column 10–20 lit particles (150 ms–4 s) · scorch decal 2–4 m · camera shake |
| Missile trail | HDR core sprite · flame ribbon 0.1–0.2 s · world-space smoke 40–80 /s, life 1.5–3 s, 0.2 → 1.2 m, lit · the trail is its own pooled node following the missile; on impact stop emitting and let it live out (freeing the missile must not delete the trail) |
| Mech laser | telegraph 300–800 ms (muzzle charge glow + faint aim line) · core white HDR ×4–8, 0.03–0.06 m · glow shell ×1.5–3, 0.2–0.4 m · UV scroll 5–20 m/s scaled by beam length · width pulse ±10% · fade 80–150 ms · impact sparks, light, burn decal |
| Muzzle flash | 16–33 ms per shot: crossed quads + front sprite, random roll, scale ×0.8–1.2, random flipbook frame · light range 3–5 m, 30–50 ms, no shadows · after 5+ rounds a 0.5–1 s smoke wisp · rendered with the first-person weapon |
| Wall collapse dust | 8–16 large lit particles, life 2.5–5 s, outward 2–4 m/s, high damping, beige-grey value 0.5–0.65, alpha ≤ 0.4, soft fade 1 m · 20–40 chips · 2–3 s grit streams |
| Decals | ring-buffer pools: 64–128 bullet holes, 16–32 scorches; fade from 25–40 m; on moving mech parts prefer a damage parameter in the part's material |
| Hit-stop / shake | hit-stop 40–80 ms on the target's animation only (not global time scale) · shake: trauma 0–1, offset = max angle × trauma² × noise, rotation only in 3D, roll ≤ 3°, decay 1–1.5/s, a setting to disable it |

## Pooling and lifecycle

- Pre-spawn every pool at load; never instantiate in the firing path.
- Cheap frequent effects (sparks, dust puffs): one shared emitter per type, `emit_particle()` at
  the hit point. Composite effects (explosions): pooled scene instances.
- Reuse a pooled one-shot by moving it and calling `restart()` — setting `emitting = true` just
  after `finished` may silently fail.
- LOD: change `amount` or swap to a lighter scene (`amount_ratio` alone saves nothing).

## Godot 4.6/4.7 specifics

- Sparks: `vertex_color_use_as_albedo` on, colour ramp `GradientTexture1D.use_hdr = true` (else
  colours clamp and nothing blooms), `explosiveness = 1`, align Y to velocity for streaks;
  `fixed_fps` default 30 — set 0 or 60 for short bursts and colliding sparks. Since 4.6 glow
  blends before tonemapping — retune emissive values from older versions.
- Decals: Forward+ or Mobile only, no custom shaders; Forward+ has 512 clustered elements in view
  shared by lights, decals and probes; `modulate.a` fades albedo but not emission (tween
  `emission_energy`); `distance_fade_enabled`; thin projection boxes; `normal_fade` 0.3–0.5;
  `cull_mask` keeps decals off characters and the weapon.
- Transient lights: shadows off, `light_volumetric_fog_energy = 0` (else they ghost in fog).
- Turbulence is expensive — a few systems on screen at most. Collision/attractors work only
  inside the visibility AABB (max 32 each); SDF colliders are static — use box colliders where
  destruction changes geometry. Sub-emitters: one per system (At Collision + hide-on-contact =
  replace on impact). Trails need `use_particle_trails` on the material.
- FogVolume only for large slow haze, not impact smoke (moving volumes ghost).
- Shader stutter: ubershaders + pipeline precompilation (4.4+) cover scenes instantiated once at
  load — prewarm every VFX scene; `PIPELINE_COMPILATIONS_DRAW` must stay 0 on first spawn.
- Deterministic capture: `use_fixed_seed`/`seed` (4.4+), `speed_scale = 0` +
  `request_particles_process(t)` to seek an exact time.
- Flipbooks without external tools: bake Mantaflow smoke/fire in Blender through the MCP, render
  ortho with transparent film, tile into an atlas; or procedural noise + alpha-erosion shader.

## 2D effects

Details, recipes and sources: `${CLAUDE_SKILL_DIR}/references/2d-effects.md`; sheets: art-2d skill.

- GPUParticles2D for many or large systems (LightOccluder2D collision, trails; `emit_particle()`
  not in Compatibility); CPUParticles2D for few particles, web or low-end. Drawn effects are
  flipbooks (AnimatedSprite2D, or particles with CanvasItemMaterial `particles_animation`) in one
  atlas so they batch.
- Pixel art: palette colours, alpha 0 or 1 (fade by palette steps or dither), particles 1–3 px,
  8–12 fps (`fixed_fps` 12, `interpolate` off; flipbook `lifetime` = frames ÷ fps), no scaled or
  rotated sprites, base-resolution rendering (no sub-pixel motion). Explosion: dark frame → white
  flash → sharp blast → fire fades fast, smoke slowly; ≥ 4 frames.
- Hit spark 3–4 frames along the reflection; screen flash 1–2 frames (accessibility skill
  limits); Light2D flash ≤ 150 ms, no shadows — additive sprites are cheaper.
- Pool as above; 2D pipelines are not precompiled — draw each effect once at load.
- Unity: Particle System + Texture Sheet Animation (Time Mode FPS); VFX Graph needs compute —
  check how it sorts against sprites.
- Check: `sprite_qa.py palette`/`alpha` on frames and an in-game capture;
  `PIPELINE_COMPILATIONS_CANVAS` flat during play.

## Budgets (working; set per target GPU in GAME.md)

VFX GPU ≤ 2 ms at 1080p in the worst fight; one close explosion ≤ 0.5 ms; overdraw hot spots ≤
4–6 layers for ≤ 1–2 s; live particles ≤ 5–10k, ≤ 300 per explosion; ≤ 8 simultaneous VFX lights;
decals in view ≤ 160; ≤ 3 turbulent systems on screen.

## Checks

1. Contact sheet at 0, 16, 33, 66, 100, 200, 400, 800, 1600, 3200 ms (fixed seed, seeking):
   peak ≤ 100 ms, main action done by 25% of life, nothing pops at the end.
2. Overdraw view of the worst-case scene.
3. Per-effect GPU cost: 10 instances in front of a fixed camera minus baseline GPU time.
4. No compile stutter on first spawn.
5. Grayscale test: threats readable without colour; ambient never out-values threats.
6. Occlusion and flash limits as above.
7. Pool stress: two guns at 600 RPM + 4 explosions → zero runtime instantiation, no spikes.
8. Distance readability at 5, 20, 50, 100 m; LOD switch invisible.
