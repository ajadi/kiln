# Doors per engine

Doors, frames, markers, triggers and links are built as nodes, prefabs or actors in the open
editor through the engine MCP (scene-first); scripts add behaviour and read those nodes. One door
scene/prefab per door kind, placed in levels. [U] = not confirmed in a primary source.

## Godot 4.6/4.7

```
DoorHinged (Node3D, door.gd)          # @export: open_angle 95, speed_deg_s 100, locked, key_id,
├── Frame (StaticBody3D + CollisionShape3D)      #   auto_close_s, push_side (+1/-1), door_id
├── Leaf (AnimatableBody3D, sync_to_physics on)  # animated door; or RigidBody3D for a physics door
│   ├── CollisionShape3D (box, leaf thickness)
│   ├── Mesh
│   └── HandleSocketPush / HandleSocketPull (Marker3D)   # IK targets for the hand
├── Hinge (HingeJoint3D)              # physics door only: node_a = Frame, node_b = Leaf
├── StandPush / StandPull (Marker3D)  # from `predict standoff`; facing the door
├── UseArea (Area3D + CollisionShape3D)          # prompt range; body_entered for auto-open
├── NavLink (NavigationLink3D)        # across the doorway; enabled = passable
├── Sfx (AudioStreamPlayer3D)         # latch, creak, thud, locked
└── Anim (AnimationPlayer)            # "open_push", "open_pull", "close", "locked_rattle"
```

- **Animated leaf**: AnimatableBody3D is meant for doors and lifts; `sync_to_physics` (on by
  default) moves it in step with physics when an AnimationPlayer drives it, so it pushes
  characters instead of tunnelling.
- **Physics leaf**: RigidBody3D with mass set (Godot defaults to 1 kg), HingeJoint3D with
  `angular_limit/enable` on (off by default; default limits ±90°) — set 0 to the open angle;
  `motor/enable`, `motor/target_velocity` (rad/s) and `motor/max_impulse` (default 1.0) for
  auto-close; under Jolt (default since 4.6) hinge motors are velocity-only and impulse × tick
  rate = torque (`predict swing` prints `godot_motor_max_impulse`); limit softness and bias
  properties are unsupported. Angular damping for the closer feel. CharacterBody3D does not push
  rigid bodies on its own reliably — apply a capped impulse at the contact from the character
  script (working).
- **Navigation**: toggle `NavigationLink3D.enabled` with the door state (locked = off); use
  `enter_cost` / `travel_cost` so agents prefer open routes; `navigation_layers` per agent kind.
  Links do not move the agent — handle `NavigationAgent3D.link_reached` (claim the door, open it,
  wait, walk through). `NavigationRegion3D.enabled` toggles a whole region. NavigationObstacle3D
  changes the navmesh only at bake time (`affect_navigation_mesh`) or steers avoidance; it does
  not re-route paths at runtime. The navmesh rounds `agent_radius` up to a multiple of
  `cell_size` (`predict clear --cell`); the default agent radius 0.5 and CapsuleShape3D radius
  0.5 do not fit a 0.9 m door.
- **Hands**: TwoBoneIK3D (4.6+, needs a pole target) from the shoulder to the handle socket,
  blended in over the reach; fingers from the hands skill's pose library.
- **Curtains**: SoftBody3D (pin the top row to the rail, precision ≥ 5, Jolt) for cloth; strips
  and bead strings as bone chains with SpringBoneSimulator3D and SpringBoneCollision3D capsules on
  the walker, or Verlet chains in script (soft-bodies skill).
- **Save**: door.gd exposes `door_id`, state (closed, open, ajar angle, locked, broken,
  barricaded) to the save service as deltas from the level (save-system skill); on load set the
  leaf angle, zero its velocity and set the NavLink before agents path.

## Unity 6

- Animated door: kinematic Rigidbody moved with `MoveRotation` in FixedUpdate (or an Animator with
  Animate Physics), so it pushes bodies; Timeline for the synced interaction.
- Physics door: HingeJoint anchored where the leaf meets the frame, axis Y; Use Limits (min/max),
  Use Spring (spring, damper, target position) for self-closing and double-action doors, Use
  Motor (target velocity, force) for powered doors, Break Force for kicked-in doors.
- CharacterController does not push rigid bodies; push in `OnControllerColliderHit` with a
  capped force (working).
- Navigation: NavMeshLink across the doorway, `Activated` off when locked, Cost Modifier for
  closed doors; or a NavMeshObstacle with carving for doors that usually block — Carve Only
  Stationary suits physics doors; carving takes effect a frame later.
- Hands and approach: Animation Rigging Two Bone IK (target + hint) to the handle socket;
  `Animator.MatchTarget` to land on the stand spot.
- Cloth curtains: Cloth component collides only with the sphere and capsule colliders assigned to
  it and pushes nothing back.

## Unreal 5.6–5.8

- Physics door: Physics Constraint Component with a hinge setup (one angular axis limited, e.g.
  0–110°, others locked) and an angular drive for closing; Character Movement's physics
  interaction (`bEnablePhysicsInteraction`, `PushForceFactor`) pushes it [U for defaults].
- Animated door: Timeline or a Level Sequence on a movable actor; the synced interaction as a
  Contextual Animation scene (roles character + door, warp points, alignment, IK targets) with
  Motion Warping (Skew Warp to the stand spot during a notify window; needs root motion and the
  plugin).
- AI: NavLinkProxy smart link across the doorway — `bSmartLinkIsRelevant`,
  `OnSmartLinkReached` (open, wait, then `ResumePathFollowing`); toggle it or a Nav Modifier
  area with the door state. Smart Objects for who opens: claim a slot, occupy, release (one slot
  per side; a vehicle has a slot per seat). Smart-link events have failed in PIE in older
  versions (UE-36194) — test standalone if they never fire.
- Cloth curtains: Chaos Cloth with tethers; strips as AnimDynamics or Kawaii Physics chains
  (soft-bodies skill).
