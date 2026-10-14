---
name: flight
description: Flying in games — jetpacks and jump kits, wingsuits, paragliders and hang gliders, fixed-wing aircraft, helicopters, drones and flying creatures — with the weight of fuel, pilot and gadgets (thrust-to-weight full and empty, hover endurance as fuel burns off, the most gear it can lift), thrust line through the centre of mass, hover and lean, stall and turns, glide ratios and lift, rotor momentum theory, arcade vs sim models and assists, fuel/heat meters, camera, measured real devices and games, exact test cases checked by flight_check.py, and Godot/Unity/Unreal setup. Use when designing, building or reviewing anything that flies or glides.
user-invocable: false
---

# Flight

Every flyer is a weight budget against a force: thrust, lift or a rotor's push. Write the budget
first — device, pilot, gadgets, fuel — and check it full and empty with
`${CLAUDE_SKILL_DIR}/scripts/flight_check.py` (stdlib Python, Bash). Lift and drag basics are in
fields-forces; vehicles covers wheels; traversal covers bodies and load. Values marked (working)
are starting points.

## 1. Weight: fuel, pilot, gadgets

1. **Budget everything that flies**: dry device + pilot + gadgets (weapons, tools, armour, packs)
   + fuel. Thrust-to-weight T/W ≥ 1 to hover; it **rises as fuel burns** — a Bell Rocket Belt
   (1334 N, 30.6 kg dry, 26.4 kg peroxide) with an 80 kg pilot starts at T/W 0.99 and cannot lift
   off until ~1 kg has burned; empty it is 1.23. `predict loadout` gives T/W full/empty, whether
   it takes off, and the most gadget mass it can carry.
2. **Hover endurance with burning fuel**: holding a hover, fuel flow is proportional to thrust,
   so t = c/g · ln(m₀/m₁), c = Isp·g₀ for rockets (H₂O₂ ~140 s), 1/TSFC for turbines. Real devices:
   Rocket Belt ~21 s, jet suits and jetpacks 8–10 min (Gravity suit 4 L/min from 40 L).
3. **Gameplay mirrors it**: pickups and gadgets add mass → less climb, shorter flight; the HUD shows
   the budget (Anthem's heat meter, Apex's fuel bar refilling on the ground). Decide whether mass
   matters (sim) or is abstracted into a meter (arcade) — and say so in the design.
4. **Thrust line through the centre of mass**: 1079 N 10 cm off-centre is a 108 N·m tumbling
   torque — mount the pack high on the back, nozzles angled toward the CoM; the CoM moves as fuel
   and gadgets change (traversal: carried load).

## 2. Jetpacks and jump kits

- Lean to move while holding altitude needs T/W ≥ 1/cos θ (1.155 at 30°, 1.414 at 45°); with T/W
  1.3 the steepest level lean is 39.7°, giving g·tan θ sideways acceleration (`predict hover`).
- Real devices: Bell Rocket Belt 21 s, 18 m ceiling, steam exhaust ~740 °C; Gravity Daedalus 5
  turbines, 27 kg, up to 10 min, 137 km/h record; JetPack Aviation JB-10 ~8–10 min.
- Game patterns: a separate fuel or heat meter (Anthem overheats, cools on dives and water);
  horizontal flight costs the same as climbing (Apex); no firing or reduced accuracy while
  thrusting; refill on landing; a soft ceiling as a downdraft rather than a wall (Anthem);
  double-jump to ignite, use to slow falls (Fortnite); short bursts drain faster (Halo Reach).
  Players who can stay airborne will fight airborne — design enemies for it (Anthem).

## 3. Gliding

| Glider | Glide ratio | Speed | Sink |
|---|---|---|---|
| Wingsuit | ~2.5–3 | ~160 km/h (85–140 mph measured) | 15–18 m/s |
| Paraglider | 9 recreational, 11 competition | 22–55 km/h, trim 32–40 | ~1.1 m/s |
| Hang glider | ~17 flex, ~20 rigid | 30–145 km/h, best glide 45–60 | — |
| Sailplane | 44–70 | — | — |

- Distance = ratio × height; time = height / sink (`predict glide`, `glide` check). From 3000 m a
  wingsuit flies ~7.5 km in ~170 s.
- Lift: thermals climb "several m/s" (hang gliders average 2.5–4 m/s); ridge lift up to about
  twice the ridge height; a big fire's updraft (BotW) — an updraft volume only needs a vertical
  speed above the glider's sink.
- BotW paraglider: drains stamina and stows at zero, one emergency 1 s opening, fire updrafts.

## 4. Fixed-wing aircraft

- Lift L = ½ρv²S·C_L; C_L ≈ 2πα; stall ~15° (8–20°), C_Lmax 1.0–1.6 (flaps higher); stall speed
  V_s = √(2W/(ρ S C_Lmax)) (`predict stall`); in a turn stall rises by √n (1.19 at 45°, 1.41 at 60°).
