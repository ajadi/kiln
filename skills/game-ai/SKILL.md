---
name: game-ai
description: Enemy and NPC AI for action games in numbers — choosing FSM/HFSM, behaviour trees, utility scoring or GOAP/HTN by enemy complexity, perception (sight cones, hearing events, memory and forgetting), think rates and reaction times, navigation agents per size, avoidance, cover and flanking, squad roles and attack tokens, difficulty knobs, debug visualisation and probes for qa-ai (ai_probe.py), performance budgets, and Godot 4.6/4.7, Unity 6 and Unreal 5.8 setup through the engine MCP. Use when designing, building, tuning or reviewing enemy behaviour or navigation agents.
user-invocable: false
---

# Game AI

Enemy AI gives the player a readable, fair, beatable fight; it is not trying to win. Players
judge it by what they see and hear — telegraphs, barks, positioning, and how hard it is to kill
(Halo playtests rated tougher enemies as smarter). Values marked (working) are starting points;
[U] = not confirmed in a primary source. Detail: `${extensionPath}${/}skills${/}game-ai/references/techniques.md`
(architectures, perception model, cover/flank scoring, tokens, accuracy) and
`${extensionPath}${/}skills${/}game-ai/references/engines.md`. Reaction and vision numbers come from
`human-biomechanics`, telegraphs from feel-numbers, navigation meshes per agent size from
`level-design` §7.

## Choose the architecture

| Enemy | Default | Why |
|---|---|---|
| ≤ 5 behaviours, one mode (turret, swarm critter) | FSM: enum + match in one script | cheapest to read and test |
| Modes with sub-behaviours (patrol → investigate → combat{advance, cover, attack, reload} → search) | **HFSM — Kiln default**, states as child nodes visible in the scene tree | DOOM 2016 demons are HFSMs |
| Many prioritised reactions reused across enemy types, designer-authored | behaviour tree / StateTree | Halo 2 prioritised tree; Unreal's StateTree |
| Many options scored by context (target, ability, cover point) | utility scoring inside a state or tree leaf | IAUS: considerations 0–1 through curves, multiplied |
| Multi-step plans, interchangeable actions, changing world | GOAP or HTN, only after a tech-design decision | F.E.A.R.: 3-state FSM + A* planner; costly to debug |

Separate deciding (what) from executing (move, aim, animate). A squad/director layer issues
goals to individuals, not button presses.

## Perception

| Sense | Start (working) | Basis |
|---|---|---|
| Sight, focus | cone ±45–60°, range ≈ arena length (30–60 m); rays to head, chest, pelvis — any clear ray counts | acuity ±30° (human-biomechanics) |
| Sight, periphery | ±90–100° within 10–15 m, awareness gain ×0.3–0.5 | motion seen to ±100°; Splinter Cell Blacklist |
| Close sense | 1.5–3 m sphere, behind included | Blacklist (UNVERIFIED) |
| Awareness | meter 0→1: full in 0.5–2 s at mid range (stealth), 0.2–0.4 s when alerted; scaled by distance, angle, light, stance, motion; decays after LOS loss | Blacklist |
| Hearing | event radius: footsteps 5–10 m walk / 15–20 m run, gunshot 50–100 m [U]; −50% per wall or navmesh path distance; position error 1–3 m | hearing error grows to the side |
| Memory | last known position + velocity; predict ≤ 1–2 s; search 10–30 s, then return; forget unconfirmed stimuli after 5–15 s | Unreal Max Age; Isla |

Honest perception: no knowledge without a sense event, unless a director is scripted to say so.

## Decision timing

- Think 4–10 Hz (100–250 ms), staggered; steering and aim every physics tick; LOS checks 5–10 Hz.
- Reaction is an explicit timer, not a side effect of the think rate: no shot within 250 ms of
  first sighting (qa-ai); first accurate shot 0.4–0.7 s (human-biomechanics rule 10).
- Telegraphs ≥ 400–600 ms on screen (feel-numbers).
- No dithering: ≥ 0.5–1 s in a combat state, utility commitment bonus 10–25%, cooldowns.

