---
name: procedural-audio
description: Designing game sound effects procedurally (no sample libraries) — reference analysis, a synthesis toolkit (modal, PhISEM, FM, N-wave, comb, stick-slip, formant banks), per-family recipes with timings for mechs, servos, motors, hydraulics, lasers, guns, missiles, explosions, armour hits, breaking parts, debris and collapses, variation and loudness rules, enclosed-space treatment, engine implementation (Godot here; Unity/Unreal in engine skills) and measurable checks. Use for any sound-effect, ambience or mix task.
user-invocable: false
---

# Procedural sound design

The deliverable is a reproducible generator plus rendered sounds. Every file in the game's SFX
folder can be rebuilt from `tools/audio/<family>.py` with a fixed seed and parameters stored in a
manifest. References are for analysis only — never shipped, never committed.

Environment: a user-level venv outside the project, `<venvs>/audio` (machine.json `tools_root`/venvs,
else `~/.local/share/kiln/venvs`), on Python 3.12–3.13 (librosa 1.0 needs ≥ 3.12; some tools stop
at 3.13): numpy, scipy, soundfile, librosa, pyloudnorm, pyroomacoustics, cma — `pip install -r
${CLAUDE_SKILL_DIR}/requirements.txt` into that venv. Check what is installed before installing.
Loudness checks need only numpy + soundfile + pyloudnorm (soundfile reads Ogg Vorbis), so ffmpeg is
optional; librosa (beat/key checks) may have no wheel for the newest Python — use 3.12/3.13 (g2
row 111).

| Script / file | Use |
|---|---|
| `${CLAUDE_SKILL_DIR}/scripts/audio_check.py` | numpy-only gates: `asset` (true peak, clipping, DC, end click, BS.1770 loudness + LRA), `loop` (exact length for bars/BPM, seam click), `stems` (equal length/rate, null test against the mix), `variations` (pairwise correlation), `rt60` (Schroeder T20 of a recorded impulse) |
| `${CLAUDE_SKILL_DIR}/references/reference-analysis.md` | read when a sound must match real references: legal sources, analysis pipeline, fitting a synth to references (analysis-by-synthesis), anti-copy rule, worked machine-gun example |

## Toolkit (Python: numpy, scipy)

| Block | Use |
|---|---|
| Modal synthesis y(t)=Σ aₙ·e^(−dₙt)·sin(2πfₙt) | metal plates, armour, clanks, beams. Material = decay: dₙ ∝ fₙ·tanφ (metal low tanφ → long ring; concrete/wood high). Randomise the gain vector aₙ per hit = hit location |
| Excitation pulse 1−cos(2πt/τ), 0≤t≤τ | its length τ conveys hardness (bullet τ 0.1–1 ms, heavy round 2–5 ms); add a residual noise burst — a single clean contact sounds too clean |
| PhISEM (Cook) | debris, gravel, glass: collisions at a Poisson rate driven by a decaying energy variable, each exciting resonant filters — physically plausible thinning out |
| N-wave / shock pulses | muzzle blast, explosion crack |
| Comb filters, swept delays | tube and pressure resonance |
| Parallel band-pass "formant" banks | gun bodies (8 band-passes), structure resonances |
| Phasor stator + band-passed noise rotor | electric motors (brush noise ~4 kHz, housing ~150–250 Hz) |
| Stick-slip friction | creaks, groans, tearing metal |
| Geometric bounce schedule | falling parts (interval ratio 0.6–0.8) |
| Oscillators with pitch envelopes, FM | servos, lasers, sub thumps |
| Noise colours + biquads, waveshaping/soft clip | bodies, hiss, grit, weight |

## Recipes by family (starting values; times relative to the impact at 0)

