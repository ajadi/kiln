# Accessibility checklist

Use at the slice gate (all **core** items), polish and release (all items that apply). Each row
names its source and a check that can be run in the game. Copy the table into
`design/ACCESSIBILITY.md`, mark each row `yes / no / n.a.` with the evidence path.

Sources: XAG = Xbox Accessibility Guidelines v3.2 (number = guideline); GAG = Game
Accessibility Guidelines (B basic, I intermediate, A advanced); WCAG = WCAG 2.2; BBC = BBC
subtitle guidelines; NFX = Netflix timed-text style guide.

## Text and UI (numbers in the ui skill)

| # | Item | Check | Source | Core |
|---|---|---|---|---|
| T1 | Body text ≥ 18 px @1080p PC, ≥ 26 px console/TV, 2× at 4K | `ui_check.py text` | XAG 101 | yes |
| T2 | Text scales to 200% without losing content | captures at 200%, `ui_check.py layout` 0 off-screen | XAG 101, GAG A | yes |
| T3 | Contrast 4.5:1 (large 3:1) on the worst background | `ui_check.py text` | XAG 102, GAG B | yes |
| T4 | High-contrast mode 7:1 | `ui_check.py text --min-contrast 7` | XAG 102 | no |
| T5 | Sans-serif option, sentence case option, left-aligned blocks | inspect settings and captures | XAG 101 | no |
| T6 | Visible focus on every background, focus never lost | `ui_check.py focus` | XAG 113 | yes |
| T7 | All UI usable with keyboard alone and digital gamepad alone | focus trace per screen, both devices | XAG 107/112, GAG B | yes |
| T8 | Linear menus wrap; Back always goes up; route to main menu everywhere | focus trace with `--expect-wrap`; flow walk | XAG 112 | yes |
| T9 | Destructive actions confirm, safe option focused | flow walk | XAG 115 | yes |
| T10 | Game starts without navigating several menu levels | count confirms from launch to play (≤ 2, working) | GAG B | yes |
| T11 | Settings saved and restored after restart | change, restart, compare | GAG B | yes |
| T12 | UI scale / HUD resize | captures at 75% and 150% | GAG I | no |

## Subtitles and captions

| # | Item | Check | Source | Core |
|---|---|---|---|---|
| S1 | Subtitles for all important speech, on or offered before the first line | first-launch walk | XAG 104, GAG B/I | yes |
| S2 | ≤ 40 chars per line, ≤ 2 lines | `subtitle_check.py` | XAG 104, GAG B | yes |
| S3 | 5/6–7 s per cue, ≤ 20 chars/s | `subtitle_check.py` | NFX | yes |
| S4 | Size option reaching ≥ 46 px @1080p, ≥ 200% of minimum | `ui_check.py text` on a capture | GAG B, XAG 104 | yes |
| S5 | Background plate, opacity 0–100% | capture at 0/50/100% | XAG 104 | yes |
| S6 | Speaker names on change / after 1–2 min | `subtitle_check.py --speakers-need-labels` | XAG 104, GAG I | yes |
| S7 | Captions for important non-speech sounds with direction for off-screen | review caption list vs sound event list | XAG 104, GAG I | yes |
| S8 | Subtitles for supplementary speech (barks, chatter) | subtitle coverage of bark tables | GAG I | no |
| S9 | Presentation customisable (size, background, colour) | settings walk | GAG I | no |
| S10 | Background noise kept low under speech | qa-audio ducking measurement | GAG I | no |

## Input and motor

