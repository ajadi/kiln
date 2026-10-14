# Input reference

Values marked (working) are starting points; [U] = not confirmed in a primary source.

## 1. Default layouts

Gamepad names use Xbox positions (A bottom, B right, X left, Y top). Keep a layout per genre,
then let the player remap every action, including pause/Esc (XAG 107).

| Genre | Keyboard / mouse | Gamepad |
|---|---|---|
| FPS | WASD move, mouse look, LMB fire, RMB aim, R reload, Space jump, C or Ctrl crouch, Shift sprint, E interact, F or V melee, G grenade, Q ability, 1–4 / wheel weapons, Tab map/score, Esc pause | LS move, RS look, RT fire, LT aim, A jump, B crouch/slide, X reload + hold interact, Y swap weapon, LB/RB grenade + ability, L3 sprint, R3 melee (CoD/Apex) or B/RB melee (Halo family), View map, Menu pause |
| Third-person shooter | as FPS; Space or Shift also cover/roll; scroll or middle mouse swaps shoulder | as FPS; A cover/roll/sprint, click R3 swaps shoulder |
| Third-person melee | WASD, mouse camera, LMB light, RMB heavy or block, Space dodge, Shift sprint, Q/middle mouse lock-on | LS, RS camera, X light, Y heavy (or RB/RT), B dodge (hold sprint), LB/LT block/parry, R3 lock-on, RS flick switches target |
| Platformer | arrows/WASD, Space jump, J/K or Z/X actions | LS or D-pad, A jump, X attack/run, B action, RT/RB dash |
| Twin-stick / top-down | WASD move, mouse aim, LMB fire, RMB alt, Space dash | LS move, RS aim (fire on deflection or RT), LT alt, A/RB dash |
| Racing | W/S or arrows throttle/brake, A/D steer, Space handbrake | RT throttle, LT brake, LS steer, A handbrake, B/X look back |
| RTS / tactics | LMB select/box, RMB command, WASD/edge pan, Ctrl+n groups | virtual cursor or radial menus; LB/RB cycle units, A command, B cancel |
| Menus | arrows/Tab, Enter confirm, Esc back, mouse | A confirm, B back (Nintendo: right button confirms; PlayStation 5 uses Cross everywhere) |

Rules: one verb per button per context; context-sensitive buttons resolve by priority (interact
> reload when both are valid) and show what will happen; no essential action on stick clicks
only (XAG 107 allows them if remappable).

## 2. Dead zones, curves, triggers

```
m = |v|                                   # raw stick vector v
if m < inner: out = 0
else:        t = min((m - inner) / (outer - inner), 1); out = v/m * t      # scaled radial
look:  out = out/|out| * |out|^gamma       # gamma 1.5–2.5; movement gamma 1
```

| Item | Value | Source |
|---|---|---|
| Inner dead zone | 0.10–0.20, start 0.15; slider 0–0.3 | Sutphin; XInput |
| XInput constants | left 7849/32767 ≈ 0.24, right 8689/32767 ≈ 0.27, trigger 30/255 ≈ 0.12 | Microsoft XInput docs |
| Outer threshold | 0.90–0.95 (stick gates are not round; full speed must be reachable at every angle) | Unity StickDeadzone max 0.925 |
| Engine defaults | Godot action 0.2 (`ui_*` 0.5), radial scaled, no outer zone; Unity 0.125/0.925 scaled; Unreal Dead Zone modifier Radial, 0.2/1.0 | engine source/docs |
| Axial | per-axis; snaps to cardinals — only for menus and 4/8-way movement | Sutphin |
| Trigger | dead 0.05–0.12; digital press 0.5, release 0.375 | XInput, Unity |
| Analog-as-digital | press 0.5, release 0.375–0.4 (hysteresis) | Unity defaults |
| Menu repeat | 0.4–0.5 s first repeat, then 8–12 Hz (working) | OS key repeat practice |

Notes: never take max(|x|, |y|) as magnitude (square output, faster diagonals); clamp |v| to 1
before the curve; apply the dead zone to the 2D vector before splitting into actions; drift on
worn controllers needs the inner slider, not a bigger default.

## 3. Look speed and mouse

- Gamepad: angular rate = curve(stick) × max speed. Separate yaw and pitch speeds (°/s);
  competitive shooters expose yaw 160–500°/s and pitch below yaw [U]; default ~180–250°/s yaw
  (working). Turn boost (extra yaw when held at ≥ 0.95 for 0.1–0.2 s, ramp 0.2–0.4 s) helps
  180° turns; make it optional.
