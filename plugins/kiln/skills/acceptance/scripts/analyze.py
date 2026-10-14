"""Metrics over probe recordings (Python 3.12+, numpy).

Reads both probe formats:
  JSON        one object, written by recorder.gd (Godot): physics_ticks_per_second, ticks,
              samples {name: [value per tick]}, frame_ms [per frame], gpu_ms, ...
  JSON Lines  one object per line, written by KilnProbe.cs (Unity) and UKilnProbeComponent
              (Unreal): a "header" line (physics_hz, units_per_meter, up), "tick" lines
              ({"tick", "t", <channel>: value}), "frame" lines ({"dt_ms", "gpu_ms", ...}) and
              an "end" line. Lines without "type" are ticks. Any line with "dt_ms" is a frame.
Positions are converted to metres and Y-up from the header (Unreal: cm, Z-up), so the
thresholds below are in metres and seconds for every engine.

  python analyze.py skating <dump> --foot heel_l,ball_l,toe_l [--contact-flag stance_l]
         [--ground <probe>] [--contact 0.05] [--slip-speed 0.15] [--max-ratio 0.05]
      foot skating ratio (share of contact ticks where the planted foot moves faster than
      --slip-speed m/s horizontally) and mean planted-foot speed. Foot probes = world positions
      of sole points (not the ankle); per tick pair the least-moving point in contact counts, so
      a forefoot rolling about the toe joint is not skating. Contact = --contact-flag probe
      (> 0.5: the authored stance window or a planted flag) when given, else height below
      --contact; with height alone a low swing toe and the heel strike count as planted.
      Ground probe = ground height (number) or ground point (vector) under the foot, else 0.
  python analyze.py stance <dump> --feet heel_l+toe_l,heel_r+toe_r [--contact-flag <probe>]
         [--root hero] [--ground <probe>] [--contact 0.05] [--min-stance 0.05] [--max-slip 0.02]
         [--turn-deg 10]
      slip per stance: horizontal distance each planted foot travels from touch-down to lift-off
      (perception threshold ~21 mm, Prazak 2011); with --root, stances during which the root's
      heading turns >= --turn-deg are reported separately (direction changes are where feet
      skate). FAIL if any stance slips more than --max-slip.
  python analyze.py gait <dump> --pelvis hips_root [--hips hip_l,hip_r] [--feet foot_l,foot_r]
         [--max-shift 0.025] [--max-obliquity 5] [--max-rotation 5] [--min-width 0.08]
         [--max-width 0.12 | --foot-width M] [--window-s 1.5] [--ref-stride M --ref-cadence SPM --keep-tol 0.03]
      hip sway over a walk (record >= 10 gait cycles on a straight or gently curved path):
      lateral pelvis shift from the travel line (curves removed by a moving average), pelvis
      obliquity and rotation from the hip joints, step width and midline-crossing steps from the
      foot contacts. A catwalk or drunk walk fails (big sway, crossing steps). With --feet it also
      reports stride length (pelvis travel between touch-downs of the same foot) and cadence;
      --ref-stride / --ref-cadence fail a fix that moves them more than --keep-tol.
  python analyze.py idle <dump> --pos pelvis [--chest chest] [--bones arm_l,head,...]
         [--ap-axis z] [--ap-min 1 --ap-max 8] [--ml-min 0.5 --ml-max 4] [--min-deg 0.5]
      an idle that is alive but calm (record >= 60 s): pelvis/CoM sway RMS front-back and
      side within the ranges (quiet-standing data: AP 2-8 mm, ML 1-4 mm), >= 80 % of sway power
      below 0.5 Hz; with --chest, a breathing peak at 0.2-0.33 Hz (12-20/min) in the chest-pelvis
      distance, which must move >= --min-breath-mm (2) peak to peak - below that the report
      says "breathing invisible" instead of a rate (the loop length dominates the spectrum);
      with --bones, no part frozen (< --min-deg peak-to-peak in a 10 s window).
  python analyze.py frames <dump> [--budget-ms 16.67] [--skip 0]
      frame-time mean, p95, p99, 1% low fps, hitches (> 2x rolling median or > 50 ms);
      GPU/CPU render times when recorded. --skip drops the first N frames (loading).
  python analyze.py settle <dump> --pos <probe> [--speed 0.03] [--max-s 5]
      first time after which the body stays below --speed m/s (debris sleep / death collapse).
  python analyze.py reaction <dump> --input <probe> --response <probe> [--max-ticks 2]
         [--eps 0]
      ticks and ms from the first input change to the first response change.

<dump> may be a glob (quote it). One file prints one JSON object {metric, value, threshold,
verdict, file, ...}; several files print {"verdict", "results": [...]} where verdict is FAIL if
any file fails. verdict is PASS, FAIL or NOT ASSESSED (missing file or probe). Exit code 0 when
the analysis ran, 1 when nothing matched the pattern.
"""

