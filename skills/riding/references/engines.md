# Engine notes for riding — Godot 4.6/4.7, Unity 6, Unreal 5.6–5.8

How to attach the rider, drive the rider from the horse's phase, move the pair and place hands and
feet. Build scenes in the editor through the engine MCP (protocol: scene_first). Sources in
the research notes for this skill (kept in Kiln's development repository); [U] = unverified.

## Godot 4.6/4.7

- **Attach**: the rider scene under a `BoneAttachment3D` on the horse's saddle (spine) bone, in
  follow-only mode (`override_pose` off — its signal-driven override misbehaves next to
  SkeletonModifier3D). `use_external_skeleton` + `external_skeleton` when the attachment node is not
  a child of the horse's Skeleton3D. Turn off the rider's CharacterBody3D collision while mounted
  (or switch it to a layer that ignores the horse) and `reparent(seat, true)` on mount, back on
  dismount (traversal: seats).
- **Gait blending**: AnimationTree with a BlendSpace1D (or 2D with turn rate) per gait group. 4.7:
  `sync_mode` = `SYNC_MODE_CYCLIC_MUTABLE` (all clips time-scaled to one cycle computed from the
  active weights) or `SYNC_MODE_CYCLIC_CONSTANT` (one cycle of `cyclic_length` s); the old `sync`
  bool is deprecated (true = `SYNC_MODE_INDEPENDENT`). 4.6 has only the `sync` bool.
- **Rider from the horse's phase**: author each rider clip with the same normalized cycle as the
  horse clip it rides (same marker positions — recommendation [U]); each tick write the horse's
  phase into the rider tree with an `AnimationNodeTimeSeek` (`seek_request`, seconds). A TimeSeek
  placed after a cyclic-synced blend space breaks the sync when clip lengths differ — use
  `use_custom_timeline` on the clips instead.
- **Root motion or code**: code-driven velocity with clips scaled to it (phase from distance) is the
  default for a player mount; root motion (`root_motion_track`, `get_root_motion_position()` /
  `get_root_motion_rotation()`, read in `_physics_process`) for mount/dismount, jumps, rears and
  stops where the clip must land exactly.
- **IK**: 4.6+ `TwoBoneIK3D` (deterministic) for rider hands to rein targets and feet to stirrup
  sockets, with pole targets (elbows down and out, knees forward); horse hooves to the ground with
  one `TwoBoneIK3D` per leg (intermediate bones as virtual bones for the 3-segment leg) or
  `IterateIK3D`/`FABRIK3D`; `LimitAngularVelocityModifier3D` after deterministic IK to smooth jumps.
  Modifiers run after the AnimationMixer in child order: horse IK first, then the rider.
- **Navigation**: one navigation map and navmesh per agent radius and height — the horse gets its
  own (game-ai).

## Unity 6

- **Attach**: `Transform.SetParent(saddleSocket, false)` on mount; disable the rider's
  CharacterController; or a Multi-Parent constraint (Animation Rigging) to blend between the ground
  and the saddle during mount clips.
- **Phase**: read the horse's phase as the fractional part of `AnimatorStateInfo.normalizedTime`;
  drive the rider with the state's Motion Time parameter, or `Animator.Play(state, layer,
  normalizedTime)`.
- **IK**: Animation Rigging Two Bone IK (target + hint) for hands to reins and feet to stirrups;
  `Animator.MatchTarget` (root motion, one match at a time) to land the seat on the saddle at the end
  of a mount clip.
- **Navigation**: `NavMeshSurface` per Agent Type (horse radius and height).

## Unreal 5.6–5.8

- **Attach**: `Attach Actor To Component` with the horse's mesh and a saddle socket name; snap to
  target; disable the rider's capsule collision and set its movement mode to none while mounted.
- **Phase**: sync groups and sync markers work inside one Anim Blueprint; across two actors copy the
  horse's normalized phase (or marker position) into the rider's Anim Blueprint each tick [U].
- **Mount/dismount**: Motion Warping (warp target on the saddle, warp windows on the root-motion
  montage); Contextual Animation scene assets hold one track per role (rider, horse), one set per
  side, warp points and IK tracks.
- **IK**: Control Rig / IK Rig two-bone chains for hands and feet; Full Body IK for the seat.

## Probes for the checks

Record per tick (acceptance recorder): horse root position, saddle seat socket world position,
rider seat (pelvis) point, the four hoof positions or contact flags, the horse's lean (degrees or
the body up vector), and booleans such as `sitting`, `mounted`. Then run `riding_check.py seat`,
`follow`, `hooves`, `lean`, `grip`.
