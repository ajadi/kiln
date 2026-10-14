"""Checks for weather — fog and visibility, thunder, lightning flashes, rain particle budgets,
wetness, transitions, schedules, wind and perception — against exact answers (Python 3.12+,
stdlib only). Snowfall, settling, melt and other snow mechanics: fluids-granular's fluid_check.py
(predict snowfall | settle | melt | footprint | blowsnow | drift).

Prediction (design time):
  python weather_check.py predict fog        --visibility 200 [--threshold 0.02] [--at 50 100]
  python weather_check.py predict fog        --density 0.01
  python weather_check.py predict thunder    --distance 1000 [--temp 20] [--audible 16000]
  python weather_check.py predict thunder    --delay 6 [--temp 20]
  python weather_check.py predict flash      --strokes 4 --interval 0.045 [--period 8] [--max 3]
  python weather_check.py predict rain       --box 30 30 20 --density 0.5 --speed 8
                                             [--budget 20000] [--rate 10 [--dmin 1]]
  python weather_check.py predict wetness    --from 1 --to 0.1 (--tau 60 | --rate 0.01)
  python weather_check.py predict transition --from 0 --to 1 (--duration 120 [--shape linear|
                                             smoothstep] | --shape exp --tau 40)
                                             [--on 0.6 --off 0.4 [--noise 0.1]] [--max-rate 0.02]
  python weather_check.py predict schedule   --on-min 12000 --on-max 24000 [--off-min 12000
                                             --off-max 180000] [--unit-s 0.05 | --day-minutes 48]
  python weather_check.py predict wind       --speed 10 [--temp -5] [--gust-factor 1.5]
  python weather_check.py predict perception --visibility 400 [--contrast 0.3] [--threshold 0.02]
                                             [--hearing 30 --noise-db 6]

  fog: Koschmieder — extinction sigma = -ln(threshold)/V (threshold 0.02 gives 3.912/V; the WMO
  meteorological optical range uses 0.05, 2.996/V), and the engine values that produce it: Godot
  fog_density and volumetric_fog_density (both extinction per metre: fog = 1 - exp(-d*density)),
  Unity Exponential density (= sigma) and Exponential Squared density (sqrt(-ln t)/V), HDRP Fog
  Attenuation Distance (1/sigma, the mean free path), fog amount 1 - exp(-sigma*d) at --at
  distances. thunder: speed of sound c = 331.3*sqrt(1 + T/273.15) m/s, delay = distance/c (or
  distance from a delay), audible within --audible metres (16 km, NWS "about 10 miles").
  flash: a lightning burst of --strokes pulses --interval s apart, repeating every --period s;
  the most pulses in any 1 s window against the photosensitivity limit (3 flashes per second),
  and a burst period that is always safe (1 s from the last pulse to the next burst).
  rain: a camera-local box W x D x H m with --density streaks per m3 falling at --speed m/s:
  particles = density*volume, lifetime = H/speed, emission = particles/lifetime, ground hits per
  m2 per s = density*speed; with --rate (mm/h) the real Marshall-Palmer drop count
  N = N0/L*exp(-L*dmin), N0 = 8000 m^-3 mm^-1, L = 4.1*R^-0.21 mm^-1.
  wetness: time to go --from -> --to; exponential (--tau) approaches 1 when wetting
  (t = tau*ln((1-w0)/(1-w1))) and 0 when drying (t = tau*ln(w0/w1)); linear (--rate per s)
  t = |w1-w0|/rate. transition: max rate of change (linear D/D, smoothstep 1.5x linear, exp at
  the start delta/tau), time to 95%, when the hysteresis threshold is crossed (--on rising, --off
  falling), and whether the hysteresis band exceeds the driver noise. schedule: two states with
  uniform random dwell times (Minecraft rain/clear) — mean dwell, share of time in the "on"
  state, converted to seconds by --unit-s or by --day-minutes (dwell in game hours). wind:
  Beaufort force (table)
  and B = (v/0.836)^(2/3), gust speed, wind chill 13.12 + 0.6215T - 11.37V^0.16 + 0.3965TV^0.16
  (V km/h; valid T <= 10 C, V > 4.8 km/h). perception: sight distance for a target of inherent
  contrast C0 in fog: ln(C0/threshold)/sigma; hearing radius after the background noise rises
  by --noise-db: R*10^(-dB/20) (spherical spreading, 6 dB per doubling of distance).

Measurement (recordings from the running game):
  python weather_check.py smooth   <dump> --probe weather_intensity=0.05 [--probe fog=0.002 ...]
                                          [--window 0.5] [--state rain_on --min-dwell 5]
  python weather_check.py wetness  <dump> --wetness ground_wet --rain raining [--rain-on 0]
                                          [--wet-level 0.8 --wet-within 60]
                                          [--dry-level 0.1 --dry-within 300 --dry-min 30]
  python weather_check.py shelter  <dump> (--inside wet_under_roof [--max 0.05] |
                                          --splashes splash_pos --roof x0 y0 z0 x1 y1 z1
                                          [--max-count 0]) [--outside wet_open --min-outside 0.5]
  python weather_check.py visibility <targets.json> --visibility 200 [--threshold 0.02] [--tol 0.15]
  python weather_check.py flashes  <dump> --luma sky_luma [--area sky_area] [--min-area 0.2]
                                          [--max 3]

  smooth: for each --probe name=limit, the largest change per second over --window seconds
  (vectors by Euclidean distance) against the limit — no visible pops in intensity, fog, light,
  wind; with --state, every inner run of a state lasts >= --min-dwell s (no flicker between
  states). wetness: from rain start the wetness reaches --wet-level within --wet-within s and
  never drops while it rains; from rain stop it falls to --dry-level after at least --dry-min and
  within --dry-within s and never rises while dry. shelter: under a roof the wetness stays
  <= --max, or no splash position falls inside the roof box; --outside proves it rained (NOT
  ASSESSED otherwise). visibility: fits the extinction from measured contrast (or transmittance)
  of targets at known distances, sigma = -sum(d*ln C)/sum(d^2), V = -ln(threshold)/sigma, against
  the design visibility — the way to calibrate unitless fog settings (Unreal). flashes: WCAG
  general flashes in a recorded luminance series (0-1): opposing changes >= 0.1 where the darker
  state is < 0.8, counted over any 1 s; more than 2*--max transitions (--max flashes) fails;
  with --area only changes over at least --min-area of the screen count.

Recordings: the acceptance recorder JSON (tick `samples` or per-frame `frame_samples`) or JSON
Lines; positions [x, y, z] metres, Y up. Targets: {"targets": [{"distance": m, "contrast": C/C0}]}
("transmittance" or "fog" = 1 - transmittance also accepted). Prints one JSON object
{"verdict", "metrics": [...]} (predict: {"prediction": {...}}); exit code 1 on FAIL, 2 on bad
input; NOT ASSESSED exits 0.
"""

