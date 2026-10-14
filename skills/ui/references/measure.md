# Measuring UI in the running game

Save every dump and capture under `production/captures/<task>/ui/` (review roles may write
there) and name it `<screen>_<state>_<WxH>`. Run `ui_check.py` from Bash.

## Godot (Godot AI)

1. `project_run`; wait for `editor_state` `game_status.status == "live"`.
2. Viewport size in UI coordinates: `editor_manage` `game_eval`
   `return Engine.get_main_loop().root.get_visible_rect().size`.
3. Element dump: `game_manage` `get_ui_elements` {include_hidden: false} → save the reply as
   JSON. It lists path, type, visible, disabled, text, rect, global_rect (no focus or font data).
4. Capture: `editor_screenshot` {source: "game"} or `game_eval`
   `Engine.get_main_loop().root.get_texture().get_image().save_png(ProjectSettings.globalize_path("res://production/captures/<task>/ui/<name>.png"))`.
5. `python ui_check.py layout <dump> --viewport WxH` and
   `python ui_check.py text <png> <dump> --viewport WxH --profile pc|console`.

### Focus trace (keyboard or gamepad)

`game_manage` `input_action` sets action state without an InputEvent, so GUI focus does not move
with it. Use real events: either `game_manage` `input_key` {key: "Down"} / `input_gamepad`
{control: "button", index: 12} (D-pad down; 11 up, 13 left, 14 right) followed by a
`game_eval` that returns the focus owner, or one `game_eval` loop:

```gdscript
var tree: SceneTree = Engine.get_main_loop()
var vp := tree.root
var steps := []
var f := vp.gui_get_focus_owner()
steps.append({"input": null, "focus": str(f.get_path()) if f else ""})
for key in [KEY_DOWN, KEY_DOWN, KEY_DOWN, KEY_DOWN, KEY_DOWN, KEY_UP, KEY_RIGHT, KEY_LEFT]:
    for pressed in [true, false]:
        var ev := InputEventKey.new()
        ev.keycode = key
        ev.physical_keycode = key
        ev.pressed = pressed
        Input.parse_input_event(ev)
        await tree.process_frame
    f = vp.gui_get_focus_owner()
    steps.append({"input": OS.get_keycode_string(key), "focus": str(f.get_path()) if f else ""})
return steps
```

Gamepad: the same with `InputEventJoypadButton` (`button_index` 11–14). Send N+1 moves along
each list so wrap-around shows. Save the result as JSON →
`python ui_check.py focus trace.json --elements dump.json [--expect-wrap]`. Repeat per screen
and after opening and closing each dialog (focus restored? trapped while open?).

### Latency (input → first visible change)

```gdscript
var tree: SceneTree = Engine.get_main_loop()
var vp := tree.root
await RenderingServer.frame_post_draw
var before := vp.get_texture().get_image().get_data()
var t0 := Time.get_ticks_usec()
var ev := InputEventKey.new()
ev.keycode = KEY_ENTER
ev.physical_keycode = KEY_ENTER
ev.pressed = true
Input.parse_input_event(ev)
var first := -1.0
var last := -1.0
for i in 60:
    await RenderingServer.frame_post_draw
    var now := vp.get_texture().get_image().get_data()
    if now != before:
        last = (Time.get_ticks_usec() - t0) / 1000.0
        if first < 0.0:
            first = last
    before = now
return {"first_change_ms": first, "settled_ms": last}
```

Pass: `first_change_ms` ≤ 100; `settled_ms` ≤ 300 for screen transitions (animated
backgrounds keep changing — measure on a static screen or crop). Pause: first change ≤ 1 frame
after the frame the input arrived.

## Unity (MCP for Unity)

Play with `manage_editor`; `manage_ui` `get_visual_tree` (UI Toolkit) for element names and
bounds — field names of its reply are UNVERIFIED, map them to {path, type, text, rect} before
`ui_check.py`; `manage_ui` `render_ui` (play mode: call twice) or `manage_camera` screenshot for
captures. uGUI rects: `find_gameobjects` + RectTransform world corners through a probe component
(`#if UNITY_EDITOR || DEVELOPMENT_BUILD`). Focus: a probe logs
`EventSystem.current.currentSelectedGameObject` (uGUI) or `panel.focusController.focusedElement`
(UI Toolkit) after each injected navigation event.

## Unreal (Epic Unreal MCP)

PIE with `EditorAppToolset` StartPIE; captures with CaptureViewport / the Kiln toolset
`highres_shot`; widget rects and focus via a Kiln toolset probe that walks the viewport's
widgets and writes `{path, type, text, rect}` JSON (`GetCachedGeometry().GetAbsolutePosition()`
/ `GetAbsoluteSize()` divided by the DPI scale) and the focused widget after each `inject_input`.

## Report

Per screen and resolution: layout verdict and violations, text table (path, body px at 1080p,
contrast, verdict), focus verdict (unreachable, lost, wrap), latency numbers, pseudolocalized
capture checked, CVD simulation of HUD captures looked at. Verdict line first, numbers before
judgement; the builder's own numbers are not acceptance.