import argparse
import glob
import json
import math
import os
import sys

import numpy as np

RESERVED = {"type", "tick", "t", "frame", "dt_ms", "gpu_ms", "cpu_ms", "main_ms", "render_ms",
            "game_ms", "cpu_render_ms"}


class NotAssessed(Exception):
    """Input cannot answer the question (missing probe, empty recording)."""


def _from_json(raw):
    hz = float(raw.get("physics_ticks_per_second") or 60)
    ticks = list(raw.get("ticks") or [])
    samples = raw.get("samples") or {}
    n = len(ticks) or max((len(v) for v in samples.values()), default=0)
    start = ticks[0] if ticks else 0
    times = [(tk - start) / hz for tk in ticks] if ticks else [i / hz for i in range(n)]
    return {
        "hz": hz, "times": times, "samples": samples,
        "frame_ms": list(raw.get("frame_ms") or []),
        "gpu_ms": list(raw.get("gpu_ms") or []),
        "cpu_ms": list(raw.get("cpu_render_ms") or []),
        "up": 1, "scale": 1.0, "meta": {k: raw[k] for k in ("format", "engine") if k in raw},
    }


def _from_jsonl(lines):
    header, ticks, frames = {}, [], []
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            if number == len(lines):  # last line cut off while the probe was still writing
                break
            raise NotAssessed(f"line {number} is not JSON: {exc}") from exc
        kind = obj.get("type", "tick")
        if kind == "header":
            header = obj
            continue
        if kind == "end":
            continue
        if "dt_ms" in obj:
            frames.append(obj)
        if kind in ("tick", "sample"):
            ticks.append(obj)
    hz = float(header.get("physics_hz") or 0)
    names = []
    for obj in ticks:
        for key in obj:
            if key not in RESERVED and key not in names:
                names.append(key)
    samples = {name: [obj.get(name) for obj in ticks] for name in names}
    if ticks and all("t" in obj for obj in ticks):
        t0 = float(ticks[0]["t"])
        times = [float(obj["t"]) - t0 for obj in ticks]
    else:
        step = 1.0 / (hz or 60.0)
        times = [i * step for i in range(len(ticks))]
    if not hz and len(times) > 1 and times[-1] > 0:
        hz = (len(times) - 1) / times[-1]
    up = str(header.get("up", "y")).lower()
    return {
        "hz": hz or 60.0, "times": times, "samples": samples,
        "frame_ms": [obj["dt_ms"] for obj in frames],
        "gpu_ms": [obj.get("gpu_ms", 0) for obj in frames],
        "cpu_ms": [obj.get("cpu_ms", obj.get("game_ms", 0)) for obj in frames],
        "up": {"x": 0, "y": 1, "z": 2}.get(up, 1),
        "scale": 1.0 / float(header.get("units_per_meter") or 1.0),
        "meta": {k: header[k] for k in ("format", "engine", "task", "run") if k in header},
    }


def load(path):
    """Normalised recording: hz, times (s), samples, frame_ms, gpu_ms, cpu_ms, up, scale."""
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    if not path.lower().endswith((".jsonl", ".ndjson")):
        try:
            raw = json.loads(text)
            if isinstance(raw, dict) and "samples" in raw:
                return _from_json(raw)
        except json.JSONDecodeError:
            pass
    return _from_jsonl(text.splitlines())


def _num(v):
    return math.nan if v is None else v