import argparse
import json
import math
import sys

MP_N0 = 8000.0               # Marshall-Palmer intercept, drops per m3 per mm of diameter
BEAUFORT_MAX = [0.2, 1.5, 3.3, 5.4, 7.9, 10.7, 13.8, 17.1, 20.7, 24.4, 28.4, 32.6]  # m/s
WCAG_STEP = 0.1              # relative luminance change of one flash transition
WCAG_DARK = 0.8              # the darker state must be below this


class NotAssessed(Exception):
    """The input cannot answer the question."""


def metric(name, value, threshold, ok, **extra):
    return {"metric": name, "value": value, "threshold": threshold,
            "verdict": "PASS" if ok else "FAIL", **extra}


def rnd(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, n)


# ---------- recordings ----------

def load_recording(path):
    """Return {probe: (times_s, values)} for tick probes and per-frame probes."""
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    series = {}
    if isinstance(data, dict) and isinstance(data.get("samples"), dict):
        hz = float(data.get("physics_ticks_per_second") or 60)
        ticks = data.get("ticks") or []
        for name, vals in data["samples"].items():
            if ticks:
                n = min(len(ticks), len(vals))
                series[name] = ([(t - ticks[0]) / hz for t in ticks[:n]], vals[:n])
            else:
                series[name] = ([i / hz for i in range(len(vals))], vals)
        acc, ftimes = 0.0, []
        for ms in data.get("frame_ms") or []:
            acc += float(ms) / 1000.0
            ftimes.append(acc)
        for name, vals in (data.get("frame_samples") or {}).items():
            if name in series:
                continue
            if ftimes:
                n = min(len(ftimes), len(vals))
                series[name] = ([t - ftimes[0] for t in ftimes[:n]], vals[:n])
            else:
                series[name] = ([i / 60.0 for i in range(len(vals))], vals)
        return series
    rows = data if isinstance(data, list) else [json.loads(x) for x in text.splitlines()
                                                 if x.strip()]
    rows = [r for r in rows if isinstance(r, dict) and r.get("type", "tick") in ("tick", "sample")]
    times = [float(r["t"]) if "t" in r else float(r.get("tick", i)) / 60.0
             for i, r in enumerate(rows)]
    if times:
        times = [t - times[0] for t in times]
    keys = []
    for row in rows:
        keys.extend(k for k in row if k not in keys and k not in ("type", "t", "tick"))
    return {k: (times, [row.get(k) for row in rows]) for k in keys}


