# Building UI in Godot 4.6/4.7 through Godot AI

All calls are `<tool>(op=..., params={...})` of the Godot AI MCP, in the open editor. Confirm a
class or property you have not used before with `api_manage` or `node_get_properties`. Save with
`scene_save` after each logical step. Scripts only reference nodes (`@onready`, `@export`); the
guard denies `Label.new()`, `Button.new()`, `*Container.new()` in scripts.

## 1. Project settings (`project_manage` op `settings_set`)

| key | value | note |
|---|---|---|
| `display/window/size/viewport_width` / `viewport_height` | 1920 / 1080 | design resolution |
| `display/window/stretch/mode` | `canvas_items` (pixel art: `viewport`) | Godot docs, multiple resolutions |
| `display/window/stretch/aspect` | `expand` | wider/taller screens add space; anchors keep UI at the edges |
| `display/window/stretch/scale_mode` | `fractional` (pixel art: `integer`, 4.2+) | |
| `gui/theme/custom` | `res://ui/theme/main.tres` | project-wide theme |
| `gui/theme/custom_font` | `res://assets/fonts/ui_main.tres` | FontFile/FontVariation with fallbacks |
| `gui/common/show_focus_state_on_pointer_event` | 1 (default: text inputs only) | 2 = always show focus |
| `gui/theme/default_theme_scale` | 1.0 | read at startup only; runtime UI scale: `get_tree().root.content_scale_factor` |

Localization and accessibility settings: see those skills. `gui/common/auto_focus_strategy`
(Balloon) exists only in the 4.8 development docs — do not rely on it in 4.6/4.7.

## 2. Theme (`theme_manage`)

1. `create` {path: "res://ui/theme/main.tres"}.
2. Font sizes, `set_font_size` {theme_path, class_name, name, value}: `Label`/`font_size`,
   `Button`/`font_size`, `LineEdit`, `OptionButton`, `CheckBox`, `CheckButton`, `PopupMenu`,
   `ItemList`, `TabBar`, `TooltipLabel`; `RichTextLabel`/`normal_font_size` and
   `bold_font_size`. Body height is ~0.92 × font size for Arial-like sans (measured: 24 px →
   22 px "Hgjpqy"); so font_size ≥ 20 for an 18 px body (PC), ≥ 29 for 26 px (TV). Measure your
   font with `ui_check.py text`.
3. Colours, `set_color`: `Label` `font_color`, `font_outline_color`, `font_shadow_color`;
   `Button` `font_color`, `font_hover_color`, `font_focus_color`, `font_pressed_color`,
   `font_hover_pressed_color`, `font_disabled_color`. Constants, `set_constant`: `Label`
   `outline_size`, `line_spacing`; `Button` `outline_size`, `h_separation`; containers
   `separation`; `MarginContainer` `margin_left/top/right/bottom`.
4. Styleboxes, `set_stylebox_flat` {theme_path, class_name, name, bg_color, border_color,
   border: {all}, corners: {all}, margins: {all}}: `Button` `normal`, `hover`, `pressed`,
   `hover_pressed`, `disabled`, **`focus`** (drawn on top of the state: transparent bg
   `#00000000`, border 3 px in a colour ≥ 3:1 against both the button and the screen background);
   `PanelContainer`/`panel`; `LineEdit` `normal`/`focus`; `ProgressBar` `background`/`fill`;
   `HSlider` `slider`, `grabber_area`, `grabber_area_highlight`. Artwork: `set_stylebox_texture`
   {texture_path, margins: {all: 8}, axis_stretch_horizontal: "tile_fit"} (9-slice; pixel art
   imported with nearest filter, no mipmaps).