def series(d, name, vector=None):
    """Probe values as floats; vectors become (n, k) arrays, missing entries NaN."""
    if name not in d["samples"]:
        raise NotAssessed(f"probe '{name}' not in recording; probes: "
                          + ", ".join(sorted(d["samples"])))
    vals = d["samples"][name]
    width = next((len(v) for v in vals if isinstance(v, list)), 0)
    if width:
        rows = [[_num(x) for x in v] if isinstance(v, list) else [math.nan] * width for v in vals]
    else:
        rows = [_num(v) for v in vals]
    arr = np.asarray(rows, dtype=float)
    if vector is True and arr.ndim != 2:
        raise NotAssessed(f"probe '{name}' is not a position vector")
    return arr


def to_metres_y_up(d, pos):
    """(n, 3) positions in engine units/axes -> metres, column 1 = up."""
    pos = pos * d["scale"]
    if pos.ndim == 2 and pos.shape[1] >= 3 and d["up"] != 1:
        order = [0, 2, 1] if d["up"] == 2 else [1, 0, 2]
        pos = pos[:, order]
    return pos


def result(metric, value, threshold, ok, **extra):
    return {"metric": metric, "value": value, "threshold": threshold,
            "verdict": "PASS" if ok else "FAIL", **extra}


def _ground(d, a, n):
    if a.ground:
        g = series(d, a.ground)
        return to_metres_y_up(d, g)[:, 1] if g.ndim == 2 else g * d["scale"]
    return np.zeros(n)


def _sole(d, a, names):
    """[(position track, contact mask)] for one foot's sole points. Contact comes from the
    --contact-flag probe (authored stance window or planted flag) when given, else from height."""
    flag = None
    if getattr(a, "contact_flag", None):
        flag = np.asarray(series(d, a.contact_flag), dtype=float) > 0.5
    out = []
    for name in names:
        pos = to_metres_y_up(d, series(d, name, vector=True))
        contact = flag if flag is not None else (pos[:, 1] - _ground(d, a, len(pos))) < a.contact
        out.append((pos, contact))
    return out


def skating(d, a):
    """Skating ratio of the planted point: per tick pair the least-moving sole point that is in
    contact (heel, ball, toe) - a single point reads a forefoot roll as skating (g2 row 128)."""
    sole = _sole(d, a, [n.strip() for n in a.foot.split(",") if n.strip()])
    t = np.asarray(d["times"], dtype=float)
    dt = np.diff(t)
    dt[dt <= 0] = np.nan
    speeds = []
    for pos, contact in sole:
        v = np.linalg.norm(np.diff(pos[:, [0, 2]], axis=0), axis=1) / dt
        v[~(contact[1:] & contact[:-1])] = np.inf
        speeds.append(v)
    horiz = np.min(np.vstack(speeds), axis=0)
    planted = np.isfinite(horiz)
    heights = [pos[:, 1] - _ground(d, a, len(pos)) for pos, _ in sole]
    min_height = round(float(min(np.nanmin(h) for h in heights)), 4) if len(t) else None
    if not planted.any():
        return result("foot_skating_ratio", None, a.max_ratio, False,
                      note="no contact ticks detected (foot never below --contact, or the "
                           "--contact-flag probe is never on)", min_height=min_height)
    ratio = float((horiz[planted] > a.slip_speed).mean())
    return result("foot_skating_ratio", round(ratio, 4), a.max_ratio, ratio <= a.max_ratio,
                  planted_mean_speed=round(float(horiz[planted].mean()), 4),
                  planted_ticks=int(planted.sum()), min_height=min_height,
                  sole_points=len(sole), contact_from=a.contact_flag or "height")


def _contact(d, a, foot):
    return (foot[:, 1] - _ground(d, a, len(foot))) < a.contact