def probe(series, name):
    if name not in series:
        raise NotAssessed(f"probe '{name}' not in recording; probes: " + ", ".join(sorted(series)))
    return series[name]


def as_float(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    return float(v)


def distance(a, b):
    if isinstance(a, list):
        return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))
    return abs(float(a) - float(b))


# ---------- predictions ----------

def p_fog(a):
    if not 0 < a.threshold < 1:
        raise ValueError("--threshold must be between 0 and 1")
    k = -math.log(a.threshold)
    if a.visibility:
        sigma = k / a.visibility
    elif a.density:
        sigma = a.density
    else:
        raise ValueError("fog needs --visibility (m) or --density (extinction per m)")
    vis = k / sigma
    out = dict(extinction_per_m=rnd(sigma, 6), visibility_m=rnd(vis, 2), threshold=a.threshold,
               mor_5pct_m=rnd(math.log(20) / sigma, 2),
               godot_fog_density=rnd(sigma, 6), godot_volumetric_fog_density=rnd(sigma, 6),
               unity_exp_density=rnd(sigma, 6), unity_exp2_density=rnd(math.sqrt(k) / vis, 6),
               hdrp_attenuation_distance_m=rnd(1 / sigma, 2))
    if a.at:
        out["fog_amount_at"] = {f"{d:g}": rnd(1 - math.exp(-sigma * d), 4) for d in a.at}
    return out


def sound_speed(temp_c):
    return 331.3 * math.sqrt(1 + temp_c / 273.15)


def p_thunder(a):
    c = sound_speed(a.temp)
    if a.distance is not None:
        d = a.distance
    elif a.delay is not None:
        d = a.delay * c
    else:
        raise ValueError("thunder needs --distance (m) or --delay (s)")
    return dict(speed_m_s=rnd(c, 3), distance_m=rnd(d, 2), delay_s=rnd(d / c, 4),
                audible=d <= a.audible, rule_of_thumb_s=rnd(d / 1000 * 3, 2))


def max_in_window(times, width=1.0):
    times = sorted(times)
    best, j = 0, 0
    for i, t in enumerate(times):
        while t - times[j] >= width - 1e-9:
            j += 1
        best = max(best, i - j + 1)
    return best


def p_flash(a):
    if not a.strokes or a.strokes < 1:
        raise ValueError("flash needs --strokes >= 1")
    span = (a.strokes - 1) * a.interval
    if a.period is not None and a.period <= span:
        raise ValueError("--period must be longer than the burst (strokes-1)*interval")
    bursts = 1 if a.period is None else math.ceil(2.0 / a.period) + 2
    pulses = [b * (a.period or 0.0) + k * a.interval for b in range(bursts)
              for k in range(int(a.strokes))]
    best = max_in_window(pulses, 1.0)
    return dict(burst_length_s=rnd(span, 4), max_flashes_per_s=best, limit=a.max,
                photosafe=best <= a.max,
                safe_period_s=rnd(1.0 + span, 4) if a.strokes <= a.max else None)


def p_rain(a):
    if not (a.box and a.density is not None and a.speed):
        raise ValueError("rain needs --box W D H, --density (per m3) and --speed (m/s)")
    w, d, h = a.box
    vol = w * d * h
    count = a.density * vol
    life = h / a.speed
    out = dict(volume_m3=rnd(vol, 2), particles=rnd(count, 1), lifetime_s=rnd(life, 4),
               emission_per_s=rnd(count / life, 2),
               ground_hits_per_m2_s=rnd(a.density * a.speed, 4))
    if a.budget:
        out["fits_budget"] = count <= a.budget
    if a.rate:
        lam = 4.1 * a.rate ** -0.21
        total = MP_N0 / lam
        big = total * math.exp(-lam * a.dmin)
        out.update(real_drops_per_m3=rnd(total, 1), real_drops_over_dmin_per_m3=rnd(big, 2),
                   dmin_mm=a.dmin, rendered_share=rnd(a.density / big, 5) if big else None)
    return out


