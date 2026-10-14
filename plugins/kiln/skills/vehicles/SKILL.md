---
name: vehicles
description: Wheeled vehicles for games (cars, trucks, buggies; motorbikes, tracked vehicles, boats and hovercraft briefly) — arcade vs sim, raycast suspension, tyre models (slip ratio and angle, friction circle, Pacejka and brush), surface friction, suspension frequency and damping, weight transfer, drivetrain and gearing, steering geometry and understeer, braking and ABS, top speed and launch, assists that make cars feel good, tick rate, what Godot's VehicleBody3D really does (from its source), Unity WheelCollider and Chaos Vehicles, exact test cases checked by vehicle_check.py. Use when designing, building, tuning or reviewing anything the player drives or rides; driver and rider poses, getting in and out are in the traversal skill; aircraft, helicopters, drones and jetpacks are in the flight skill.
user-invocable: false
---

# Vehicles

Good-feeling vehicles are a solid simulation plus a layer of assists and camera work (Criterion,
GDC 2018) — never a pile of hacks without a model underneath, and never a raw sim without
assists. Tune numbers in data, prove them with `${CLAUDE_SKILL_DIR}/scripts/vehicle_check.py`
(stdlib Python, Bash). Driver/rider poses, mounting, entering and exiting: `traversal` skill.
Riding animals: `riding` skill.
Values marked (working) are starting points.

## 1. Arcade or sim — decide first

- **Arcade** (Rocket League): no transmission — an acceleration curve by speed; mass constant and
  ignored when applying forces; no longitudinal tyre friction; lateral friction from a curve of
  side-slip ratio SideSpeed/(SideSpeed + ForwardSpeed) × ground-normal factor; forces applied at
  centre-of-mass height; "stay upright" forces; fixed 120 Hz tick. Physics presets separate from
  visuals.
- **Simcade/sim**: raycast (or shapecast) suspension per wheel on one rigid body (Very Very Valet,
  Space Dust Racing), a tyre model with slip, a drivetrain with gears. Turn 10 (Forza) and Avalanche
  (Just Cause 4) both left Pacejka for their own fewer-parameter tyre models — tunability beats
  fidelity.
- Data for designers (GTA V handling.meta as a template): traction max/min in g, peak slip angle,
  drive bias front/rear, drive force, top flat speed, suspension force, anti-roll force, roll
  centre height ≤ CoM height. One designer tuned 90+ Saints Row vehicles in six months from such
  a table.

## 2. Tyres

1. Slip ratio σ = (r·Ω − v_x)/|v_x| (peak grip ~6–20% slip); slip angle α = atan(v_y/|v_x|)
   (peak a few degrees). Total force stays inside a friction circle (really an ellipse).
2. Pacejka F = F_z·D·sin(C·atan(B·κ − E·(B·κ − atan(B·κ)))): dry B 10, C 1.9, D 1, E 0.97 (peak
   μ 1.0 at κ 0.18, locked 0.92); wet 12/2.3/0.82/1; snow 5/2/0.3/1; ice 4/2/0.1/1.
   Brush (Fiala): F_y = −C_α·tan α + C_α²/(3F_max)·|tan α|·tan α − C_α³/(27F_max²)·tan³α up to
   α_slide = atan(3F_max/C_α), then −F_max·sign α.
3. Surface μ (peak/sliding): dry asphalt 0.8–0.9/0.75, wet 0.5–0.7/0.45–0.6, gravel 0.6, packed
   snow 0.2/0.15, ice 0.1/0.07. Rolling resistance 0.010–0.015 (cars). Hook surface μ to the
   elements-materials skill (wet, frozen).

## 3. Suspension and load

1. Ride frequency f = √(k/m)/(2π) per corner (m = sprung mass on that corner): passenger 0.5–1.5
   Hz, sedan racers 1.5–2.0, downforce cars 3–5+. Damping ratio ~0.25 passenger, 0.65–0.70 race.
   1500 kg car, 335 kg per corner, 30 kN/m → 1.51 Hz; ζ 0.25 needs 1585 N·s/m (`predict ride`,
   `ride`).
2. Weight transfer: longitudinal ΔW = m·a·h/L (0.8 g braking, h 0.55, L 2.7 → 16% of the weight:
   55/45 becomes 71/29); lateral ΔW = m·a_y·h/track (0.9 g, 1.55 m track → 32%); a rigid car
   rolls at t/(2h) g (1.41 g). Roll gradient 1.0–1.8°/g sedans (`predict transfer`).
3. Anti-roll bars move load transfer between axles — the main handling-balance knob after tyres.

## 4. Drivetrain, speed, braking

1. Torque at the wheels = engine torque × gear × final drive × efficiency / wheel radius.
   Monster's Corvette: gears 2.66/1.78/1.30/1.0/0.74/0.50, final 3.42, wheel 0.34 m, 475 N·m.
2. Top speed from power balance P·η = (½ρ·Cd·A·v² + C_rr·m·g)·v: 100 kW, Cd 0.3, A 2.2, C_rr
   0.012, 1500 kg → 218 km/h (205 at 85% efficiency); drag equals rolling resistance at ~75 km/h
   (`predict topspeed`).
3. Launch (traction-limited, μ 0.9, h 0.55, L 2.7): RWD 50/50 0.55 g → 0–100 in 5.1 s, FWD 60/40
   6.2 s, AWD 0.9 g 3.15 s — ignoring weight transfer is off by ~1 s (`predict launch` without
   transfer is a lower bound).
4. Stopping d = v²/(2μg) + v·t_reaction: from 100 km/h, μ 0.8 → 49.2 m (3.5 s), μ 0.5 → 78.7 m,
   ice 0.1 → 393 m; reaction 1–1.5 s adds 28–42 m. ABS keeps slip near the peak (~10–20%)
   (`predict stop`, `stop`).