def stance(d, a):
    """Slip per stance: horizontal distance a planted foot travels between touch-down and
    lift-off (the least-moving of its sole points `heel+ball+toe`); stances during a turn (root
    heading change >= --turn-deg) reported separately."""
    t = np.asarray(d["times"], dtype=float)
    results = []
    heading = None
    if a.root:
        root = to_metres_y_up(d, series(d, a.root, vector=True))
        vel = np.gradient(root[:, [0, 2]], t, axis=0)
        speed = np.linalg.norm(vel, axis=1)
        heading = np.unwrap(np.arctan2(vel[:, 1], vel[:, 0]))
        heading[speed < 0.2] = np.nan  # standing: no heading
    worst, worst_turn, over, n_turn = 0.0, 0.0, 0, 0
    stances = 0
    for name in a.feet.split(","):
        sole = _sole(d, a, [n.strip() for n in name.split("+") if n.strip()])
        contact = np.any(np.vstack([c for _, c in sole]), axis=0)
        k = 0
        while k < len(contact):
            if not contact[k]:
                k += 1
                continue
            start = k
            while k < len(contact) and contact[k]:
                k += 1
            end = k - 1
            if t[end] - t[start] < a.min_stance:
                continue
            stances += 1
            planted = [pos for pos, c in sole if c[start] and c[end]] or [p for p, _ in sole]
            slip = min(float(np.linalg.norm(pos[end, [0, 2]] - pos[start, [0, 2]]))
                       for pos in planted)
            turning = False
            if heading is not None:
                h = heading[start:end + 1]
                h = h[np.isfinite(h)]
                turning = len(h) >= 2 and abs(math.degrees(h[-1] - h[0])) >= a.turn_deg
            worst = max(worst, slip)
            if turning:
                n_turn += 1
                worst_turn = max(worst_turn, slip)
            if slip > a.max_slip:
                over += 1
                results.append({"foot": name.strip(), "t_s": round(float(t[start]), 3),
                                "slip_m": round(slip, 4), "turning": turning})
    if not stances:
        raise NotAssessed("no stances detected (foot never below --contact long enough)")
    return result("stance_slip_max_m", round(worst, 4), a.max_slip, over == 0,
                  turning_slip_max_m=round(worst_turn, 4) if n_turn else None,
                  stances=stances, turning_stances=n_turn, stances_over=over,
                  examples=results[:10])