def p_wetness(a):
    w0, w1 = a.from_, a.to
    if w0 is None or w1 is None or not (0 <= w0 <= 1 and 0 <= w1 <= 1) or w0 == w1:
        raise ValueError("wetness needs --from and --to in 0..1, different")
    wetting = w1 > w0
    if a.tau:
        if wetting and w1 >= 1:
            raise ValueError("an exponential approach never reaches 1; use --to < 1")
        if not wetting and w1 <= 0:
            raise ValueError("an exponential approach never reaches 0; use --to > 0")
        t = a.tau * (math.log((1 - w0) / (1 - w1)) if wetting else math.log(w0 / w1))
        model = "exponential"
    elif a.rate:
        t = abs(w1 - w0) / a.rate
        model = "linear"
    else:
        raise ValueError("wetness needs --tau (s) or --rate (per s)")
    return dict(direction="wetting" if wetting else "drying", model=model, time_s=rnd(t, 3),
                time_min=rnd(t / 60, 4))


def smoothstep_inverse(f):
    # 3u^2 - 2u^3 = f  ->  u = 1/2 - sin(asin(1 - 2f)/3)
    return 0.5 - math.sin(math.asin(1 - 2 * f) / 3)


def p_transition(a):
    x0, x1 = a.from_, a.to
    if x0 is None or x1 is None or x0 == x1:
        raise ValueError("transition needs --from and --to, different")
    delta = x1 - x0
    shape = a.shape
    if shape == "exp":
        if not a.tau:
            raise ValueError("--shape exp needs --tau (s)")
        max_rate = abs(delta) / a.tau
        t95 = a.tau * math.log(20)
    else:
        if not a.duration:
            raise ValueError(f"--shape {shape} needs --duration (s)")
        max_rate = abs(delta) / a.duration * (1.5 if shape == "smoothstep" else 1.0)
        t95 = a.duration * (smoothstep_inverse(0.95) if shape == "smoothstep" else 0.95)
    out = dict(shape=shape, max_rate_per_s=rnd(max_rate, 6), time_to_95pct_s=rnd(t95, 3))
    rising = delta > 0
    thr = a.on if rising else a.off
    if thr is not None:
        f = (thr - x0) / delta
        if 0 < f < 1:
            if shape == "linear":
                t = f * a.duration
            elif shape == "smoothstep":
                t = smoothstep_inverse(f) * a.duration
            else:
                t = -a.tau * math.log(1 - f)
            out.update(threshold=thr, crosses_threshold_at_s=rnd(t, 3))
        else:
            out.update(threshold=thr, crosses_threshold_at_s=None)
    if a.on is not None and a.off is not None:
        if a.on <= a.off:
            raise ValueError("hysteresis needs --on above --off")
        band = a.on - a.off
        out["hysteresis_band"] = rnd(band, 6)
        if a.noise is not None:
            out["chatter_safe"] = band > a.noise
    if a.max_rate is not None:
        out["smooth_ok"] = max_rate <= a.max_rate
    return out


def p_schedule(a):
    if a.on_min is None or a.on_max is None or a.on_max < a.on_min:
        raise ValueError("schedule needs --on-min <= --on-max")
    unit = a.unit_s if a.unit_s else (a.day_minutes * 60 / 24 if a.day_minutes else None)
    mean_on = (a.on_min + a.on_max) / 2
    out = dict(mean_on=rnd(mean_on, 4))
    if unit:
        out.update(unit_s=rnd(unit, 6), on_s=[rnd(a.on_min * unit, 3), rnd(a.on_max * unit, 3)],
                   mean_on_s=rnd(mean_on * unit, 3), mean_on_min=rnd(mean_on * unit / 60, 4))
    if a.off_min is not None and a.off_max is not None:
        if a.off_max < a.off_min:
            raise ValueError("--off-min must be <= --off-max")
        mean_off = (a.off_min + a.off_max) / 2
        out.update(mean_off=rnd(mean_off, 4), share_on=rnd(mean_on / (mean_on + mean_off), 6),
                   mean_cycle=rnd(mean_on + mean_off, 4))
        if unit:
            out.update(off_s=[rnd(a.off_min * unit, 3), rnd(a.off_max * unit, 3)],
                       mean_off_s=rnd(mean_off * unit, 3),
                       mean_off_min=rnd(mean_off * unit / 60, 4))
    return out


