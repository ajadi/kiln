---
name: ui
description: "Game UI and HUD - HUD types and information hierarchy, safe areas, text/icon/target sizes for 1080p, 4K and TV, contrast, menu flow (title, pause, results, restart), settings menu contents, keyboard/gamepad focus, themes, fonts and CJK fallbacks, resolution scaling, pixel-art UI, motion timing, UI sounds, ui_check.py measurements, and building UI through Godot AI, MCP for Unity and the Unreal MCP. Load for any HUD, menu, settings, theme, font or UI review task."
user-invocable: false
---

# Game UI and HUD

UI is built in the editor through the engine MCP (scene_first: no `Label.new()`; repeated rows are
prepared scenes/templates), styled by one theme, and accepted by measurement. Values marked
(working) are starting points. Accessibility options: skill `kiln:accessibility`; strings and
fonts per language: `kiln:localization`.

- `${extensionPath}${/}skills${/}ui/scripts/ui_check.py` — `focus-diff` (focus ring size and contrast from a
  focused / unfocused capture pair), `layout`, `text` (body px + contrast from a
  capture), `focus` (reachability trace), `colours` (CVD), `simulate`. Pillow + numpy.
- `${extensionPath}${/}skills${/}ui/references/godot.md` — read when building UI through Godot AI.
- `${extensionPath}${/}skills${/}ui/references/unity-unreal.md` — read when engine=unity or engine=unreal.
- `${extensionPath}${/}skills${/}ui/references/flow-and-settings.md` — read when building title, pause,
  results or settings screens (settings list, defaults, persistence, remapping).
- `${extensionPath}${/}skills${/}ui/references/measure.md` — read when accepting UI (dumps, traces, latency).

## 1. Workflow and checkpoints

1. **Inputs**: platforms and viewing distance (desk ~60 cm / TV ~3 m), input devices, languages,
   art bible fonts and palette.
2. **Information inventory**: per item the decision it serves, urgency, change rate, channel
   (HUD, diegetic, audio, haptic), priority 1–3. Cut what changes no decision.
3. **Grey wireframes** at 1920×1080 of the HUD and every screen; flow graph.
4. **Style system first**: theme with fonts, size scale, colour tokens and every interactive
   state (normal, hover, focus, pressed, disabled); then screens, built through the MCP.
5. **Self-check** with ui_check at 1080p, 4K, 16:10, 21:9 and the minimum window,
   pseudolocalized, text at 200%, keyboard-only and gamepad-only; hand off to qa-readability.

## 2. HUD

| Type (Fagerholt & Lorentzon 2009) | In the fiction / in 3D space | Use |
|---|---|---|
| non-diegetic | no / no | precise numbers, crosshair, ammo, timers |
| diegetic | yes / yes | ammo counter on the gun, cockpit gauges — must still meet size and contrast |
| spatial | no / yes | markers, outlines, nameplates, damage numbers in the world |
| meta | yes / no | blood splatter, cracked visor, screen tint for health |

1. Show only what changes the next decision; priority 1 is always readable at a glance.
2. Temporary critical information near the eye-line (crosshair, character), not in far corners
   (GAG). Stable information in fixed corners inside the safe area.
3. Bars for glance, numbers for precision; both for health/ammo when exact values matter.
4. No colour-only codes: every colour also has shape, icon, position or text (XAG 103).
5. Off-screen threats and important sounds get a directional indicator (XAG 103/104).
6. Contextual fading is fine; options keep critical HUD always on, scale it, hide it.
7. Meta effects (vignette, tint, shake) never hide what they announce and obey the motion/flash
   options.

## 3. Numbers

| Item | Target | Source |
|---|---|---|
| Text body height (descender to ascender) | PC 18 px @1080p, 36 @4K; console/TV 26 px, 52 @4K; TV floor 28 px | XAG 101; GAG |
| Large text (3:1 allowed) | PC ≥ 36 px, console ≥ 52 px @1080p | XAG 102 |
| Text and icon contrast | 4.5:1; large text/elements and disabled text 3:1; control borders 3:1 (WCAG 1.4.11); high-contrast mode 7:1; against the worst part of the background | XAG 102 |
| Text scaling | to 200% without losing content; sentence case option; sans-serif option | XAG 101 |
| Text blocks > 2 lines | ≤ 80 chars per line (40 CJK), line spacing ≥ 1.5, left-aligned | XAG 101 |
| Safe area | interactive and text content inside 90% title safe (5% margins: 96 × 54 px @1080p); platform safe area on phones | SMPTE ST 2046-1; UE default 0.9 |
| Pointer/touch targets | ≥ 24 px (44 recommended) @1080p; phones 15 mm | WCAG 2.5.8/2.5.5; XAG 107 |
| Critical HUD icons | ≥ 32 px PC, ≥ 48 px TV @1080p (working) | — |
| Focus indicator | visible on every background, ≥ 2 px, 3:1 against the unfocused state | XAG 113; WCAG 2.4.13 |
| Input → visible response | ≤ 100 ms (6 frames @60 fps) | Nielsen 0.1 s |
| Screen transitions | 150–300 ms, input accepted during them; progress shown after 1 s of loading | Material 3 durations; Nielsen |

