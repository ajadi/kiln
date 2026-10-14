---
name: elements-materials
description: Element and material systems for games — heat and cold, fire, water and wetness, electricity (wind as a carrier) and how they change materials (freeze, melt, boil, ignite, char, conduct, embrittle). The elements-vs-materials rule model, choosing the simulation level (per-object lump, surface grid, cellular automaton, fire entities), temperature with Newton cooling, time compression and diffusion stability, phase changes with latent heat and hysteresis, fire spread with fuel, wind, slope, wetness, burn-out, percolation and hard caps, wetness and drying, conduction graphs and lightning, effects on physics, visuals, audio and AI, readability rules, performance (measured GDScript grid cost) and determinism, lab gyms with exact answers checked by element_check.py, review checklist, Godot/Unity/Unreal notes. Use when designing, building, tuning or reviewing anything that burns, freezes, melts, gets wet, heats up or conducts.
user-invocable: false
---

# Elements and materials

The physics engine is a rule-based movement calculator; an element system is a rule-based
**state** calculator (Breath of the Wild's "chemistry engine"). Its numbers live in data, it runs
at its own tick over active cells only, and every rule is proven in a lab gym against an exact
answer with `${CLAUDE_SKILL_DIR}/scripts/element_check.py` (stdlib Python, Bash). Material
properties, game-scale values and worked test numbers: `${CLAUDE_SKILL_DIR}/references/materials.md`.
Values marked (working) are starting points, not sourced standards.

## 1. Rule model

1. **Elements** have no fixed state and act: fire, water, cold/ice, electricity, wind (carrier).
   **Materials** hold state: wood, grass, cloth, oil, metal, stone, glass, ice blocks, flesh.
2. Three rules (BotW): elements change materials (fire burns a tree); elements change each other
   (water puts out fire); materials never change each other directly — a burning tree lights its
   neighbour through the fire it emits. The table stays elements × (elements + materials), not
   materials².
3. Stimulus + properties, not object-to-object links: an emitter sends a stimulus (heat W, water,
   current, impulse) with a magnitude; each object reacts by its material's properties, so a new
   object needs a material assignment, no code (Harvey Smith, Deus Ex era).
4. The interaction table is data: one row per (element, target) → result, threshold, time, by-
   products. Start with 3–4 elements × 6–8 materials and add only what the player will see —
   "anything in the game model that doesn't copy into the player model is worthless" (Sylvester);
   Noita's slow processes went unnoticed. DOS2's surface/cloud table is a good template (fire +
   water → steam, fire + oil → ignites, cold + water → ice, shock + water → electrified).
5. Each material has an explicit state enum driven by continuous values at thresholds:
   temperature (or enthalpy), wetness 0–1, charge, fuel left. Example wood: dry → wet → drying →
   dry → burning → charred (non-flammable, brittle). Every state lists its effects (physics,
   visuals, audio, AI, damage) — see §8.
6. One model for everything that interacts: mixing physics-driven and non-physics objects
   "caused daily problems" on Tears of the Kingdom until everything was physics-driven.

## 2. Choose the simulation level (tech-design decides, before building)

| Level | What it is | Use | Cost | Shipped example |
|---|---|---|---|---|
| Per-object lump | one temperature / wetness / charge per object; exchange with neighbours by proximity | most 3D games: tens to hundreds of interactive objects | O(active objects) | Dwarf Fortress item temperature; BotW-style objects |
| Surface grid | 2-D cells 0.25–1 m on ground and surfaces (grass, oil, puddles, ice) | grass and brush fires, surface combos | O(active cells) | Far Cry 2 savanna fire, DOS2 surfaces |
| Sparse 3-D voxels | cells in volumes | smoke, gas, room heat in small volumes | heavy; keep small | — |
| Cellular automaton | every pixel a material, local swap/reaction rules | 2-D falling-sand games | chunked + multithreaded or GPU | Noita: 64×64 chunks, dirty rects, 4-pass checkerboard |
| Fire entities | fires as point entities with count queries | destruction sandboxes | O(fires) | Teardown `SpawnFire`, `GetFireCount` |

Choose the minimum representation that supports the stories the design wants (Sylvester). A
lump is valid only when the Biot number h·(V/A)/k < 0.1 — a 5 cm steel cube is (0.002), a 10 cm
oak log is not (1.5) — but games may still lump thick objects if the look is right; then don't
claim physical times.

## 3. Temperature, heat and cold

1. **Compress time with one factor.** Real thermal times are far too slow for play: diffusing
   across a 0.5 m cell takes wood ~590 h, steel ~6 h, copper ~0.6 h; a 2.5 cm ice cube freezes in
   ~2.5 h. Results depend only on Fo = α·t/L², so multiplying α (and h/ρc) by one factor K
   compresses every thermal time by K and keeps the real **ordering** (metal ≫ stone ≫ wood;
   water's huge heat capacity and latent heat; wet things resist ignition). Freezing that ice cube
   in ~10 s needs K ≈ 900; wood needs 10⁴–10⁵. Set τ per material in game seconds; take ratios,
   not absolute times, from physics.
2. **Per-object update** toward the local ambient each sim tick:
   `T += (T_env - T) * (1 - exp(-dt / tau))` — exact for any dt. The naive
   `T += (T_env - T) * dt / tau` overshoots and oscillates when dt > τ. τ = m·c/(h·A); h ≈ 2–25
   W/m²K still air, 25–250 moving air, 50–1000 still water. Hot objects also radiate
   (h_rad ≈ 33 W/m²K at 500 °C vs 5 at 50 °C), so a constant-h model cools glowing metal too
   slowly — shorten τ above ~300 °C if it matters.
3. **Heat sources are power.** Time to reach a threshold at net power P:
   t = m·(c·ΔT + L)/P (`predict melt|ignite`). Fire radiation falls with distance (point source
   q = χ·Q/(4πR²), χ ≈ 0.3 UNVERIFIED): for a 1 MW fire, 12.5 kW/m² (piloted wood ignition,
   handbook value) at ~1.4 m and 2.5 kW/m² (skin tolerable for long) at ~3.1 m.
4. **Grids.** Explicit diffusion `T += r·Laplacian`, r = α·dt/dx², is stable only for r ≤ ½ (1-D),
   ¼ (2-D), 1/6 (3-D) (`predict stable`); past it values explode within a few hundred steps.
   Compressing time raises r — sub-step or cap α. With zero-flux edges and flux-form updates the
   total Σ ρ·c·V·T is conserved to rounding (`conserve`). Diffusing hot spots grow their variance
   by 2·α·t per axis (`diffusion`).
5. **Player temperature as zones**, not a simulation (BotW): below 0 °C slow cold damage, below
   −10 °C faster; above 40 °C slow heat damage, above 50 °C faster; counters are gear, food, fire,
   water. Show the reading on the HUD.

## 4. Phase changes

1. Thresholds from the material row: ice melts at 0 °C, water boils at 100 °C, metals melt high
   (Al 660, Cu 1084, steel ~1425–1540 °C), soda-lime glass softens ~700 °C.
2. **Latent heat is a plateau**: at the threshold, added heat goes into the change before the
   temperature moves (ice: L_f 334 kJ/kg ≈ 160× the heat to warm the ice by 1 K; boiling water:
   L_v 2256 kJ/kg). Melting a 25 g cube from −18 °C needs 9.3 kJ, 90% of it latent. Implement with
   an enthalpy value or a progress accumulator at the threshold, never an instant flip.
3. **Hysteresis**: freeze at ≤ 0, thaw at ≥ +1 (working), so a body sitting at the threshold does
   not flicker between states.
4. A phase change changes physics: water → ice is walkable with friction ~0.03; a melting block
   shrinks — rebuild its collision in steps (every 10–25% of volume, working), not every tick.

## 5. Fire

1. Per cell or object: `flammable`, ignition threshold (temperature or accumulated heat), fuel
   (burn time), heat output, and a **charred** end state that is not flammable — finite fuel plus
   a dead end state is what ends fires. Real anchors: piloted wood ignition 250 °C glowing, ~300 °C
   flaming softwood, ~350 °C hardwood; paper autoignites ~220–250 °C; kerosene flashes at
   37–65 °C; wood char rate ~0.65 mm/min softwood.
2. **Spread**: each sim tick a burning cell heats or tries to ignite each fuel neighbour (p per
   tick). On a 1-D chain the front moves exactly p cells/tick; a 4-neighbour 2-D grid runs faster
   (0.18 / 0.51 / 0.70 cells/tick at p 0.1 / 0.3 / 0.5) because fire has many paths. If a cell
   burns B ticks, the chance it passes fire on is q = 1 − (1 − p)^B, and 2-D fires sit near the
   **bond percolation threshold 0.5**: at q 0.45 no run became a big fire, at 0.55 95% did. Tune
   q away from 0.5 on purpose (`predict front --burn`), or tiny changes flip "fizzles" to "map
   burns".
3. **Modifiers**: wind biases direction and speed (real wildfires: forest ≈ 10%, cured grass
   ≈ 20% of the 10 m wind speed — a 25 km/h wind gives ~0.7 and ~1.4 m/s); uphill faster than
   downhill; humidity and recent rain delay ignition until dry; water puts out only the
   submerged or wet part; burning characters carry fire (Far Cry 2). Rain, wind and temperature
   come from the weather skill's controller, which also drives surface wetness.
4. **Reference rates**: Minecraft fire updates every 30–40 game ticks (1.5–2 s), ages 0–15, has
   per-material ignite/burn odds (grass 60/100, leaves and wool 30/60, planks 5/20, logs 5/5),
   halves spread in humid biomes, is blocked by rain, and only updates near a player. Noita
   materials carry `fire_hp`, `autoignition_temperature`, `temperature_of_fire`.
5. **Runaway is the classic failure**: one Far Cry 2 shot spread fire "literally miles" in ~2 min
   and crippled performance. Ship hard caps: max burning cells/objects, spread only within N m of
   the player, finite fuel, capped particles (`spread --cap --max-burn`).
6. **By-products**: smoke (blocks vision; DOS2), steam from water, updrafts over big fires (BotW
   glide), heat to neighbours, light, charred/ash look. AI treats fire as a fear zone; burning
   creatures panic (Far Cry 2, Noita: on fire = 2% max HP/s, +15% speed).

## 6. Water, wetness, cold

1. Wetness is a value 0–1 with a state above a threshold; it dries over time, faster near heat.
   Rain wets only exposed surfaces (ray up; BotW sheltered fires survive rain).
2. Wet: blocks ignition until dried below the threshold (real wet wood spends heat boiling water
   off first; firewood burns well below 20% moisture), raises fire resistance (DOS2 +10%),
   conducts electricity, freezes under cold (DOS2: wet + chilled = frozen), makes climbing slip
   (BotW rain).
3. Cold makes things brittle — a design lever with a real anchor: body-centred metals such as
   steel turn brittle below a transition temperature (Liberty ships, Titanic hull steel), rubber
   loses springback well above its glass transition (Challenger O-rings at about −2 °C).
   Lower the break threshold of frozen or chilled objects (destruction-vfx skill).
4. Water + fire → steam cloud; fire on ice → water; cold on water → ice platform (DOS2, BotW).

## 7. Electricity and lightning

1. A conduction graph, not a field: nodes are objects or cells whose material conducts (metal,
   water, wet things), edges are contacts/overlaps; each sim tick flood-fill from the sources;
   powered = reachable conductors (`conduction`). Real classes: metals ~10⁻⁸ Ω·m, seawater
   ~50 mS/cm, tap water 200–800 µS/cm, ultrapure 0.055 µS/cm, dry wood 10¹⁴–10¹⁶ Ω·m (insulator),
   damp wood 10³–10⁴ (poor conductor).
2. Effects: damage or stun (DOS2: wet + shocked = stunned), electrified water surfaces, powered
   devices. Body anchors: 1 mA felt, 10–20 mA can't let go, 100–300 mA fibrillation.
3. Use Ohm (V = I·R) and Kirchhoff only when the design has circuit puzzles; otherwise a boolean
   graph.
4. Lightning picks the tallest, most isolated, pointed objects; metal conducts rather than
   "attracts". Games may lie (BotW: worn metal sparks, then draws the strike) — telegraph it.

## 8. Effects on the rest of the game

- **Physics**: swap friction for ice/wet (ice ~0.03 vs steel); a charred or frozen object gets
  lower break thresholds; updraft force volumes over big fires; mass loss as fuel burns (working).
- **Visuals**: per-instance shader parameters (wetness darkens and adds gloss, char, frost, heat
  glow by temperature), particles for fire/smoke/steam, scorch decals.
- **Audio**: a loop or one-shot per state (crackle, hiss, ice crack, electric buzz).
- **AI**: perception of fire/electrified zones, fear and panic states.
- **Damage**: element damage per tick per state, resistances per material and per gear.
- **Save**: states and the continuous values are world state — the save system stores them.

## 9. Readability (design rules)

1. Rules players can predict from the real world, the same everywhere; deliberate lies are fine
   if consistent ("of course paper should burn") — BotW, Harvey Smith.
2. Every state is visible and audible before it matters (sparking metal before a strike, a wet
   sheen, frost, heat shimmer); player temperature on the HUD.
3. Few elements done fully beat many done shallowly; cut what nobody notices.
4. "Will they understand what's going on?" (Noita) — a playtest question for every combination
   the level relies on. Fire walls that trap the player are fine when they read (Far Cry 2).
5. Emergent exploits cost testing time: sweep every element × material once in a gym (DOS2 tested
   combinations in an arena prototype) before levels depend on them.

## 10. Performance and determinism

1. Element tick 5–10 Hz (working; Minecraft fire 0.5–0.7 Hz), separate from the 60 Hz physics,
   fixed step with an accumulator, visuals interpolated.
2. Update only active cells/objects (dirty sets); a stable world costs nothing.
3. Measured here (Godot 4.7.2, typed GDScript, PackedFloat32Array, one thread, i5-10500T):
   explicit 5-point diffusion ≈ 130 ns/cell — 64² 0.53 ms, 128² 2.1 ms, 256² 8.7 ms per step;
   6.5k active cells of a 256² grid 1.3 ms. So: dense grids up to ~128² in GDScript at 5–10 Hz;
   larger ones sparse, split over WorkerThreadPool, or in C++/compute.
4. Caps on burning count, active cells and particles (§5).
5. Determinism: one seeded RNG per system; same binary + same inputs → same result; a regression
   test hashes the state after N ticks. Float results differ across compilers and platforms.

## 11. Lab gyms — exact answers

One gym scene per law (gym skill), a probe or grid export, and `element_check.py`:

| Check | Gym | Probe / export | Command | PASS |
|---|---|---|---|---|
| State thresholds | object heated/cooled slowly past each threshold | temperature, state | `threshold --at --tol [--above]` | changes at the threshold ± tol, never early, never missing |
| Cooling | hot object in neutral ambient | temperature | `cooling --tau` | fitted τ within 15% of the design τ |
| Heating time | heat source of known power on ice/wood | state change time | `predict melt\|ignite`, then measure | within 15% (working) |
| Grid diffusion | hot spot, zero-flux edges | snapshots | `diffusion --alpha`; `conserve` | α within 20%; drift ≤ 1% |
| Stability | design α, dx, dt | — | `predict stable` | stable at the shipped settings |
| Fire spread | uniform grass strip; then wind, slope, wet patch, stone wall | per-cell ignite/out times | `spread --speed --max-burn --cap` | speed within 30%; stone never lit; all out; cap held |
| Conduction | battery, metal rail, puddle, wooden crate, second rail | powered per node | `conduction` | powered = reachable conductors |
| Combinations | every element on every material once | resulting states | diff against the interaction table | all match |
| Determinism | same seed twice | state hash after N ticks | compare | equal |

Plus the player check: can a playtester predict what happens (§9.4).

## 12. Review checklist

- [ ] Interaction table and material rows in data with units and a source or "(working)".
- [ ] Simulation level chosen in tech-design with its cost; one model for everything that interacts.
- [ ] Time compression stated (one factor K) and real ordering kept.
- [ ] Exact per-object update or a stable grid (`predict stable`); totals conserved where closed.
- [ ] Phase changes with a plateau and hysteresis; collision rebuilt in steps.
- [ ] Fire: finite fuel, non-flammable end state, q tuned away from 0.5, caps, player radius.
- [ ] Wetness dries; rain respects shelter; wet blocks ignition and conducts.
- [ ] Every state visible and audible; HUD for player temperature.
- [ ] Element tick, active sets, measured cost on the target machine.
- [ ] Lab gyms pass (§11); combination sweep matches the table; a playtester predicts outcomes.

## 13. Engine notes

**Godot 4.6/4.7**
- Material table: a `Resource` class with `class_name` and `@export` fields (`data/materials/*.tres`);
  loaded resources are shared — per-object state lives on the node, not in the table.
- Proximity: Area3D overlap lists refresh once per physics step; `intersect_shape` with a small
  `max_results`; space queries only in `_physics_process`.
- Grids: `PackedFloat32Array` (passed by reference; properties return copies — assign back);
  `WorkerThreadPool.add_group_task` for rows (wait for every task; tiny tasks lose); writing
  existing elements from threads is fine, resizing is not; the scene tree only via `call_deferred`.
- Visuals from a grid: `Image` `FORMAT_RF` + `ImageTexture.update()` (same size/format); GPU grids
  with `Texture2DRD`. Compute shaders: local `RenderingDevice`, Forward+/Mobile only, `sync` 2–3
  frames after `submit`; `buffer_get_data` stalls, `buffer_get_data_async` (4.4+) lags frames.
- Per-object looks: `instance uniform` + `set_instance_shader_parameter` (≤ 16 per shader, no
  textures); `GPUParticles3D.amount_ratio` for intensity (changing `amount` restarts); decals are
  Forward+/Mobile only.
- Friction: changing a `PhysicsMaterial`'s friction at runtime reaches live StaticBody3D and
  RigidBody3D bodies under Jolt; `CharacterBody3D` has no physics material — ice and wet floors
  for the player belong in the controller.
- Scene-first: emitters, material assignments, gyms and caps are editor nodes and resources; the
  simulation script only reads them. No fire/temperature/element addon in the Asset Library
  (checked 2026-10); small GitHub samples only.

**Unity 6**: ScriptableObject tables (one shared copy, read-only in builds — runtime state
elsewhere); grids in `IJobParallelFor` + Burst over NativeArrays; GPU grids with compute shaders
and `AsyncGPUReadback` (a few frames late, no stall); `PhysicsMaterial` (renamed from
`PhysicMaterial`; `Collider.material` duplicates the shared one); VFX Graph needs compute (no GLES)
and is driven by `SendEvent`/`SetFloat`.

**Unreal 5.6–5.8**: element states as Gameplay Tags and GameplayEffects (duration, periodic ticks,
stacking, tag requirements and immunity); GPU grids in Niagara Grid2D/3D with simulation stages;
Niagara Data Channels batch many small effects (maturity UNVERIFIED); `SetPhysMaterialOverride`
swaps friction at runtime (mass and inertia unchanged); Mass Entity for many cells (maturity
UNVERIFIED); no built-in fire or temperature system.
