"""Objective checks for rendered game audio (SFX, ambience, music stems). numpy only.

  python audio_check.py asset sfx/mg/*.wav --target-lufs -20 --tol 1.5
  python audio_check.py loop music/combat_a.wav --bpm 144 --bars 16 --beats-per-bar 4
  python audio_check.py stems stems/combat_*.wav --mix music/combat_full.wav
  python audio_check.py variations sfx/step_heavy/*.wav --max-corr 0.9
  python audio_check.py rt60 captures/ir_courtyard.wav --target 1.8 --tol 0.2

Reads WAV (PCM 8/16/24/32-bit, float32/64); other formats through soundfile or ffmpeg if present.
Loudness is ITU-R BS.1770-4 (K-weighting applied as a zero-phase magnitude filter, gated
integrated loudness, LRA per EBU 3342); pyloudnorm is used instead when installed. True peak uses
4x FFT oversampling. Every result carries a verdict; exit code 1 if any check fails.
"""

import argparse
import glob
import itertools
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

import numpy as np


# ---------------------------------------------------------------- reading


def expand(patterns):
    """Expand glob patterns here: Windows shells pass them through unexpanded."""
    out = []
    for p in patterns:
        hits = sorted(glob.glob(p, recursive=True)) if any(c in p for c in "*?[") else [p]
        out.extend(hits or [p])
    return out

def read_wav(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file")
    pos, fmt, raw = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            tag, channels, sr = struct.unpack("<HHI", body[:8])
            bits = struct.unpack("<H", body[14:16])[0]
            if tag == 0xFFFE and len(body) >= 26:
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, channels, sr, bits)
        elif cid == b"data":
            raw = body
        pos += 8 + size + (size & 1)
    if not fmt or raw is None:
        raise ValueError("missing fmt or data chunk")
    tag, channels, sr, bits = fmt
    width = bits // 8
    raw = raw[:len(raw) - len(raw) % (width * channels)]
    if tag == 3:
        x = np.frombuffer(raw, dtype="<f4" if bits == 32 else "<f8").astype(np.float64)
    elif tag == 1 and bits == 24:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v) / float(1 << 23)
    elif tag == 1 and bits in (8, 16, 32):
        dtype = {8: np.uint8, 16: "<i2", 32: "<i4"}[bits]
        x = np.frombuffer(raw, dtype=dtype).astype(np.float64)
        x = (x - 128) / 128 if bits == 8 else x / float(1 << (bits - 1))
    else:
        raise ValueError(f"unsupported WAV format tag {tag}, {bits} bit")
    return x.reshape(-1, channels), sr


def read_audio(path):
    if path.lower().endswith(".wav"):
        return read_wav(path)
    try:
        import soundfile  # optional
        x, sr = soundfile.read(path, always_2d=True, dtype="float64")
        return x, sr
    except ImportError:
        pass
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("non-WAV input needs soundfile or ffmpeg")
    out = os.path.join(tempfile.mkdtemp(prefix="kiln-audio-"), "d.wav")
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", path, "-c:a", "pcm_f32le", out],
                   check=True, timeout=300)
    return read_wav(out)


def db(v):
    return float(20 * np.log10(max(float(v), 1e-12)))


# ---------------------------------------------------------------- loudness

def _biquad_response(b, a, w):
    z = np.exp(-1j * w)
    return (b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z)


