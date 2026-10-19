"""Video reference for animation: frames, 2D keypoints, the cycle, key poses, gates on the clip,
and our render compared with the reference. Normal Python (numpy; Pillow for frames); `pose`
needs rtmlib (tools_check.py install pose, on the user's yes); `frames` needs ffmpeg.

  python video_ref.py frames ref.mp4 --out art/source/<char>/anim_ref/walk [--fps 30]
  python video_ref.py pose <frames dir> --out walk.kp.json [--mode balanced]
  python video_ref.py period walk.kp.json            # cycle length and the best loop cut
  python video_ref.py keys walk.kp.json              # contact and extreme frames per cycle
  python video_ref.py gate walk.kp.json [--frames <dir>] [--loop]   # is the clip usable?
  python video_ref.py compare ref.kp.json ours.kp.json [--noise noise.json]
  python video_ref.py noise ours_estimated.kp.json ours_true.kp.json --out noise.json

Keypoints: {"format": "kiln-keypoints/1", "layout": "coco17", "fps": .., "frames": [{"kp":
[[x, y, score] x 17]} | null]}, image pixels, y down. Run the same estimator on the reference and
on our render so its bias cancels; `noise` measures it on our render against the true projected
joints and every threshold becomes max(listed value, 2 sigma).
Gates (reject the clip before authoring; working values, research 2026-10-19):
  confidence   mean score >= 0.5 on >= 90 % of frames
  scale        body height one cycle apart changes <= 3 %
  limbs        thigh, shank, upper arm, forearm lengths one cycle apart change <= 5 %
  camera       (--frames) background shift <= 1 px per frame and <= 0.5 % of the width overall
  seam         (--loop) pose distance at the best cut <= 0.03 H
Compare (our clip against the reference): period within 3 %; key poses (contacts, extremes)
within 1 frame at 30 fps; DTW warp within 1 frame mean, 2 max; sagittal joint angles (hip,
knee, shoulder, elbow) RMSE <= 8 degrees and extremes within 10; PCK at 0.05 H >= 0.85.
The clip guides timing and key poses only: Kiln's joint limits, phase, slip and seam rules win
when they disagree. Exit 1 on a fail.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

import numpy as np

LSHO, RSHO, LELB, RELB, LWRI, RWRI, LHIP, RHIP, LKNE, RKNE, LANK, RANK = range(5, 17)
LIMBS = {"thigh_l": (LHIP, LKNE), "thigh_r": (RHIP, RKNE), "shank_l": (LKNE, LANK),
         "shank_r": (RKNE, RANK), "upper_arm_l": (LSHO, LELB), "upper_arm_r": (RSHO, RELB),
         "forearm_l": (LELB, LWRI), "forearm_r": (RELB, RWRI)}
FPS_OUT = 30.0


# --- keypoints ----------------------------------------------------------------------------------

def load(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    frames = data["frames"]
    kp = np.full((len(frames), 17, 3), np.nan)
    for i, f in enumerate(frames):
        if f and f.get("kp"):
            kp[i] = np.asarray(f["kp"], float)[:17]
    return data, kp


def fill_gaps(kp):
    """Linear interpolation over missing frames, per coordinate."""
    out = kp.copy()
    t = np.arange(len(kp))
    for j in range(17):
        for c in range(3):
            v = out[:, j, c]
            ok = ~np.isnan(v)
            if ok.sum() >= 2 and not ok.all():
                out[:, j, c] = np.interp(t, t[ok], v[ok])
    return out


def resample(kp, fps, fps_out=FPS_OUT):
    if abs(fps - fps_out) < 1e-6:
        return kp
    n = int(round(len(kp) * fps_out / fps))
    src = np.arange(len(kp)) / fps
    dst = np.arange(n) / fps_out
    out = np.empty((n, 17, 3))
    for j in range(17):
        for c in range(3):
            out[:, j, c] = np.interp(dst, src, kp[:, j, c])
    return out


def body_height(kp):
    """Median head-to-ankle height (the reference's own scale)."""
    head = np.nanmin(kp[:, :5, 1], axis=1)
    feet = np.nanmax(kp[:, [LANK, RANK], 1], axis=1)
    return float(np.nanmedian(feet - head))


def normalised(kp, H=None):
    """Positions relative to the hip centre, in body heights."""
    H = H or body_height(kp)
    hip = (kp[:, LHIP, :2] + kp[:, RHIP, :2]) / 2
    return (kp[:, :, :2] - hip[:, None, :]) / H


def angle(a, b, c):
    """Flexion at b in degrees: 0 = straight line a-b-c."""
    u, v = a - b, c - b
    cos = (u * v).sum(-1) / (np.linalg.norm(u, axis=-1) * np.linalg.norm(v, axis=-1) + 1e-9)
    return 180.0 - np.degrees(np.arccos(np.clip(cos, -1, 1)))


def joint_angles(kp):
    p = kp[:, :, :2]
    sho = (p[:, LSHO] + p[:, RSHO]) / 2
    hip = (p[:, LHIP] + p[:, RHIP]) / 2
    above = 2 * sho - hip                         # the trunk line continued above the shoulders
    return {"knee_l": angle(p[:, LHIP], p[:, LKNE], p[:, LANK]),
            "knee_r": angle(p[:, RHIP], p[:, RKNE], p[:, RANK]),
            "elbow_l": angle(p[:, LSHO], p[:, LELB], p[:, LWRI]),
            "elbow_r": angle(p[:, RSHO], p[:, RELB], p[:, RWRI]),
            "hip_l": angle(sho, hip, p[:, LKNE]) * np.sign(_side(sho, hip, p[:, LKNE])),
            "hip_r": angle(sho, hip, p[:, RKNE]) * np.sign(_side(sho, hip, p[:, RKNE])),
            "shoulder_l": angle(above, sho, p[:, LELB]) * np.sign(_side(above, sho, p[:, LELB])),
            "shoulder_r": angle(above, sho, p[:, RELB]) * np.sign(_side(above, sho, p[:, RELB]))}


def _side(a, b, c):
    """Which side of the line a-b the point c is on (forward / back in a side view)."""
    d, e = b - a, c - b
    s = d[:, 0] * e[:, 1] - d[:, 1] * e[:, 0]
    return np.where(s == 0, 1.0, s)


# --- cycle --------------------------------------------------------------------------------------

def period(norm, min_frames=8):
    """Cycle length in frames from the autocorrelation of the pose vector."""
    x = norm.reshape(len(norm), -1)
    x = x - x.mean(0)
    n = len(x)
    best, best_lag = -1.0, None
    scores = []
    for lag in range(min_frames, n // 2 + 1):
        a, b = x[:-lag], x[lag:]
        s = float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-12))
        scores.append((lag, s))
    for i in range(1, len(scores) - 1):          # first strong local maximum
        lag, s = scores[i]
        if s >= scores[i - 1][1] and s >= scores[i + 1][1] and s > 0.5:
            best, best_lag = s, lag
            break
    if best_lag is None and scores:
        best_lag, best = max(scores, key=lambda q: q[1])
    if best_lag is None:
        return None, 0.0
    # parabolic refinement around the peak
    s = dict(scores)
    if best_lag - 1 in s and best_lag + 1 in s:
        y0, y1, y2 = s[best_lag - 1], s[best_lag], s[best_lag + 1]
        den = y0 - 2 * y1 + y2
        if den < 0:
            return best_lag + 0.5 * (y0 - y2) / den, best
    return float(best_lag), best