def beaufort_force(v):
    v = round(v, 1)
    for force, top in enumerate(BEAUFORT_MAX):
        if v <= top:
            return force
    return 12


def p_wind(a):
    if a.speed is None or a.speed < 0:
        raise ValueError("wind needs --speed (m/s at 10 m)")
    v = a.speed
    kmh = v * 3.6
    out = dict(speed_km_h=rnd(kmh, 3), beaufort_force=beaufort_force(v),
               beaufort_number=rnd((v / 0.836) ** (2 / 3), 3),
               gust_m_s=rnd(v * a.gust_factor, 3))
    if a.temp is not None:
        if a.temp <= 10 and kmh > 4.8:
            p = kmh ** 0.16
            out["wind_chill_c"] = rnd(13.12 + 0.6215 * a.temp - 11.37 * p + 0.3965 * a.temp * p, 3)
        else:
            out["wind_chill_c"] = None
            out["note"] = "wind chill is defined only for T <= 10 C and wind > 4.8 km/h"
    return out


def p_perception(a):
    if not a.visibility:
        raise ValueError("perception needs --visibility (m)")
    k = -math.log(a.threshold)
    sigma = k / a.visibility
    out = dict(extinction_per_m=rnd(sigma, 6))
    if a.contrast <= a.threshold:
        out["sight_m"] = 0.0
    else:
        out["sight_m"] = rnd(math.log(a.contrast / a.threshold) / sigma, 2)
    if a.hearing:
        out["hearing_m"] = rnd(a.hearing * 10 ** (-(a.noise_db or 0.0) / 20), 3)
    return out


PREDICT = {"fog": p_fog, "thunder": p_thunder, "flash": p_flash, "rain": p_rain,
           "wetness": p_wetness, "transition": p_transition, "schedule": p_schedule,
           "wind": p_wind, "perception": p_perception}


# ---------- measurements ----------

def max_rate(pts, window):
    """Largest |change| per second between samples at least `window` s apart."""
    best, at, j = None, None, 0
    for i in range(len(pts)):
        if j <= i:
            j = i + 1
        while j < len(pts) and pts[j][0] - pts[i][0] < window - 1e-9:
            j += 1
        if j >= len(pts):
            break
        dt = pts[j][0] - pts[i][0]
        if dt <= 0:
            continue
        r = distance(pts[j][1], pts[i][1]) / dt
        if best is None or r > best:
            best, at = r, pts[i][0]
    return best, at


def smooth(a):
    series = load_recording(a.dump)
    out = []
    for spec in a.probe or []:
        name, _, lim = spec.partition("=")
        if not lim:
            raise ValueError(f"--probe needs name=max_change_per_s, got '{spec}'")
        limit = float(lim)
        times, vals = probe(series, name)
        pts = [(t, v) for t, v in zip(times, vals) if v is not None]
        rate, at = max_rate(pts, a.window)
        if rate is None:
            raise NotAssessed(f"'{name}': recording shorter than the {a.window} s window")
        out.append(metric(f"{name}_max_change_per_s", rnd(rate, 6), f"≤ {limit}", rate <= limit,
                          at_s=rnd(at, 3), window_s=a.window))
    if a.state:
        times, vals = probe(series, a.state)
        runs = []
        for t, v in zip(times, vals):
            if v is None:
                continue
            if not runs or runs[-1][0] != v:
                runs.append([v, t])
        inner = [(runs[i][0], runs[i + 1][1] - runs[i][1]) for i in range(1, len(runs) - 1)]
        shortest = min((d for _, d in inner), default=None)
        out.append(metric(f"{a.state}_min_dwell_s", rnd(shortest, 3), f"≥ {a.min_dwell}",
                          shortest is None or shortest >= a.min_dwell, toggles=len(runs) - 1))
    if not out:
        raise ValueError("smooth needs --probe name=limit and/or --state")
    return out