def k_weight_magnitude(n, sr):
    """|H(f)| of the BS.1770 K-filter (pre-filter shelf + RLB high-pass) on an rfft grid."""
    # libebur128's bilinear design: reproduces the BS.1770 48 kHz coefficients exactly
    w = 2 * np.pi * np.fft.rfftfreq(n, 1.0 / sr) / sr
    f0, gain, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    K = np.tan(np.pi * f0 / sr)
    vh = 10 ** (gain / 20)
    vb = vh ** 0.4996667741545416
    a0 = 1 + K / q + K * K
    h1 = _biquad_response([vh + vb * K / q + K * K, 2 * (K * K - vh), vh - vb * K / q + K * K],
                          [a0, 2 * (K * K - 1), 1 - K / q + K * K], w)
    f0, q = 38.13547087602444, 0.5003270373238773
    K = np.tan(np.pi * f0 / sr)
    a0 = 1 + K / q + K * K  # the RLB numerator stays [1, -2, 1]; only the poles are normalised
    h2 = _biquad_response([1, -2, 1], [1, 2 * (K * K - 1) / a0, (1 - K / q + K * K) / a0], w)
    return np.abs(h1 * h2)


def block_energy(x, sr):
    """K-weighted mean square per 100 ms sub-block, summed over channels (weights 1)."""
    n = len(x) + sr  # zero padding against circular wrap
    mag = k_weight_magnitude(n, sr)
    y = np.fft.irfft(np.fft.rfft(x, n=n, axis=0) * mag[:, None], n=n, axis=0)[:len(x)]
    step = sr // 10
    count = len(y) // step
    sub = (y[:count * step] ** 2).reshape(count, step, -1).mean(axis=1).sum(axis=1)
    return sub


def gated_loudness(sub, window, rel_gate):
    if len(sub) < window:
        return None, None
    blocks = np.convolve(sub, np.ones(window) / window, mode="valid")
    lufs = -0.691 + 10 * np.log10(np.maximum(blocks, 1e-20))
    keep = lufs > -70
    if not keep.any():
        return None, lufs
    rel = -0.691 + 10 * np.log10(blocks[keep].mean()) + rel_gate
    keep &= lufs > rel
    return keep, lufs


def loudness(x, sr):
    try:
        import pyloudnorm  # optional, exact reference implementation
        meter = pyloudnorm.Meter(sr)
        integrated = float(meter.integrated_loudness(x if x.shape[1] > 1 else x[:, 0]))
        source = "pyloudnorm"
    except (ImportError, ValueError):
        integrated, source = None, "builtin"
    sub = block_energy(x, sr)
    if integrated is None:
        keep, _ = gated_loudness(sub, 4, -10)
        if keep is not None and keep.any():
            blocks = np.convolve(sub, np.ones(4) / 4, mode="valid")
            integrated = float(-0.691 + 10 * np.log10(blocks[keep].mean()))
    keep, lufs = gated_loudness(sub, 30, -20)
    lra = None
    if keep is not None and keep.sum() >= 2:
        lo, hi = np.percentile(lufs[keep], [10, 95])
        lra = float(hi - lo)
    return integrated, lra, source


def true_peak(x, factor=4, block=1 << 15, overlap=512):
    """Max of the 4x band-limited interpolation; segment edges (wrap ringing) are discarded."""
    peak = 0.0
    for ch in range(x.shape[1]):
        s = x[:, ch]
        for start in range(0, len(s), block):
            lo = max(0, start - overlap)
            seg = np.concatenate([np.zeros(overlap), s[lo:start + block + overlap],
                                  np.zeros(overlap)])
            up = np.fft.irfft(np.fft.rfft(seg), n=len(seg) * factor) * factor
            keep = up[(overlap + start - lo) * factor:(overlap + start - lo + block) * factor]
            if keep.size:
                peak = max(peak, float(np.abs(keep).max()))
    return peak


# ---------------------------------------------------------------- checks

