# Implementing accessibility options per engine

How to build each option of the accessibility SKILL in Godot 4.6/4.7, Unity 6 and Unreal 5.8.
Screens, rows, plates and overlays are built in the open editor through the engine MCP and
styled by the theme (ui skill: `references/godot.md`, `references/unity-unreal.md`,
`references/flow-and-settings.md` for the settings list and persistence); scripts read settings
and drive existing nodes. Input internals (rebinding APIs, glyphs, dead zones) live in
controls-camera `references/input.md` §6–10, camera rigs in `references/camera.md` §8 — not
repeated here. UNVERIFIED = not confirmed in a primary source.

## 1. One settings service, many consumers

| Option (SKILL §) | Key (example) | Consumer |
|---|---|---|
| remap, hold/toggle (§3) | `input.bindings`, `input.toggle.aim` | input layer |
| subtitles (§2) | `subs.on`, `subs.size` 100–200%, `subs.plate` 0–1, `subs.speakers` | caption service + subtitle view |
| text / UI scale (§4) | `ui.text_scale` 100–200%, `ui.scale` 75–150% | theme / panel scaling |
| colour (§4) | `colour.profile`, `colour.markers` | palette resource, shader globals |
| motion (§5) | `cam.fov_h`, `cam.shake`, `cam.bob` 0–1, `fx.motion_blur`, `fx.dof`, `fx.grain` … | camera rig, post-process |
| flashing (§6) | `fx.flash_scale` 0–1 | effect shaders and lights |
| audio (§7) | bus volumes, `audio.mono` | mixer |
| difficulty (§8) | `game.preset`, assist multipliers, `game.speed` | gameplay data |

Godot: the `Settings` autoload (`ConfigFile` at `user://settings.cfg`, `version` key, signal
`changed(key)`). Unity: a settings service loaded before the first scene, JSON in
`Application.persistentDataPath`, C# event `Changed`. Unreal: a `UGameUserSettings` subclass for
video/audio plus a `ULocalPlayerSaveGame` for the rest, broadcast by a `UGameInstanceSubsystem`.
Every consumer applies its value on load and on change — no restart.

## 2. Godot 4.6/4.7

- **Remap**: `InputMap` rebinding and `user://input.cfg` per input.md §10; the controls screen
  holds prepared `remap_row.tscn` instances (ui godot.md §4); defaults via `input_map_manage`.
- **Hold/toggle**: in the input layer, per action: toggle mode flips `aiming` on
  `Input.is_action_just_pressed(&"aim")`, hold mode sets it from `Input.is_action_pressed(&"aim")`;
  clear toggled states on pause, death, cutscene and device change.
- **Subtitles**: `scenes/ui/subtitles.tscn` built with `ui_manage build_layout`: `CanvasLayer`
  (above the HUD) → full-rect `Control` → `MarginContainer` (title-safe, bottom) → `VBoxContainer`
  (bottom-aligned) → `PanelContainer` "Plate" (type variation `SubtitlePlate`) →
  `RichTextLabel` "Line" (`SubtitleText`, `fit_content`, autowrap smart, BBCode for speaker
  colour as an extra). The script sets `add_theme_font_size_override(&"normal_font_size",
  base * scale)` and a duplicated plate `StyleBoxFlat` with `bg_color.a` via
  `add_theme_stylebox_override`. Lines come from data (`data/subtitles/*.csv`, keys through
  `tr()`); captions from a caption id on each important sound event; off-screen sources get
  `<`/`>` from the source direction relative to the camera.
- **Text scaling**: UI scale = `get_tree().root.content_scale_factor`; text size = prepared themes
  (`main.tres`, `main_150.tres`, `main_200.tres` from `theme_manage`, same styleboxes, larger
  sizes) assigned to `get_tree().root.theme` — a Window's theme applies to all its Controls.
  Layouts reflow because they are containers with autowrap; check with `ui_check.py layout` at 200%.
- **Colour**: a palette resource (`data/ui/palette_default.tres`, `_deutan`, `_protan`,
  `_tritan`) for HUD and markers; world markers and outlines read global shader uniforms
  (declared in Project Settings → Shader Globals via `project_manage`, set with
  `RenderingServer.global_shader_parameter_set(&"ally_colour", c)`); each faction/rarity also has
  an icon or shape. A full-screen filter, if offered, is a prepared `ColorRect` + shader on its
  own `CanvasLayer`, hidden by default.
