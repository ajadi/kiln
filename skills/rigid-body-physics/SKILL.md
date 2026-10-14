---
name: rigid-body-physics
description: Rigid-body physics for games — SI scale, masses and inertia from materials, solver stability (mass ratios, timestep, sub-stepping, CCD, speed caps), shape choice, ghost collisions, penetration and sleeping, damping and material combining, joints, motors and torque sizing, detachment, ragdolls and active ragdolls, settling, pre-fractured destruction with bonds and islands, debris lifecycle, kinematic heavy machines, projectile impulses, material table, review checklist and Godot/Jolt specifics. Use when setting up or reviewing anything physical.
user-invocable: false
---

# Rigid-body physics

Values from engine sources are Godot/Jolt (4.6/4.7); the physics is the same in any engine —
see the engine skill for Unity (PhysX) and Unreal (Chaos) parameter names.

## Scale, mass, inertia

1. SI units, 1 unit = 1 m. Solvers are tuned for moving objects of 0.1–10 m, speeds 0–500 m/s,
   gravity ≈ 10 m/s². A 12 m mech is fine; a 2 cm bullet is not a physics body.
2. Set every body's mass (Godot defaults to 1 kg): effective density × volume. Hollow or armoured
   parts use an effective density (a ~60 t tank in ~70 m³ ≈ 850 kg/m³; solid steel would be 9×
   too heavy). Custom centre of mass for top-heavy parts or parts with a dense core.
3. Wrong inertia is visible: too low spins like cardboard, too high turns sluggishly. Raising
   small links' inertia 2–4× is an accepted stabiliser.
4. Keep gravity 9.81 and gravity scale 1 for anything meant to look big — slow falls read as
   heavy; stronger gravity makes things look like miniatures.

## Solver stability

5. Mass ratio: jointed or stacked neighbours ≤ 10:1, ideally ≤ 5:1 (iterations for 95%
   convergence ≈ 3 × ratio + 2). A 50 t mech against 200 kg debris is 250:1 — make the mech
   kinematic in contact.
6. Fixed 60 Hz step; physics interpolation on (one tick of latency; reset after teleports); cap
   steps per frame (spiral of death).
7. Sub-stepping beats more iterations. Fix order: mass ratios → raise tick rate (e.g. 120) →
   raise velocity steps (default 10, ≥ 2 for friction) and position steps (default 2).
8. CCD only for fast, small bodies against static geometry (grenades, blown-off limbs, small
   fast debris); it engages above ~75% of the inner radius per step and long thin fast-spinning
   objects can still tunnel. Otherwise walls thicker than speed × dt.
9. Speed caps (Jolt in Godot): linear 500 m/s, angular 47.1 rad/s — rifle rounds (850–940 m/s)
   are hitscan or ray-stepped, never rigid bodies.
10. Shapes: primitives → convex hulls (≤ 32 points; Jolt max 256) → compounds of convex.
    Triangle meshes only on static/kinematic bodies. Prefer capsules over cylinders (least
    stable). Convex radius rounds corners without growing the shape.
11. Ghost collisions on internal edges: merge adjacent static boxes into one body (edge removal
    works within a shape); avoid T-junctions.
12. Penetration: slop ~2 cm, speculative distance ~2 cm, Baumgarte 0.2 — overlaps resolve slowly
    without overshoot. Spawn pieces with 1–2 cm gaps.
13. Sleeping: an island sleeps when every point stays under 0.03 m/s for 0.5 s (global setting in
    Jolt); one jittering body keeps its whole island awake.
14. Damping is a proportional slowdown, not air drag (defaults 0.1 added to per-body values). For
    debris add angular damping 0.5–2 after first impact instead of heavy mid-air linear damping
    (looks floaty).
15. Material combining (Godot/Jolt): friction = min(a, b) unless "rough"; bounce = clamp(a + b,
    0, 1) — set bounce on one side only; no bounce below 1 m/s.

## Joints, motors, detachment

16. Ragdolls: cone joints for shoulder, hip, neck (swing 20–90°, twist 20–45°), limited hinges for
    elbows and knees; never pin joints. Mechs: hinges for knees/ankles, 6DOF or cone for hips.
17. Spring/motor frequency ≤ 0.5 × tick rate (~20 Hz stiff, ~2 Hz soft at 60 Hz), damping 1 =
    critical.