def check_asset(path, target, tol, ceiling):
    x, sr = read_audio(path)
    peak = float(np.abs(x).max()) if x.size else 0.0
    tp = true_peak(x)
    dc = float(np.abs(x.mean(axis=0)).max())
    steps = np.abs(np.diff(x, axis=0)).max(axis=1) if len(x) > 1 else np.zeros(1)
    p99 = float(np.percentile(steps, 99))
    end_jump = float(np.abs(x[-1]).max()) if len(x) else 0.0  # playback drops to 0 after it
    problems = []
    if not np.isfinite(x).all():
        problems.append("NaN/inf samples")
    clipped = int((np.abs(x) >= 0.999).sum())
    if clipped:
        problems.append(f"{clipped} clipped samples")
    if db(tp) > ceiling:
        problems.append(f"true peak {db(tp):.2f} dBTP > {ceiling}")
    if dc >= 1e-3 and len(x) >= sr:  # short transients have a genuine non-zero mean
        problems.append(f"DC offset {dc:.4f} (high-pass at 20-30 Hz)")
    if end_jump > max(p99, 1e-3):
        problems.append(f"click at the end: last sample {end_jump:.4f} > p99 step {p99:.4f} "
                        "(fade out over >= 5 ms)")
    res = {"file": path, "sr": sr, "channels": x.shape[1], "seconds": round(len(x) / sr, 4),
           "peak_dbfs": round(db(peak), 2), "true_peak_dbtp": round(db(tp), 2),
           "dc": round(dc, 5), "end_sample": round(end_jump, 5)}
    if len(x) / sr >= 0.4:
        integrated, lra, source = loudness(x, sr)
        res.update(lufs_i=None if integrated is None else round(integrated, 2),
                   lra=None if lra is None else round(lra, 2), loudness_by=source)
        if target is not None and integrated is not None and abs(integrated - target) > tol:
            problems.append(f"loudness {integrated:.1f} LUFS, target {target}±{tol}")
    else:
        rms = np.sqrt((x ** 2).mean()) if x.size else 0
        res.update(lufs_i=None, rms_dbfs=round(db(rms), 2),
                   note="shorter than 0.4 s: no integrated loudness; compare peak + RMS")
    res.update(problems=problems, verdict="fail" if problems else "pass")
    return res


def check_loop(path, bpm, bars, beats_per_bar):
    x, sr = read_audio(path)
    expected = bars * beats_per_bar * 60.0 / bpm * sr
    steps = np.abs(np.diff(x, axis=0)).max(axis=1)
    p99 = float(np.percentile(steps, 99)) if len(steps) else 0.0
    jump = float(np.abs(x[0] - x[-1]).max())
    problems = []
    if abs(len(x) - expected) >= 1:
        problems.append(f"length {len(x)} samples, expected {expected:.1f} "
                        f"({bars} bars x {beats_per_bar} beats at {bpm} BPM)")
    if expected != int(expected):
        problems.append("one bar is not a whole number of samples at this BPM/rate; pick a BPM "
                        "that divides 60*sr (48 kHz: 90, 96, 100, 120, 125, 128, 144, 150, 160)")
    if jump > p99:
        problems.append(f"seam jump {jump:.4f} > p99 step {p99:.4f}: click at the loop point "
                        "(render two cycles and keep the second)")
    return {"file": path, "samples": len(x), "expected": round(expected, 2),
            "seam_jump": round(jump, 5), "p99_step": round(p99, 5), "problems": problems,
            "verdict": "fail" if problems else "pass"}


def check_stems(paths, mix):
    loaded = [read_audio(p) for p in paths]
    problems = []
    rates = {sr for _, sr in loaded}
    lengths = {len(x) for x, _ in loaded}
    if len(rates) > 1:
        problems.append(f"sample rates differ: {sorted(rates)}")
    if len(lengths) > 1:
        problems.append(f"lengths differ: {sorted(lengths)} samples")
    res = {"stems": paths, "lengths": sorted(lengths), "rates": sorted(rates)}
    if mix and not problems:
        m, _ = read_audio(mix)
        total = sum(x for x, _ in loaded)
        n = min(len(m), len(total))
        if m.shape[1] != total.shape[1]:
            problems.append("mix and stems have different channel counts")
        else:
            residual = db(np.abs(total[:n] - m[:n]).max())
            res["null_residual_dbfs"] = round(residual, 1)
            if residual > -60:
                problems.append(f"stems do not sum to the mix (residual {residual:.1f} dBFS)")
    res.update(problems=problems, verdict="fail" if problems else "pass")
    return res