- **Motion**: `Camera3D.fov` is vertical with the default Keep Height —
  `fov = rad_to_deg(2 * atan(tan(deg_to_rad(h) / 2) / aspect))`; shake and bob amplitudes on the
  rig's `Shake`/`Bob` nodes × settings (camera.md §8); depth of field via
  `CameraAttributesPractical.dof_blur_far_enabled`/`near`; motion blur, grain, vignette and
  chromatic aberration are not built in — they are project shaders or compositor effects on
  prepared nodes, toggled by `visible`/`enabled`. First-launch default from
  `DisplayServer.accessibility_should_reduce_animation()` (returns int; values UNVERIFIED).
- **Flashing**: a `flash_scale` shader global and an exported energy multiplier in effect scenes.
- **Audio**: `AudioServer.set_bus_volume_db(i, linear_to_db(v))`; mono = `AudioEffectStereoEnhance`
  on Master with `pan_pullout` 0 ("downmix stereo to mono"), toggled with
  `AudioServer.set_bus_effect_enabled`.
- **Difficulty**: `data/difficulty/*.tres` presets (damage taken, enemy reaction, aim assist,
  timing windows); game speed `Engine.time_scale` (scales delta for timers, `_process` and
  `_physics_process`, not audio — `AudioServer.playback_speed_scale`; UI tweens
  `set_ignore_time_scale(true)`).
- **Screen reader** (4.5+, experimental): AccessKit exposes standard Controls; set
  `accessibility_name` on icon-only buttons and sliders, `accessibility_description` for hints,
  `accessibility_live` polite on objective/toast labels (all via `node_set_property`); project
  setting `accessibility/general/accessibility_support` default Auto (updates only while an
  assistive app is active); `DisplayServer.accessibility_screen_reader_active()`. Self-voicing:
  `DisplayServer.tts_speak(text, voice, volume, pitch, rate, id, interrupt = true)` with
  `audio/general/text_to_speech` on. Supported desktop platforms per export: UNVERIFIED.

## 3. Unity 6

- **Remap**: Input System `PerformInteractiveRebinding()` and
  `SaveBindingOverridesAsJson()` per input.md §10 (start from the package's "Rebinding UI"
  sample); rows are prepared UXML templates or prefabs.
- **Hold/toggle**: `aiming = toggleAim ? aiming ^ aim.WasPressedThisFrame() : aim.IsPressed()`;
  Hold interaction default 0.4 s — keep holds short and optional.
- **Subtitles**: no engine subtitle system (UNVERIFIED that none ships in 6.x): `Subtitles.uxml`
  (plate `VisualElement` + `Label`) via `manage_ui`, `UIDocument` on a scene object; size from a
  USS variable, plate alpha via `style.backgroundColor`; lines from Localization string tables or
  a CSV `TextAsset`, cued by Timeline Signals and audio events.
- **Text scaling**: USS variables per text role on `:root` (`--font-size-body`); root classes
  `.text-150`/`.text-200` redefine them (`root.EnableInClassList("text-200", true)`); UI scale
  via `PanelSettings.scale`. uGUI: `CanvasScaler.scaleFactor` and per-role TMP sizes. Mobile
  default: `AccessibilitySettings.fontScale` (Android, iOS).
- **Colour**: palette ScriptableObject; `Shader.SetGlobalColor` for markers and outlines; USS
  classes for HUD colour profiles; icons per faction. Optional filter: a URP Full Screen Pass
  Renderer Feature with a correction material, off by default.
- **Motion**: `Camera.fieldOfView` is vertical — `Camera.HorizontalToVerticalFieldOfView(h,
  aspect)`; shake = `CinemachineImpulseListener` Gain × setting; URP Volume overrides
  (`MotionBlur`, `DepthOfField`, `ChromaticAberration`, `FilmGrain`, `Vignette`, `LensDistortion`):
  `volume.profile.TryGet(out MotionBlur mb); mb.active = on;` (`profile` is a per-instance copy,
  `sharedProfile` edits the asset).
- **Audio**: AudioMixer exposed parameters (ui unity-unreal.md); mono via
  `AudioSettings.GetConfiguration()` → `speakerMode = AudioSpeakerMode.Mono` →
  `AudioSettings.Reset(config)` (can stall; effect on playing sources UNVERIFIED).
- **Difficulty**: ScriptableObject presets; `Time.timeScale` for game speed, UI on unscaled time.
- **Screen reader**: Accessibility module (built-in, on by default): `AccessibilityHierarchy`,
  `AccessibilityNode` (`label`, `role`, `state`, `frame`, `invoked`), assigned to
  `AssistiveSupport.activeHierarchy` and re-assigned on `screenReaderStatusChanged`. TalkBack and
  iOS VoiceOver since 6.0; Windows Narrator and macOS VoiceOver since 6.3. Not automatic for UI
  Toolkit or uGUI: one node per control, frame = `worldBound × panel.scaledPixelsPerPoint`
  updated on `GeometryChangedEvent`; inspect with Window > Accessibility > Hierarchy Viewer.