def best_cut(norm, T):
    T = int(round(T))
    d = [float(np.linalg.norm(norm[i] - norm[i + T], axis=-1).mean())
         for i in range(0, len(norm) - T)]
    i = int(np.argmin(d))
    return i, d[i]


def keys(kp, T):
    """Contacts (the frame an ankle comes down to the ground band) and swing knee peaks, as
    frame indices within the clip."""
    out = {}
    ang = joint_angles(kp)
    H = body_height(kp)
    half = max(2, int(round(T / 2)))
    n = len(kp)
    for side, ank in (("l", LANK), ("r", RANK)):
        y = kp[:, ank, 1]                          # image y grows downward: ground = largest
        hits = []
        for i in range(1, n):
            lo, hi = max(0, i - half), min(n, i + half + 1)
            band = np.nanmax(y[lo:hi]) - 0.03 * H
            if y[i] >= band > y[i - 1]:
                hits.append(i)
        out[f"contact_{side}"] = _dedupe(hits, half)
        k = ang[f"knee_{side}"]
        peaks = []
        for i in range(1, n - 1):
            lo, hi = max(0, i - half), min(n, i + half + 1)
            top, bottom = np.nanmax(k[lo:hi]), np.nanmin(k[lo:hi])
            if k[i] == top and k[i] >= bottom + 0.6 * (top - bottom) and top - bottom > 5:
                peaks.append(i)
        out[f"knee_{side}_max"] = _dedupe(peaks, half)
    return out