def gait(d, a):
    """Hip sway and step width over a walk: pelvis lateral shift (from the travel line), pelvis
    obliquity and rotation (from the hip joints), step width and crossing steps (from the feet)."""
    t = np.asarray(d["times"], dtype=float)
    pelvis = to_metres_y_up(d, series(d, a.pelvis, vector=True))
    xz = pelvis[:, [0, 2]]
    ok = np.all(np.isfinite(xz), axis=1)
    if ok.sum() < 30:
        raise NotAssessed("fewer than 30 pelvis samples")
    # travel line: least-squares fit of the horizontal path
    centre = xz[ok].mean(axis=0)
    _, _, vt = np.linalg.svd(xz[ok] - centre)
    fwd = vt[0]
    idx = np.nonzero(ok)[0]
    if (xz[idx[-1]] - xz[idx[0]]) @ fwd < 0:
        fwd = -fwd  # point along the actual travel
    side = np.array([fwd[1], -fwd[0]])  # left of travel: up x forward, Y-up, (x, z) coords
    along = (xz - centre) @ fwd
    # detrend the lateral offset with a slow moving average (keeps per-step sway, removes curves)
    lat = (xz - centre) @ side
    win = max(3, int(round(a.window_s * d["hz"])))
    kernel = np.ones(win) / win
    slow = np.convolve(np.nan_to_num(lat), kernel, mode="same")
    sway = lat - slow
    core = slice(win, len(sway) - win) if len(sway) > 3 * win else slice(None)
    lat_amp = float(np.nanmax(sway[core]) - np.nanmin(sway[core])) / 2
    out = {"lateral_shift_amp_m": round(lat_amp, 4),
           "distance_m": round(float(np.nanmax(along) - np.nanmin(along)), 2)}
    problems = []
    if lat_amp > a.max_shift:
        problems.append(f"lateral pelvis shift ±{lat_amp * 100:.1f} cm > ±{a.max_shift * 100:.1f}")
    if a.hips:
        hl, hr = (to_metres_y_up(d, series(d, n.strip(), vector=True)) for n in a.hips.split(","))
        v = hr - hl
        obliq = np.degrees(np.arctan2(v[:, 1], np.linalg.norm(v[:, [0, 2]], axis=1)))
        hip_dir = v[:, [0, 2]] / np.linalg.norm(v[:, [0, 2]], axis=1, keepdims=True)
        rot = np.degrees(np.arcsin(np.clip(hip_dir @ fwd, -1, 1)))
        o_amp = float(np.nanmax(obliq[core]) - np.nanmin(obliq[core])) / 2
        r_amp = float(np.nanmax(rot[core]) - np.nanmin(rot[core])) / 2
        out.update(obliquity_amp_deg=round(o_amp, 2), rotation_amp_deg=round(r_amp, 2))
        if o_amp > a.max_obliquity:
            problems.append(f"pelvis obliquity ±{o_amp:.1f}° > ±{a.max_obliquity}°")
        if r_amp > a.max_rotation:
            problems.append(f"pelvis rotation ±{r_amp:.1f}° > ±{a.max_rotation}°")
    if a.feet:
        if a.foot_width:  # the 8-12 cm default is for ~10 cm wide shoes
            a.min_width, a.max_width = 0.8 * a.foot_width, 1.25 * a.foot_width
        names = [n.strip() for n in a.feet.split(",")]
        contacts = []  # (time, foot index, lateral offset from the slow travel line)
        onsets = []    # (touch-down index, foot index)
        for fi, name in enumerate(names):
            foot = to_metres_y_up(d, series(d, name, vector=True))
            contact = foot[:, 1] < a.contact
            k = 0
            while k < len(contact):
                if not contact[k]:
                    k += 1
                    continue
                s = k
                while k < len(contact) and contact[k]:
                    k += 1
                mid = (s + k - 1) // 2
                offset = float((foot[mid, [0, 2]] - centre) @ side) - float(slow[mid])
                contacts.append((float(t[mid]), fi, offset))
                if s > 0:  # a stance already running when the recording starts has no touch-down
                    onsets.append((s, fi))
        contacts.sort()
        onsets.sort()
        # stride = pelvis travel from one touch-down to the next of the same foot; cadence =
        # touch-downs of both feet per minute
        strides = [float(along[b[0]] - along[a_[0]]) for fi in range(len(names))
                   for a_, b in zip([o for o in onsets if o[1] == fi], [o for o in onsets if o[1] == fi][1:])]
        if strides and len(onsets) > 1:
            stride = float(np.median(strides))
            cadence = (len(onsets) - 1) / (t[onsets[-1][0]] - t[onsets[0][0]]) * 60
            out.update(stride_m=round(stride, 3), cadence_spm=round(float(cadence), 1),
                       gait_cycles=len(strides))
            for label, got, ref in (("stride", stride, a.ref_stride), ("cadence", cadence, a.ref_cadence)):
                if ref and abs(got - ref) > a.keep_tol * ref:
                    problems.append(f"{label} {got:.3g} moved more than {a.keep_tol * 100:.0f} % "
                                    f"from {ref:.3g}")
        widths = [abs(b[2] - a_[2]) for a_, b in zip(contacts, contacts[1:]) if a_[1] != b[1]]
        # --feet is "left,right": the left foot must land left of the travel line, the right
        # foot right of it; a foot on the other side is a crossing (catwalk) step
        want = {0: 1.0, 1: -1.0}
        crossings = sum(1 for c in contacts if c[1] in want and np.sign(c[2]) == -want[c[1]]
                        and abs(c[2]) > 0.005)
        if widths:
            step_width = float(np.median(widths))
            out.update(step_width_m=round(step_width, 3), crossing_steps=crossings)
            if not (a.min_width <= step_width <= a.max_width):
                problems.append(f"step width {step_width * 100:.1f} cm outside "
                                f"{a.min_width * 100:.0f}-{a.max_width * 100:.0f}")
            if crossings:
                problems.append(f"{crossings} step(s) cross the midline")
    return result("gait_hip_sway", len(problems), 0, not problems, problems=problems, **out)


def _band_share(x, hz, lo, hi):
    """Share of the signal's power (mean removed) between lo and hi Hz, and its peak frequency."""
    x = np.asarray(x, dtype=float) - np.nanmean(x)
    x = np.nan_to_num(x)
    spec = np.abs(np.fft.rfft(x)) ** 2
    freqs = np.fft.rfftfreq(len(x), 1.0 / hz)
    total = spec[1:].sum()
    if total <= 0:
        return 0.0, None
    band = spec[(freqs >= lo) & (freqs <= hi)].sum()
    peak = float(freqs[1:][np.argmax(spec[1:])])
    return float(band / total), peak


