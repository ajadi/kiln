# Narrative production: quests, VO, cutscenes, environmental storytelling, engines

## Quest spec (`design/narrative/quests/<QID>.md`)

```markdown
# Q01 The Cellar Key
giver: SMITH | area: village | serves pillar: <GAME.md pillar> | mechanic: <M0x>
| stage | objective text ID (≤ 60 chars) | complete when (event / flag) | marker | fail when → recovery | flags set | reward |
|---|---|---|---|---|---|---|
| offered | Q01_OBJ_0010 Talk to the smith | dialogue Q01_SMITH_START finished | smith | — | q01_stage=1 | — |
| 1 | Q01_OBJ_0020 Clear the cellar | rats_killed(cellar) ≥ 6 | cellar door | player dies → stage kept, rats reset | q01_stage=2 | — |
| 2 | Q01_OBJ_0030 Return to the smith | dialogue Q01_SMITH_KEY finished | smith | smith dead → Q01_OBJ_0040 Take the key from the forge | q01_done=1 | cellar_key |
completed: q01_done=1, journal Q01_OBJ_0090 | failed: never (alternative path at stage 2)
soft-lock review: giver death ✓ alt path · key item not sellable ✓ · out-of-order (cellar cleared first) ✓ · save/load each stage ✓
```

Event and flag names come from `memory/registries.md`; the gameplay developer turns the table into
quest data resources through the engine MCP. Evidence per quest: a run in the game that reaches
every stage, a save/load at each stage with the journal text checked, and each alternative path.

## VO pipeline

1. **Lock** the script (IDs frozen). Export the VO script per line ID:
   `id,speaker,text,direction,context,addressee,intensity,max_s,file,status,take` with
   `file = <ID>.wav`, `status = temp | recorded | final`. Barks and efforts are in the same sheet.
2. **Character sheets** for casting: age, accent, energy, 3 sample lines from the script.
3. **Temp VO** (so timing, subtitles and lip-sync can be tested early), one of:
   - OS text-to-speech at runtime (Godot `DisplayServer.tts_speak`, Windows/macOS/Linux/Android/
     iOS/Web) — no files are shipped;
   - scratch recordings by the team, `status=temp`;
   - TTS-generated files: only when the manifest's `audio_generators` policy allows it, with a
     provenance file (tool, version, voice, licence). Licences differ per voice model, not just per
     engine: the original Piper engine is MIT (archived), its successor `piper1-gpl` is GPL-3.0, and
     each Piper voice has its own model-card licence. Hosted TTS services set commercial rights and
     training use per plan — read the current terms before any file is kept.
4. **Recording**: per character in batches; barks and efforts at each intensity; 2–3 takes of key
   lines (working); a pickup list for every changed line. Union actors (SAG-AFTRA Interactive Media
   Agreement 2025): informed consent with a reasonably specific description for any digital
   replica use; real-time generation from a replica is paid at a higher minimum (reported 7.5×
   scale). For non-union actors put the same consent into the contract.
5. **Delivery and import**: files named by ID per locale (`audio/vo/<locale>/<ID>.wav`); loudness
   and format targets from the sound designer's skill; imported and routed to the VO bus through
   the engine MCP; subtitles keyed by the same ID.
6. **Checks**: every voiced ID has a `final` file; 0 `temp` files in a release build; recorded
   duration ≤ `max_s`; the subtitle text matches the take (pickups update both).

## Cutscenes and in-engine cinematics

Common rules: built in the open editor through the engine MCP (cameras, markers, actors, audio and
the timeline/animation are scene content, not code); skippable at any time by a held input
(0.5–1.0 s with a visible indicator, working) or a confirm; pausable; subtitles with speaker names;
the skip handler applies the **end state explicitly** (flags, positions, spawned actors, music
state) through the same idempotent method the timeline calls at its end; ≤ 60–90 s each unless the
game is story-led (working); player control returns ≤ 0.5 s after the end; letterbox never covers
subtitles. Check: dump the game state after watching and after skipping at 10%, 50% and 90% — the
dumps must match.

## Engines

**Godot 4.6/4.7**
- Cutscene = a `Cutscene` node in the level scene with an AnimationPlayer, Camera3D(s), Marker3Ds
  and AudioStreamPlayers for VO. Tracks: camera transform and `current`, actor animation playback,
  audio (VO), method-call keys for subtitles (`show_line("ID")`) and gameplay events.
- Skip: `seek(current_animation_length, true)`; events between are skipped (method and audio
  tracks), and seeking to the end does not emit `animation_finished` — call the end-state method
  yourself. Pause: `pause()` on the AnimationPlayer and the VO players.
- Text: `tr()` / `TranslationServer`; CSV translations (`keys,en,…`) or PO; controls translate
  their text automatically when their auto-translate mode is on. OS TTS starts on the first TTS
  call (Godot 4.5+); `audio/general/text_to_speech` only enables it at startup.

**Unity 6**
- Timeline asset + PlayableDirector on a `Cutscene` object; Cinemachine cameras; Signal Emitters
  for events (`retroactive`: emit if playback starts after the signal time; `emitOnce`: once per
  loop). Skip: `director.time = director.duration; director.Evaluate();` then call the end-state
  method — do not rely on signals firing during a time jump (UNVERIFIED).
- Text: Localization package string tables (Yarn Spinner and ink integrations can feed them).

**Unreal 5.8**
- Level Sequence actor in the level; camera cuts, skeletal animation, audio and Event tracks.
  Event tracks fire when playback passes them (Fire Events when Forwards / Backwards); there is no
  "fire when jumping forwards" switch (that was Matinee), so events are not relied on during a skip.
  Skip through the sequence player's go-to-end call (`GoToEndAndStop` on the movie scene sequence
  player — confirm the name in the editor's API). Playback settings can disable movement/look and
  hide the HUD.
- VO: Dialogue Voice (speaker/listener) + Dialogue Wave (per-context sound waves, spoken text,
  subtitle override, actor direction notes); localization dashboards gather dialogue scripts per
  culture. Subtitles: sound/dialogue subtitles or the Subtitles and Closed Captions plugin.
- Text: String Tables (`FText`), DataTables imported from the Kiln CSV.

## Environmental storytelling hand-off (`design/narrative/places.md`)

| place | view bookmark | what happened here | props and arrangement | supporting text ID | light motivation |
|---|---|---|---|---|---|

Rules: one clear vignette per space, cause and effect visible ("what happened here"); readable in
a ≤ 3 s glance from the bookmark (working); never blocks navigation or cover; notes and logs are
optional reading — critical information is never only in an optional note. The level designer
builds it, the lighting artist lights it; the playtester captures the bookmark view and describes
it, and the description must match the row.

## Sources

Sam Kabo Ashwell, "Standard Patterns in Choice-Based Games" (2015); Paweł Sasko, "10 Key Quest
Design Lessons from The Witcher 3 and Cyberpunk 2077" (GDC 2023); Josh Sawyer, "Do (Say) The Right
Thing: Choice Architecture … in Fallout: New Vegas" (GDC 2012); Harvey Smith & Matthias Worch, "What Happened Here? Environmental
Storytelling" (GDC 2010); Henry Jenkins, "Game Design as Narrative Architecture" (2004); Xbox
Accessibility Guideline 104; BBC Subtitle Guidelines (160–180 wpm, 0.3 s/word); W3C "Text size in
translation"; Godot docs (AnimationPlayer.seek, DisplayServer.tts_speak); Unity Timeline
SignalEmitter API; Unreal Cinematic Event Track docs; UDialogueWave API; SAG-AFTRA 2025 Interactive
Media Agreement as reported by TheWrap.
