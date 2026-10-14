# Matching a sound to real references (analysis → resynthesis)

An agent cannot listen. It can measure references, fit a synthesiser to the measurements, and
prove the result is in the same class as the references without copying any of them.

## 1. Legal sources (analysis only)

| Source | Use in a commercial game's analysis? | Notes |
|---|---|---|
| Freesound, CC0 | yes | API search: `GET https://freesound.org/apiv2/search/?query=machine%20gun&filter=license:"Creative Commons 0" duration:[0.5 TO 8]&fields=id,name,username,license,url,previews,duration&token=KEY`; previews (`preview-hq-ogg`) need only the token, originals need OAuth2 |
| Freesound, CC BY | yes | credit the author in the provenance file |
| Freesound, CC BY-NC / Sampling+ | no | non-commercial; honour "no generative AI use" flags |
| Sonniss GDC bundles | yes, for scripted measurement | licence forbids redistribution and use for training AI |
| DVIDS (US military media) | yes | mostly US-government public domain; check each item; non-endorsement disclaimer |
| own recordings (metal hits, doors, servos) | best | no licence questions |
| BBC Sound Effects | **no** | RemArc licence needs BBC permission for computer analysis and commercial use |
| YouTube | **no** | terms forbid downloading and automated access |

Provenance: references live outside the repository and outside the game's content folders.
`tools/audio/refs_manifest.csv` columns: `ref_id, source_url, author, licence, licence_url, retrieved_utc,
sha256, local_path, purpose=analysis-only, derived_files`. Commit only derived numbers (feature
and parameter JSON), never the reference audio.

## 2. Analysis (librosa + scipy, 48 kHz mono)

| Measure | How |
|---|---|
| onsets, rate of fire | `onset_strength(hop_length=128)` → `onset_detect(backtrack=True, units='time')`; RPM = 60 / median IOI; IOI std = jitter |
| envelope | Hilbert magnitude smoothed 1 ms, or `feature.rms(frame_length=256, hop_length=64)`; attack = t(90%) − t(10%); decay = line fit to the dB envelope from −3 to −40 dB; two segments for body + tail |
| spectrum | `spectral_centroid`, `spectral_rolloff(roll_percent=0.85)`, `spectral_flatness`; long-term spectrum `scipy.signal.welch(nperseg=4096)` collapsed to 1/3 octaves — the main target for noise layers |
| tonal vs noise | `librosa.decompose.hpss(S, margin=(1.0, 3.0))`: H = whines/hums/lasers, P = clicks/impacts, residual = noise |
| pitch | `librosa.pyin(fmin=50, fmax=2000)` for servos, motors, laser sweeps; fit a chirp law f(t) = f1 + (f0 − f1)·e^(−t/τ) |
| modes (for modal synthesis) | STFT peak tracking (`find_peaks(prominence=10)` + parabolic interpolation), T60 per partial from its dB slope; higher resolution: matrix pencil or ESPRIT on a band-passed segment |
| layers | NMF (`librosa.decompose.decompose(S, n_components=4)`): activations give each layer's offset (crack, body, mechanism, tail) |
| space | Schroeder curve on a free decay, T20 × 3 per octave band (needs ≥ 35 dB above the noise floor; otherwise EDT) |

## 3. Fitting a synth (analysis-by-synthesis)

1. Synth = the toolkit blocks from SKILL.md with ~10–25 parameters θ ∈ [0, 1]ⁿ (frequencies and
   times on log scales). Initialise from §2 measurements.
2. Align before comparing: onset-align (±5 ms envelope cross-correlation) and loudness-match —
   spectral losses are very sensitive to time shifts.
3. Loss = multi-resolution STFT log-magnitude L1 (FFT sizes 64…2048) + 0.5 × envelope dB L1
   (1 ms hop, floor −60 dB) + 0.3 × MFCC c1–c19 L2 + 0.2 × 1/3-octave long-term spectrum dB L1.
4. Optimise with CMA-ES: `cma.fmin2(f, x0, 0.25, {'bounds': [0, 1], 'popsize': 20, 'maxfevals': 3000, 'seed': k})`
   over 3–5 seeds. A numpy render of 0.3 s takes milliseconds, so this is minutes on a CPU.
5. Variations: fit several references, take the min–max range of fitted θ widened by 10%, sample
   inside it with new noise seeds.

## 4. Close enough, not a copy

Collect ≥ 5 references per class; D_inter = median pairwise loss between references. Accept a
synth when:

- D(synth, nearest reference) ≤ D_inter — as close to the class as two real recordings are to
  each other;
- its features (centroid, attack, decay, band ratios) fall within ±2σ of the reference cloud;
- **anti-copy:** it is not closer to any single reference than the 10th percentile of
  inter-reference distances, and its waveform cross-correlation with every reference is < 0.3.

Optional class check (evaluation only, nothing ships): PANNs CNN14 AudioSet tags (the intended
class in the top 3) or CLAP text similarity. Set-level comparison of 10–50 variations: KAD
(unbiased at small sizes) rather than FAD; if FAD, use PANNs embeddings, not VGGish.

## 5. Worked example: machine gun

1. References: 6–10 (Freesound CC0, DVIDS footage, Sonniss weapons) in the manifest.
2. Analysis: onsets → IOI and RPM (typ. 550–1200 RPM) and jitter; cut each shot from onset −2 ms
   to onset + IOI, align, median shot = template; measure attack (< 1 ms), two decay slopes,
   1/3-octave spectrum, H/P/residual ratio, 4-component NMF, Schroeder RT of the tail after the
   burst.
3. Synth per shot: crack N-wave 0.2–0.5 ms · blast noise (attack 0.3 ms, τ1 3–8 ms, τ2 20–60 ms)
   through 4–8 band-passes 30 Hz–11 kHz · thump sine 60–120 Hz swept down over ~60 ms ·
   mechanism click 3–6 modes 1.5–8 kHz, T60 15–50 ms at +5…25 ms · tanh drive 1–4 · high-pass
   30 Hz. Mech variant: lower band centres + feed-motor whine tied to RPM.
4. Fit: CMA-ES, popsize 20, 3000 evaluations, 5 seeds. Accept per §4.
5. Render: 12 single-shot variants, 3 tails per zone (street, courtyard, interior) from IRs, 2
   distant versions (low-pass 2–4 kHz, more tail); 48 kHz mono, −1 dBTP; `audio_check.py asset`
   and `variations`.
6. Engine: randomizer no-repeat, pitch 1.03, volume offset 1 dB; polyphony 4–6; tail on release;
   then record the bus in the running game and re-measure RPM, peak, loudness and RT.
