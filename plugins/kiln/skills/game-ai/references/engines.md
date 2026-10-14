# Game AI per engine

Agents are scenes/prefabs/Blueprints built in the open editor through the engine MCP; scripts add
behaviour and read their nodes. Values marked [U] are not confirmed in a primary source.

## Godot 4.6/4.7

```
Grunt (CharacterBody3D)               # scenes/actors/grunt/grunt.tscn
├── CollisionShape3D
├── Model (instanced .glb) + AnimationTree
├── NavigationAgent3D                 # radius = capsule radius, avoidance on, max_speed from the stride table
├── Eyes (Marker3D at eye height)
├── Brain (Node, brain.gd)            # HFSM root: @export think_hz, reaction_s, data: EnemyData
│   ├── Patrol / Investigate / Search / Dead (Node + state script)
│   └── Combat (Node)
│       └── Advance / TakeCover / Attack / Reload
├── ThinkTimer (Timer, 0.1–0.25 s)    # brain randomises the first start to stagger agents
└── DebugOverlay (instanced debug scene, hidden unless the debug toggle is on)
```

- State base: `class_name AIState extends Node` with `enter`, `exit`, `think(dt) -> StringName`
  (next state or `&""`), `physics(dt)`. The brain calls `think` on the timer and `physics` from
  `_physics_process`; tunables are `@export` on state nodes or in `data/enemies/*.tres`.
- Perception: LOS with `PhysicsRayQueryParameters3D.create(eye, target, WORLD_MASK, [get_rid()])`
  inside `_physics_process`. Put a `PerceptionManager` node in the level scene (placed in the
  editor) that round-robins LOS requests under a per-frame ray budget — no new autoload. Noise
  events go through the project's signals-only event bus or that manager.
- `NavigationAgent3D` defaults: radius 0.5, height 1.0, max_speed 10, avoidance off,
  neighbor_distance 50, max_neighbors 10, time_horizon_agents 1.0, path_desired_distance 1.0,
  target_desired_distance 1.0, path_max_distance 5.0. Set radius to the capsule, lower
  neighbor_distance to 5–10 m, use `navigation_layers` for access rules and
  `set_navigation_map()` for the size-specific map.
- Loop: set `target_position` when the goal moves > 1–2 m; call `get_next_path_position()` once
  per physics frame; with avoidance call `set_velocity(desired)` and move in the
  `velocity_computed(safe_velocity)` handler with `move_and_slide()`. Skip while
  `NavigationServer3D.map_get_iteration_id(map) == 0` (map not synced). Jumps and climbs:
  `NavigationLink3D` + `link_reached`. Moving blockers: `NavigationObstacle3D` (avoidance);
  carving happens only at bake.
- Reachability probe: `NavigationServer3D.map_get_path(map, from, to, true)`; last point within
  0.5 m of the goal.
- Debug: `NavigationAgent3D.debug_enabled`, Debug → Visible Navigation / Avoidance; cost from
  `Performance.TIME_NAVIGATION_PROCESS` and the navigation monitors.
- 2D: `NavigationAgent2D` with the same API; `NavigationRegion2D` per layer of the level.
- Optional plugins (third-party editor plugins — ask the user, record the approval in
  `memory/decisions.md`): **LimboAI** 1.8.x (MIT; GDExtension for Godot 4.6+, module builds per
  engine version; behaviour trees + `LimboHSM` state machines, blackboard plans and scopes,
  visual debugger) and **Beehave** (MIT; behaviour trees as scene-tree nodes with a debug view;
  2.10+ for Godot 4.5+ per its README, latest tagged release 2.9.3).

## Unity 6

