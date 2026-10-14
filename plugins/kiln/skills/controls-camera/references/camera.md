# Camera reference

Values marked (working) are starting points; [U] = not confirmed in a primary source. "Nesky #n"
refers to the list in §6.

## 1. Pick the rig

| Rig | Use | Start values (working) |
|---|---|---|
| First person | shooters, immersive sims | eye height 0.936 H (human-biomechanics); FOV setting; near plane 0.02–0.05 m |
| Over the shoulder | third-person shooters | distance 1.5–2.5 m; shoulder 0.4–0.7 m sideways, 0.2–0.4 m up (Cinemachine example 0.7/0.3/−0.5, arm 0.5, distance 2); vertical FOV 50–60° |
| Free orbit | action-adventure, melee | 3–5 m; pitch −60…+70°; optional recentering |
| Lock-on | duels, bosses | §4 |
| Top-down / isometric | twin-stick, tactics | fixed pitch 45–60°; look-ahead toward aim, not only movement |
| Side view (2D) | platformers | feel-numbers § 2D (drag margins, look-ahead, pixel snapping) |
| Fixed / cinematic | horror, cutscenes | cuts; keep the control frame (§5) |

Use a dynamic orbit camera only when the level needs it (Nesky #1); design levels and camera
together (#2).

## 2. Third-person cameras

**Framing.** Aiming rigs put the avatar 1/6–1/3 of the screen width toward the shoulder with
the reticle at screen centre; free cameras keep the avatar near centre with lead room in the
move direction. Look-ahead: shift the pivot 0.5–1.5 m along velocity, smoothed over 0.3–0.5 s,
less while aiming. Look at what matters, not only the avatar (#21): hint toward landmarks,
threats and drop edges (#25), pitch with slopes (#26), and avoid excessive rotation toward near
targets (#31).

**Smoothing.** Follow the pivot with a frame-rate-independent spring:
`x += (target - x) * (1 - exp(-dt / tau))`, tau 0.05–0.15 s horizontal, 0.15–0.3 s vertical, and
a vertical dead band of ~1 m in the air so jumps do not bob the view (#28, #45). Rotation from
player input is never damped.

**Collision and occlusion** (one solver owns the camera position; no competing pushes, #8):
1. Sphere-cast from the pivot (head or shoulder) to the desired position. Radius r ≥ near-plane
   half-diagonal: `r = n * tan(vfov/2) * sqrt(1 + aspect²) + 0.02 m` (n 0.05, vFOV 60°, 16:9
   → 0.08 m; use 0.1–0.15 m).
2. On a hit place the camera at the hit distance in the same tick — never interpolate inward
   through a wall (#7).
3. When clear, ease back over 0.3–0.6 s after holding 0.1–0.3 s, so weaving between columns
   does not pump the distance (Lyra blends in 0.1 s / out 0.15 s [U]).
4. Predict side occlusion with feeler rays from the pivot at ±15–30° yaw (Lyra: centre, ±16°,
   ±32°, ±20° pitch [U]) and react before the centre ray is blocked (#4, #5).
5. Thin occluders (posts, branches, < ~0.3 m) and short occlusions (< 0.2–0.3 s) fade or dither
   instead of moving the camera (#9, #10); a slope below the pivot raises the camera instead of
   pulling it in (#11); occluders behind the camera do not swing it sideways (#12).
6. If the player rotates the camera into a wall, let them; pull in, do not push back (#6).
7. Camera within 0.3–0.5 m of the avatar: fade the avatar; the near plane never cuts the avatar
   (#13). Cut if the avatar stays behind opaque geometry > 0.5 s (#17).

**Recentering and hints.** Wait 1.5–3 s after the last look input (Sea of Thieves 2.0 s), turn
≤ 90–180°/s with ease in/out, yaw first, never while aiming or locked on, and expose an off
switch (XAG 117). While running and not steering the camera, follow the run direction with a low
gain (#23). Designer camera hints (trigger volumes with desired yaw/pitch/distance) blend over
0.5–1 s and wait 1–2 s after the player last turned the camera (#35).

**Limits.** Pitch −60…+70° (third person), ±85–89° (first person); slow down over the last
10–15° instead of stopping at full speed (#47). Pitch, distance and FOV come from one curve
(#14–#16): low angles shorten the distance and widen the FOV.

## 3. First-person cameras

- Eye height 0.936 H; crouch eye per the crouch pose; the camera follows input, never the
  animation (human-biomechanics rule 13). Body-aware cameras stabilise the head bone.
- FOV conversion: `h = 2·atan(tan(v/2)·aspect)`, `v = 2·atan(tan(h/2)/aspect)`. At 16:9:
  90° h = 58.7° v; 75° v = 107.5° h; 60° v = 91.5° h. Godot `Camera3D.fov` is vertical with
  `KEEP_HEIGHT` (default 75°); Unity `Camera.fieldOfView` is vertical (default 60°); Unreal
  `FieldOfView` is horizontal (default 90°). Keep vertical FOV fixed on ultrawide (Hor+).
- Option range: 70–110° horizontal common (Minecraft up to 110°, Halo Infinite shown at 97° in
  XAG 117); a too-small FOV causes sickness (#41); rapid FOV shifts too (#42).
- Viewmodel: render arms/weapon with their own FOV (50–70° vertical, working) and scale so they
  do not stretch at wide FOV or clip walls — Unreal First Person Rendering (First Person Field
  Of View / Scale), Godot a second camera in a SubViewport or a vertex shader, Unity URP Render
  Objects with an FOV override.
- Recoil (working): pitch kick 0.2–1.5° per shot, yaw ±0.1–0.5° random, 60–100% recovery within
  0.1–0.3 s by spring; weapon-model recoil separate from aim recoil (feel-numbers).
- Head bob (#44): off or ≤ 1–2 cm vertical and ≤ 0.5° roll, phase-locked to footfalls, 0–100%
  slider. Landing dip 3–8 cm over 0.15–0.3 s scaled by fall speed (working). Sprint FOV +5–10°
  over 0.2–0.3 s. Shake rotation-only, decays in ~0.5 s, slider (#43, XAG 117).

## 4. Lock-on

- Acquire: visible candidates within 15–25 m (melee, working) and ±30–45° of camera forward;
  score by angle (weight ~0.6) then distance (~0.4).
- Frame: look at a point between avatar and target weighted 0.5–0.7 toward the target; avatar in
  the lower third; aim at the target's chest, raise and widen for tall targets; target in view
  100% of lock ticks.
- Switch: right-stick flick ≥ 0.7–0.8 picks the nearest target in that screen direction; the
  stick must return below 0.3 before the next switch.
- Break: target dies → nearest valid target within 0.3–0.5 s or release; line of sight lost
  > 1–2 s; distance > 1.2 × acquire range (hysteresis).
- Rotation ≤ 180°/s eased; when the target passes over or behind the avatar, cap pitch and allow
  brief avatar occlusion rather than spinning.

## 5. Transitions and cinematics

- Cut when the view changes more than ~60–90° or the space changes; blend gameplay cameras over
  0.3–1.0 s ease-in-out, cinematic 1–2 s (#46).
- Keep the player's control frame after a cut until the stick is released or turns > 45° (#18);
  keep direction sense across shots (#19) and the 180° rule (#20).
- Returning from a cutscene blends into the gameplay camera's current desired pose; input may
  interrupt the blend. Do not take control away mid-action (#34).

## 6. Camera mistakes (Nesky, GDC 2014) — review checklist

1 dynamic camera where another would do · 2 level and camera design mismatch · 3 persisting
camera state in global coordinates/quaternions · 4 default distance likely to lose line of sight
· 5 side obstacles break line of sight · 6 pushing away while the player swings toward an
obstacle · 7 player pushes the camera inside an obstacle · 8 independent forces compete · 9
moving a lot for unimportant occluders · 10 intersecting narrow columns · 11 treating a hill as
a wall · 12 swinging sideways for occluders from behind · 13 near plane cuts the avatar · 14 same
distance at all angles · 15 same FOV at worm's-eye angles · 16 pitch, distance and FOV shifted
independently · 17 no cut when the avatar passes through opaque objects · 18 cuts remap
directional controls · 19 breaking the sense of direction · 20 violating the 180° rule · 21
focusing only on the avatar · 22 player must steer the camera all the time · 23 yaw left alone
while running · 24 hard to judge distances · 25 looking straight ahead at a cliff · 26 level
camera on slopes · 27 misused rule of thirds · 28 same logic on ground and in the air · 29 only
procedural behaviour · 30 letting players get lost · 31 rotating a lot toward nearby targets · 32
translating to look at distant targets · 33 avatar's body occludes targets ahead · 34 giving
control then taking it away · 35 hint right after the player turned the camera · 36 experts
cannot explore · 37 no inverted controls · 38 responding to accidental input · 39 linear
sensitivity · 40 pivot drifts too far · 41 FOV too small · 42 rapidly shifting FOV · 43
excessive shake · 44 bobbing with the walk cycle · 45 moving with the jump · 46 rapid transitions
· 47 full pitch speed until the limit · 48 VR as the primary target · 49 testing with a narrow
demographic · 50 a general constraint solver for the camera.

## 7. Probes for camera_probe.py

Godot (game eval, recorder from the acceptance skill; `cam`, `hero`, `cam_shape` are scene
nodes — `cam_shape` is a ShapeCast3D child of the camera in the gym scene with a SphereShape3D
of radius r, `target_position` zero, world mask):

```gdscript
var aim := func(): return hero.global_position + Vector3.UP * 1.3
rec.add_probe("cam_pos", func(): return cam.global_position)
rec.add_probe("cam_fwd", func(): return -cam.global_basis.z)
rec.add_probe("target_pos", aim)
rec.add_probe("fov", func(): return cam.fov)
rec.add_probe("occ", func(): return not cam.get_world_3d().direct_space_state.intersect_ray(
    PhysicsRayQueryParameters3D.create(cam.global_position, aim.call(), WORLD_MASK, [hero.get_rid()])).is_empty())
rec.add_probe("inside", func(): cam_shape.force_shapecast_update(); return cam_shape.is_colliding())
rec.add_probe("look_in", func(): return Input.get_vector(&"look_left", &"look_right", &"look_up", &"look_down").length())
```

Unity/Unreal probes write the same names as JSON Lines (one object per tick, vectors as
`[x, y, z]`, plus `dt`); pass `--unit-scale 0.01` for Unreal centimetres. Add a boolean `cut`
on ticks where a deliberate cut happens and `zoom` while ADS/zoom changes the FOV.

Metrics: inside ticks; occluded ratio and longest run; target-in-view ratio (cone of half the
vertical FOV, conservative); automatic angular speed and acceleration (ticks with look input
below 0.05 and 0.25 s after it, cuts excluded); pops (automatic turn > 30° per tick, or a
sideways/outward jump > 1 m that is not a pull-in toward the target); FOV range and rate; look
latency (input onset → first camera rotation, in ticks).

## 8. Engine cameras (built through the engine MCP)

**Godot 4.6/4.7**

```
Player (CharacterBody3D)
└── CameraRig (Node3D, top_level)      # follows hero.get_global_transform_interpolated() in _process
    └── Yaw (Node3D)
        └── Pitch (Node3D)
            ├── SpringArm3D            # shape SphereShape3D r 0.1–0.15, spring_length 3, margin 0.05, mask World
            └── Camera3D               # current, fov (vertical), physics_interpolation_mode Off
```

- `SpringArm3D` moves its direct children to the hit point instantly in both directions. For an
  eased return keep the camera as a sibling, read `get_hit_length()` each frame, snap inward,
  ease outward. Exclude the player with `add_excluded_object(player.get_rid())` or the mask.
- Physics interpolation (3D since 4.4): cameras follow the interpolated target in `_process`
  and turn the camera's own interpolation off; mouse look applied directly in
  `_unhandled_input` with `event.screen_relative` (engine docs, advanced physics interpolation).
- First person: `Head` (Node3D at eye height) under the body, pitch on Head, yaw on the body;
  shake on a dedicated `Shake` Node3D between Head and Camera3D; `CameraAttributesPractical` for
  exposure/DOF.
- Lock-on and hints: Area3D trigger volumes and Marker3D targets placed in the level; scripts read
  them through `@export`.
- Phantom Camera (MIT, 0.11.x, Godot 4.4+): `PhantomCameraHost` under the Camera3D,
  `PhantomCamera3D` nodes with priority, follow modes (Glued, Simple, Group, Path, Framed, Third
  Person) and tweened transitions. Third-party editor plugin — only with the user's approval,
  recorded in `memory/decisions.md`.

**Unity 6 (Cinemachine 3.1)** — through `manage_camera` / `manage_gameobject` /
`manage_components`.
- Main Camera + `CinemachineBrain` (Update Method Smart Update; default blend EaseInOut 2 s →
  custom blends 0.3–1 s for gameplay).
- Shoulder: `CinemachineCamera` tracking a look-target child + `CinemachineThirdPersonFollow`
  (built-in collision: camera radius 0.1–0.2, damping into collision ~0, from collision
  0.3–0.6) + `CinemachineThirdPersonAim`.
- Free orbit: `CinemachineOrbitalFollow` (recentering Wait/Time per axis) +
  `CinemachineRotationComposer` + `CinemachineInputAxisController` (Gain; keep Accel/Decel near 0
  for look) + `CinemachineDeoccluder` (strategy, Camera Radius, Minimum Occlusion Time 0.1–0.3 s,
  Damping 0.3–0.6, Damping When Occluded ~0, Transparent Layers, Ignore Tag = player) or
  `CinemachineDecollider` (keeps out of colliders without preserving line of sight).
- First person: `CinemachinePanTilt`, or a plain Camera under the head. Lock-on: a second
  `CinemachineCamera` looking at a `CinemachineTargetGroup` (player + target, weights), switched by
  priority. Shake: `CinemachineImpulseSource` + `CinemachineImpulseListener`, gain from settings.
- CM2 → CM3: VirtualCamera/FreeLook → CinemachineCamera; Collider → Deoccluder; 3rdPersonFollow →
  ThirdPersonFollow; POV → PanTilt; Transposer → Follow; FramingTransposer → PositionComposer;
  Composer → RotationComposer; namespace `Unity.Cinemachine`.

**Unreal 5.8**
- `SpringArmComponent`: TargetArmLength 300 cm default (250–400 action, 150–250 shoulder);
  SocketOffset Y 50–70, Z 50–70 cm for over-the-shoulder; `bUsePawnControlRotation` on;
  `bDoCollisionTest` on with ProbeChannel Camera, ProbeSize 10–15 cm (default 12); camera lag
  10–20 with a max distance; no rotation lag on input-driven aim. Small props and foliage ignore
  the Camera channel; level geometry blocks it.
- `CameraComponent` FOV is horizontal; set the local player's aspect-ratio axis constraint to
  keep vertical FOV for ultrawide (`AspectRatio_MaintainYFOV`). `PlayerCameraManager`: ViewPitchMin/Max, DefaultFOV,
  camera modifiers for zoom; camera shakes (`UCameraShakeBase` patterns) scaled by a setting.
- First Person Rendering (5.6 template): First Person Field Of View / Scale on the camera,
  first-person primitive type on arms and weapon.
- Gameplay Cameras plugin (camera rigs, camera director) was Experimental in 5.7; 5.8 status [U] —
  optional, user approval. Lyra's third-person camera mode is the reference for feeler-based
  penetration avoidance.

## Sources

Nesky "50 Game Camera Mistakes" (GDC 2014; list via shermanrose.uk notes); Haigh-Hutchinson
"Real-Time Cameras" (2009, background); XAG 117; Godot Camera3D/SpringArm3D docs and physics
interpolation guide; Cinemachine 3 manual (GitHub docs); Unreal SpringArmComponent and First
Person Rendering docs; Lyra camera (UE sample) [U values].
