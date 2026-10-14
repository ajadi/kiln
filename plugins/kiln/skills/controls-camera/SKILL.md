---
name: controls-camera
description: Player controls and gameplay cameras in numbers — action mapping, default keyboard/mouse and gamepad layouts per genre, remapping and persistence, stick dead zones and response curves, aim assist, input buffering, device switching and glyph prompts, Steam Input, hold vs toggle, vibration; third-person, first-person, lock-on and cinematic cameras, the camera-mistakes list, measurable camera acceptance with camera_probe.py, and Godot 4.6/4.7, Unity 6 and Unreal 5.8 setup through the engine MCP. Use when building, tuning or reviewing input, sensitivity, aiming, prompts or any gameplay camera.
user-invocable: false
---

# Controls and cameras

Controls are the player's hands and the camera is their eyes; both are judged in ticks, degrees
and percentages. Values marked (working) are starting points to tune per project; [U] = not
confirmed in a primary source. Latency, coyote time, jump buffer, shake and FOV complaints are in
feel-numbers (`${CLAUDE_PLUGIN_ROOT}/skills/pipeline/references/feel-numbers.md`); player-facing
requirements (remap UI, subtitles, motion options) in the `accessibility` skill. Detail:
`${CLAUDE_SKILL_DIR}/references/input.md` (layouts, dead zones, aim assist, glyphs, engine input)
and `${CLAUDE_SKILL_DIR}/references/camera.md` (rigs, collision, lock-on, mistakes, engine cameras).

## Workflow

1. **Action list** in `memory/registries.md`: actions named by intent (move, look, fire, aim,
   interact), one context per mode (on foot, vehicle, menu). Never code against keys. Vehicle
   handling and assists: vehicles skill; getting in and out, driver poses: traversal skill.
2. **Default bindings** for keyboard/mouse and gamepad from the genre table (input.md §1). No
   action needs two simultaneous buttons, rapid mashing or a hold over 1 s (working) without an
   alternative (XAG 107).
3. **Analog chain** per stick: raw → scaled radial dead zone → response curve → yaw/pitch
   sensitivity → aim assist → camera. Mouse: raw delta × sensitivity, no smoothing, no
   acceleration.
4. **Camera rig as scene nodes** in a camera gym (`scenes/gyms/camera_gym`: walls, thin columns,
   low ceiling, slope, cliff edge, doorway, moving target), built in the editor through the MCP;
   scripts only drive it.
5. **Options and persistence**: remap, sensitivity per axis, invert per axis, dead zone, FOV,
   shake/bob/sway sliders, hold/toggle, vibration, aim assist; saved per user, loaded before the
   first gameplay frame.
6. **Probe and accept** with the table below; qa-feel signs off.

## Rules

1. Prompts read the live binding; a remap updates every hint, tutorial and glyph (XAG 107).
2. Sticks use a **scaled radial** dead zone: inner 0.10–0.20 (start 0.15), outer 0.90–0.95,
   output rescaled to start at 0 at the inner edge (Sutphin). XInput's 0.24/0.27 defaults suit
   worn sticks; expose the inner value as a setting. Axial dead zones only for 4/8-way use.