5. Roles as type variations: give items to a custom type name (`set_font_size` on
   `HeaderLabel`/`font_size` = 48), **declare the variation** (`Theme.set_type_variation(
   "HeaderLabel", "Label")`) and set `theme_type_variation` = `HeaderLabel` on the node
   (`node_set_property`). Measured in 4.7.2 (g2): an undeclared variation is ignored and the
   node falls back to its class (a 56 px TitleLabel rendered at 30 px). `theme_manage` has no op
   to declare one: use a run-once `@tool` helper (a script with an exported `run` flag that
   loads the theme, calls `set_type_variation` for each role and saves it; attach it to a
   scratch node through the MCP, set the flag, then remove the node) or ask the user to add it in
   the Theme editor.
6. Fonts: `set_font` {theme_path, class_name, name: "font", font_path}. Fallback chain as a
   resource: `resource_manage` `create` {type: "FontVariation", properties: {base_font:
   "res://assets/fonts/Main.ttf", fallbacks: [CJK, Arabic, ... font paths]}, resource_path:
   "res://assets/fonts/ui_main.tres"} (`fallbacks` is a `Font` property; passing an array of
   paths through `create` is UNVERIFIED — check with `resource_manage load` afterwards). MSDF,
   hinting and antialiasing are import options of the font file (Import dock) — ask the user to
   set them if no MCP op covers it; do not hand-edit `.import` files.
7. Apply: project setting `gui/theme/custom`, or `apply` {node_path, theme_path} on a screen root.
8. One-off emphasis without touching the theme: `stylebox_override` {path, slot, patch}.

## 3. HUD scene

1. `scene_manage` `create` {path: "res://scenes/ui/hud.tscn", root_type: "CanvasLayer",
   root_name: "HUD"}.
2. `ui_manage` `build_layout` {parent_path: "/HUD", tree: ...} — one atomic, validated step:

```json
{"type": "Control", "name": "Root", "anchor_preset": "full_rect",
 "properties": {"mouse_filter": 2},
 "children": [
  {"type": "MarginContainer", "name": "Safe", "anchor_preset": "full_rect",
   "properties": {"mouse_filter": 2,
     "theme_override_constants/margin_left": 96, "theme_override_constants/margin_right": 96,
     "theme_override_constants/margin_top": 54, "theme_override_constants/margin_bottom": 54},
   "children": [
    {"type": "VBoxContainer", "name": "TopLeft",
     "properties": {"size_flags_horizontal": 0, "size_flags_vertical": 0},
     "children": [{"type": "Label", "name": "Objective",
                   "properties": {"text": "HUD_OBJECTIVE", "theme_type_variation": "HudLabel"}}]},
    {"type": "HBoxContainer", "name": "BottomRight",
     "properties": {"size_flags_horizontal": 8, "size_flags_vertical": 8},
     "children": [{"type": "Label", "name": "Ammo",
                   "properties": {"text": "30 / 90", "theme_type_variation": "HudValue"}}]}]}]}
```

   Values: `mouse_filter` 2 = IGNORE (the HUD does not eat clicks); size flags 0 = shrink begin,
   4 = center, 8 = shrink end; children of a MarginContainer share its rect, so size flags place
   them in corners. 96/54 px = 5% title-safe margins at 1920×1080; on phones a script sets the
   margins from `DisplayServer.get_display_safe_area()` (Android/iOS only).
3. `scene_save`; instance it: `node_create` {scene_path: "res://scenes/ui/hud.tscn",
   parent_path: "/Game"}.
4. Behaviour: `script_create` `res://scenes/ui/hud.gd` + `script_attach`; `@onready var ammo:
   Label = %Ammo` (mark unique names) and setters called from gameplay signals. Number formatting
   through the localization skill.
5. Vector HUD pieces (crosshair, radial gauges, corner brackets) without textures:
   `ui_manage` `draw_recipe` {path, ops: [...]} on a Control.

## 4. Menus, pause, dialogs

- Screen root: `Control` (full_rect) → background → `CenterContainer` → `VBoxContainer` of
  `Button`s whose `text` is a translation key. Build with `build_layout`, then wire signals:
  `signal_manage` `connect` {path: ".../Play", signal: "pressed", target: "/MainMenu",
  method: "_on_play_pressed"} (the method must exist in the attached script).
