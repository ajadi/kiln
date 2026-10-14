---
name: accessibility
description: "Designing and accepting game accessibility - subtitles and captions (size, background, speaker labels, line length, timing), input remapping and hold/toggle, colour-blind support by redundant shapes and icons rather than filters, difficulty and assist options, motion-sickness options (FOV, shake, head bob, motion blur), text scaling, photosensitivity, audio-visual cue redundancy, screen readers and narration, per-engine how-to for Godot, Unity and Unreal, a checklist with the guideline source per item, and subtitle_check.py. Load when designing a mechanic, HUD, settings or audio cue, and at slice, polish and release gates."
user-invocable: false
---

# Accessibility

Accessibility is designed into systems from the first mechanic — an input layer that remaps, a
caption id on every important sound, a shape on every colour code, assists as multipliers in
the data — and checked by measurement and by playing with options at their extremes. Sources:
Xbox Accessibility Guidelines v3.2 (XAG), Game Accessibility Guidelines (GAG), BBC subtitle
guidelines, Netflix timed-text guide, WCAG 2.2. Sizes, contrast and focus rules for UI are in
the ui skill; flashes and scene contrast are measured by qa-readability.

- `${CLAUDE_SKILL_DIR}/scripts/subtitle_check.py` — line length, lines, duration, chars/s,
  overlaps, ALL CAPS, speaker labels on .srt/.vtt/.csv/.json subtitle data.
- `${CLAUDE_SKILL_DIR}/../ui/scripts/ui_check.py colours|simulate` — coded colours under CVD.
- `${CLAUDE_SKILL_DIR}/references/checklist.md` — read when planning features or at slice,
  polish and release gates: every item with its source and check.
- `${CLAUDE_SKILL_DIR}/references/engines.md` — read when implementing an option in Godot,
  Unity or Unreal.

## 1. Way of working

1. **Demand audit** per mechanic (design doc): what must be seen, heard, pressed (timing, holds,
   repeats, simultaneity, precision), remembered or read under time pressure. Each demand gets
   a mitigation from the checklist, recorded in `design/ACCESSIBILITY.md` with its source.
2. **Systems, not patches**: one input layer (remap, hold/toggle, sensitivity), one caption
   service fed by sound events, one cue registry (each gameplay cue: visual + audio + optional
   haptic), damage/timing values in data so assists are multipliers.
3. **Defaults** decide most players' experience: subtitles on or asked before the first line,
   readable text size, motion blur off, settings saved (GAG basic).
4. **Accept** with numbers (subtitle_check, ui_check, flash check) and extreme-option play:
   text 200%, all motion off, mono, muted, every action remapped, keyboard-only, max assists.

## 2. Subtitles and captions

| Item | Target | Source |
|---|---|---|
| Availability | on by default or offered before the first speech/cinematic | XAG 104, GAG |
| Size | ≥ 46 px @1080p available; scalable to ≥ 200% of minimum | GAG, XAG 104 |
| Background | solid plate behind text, opacity 0–100% player-set (default ~75%, working) | XAG 104 |
| Layout | ≤ 40 chars/line (Netflix English 42), ≤ 2 lines (3 exceptional), mixed case, sans-serif option, bottom, not over HUD | XAG 104, Netflix |
| Timing | 5/6–7 s per cue, ≤ 20 chars/s (17 for children); BBC 160–180 wpm ≈ 0.3 s/word | Netflix, BBC |
| Speakers | name on speaker change or after ≥ 1–2 min pause; colour only as an extra (BBC white, yellow, cyan, green) | XAG 104, BBC |
| Captions | important non-speech sounds, `[distant explosion]`, arrows `< >` or `(on radio)` for off-screen sources | XAG 104, BBC, Netflix |
| Chatter | barks that carry information are subtitled too | GAG |

Check: `subtitle_check.py` on the subtitle data; `ui_check.py text` on a capture for size and
contrast.

## 3. Input and motor

1. Every action remappable per device, any input to any action, prompts update; X/Y inversion
   separate per stick; sensitivity per axis ±50% of default (XAG 107).