def idle(d, a):
    """Is an idle alive but calm? Sway of the pelvis/CoM probe, breathing from the chest probe,
    frozen parts from angle probes."""
    t = np.asarray(d["times"], dtype=float)
    if len(t) < 2 or t[-1] - t[0] < 20:
        raise NotAssessed("record at least 20 s (60 s recommended) of idle")
    hz = (len(t) - 1) / (t[-1] - t[0])
    pos = to_metres_y_up(d, series(d, a.pos, vector=True))
    ap = pos[:, {"x": 0, "z": 2}[a.ap_axis]]
    ml = pos[:, {"x": 2, "z": 0}[a.ap_axis]]
    rms_ap = float(np.sqrt(np.nanmean((ap - np.nanmean(ap)) ** 2))) * 1000
    rms_ml = float(np.sqrt(np.nanmean((ml - np.nanmean(ml)) ** 2))) * 1000
    low_share, peak = _band_share(ap, hz, 0.0, 0.5)
    out = {"sway_rms_ap_mm": round(rms_ap, 3), "sway_rms_ml_mm": round(rms_ml, 3),
           "sway_power_below_0p5hz": round(low_share, 3),
           "sway_peak_hz": round(peak, 3) if peak is not None else None}
    problems = []
    if not (a.ap_min <= rms_ap <= a.ap_max):
        problems.append(f"front-back sway {rms_ap:.2f} mm outside {a.ap_min}-{a.ap_max}")
    if not (a.ml_min <= rms_ml <= a.ml_max):
        problems.append(f"side sway {rms_ml:.2f} mm outside {a.ml_min}-{a.ml_max}")
    if low_share < 0.8:
        problems.append(f"only {low_share:.0%} of sway power below 0.5 Hz (jittery)")
    if a.chest:
        chest = to_metres_y_up(d, series(d, a.chest, vector=True))
        rel = np.linalg.norm(chest - pos, axis=1)
        share, bpeak = _band_share(rel, hz, 0.15, 0.5)
        p2p = float(np.nanmax(rel) - np.nanmin(rel)) * 1000
        out.update(breath_hz=round(bpeak, 3) if bpeak is not None else None,
                   breaths_per_min=round(bpeak * 60, 1) if bpeak else None,
                   chest_p2p_mm=round(p2p, 2), min_breath_mm=a.min_breath_mm)
        if p2p < a.min_breath_mm:
            # below this the loop length dominates the spectrum and the "rate" is noise
            problems.append(f"breathing invisible: chest-pelvis distance moves {p2p:.2f} mm "
                            f"peak to peak (< {a.min_breath_mm} mm); scale the breath up")
        elif bpeak is None or not (0.2 <= bpeak <= 0.34):
            problems.append(f"breathing peak {bpeak} Hz outside 0.2-0.33 (12-20/min)")
    frozen = []
    for name in [n.strip() for n in (a.bones or "").split(",") if n.strip()]:
        ang = series(d, name)
        if ang.ndim == 2:  # quaternion [x, y, z, w]: angle from the first sample
            q0 = ang[0] / np.linalg.norm(ang[0])
            q = ang / np.linalg.norm(ang, axis=1, keepdims=True)
            ang = np.degrees(2 * np.arccos(np.clip(np.abs(q @ q0), -1, 1)))
        win = max(2, int(10 * hz))
        p2p = min(float(np.nanmax(ang[i:i + win]) - np.nanmin(ang[i:i + win]))
                  for i in range(0, max(1, len(ang) - win + 1), max(1, win // 2)))
        if p2p < a.min_deg:
            frozen.append({"bone": name, "p2p_deg": round(p2p, 3)})
    if frozen:
        problems.append(f"{len(frozen)} part(s) frozen (< {a.min_deg} deg in a 10 s window)")
    return result("idle_alive_and_calm", len(problems), 0, not problems, problems=problems,
                  frozen=frozen, seconds=round(float(t[-1] - t[0]), 1), **out)


def _stats(values):
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v) & (v > 0)]
    if not len(v):
        return None
    return {"mean": round(float(v.mean()), 3), "p95": round(float(np.percentile(v, 95)), 3),
            "p99": round(float(np.percentile(v, 99)), 3)}


def frames(d, a):
    ms = np.asarray(d["frame_ms"][a.skip:], dtype=float)
    ms = ms[np.isfinite(ms) & (ms > 0)]
    if len(ms) == 0:
        raise NotAssessed("no frame samples")
    med = np.array([np.median(ms[max(0, i - 30):i + 1]) for i in range(len(ms))])
    hitches = int(((ms > 2 * med) | (ms > 50)).sum())
    low1 = 1000.0 / np.percentile(ms, 99)
    ok = np.mean(ms) <= a.budget_ms and low1 >= 0.75 * (1000.0 / a.budget_ms) and hitches == 0
    extra = {"frames": int(len(ms)), "p95": round(float(np.percentile(ms, 95)), 3),
             "p99": round(float(np.percentile(ms, 99)), 3), "low1_fps": round(float(low1), 1),
             "hitches": hitches, "worst_ms": round(float(ms.max()), 3)}
    for key in ("gpu_ms", "cpu_ms"):
        stats = _stats(d[key][a.skip:])
        if stats:
            extra[key] = stats
    return result("frame_time", round(float(np.mean(ms)), 3), a.budget_ms, bool(ok), **extra)


def settle(d, a):
    pos = to_metres_y_up(d, series(d, a.pos, vector=True))
    t = np.asarray(d["times"], dtype=float)
    if len(pos) < 2:
        raise NotAssessed("fewer than two samples")
    dt = np.diff(t)
    dt[dt <= 0] = np.nan
    speed = np.linalg.norm(np.diff(pos, axis=0), axis=1) / dt
    moving = np.nonzero(~(speed <= a.speed))[0]  # NaN counts as moving
    index = int(moving[-1] + 1) if len(moving) else 0
    seconds = float(t[index] - t[0])
    settled = index < len(speed)  # still moving at the last sample = never settled
    return result("settle_time_s", round(seconds, 3), a.max_s, seconds <= a.max_s and settled,
                  settled=settled, final_speed=round(float(speed[-1]), 4))


def _changed(a, b, eps):
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return any(_changed(x, y, eps) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and \
            not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) > eps
    return a != b


def reaction(d, a):
    t = d["times"]

    def first_change(name):
        if name not in d["samples"]:
            series(d, name)  # raises NotAssessed with the probe list
        vals = d["samples"][name]
        for i in range(1, len(vals)):
            if _changed(vals[i], vals[0], a.eps):
                return i
        return None
    i_in, i_out = first_change(a.input), first_change(a.response)
    if i_in is None or i_out is None:
        return result("reaction_ticks", None, a.max_ticks, False, note="no change detected",
                      input_changed=i_in is not None, response_changed=i_out is not None)
    ticks = i_out - i_in
    return result("reaction_ticks", ticks, a.max_ticks, 0 <= ticks <= a.max_ticks,
                  ms=round(1000.0 * (t[i_out] - t[i_in]), 1))


COMMANDS = {"skating": skating, "stance": stance, "idle": idle, "gait": gait, "frames": frames,
            "settle": settle, "reaction": reaction}


def expand(pattern):
    if glob.has_magic(pattern):
        return sorted(glob.glob(pattern, recursive=True))
    return [pattern]


def analyse(path, args):
    base = {"file": path}
    try:
        d = load(path)
        out = COMMANDS[args.cmd](d, args)
        meta = d.get("meta") or {}
        return {**out, **base, **({"source": meta} if meta else {})}
    except FileNotFoundError:
        return {"metric": args.cmd, "value": None, "verdict": "NOT ASSESSED",
                "note": "file not found", **base}
    except NotAssessed as exc:
        return {"metric": args.cmd, "value": None, "verdict": "NOT ASSESSED", "note": str(exc),
                **base}


def clean(value):
    """Strict JSON: NaN/inf -> null, numpy scalars -> Python numbers."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("skating")
    s.add_argument("dump")
    s.add_argument("--foot", required=True)
    s.add_argument("--ground")
    s.add_argument("--contact", type=float, default=0.05, help="contact height, m")
    s.add_argument("--slip-speed", type=float, default=0.15, help="m/s")
    s.add_argument("--max-ratio", type=float, default=0.05)
    s.add_argument("--contact-flag", help="per-tick probe, > 0.5 = foot planted (authored stance)")
    st = sub.add_parser("stance")
    st.add_argument("dump")
    st.add_argument("--feet", required=True, help="comma-separated foot probes")
    st.add_argument("--root", help="root/capsule position probe: marks turning stances")
    st.add_argument("--ground")
    st.add_argument("--contact", type=float, default=0.05, help="contact height, m")
    st.add_argument("--min-stance", type=float, default=0.05, help="s")
    st.add_argument("--max-slip", type=float, default=0.02, help="m per stance")
    st.add_argument("--turn-deg", type=float, default=10.0, help="heading change in a stance")
    st.add_argument("--contact-flag", help="per-tick probe, > 0.5 = foot planted (authored stance)")
    g = sub.add_parser("gait")
    g.add_argument("dump")
    g.add_argument("--pelvis", required=True, help="pelvis/root position probe")
    g.add_argument("--hips", help="hip_l,hip_r joint position probes (obliquity, rotation)")
    g.add_argument("--feet", help="foot_l,foot_r position probes (step width, crossing)")
    g.add_argument("--contact", type=float, default=0.05, help="foot contact height, m")
    g.add_argument("--window-s", type=float, default=1.5, help="detrend window for curves, s")
    g.add_argument("--max-shift", type=float, default=0.025, help="lateral pelvis shift, ±m")
    g.add_argument("--max-obliquity", type=float, default=5.0, help="±deg")
    g.add_argument("--max-rotation", type=float, default=5.0, help="±deg")
    g.add_argument("--min-width", type=float, default=0.08)
    g.add_argument("--max-width", type=float, default=0.12)
    g.add_argument("--foot-width", type=float,
                   help="boot/foot width, m: step width range becomes 0.8-1.25 x this (wide boots, armour)")
    g.add_argument("--ref-stride", type=float, help="stride (m) a fix must keep, e.g. the before-run")
    g.add_argument("--ref-cadence", type=float, help="cadence (steps/min) a fix must keep")
    g.add_argument("--keep-tol", type=float, default=0.03, help="allowed change vs the refs, fraction")
    i = sub.add_parser("idle")
    i.add_argument("dump")
    i.add_argument("--pos", required=True, help="pelvis or centre-of-mass position probe")
    i.add_argument("--chest", help="chest/upper-spine position probe (breathing)")
    i.add_argument("--bones", help="comma-separated angle (deg) or quaternion probes")
    i.add_argument("--ap-axis", choices=["x", "z"], default="z", help="front-back axis")
    i.add_argument("--ap-min", type=float, default=1.0)
    i.add_argument("--ap-max", type=float, default=8.0)
    i.add_argument("--ml-min", type=float, default=0.5)
    i.add_argument("--ml-max", type=float, default=4.0)
    i.add_argument("--min-deg", type=float, default=0.5, help="frozen below this p2p in 10 s")
    i.add_argument("--min-breath-mm", type=float, default=2.0,
                   help="chest-pelvis peak-to-peak below which breathing is invisible")
    f = sub.add_parser("frames")
    f.add_argument("dump")
    f.add_argument("--budget-ms", type=float, default=16.67)
    f.add_argument("--skip", type=int, default=0, help="frames to drop at the start")
    t = sub.add_parser("settle")
    t.add_argument("dump")
    t.add_argument("--pos", required=True)
    t.add_argument("--speed", type=float, default=0.03, help="m/s")
    t.add_argument("--max-s", type=float, default=5.0)
    r = sub.add_parser("reaction")
    r.add_argument("dump")
    r.add_argument("--input", required=True)
    r.add_argument("--response", required=True)
    r.add_argument("--max-ticks", type=int, default=2)
    r.add_argument("--eps", type=float, default=0.0, help="numeric change threshold")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    paths = expand(args.dump)
    if not paths:
        print(json.dumps({"metric": args.cmd, "verdict": "NOT ASSESSED",
                          "note": f"no file matches {args.dump}"}))
        return 1
    results = [analyse(os.path.normpath(p), args) for p in paths]
    if len(results) == 1:
        print(json.dumps(clean(results[0]), allow_nan=False))
        return 0
    verdicts = {r["verdict"] for r in results}
    overall = "FAIL" if "FAIL" in verdicts else "PASS" if verdicts == {"PASS"} else "NOT ASSESSED"
    print(json.dumps(clean({"verdict": overall, "results": results}), allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