def _dedupe(hits, gap):
    """One key per event: runs of nearby hits (a held pose) become their middle."""
    runs = []
    for i in hits:
        if runs and i - runs[-1][-1] < gap:
            runs[-1].append(i)
        else:
            runs.append([i])
    return [r[len(r) // 2] for r in runs]


# --- commands -----------------------------------------------------------------------------------

def cmd_frames(a):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is needed to read video (the tools skill can install it)")
    os.makedirs(a.out, exist_ok=True)
    argv = [ffmpeg, "-v", "error", "-y"]
    if a.start:
        argv += ["-ss", str(a.start)]
    argv += ["-i", a.video]
    if a.dur:
        argv += ["-t", str(a.dur)]
    argv += ["-vf", f"fps={a.fps}", os.path.join(a.out, "%05d.png")]
    p = subprocess.run(argv, capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(f"ffmpeg failed: {p.stderr[-400:]}")
    files = sorted(glob.glob(os.path.join(a.out, "*.png")))
    from PIL import Image
    size = Image.open(files[0]).size if files else None
    meta = {"format": "kiln-frames/1", "video": os.path.basename(a.video), "fps": a.fps,
            "count": len(files), "size": size}
    with open(os.path.join(a.out, "frames.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    return meta, 0


def pose_python():
    """A Python with rtmlib: this one, or the venv tools_check.py installed (machine.json)."""
    try:
        import rtmlib  # noqa: F401
        return None
    except ImportError:
        pass
    home = os.environ.get("KILN_HOME") or os.path.join(os.path.expanduser("~"), ".kiln")
    try:
        with open(os.path.join(home, "machine.json"), encoding="utf-8-sig") as fh:
            py = (json.load(fh).get("tools") or {}).get("pose", {}).get("path")
    except (OSError, ValueError):
        py = None
    if py and os.path.isfile(py):
        return py
    raise SystemExit("no pose estimator: `tools_check.py install pose` (asks the user first; "
                     "rtmlib, Apache-2.0, CPU)")


def cmd_pose(a):
    py = pose_python()
    if py:
        p = subprocess.run([py, os.path.abspath(__file__), "pose", a.frames, "--out", a.out,
                            "--mode", a.mode], capture_output=True, text=True)
        sys.stdout.write(p.stdout)
        return None, p.returncode
    import cv2
    from rtmlib import Body
    meta_path = os.path.join(a.frames, "frames.json")
    fps = FPS_OUT
    if os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8") as fh:
            fps = json.load(fh).get("fps", fps)
    body = Body(mode=a.mode, to_openpose=False, backend="onnxruntime", device="cpu")
    frames = []
    files = sorted(glob.glob(os.path.join(a.frames, "*.png")))
    for f in files:
        img = cv2.imread(f)
        kps, scores = body(img)
        if kps is None or not len(kps):
            frames.append(None)
            continue
        best = int(np.argmax([np.mean(s) * (np.ptp(k[:, 1]) + 1) for k, s in zip(kps, scores)]))
        frames.append({"kp": [[float(x), float(y), float(s)] for (x, y), s in
                              zip(kps[best][:17], scores[best][:17])]})
    h, w = (cv2.imread(files[0]).shape[:2]) if files else (0, 0)
    out = {"format": "kiln-keypoints/1", "layout": "coco17", "fps": fps, "size": [w, h],
           "estimator": f"rtmlib Body ({a.mode})", "frames": frames}
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    return {"out": a.out, "frames": len(frames), "missing": sum(f is None for f in frames)}, 0


def cmd_period(a):
    data, kp = load(a.kp)
    kp = resample(fill_gaps(kp), data.get("fps", FPS_OUT))
    norm = normalised(kp)
    T, score = period(norm)
    if T is None:
        raise SystemExit("no repeating cycle found")
    cut, dist = best_cut(norm, T)
    return {"period_frames": round(T, 2), "period_s": round(T / FPS_OUT, 3), "fps": FPS_OUT,
            "correlation": round(score, 3), "loop_cut": [cut, cut + int(round(T))],
            "seam_H": round(dist, 4)}, 0


def cmd_keys(a):
    data, kp = load(a.kp)
    kp = resample(fill_gaps(kp), data.get("fps", FPS_OUT))
    T, _ = period(normalised(kp))
    return {"fps": FPS_OUT, "period_frames": round(T, 2) if T else None,
            "keys": keys(kp, T or len(kp))}, 0


def camera_shift(frames_dir, kp, fps):
    """Median and total background shift between frames (phase correlation, subject masked)."""
    from PIL import Image
    files = sorted(glob.glob(os.path.join(frames_dir, "*.png")))
    prev, shifts, total = None, [], np.zeros(2)
    width = None
    for i, f in enumerate(files):
        img = np.asarray(Image.open(f).convert("L"), float)
        width = img.shape[1]
        k = kp[min(i, len(kp) - 1)] if len(kp) else None
        if k is not None and not np.isnan(k[:, :2]).all():
            x0, y0 = np.nanmin(k[:, :2], 0)
            x1, y1 = np.nanmax(k[:, :2], 0)
            pad = 0.25 * (y1 - y0)
            img[int(max(0, y0 - pad)):int(y1 + pad), int(max(0, x0 - pad)):int(x1 + pad)] = img.mean()
        if prev is not None:
            F = np.fft.fft2(prev) * np.conj(np.fft.fft2(img))
            r = np.fft.ifft2(F / (np.abs(F) + 1e-9)).real
            dy, dx = np.unravel_index(np.argmax(r), r.shape)
            dy = dy - r.shape[0] if dy > r.shape[0] / 2 else dy
            dx = dx - r.shape[1] if dx > r.shape[1] / 2 else dx
            shifts.append(np.hypot(dx, dy))
            total += (dx, dy)
        prev = img
    return (float(np.median(shifts)) if shifts else 0.0,
            float(np.hypot(*total)) / (width or 1))


def cmd_gate(a):
    data, raw = load(a.kp)
    fps = data.get("fps", FPS_OUT)
    scores = np.nanmean(raw[:, :, 2], axis=1)
    conf = float(np.mean(np.nan_to_num(scores) >= 0.5))
    kp = fill_gaps(raw)
    norm = normalised(kp)
    T, _ = period(norm)
    gates = {"confidence": {"share_of_frames": round(conf, 3), "limit": 0.9,
                            "verdict": "pass" if conf >= 0.9 else "fail"}}
    # a pose repeated on consecutive frames: the video holds frames (a lower real frame rate),
    # so key timing cannot be read finer than the hold
    step = np.linalg.norm(np.diff(normalised(fill_gaps(raw)), axis=0), axis=-1).mean(-1)
    moving = float(np.percentile(step, 75)) if len(step) else 0.0
    held = float(np.mean(step < 0.05 * moving)) if moving > 0 else 1.0
    gates["held_frames"] = {"share": round(held, 3), "limit": 0.2,
                            "verdict": "pass" if held <= 0.2 else "fail"}
    if T:
        lag = int(round(T))
        heights = np.nanmax(kp[:, [LANK, RANK], 1], 1) - np.nanmin(kp[:, :5, 1], 1)
        scale = np.abs(heights[lag:] / heights[:-lag] - 1)
        gates["scale"] = {"p90_change": round(float(np.nanpercentile(scale, 90)), 4),
                          "limit": 0.03,
                          "verdict": "pass" if np.nanpercentile(scale, 90) <= 0.03 else "fail"}
        worst = {}
        for name, (i, j) in LIMBS.items():
            length = np.linalg.norm(kp[:, i, :2] - kp[:, j, :2], axis=1)
            worst[name] = float(np.nanpercentile(np.abs(length[lag:] / length[:-lag] - 1), 90))
        top = max(worst.values())
        gates["limbs"] = {"p90_change": {k: round(v, 4) for k, v in worst.items()},
                          "limit": 0.05, "verdict": "pass" if top <= 0.05 else "fail"}
        if a.loop:
            _, seam = best_cut(norm, T)
            gates["seam"] = {"H": round(seam, 4), "limit": 0.03,
                             "verdict": "pass" if seam <= 0.03 else "fail"}
    else:
        gates["cycle"] = {"verdict": "fail", "why": "no repeating cycle found"}
    if a.frames:
        per_frame, total = camera_shift(a.frames, raw, fps)
        gates["camera"] = {"median_px_per_frame": round(per_frame, 2),
                           "total_of_width": round(total, 4), "limit": [1.0, 0.005],
                           "verdict": "pass" if per_frame <= 1.0 and total <= 0.005 else "fail"}
    verdict = "fail" if any(g["verdict"] == "fail" for g in gates.values()) else "pass"
    return {"gates": gates, "verdict": verdict,
            "next": "pass: author the key poses against it; fail: regenerate or cut elsewhere"}, \
        1 if verdict == "fail" else 0


def dtw(a, b, band):
    """DTW path between two sequences of pose vectors (Sakoe-Chiba band)."""
    n, m = len(a), len(b)
    cost = np.full((n + 1, m + 1), np.inf)
    cost[0, 0] = 0
    for i in range(1, n + 1):
        lo, hi = max(1, i - band), min(m, i + band)
        for j in range(lo, hi + 1):
            d = np.linalg.norm(a[i - 1] - b[j - 1])
            cost[i, j] = d + min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])
    i, j, path = n, m, []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        step = np.argmin([cost[i - 1, j - 1], cost[i - 1, j], cost[i, j - 1]])
        i, j = (i - 1, j - 1) if step == 0 else (i - 1, j) if step == 1 else (i, j - 1)
    return path[::-1]


def cycle_keys(kc):
    """Keys of one cycle, found on the cycle repeated three times (no edge effects)."""
    n = len(kc)
    found = keys(np.concatenate([kc, kc, kc]), n)
    return {k: sorted({i - n for i in v if n <= i < 2 * n}) for k, v in found.items()}


def cycle(kp, norm, T):
    cut, _ = best_cut(norm, T)
    n = int(round(T))
    return kp[cut:cut + n], norm[cut:cut + n]


def cmd_compare(a):
    rdata, rkp = load(a.ref)
    odata, okp = load(a.ours)
    rkp = resample(fill_gaps(rkp), rdata.get("fps", FPS_OUT))
    okp = resample(fill_gaps(okp), odata.get("fps", FPS_OUT))
    H = body_height(rkp)
    rnorm, onorm = normalised(rkp, H), normalised(okp, body_height(okp))
    Tr, _ = period(rnorm)
    To, _ = period(onorm)
    if not Tr or not To:
        raise SystemExit("no repeating cycle in one of the clips")
    noise = {}
    if a.noise:
        with open(a.noise, encoding="utf-8") as fh:
            noise = json.load(fh)
    rk, rn = cycle(rkp, rnorm, Tr)
    ok, on = cycle(okp, onorm, To)
    # bring our cycle to the reference's length, then the best circular phase
    t = np.linspace(0, len(on) - 1, len(rn))
    on = np.stack([np.stack([np.interp(t, np.arange(len(on)), on[:, j, c]) for c in range(2)], -1)
                   for j in range(17)], 1)
    ok = np.stack([np.stack([np.interp(t, np.arange(len(ok)), ok[:, j, c]) for c in range(3)], -1)
                   for j in range(17)], 1)
    shifts = [np.linalg.norm(rn - np.roll(on, s, 0), axis=-1).mean() for s in range(len(rn))]
    s = int(np.argmin(shifts))
    on, ok = np.roll(on, s, 0), np.roll(ok, s, 0)
    band = max(1, int(round(0.1 * len(rn))))
    path = dtw(rn.reshape(len(rn), -1), on.reshape(len(on), -1), band)
    warp = [abs(i - j) for i, j in path]
    ra, oa = joint_angles(rk), joint_angles(ok)
    angles = {}
    for name in ra:
        lim = max(8.0, 2 * noise.get("angle_sigma", {}).get(name, 0))
        d = ra[name] - oa[name]
        rmse = float(np.sqrt(np.nanmean(d ** 2)))
        ext = max(abs(float(np.nanmax(ra[name]) - np.nanmax(oa[name]))),
                  abs(float(np.nanmin(ra[name]) - np.nanmin(oa[name]))))
        angles[name] = {"rmse": round(rmse, 2), "extremes": round(ext, 2), "limit": [lim, 10.0],
                        "verdict": "pass" if rmse <= lim and ext <= 10 else "fail"}
    pck_tol = max(0.05, 2 * noise.get("position_sigma_H", 0))
    pck = float(np.mean(np.linalg.norm(rn - on, axis=-1) <= pck_tol))
    n = len(rk)
    rkeys, okeys = cycle_keys(rk), cycle_keys(ok)
    # a key cannot be placed finer than one source frame
    tol = max(1, int(np.ceil(FPS_OUT / min(rdata.get("fps", FPS_OUT), odata.get("fps", FPS_OUT)))))
    timing = {}
    for name in rkeys:
        diffs = [min((min(abs(i - j), n - abs(i - j)) for j in okeys[name]), default=99)
                 for i in rkeys[name]]
        worst = max(diffs) if diffs else 0
        timing[name] = {"frames_off": worst, "limit": tol, "verdict": "pass" if worst <= tol else "fail"}
    per = abs(To / Tr - 1)
    checks = {"period": {"ref_frames": round(Tr, 2), "ours_frames": round(To, 2),
                         "change": round(per, 4), "limit": 0.03,
                         "verdict": "pass" if per <= 0.03 else "fail"},
              "warp": {"mean": round(float(np.mean(warp)), 2), "max": int(max(warp)),
                       "limit": [1, 2],
                       "verdict": "pass" if np.mean(warp) <= 1 and max(warp) <= 2 else "fail"},
              "pck": {"value": round(pck, 3), "tolerance_H": pck_tol, "limit": 0.85,
                      "verdict": "pass" if pck >= 0.85 else "fail"},
              "angles": angles, "key_timing": timing}
    fails = [k for k, v in checks.items() if isinstance(v, dict) and v.get("verdict") == "fail"]
    fails += [f"angle {k}" for k, v in angles.items() if v["verdict"] == "fail"]
    fails += [f"timing {k}" for k, v in timing.items() if v["verdict"] == "fail"]
    return {"fps": FPS_OUT, "phase_shift_frames": s, "checks": checks, "fails": fails,
            "verdict": "fail" if fails else "pass",
            "rule": "the reference guides timing and key poses; Kiln's joint limits, phase, slip "
                    "and seam rules win"}, 1 if fails else 0


def cmd_noise(a):
    edata, ekp = load(a.estimated)
    tdata, tkp = load(a.truth)
    n = min(len(ekp), len(tkp))
    ekp, tkp = fill_gaps(ekp[:n]), fill_gaps(tkp[:n])
    H = body_height(tkp)
    pos = np.linalg.norm(ekp[:, :, :2] - tkp[:, :, :2], axis=-1) / H
    ea, ta = joint_angles(ekp), joint_angles(tkp)
    out = {"position_sigma_H": round(float(np.nanstd(pos) + np.nanmean(pos)), 4),
           "angle_sigma": {k: round(float(np.nanstd(ea[k] - ta[k])), 2) for k in ea}}
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return out, 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("frames")
    f.add_argument("video")
    f.add_argument("--out", required=True)
    f.add_argument("--fps", type=float, default=FPS_OUT)
    f.add_argument("--start", type=float, default=0)
    f.add_argument("--dur", type=float, default=0)
    p = sub.add_parser("pose")
    p.add_argument("frames")
    p.add_argument("--out", required=True)
    p.add_argument("--mode", default="balanced", choices=["lightweight", "balanced", "performance"])
    for name in ("period", "keys"):
        sub.add_parser(name).add_argument("kp")
    g = sub.add_parser("gate")
    g.add_argument("kp")
    g.add_argument("--frames")
    g.add_argument("--loop", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("ref")
    c.add_argument("ours")
    c.add_argument("--noise")
    n = sub.add_parser("noise")
    n.add_argument("estimated")
    n.add_argument("truth")
    n.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        out, code = globals()["cmd_" + a.cmd](a)
    except SystemExit as e:
        if isinstance(e.code, int):
            raise
        print(json.dumps({"error": str(e.code)}))
        return 1
    if out is not None:
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(out, indent=1))
    return code


if __name__ == "__main__":
    sys.exit(main())