2. Toggle alternative for every hold (aim, sprint, crouch, interact); no required mashing or
   QTE without an auto option; no required simultaneous presses (XAG 107, GAG).
3. All UI with single digital inputs and keyboard alone (XAG 107/112).
4. Timing-critical actions: game speed option or wider windows as an assist (GAG, XAG 108).
5. Haptics: intensity slider and off (GAG). Touch: 15 mm targets on phones, act on release
   (XAG 107).

Check: the playtester plays the slice with all actions remapped, holds as toggles, keyboard
only and gamepad only; no step needs two inputs at once.

## 4. Colour and vision

1. No cue by colour alone — important information uses at least two of text, symbol, colour,
   position, spatial audio, distinct sound, haptics, narration (XAG 103).
2. Fix the cue, not the screen: shapes/icons/patterns plus player-selectable colours for key
   elements (enemy/ally markers, rarity, crosshair). Full-screen filters are a blunt
   instrument — offer them only in addition (GAG). Safe default pair: orange vs blue with a
   lightness difference (GAG).
3. Text scaling to 200% and a 7:1 high-contrast mode (XAG 101/102, numbers in the ui skill).

Check: `ui_check.py colours` on the coded palette (ΔE ≥ 20 for protan, deutan, tritan —
working) and `simulate` on HUD captures; qa-readability colour-only check.

## 5. Motion and visual comfort

1. Options: FOV (3D), camera shake 0–100%, head bob 0–100%, motion blur off, depth of field,
   chromatic aberration, film grain, vignette, speed lines, automatic camera moves, UI motion
   (XAG 117, GAG). Defaults: motion blur off, shake ≤ 50% (working).
2. FOV slider names its axis. Horizontal 60–110° at 16:9 (working; XAG 117 example: up to 110°).
   vfov = 2·atan(tan(hfov/2)·H/W): 90° horizontal at 16:9 = 58.7° vertical. Godot `Camera3D.fov`
   is vertical with the default Keep Height aspect.
3. No camera roll or forced turns the player did not cause; stable horizon.

Check: with shake, bob and blur at 0, the camera transform does not change over 120 frames
while the player stands still (recorder), and screen effects toggle per option.

## 6. Photosensitivity

Fail when, in any 1 s, more than ~3 flashes cover ≥ ~20% of the screen (flash = ≥ 10%
luminance change with the darker state < 0.8; red flash: R/(R+G+B) ≥ 0.8), or a
high-contrast striped pattern covers ≥ ~20% of the screen (XAG 118, WCAG 2.3.1). Remove the
trigger rather than warn; add a "reduce flashing" option that dims muzzle flashes, explosions,
lightning and hit flashes. qa-readability measures the frame sequence with the option on and off.
Lightning sequences: plan them with `weather_check.py predict flash` and measure with its
`flashes` check (weather skill).

## 7. Audio-visual redundancy

1. Every critical sound has a visual (caption, directional indicator) and every critical visual
   telegraph has a distinct sound (XAG 103, GAG).
2. Volume per bus (Master, Music, SFX, Voice, Ambience, UI) and a mono toggle (GAG).
3. Check: complete the slice muted, and with the screen in grayscale; every attack telegraph is
   both visible and audible (qa-audio + qa-readability).

## 8. Difficulty, assists, cognition

1. ≥ 4 presets incl. story-first, changeable any time without penalty, named by what they do,
   plus granular assists (aim assist, game speed, damage taken, skip) (XAG 108, GAG).
2. Pause anywhere, cutscenes included (XAG 108); text at the player's pace; objective and
   control reminders on demand; practice without failure (GAG).

## 9. Narration and screen readers

Menus announce label, role, value and position ("Music volume, slider, 52%, 3 of 8"); speech
interrupts on focus change; rate adjustable (XAG 106). Godot 4.5+: AccessKit screen-reader
support for Controls (`accessibility_name`, `accessibility_description`, `accessibility_live`)
and `DisplayServer.tts_speak` for self-voicing; Unity 6.3+: Accessibility module (Narrator,
VoiceOver, TalkBack); Unreal: UNVERIFIED. Check: title → settings → change a volume → back with
Windows Narrator, every focus announced.
