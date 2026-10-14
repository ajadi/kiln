---
name: fields-forces
description: Force fields in games — gravity variants (uniform, zones with priority, small planets you walk around, inverse-square), orbits and space (integrator choice and energy drift, patched conics and on-rails orbits, time warp), drag, wind and lift (terminal speed, ballistics with drag, wind volumes that move rigid bodies, gliders and updrafts, vegetation wind), magnetism as game rules, beams with reflection and refraction, and large worlds (float32 precision, floating origin, double-precision builds). Numbers, exact test cases checked by field_check.py, pitfalls, and Godot/Unity/Unreal setup. Use when designing, building or reviewing gravity, orbits, wind, projectiles with drag, magnets, light/laser puzzles or worlds larger than a few kilometres.
user-invocable: false
---

# Fields and forces

A field gives every body in a region a force (or acceleration) from a rule. Most game bugs here
are not physics but bookkeeping: the wrong integrator, overlapping zones, unclamped falloff,
float precision far from the origin. Prove every field in a gym against an exact answer with
`${extensionPath}${/}skills${/}fields-forces/scripts/field_check.py` (stdlib Python, Bash). Values marked (working) are
starting points.

## 1. Gravity

1. Constants: g₀ = 9.80665 m/s² (Godot's project default is 9.8 — state which one the game
   uses); G = 6.67430e-11; μ = G·M (Earth 3.986e14 m³/s²).
2. **Zones with priority** (Super Mario Galaxy): gravity objects shaped as plane, sphere, box,
   cylinder, cone, torus, each with range, priority and falloff; the highest priority wins and
   equal priorities combine. Sum several sources only where you want blends; hard priority where
   you want clean switches.