- Turn radius r = v²/(g tan φ), standard rate 3°/s (`predict turn`, `turn` check). Wing loading:
  birds 1–25 kg/m², light aircraft ~70, airliners ~680. Cessna 172: 1111 kg, 16.2 m², stall 47 kn,
  cruise 122 kn, climb 3.7 m/s.
- Arcade vs sim: Ace Combat "standard" turns the plane directly; "expert" rolls and pulls; War
  Thunder arcade adds a lead marker and forgiving dives; MSFS sums forces over many surface
  elements. Assists: auto-level, stall protection (design choice), coordinated turns.

## 5. Helicopters and drones

- Momentum theory: induced velocity v = √(T/(2ρA)), ideal hover power √(T³/(2ρA)), real power /FM
  (0.75–0.8); a 2000 kg helicopter with an 11 m rotor needs ~180 kW ideal, ~240 kW real, +16% at
  3000 m (`predict rotor`). Disk loading: R22 14 kg/m², Chinook 43, Mi-26 71.
- Controls: cyclic (direction), collective (all blades), pedals (tail rotor); translational lift
  above ~16–24 kt; autorotation glides ~17–20° with the flare at 50–100 ft. Arcade (Battlefield):
  W/S collective, A/D yaw, mouse pitch and roll; hover assists auto-level.
- Drones: four rotors, yaw by unbalancing torque; T/W ≥ 2, hovering at ~40–50% throttle; tilt θ
  gives g·tan θ (needs T/W 1/cos θ); cascaded control position → velocity → attitude → rate (PX4).

## 6. Flying creatures

Wingbeat frequency falls with size (hummingbirds 43–80 Hz); flight cost grows with size, so the
biggest flyers soar. Square-cube: scale a flyer 10× → 1000× mass, 10× wing loading, 3.2× minimum
speed, 0.3× wingbeat — a dragon needs huge wings, fast flight or a stated lie. Quetzalcoatlus:
10–11 m span, ~200–250 kg, likely quad-launched (creature-locomotion skill).

## 7. Feel and camera

- Fixed physics step high enough for the speed (120 Hz for fast craft; raise
  `max_physics_steps_per_frame` with it); physics interpolation on.
- Camera: spring arm behind, FOV widening with speed (working), horizon kept readable; banking cues.
- Big airspace: float precision and floating origin (fields-forces "Large worlds").

## 8. Lab gyms

| Check | Gym | Command | PASS |
|---|---|---|---|
| Loadout | full / empty tank, with and without gadgets | `predict loadout` vs in-game climb | takes off when T/W ≥ 1 only; climb accel within 10% |
| Hover | hold position 10 s | `hover --pos [--when]` | altitude within ±0.25 m |
| Glide | glide from a known height | `glide --ratio` | ratio within 15% |
| Turn | steady bank at constant speed | `turn --bank` | radius within 15% of v²/(g tan φ) |
| Fuel | hover until empty | timer vs `predict loadout --isp/--tsfc` | endurance within 15% (working) |

## 9. Review checklist

- [ ] Weight budget in data: device, pilot, gadgets, fuel; T/W full and empty; max gadget mass.
- [ ] Fuel burn changes mass (sim) or is a stated meter (arcade); the HUD shows it.
- [ ] Thrust line through the CoM; CoM shift with fuel and gear handled.
- [ ] Glide ratios, stall and turn numbers from the tables; assists stated.
- [ ] Tick rate, interpolation and floating origin fit the speeds and distances.
- [ ] Lab gyms pass.

## 10. Engine notes

**Godot 4.6/4.7** — RigidBody3D `_integrate_forces` (runs before integration; `custom_integrator`
drops gravity and damping), `apply_central_force` every tick (impulses each frame are frame-rate
dependent), `apply_torque` needs inertia; `continuous_cd` for fast craft. Area3D overrides gravity
and damping only — updrafts are an Area3D plus your own force per body (its wind affects soft
bodies only). CharacterBody3D `MOTION_MODE_FLOATING` for arcade flight. SpringArm3D camera.
`physics_ticks_per_second` (60) and `max_physics_steps_per_frame` (8) together; Jolt is the
default; single precision is fine to ~8 km (third person) or ~65 km, beyond needs `precision=double`.

**Unity 6** — `Rigidbody.AddForce` with ForceMode (Force, Acceleration, Impulse, VelocityChange);
WindZone affects trees and particles only.

**Unreal 5.6–5.8** — `AddForce` (`bAccelChange` ignores mass), `AddTorqueInRadians`; MOVE_Flying
ignores gravity and uses the volume's fluid friction; physics sub-stepping (max substep delta);
Large World Coordinates (~88 million km).
