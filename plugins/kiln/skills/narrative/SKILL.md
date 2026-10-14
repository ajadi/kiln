---
name: narrative
description: "Narrative design for games — pillars and a beat map that serve the mechanics, quests as state machines, branching scope control, dialogue, choice and bark writing (trigger rules, cooldowns), dialogue system per engine with licences (Yarn Spinner, Ink, Godot Dialogue Manager, engine-native line tables), line IDs as localization keys, VO and temp VO, skippable subtitled cutscenes, environmental storytelling hand-off, measurable checks and dialogue_lint.py; Godot 4.6/4.7, Unity 6, Unreal 5.8 notes. Use when writing or reviewing story, quests, dialogue, barks, item/UI text or cinematics."
user-invocable: false
---

# Narrative

Story is delivered through play, around the 30-second loop and the places the player goes. Every
player-facing string is data with a stable ID; narrative work is judged with numbers and
playthroughs. Values marked (working) are starting points. LLM-generated NPC dialogue is the
opt-in `kiln:llm-npc` skill; plurals, fonts and translation pipelines are in `kiln:localization`.

## Workflow and checkpoints

1. **Brief** `design/narrative/brief.md`: logline (1 sentence), one world rule that changes play,
   protagonist want vs need, opposing force, tone (3 adjectives + 2 reference works), 2–3
   narrative pillars, each tied to a `GAME.md` pillar and able to reject a feature. No story:
   write "No story: <why>" — barks, item and UI text are still needed.
2. **Beat map** `design/narrative/beats.md`, one row per beat: `beat | place | mechanic it teaches,
   motivates or rewards | delivery (environment, bark, dialogue, cutscene, item text) | length |
   skippable | flags set`. No beat without a place and a mechanic. The user approves brief + beat
   map (open question otherwise).
3. **Budget** `design/narrative/budget.md`: lines, words, VO minutes, structural branches,
   endings, languages — measured with `dialogue_lint.py` stats, re-measured at every lock.
4. **Write** in the chosen format with IDs; lint after every batch.
5. **Play** every branch and quest state in the running game; read subtitles on the target screen.
6. **Lock** for localization/VO: IDs frozen; a later change of meaning gets a new ID.

## Story serves mechanics

1. Delivery order: environment and barks > in-engine dialogue > cutscenes (only for what the
   player cannot do).
2. A beat that contradicts play (story says "hurry", the game offers 20 detours) is a design bug —
   an open question, not something to paper over with text.
3. The next goal is always known: objective line ≤ 60 chars (working); critical information in
   ≥ 2 channels (line + journal or marker).
4. ≤ 3 lines of exposition before the player acts again (working).

## Quests and missions

A quest is a state machine the writer specifies as data and gameplay code runs:
`inactive → offered → active:<stage> → completed | failed`. Each stage: objective text ID,
completion condition in game events/flags (names from `memory/registries.md`), marker target, fail
condition and recovery, flags set, reward. Template: `${CLAUDE_SKILL_DIR}/references/production.md`.

- Side quests 3–5 stages (working); each stage changes place, verb or stakes; complication at ~⅔.
- No soft locks: quest-critical NPCs are protected or have an alternative path; key items cannot
  be sold or lost; steps done out of order ("already have the item") are handled.
- Rewards and quest flags are set by game code from events, never parsed from dialogue text or LLM
  output.

## Branching scope control

Pick a structure (Ashwell's patterns): branch-and-bottleneck by default, hub-and-spoke for quest
hubs, gauntlet for linear games, time cave only for tiny scopes. A structural branch roughly
doubles everything downstream; prefer reactivity (a flag remembered in 1–3 later lines). Working
limits: ≤ 2 structural branch points per act, reconverge within the scene or the next, ≤ 3
endings unless endings are the product, a playthrough shows ≥ 60% of non-reactive lines, a
choice's consequence shows within ~3 minutes or it is labelled flavour.

## Dialogue writing

| Item | Rule |
|---|---|
| Line | one subtitle card: ≤ 80 visible chars (2 lines × 40, XAG 104), ≤ ~15 words, ≤ 6 s spoken (working) |
| Reading time | ≥ 0.3 s per word on screen (BBC: 160–180 wpm); cue timing via `kiln:accessibility` |
| Speaker | named whenever the speaker changes (XAG 104) |
| Choices | 2–4 options, ≤ 40 chars each; the option text predicts what is said and its tone; a leave/fallback option at every hub; never all options conditional |
| Localizable | placeholders for names/numbers, no sentence fragments glued in code, plural/gender via the localization skill |
| Barks | ≤ 6 words / ≤ 2 s; rules, cooldowns, priorities and pool sizes in `${CLAUDE_SKILL_DIR}/references/barks.md` |

## Dialogue system per engine

Details, licences with dates and the Kiln JSON/CSV formats:
`${CLAUDE_SKILL_DIR}/references/dialogue-systems.md`.

| Need | Choose |
|---|---|
| Barks, item/UI text, linear lines | engine-native Kiln line table (CSV/JSON → engine string tables), no plugin |
| Branching conversations, Godot (GDScript) | Godot Dialogue Manager v4 (MIT, Godot 4.6+) or Yarn Spinner GDScript (YSPL: credit required) |
| Branching, Unity 6 | Yarn Spinner for Unity (MIT) or ink-unity-integration (MIT) |
| Branching, Unreal 5.8 | engine-native (DataTables, Dialogue Waves) or Inkpot (MIT) / Yarn Spinner (YSPL, pre-release) |
| Prose-heavy, highly reactive text | Ink (MIT) + Ink-Localiser for line IDs |

A third-party editor plugin needs the user's approval (open question with options, licence and
credit duties), then a `memory/decisions.md` row. Dialogue sources (`.yarn`, `.ink`, `.dialogue`,
line-table CSV/JSON) are text the writer edits; engine resources and dialogue UI scenes change only
through the engine MCP.

