# Building UI in Unity 6 and Unreal 5.8 through their MCP servers

## Unity 6 (MCP for Unity)

**Which system.** Unity's comparison page (6.0) recommends uGUI for runtime UI that is positioned and
lit in the 3D world, uses custom shaders/materials, is animated with Animation Clips/Timeline,
or is referenced directly from MonoBehaviours; UI Toolkit for multi-resolution menus and HUD in
UI-heavy projects (global styles, flexbox layout, textureless rendering). World-space UI Toolkit
panels exist since 6.2, and the 6.2 page lists world-space UI and VR under UI Toolkit. Kiln default: UI Toolkit for menus and HUD, uGUI only for the cases above.

**Tools.** `manage_ui` lives in the tool group `ui`, off by default:
`manage_tools(action="activate", group="ui")`. Actions: `list`, `create` (UXML/USS file with
`contents`), `read`, `update`, `delete`, `link_stylesheet`, `create_panel_settings`,
`update_panel_settings`, `attach_ui_document` (UIDocument on a GameObject), `detach_ui_document`,
`get_visual_tree`, `modify_visual_element` (text, classes, inline style, enabled, visible,
tooltip), `render_ui` (PNG capture; in play mode call twice: queue, then read). Always write
`<ui:Style>` with the `ui:` prefix or UI Builder cannot open the file.

UI Toolkit recipe:
1. `create_panel_settings` with settings {scaleMode: "ScaleWithScreenSize",
   referenceResolution: {width: 1920, height: 1080}, screenMatchMode: "MatchWidthOrHeight",
   match: 1 (landscape: follow height, working), themeStyleSheet: "Assets/_Project/UI/Game.tss"}.
2. Theme: one TSS importing the USS files; colour, size and spacing as USS variables
   (`--color-accent`, `--font-size-body: 20px`); states with pseudo-classes `:hover`, `:focus`,
   `:active`, `:disabled` — the `:focus` rule draws a ≥ 2 px border with ≥ 3:1 contrast.
3. Screens as UXML (one per screen, templates for repeated rows via `<ui:Template>`/
   `<ui:Instance>`); text attributes hold placeholders only — real text comes from Localization
   bindings (localization skill).
4. `attach_ui_document` to a GameObject created with `manage_gameobject`; behaviour in a C#
   component that queries elements (`root.Q<Button>("Play")`) and registers callbacks.
   Repeated rows at runtime: `rowTemplate.Instantiate()` from a serialized VisualTreeAsset (a
   prepared asset), not `new Button()`.
5. Focus: elements focusable by default only if they are controls; order = depth-first tree
   order, `tabIndex` > 0 first, < 0 skipped (Unity manual, focus order). Initial focus with
   `element.Focus()` when the screen opens; directional overrides with a
   `NavigationMoveEvent` callback. Gamepad/keyboard reach UI Toolkit through the EventSystem's
   `InputSystemUIInputModule` (actions shared with uGUI).
6. Text: TextCore font assets (SDF) with fallback font assets per script; Advanced Text
   Generator (Project Settings → UI Toolkit, HarfBuzz/ICU) for RTL and complex scripts —
   dynamic font assets only.

uGUI recipe: `manage_gameobject` create a Canvas object with components Canvas, CanvasScaler,
GraphicRaycaster (`manage_components`: CanvasScaler `uiScaleMode` Scale With Screen Size,
reference 1920×1080, match 1), TextMeshProUGUI for text (SDF), an EventSystem with
`InputSystemUIInputModule` and `firstSelectedGameObject`; `Selectable.navigation` Explicit with
`selectOnUp/Down/Left/Right` for non-trivial layouts; repeated rows as prefabs
(`manage_prefabs`). The guard denies `AddComponent<Canvas|Image|Text|TextMeshProUGUI>` in scripts.

Settings plumbing: AudioMixer exposed parameters per bus (`mixer.SetFloat("MusicVol",
Mathf.Log10(Mathf.Max(v, 0.0001f)) * 20f)`), Input System rebinding
(`PerformInteractiveRebinding()`, `SaveBindingOverridesAsJson()` /
`LoadBindingOverridesFromJson()`), `Screen.SetResolution`, `QualitySettings.SetQualityLevel`,
`Screen.safeArea` for phones.

Evidence: `manage_editor` play → `manage_ui` `get_visual_tree` (rects) → `ui_check.py layout`;
`manage_ui` `render_ui` or `manage_camera` screenshot → `ui_check.py text`.

## Unreal 5.8 (Epic Unreal MCP)

**Which system.** UMG widget blueprints for every screen; **CommonUI** for menus that must work
with gamepad: set Game Viewport Client Class = `CommonGameViewportClient`, input data asset
(`CommonUIInputData`: universal Click and Back actions) and per-platform
`CommonInputBaseControllerData` (glyphs) in Project Settings → Game → Common Input Settings;
screens derive from `CommonActivatableWidget` and live in `CommonActivatableWidgetStack`s
(push = open, deactivate = back); buttons from `CommonButtonBase`; text styles as
`CommonTextStyle` / button styles as `CommonButtonStyle` data assets (the theme). CommonUI
routes input to the top activatable widget and sets focus via `GetDesiredFocusTarget`; Enhanced
Input integration for CommonUI is UNVERIFIED for 5.8 — check the plugin settings.

**Tools** (`call_tool` with toolset `UMGToolSet`; names from Epic's 5.8 toolset dump, confirm
with `describe_toolset` first): `CreateWidgetBlueprint` {folderPath "/Game/UI/HUD", assetName
"WBP_HUD", parentClass "/Script/UMG.UserWidget" or a CommonActivatableWidget subclass},
`AddWidget` {widgetBlueprint, widgetClass, parentWidget, childIndex} → returns widget and Slot
refs; then `ObjectTools.list_properties` / `set_properties` on the widget (text, font size,
style) and on the Slot (anchors, offsets, alignment, padding); `WrapWidgets`, `MoveWidget`,
`RenameWidget`, `ToggleWidgetAsVariable` (for `BindWidget` in C++), `BindToEventProperty`
(e.g. OnClicked → graph), `ReplaceWidgetWithTemplate`, `CompileWidgetBlueprint`, read back with
`GetWidgets` / `GetWidgetDescription`. String tables: `StringTableTools` (`create`, `set_entry`,
`import_file`, `list_keys`).

Layout: root `CanvasPanel` → `SafeZone` (applies the platform/title safe zone) → `Overlay` /
boxes; anchors for screen edges; `ScaleBox` only for art, never for text. DPI: Project Settings →
User Interface → DPI Scaling Rule Shortest Side with the curve at 1080 → 1.0. Debug the safe
zone with `r.DebugSafeZone.Mode 1` and `r.DebugSafeZone.TitleRatio 0.9` (console; read-only
roles may not run console commands except the safe list in the engine profile — the builder
runs these). Widget navigation: per-widget Navigation rules (Escape, Explicit, Wrap, Stop,
Custom); CommonUI handles most of it.

Settings plumbing: `UGameUserSettings` (resolution, window mode, vsync, scalability, frame
limit), Sound Classes/Mixes or submix volumes per bus, Enhanced Input user settings with player
mappable keys for remapping, `UWidgetBlueprintLibrary::SetColorVisionDeficiencyType` for a CVD
simulation/correction toggle (accessibility skill).

Evidence: `EditorAppToolset` StartPIE → CaptureViewport → `ui_check.py text`; widget rects from
`SlateInspectorToolset` Snapshot (UNVERIFIED that PIE game widgets appear in it) or a Kiln
toolset probe that dumps `GetCachedGeometry()` of each widget as JSON for `ui_check.py layout`.