## 4. Menu flow

Title → game ⇄ pause → result → again/next, every transition working before art.

- **Title**: Continue/Play focused by default; launch to gameplay ≤ 2 confirms (working; GAG:
  start without navigating multiple menu levels). Settings reachable before first play.
- **Pause**: opens within one frame, stops game time, Resume focused; Settings, Restart, Quit to
  title. Pausable everywhere in single player, cutscenes included (XAG 108).
- **Results / game over**: outcome, 1–3 key stats, Retry focused; restart ≤ 2 inputs.
- **Back** (B/Esc) always goes up one level; prompts and tab buttons identical on every screen;
  a route to the main menu from every submenu (XAG 112).
- **Destructive actions** (quit unsaved, overwrite save, reset settings) ask once, safe option
  focused (XAG 115).
- **Settings** apply immediately, persist across restarts (GAG), reset per tab; display-mode
  changes revert after 15 s unless confirmed (working).

## 5. Focus and navigation

1. Every screen works with keyboard alone, gamepad digital input alone, and mouse/touch (XAG 112,
   107); one input per action, no chords.
2. Focus is set when a screen opens, restored when returning to it, and trapped inside an open
   dialog (XAG 113).
3. Explicit neighbours for any layout that is not a single row/column; linear lists wrap, grids
   do not (XAG 112). The input that moved focus moves it back.
4. Focus state differs from hover; disabled and hidden controls never take focus.
5. Button glyphs follow the last-used device; remapping updates every prompt (XAG 107).

## 6. Style system, fonts, scaling

- One theme for the game; roles as type variations (Title, Header, Body, Caption, HudValue,
  Prompt), not per-node overrides; colour tokens from the art bible.
- Fonts: dynamic TTF/OTF; MSDF for display text that scales or animates (pixel range ≥ 2×
  outline); fallbacks primary → Noto Sans CJK → Arabic/Hebrew/Thai/Devanagari → symbols; each
  font's licence recorded (OFL preferred).
- Resolution: design at 1920×1080, scale with the window (Godot `canvas_items` + `expand`),
  layout by anchors and containers — nothing positioned in absolute pixels against screen edges;
  wide screens add space, not stretched UI. UI scale option 75–150% (working) plus text size.
- Pixel art: `viewport` stretch, integer scale, pixel fonts at integer multiples, nearest filter,
  no MSDF, subpixel positioning off; body height in base pixels ≥ min px × base height / 1080
  (640×360: 6 px PC, 9 px TV). Text scaling needs integer steps or a high-resolution text layer.

## 7. Motion and sound

- State change on the next frame; hover/focus 50–100 ms, press 100–150 ms, panels/screens
  200–300 ms, ease-out on enter (Material 3 short1–medium2). Pause and back are instant; a
  reduce-UI-motion option skips animation (XAG 117).
- UI sounds: focus move, confirm, back, denied, slider step, tab, pause open/close,
  notification — each distinct (GAG), on a UI bus that keeps playing while paused.

## 8. Acceptance (qa-readability measures; the builder self-checks)

| Check | How | Pass |
|---|---|---|
| Text size and contrast | `ui_check.py text` on captures @1080p and @4K, every screen and HUD state | every text element passes its profile |
| Layout | `ui_check.py layout` per screen at 16:9, 16:10, 21:9, minimum window | 0 off-screen, outside safe area, overlapping or undersized targets |
| Focus | `ui_check.py focus` trace per screen, keyboard and gamepad | initial focus, every interactive reached, no focus loss, lists wrap |
| Focus visible | `ui_check.py focus-diff` per focusable type (button, slider, tab, toggle) | ring ≥ 2 px around the control, ≥ 3:1 focused vs unfocused (WCAG 2.2 SC 2.4.13); a tint alone fails |
| Colour codes | `ui_check.py colours` on the coded palette + look for the second channel | ΔE ≥ 20 under all CVD types (working); no colour-only code |
| Localization | pseudolocalization on (+30%, accents), `loc_check.py` | no clipped text, verdict pass |
| Latency | frames from input to visible change (`references/measure.md`) | ≤ 100 ms; transitions ≤ 300 ms |
| Flow | title → game → pause → result → again, keyboard-only then gamepad-only | no dead end, ≤ 2 confirms to gameplay |

## Engines (details in the references)

- **Godot 4.6/4.7**: `CanvasLayer` → full-rect `Control` → `MarginContainer`; one `Theme` as
  `gui/theme/custom`; `ui_manage`, `theme_manage`, `node_set_property`, `signal_manage`.
- **Unity 6**: UI Toolkit (UXML/USS) via `manage_ui`; uGUI for world-lit, shader or Timeline UI.
- **Unreal 5.8**: UMG + CommonUI via `UMGToolSet`; `USafeZone` around the HUD.