- Decelerate pitch before the pitch limit instead of stopping dead (Nesky #47).
- Mouse: degrees per count × sensitivity; never multiply mouse delta by frame time; raw input,
  no smoothing, no acceleration by default; show sensitivity as a number, offer cm/360 if the
  audience cares.
- Zoom/ADS: multiply by tan(fov_zoom/2)/tan(fov_hip/2) (Unreal FOV Scaling modifier does this),
  plus a per-zoom slider.
- Gyro aim (motion-sensing pads, Steam Input): add as an optional aim source with its own
  sensitivity; Godot 4.7 exposes `Input.get_joy_gyroscope()` (experimental).

## 4. Buffering and priority

- Buffer one press per action: 0.10–0.20 s for attacks/dodges, 0.10–0.15 s for jumps
  (feel-numbers); consumed once; cleared on death, menu, cutscene or a state change that makes
  it invalid.
- Cancel windows: allow dodge/jump to cancel recovery frames from a defined frame, not
  anywhere; record windows per move in the design table.
- Simultaneous presses in the same tick resolve by a fixed priority list (defence > movement >
  attack, working).

## 5. Aim assist

Components (Insomniac R3 talk; Halo): **slowdown/friction** (lower look rate near a target),
**rotation/adhesion/magnetism** (camera follows a moving target while the player aims),
**bullet bending/auto-aim** (shot direction bends toward the target), **snap** on ADS.

| Parameter | Start (working) | Note |
|---|---|---|
| Target zone | target's angular radius + 1–2° (inner); outer cone 3–8° [U] | scale with distance; none beyond weapon range |
| Slowdown | ×0.5–0.7 look rate in the zone (30–50% less) | ramp in/out across the zone edge |
| Rotation strength | 0.3–0.6 × target's angular velocity | Apex: 0.6 console, PC controller 0.4 → 0.3, −25% (Season 22) |
| Rotation gate | only while look or move input > dead zone | idle stick must never track |
| Bullet bending | ≤ 1–2° or hitbox ×1.1–1.3 for hit tests [U] | never through cover; LOS test first |
| ADS snap | ≤ 5–10° cone, ≤ 0.15–0.25 s, single-player/casual only | off in PvP |

Rules: analog stick and gyro only — mouse never; in crossplay PvP use input-based matchmaking or
reduce strength; option off/low/standard; per weapon class; prefer the target nearest the
reticle in angle, then distance; ignore targets behind cover; no target switching while one is
tracked unless input moves away. Acceptance: scripted strafing target at 10/20/40 m — assist
raises time-on-target without moving the camera when the stick is idle (0° over 1 s), and never
locks through walls.

## 6. Remapping and persistence

- Remap actions, not raw buttons; every action, both devices, invert X/Y per stick,
  sensitivity per axis, Esc included (XAG 107).
- Conflict: offer swap with the conflicting action or warn; reserved system buttons
  (Guide/PS/Home) are not bindable. Reset per action and reset all.
- Keyboard: bind physical keys so WASD stays in place on AZERTY/QWERTZ; show the label of the
  user's layout.
- Save per user with a `version` field and per-device sections; load before the first frame;
  unknown or invalid entries fall back to defaults with a log line, never a crash.
- Prompts, tutorials and the controls screen read the current binding through one function.

## 7. Device switching, glyphs, Steam Input

- Accept all devices simultaneously; track the last meaningful device per player; switch the
  glyph set within one frame; hysteresis against stick drift and mouse jitter (§ rule 9 in SKILL).
- Glyph families: Xbox, PlayStation (Cross/Circle/Square/Triangle), Nintendo (A/B swapped in
  position; A right), Steam Deck, keyboard/mouse. Choose by controller type, not by the
  bottom-button index alone; label by position semantics (south/east/west/north).
- Steam Input on: the game sees a virtual Xbox pad, so device names lie. Use the reported
  controller type (`ISteamInput::GetInputTypeForHandle`) and Steam glyphs
  (`GetGlyphPNGForActionOrigin` / `GetGlyphSVGForActionOrigin`); re-read origins each time a prompt is shown. Godot's
  `Input.get_joy_info()` may include `steam_input_index`.
- Steam Deck Verified: "On-screen glyphs must match the inputs being used"; no mouse/keyboard
  glyphs when they are not the active input; text entry opens the on-screen keyboard; the default
  controller configuration reaches all content.

## 8. Hold vs toggle

- Defaults: aim hold (toggle option), crouch toggle on gamepad, sprint toggle or auto-sprint
  option, interact hold 0.3–0.6 s only for destructive or committing actions (working).
- Hold-to-confirm ≤ 1 s and always a press alternative; XAG 107 flags holds of 2–3 s and more.
- Mashing/QTE: offer hold or auto alternatives (Gears 5, The Long Dark examples in XAG 107).

## 9. Vibration

- Two motors: low-frequency "strong" for impacts/explosions, high-frequency "weak" for
  texture (fire rate, engine). Start values (working): shot 40–80 ms weak 0.3–0.6; hit taken
  100–200 ms strong 0.5–0.8; explosion 200–500 ms decaying; never continuous at > 0.5 during
  idle gameplay.
- Scale by a user slider; off switch; stop on pause, menu, focus loss and controller change.

## 10. Engine specifics

**Godot 4.6/4.7**
- Actions through `input_map_manage` (registry in `memory/registries.md`). `InputMap.add_action`
  default dead zone 0.2; `ui_*` and toggle actions 0.5 (engine source `input_map.h`).
- `Input.get_vector(neg_x, pos_x, neg_y, pos_y, deadzone = -1)` averages the four actions' dead
  zones, returns 0 inside, rescales (dead zone, 1) → (0, 1), clamps length > 1 — a scaled radial
  dead zone. Apply the look curve after it. `get_action_strength` per axis gives a square shape.
- Joypad input runs through SDL3 on desktop since 4.5; `Input.get_joy_name`, `get_joy_info`
  (`vendor_id`, `product_id`, `raw_name`, `steam_input_index`) choose glyphs;
  `joy_connection_changed(device, connected)` for hot-plug. Controllers send input to unfocused
  windows — ignore input while unfocused (4.7+: `input_devices/joypads/ignore_joypad_on_unfocused_application`; 4.6: in script). Joypad buttons do not echo; make menu repeat yourself.
- Rebind: `InputMap.action_erase_events` + `action_add_event` with `InputEventKey`
  (`physical_keycode`), `InputEventMouseButton`, `InputEventJoypadButton`,
  `InputEventJoypadMotion` (`axis`, `axis_value` sign). Persist with `ConfigFile` at
  `user://input.cfg` (or `ResourceSaver` of the events). Show labels with
  `DisplayServer.keyboard_get_label_from_physical()`.
- Device tracking: `_input(event)`; `InputEventJoypadMotion` counts only past the threshold.
- Vibration: `Input.start_joy_vibration(device, weak, strong, duration)` (duration 0 ≈ 65 s);
  `stop_joy_vibration`; LED `set_joy_light` (4.7 docs).
- Rebinding UI is a scene (Control nodes built through the MCP); the script fills labels.

**Unity 6 (Input System 1.x)**
- Project-wide actions asset; control schemes "Keyboard&Mouse" and "Gamepad"; read actions in
  `Update`.
- Processors: `StickDeadzone(min, max)` (defaults 0.125/0.925, scaled radial with outer clamp,
  present on `Gamepad.leftStick/rightStick` by default), `AxisDeadzone`, `NormalizeVector2`,
  `ScaleVector2`, `InvertVector2`. Interactions: Press (press point 0.5, release 0.75 × press),
  Hold (0.4 s), Tap (0.2 s), SlowTap (0.5 s), MultiTap (2 taps); defaults live in
  `InputSystem.settings`.
- Rebinding: `action.PerformInteractiveRebinding().WithControlsExcluding("<Mouse>/position")
  .WithCancelingThrough("<Keyboard>/escape").OnMatchWaitForAnother(0.1f).Start()`; disable the
  action while rebinding; `Dispose()` the operation; persist
  `actions.SaveBindingOverridesAsJson()` → `LoadBindingOverridesFromJson()`.
- Prompts: `GetBindingDisplayString(index, out deviceLayout, out controlPath)` → sprite lookup
  per layout; device switching via `PlayerInput.onControlsChanged` or `InputUser.onChange`.
- Haptics: `Gamepad.SetMotorSpeeds(low, high)`, `PauseHaptics`, `ResumeHaptics`,
  `ResetHaptics`.

**Unreal 5.8 (Enhanced Input)**
- Input Actions (Axis2D for move/look) in Input Mapping Contexts added through
  `UEnhancedInputLocalPlayerSubsystem` with priorities per context.
- Modifiers: Dead Zone (Lower/Upper threshold, Type Axial/Radial/UnscaledRadial — use Radial),
  Response Curve Exponential / User Defined, Scalar, Negate, Swizzle, FOV Scaling, Smooth (adds
  latency — keep off look). Triggers: Down, Pressed, Released, Hold (HoldTimeThreshold 1.0 s
  default — lower it), Hold And Release, Tap, Pulse, Chorded Action, Combo.
- Remap: Player Mappable Key Settings on actions; Enhanced Input User Settings (project setting
  on) → `MapPlayerKey` / `UnMapPlayerKey`, `ApplySettings`, `SaveSettings`/`AsyncSaveSettings`
  (slot `EnhancedInputUserSettings`); key profiles per player.
- Glyphs: CommonUI/CommonInput — current input type (mouse+keyboard, gamepad, touch), controller
  data assets per platform map keys to icons, action widgets show the bound key.
- Debug: `showdebug enhancedinput`; injection `Input.+key Gamepad_Left2D X=0.7 Y=0.5`.
- Force feedback assets + `ClientPlayForceFeedback`; stop on pause.

## Sources

Sutphin "Doing thumbstick dead zones right"; Microsoft XInput docs; Godot input source and docs;
Unity Input System source (InputSettings, StickDeadzoneProcessor, Gamepad) and manual; Unreal
Enhanced Input docs; Weihs, "Techniques for Building Aim Assist in Console Shooters" (GDC 2013);
Halopedia aim assist; Respawn Season 22 aim-assist change (press); XAG 107 and 117; Steamworks
Steam Input and Steam Deck compatibility docs; Nesky "50 Game Camera Mistakes" (GDC 2014).