def max_xcorr(a, b):
    a, b = a - a.mean(), b - b.mean()
    n = len(a) + len(b)
    c = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    norm = np.sqrt((a ** 2).sum() * (b ** 2).sum())
    return float(np.abs(c).max() / norm) if norm else 1.0


def check_variations(paths, limit):
    mono = [read_audio(p)[0].mean(axis=1) for p in paths]
    pairs = []
    for (i, a), (j, b) in itertools.combinations(enumerate(mono), 2):
        pairs.append((round(max_xcorr(a, b), 3), paths[i], paths[j]))
    worst = max(pairs) if pairs else (0.0, "", "")
    problems = [f"{a} and {b} correlate {c} (> {limit}): too similar"
                for c, a, b in pairs if c > limit]
    return {"files": len(paths), "max_corr": worst[0], "problems": problems,
            "verdict": "fail" if problems else "pass"}


def check_rt60(path, target, tol):
    x, sr = read_audio(path)
    h = x.mean(axis=1)
    h = h[int(np.abs(h).argmax()):]
    edc = np.cumsum((h ** 2)[::-1])[::-1]
    edc_db = 10 * np.log10(np.maximum(edc / edc[0], 1e-20))
    t = np.arange(len(h)) / sr
    sel = (edc_db <= -5) & (edc_db >= -25)
    if sel.sum() < 10:
        return {"file": path, "verdict": "fail", "problems": ["decay range too short for T20"]}
    slope = np.polyfit(t[sel], edc_db[sel], 1)[0]
    rt = -60.0 / slope
    problems = []
    if edc_db.min() > -35:
        problems.append("less than 35 dB of decay above the noise floor; result unreliable")
    if target is not None and abs(rt / target - 1) > tol:
        problems.append(f"RT60 {rt:.2f} s, target {target} s ±{tol * 100:.0f}%")
    return {"file": path, "rt60_t20": round(float(rt), 3), "problems": problems,
            "verdict": "fail" if problems else "pass"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("asset")
    a.add_argument("files", nargs="+")
    a.add_argument("--target-lufs", type=float, default=None)
    a.add_argument("--tol", type=float, default=1.5)
    a.add_argument("--ceiling", type=float, default=-1.0, help="true-peak ceiling, dBTP")
    lp = sub.add_parser("loop")
    lp.add_argument("files", nargs="+")
    lp.add_argument("--bpm", type=float, required=True)
    lp.add_argument("--bars", type=int, required=True)
    lp.add_argument("--beats-per-bar", type=int, default=4)
    st = sub.add_parser("stems")
    st.add_argument("files", nargs="+")
    st.add_argument("--mix", default=None)
    va = sub.add_parser("variations")
    va.add_argument("files", nargs="+")
    va.add_argument("--max-corr", type=float, default=0.9)
    rt = sub.add_parser("rt60")
    rt.add_argument("files", nargs="+")
    rt.add_argument("--target", type=float, default=None)
    rt.add_argument("--tol", type=float, default=0.2)
    args = parser.parse_args(argv)
    if hasattr(args, "files"):
        args.files = expand(args.files)
    if args.cmd == "asset":
        results = [check_asset(f, args.target_lufs, args.tol, args.ceiling) for f in args.files]
    elif args.cmd == "loop":
        results = [check_loop(f, args.bpm, args.bars, args.beats_per_bar) for f in args.files]
    elif args.cmd == "stems":
        results = [check_stems(args.files, args.mix)]
    elif args.cmd == "variations":
        results = [check_variations(args.files, args.max_corr)]
    else:
        results = [check_rt60(f, args.target, args.tol) for f in args.files]
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(results if len(results) > 1 else results[0], indent=1))
    sys.exit(0 if all(r["verdict"] == "pass" for r in results) else 1)


if __name__ == "__main__":
    main()