def wetness(a):
    series = load_recording(a.dump)
    times, wv = probe(series, a.wetness)
    _, rv = probe(series, a.rain)
    rows = [(t, as_float(w), as_float(r) > a.rain_on) for t, w, r in zip(times, wv, rv)
            if w is not None and r is not None]
    if len(rows) < 2:
        raise NotAssessed("fewer than 2 samples with both probes")
    t = [r[0] for r in rows]
    w = [r[1] for r in rows]
    rain = [r[2] for r in rows]
    n = len(rows)
    start = next((i for i in range(n) if rain[i] and (i == 0 or not rain[i - 1])), None)
    if start == 0 and w[0] >= a.wet_level:
        start = next((i for i in range(1, n) if rain[i] and not rain[i - 1]), None)
    stop = next((i for i in range((start or 0) + 1, n) if not rain[i] and rain[i - 1]), None)
    out = []
    if start is not None:
        end = stop if stop is not None else n
        hit = next((i for i in range(start, end) if w[i] >= a.wet_level), None)
        rained = t[end - 1] - t[start]
        if hit is not None:
            ramp = t[hit] - t[start]
            out.append(metric("wet_ramp_s", rnd(ramp, 3), f"≤ {a.wet_within}",
                              ramp <= a.wet_within, wet_level=a.wet_level))
        elif rained >= a.wet_within:
            out.append(metric("wet_ramp_s", None, f"≤ {a.wet_within}", False,
                              note=f"never reached {a.wet_level} in {rnd(rained, 2)} s of rain"))
        peak, drop = -1.0, 0.0
        for i in range(start, end):
            peak = max(peak, w[i])
            drop = max(drop, peak - w[i])
        out.append(metric("wet_drop_while_raining", rnd(drop, 4), f"≤ {a.eps}", drop <= a.eps))
    if stop is not None:
        end = next((i for i in range(stop + 1, n) if rain[i]), n)
        hit = next((i for i in range(stop, end) if w[i] <= a.dry_level), None)
        dry_span = t[end - 1] - t[stop]
        if hit is not None:
            dry = t[hit] - t[stop]
            out.append(metric("dry_time_s", rnd(dry, 3), f"{a.dry_min}–{a.dry_within}",
                              a.dry_min <= dry <= a.dry_within, dry_level=a.dry_level))
        elif dry_span >= a.dry_within:
            out.append(metric("dry_time_s", None, f"{a.dry_min}–{a.dry_within}", False,
                              note=f"never fell to {a.dry_level} in {rnd(dry_span, 2)} s"))
        low, rise = 2.0, 0.0
        for i in range(stop, end):
            low = min(low, w[i])
            rise = max(rise, w[i] - low)
        out.append(metric("wet_rise_while_dry", rnd(rise, 4), f"≤ {a.eps}", rise <= a.eps))
    if not out:
        raise NotAssessed("no rain start or stop in the recording")
    return out


def points_of(value):
    if not value:
        return []
    if isinstance(value, list) and len(value) == 3 and all(isinstance(x, (int, float))
                                                           for x in value):
        return [value]
    return [p for p in value if isinstance(p, list) and len(p) == 3]


def shelter(a):
    series = load_recording(a.dump)
    out = []
    if not (a.inside or a.splashes):
        raise ValueError("shelter needs --inside <probe> or --splashes <probe> --roof ...")
    if a.outside:
        _, ov = probe(series, a.outside)
        vals = [as_float(v) for v in ov if v is not None]
        peak = max(vals, default=0.0)
        if peak < a.min_outside:
            raise NotAssessed(f"'{a.outside}' peaked at {rnd(peak, 4)} < {a.min_outside}: it did "
                              "not rain on the open side, so the shelter check proves nothing")
        out.append(metric("outside_peak", rnd(peak, 4), f"≥ {a.min_outside}", True))
    if a.inside:
        _, iv = probe(series, a.inside)
        vals = [as_float(v) for v in iv if v is not None]
        if not vals:
            raise NotAssessed(f"'{a.inside}' has no samples")
        peak = max(vals)
        out.append(metric("inside_peak", rnd(peak, 4), f"≤ {a.max}", peak <= a.max))
    if a.splashes:
        if not a.roof:
            raise ValueError("--splashes needs --roof x0 y0 z0 x1 y1 z1")
        lo = [min(a.roof[i], a.roof[i + 3]) for i in range(3)]
        hi = [max(a.roof[i], a.roof[i + 3]) for i in range(3)]
        times, sv = probe(series, a.splashes)
        total, inside, first = 0, 0, None
        for t, v in zip(times, sv):
            for p in points_of(v):
                total += 1
                if all(lo[k] <= p[k] <= hi[k] for k in range(3)):
                    inside += 1
                    first = t if first is None else first
        if total == 0:
            raise NotAssessed(f"'{a.splashes}' recorded no splash positions at all")
        out.append(metric("splashes_under_roof", inside, f"≤ {a.max_count}",
                          inside <= a.max_count, splashes_total=total, first_at_s=rnd(first, 3)))
    return out


