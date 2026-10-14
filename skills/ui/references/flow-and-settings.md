# Menu flow and settings menu

## Flow graph (slice minimum)

```
boot → [splash ≤ 3 s, skippable] → Title ──Play/Continue──▶ Game ◀──Resume── Pause
         Title ── Settings ◀──────────────────────────────────────────── Pause ── Settings
         Game ── win/lose ──▶ Results ── Retry ──▶ Game (same level, ≤ 2 inputs)
                                    └── Next ──▶ Game (next)   └── Quit ──▶ Title
         Pause ── Restart (confirm) ──▶ Game        Pause ── Quit to title (confirm if unsaved)
```

- First launch: language (if more than one; default = OS locale), then subtitles on/off and size
  shown before any speech (XAG 104: subtitles on by default or offered before the first
  cinematic; GAG: before any sound), then Title.
- Every screen: one default-focused action, Back = previous screen, prompts in the same place.
- Loading: progress after 1 s; tips readable at their own pace; never auto-advance text the
  player must read (GAG: progress text prompts at own pace).
- Quit to desktop exists on PC (title and pause), not on consoles where the platform owns it.

## Settings contents

Tabs: Gameplay · Controls · Display · Graphics · Audio · Accessibility · Language. Every
option: label, current value, a one-line description of its effect (XAG 108 for difficulty), and
works with keyboard, gamepad and mouse. Changes apply immediately (preview) and persist.

| Tab | Option | Range / default | Source |
|---|---|---|---|
| Gameplay | difficulty preset | ≥ 4 presets incl. story-first; changeable any time, descriptive names | XAG 108 |
| Gameplay | assists | aim assist, game speed (e.g. 50–100%), damage taken, skip puzzle/combat | XAG 108, GAG |
| Controls | remap | every action, per device (keyboard/mouse, gamepad), any key to any action; prompts and tutorials update | XAG 107 |
| Controls | sensitivity | per axis, ±50% of default at least; separate aim/look | XAG 107 |
| Controls | invert | X and Y, per stick, separately | XAG 107 |
| Controls | hold/toggle | per hold action (aim, sprint, crouch, interact) | XAG 107 |
| Controls | dead zone, vibration | inner/outer dead zone; vibration 0–100% and off | GAG haptics |
| Display | window mode, resolution, monitor, vsync, frame cap | confirm/revert within 15 s for mode changes (working) | — |
| Display | brightness/gamma | calibration screen with a "barely visible" reference image | — |
| Display | FOV (3D) | slider with the axis named (horizontal at 16:9 or vertical) | GAG, XAG 117 |
| Display | UI scale, HUD opacity, HUD elements on/off | 75–150% (working), 0–100% | GAG resize interfaces |
| Graphics | preset + key toggles | render scale/upscaler, shadows, effects, motion blur (off by default, working) | XAG 117 |
| Audio | volume per bus | Master, Music, SFX, Voice/Dialogue, Ambience, UI; 0–100, 0 = mute | GAG separate volumes |
| Audio | mono, dynamic range (night mode), subtitles-with-audio-cues | toggles | GAG stereo/mono |
| Accessibility | subtitles + captions, size, background opacity, speaker names | see accessibility skill | XAG 104 |
| Accessibility | text size, high contrast, colour options, motion and flash options | see accessibility skill | XAG 101/102/117/118 |
| Language | text language; voice language separately | default = OS locale if supported | — |

Defaults matter: most players never open settings. Subtitles on (working), motion blur off,
camera shake moderate, sensible FOV for the platform.

## Persistence and application

- One settings file in the user data folder (Godot `user://settings.cfg` via `ConfigFile`;
  Unity `Application.persistentDataPath`; Unreal `GameUserSettings` + a SaveGame or config
  section). Store primitives (key codes, button indices, floats), not serialized engine
  objects; version the file (`version = 2`) and migrate.
- Load before the first frame that shows UI (an autoload / GameInstance subsystem), apply, then
  show Title — no flash of default values.
- Volume: slider value v in 0–1 → bus gain `linear_to_db(v)` (Godot), `20·log10(v)` (Unity
  mixer), clamp at −80 dB / mute at 0.
- Remapping (Godot): `InputMap.action_erase_events(action)` + `InputMap.action_add_event(action,
  event)`; the remap row listens in `_input` for the next key/button, rejects the pause and
  UI-back actions as targets if the design requires it, warns on conflicts (same input on two
  actions in one context) and offers swap. Save `physical_keycode` for keyboard (layout
  independent), button index / axis + sign for gamepad. Unity: Input System
  `PerformInteractiveRebinding()` + `SaveBindingOverridesAsJson()`. Unreal: Enhanced Input user
  settings with player-mappable keys.
- Prompts/glyphs: one lookup (action → current binding → glyph for the last-used device); every
  prompt reads it, so remapping updates tutorials too (XAG 107).
- Reset to defaults per tab, with a confirm.