- **Behavior package** (`com.unity.behavior` 1.0.x): Behavior Graph assets (Action nodes,
  flow nodes incl. Abort/Restart — observer aborts, modifiers such as Repeat, Conditional Guard/Branch,
  event channels), Blackboard variables, and the **Behavior Agent** component that runs a graph on
  a GameObject and overrides exposed variables per instance; play-mode debug view shows node
  status. Custom nodes are C# ("Create new Action"). It relies on `SerializeReference`:
  renaming or moving node classes breaks graph assets. If the MCP cannot edit graph assets, use a
  C# HFSM (plain classes driven by one MonoBehaviour, tuning in ScriptableObjects) or author the
  graph with the user.
- Navigation (AI Navigation 2.x): one `NavMeshSurface` per agent type (radius, height, step,
  slope; Humanoid default 0.5 / 2 / 0.75 / 45°); `NavMeshModifier`/`Volume` area costs for
  flank routes; `NavMeshLink` for jumps; `NavMeshObstacle` carving for blockers that stay put.
- `NavMeshAgent`: speed, angular speed, acceleration, stopping distance, auto braking, radius,
  height, obstacle avoidance quality (lower it for crowds), priority 0–99 (lower = more
  important). Reachability: `NavMesh.CalculatePath` + `NavMeshPath.status == PathComplete`;
  cover sampling: `NavMesh.SamplePosition`.
- Perception: no built-in system — `Physics.OverlapSphereNonAlloc` + angle + `Physics.Raycast`
  with a world-only `LayerMask`; batch many rays with `RaycastCommand`.
- Debug and cost: Behavior graph debug, `OnDrawGizmosSelected` (editor only), AI Navigation
  overlay, `ProfilerMarker` per AI system for ms in the Profiler.

## Unreal 5.8

- **StateTree** for new AI: a hierarchical state machine with behaviour-tree style selection;
  `StateTreeAIComponent` (AI schema) on the AIController; states with tasks, enter conditions and
  transitions (on completed, failed, event, tick); global tasks/evaluators for perception data;
  property bindings; StateTree debugger. Practitioners report the Behavior Tree editor has seen
  little feature work since 5.3 [U].
- **Behavior Tree + Blackboard**: Selector, Sequence, Simple Parallel; decorators with observer
  aborts (Self, Lower Priority, Both); services for periodic updates (default interval 0.5 s,
  random deviation 0.1 s); event-driven re-evaluation.
- **EQS** for cover and flank points: generators (on circle, grid, pathing grid, actors of
  class), tests (trace/visibility, distance, dot, pathfinding), best or random-top-5% selection;
  EQS Testing Pawn shows scores in the editor.
- **AI Perception**: `AIPerceptionComponent` on the controller; Sight (Sight Radius, Lose Sight
  Radius > Sight Radius, Peripheral Vision Half Angle, Auto Success Range From Last Seen, Max Age,
  Detection by Affiliation), Hearing (`ReportNoiseEvent` / `MakeNoise` with loudness and max
  range), Damage, Team, Touch, Prediction; targets carry `AIPerceptionStimuliSourceComponent`.
  Affiliation needs `IGenericTeamAgentInterface` (C++); without it everything is neutral.
- Navigation: a RecastNavMesh per Supported Agent; `NavModifierVolume` + area classes for costs;
  `NavLinkProxy` / smart links for jumps; avoidance by RVO on Character Movement or Detour Crowd
  (`UCrowdFollowingComponent`) — one per agent type; Mass for crowds.
- Tokens, perception helpers and probes in C++ (systems), behaviours in StateTree/BT assets
  (content), per the engine profile.
- Evidence: Gameplay Debugger (apostrophe key; Numpad 4 = perception; AI, BT, EQS, navigation
  categories), Visual Logger recordings per agent, probe JSON Lines per the engine profile.

## Sources

Godot NavigationAgent3D class reference and "Using NavigationAgents"; LimboAI and Beehave
READMEs (GitHub); Unity Behavior 1.0 manual; Unity AI Navigation 2.0 manual; Unreal StateTree,
Behavior Tree, EQS and AI Perception docs (5.8); StraySpark StateTree vs Behavior Tree blog
(practitioner).