def visibility(a):
    with open(a.targets, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    rows = data.get("targets") if isinstance(data, dict) else data
    pts = []
    for r in rows or []:
        d = float(r["distance"])
        if "contrast" in r:
            c = float(r["contrast"])
        elif "transmittance" in r:
            c = float(r["transmittance"])
        elif "fog" in r:
            c = 1.0 - float(r["fog"])
        else:
            raise ValueError("each target needs distance and contrast | transmittance | fog")
        if d > 0 and 0 < c < 1:
            pts.append((d, c))
    if len(pts) < 2:
        raise NotAssessed("need at least 2 targets with 0 < contrast < 1")
    sigma = -sum(d * math.log(c) for d, c in pts) / sum(d * d for d, _ in pts)
    vis = -math.log(a.threshold) / sigma
    err = abs(vis - a.visibility) / a.visibility
    resid = max(abs(math.exp(-sigma * d) - c) for d, c in pts)
    return [metric("visibility_m", rnd(vis, 2), f"{a.visibility} ± {a.tol:.0%}", err <= a.tol,
                   extinction_per_m=rnd(sigma, 6), relative_error=rnd(err, 4),
                   max_contrast_residual=rnd(resid, 4), targets=len(pts))]


def zigzag(pts, step):
    """Turning points of a series, ignoring wiggles smaller than `step`."""
    ext, trend, cand = [], 0, None
    lo = hi = pts[0]
    for p in pts[1:]:
        v = p[1]
        if trend == 0:
            if v > hi[1]:
                hi = p
            if v < lo[1]:
                lo = p
            if hi[1] - lo[1] >= step - 1e-12:
                if hi[0] > lo[0]:
                    ext.append(lo)
                    trend, cand = 1, hi
                else:
                    ext.append(hi)
                    trend, cand = -1, lo
        elif trend == 1:
            if v > cand[1]:
                cand = p
            elif cand[1] - v >= step - 1e-12:
                ext.append(cand)
                trend, cand = -1, p
        else:
            if v < cand[1]:
                cand = p
            elif v - cand[1] >= step - 1e-12:
                ext.append(cand)
                trend, cand = 1, p
    if trend != 0:
        ext.append(cand)
    return ext


def flashes(a):
    series = load_recording(a.dump)
    times, lv = probe(series, a.luma)
    areas = probe(series, a.area)[1] if a.area else [1.0] * len(lv)
    pts = [(t, as_float(v), as_float(ar)) for t, v, ar in zip(times, lv, areas)
           if v is not None and ar is not None]
    if len(pts) < 2:
        raise NotAssessed("fewer than 2 luminance samples")
    ext = zigzag(pts, WCAG_STEP)
    trans = [q[0] for p, q in zip(ext, ext[1:])
             if min(p[1], q[1]) < WCAG_DARK and max(p[2], q[2]) >= a.min_area]
    worst = max_in_window(trans, 1.0) if trans else 0
    return [metric("flashes_per_s_max", worst / 2, f"≤ {a.max}", worst <= 2 * a.max,
                   transitions_in_worst_1s=worst, transitions_total=len(trans))]


MEASURE = {"smooth": smooth, "wetness": wetness, "shelter": shelter, "visibility": visibility,
           "flashes": flashes}


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("predict")
    cases = pr.add_subparsers(dest="case", required=True)

    c = cases.add_parser("fog")
    c.add_argument("--visibility", type=float)
    c.add_argument("--density", type=float)
    c.add_argument("--threshold", type=float, default=0.02)
    c.add_argument("--at", type=float, nargs="+")
    c = cases.add_parser("thunder")
    c.add_argument("--distance", type=float)
    c.add_argument("--delay", type=float)
    c.add_argument("--temp", type=float, default=20.0)
    c.add_argument("--audible", type=float, default=16000.0)
    c = cases.add_parser("flash")
    c.add_argument("--strokes", type=int, required=True)
    c.add_argument("--interval", type=float, default=0.045)
    c.add_argument("--period", type=float)
    c.add_argument("--max", type=int, default=3)
    c = cases.add_parser("rain")
    c.add_argument("--box", type=float, nargs=3, metavar=("W", "D", "H"))
    c.add_argument("--density", type=float)
    c.add_argument("--speed", type=float)
    c.add_argument("--budget", type=float)
    c.add_argument("--rate", type=float)
    c.add_argument("--dmin", type=float, default=1.0)
    c = cases.add_parser("wetness")
    c.add_argument("--from", dest="from_", type=float)
    c.add_argument("--to", type=float)
    c.add_argument("--tau", type=float)
    c.add_argument("--rate", type=float)
    c = cases.add_parser("transition")
    c.add_argument("--from", dest="from_", type=float)
    c.add_argument("--to", type=float)
    c.add_argument("--duration", type=float)
    c.add_argument("--shape", choices=["linear", "smoothstep", "exp"], default="linear")
    c.add_argument("--tau", type=float)
    c.add_argument("--on", type=float)
    c.add_argument("--off", type=float)
    c.add_argument("--noise", type=float)
    c.add_argument("--max-rate", type=float)
    c = cases.add_parser("schedule")
    for name in ("on-min", "on-max", "off-min", "off-max", "unit-s", "day-minutes"):
        c.add_argument(f"--{name}", type=float)
    c = cases.add_parser("wind")
    c.add_argument("--speed", type=float)
    c.add_argument("--temp", type=float)
    c.add_argument("--gust-factor", type=float, default=1.5)
    c = cases.add_parser("perception")
    c.add_argument("--visibility", type=float)
    c.add_argument("--contrast", type=float, default=1.0)
    c.add_argument("--threshold", type=float, default=0.02)
    c.add_argument("--hearing", type=float)
    c.add_argument("--noise-db", type=float)

    s = sub.add_parser("smooth")
    s.add_argument("dump")
    s.add_argument("--probe", action="append")
    s.add_argument("--window", type=float, default=0.5)
    s.add_argument("--state")
    s.add_argument("--min-dwell", type=float, default=5.0)
    w = sub.add_parser("wetness")
    w.add_argument("dump")
    w.add_argument("--wetness", required=True)
    w.add_argument("--rain", required=True)
    w.add_argument("--rain-on", type=float, default=0.0)
    w.add_argument("--wet-level", type=float, default=0.8)
    w.add_argument("--wet-within", type=float, default=60.0)
    w.add_argument("--dry-level", type=float, default=0.1)
    w.add_argument("--dry-within", type=float, default=300.0)
    w.add_argument("--dry-min", type=float, default=0.0)
    w.add_argument("--eps", type=float, default=0.02)
    h = sub.add_parser("shelter")
    h.add_argument("dump")
    h.add_argument("--inside")
    h.add_argument("--max", type=float, default=0.05)
    h.add_argument("--splashes")
    h.add_argument("--roof", type=float, nargs=6)
    h.add_argument("--max-count", type=int, default=0)
    h.add_argument("--outside")
    h.add_argument("--min-outside", type=float, default=0.5)
    v = sub.add_parser("visibility")
    v.add_argument("targets")
    v.add_argument("--visibility", type=float, required=True)
    v.add_argument("--threshold", type=float, default=0.02)
    v.add_argument("--tol", type=float, default=0.15)
    f = sub.add_parser("flashes")
    f.add_argument("dump")
    f.add_argument("--luma", required=True)
    f.add_argument("--area")
    f.add_argument("--min-area", type=float, default=0.2)
    f.add_argument("--max", type=int, default=3)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "predict":
            out = {"case": a.case, **PREDICT[a.case](a)}
            print(json.dumps({"prediction": out}, ensure_ascii=False))
            return 0
        metrics = MEASURE[a.cmd](a)
    except NotAssessed as exc:
        print(json.dumps({"verdict": "NOT ASSESSED", "reason": str(exc), "metrics": []},
                         ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        print(json.dumps({"verdict": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    verdict = "FAIL" if any(m["verdict"] == "FAIL" for m in metrics) else "PASS"
    print(json.dumps({"verdict": verdict, "metrics": metrics}, ensure_ascii=False))
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