3. **Falloff**: linear falloff between an inner and outer radius is easier to design with than
   inverse-square (Catlike Coding); Outer Wilds uses linear for most planets and inverse-square
   for the sun. Inverse-square g·d²/r² explodes inside the unit distance — **clamp it** (×4 at half
   the radius; Godot's own formula is unclamped).
4. **Small planets you walk on**: the character's up = −normalize(gravity), re-aligned every
   tick; floor angle and snap follow that up. Speed caps matter: with g 9.8 and R 100 m a
   31 m/s dash orbits and 44 m/s escapes (`predict orbit`).

## 2. Orbits and space

1. **Integrator**: semi-implicit (symplectic) Euler — velocity first, then position — is what
   game engines use (Godot does) and keeps energy bounded. Hand-written `x += v·dt; v += a·dt` is
   explicit Euler and gains energy every step: +3.3% per orbit at 60 Hz, +27% radius in 10 orbits.
   Velocity Verlet is better still; RK4 is accurate but slowly loses energy (orbits decay inward).
2. Drift on a 150 m orbit around a 100 m planet, max |ΔE/E| (research computation):

   | steps/orbit | explicit Euler | semi-implicit Euler | velocity Verlet | RK4 |
   |---|---|---|---|---|
   | 2212 (60 Hz) | 3.3% → 56% after 100 orbits | 8e-6 bounded | 2e-11 | 4e-14 per orbit, growing |
   | 221 (10× warp) | — | 8e-4 bounded, −20° phase after 100 | 2e-7 | 3e-7 after 100 |
   | 22 (100× warp) | escapes | 8% | 0.15% | 4% after 100 |

   Acceptance at 60 Hz: |ΔE/E| < 1e-4 and radius within 0.01% (`orbit --drift 1e-4`).
3. Space needs zero damping: Godot's default linear damp 0.1 leaves 0.905 of the speed per second
   (REPLACE damping with 0 in space areas).
4. **Many bodies**: patched conics (one sphere of influence at a time, r_SOI ≈ a·(m/M)^(2/5)) are
   predictable and cheap (KSP); full n-body only if the design needs Lagrange points or chaos.
5. **Time warp**: physics warp only to ~4× (raise ticks and `max_physics_steps_per_frame`); beyond,
   switch to on-rails Kepler propagation with no forces (KSP up to 100 000×).
6. Formulas: circular v = √(μ/r), period 2π√(r³/μ), escape √(2μ/r), vis-viva v² = μ(2/r − 1/a),
   Kepler T² ∝ a³ (`predict orbit|kepler`).

## 3. Drag, wind and lift

The global wind vector and gusts come from the weather skill's controller; this section turns
wind into forces.

1. Drag F = ½·ρ·v²·Cd·A, ρ = 1.225 kg/m³ at sea level. Cd: rough sphere 0.47, flat plate 1.28,
   upright human 1.0–1.3, bullet ~0.3, arrow ~1.5 (shaft cross-section).
2. Terminal speed v_t = √(2mg/(ρ·Cd·A)); v(t) = v_t·tanh(g·t/v_t). Belly-down skydiver ≈ 55 m/s
   (50/90/99% at 3/8/15 s), raindrop 2–9 m/s, A4 sheet ~1 m/s (`predict terminal`, `terminal`).
3. Ballistics with drag cut range hard: a 0.145 kg ball at 40 m/s and 45° flies 85 m instead of
   163 m, best angle ~40°, a 5 m/s crosswind drifts it 8.6 m (`predict projectile`).
4. **Wind on rigid bodies is yours to write**: drag against the velocity relative to the wind.
   Godot Area3D wind affects only SoftBody3D; Unreal's WindDirectionalSource only SpeedTree;
   Unity's WindZone only trees and particles. Just Cause 4: per-triangle drag precomputed into a
   small cubemap (~7 kB per object), wind volumes as cylinders (tornado = stacked cylinders on a
   spline), ~1 ms of an 8.5 ms physics budget, and the rule "wind is either moderate and purely
   cosmetic over large areas, or strong and physical in small volumes".
5. Lift L = ½ρv²·S·C_L, thin airfoil C_L ≈ 2πα, stall ~10–15°. A paraglider trims at 32–40 km/h
   with glide ratio ~9 (sink ~1.1 m/s); an updraft volume over a big fire (BotW) just needs a
   vertical speed above the sink rate.
6. Flying craft and gliders (glide ratios, stall, rotors, jetpacks, fuel weight): flight skill.
7. Vegetation wind is a vertex shader (vertex-colour-weighted sine of time in world space), not
   physics — keep it out of the physics budget.

## 4. Magnetism and other game fields

- Real dipoles: field ∝ 1/r³, force between dipoles ∝ 1/r⁴ (½ the distance → 16× the force) —
  unreadable for players. Games use rules: polarity attract/repel with linear or capped falloff
  (Teslagrad). Tune by feel in a gym, then lock the curve in data.
- Any field = shape + falloff curve + priority + affected layers. Keep fields in data and visible
  in the editor (gizmos) — scene-first.

## 5. Beams, reflection, refraction

- Reflection r = d − 2(d·n)n. Snell n₁·sin θ₁ = n₂·sin θ₂; past the critical angle arcsin(n₂/n₁)
  (water 48.6°, glass 41.8°, diamond 24.5°) light reflects totally (`predict refract`).
- Puzzle beams may lie: Portal 2's redirection cube emits from a fixed lens and turns to face away
  from the player instead of reflecting by angle. Decide "physical" or "designed" and keep it
  consistent; the `beams` check verifies physical hits from an export.

## 6. Large worlds

- float32 step at a coordinate: 1 km 0.06 mm, 10 km ~1 mm, 100 km 7.8 mm, 1000 km 6.25 cm — at
  1000 km an object moving 1 m/s does not move at all (`predict ulp`). Jitter shows from a few km.
- Fixes: floating origin (shift the world so the player stays near 0 — continuous or on a
  threshold; KSP's Krakensbane also re-bases velocities); 64-bit positions (Star Citizen,
  Unreal 5 Large World Coordinates, Godot built with `precision=double` — no official double
  binaries, costs speed and memory, shaders emulate doubles). Rendering stays camera-relative.
- Shader time wraps (Godot TIME rolls over at 3600 s by default); an unwrapped float32 clock has
  7.8 ms resolution after a day — wind shaders stutter.
- `jitter` measures a recorded object's high-frequency position noise against `--max-mm`.

## 7. Lab gyms

| Check | Gym | Command | PASS |
|---|---|---|---|
| Gravity value | drop a ball from 20 m | `fall --g` | fitted g within 5% (a step integrator lands ±½·g·dt·t off in position, the fitted g is exact) |
| Terminal speed | long fall with drag | `terminal --vt` | plateau within 5% and flat |
| Orbit | body on a circular orbit, several turns | `orbit --mu --drift 1e-4` | period within 2%, energy drift ≤ 1e-4 |
| Projectile | launch at fixed speed/angle | `predict projectile`, measure landing | range within 5% (working) |
| Zones | walk through overlapping zones | log gravity vector per tick | no jumps where the design wants blends; priority wins where it wants switches |
| Far from origin | object gliding at 1 m/s at the world's farthest point | `jitter --max-mm 1` | jitter ≤ 1 mm |
| Beams | reflect/refract set-ups | `beams` | angle error ≤ 0.5° |

## 8. Review checklist

- [ ] g value stated (9.81 / 9.80665 / 9.8); every gravity area's override mode set (Godot's is
      DISABLED by default — a new Area3D does nothing).
