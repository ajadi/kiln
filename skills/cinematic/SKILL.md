---
name: cinematic
description: "Cutscenes, in-game cinematics, trailer shots and standalone clips made by agents; /kiln:cinematic <description> makes one end to end (a clip rendered in Blender in asset mode, a cutscene in the engine in a game) - in-engine vs pre-rendered, script to shot list to animatic, camera grammar with numbers (180-degree line, 30-degree rule, cutting on action, shot lengths, lenses per shot size), building them in the open editor (Godot AnimationPlayer + Camera3D + Movie Maker, Unity Timeline + Cinemachine 3 + Recorder, Unreal Level Sequence + Cine Camera + Camera Cuts + Movie Render Queue, Blender cameras bound to markers + FFmpeg output in 5.x), subtitles and pause/skip, and measured acceptance (shot_check.py continuity and subtitle timing, frame rate, camera clipping, A/V sync). Use for any cutscene, cinematic, camera sequence, trailer or rendered clip."
argument-hint: "[what the clip or cutscene should show]"
---

# Cinematic

A cinematic is judged on screen: every claim is a frame grab, a measurement or the user's eye.
Build it in the open editor through the engine's MCP (`mcp_only`, `scene_first`); scripts only
trigger it.

| File | Use |
|---|---|
| `${extensionPath}${/}skills${/}cinematic/scripts/shot_check.py shots <shots.json>` | timeline gaps, the 180-degree line, the 30-degree rule; mean/min/max shot length |
| `shot_check.py subs <file.srt> --fps 24` | reading speed, line length and count, minimum duration, gaps |

## /kiln:cinematic <description>

When the user runs the command (`$ARGUMENTS` = what the clip shows), run the job end to end;
roles that load this skill for a task skip to §1.

1. **Brief, one question**, with recommended answers: what happens and who is in it; length
   (➡️ 15-30 s); format (➡️ 1920×1080 16:9; 1080×1920 for vertical shorts; 1080×1080);
   frame rate (➡️ 24 for a film look, 30 or 60 for gameplay-like); style and mood; sound (music
   through the `/kiln:track` steps, effects, voice); on-screen text and subtitles; where it goes
   (video site, trailer, a game). Models and scenes it needs: existing ones in `out/` or the
   project, else the `/kiln:model` steps first. Images into `ref/<clip>/` with manifest rows.
2. **Task.** `tasks/TASK-NNN.md`: `type: cinematic`, `role: animator` (plus modeler,
   lighting-artist, composer as the brief needs), paths `out/<clip>/` in asset mode; backlog
   line; gates from `pipeline.py gates --suggest`.
3. **Shot list and animatic** (§2): `design/cinematics/<clip>.md` + `shots.json`, then a
   low-resolution viewport render with temporary sound for the timing. The user approves the
   animatic per `user_gates` (proxy: take it, mark PROXY, list it).
4. **Build.** Asset mode (`kind=assets`): in Blender through its MCP (§4 Blender); a game
   project: in the engine's sequencer (§4) as a real cutscene, or in Blender when the user wants
   only a video.
5. **Render.** Measure 3 frames first and tell the user the full render time before starting
   it (EEVEE for most clips; Cycles only when the look needs it and the time is accepted).
   Blender: MP4, H.264, AAC audio set explicitly; engines: §4 recorders.
6. **Gates.** `shot_check.py shots` and `subs`; frame count = length × fps exactly; A/V offset
   within 45 ms early / 125 ms late; loudness -14 LUFS ±1 integrated, true peak ≤ -1 dBTP for
   online video (`audio_check.py`); frame grabs of every shot to `kiln:art-director`;
   `kiln:verifier` closes.