18. Size motors: τ = I·α + m·g·(L/2). Example: a 2 t, 3 m leg needs ~12 kN·m to accelerate plus
    ~29 kN·m against gravity → Godot hinge `motor/max_impulse` ≈ 700 at 60 Hz (impulse × tick
    rate = torque; the default 1.0 is only 60 N·m). Servos: 6DOF angular springs with the
    equilibrium moved each tick.
19. Detachment is game logic (part HP + mount HP), not joint break force (Godot exposes neither
    break thresholds nor reaction impulses). On detach spawn a body at the same transform with
    v = v_parent + ω × r, ω = ω_parent, plus a small separating impulse; recompute the parent's
    mass and COM.
20. Ragdoll mass split (Dempster): trunk 49.7%, thigh 10%, head 8.1%, shank 4.65%, upper arm 2.8%,
    forearm 1.6%, foot 1.45%, hand 0.6% — merge hands into forearms, drop fingers, raise arm
    inertia; start from the current animated pose and velocities; partial ragdolls with
    `influence`.
21. Active ragdolls: PD control τ = kp(θ* − θ) − kd·ω, or soft keying (velocities toward the
    animated pose), or 6DOF springs driven to the pose.
22. Settling after death: motors off, angular damping 1–3 once grounded, friction ≥ 0.6, no
    starting overlaps; after N seconds asleep freeze or bake to static.

## Destruction, machines, projectiles

23. Pre-fractured chunks: mass = ρ × volume (0.5×0.5×0.2 m concrete ≈ 120 kg); smaller than
    0.1–0.2 m → particles. Bonds with health between adjacent chunks, anchors bonded to the
    world; broken bonds → island detection → unanchored islands become one rigid body with a
    compound shape (not many bodies held by joints). A support-count/overhang rule is usually
    enough; full stress solvers (NVIDIA Blast) check tension/compression/shear.
24. Debris: own collision layer (static world only), batch adds, sleep → freeze → fade/pool after
    5–15 s, a hard cap. Budget a few hundred awake bodies and measure (native Jolt: 3680-body
    ragdoll pile ≈ 6 ms/step on 4 threads).
25. Mechs move kinematically (character body or frozen-kinematic rigid body driven by animation
    and IK). Hit reactions are additive animation, not impulses: a 12.7 mm round (≈ 37 N·s)
    moves a 50 t mech 0.0007 m/s. Kinematic bodies push debris with infinite mass — debris under
    a foot jitters: cull it or use a separate layer. On death: unfreeze, set linear/angular
    velocity from the last two transforms, weak 1–2 Hz springs so it sags and settles.
26. Projectiles: ray-step p → p + v·dt each tick, v += g·dt (drop ½gt²: 900 m/s over 300 m ≈
    0.55 m). Impulse J = m·Δv (m·v embedded, up to 2m·v ricochet) at the hit point. A 5.56 mm round
    moves an 80 kg ragdoll ~0.05 m/s — use a gameplay multiplier but clamp Δv (debris ≤ 3 m/s,
    limbs ≤ 1.5 m/s). Splash damage: linear falloff D·(1 − d/R) with an occlusion ray (working).

## Material table

| Material | Density kg/m³ | Friction (pair) | Bounce (game) |
|---|---|---|---|
| Steel | 7820–7850 | 0.5–0.8 static / 0.42 kinetic (steel–steel) | 0.05–0.15 |
| Aluminium | 2700 | 0.61 / 0.47 (Al–steel) | 0.1 |
| Concrete | 2000–2400 | 0.6–0.85 (rubber–concrete) | 0–0.05 |
| Brick | 1400–2400 | 0.6 | 0.05 |
| Glass | 2400–2800 | 0.9–1.0 / 0.4 (glass–glass) | 0.1–0.2 |
| Stone | 2300–2800 | — | 0.05 |
| Oak / plywood | 720 / 540 | 0.62 / 0.48 (wood–wood) | 0.1–0.2 |
| Rubber | 910–930 | 0.9 / 0.5–0.8 (rubber–asphalt) | 0.5–0.8 |
| Plasterboard | 800 | — | 0 |
| Soil | 2050 | — | 0 |
| Ice | 917 | 0.03 (steel–ice) | 0.05 |
| Mech hull (effective) | ~500–1500 | as steel | 0–0.05 |