- Sliders (4.7.2, g2): `HSlider` ignores gamepad D-pad / stick left-right (keyboard arrows
  work; a synthesized `InputEventJoypadButton` for `ui_left` changes nothing), and the mouse wheel
  changes its value by default (`scrollable = true`), which fights a `ScrollContainer`. On every
  settings slider set `scrollable = false` and handle `ui_left` / `ui_right` in a `gui_input`
  hook that steps the value; give the slider its own focus stylebox (a grabber tint is not a
  focus ring — check it with `ui_check.py focus-diff`).
- Focus: `focus_mode` 2 (ALL) on interactive controls, 0 on decoration; explicit neighbours as
  NodePaths relative to the node: `node_set_property` {path: ".../Play", property:
  "focus_neighbor_top", value: "../Quit"} (wrap) and `focus_neighbor_bottom` "../Settings";
  `focus_next`/`focus_previous` for Tab order.
- Initial and restored focus (script): `@export var first_focus: Control`; on
  `visibility_changed` when visible → `first_focus.grab_focus.call_deferred()`; remember
  `get_viewport().gui_get_focus_owner()` before opening a submenu and refocus it on return.
- Dialog: an overlay `PanelContainer` scene; while it is open set the menu behind it to
  `focus_behavior_recursive` = 1 (DISABLED, 4.5+) so focus cannot leave the dialog; focus the
  safe button.
- Pause: pause menu under its own `CanvasLayer` with `process_mode` = 2 (WHEN_PAUSED); a script
  toggles `get_tree().paused`; action `pause` via `input_map_manage` `ensure_binding` (key
  `Escape`; `joy_button` 6 = Start).
- Repeated rows (key remapping, save slots, credits): a prepared scene (`remap_row.tscn`) built
  in the editor; place one instance per action in the editor (visible to the user) or
  `preload(...).instantiate()` at runtime.
- UI sounds: `audio_manage` `player_create` {parent_path, type: "1d"} + `player_set_playback`
  {bus: "UI"}; set the players' `process_mode` 3 (ALWAYS) so they play while paused; a script
  connects `get_viewport().gui_focus_changed` → focus tick and `pressed` → confirm.
- Motion: `create_tween()` in scripts (a Tween is not a node) with the durations of SKILL.md §7.

## 5. Verify before handoff

`project_run` → `game_manage` `get_ui_elements` (save the reply as JSON) → `ui_check.py layout`;
`editor_screenshot` {source: "game"} → `ui_check.py text`; focus trace per `measure.md`; one
`ui_check.py focus-diff` per focusable control type (button, slider, tab, toggle).
Re-run with pseudolocalization on and at 3840×2160 and 2560×1080 windows.

- `ui_check.py text` needs the element rects of the same run and window as the capture: rects
  from a headless SubViewport layout on a windowed PNG gave false small-text fails (13 px read
  for 22-23 px text in g2).
- With the editor minimized (the project rule while the user works) `editor_screenshot`
  `source: "viewport_2d"` returns a 2x2 black image. Without an on-screen run, check UI headless:
  a probe under `tests/probes/` instances the screen in a `SubViewport` sized per aspect
  (stretch-aware: 1920x1080, 1920x1200, 2560x1080, 1440x1080), dumps every visible Control's
  type, text and global rect (clip each to its `ScrollContainer`'s visible rect — rows scrolled
  out otherwise read as off-screen), records focus traces with real key events, and computes text
  heights from the font's glyph bounds and contrast from the theme colours; `ui_check.py layout`
  and `focus` take those dumps. The capture-based `text` check still needs one windowed run.
- A headless engine has no joypad A/B on `ui_accept` / `ui_cancel` unless the project's input
  map adds them; add them before probing gamepad flows.