3. Look uses a curve, not linear (Nesky #39): out = m^γ, γ 1.5–2.5 (start 2.0). Movement stays
   linear so walk/run blends follow stick tilt.
4. Yaw and pitch speeds are separate settings (pitch ≈ 0.6–0.8 × yaw, working); range at least
   ±50% of default (XAG 107); invert X and Y per stick. Optional turn boost only at ≥ 0.95
   deflection after 0.1–0.2 s, ramping over 0.2–0.4 s (working).
5. Analog→digital uses hysteresis: press ≥ 0.5, release ≤ 0.375 (Unity defaults 0.5 × 0.75).
   Menu repeat: 0.4–0.5 s delay, then 8–12 Hz (working).
6. Nothing smooths the look path; the camera turns on the same or next tick after input.
7. Buffer one press per action for 0.10–0.20 s (working), consume it once, clear it on a state
   change that makes it meaningless.
8. Holds: tap ≤ 0.2 s, hold ≥ 0.4 s (Unity defaults); every hold has a toggle option.
   Keyboard rollover: many membrane and laptop keyboards drop a third key in common combos —
   live run: W + Shift + Space typed no space, so a running jump was impossible. Core moves must
   work with two keys held: sprint defaults to a toggle on keyboard (or the run key sits off
   the W/Space cluster), and acceptance tests the combo on a real keyboard, not only through
   injected actions.
9. Both devices work at once; the last device with meaningful input (stick past the dead zone
   + 0.15, mouse > ~5 px, any key or button) owns the prompts, switching within one frame without
   flicker from idle drift. Under Steam Input take glyphs from the Steam API (input.md §7).
10. Aim assist is for analog aim only, never the mouse; per weapon; off/low/standard option.
    Slowdown 30–50% near targets, rotation 0.3–0.6 of the target's angular velocity only while
    the player gives input, bullet bending ≤ 1–2°, never through walls (input.md §5).
11. ADS sensitivity scales by tan(fov_ads/2) / tan(fov_hip/2) so screen-space speed is kept.
12. Vibration follows events, lasts ≤ 0.5 s except sustained states, has an intensity slider
    and an off switch, and stops on pause and focus loss.

Camera:

13. Never inside geometry: pull in within 1 tick, ease back out over 0.3–0.6 s; probe radius ≥
    near-plane half-diagonal + margin (camera.md §2).
14. Keep the avatar visible: thin (< ~0.3 m) or brief (< 0.2–0.3 s) occluders fade instead of
    moving the camera; no sideways swing for occluders behind the camera (Nesky #5–#12).
15. The camera moves on its own only with a reason (recenter, lock-on, hint): ≤ 180°/s with
    ease in/out; recentering waits 1.5–3 s after the last look input (Sea of Thieves 2.0 s,
    180), can be disabled (XAG 117), and never fights player input (Nesky #34, #35).
16. One curve drives distance, height and FOV from pitch (Nesky #14–#16).
17. FOV is a setting: first person 70–110° horizontal at 16:9 (PC default ~90°, TV 70–80°),
    third person ~50–60° vertical; gameplay FOV changes (sprint, damage) ≤ ±10° over ≥ 0.15 s
    (working; Nesky #41, #42). Store FOV with its axis — engines differ (camera.md §3).
18. Head bob ≤ 1–2 cm with a 0–100% slider; shake rotation-only with a slider; sway optional
    (XAG 117).
19. A cut keeps the control frame until the stick is released (Nesky #18) and respects the 180°
    rule (#20).

## Acceptance (qa-feel)

| Check | PASS | Source |
|---|---|---|
| Camera inside geometry | 0 ticks (sphere = near-plane half-diagonal) | Nesky #7, #10, #13 |
| Avatar / target occluded | ≤ 5% of ticks, no run > 0.5 s (working) | Nesky #4, #5 |
| Lock-on target in view | 100% of lock ticks | — |
| Automatic rotation | ≤ 180°/s and ≤ 720°/s² (working) | Sea of Thieves setting (XAG 117); Nesky #46 |
| Pops | no automatic turn > 30° or sideways jump > 1 m in one tick without a cut flag | Nesky #46 |
| FOV | inside the option range; ≤ 60°/s outside zoom events (working) | XAG 117 |
| Look input → camera | ≤ 1 tick | feel-numbers |
| Stick | no output inside the dead zone; ≤ 10% of max just past it; diagonal vs cardinal max within ±5% | Sutphin |
| Remap / device switch | prompts show the new binding after restart; glyphs switch within 1 frame | XAG 107, Deck Verified |

```
python ${CLAUDE_SKILL_DIR}/scripts/camera_probe.py camera <dump> --cam-pos cam_pos --cam-fwd cam_fwd \
    --target target_pos [--occluded occ] [--inside inside] [--fov fov --fov-range 60 110] \
    [--look look_in] [--cut cut] [--zoom zoom] [--lock-on] [--unit-scale 0.01]
python ${CLAUDE_SKILL_DIR}/scripts/camera_probe.py stick <dump> --input stick --response look_rate --inner 0.15
```

Reads the acceptance recorder dump or JSON Lines (Unity/Unreal probes). Probes: `cam_fwd` =
camera forward vector; `occ` = world-only ray camera → target chest hits; `inside` = sphere
overlap at the camera; `look_in` = look input magnitude. Prints JSON with `verdict`; exit 1 on
FAIL.

## Engines (configure through the engine MCP; details in the references)

- **Godot 4.6/4.7**: actions through `input_map_manage` (new-action dead zone 0.2, `ui_*` 0.5);
  `Input.get_vector()` is a scaled radial dead zone without an outer zone; rebind with
  `InputMap.action_erase_events`/`action_add_event`, persist with `ConfigFile` in `user://`.
  Camera: `SpringArm3D` + `Camera3D` nodes (Camera3D `fov` is vertical, default 75° ≈ 107.5°
  horizontal at 16:9). Phantom Camera (MIT) only with the user's approval.
- **Unity 6**: Input System — gamepad sticks carry `StickDeadzone` (0.125/0.925) by default;
  `PerformInteractiveRebinding()` (dispose it) + `SaveBindingOverridesAsJson()`; control schemes.
  Cinemachine 3: `CinemachineCamera` + `CinemachineThirdPersonFollow` or `OrbitalFollow`,
  `CinemachineDeoccluder`/`Decollider`, `CinemachineInputAxisController`; Brain default blend
  is EaseInOut 2 s — set gameplay blends to 0.3–1 s.
- **Unreal 5.8**: Enhanced Input modifiers Dead Zone (Radial), Response Curve Exponential, FOV
  Scaling; triggers Hold/Tap; remap with Player Mappable Key Settings + Enhanced Input User
  Settings (`SaveSettings`). `SpringArmComponent` (arm 300 cm default) + `PlayerCameraManager`;
  Unreal FOV is horizontal.