## Line IDs and localization keys

One stable ID per player-facing string = localization key = VO file stem. Scheme
`<AREA|QUEST>_<SPEAKER>_<NNNN>`, uppercase, numbered in steps of 10, never reused. Yarn `#line:ID`,
Dialogue Manager `[ID:KEY]`, Ink `#id:` tags from Ink-Localiser, Kiln tables `id`. Each line
carries notes for translators and actors (context, addressee, tone, max chars). Short strings grow
most in translation (≤ 10 chars: 200–300%, > 70 chars: 130% — IBM via W3C).

## VO, cutscenes, environmental storytelling

Summaries; full procedures in `${CLAUDE_SKILL_DIR}/references/production.md`.

- **VO**: script export per line ID (speaker, text, direction, max duration, file `<ID>.wav`,
  status temp/final) → sound-designer. Temp VO is OS TTS or files marked `temp`; shipping
  synthetic voices falls under the `audio_generators` policy, the voice model's licence and actor
  consent for digital replicas.
- **Cutscenes**: in-engine, built in the editor through the MCP (AnimationPlayer / Timeline /
  Sequencer); skippable and pausable; skipping applies the end state explicitly; subtitles on by
  default or enabled before the first cinematic, caption categories (main dialogue, background
  chatter) toggled independently (XAG 104); control returns ≤ 0.5 s after the end (working).
- **Environment**: per place a vignette row (story, props, view bookmark, supporting note ID,
  light motivation) handed to the level designer; readable in a ≤ 3 s glance (working), never
  blocks navigation, optional unless a quest needs it.

## Checks

`python ${CLAUDE_SKILL_DIR}/scripts/dialogue_lint.py "dialogue/**/*.yarn" data/text --max-chars 80`
(Yarn, `kiln-dialogue/1` JSON, CSV line tables; `--help` lists the checks).

| Check | Target | Evidence |
|---|---|---|
| `dialogue_lint.py` | 0 errors; warnings explained | JSON report |
| Line / option length | ≤ 80 / ≤ 40 visible chars | lint |
| Subtitles on target screen | ≤ 2 lines × 40 chars, speaker named, ≥ 0.3 s/word | screenshot + `subtitle_check.py` (accessibility) |
| Branch coverage | every node and quest stage reached in the running game | coverage log |
| Quest save/load | mid-quest save restores stage, flags, journal | before/after state dump |
| Barks | no line repeated < 120 s, 0 unintended overlaps, info barks ≥ 90% of eligible triggers | bark log, 10 min combat |
| Cutscene skip | end state after skip = end state after watching; control ≤ 0.5 s | state dumps |
| VO | 0 voiced IDs without final file; 0 temp files in release; subtitles match takes | script vs files |

## Engine notes

- **Godot 4.6/4.7**: dialogue box/balloon is a scene the ui-designer builds through the MCP; options
  are a fixed pool of buttons in that scene or an instanced `option_button.tscn`. Line tables import
  as CSV translations (`keys,en,…`). Cutscenes: AnimationPlayer with property, method-call, audio
  and animation tracks; `seek(length, true)` skips method tracks and does not emit
  `animation_finished`, so the skip handler calls the end-state method itself. Temp VO:
  `DisplayServer.tts_speak` (starts on first call; `audio/general/text_to_speech` = at startup).
- **Unity 6 / Unreal 5.8**: string tables, Timeline signals / Sequencer event tracks (not relied
  on during a skip), Dialogue Waves — `${CLAUDE_SKILL_DIR}/references/production.md` § Engines.