7. **Deliver** into `out/<clip>/` (or the task's paths): the video, the `.blend` or the engine
   sequence, `shots.json`, the shot list, frame grabs, subtitles, and `README.md` (length,
   resolution, fps, codec, loudness, render time, what was generated with which model and
   licence). Licence rows in `production/LICENSES.md`.
8. **Report** in the user's language: the numbers, where the video is, decisions to redo.

## 1. In-engine or pre-rendered

| | In-engine (real time) | Pre-rendered video |
|---|---|---|
| Look | matches gameplay, current costume and gear | fixed, can exceed the game's look |
| Cost | runtime frame rate; can stutter | disk size; playback is cheap |
| Change | re-light, re-time, localise any time | re-render and re-ship |
Default: in-engine. Pre-render only for shots the game cannot run (crowds, offline lighting) or
for a trailer. Asset mode (`kind=assets`): Blender renders the clip.

## 2. From script to animatic

1. Beat list from the narrative (narrative skill: what the scene must make the player know).
2. **Shot list** in `design/cinematics/<scene>.md`: shot id, size (wide, medium, close-up,
   insert), lens, camera move, subject, start/end, dialogue line, purpose. Write it also as
   `shots.json` for `shot_check.py` (positions measured in the editor at each shot's first
   frame).
3. **Animatic** first: blocking poses, final cameras and timing, temporary audio. The user
   approves timing on the animatic; animation polish comes after (per `user_gates`).
4. Final: animation, lighting per shot (lighting skill), effects, mixed audio, subtitles.

## 3. Camera grammar (numbers)

- **180-degree line** between the two subjects of a scene: cameras stay on one side; cross only
  on screen (the camera moves across) or through a neutral shot on the line. `shot_check.py`
  fails a cut that crosses without `"cross_line"`.
- **30-degree rule**: two cuts on the same subject differ by ≥ 30° around it, or change the shot
  size clearly (focal ×1.5 or more); otherwise it is a jump cut.
- **Cut on action**: cut in the middle of a movement and finish it in the next shot.
- **Shot length**: current films average 3-5 s per shot; dialogue holds longer, action shorter.
  A game cutscene of 60-90 s is 12-25 shots (heuristic).
- **Lens by shot size** (35 mm full-frame equivalent): wide/master ~24 mm, medium ~50 mm,
  close-up 85-135 mm (compresses the face, shallow focus). Godot sets vertical `fov` (default
  75°), not focal length: convert with fov = 2·atan(12 / focal) for a 24 mm-tall frame.
- Camera moves serve the story (reveal, follow, push in on a decision); hold still otherwise.
  Handheld shake in a game cutscene: low amplitude, never during subtitles-heavy dialogue.

## 4. Building it

**Godot 4.6/4.7.** One AnimationPlayer per cutscene. Track types: property, position/rotation/
scale 3D, blend shape, call method (does not fire in the editor preview), Bezier (cannot blend
with property tracks), audio playback (needs an AudioStreamPlayer*), animation playback (drives
other AnimationPlayers; the orchestration track). Cuts: a property track on each Camera3D's
`current` (one current camera per viewport) or `make_current()` via a call track. Phantom
Camera (MIT addon, Godot 4.4+) gives Cinemachine-style priority switching and blends.
Recording: Movie Maker, `--write-movie out.ogv --fixed-fps 30 --resolution 1920x1080
--quit-after <frames>` (`.ogv` recommended, `.avi` MJPEG capped at 4 GB, `.png` sequence + WAV
lossless with alpha). Mix rate must divide by the fps or audio drifts. AnimationPlayer "Movie
Quit On Finish" ends the run cleanly; Ctrl+C can corrupt the file.

**Unity 6.** Timeline (`com.unity.timeline` 1.8.x; core package from 6.6) with Cinemachine 3.1
(`CinemachineCamera`, one `CinemachineBrain` on the Unity Camera, blends Cut / Ease In Out /
Linear ..., Custom Blends per camera pair; Update Method Smart Update). Cinemachine Track: shot
clips point to CinemachineCameras; overlap = blend, end-to-start = cut; Timeline overrides
priority while it plays. Recording: Recorder 5.1 (Play mode in the Editor only): Movie (H.264
MP4, VP8 WebM, ProRes), image sequence, AOV, audio WAV; triggerable from a Timeline track.

**Unreal 5.8.** Level Sequence with Cine Camera Actors (filmback, focal length, aperture,
focus method Manual / Tracking; manual focus distance in cm). Camera Cuts track: no gaps or
overlaps by default; "Can Blend" blends transform, depth of field and focal length. Shots track
for anything longer than a few shots; Director Blueprint for event logic. Rendering: Movie
Render Queue / Movie Render Graph; outputs EXR (multilayer), JPG, ProRes and DNx (with their
plugins), WAV, FFmpeg via the command-line encoder. Anti-aliasing: temporal samples first,
engine warm-up frames at each shot start. Command line: `UnrealEditor-Cmd.exe <proj>.uproject
<Map> -game -LevelSequence=/Game/.../Seq.Seq -MoviePipelineConfig=/Game/.../Preset.Preset
-windowed -resx=1920 -resy=1080 -log -notexturestreaming` (release skill's guard rules apply).

**Blender 5.x** (asset mode, trailers, pre-rendered shots), through the Blender MCP: one camera
per shot, timeline markers with `TimelineMarker.camera` set for the cuts; output
`image_settings.media_type = 'VIDEO'` before `file_format = 'FFMPEG'` (5.0 change), container
MPEG4 or MKV, codec H.264, `constant_rate_factor` HIGH, and **`audio_codec` set** (AAC) - the
default is none, so the clip is silent. EEVEE engine id is `BLENDER_EEVEE` from 5.0. The video
sequencer uses its own scene per workspace in 5.0; output settings stay on the active scene.

## 5. Player-facing rules

- Pause anywhere, cinematics included (Xbox Accessibility Guideline 108); offer skip after the
  first viewing (and always on replay).
- Subtitles on by default or offered before the first cinematic, ≤ 40 characters per line and
  2 lines, text scalable to 200%, adjustable background, speaker named on change (XAG 104);
  reading speed ≤ 20 characters/s (17 for children), ≥ 20 frames on screen, ≥ 2 frames between
  cues (Netflix timed-text guide).
- Control returns where the cutscene left the player, camera behind them, no input eaten.

## 6. Acceptance with numbers

| Check | How | Gate |
|---|---|---|
| continuity | `shot_check.py shots` | pass |
| subtitles | `shot_check.py subs` per language | pass |
| frame rate (in-engine) | frame times over the whole cutscene (Godot `--print-fps`, Unreal `stat unit`, Unity Profiler) by qa-performance | ≥ the GAME.md target, no frame > 2× budget |
| camera clipping | sphere sweep (radius = near plane + 5 cm) along every camera path against level geometry, through the engine MCP | 0 hits |
| A/V sync | clap frame / audio onset offset in the recording | audio within 45 ms early / 125 ms late (ITU-R BT.1359 detectability) |
| look | art-director on frame grabs of every shot (first, middle, last frame) | approved |
Offline recordings use fixed timesteps (Movie Maker `--fixed-fps`, MRQ warm-up) so frames are
never dropped; real-time playback is judged separately on the build.