## 4. Unreal 5.8

- **Remap**: Enhanced Input User Settings (`MapPlayerKey`, `SaveSettings`, key profiles) per
  input.md §10; CommonUI rows via `UMGToolSet`.
- **Hold/toggle**: bind `Started`/`Completed` for hold; for toggle flip state on `Started`
  according to the setting; the Hold trigger's 1.0 s default threshold is too long — lower it.
- **Subtitles**: the Subtitles and Closed Captions plugin (Experimental): assets typed Subtitle /
  ClosedCaption / AudioDescription, queued with `USubtitlesSubsystem::QueueSubtitle`, widget
  class and per-type font, colour and opacity in Project Settings → Game → Subtitles and Closed
  Captions; it is meant to supersede the legacy Sound Wave cues (`FSubtitleCue`,
  `UGameplayStatics::SetSubtitlesEnabled`). Point it at a `WBP_Subtitles` built with `UMGToolSet`
  whose size and plate opacity read the settings (binding the plugin widget to runtime sizes:
  UNVERIFIED).
- **Text scaling**: `UUserInterfaceSettings::ApplicationScale` ("optional application scale on
  top of the custom scaling rules") for UI scale — changing it at runtime UNVERIFIED; text-only
  scaling through CommonTextStyle tiers (Body, Body150, Body200) chosen from the setting.
- **Colour**: markers through a Material Parameter Collection
  (`UKismetMaterialLibrary::SetVectorParameterValue`) and UMG styles, plus icons/outlines.
  `UWidgetBlueprintLibrary::SetColorVisionDeficiencyType(Type, Severity, bCorrectDeficiency,
  bShowCorrectionWithDeficiency)` corrects or simulates for the whole window — a filter: offer it
  only in addition; simulation mode is a QA tool.
- **Motion**: `UCameraComponent::FieldOfView` is horizontal; shakes via
  `StartCameraShake(Class, Scale × setting)`; post-process settings `MotionBlurAmount` 0,
  depth of field, `SceneFringeIntensity` (chromatic aberration), `FilmGrainIntensity`,
  `VignetteIntensity` on the camera's PostProcessSettings with overrides enabled.
- **Audio**: Sound Class / submix volumes per bus; mono toggle: UNVERIFIED.
- **Difficulty**: Data Asset presets; `UGameplayStatics::SetGlobalTimeDilation` for game speed.
- **Screen reader** (Experimental): `Accessibility.Enable=1` in the console-variable section of
  `DefaultEngine.ini` (through the Unreal MCP, not by hand); Windows (docs name NVDA and JAWS) and
  iOS VoiceOver; Text Block, Editable Text Box, Slider, Button, Checkbox accessible by default;
  per widget Accessible Behavior (Not Accessible, Auto, Summary, Custom, Tool Tip) and Can
  Children Be Accessible. Plugins Text To Speech (English only), Screen Reader, Slate Screen
  Reader. Windows Narrator and gamepad-driven narration: UNVERIFIED.

## 5. Verify in the running game

1. Extremes pass: text 200%, subtitles largest with plate 100%, all motion options off, mono,
   muted, every action remapped and held actions as toggles, keyboard-only, gamepad-only, max
   assists — captures under `production/captures/<task>/a11y_*.png`.
2. Numbers: `subtitle_check.py` on the subtitle data; `ui_check.py text` on captures at each
   subtitle size; `ui_check.py colours` on each palette profile; camera transform constant over
   120 frames with shake and bob at 0 (recorder/probe).
3. Persistence: change every option, restart, compare.
4. Screen reader walk title → settings → change a volume → back: Narrator (Godot, Unity 6.3+),
   NVDA (Unreal); every focus announced with label, role and value.

## Sources

1. Godot 4.7 class reference: Control (accessibility_*), DisplayServer (tts_*,
   accessibility_*), ProjectSettings, Window, AudioEffectStereoEnhance; Godot 4.5 release notes.
2. Unity 6.3 manual, "Get started with screen reader support"; Unity 6 scripting reference:
   AssistiveSupport, AccessibilitySettings, PanelSettings, Random, AudioSettings.Reset.
3. Unity Input System manual, Actions/Bindings (interactive rebinding, saving overrides).
4. Unreal 5.8 docs: "Supporting Screen Readers", "Blind Accessibility Features Overview",
   "Subtitles and Closed Captions Plugin"; API: UEnhancedInputUserSettings,
   UUserInterfaceSettings, UWidgetBlueprintLibrary::SetColorVisionDeficiencyType.
5. Kiln: accessibility SKILL and checklist (XAG, GAG, BBC, Netflix numbers), ui and
   controls-camera references.