| Family | Layers |
|---|---|
| Heavy mech step | −300…0 ms servo swing · 0: contact burst 1–6 kHz, 5–15 ms · sub sine 70→35 Hz drop, 120–400 ms, soft-clipped · punch 80–150 Hz, 60–150 ms (most speakers can't reproduce < 50 Hz) · modal ring 8–20 modes 150 Hz–3 kHz, 0.2–0.8 s · debris PhISEM 20–60 grains, 0.3–1 s · ground rumble 20–80 Hz, 0.3–0.8 s · hydraulic hiss 3–8 kHz **offset +50…300 ms** (on the lift, not with the impact), 0.2–0.5 s |
| Light mech step | sub 70–120 Hz, 60–150 ms · modal ring 400 Hz–5 kHz, 0.1–0.3 s · servos 2–3× higher pitch · less debris |
| Servos | band-passed saw/square 200–900 Hz (heavy) / 600–2500 Hz (light); pitch tracks joint angular velocity + ±1–3% slow jitter; gear-mesh AM at tooth rate; brush noise ~4 kHz; 30–100 ms start/stop ramps; ship a seamless loop and drive pitch at runtime |
| Electric motors (torso, turret) | stator hum + rotor noise; housing resonance 150–250 Hz; exponential spin-up/down 0.3–1.5 s |
| Hydraulics | **tonal pump**: pitch = pistons × rpm / 60 (e.g. 9 × 1750 / 60 = 262.5 Hz; odd piston counts often dominate at 2×) + harmonics 2–4 · flow noise 1–4 kHz · valve clack modal 1–3 kHz, 20–60 ms · pressure release 3–10 kHz, 0.2–0.8 s |
| Laser | shot: sine/FM chirp 2–6 kHz → 200–800 Hz over 50–300 ms, FM index decaying; dispersive all-pass cascade for a "slinky" zap · beam loop: detuned saws + ring mod + 50–120 Hz hum · impact sizzle 4–12 kHz · charge-up rising 0.3–1 s |
| Machine gun | one-shot per round, spacing 60/RPM (600–900 RPM → 67–100 ms) · crack: N-wave 1–3 ms + noise 5–15 ms · body: 8 band-passes 150–800 Hz, 50–150 ms · low 60–120 Hz · mechanical clicks modal 2–6 kHz at +20…60 ms · casings (player only) brass 3–9 kHz · distant layer low-passed < 2 kHz with longer tail, crossfaded by distance |
| Missile launch | ignition pop · chamber resonances ×2–5 · exhaust noise around 1.7 kHz · low back-pressure · tube clank · burn loop pink/brown noise 300 Hz–3 kHz · in flight: engine doppler |
| Explosion | crack 0–20 ms broadband · body: clipped band-passed noise 50–500 ms · sub 30–80 Hz with pitch drop 0.3–1.5 s · pressure wave via comb/delay feedback · debris PhISEM 0.2–3 s · tail 1–5 s · **bigger = longer and lower, not louder** |
| Armour hit | thick plate 5–20 modes 200 Hz–6 kHz with frequency-dependent decay; τ by projectile; occasional ricochet whine falling from 2–5 kHz; laser hit = sizzle |
| Part breaking | stick-slip tear 0.2–1 s · snap transient · modal ring of the detached part · electrical crackle · fluid spray hiss · bounces shrinking ×0.6–0.8 |
| Debris fall | PhISEM: concrete low-Q 300 Hz–3 kHz, glass high-Q 2–8 kHz, metal high-Q, big chunks 60–150 Hz thud; 0.5–4 s |
| Collapse (wall, car, infrastructure) | precursor creaks/groans 1–3 s (stick-slip, slow low sweeps) · crack · fall rumble brown noise 30–200 Hz swelling 0.5–2 s · impact (explosion body without fire) · debris tail 2–8 s · cars: thin-panel modes 50–500 Hz + glass PhISEM · steel beams: long low ring |

## Variation, format, loudness

- Variations by repetition rate: 8–12 for MG shots and footsteps, 3–6 for medium-frequency
  sounds, 2–3 for collapses. Vary parameters (seed, modal frequencies ±2–3%, decays ±10–20%,
  grain counts), not just pitch; heavy objects stay within ±2–4% pitch (pitch changes size).
- 48 kHz WAV (engines may resample); mono for positional 3D emitters; the player's own weapons
  as non-positional stereo.
- **Do not peak-normalise everything to −1 dBFS** — it erases relative loudness. Normalise each
  family to a loudness target with a ≤ −1 dBTP true-peak ceiling, keep a level table, and put a
  hard limiter on the master bus (ceiling −1 dB).
- Seamless loops: zero crossings, phase-continuous, no click at the boundary.

## Enclosed urban spaces

- First reflection delay ≈ extra path / 343 m/s; flutter between parallel facades ≈ 2W/c
  (3 m alley 17 ms, 10 m street 58 ms); above ~50 ms reflections read as slapback.
- Ruined, rubble-strewn streets: shorter, more diffuse tails than clean canyons; large interiors
  1–2.5 s.
- Don't bake rooms into dry 3D sounds: reverb per space type through the engine's reverb zones
  (alley, courtyard, hall, garage); offline synthetic IRs (pyroomacoustics `ShoeBox` +
  `inverse_sabine`, ray tracing on, ceiling absorption 0.99 for open sky) for baked tail layers per
  zone and as RT60 references for tuning the engine reverb.
- Street canyon early reflections with a delay effect: tap 1 at W/c (6/8/12 m → 17/23/35 ms)
  −6 dB, tap 2 at 2W/c −12 dB, feedback delay 2W/c −8 dB with a 4 kHz feedback low-pass; a 20 m
  courtyard's 117 ms period is heard as an echo — keep it ≤ −12 dB.
- Starting RT60 (upper bounds; streets are not diffuse): street 8×20×100 m 1.7 s, courtyard
  20×20×15 m 1.8 s, hard corridor 1.4 s, furnished corridor 0.7 s, garage 40×30×5 m 4.3 s, small
  room 0.46 s.
- Distance: keep the lows, low-pass the highs, crossfade close/distant layers for weapons and
  explosions. Occlusion (mass law TL = 20·log10(f·m) − 47): through brick ≈ −30…−40 dB with a
  200–400 Hz low-pass; around a corner or through a doorway −6…−15 dB with an 800–2000 Hz
  low-pass. A listener→source raycast picks the case.
- Mix priority (HDR-style): tag events with nominal loudness and attenuate/cull those far below
  the current loudest; per-family voice caps (debris ≤ 6, footsteps ≤ 8); sidechain-duck ambience
  and music from weapons and explosions.

## Godot 4.6/4.7

- Buses: Weapons_Player, Weapons_NPC, Mechs, Explosions, Debris, Ambience, Music, UI (record in
  `memory/registries.md`); `AudioEffectHardLimiter` on Master (not the deprecated Limiter);
  sidechain `AudioEffectCompressor` on Ambience/Music.
- Reverb zones: `Area3D.reverb_bus_enabled/name/amount/uniformity` — amount defaults to 0 (set
  it), the target bus needs an `AudioEffectReverb`, and the **emitter's** position is tested
  against the area. No convolution reverb.
- `AudioEffectReverb` behaves unlike its docs (read from `reverb_filter.cpp`): Freeverb, 8 combs,
  feedback g = 0.7 + 0.28·room_size, so **RT60 cannot go below ≈0.65 s**. Target RT →
  `room_size = (10^(−0.0936/(1.1·RT)) − 0.7) / 0.28` (room_size 0 → 0.65 s, 0.5 → 1.1 s,
  0.65 → 1.5 s, 0.8 → 2.5 s, 0.9 → 3.9 s). **Higher `damping` = brighter, longer high end.**
  **`predelay_msec` is a feedback echo, not a pre-delay**: with `predelay_feedback` 0 there is no
  pre-delay; the defaults (150 ms, 0.4) add echo repeats — set feedback 0 indoors, use it as
  flutter (predelay 2W/c, feedback 0.3–0.5) in streets. `hipass` ≈ value × 6 kHz one-pole
  (0.02 → 120 Hz). Rooms under 0.6 s: delay-effect early reflections + a baked tail.
- The 3D player's `attenuation_filter_*` is a high shelf scaled by (1 − distance gain): nearby
  sources get no high cut, so it cannot do occlusion — route occluded emitters to a bus with
  `AudioEffectLowPassFilter`, or swap to baked occluded variants. Measure every zone: record the
  bus with `AudioEffectRecord`, save WAV, `audio_check.py rt60`.
- `AudioStreamRandomizer`: playback mode RANDOM_NO_REPEATS (default), `random_pitch` is a
  multiplier (1.05 → ±5% ≈ 0.84 semitone), `random_volume_offset_db`, weighted streams.
- Automatic fire timed from `_physics_process` at 60 Hz quantises the interval (80 ms alternates
  67/83 ms): choose an interval that is a multiple of 16.7 ms, or play a pre-rendered loop while
  the trigger is held and a tail on release.
- `AudioStreamPlayer3D`: attenuation inverse (default) / inverse-square / logarithmic; unit_size
  10, max_db +3; built-in distance low-pass (`attenuation_filter_cutoff_hz` 5000,
  `attenuation_filter_db` −24); **`max_polyphony` defaults to 1 — automatic fire cuts itself
  off: raise to 4–8 or use `AudioStreamPolyphonic`**; doppler needs tracking on both the player
  and the camera. 4.7: the non-positional player's default `area_mask` is 0.
  **An `AudioStreamPlayer3D` is silent in a viewport that has an `AudioListener3D` but no
  `Camera3D`** (4.7.2 `_update_panning` iterates cameras; the listener only replaces the
  camera's position). An audio gym or probe scene needs a Camera3D (g2: every footstep and
  dagger cue was silent, and the check still passed because the Master recording held music).
- An "SFX audible" check records the SFX alone (music bus muted, or subtract a music-only run)
  and must be able to fail; any level above −60 dBFS in a full mix proves nothing. Effects and
  bus settings are measured on identical content (acceptance `references/methods.md`).
- WAV import default compression is QOA (lossy) — null-test short transients against PCM.
- Prefer pre-rendered WAVs and runtime `pitch_scale` over GDScript `AudioStreamGenerator`
  synthesis (use C#/GDExtension if real-time synthesis is unavoidable).
- Third-party spatial audio addons (Steam Audio ports) need the user's approval.

## Checks

- `audio_check.py asset` on every rendered file: no sample with |x| ≥ 0.999; true peak ≤ −1 dBTP;
  DC < 0.001; no end click. Loudness per family within ±1.5 LU of its target (clips under 0.4 s
  have no integrated loudness — compare peak + RMS).
- Per layer: attack (10–90%), decay to −40 dB, spectral centroid and band-energy ratios (< 80 Hz,
  80–500 Hz, 0.5–4 kHz, > 4 kHz) within ±15% of the recipe or reference.
- Variations: `audio_check.py variations` — pairwise correlation < 0.9; randomizer in no-repeat
  mode.
- Loops: `audio_check.py loop` — exact length, seam jump below the 99th-percentile step.
- Reverb: `audio_check.py rt60` on an impulse recorded through the bus — within ±20% of the
  target per space.
- In game: MG bursts without voice cut-offs, doppler on missiles, occlusion low-pass < 1.5 kHz
  behind walls; the final mix measured by qa-audio (−24 LUFS ±2 integrated over ≥ 30 min, true
  peak ≤ −1 dBTP).