## Review checklist

- [ ] Physics engine explicitly set in the project (Godot: `3d/physics_engine="Jolt Physics"`).
- [ ] Every body's mass set and plausible; custom COM where needed.
- [ ] Neighbour mass ratios ≤ 10:1; tiny bones merged.
- [ ] No triangle meshes on dynamic bodies, no cylinders, convex hulls ≤ 32–64 points, sizes 0.1–10 m.
- [ ] 60 Hz fixed step, interpolation on, reset after teleports.
- [ ] CCD only where needed; bullets hitscan or ray-stepped.
- [ ] Joint limits on, no pin joints in ragdolls, no unsupported soft-limit properties, motor torque sized.
- [ ] Bounce on one side only; friction ≥ 0.5 on things that must settle.
- [ ] Spawned/detached bodies start without overlap and inherit v and ω.
- [ ] Debris layer, cap, sleep → freeze → pool.
- [ ] After 10 s on flat ground everything is asleep (5-body pile and ragdoll drop tests).
- [ ] Local destruction: hull hits do not detach limbs; the dead machine is dynamic and settles.
- Verification: visible collision shapes and contacts; log total energy ½mv² + ½ωᵀIω + mgh — it
  must not rise without input; per-tick transform logs for replays.

## Godot 4.6/4.7 + Jolt specifics

- Jolt is the default for new 3D projects since 4.6 (built in since 4.4); existing projects keep
  their setting.
- Unsupported (warnings): pin bias/damping/impulse clamp; hinge bias/softness/relaxation; slider
  angular and limit softness/restitution/damping; cone-twist bias/relaxation/softness; 6DOF limit
  softness/restitution/damping/ERP. 6DOF springs and motors work; hinge motors are velocity-only.
- Contact impulses are estimates; frozen-kinematic bodies report contacts with static/kinematic
  bodies only with `generate_all_kinematic_contacts`; ray `face_index` -1 unless enabled.
- The Physics 3D active-object / pair / island monitors read 0 under Jolt — count awake bodies
  yourself.
- Locking all axes is unsupported (freeze instead); separate-thread physics is experimental;
  cross-platform determinism needs a special Jolt build flag.

### Character controllers and crowds (measured in g2, Godot 4.7.2 + Jolt)

- Kinematic bodies never collide with each other: two CharacterBody3Ds only stop each other by
  their own `move_and_slide`. An NPC as **AnimatableBody3D** pushes a CharacterBody3D player at
  its own speed and carries it through 5 cm and 30 cm walls (the player is depenetrated, not
  blocked); an NPC as **CharacterBody3D** does not. Crowds that touch the player:
  CharacterBody3D, or avoidance that keeps them apart (g2 row 83).
- Depenetration shoves: a body that starts a tick overlapping is pushed out along the shortest
  axis, which reads as a hop or a sideways shove. `PhysicsDirectSpaceState3D.cast_motion` ignores
  shapes it already overlaps at the start, so a sweep from inside a collider reports "free".
- The floor test uses `floor_max_angle` against the contact normal with a small tolerance
  (`FLOOR_ANGLE_THRESHOLD` 0.01 rad = 0.573°): a ramp at exactly the limit flickers between floor
  and wall.
- Step-up (a custom teleport over kerbs): limit the lift to the step height and compare it with
  the jump apex and with any prone collision proxy — a dead body's box taller than the step
  height becomes a wall, lower than it a stair. Predict these three heights together. Measured:
  Jolt lets the capsule ride a 0.25 m kerb edge for several ticks before the step-up fires, so
  the visible one-frame rise was 8.4 cm, not the 18–25 cm a calculation predicted (row 63).
- Jolt "job system exceeded the maximum number of jobs" (2048 job slots, reclaimed per tick):
  the worker pool is starved on many-core machines under load (upstream godot#110724). Set
  `threading/worker_pool/max_threads = 8`.
- Camera arm collision: put big masses on the camera layer and leave thin props (posts, railings)
  off it, by an **opt-out** layer (`no_camera`) rather than by moving everything else: the safe
  behaviour stays the default for new geometry. A mask change that excludes layer 1 makes every
  `StaticBody3D.new()` in the acceptors' probe worlds invisible to the camera, and the camera rows
  pass trivially (row 70).