## Movement

- One navigation map per agent size (radius, height, step, slope); agent radius ≥ collision
  radius; every spawn reaches every design area.
- Avoidance: 5–10 neighbours, 1–2 s horizon; small agents yield to big ones.
- Repath when the target moved > 1–2 m or every 0.5–1 s, never every tick.
- Cover: designer-placed cover markers first, sampled navmesh points second; keep points that
  block the threat's view at crouch (~0.9 m) and standing (~1.6 m) height, are reachable,
  inside the weapon's range band and unreserved (≥ 2–3 m apart); score path length, path
  exposure, angle and height (techniques.md §4).
- Flanking: path cost ×3–10 where the player can see, goal ≥ 60–90° off the player's facing,
  one flanker at a time, announced by a bark.

## Squads and attack tokens

- Token pool per target per attack type (DOOM 2016): start melee 1, ranged 2–3, grenade 1
  (working); acquire before attacking, release after, 0.5–2 s cooldown; an on-screen enemy may
  steal from an off-screen one; difficulty scales the pool.
- Without a token: reposition, strafe, take cover, taunt — visibly busy, never frozen.
- Squad behaviours give goals (F.E.A.R.: Get-to-Cover, Advance-Cover, Orderly-Advance, Search
  in pairs); barks 0.5–1 s before coordinated moves sell the coordination.

## Difficulty knobs (prefer the first)

Token pool → reaction delay → accuracy model (spread, first shots miss near the player, accuracy
drops with player speed — DOOM) → awareness gain and ranges → aggression (approach distance,
flank rate, grenade cooldown) → damage → health → count. Never aim snapping, hidden information
or superhuman reactions. Each knob per difficulty lives in a data resource.

## Debug view and acceptance (qa-ai)

Gym `scenes/gyms/ai_gym`: cover, doorway, ledge link, player dummy on a path. Toggleable overlay
per agent: state label, awareness bar, sight cone and LOS rays (green/red), hearing rings, last
known position, path and next waypoint, desired vs avoidance velocity, top-5 cover scores, token
held. The overlay is a debug scene; debug drawing carries `kiln:runtime-node debug`.

Probe per agent per tick: `<agent>.pos`, `.los` (world-only ray eye → player chest), `.fired`,
`.attacking` (bool or attack type), `.moving` (wants to move), `.state`.

```
python ${extensionPath}${/}skills${/}game-ai/scripts/ai_probe.py <dump> [--tokens 2 | --tokens melee=1,ranged=2] \
    [--min-reaction-ms 250] [--stuck-s 3 --stuck-m 0.5] [--dither-s 0.3] [--unit-scale 0.01]
```

Reports shots without LOS (0), reaction after sighting (≥ 250 ms), concurrent attackers vs
tokens, stuck episodes (0), state flips shorter than 0.3 s (0); JSON with `verdict`, exit 1 on
FAIL. Reachability, cover validity and cost stay qa-ai probes.

## Performance budget (override in GAME.md)

- AI + navigation ≤ 1.5 ms per frame at 60 fps in the heaviest arena (working).
- Agent i thinks when (frame + i) % N == 0; LOS rays ≤ ~30 per frame; ≤ 2 path requests per
  frame, queued.
- Off-screen or > 40 m agents think at 1–2 Hz without avoidance; dormant outside the encounter.

## Engines (agents are scenes/prefabs built through the engine MCP)

- **Godot 4.6/4.7**: HFSM as state nodes under the enemy scene; `NavigationAgent3D`/`2D` with
  avoidance via `velocity_computed`; LimboAI or Beehave (MIT) only with the user's approval.
- **Unity 6**: Behavior package (Behavior Graph + Behavior Agent) or a C# HFSM; `NavMeshSurface`
  per agent type, `NavMeshAgent`.
- **Unreal 5.8**: StateTree for new AI, or Behavior Tree + Blackboard + EQS; AI Perception;
  Gameplay Debugger and Visual Logger for evidence.