| # | Item | Check | Source | Core |
|---|---|---|---|---|
| M1 | Remap every action per device, any input to any action | remap all, play slice | XAG 107, GAG B | yes |
| M2 | Prompts, tutorials and glyphs follow remapping and device | captures after remap | XAG 107 | yes |
| M3 | Sensitivity per axis, ±50% of default at least | settings range | XAG 107, GAG B | yes |
| M4 | X/Y inversion separately per stick | settings walk | XAG 107 | yes |
| M5 | Toggle alternative for every hold | play with toggles | XAG 107, GAG I | yes |
| M6 | No required mashing/QTE, no required simultaneous presses | design audit + playtest | XAG 107, GAG I | yes |
| M7 | Game speed or timing assists | timing windows measured at each setting | GAG B, XAG 108 | no |
| M8 | Haptics slider and off | settings walk | GAG B | yes |
| M9 | More than one input device; PC windowed mode | launch tests | GAG I | no |
| M10 | Touch targets 15 mm phone / 24 mm tablet, act on release | `ui_check.py layout --min-target` | XAG 107, GAG B | n.a. unless touch |
| M11 | Interactive elements that need accuracy stay still | design audit | GAG I | no |

## Vision and colour

| # | Item | Check | Source | Core |
|---|---|---|---|---|
| V1 | No information by colour alone; ≥ 2 channels for important cues | cue registry audit + grayscale capture | XAG 103, GAG B | yes |
| V2 | Coded colours distinct under CVD | `ui_check.py colours` ΔE ≥ 20 (working) | GAG B | yes |
| V3 | Player-selectable colours for key markers and crosshair | settings walk | XAG 103, GAG I | no |
| V4 | FOV default fits the viewing distance; FOV adjustable (3D) | settings + capture at min/max | GAG B/I, XAG 117 | yes (3D) |
| V5 | Essential temporary information inside the eye-line | captures: within ~20% of screen centre or near the character (working) | GAG I | yes |
| V6 | Option to hide background movement / non-essential effects | settings walk | GAG I, XAG 117 | no |
| V7 | Screen reader / narration for menus | Narrator walk | XAG 106, GAG A | no |

## Motion and photosensitivity

| # | Item | Check | Source | Core |
|---|---|---|---|---|
| P1 | No flashes > ~3/s over ≥ ~20% of screen; no red flashes; no large high-contrast stripes | qa-readability frame analysis | XAG 118, WCAG 2.3.1, GAG B | yes |
| P2 | Reduce-flashing option dims transient flashes | frame analysis with option on | XAG 118 | no |
| P3 | Camera shake, head bob, motion blur adjustable/off | camera delta = 0 with options off (recorder) | XAG 117, GAG I | yes |
| P4 | Other screen effects (DoF, CA, grain, vignette, speed lines) toggles | captures | XAG 117 | no |
| P5 | Pause/hide auto-updating and moving content | settings walk | XAG 117 | no |

## Hearing and audio

| # | Item | Check | Source | Core |
|---|---|---|---|---|
| H1 | No essential information by sound alone | muted playthrough of the slice | GAG B, XAG 103 | yes |
| H2 | Separate volume per bus | settings walk + bus meters | GAG B | yes |
| H3 | Mono toggle | qa-audio channel correlation with mono on | GAG I | no |
| H4 | Directional visual indicator for off-screen threats/sounds | capture during off-screen attack | XAG 103, GAG I | yes (combat) |
| H5 | Distinct sounds per key event | qa-audio similarity check | GAG I | no |

## Difficulty, time and cognition

| # | Item | Check | Source | Core |
|---|---|---|---|---|
| D1 | ≥ 4 presets incl. story-first, descriptive names | settings walk | XAG 108, GAG B | yes |
| D2 | Change difficulty any time without losing progress | change mid-level, state kept | XAG 108, GAG I | yes |
| D3 | Granular assists (aim assist, damage, speed, skip) | each assist measurable in game | XAG 108, GAG I | no |
| D4 | Pause anywhere incl. cutscenes (single player) | input test in each state | XAG 108 | yes |
| D5 | Text at the player's pace; no forced timers on reading | flow walk | GAG B, XAG 116 | yes |
| D6 | Objective and controls reminder during play | capture | GAG I | yes |
| D7 | Practice without failure / interactive tutorial | design audit | GAG B/I | no |
| D8 | Autosave and manual save | save tests | GAG I | no |
| D9 | Accessibility features listed in game and on the store page | release checklist | GAG B, XAG 121 | release |