5. Cornering limit v = √(μ·g·r): μ 0.9 on a 50 m skidpad → 75.6 km/h, 0.9 g (`predict corner`,
   `corner`).

## 5. Steering and balance

- Ackermann: cot δ_o − cot δ_i = track/wheelbase (L 2.7, track 1.55: inner 30° → outer 23.4°).
- Understeer gradient K (°/g): δ = L/R + K·a_y; K > 0 understeer (stable, what most players
  expect), K < 0 oversteer; characteristic speed √(57.3·L·g/K).
- Steering lock that drops with speed, steering speed limits, stiffer rear grip than front for
  stability.

## 6. Assists and feel

- Forces at CoM height, stay-upright/anti-flip torques, air control (Rocket League), downforce
  that grows with speed, anti-roll, steering lock vs speed, traction control by cutting power
  above the peak slip, ABS, drift assists (counter-steer help) and drift rewards (Mario Kart mini
  turbo: blue 0.62 s, orange 1.67 s, purple 2.63 s of boost).
- Camera, sound and effects carry as much of the feel as the physics (Criterion).

## 7. Tick rate and stability

- 120 Hz is the usual floor for vehicles (Rocket League; Godot vehicle addons want 120–240 Hz;
  Godot's docs: VehicleBody is unstable at high speed — raise ticks, use CCD and thicker
  colliders). Re-test every tuning at the shipped tick rate.
- Low-speed jitter comes from high tyre stiffness — ramp stiffness with speed; parked cars slide
  on slopes — sleep or freeze them below a speed; thin wheel rays sink into gaps — use shapecasts
  or several rays.

## 8. Other vehicles (brief)

- Motorbikes: lean tan φ = v²/(g·r) for a point mass; balance needs counter-steering or a balance
  assist; rider pose and weight shift in the traversal skill.
- Tracked: body and road wheels as rigid bodies, the track as a skinned mesh (physical links are
  unstable); skid steering by different torque per side.
- Boats: buoyancy from submerged hull triangles or sample points plus viscous, pressure, slamming
  and air drag (fluids-granular skill). Hovercraft: a damped spring near the ground, free upward.

## 9. Lab gyms

| Check | Gym | Command | PASS |
|---|---|---|---|
| Braking | straight at 100 km/h, full brake on a known surface | `stop --expected-m` | within 10% of v²/(2μg) |
| Cornering | steady circle of known radius at the limit | `corner --expected-g` | lateral g within 10% of μ |
| Ride | drive over a bump, record body height | `ride --expected-hz --zeta` | frequency within 10%, ζ within ±0.1 |
| Launch | 0–100 km/h from rest | `launch --expected-s` | within 10% of the design time |
| Top speed | long straight | probe speed plateau | within 5% of `predict topspeed` (working) |
| Tick rate | the brake test at 60 and 120 Hz | `stop` twice | same distance (Godot's brake is a per-step impulse — see §10) |

## 10. Engine notes

**Godot 4.6/4.7 — VehicleBody3D/VehicleWheel3D** (a port of Bullet's raycast vehicle; the docs say
it "has known issues and isn't designed to provide realistic 3D vehicle physics"; no gears).
What the source does (read from `scene/3d/physics/vehicle_body_3d.cpp`, not run):
- Suspension force = (stiffness·Δx − damping·v)·**M of the whole body**, so `suspension_stiffness`
  is not N/mm: a four-wheel car rides at f = √s/π, ζ = d/√s, sag g/(4s). The default 5.88 gives
  0.77 Hz and 417 mm of sag and cannot hold the car up at the default travel; s ≥ ~16.4 at rest
  length 0.15 m, 50 → 2.25 Hz.
- The ray reaches only rest length + radius: rest length is the maximum droop.
- `friction_slip` acts as μ (max impulse = suspension force × dt × slip); surface friction is not
  combined despite the docs.
- Brake is a per-step impulse cap: brake 30 is 1800 N per wheel at 60 Hz but 3600 N at 120 Hz —
  re-tune when changing ticks; brake is ignored while `engine_force` ≠ 0.
- Tyre side impulses do not push the ground body (TODO in source).
- `wheel_roll_influence` 1.0 reduces roll (fixed in 4.3). Open issues: wheels sink into narrow gaps
  and parked cars slide on slopes (#98079, Jolt too).
- Addons (MIT, unverified on 4.7): Godot Easy Vehicle Physics (raycast, ABS/TCS/ESC, diffs, Jolt
  ok, ≥ 120 Hz), Dechode Godot-Advanced-Vehicle (Pacejka or brush, diffs, 240 Hz), VitaVehicle.
  For a game that needs believable handling, a raycast/shapecast vehicle in script with a tyre
  curve from data beats tuning VehicleBody3D.

**Unity 6 — WheelCollider**: built-in suspension and a slip-based two-spline friction curve
(extremum, asymptote), ignores Physics Materials; defaults spring 35 000 N/m, damper 4500, suspension
distance 0.3 (375 kg per wheel → 1.54 Hz, ζ 0.62); `ConfigureVehicleSubsteps` per vehicle.
Practitioners set extremum value 1 and tune stiffness, ramp stiffness with speed, watch slip vs
extremum slip. NWH Vehicle Physics 2 uses its own wheel.

**Unreal 5.6–5.8 — Chaos Vehicles** (`ChaosVehiclesPlugin`, `WheeledVehiclePawn`): torque curve ×
max torque, max/idle RPM, engine braking; differential front/rear split; per-wheel friction
multiplier, cornering stiffness, slip/skid thresholds, ABS/TCS, brake torque, spring rate (N/m),
preload, damping ratio, rollbar scaling, sweep shape. Chaos Modular Vehicle and physics
substepping are experimental.
