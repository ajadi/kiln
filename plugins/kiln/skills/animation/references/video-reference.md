# Video reference for a clip

A generated or filmed clip guides **timing and key poses**. It has no skeleton; its camera,
proportions and limb identity can drift. Kiln's joint limits, phase, slip, loop seam and contact
rules win whenever the clip disagrees. The shipped clip is keyed by hand against the reference
and never copied frame by frame.

Use it for move types with no mocap at hand and for stylised timing (a heavy overhead swing, a
creature's gait). Skip it for moves the biomechanics skills already pin down with numbers.

## 1. Get the clip

| Source | Policy | Notes |
|---|---|---|
| filmed or library video (the user's, a CC0 or public-domain clip) | none | record source, licence and date in `ref/manifest.csv` |
| local model (`video_generators=local`): Wan 2.2 TI2V-5B | tools catalogue (`tools_check.py offers`) | fits 8 GB with ComfyUI offloading; 24 fps; no end frame, so loop by cutting |
| rented GPU (`video_generators=remote`): Wan 2.1 FLF2V-14B | gpu-server skill | first and last frame: the open loop model |
| paid API (`video_generators=api`) | the user's own account and yes | Grok Imagine, Veo 3.1 Lite / Fast, Hailuo-02 (first + last frame), Runway (also reaches Kling, Seedance, Veo, Wan 3); Runway and the unpaid Gemini tier train on inputs, so unreleased character art goes through paid, no-training tiers only |

Never: HunyuanVideo 1.5 (its licence bars using the output in the EU, the UK and South Korea),
FramePack (non-commercial FLUX Redux encoder), Sora 2 (API removed 2026-09-24).

**Input render** (Blender): a rough key pose of the move as the first frame (walk: left contact),
not the rest pose; a long lens (≥ 85 mm) or orthographic camera at hip or chest height, exactly
side-on for locomotion, front for attacks at the camera; the whole body at 60-70 % of the frame
height with the feet visible; a flat mid-grey background with flat light and no cast shadow; the
model's native aspect ratio and resolution. A second view goes in as a character reference where
the model takes one; two separately generated clips are two performances and cannot be
triangulated - use the side clip for timing, the front one for lateral amplitudes only.

**Prompt template:**

```
The character from the image performs <a relaxed walk cycle in place>, <one full cycle per 1.0
seconds>, seamless looped animation, static shot, fixed camera, fixed lens, locked-off tripod,
side view, full body in frame, the character stays centred and walks on the spot, plain flat
grey background, even studio light, game animation reference, motion-capture reference style.
```

Negatives as nouns, not "no X": `camera movement, zoom, pan, cuts, text, extra people, props,
motion blur, depth of field`. MiniMax: add `[Static shot]`. Wan FLF2V: a Chinese prompt works
better. Loops: generate 1.5-2 cycles without an end frame and cut at the best pair (`period`).
The subject may travel across the frame: measure the root drift and remove it, do not copy it.
One move per clip, 4-6 s. Provenance (clip, prompt, seed, model, version, date, terms) goes into
`ref/manifest.csv`; clips live in `art/source/<char>/anim_ref/`, outside game content
(`.gdignore`).

## 2. Read it (`scripts/video_ref.py`)

1. `frames clip.mp4 --out <dir> --fps <the clip's fps>` (ffmpeg).
2. `pose <dir> --out ref.kp.json`: RTMPose through rtmlib (Apache-2.0, CPU; the `pose` tool,
   installed with the user's yes by `tools_check.py install pose`; the first run downloads about
   150 MB of models into `~/.cache/rtmlib`). Human-Art models also read rendered figures.
   Never OpenPose, Sapiens, GVHMR or SMPL-based tools (non-commercial).
3. `gate ref.kp.json --frames <dir> --loop`: confidence, scale and limb drift one cycle apart,
   camera drift, held frames (a video that repeats poses has a lower real frame rate), loop
   seam. A failed gate means regenerate or cut elsewhere, not "author anyway".
4. `period` (cycle and loop cut) and `keys` (contacts, swing knee peaks): the frames to author
   first. Key the extremes and breakdowns at the engine's fps, not every reference frame.

## 3. Compare our clip

Render our clip from a camera matched to the reference, run the **same** estimator on it, then
`compare ref.kp.json ours.kp.json`: period within 3 %, key-pose timing within one frame at 30
fps (or one source frame), DTW warp ≤ 1 frame mean / 2 max, sagittal joint angles RMSE ≤ 8° and
extremes within 10°, PCK at 0.05 H ≥ 0.85. Once per character, `noise` measures the estimator on
our render against the true projected joints (exported from Blender) and widens every threshold
to 2 sigma. Whole-body silhouette IoU barely reacts to a 10-15° forearm error: a gross check
only. All thresholds are working values (research 2026-10-19); record what accepted clips
measure in `memory/pipeline.md`.

Live check (Kiln 0.9): a public-domain Muybridge walk (36 frames, 12 fps) through `pose` gave
keypoints on every frame, a 1.0 s period at correlation 1.0, a seam of 0.002 H, and passed
`compare` against itself shifted by five frames; the same walk as an mp4 that holds each pose
for four frames failed the held-frames gate, and its moving cameras failed the camera gate.