- [ ] Inverse-square falloff clamped inside the unit distance; priorities deliberate.
- [ ] Characters on curved gravity re-align up every tick; speed caps vs orbit/escape speed.
- [ ] Integrator is semi-implicit or better; no hand-written explicit Euler; space damping 0.
- [ ] Time warp: physics ≤ ~4×, on-rails beyond.
- [ ] Wind applied to rigid bodies by the game's own drag code where it must move them.
- [ ] World extent vs float32 step; floating origin or doubles where the world is > a few km.
- [ ] Lab gyms pass.

## 9. Engine notes

**Godot 4.6/4.7** — Area3D: `gravity_space_override` (DISABLED by default; COMBINE,
COMBINE_REPLACE, REPLACE, REPLACE_COMBINE), `gravity_point`, `gravity_point_center` (area-local),
`gravity_point_unit_distance` (inverse-square, 0 = constant), `priority` (higher first); wind
properties affect SoftBody3D only. GodotPhysics returns zero gravity at r = 0, Jolt clamps r² to
an epsilon. `PhysicsBody3D.get_gravity()` includes all area overrides; RigidBody3D
`_integrate_forces` + `custom_integrator` for your own forces (the state exposes `total_gravity`,
`step`). CharacterBody3D: set `up_direction` = −gravity every tick; `MOTION_MODE_FLOATING` for
space. GPUParticlesAttractor3D (and the vector-field variant, ~64³ texture) move GPU particles only.
Double precision: SCons `precision=double` for editor and templates. Jolt is the default for new
3D projects since 4.6.

**Unity 6** — `Physics.gravity` global, `useGravity` per body, ConstantForce, custom gravity with
`AddForce` in FixedUpdate; `linearDamping` = v·(1 − d·dt). WindZone: trees and particles (External
Forces) only. No built-in floating origin or double physics (UNVERIFIED); HDRP camera-relative
rendering covers rendering only.

**Unreal 5.6–5.8** — Large World Coordinates (doubles, Chaos in doubles, Niagara cell + offset);
Physics Fields (transient/construction/persistent; linear force/velocity, radial and uniform
vectors) for rigid bodies, cloth and geometry collections; CharacterMovementComponent custom
gravity direction since 5.4; WindDirectionalSource affects SpeedTree only; Chaos Cloth has its
own wind (`SetWind`).
