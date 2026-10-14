"""Checks for riding — horses and other mounts, and the rider on the saddle — against exact answers
(Python 3.12+, stdlib only).

Prediction (design time):
  python riding_check.py predict gait   --v 5 [--leg 1.25] [--fr-trot 0.34] [--fr-canter 1.3]
                                        [--fr-gallop 5] [--fr-trot-max 2.8]
  python riding_check.py predict stride --gait canter --v 6 [--mass 500] [--leg 1.25] [--f 1.7]
  python riding_check.py predict scale  --v 6 --f 1.61 --leg 1.25 --to-leg 3
  python riding_check.py predict turn   --v 6 --r 10 [--mu 0.6]
  python riding_check.py predict stop   --v 15 [--decel 3] [--mu 0.6] [--delay 0.3] [--rider 80]
  python riding_check.py predict load   --horse 500 --rider 80 [--tack 10] [--gear 0]

  gait: Froude number Fr = v^2/(g*L) (L = leg length, ~1.25 m for a 500 kg riding horse, working)
  and the gait band: walk below Fr 0.34 (Griffin 2004), trot to Fr 1.3 (overground ~4 m/s,
  working), canter to Fr 5 (working), gallop above; between Fr 1.3 and 2.8 a horse may trot or
  canter (free trot-gallop transition, Heglund & Taylor 1988 at 500 kg). Prints the speed of each
  boundary for this L. stride: stride frequency f, period, stride length v/f, beats per stride and
  saddle bounces per stride for the gait — walk from Alexander's stride rule 2.3*L*Fr^0.3, trot
  from the 680 kg horse f = 0.623 + 0.25*v, canter and gallop f = 4.44*M^-0.156 at the preferred
  galloping speed 2.78*M^0.176, +10 % per doubling of speed (Heglund & Taylor 1988); --f overrides.
  scale: dynamic similarity for another mount size (equal Fr): v*sqrt(L'/L), f*sqrt(L/L'),
  stride*L'/L, isometric mass ratio (L'/L)^3. turn: lean atan(v^2/(g*r)), lateral acceleration,
  heading rate, the grip limit mu*g (mu 0.6, Tan & Wilson 2011), the tightest radius v^2/(mu*g)
  and the fastest speed on this radius sqrt(mu*g*r). stop: distance v*delay + v^2/(2a), time,
  rider's forward load a/g (a = --decel, else the grip limit mu*g). load: rider share of the
  horse's body mass (Dyson 2020 pilot: tests with riders above 15.3 % were all stopped) and rider +
  tack + gear share (Powell 2008: no more than 20 %), with the heaviest rider for each.

Measurement (recordings from the running game):
  python riding_check.py seat   <dump> --rider seat --saddle saddle [--when sitting] [--max 0.02]
  python riding_check.py follow <dump> --rider pelvis --saddle saddle --mode sitting|posting|two-point
                                [--when mounted] [--search 0.25] [--max-lag 0.05] [--min-corr 0.8]
  python riding_check.py hooves <dump> --feet LF,RF,LH,RH [--contact cLF,cRF,cLH,cRH]
                                [--height-tol 0.02] [--max 0.02]
  python riding_check.py lean   <dump> --pos horse --lean lean [--tol 3]
  python riding_check.py grip   <dump> --pos horse [--mu 0.6] [--min-speed 1] [--tol 0.1]

  seat: the rider's seat point stays on the saddle's seat point (distance ≤ max; float = vertical
  gap, slide = horizontal) while --when is true. follow: the rider's pelvis height against the
  saddle's over the longest run of ticks — sitting: correlation ≥ 0.8 at a lag ≤ 0.05 s and an
  amplitude ratio 0.7–1.3; posting: the rider rises once per stride, i.e. at half the saddle's
  bounce frequency (ratio 0.4–0.6); two-point: the rider moves at most half as much as the saddle.
  hooves: horizontal slide of each hoof during each stance (contact probes, or height within
  --height-tol of the foot's lowest point). lean: a steady circle's fitted radius and speed give
  atan(v^2/(g*r)); the horse's recorded lean (degrees, or a body up vector) must be within ±tol
  degrees. grip: the horizontal acceleration across the path, at every tick above --min-speed,
  stays within mu*g (+tol) — no instant turns.

Recordings: the acceptance recorder JSON or JSON Lines; positions [x, y, z] metres, Y up.
Prints one JSON object {"verdict", "metrics": [...]} (predict: {"prediction": {...}}); exit code 1
on FAIL, 2 on bad input; NOT ASSESSED exits 0.
"""

import argparse
import json
import math
import sys

G = 9.81
GALLOP_DOUBLING = math.log2(1.10)  # gallop frequency +10 % for a doubling of speed (Heglund 1988)
BEATS = {"walk": 4, "trot": 2, "canter": 3, "gallop": 4}
BOUNCES = {"walk": 2, "trot": 2, "canter": 1, "gallop": 1}  # saddle vertical cycles per stride
# withers vertical range, unridden (Dunbar et al. 2008); gallop: horse trunk ~15 cm (Pfau 2009)
WITHERS_PP = {"walk": (0.07, 1.06), "trot": (0.09, 2.32), "canter": (0.18, 5.82),
              "gallop": (0.15, None)}


class NotAssessed(Exception):
    """The input cannot answer the question."""


def metric(name, value, threshold, ok, **extra):
    return {"metric": name, "value": value, "threshold": threshold,
            "verdict": "PASS" if ok else "FAIL", **extra}


def rnd(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, n)


def load_recording(path):
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("samples"), dict):
        samples = data["samples"]
        hz = float(data.get("physics_ticks_per_second") or 60)
        ticks = data.get("ticks") or []
        n = max((len(v) for v in samples.values()), default=0)
        times = [(t - ticks[0]) / hz for t in ticks] if ticks else [i / hz for i in range(n)]
        return times, samples
    rows = data if isinstance(data, list) else [json.loads(x) for x in text.splitlines()
                                                 if x.strip()]
    rows = [r for r in rows if r.get("type", "tick") in ("tick", "sample")]
    times = [float(r["t"]) if "t" in r else float(r.get("tick", i)) / 60.0
             for i, r in enumerate(rows)]
    if times:
        times = [t - times[0] for t in times]
    keys = []
    for row in rows:
        keys.extend(k for k in row if k not in keys and k not in ("type", "t", "tick"))
    return times, {k: [row.get(k) for row in rows] for k in keys}


def probe(samples, name):
    if name not in samples:
        raise NotAssessed(f"probe '{name}' not in recording; probes: " + ", ".join(sorted(samples)))
    return samples[name]


def is_pos(p):
    return isinstance(p, list) and len(p) >= 3


# ---------- predictions ----------

def gallop_freq(v, mass):
    """Heglund & Taylor 1988: f at the preferred galloping speed, +10 % per doubling of speed."""
    f_pref = 4.44 * mass ** -0.156
    v_pref = 2.78 * mass ** 0.176
    return f_pref * (v / v_pref) ** GALLOP_DOUBLING, f_pref, v_pref


def predict(a):
    out = {"case": a.case}
    if a.case == "gait":
        if not (a.v and a.v > 0 and a.leg > 0):
            raise ValueError("gait needs --v > 0 and --leg > 0 (m)")
        fr = a.v ** 2 / (a.g * a.leg)
        if fr < a.fr_trot:
            gait = "walk"
        elif fr < a.fr_canter:
            gait = "trot"
        elif fr < a.fr_gallop:
            gait = "canter"
        else:
            gait = "gallop"
        also = "trot" if gait == "canter" and fr < a.fr_trot_max else None

        def speed(f):
            return rnd(math.sqrt(f * a.g * a.leg), 3)
        out.update(froude=rnd(fr, 4), gait=gait, also_possible=also,
                   walk_trot_m_s=speed(a.fr_trot), trot_canter_m_s=speed(a.fr_canter),
                   free_trot_max_m_s=speed(a.fr_trot_max), canter_gallop_m_s=speed(a.fr_gallop),
                   note="switch gaits with hysteresis: hold the old gait a little past each "
                        "boundary (Heglund & Taylor 1988)")
    elif a.case == "stride":
        if not (a.gait and a.v and a.v > 0):
            raise ValueError("stride needs --gait and --v > 0")
        note = None
        if a.f:
            f = a.f
        elif a.gait == "walk":
            fr = a.v ** 2 / (a.g * a.leg)
            f = a.v / (2.3 * a.leg * fr ** 0.3)
        elif a.gait == "trot":
            f = 0.623 + 0.25 * a.v
            if not 1.42 <= a.v <= 5.46:
                note = "outside the measured trot range 1.42-5.46 m/s (680 kg horse)"
        else:
            f, _, _ = gallop_freq(a.v, a.mass)
            v_max = 3.71 * a.mass ** 0.176
            if a.v > v_max:
                note = (f"above the maximum sustained gallop {v_max:.2f} m/s the stride here is "
                        "too long; racing gallops use 2.34 Hz (Thoroughbred) to 2.88 Hz (Quarter "
                        "Horse) and ~7.5 m strides - pass --f")
        pp, at = WITHERS_PP[a.gait]
        out.update(gait=a.gait, stride_hz=rnd(f, 4), period_s=rnd(1 / f, 4),
                   stride_m=rnd(a.v / f, 4), beats_per_stride=BEATS[a.gait],
                   saddle_bounces_per_stride=BOUNCES[a.gait],
                   saddle_bounce_hz=rnd(f * BOUNCES[a.gait], 4),
                   posting_rise_hz=rnd(f, 4) if a.gait == "trot" else None,
                   withers_vertical_pp_m=pp, measured_at_m_s=at, note=note)
    elif a.case == "scale":
        if not (a.v and a.f and a.leg and a.to_leg):
            raise ValueError("scale needs --v --f --leg --to-leg")
        k = math.sqrt(a.to_leg / a.leg)
        out.update(froude=rnd(a.v ** 2 / (a.g * a.leg), 4), v_m_s=rnd(a.v * k, 4),
                   stride_hz=rnd(a.f / k, 4), stride_m=rnd(a.v / a.f * k * k, 4),
                   time_scale=rnd(k, 4), mass_ratio_isometric=rnd((a.to_leg / a.leg) ** 3, 4))
    elif a.case == "turn":
        if not (a.v and a.r and a.r > 0):
            raise ValueError("turn needs --v and --r > 0")
        lat = a.v ** 2 / a.r
        out.update(lean_deg=rnd(math.degrees(math.atan(lat / a.g)), 3),
                   lateral_accel_m_s2=rnd(lat, 4), lateral_g=rnd(lat / a.g, 4),
                   heading_rate_deg_s=rnd(math.degrees(a.v / a.r), 3),
                   grip_ok=lat <= a.mu * a.g,
                   min_radius_m=rnd(a.v ** 2 / (a.mu * a.g), 3),
                   max_speed_on_r_m_s=rnd(math.sqrt(a.mu * a.g * a.r), 3),
                   max_lean_deg=rnd(math.degrees(math.atan(a.mu)), 2),
                   note="measured horses lean 1.2 ± 2.4° less than this (Pfau 2012, trot)")
    elif a.case == "stop":
        if not (a.v and a.v > 0):
            raise ValueError("stop needs --v > 0")
        dec = a.decel if a.decel else a.mu * a.g
        if dec <= 0:
            raise ValueError("--decel must be > 0")
        out.update(decel_m_s2=rnd(dec, 4), distance_m=rnd(a.v * a.delay + a.v ** 2 / (2 * dec), 3),
                   time_s=rnd(a.delay + a.v / dec, 3), rider_load_g=rnd(dec / a.g, 4),
                   rider_force_n=rnd(a.rider * dec, 1) if a.rider else None,
                   exceeds_grip=dec > a.mu * a.g + 1e-9)
    elif a.case == "load":
        if not (a.horse and a.horse > 0 and a.rider is not None):
            raise ValueError("load needs --horse > 0 and --rider (kg)")
        tack, gear = a.tack or 0.0, a.gear or 0.0
        rider_share = a.rider / a.horse
        total_share = (a.rider + tack + gear) / a.horse
        status = ("overloaded" if total_share > 0.20 else
                  "caution" if rider_share > 0.15 else "ok")
        out.update(rider_share=rnd(rider_share, 4), total_share=rnd(total_share, 4),
                   status=status, max_rider_15pct_kg=rnd(0.15 * a.horse, 1),
                   max_rider_20pct_total_kg=rnd(0.20 * a.horse - tack - gear, 1),
                   note="20 % = rider + tack + gear (Powell 2008); 15 % = rider body mass only "
                        "(Dyson 2020 pilot)")
    return {"prediction": out}


# ---------- measurements ----------

def seat(a):
    _, samples = load_recording(a.dump)
    rider, sad = probe(samples, a.rider), probe(samples, a.saddle)
    when = probe(samples, a.when) if a.when else [True] * len(rider)
    pairs = [(r, s) for r, s, w in zip(rider, sad, when) if w and is_pos(r) and is_pos(s)]
    if len(pairs) < 10:
        raise NotAssessed("fewer than 10 ticks with both points while the condition holds")
    gaps = [math.dist(r[:3], s[:3]) for r, s in pairs]
    worst = max(gaps)
    return [metric("seat_gap_m", rnd(worst, 4), f"≤ {a.max}", worst <= a.max,
                   mean_m=rnd(sum(gaps) / len(gaps), 4),
                   float_m=rnd(max(abs(r[1] - s[1]) for r, s in pairs), 4),
                   slide_m=rnd(max(math.hypot(r[0] - s[0], r[2] - s[2]) for r, s in pairs), 4),
                   ticks=len(gaps))]


def longest_run(mask):
    best, start = (0, 0), None
    for i, m in enumerate(list(mask) + [False]):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    return best


def detrend(ys):
    n = len(ys)
    xm, ym = (n - 1) / 2, sum(ys) / n
    sxx = sum((i - xm) ** 2 for i in range(n)) or 1.0
    slope = sum((i - xm) * (y - ym) for i, y in enumerate(ys)) / sxx
    return [y - ym - slope * (i - xm) for i, y in enumerate(ys)]


def std(xs):
    return math.sqrt(sum(x * x for x in xs) / len(xs))


def crossing_freq(xs, dt):
    signs = [x > 0 for x in xs if x != 0]
    crossings = sum(1 for p, q in zip(signs, signs[1:]) if p != q)
    return crossings / (2 * dt * (len(xs) - 1))


def follow(a):
    times, samples = load_recording(a.dump)
    rider, sad = probe(samples, a.rider), probe(samples, a.saddle)
    when = probe(samples, a.when) if a.when else [True] * len(rider)
    ok = [bool(w) and is_pos(r) and is_pos(s) for r, s, w in zip(rider, sad, when)]
    i0, i1 = longest_run(ok)
    if i1 - i0 < 30:
        raise NotAssessed("fewer than 30 consecutive ticks with both points")
    ts = times[i0:i1]
    dt = sorted(b - c for b, c in zip(ts[1:], ts))[len(ts) // 2]
    if dt <= 0:
        raise ValueError("ticks are not increasing")
    r = detrend([p[1] for p in rider[i0:i1]])
    s = detrend([p[1] for p in sad[i0:i1]])
    sr, ss = std(r), std(s)
    if ss < 1e-4:
        raise NotAssessed("the saddle does not move vertically")
    ratio = sr / ss
    base = dict(samples=i1 - i0, saddle_pp_m=rnd(2 * math.sqrt(2) * ss, 4),
                rider_pp_m=rnd(2 * math.sqrt(2) * sr, 4))
    if a.mode == "two-point":
        return [metric("rider_amplitude_ratio", rnd(ratio, 4), "≤ 0.5", ratio <= 0.5, **base)]
    if a.mode == "posting":
        if sr < 1e-4:
            return [metric("rider_to_saddle_frequency", None, "0.5 ± 0.1", False,
                           note="the rider does not rise", **base)]
        fr_, fs = crossing_freq(r, dt), crossing_freq(s, dt)
        q = fr_ / fs
        return [metric("rider_to_saddle_frequency", rnd(q, 4), "0.5 ± 0.1", abs(q - 0.5) <= 0.1,
                       rider_hz=rnd(fr_, 3), saddle_hz=rnd(fs, 3), **base)]
    kmax = max(1, round(a.search / dt))
    best = (-2.0, 0)
    for k in range(-kmax, kmax + 1):
        pairs = [(s[i], r[i + k]) for i in range(len(s)) if 0 <= i + k < len(r)]
        num = sum(x * y for x, y in pairs)
        den = math.sqrt(sum(x * x for x, _ in pairs) * sum(y * y for _, y in pairs)) or 1e-12
        c = num / den
        if c > best[0] + 1e-9 or (abs(c - best[0]) <= 1e-9 and abs(k) < abs(best[1])):
            best = (c, k)
    corr, lag = best[0], best[1] * dt
    return [metric("rider_saddle_correlation", rnd(corr, 4), f"≥ {a.min_corr}",
                   corr >= a.min_corr, **base),
            metric("rider_lag_s", rnd(lag, 4), f"|lag| ≤ {a.max_lag}", abs(lag) <= a.max_lag + 1e-9,
                   note="positive = rider lags the saddle"),
            metric("rider_amplitude_ratio", rnd(ratio, 4), "0.7–1.3", 0.7 <= ratio <= 1.3)]


def hooves(a):
    _, samples = load_recording(a.dump)
    feet = [f.strip() for f in a.feet.split(",") if f.strip()]
    contacts = [c.strip() for c in a.contact.split(",")] if a.contact else None
    if contacts and len(contacts) != len(feet):
        raise ValueError("--contact needs one probe per foot")
    per_foot, stances = {}, 0
    for j, foot in enumerate(feet):
        pos = probe(samples, foot)
        if contacts:
            down = [bool(c) for c in probe(samples, contacts[j])]
        else:
            ys = [p[1] for p in pos if is_pos(p)]
            if not ys:
                raise NotAssessed(f"no positions for '{foot}'")
            floor = min(ys)
            down = [is_pos(p) and p[1] <= floor + a.height_tol for p in pos]
        worst, i = 0.0, 0
        while i < len(pos):
            if down[i] and is_pos(pos[i]):
                j0 = i
                while i < len(pos) and down[i] and is_pos(pos[i]):
                    i += 1
                if i - j0 >= 2:
                    td = pos[j0]
                    worst = max(worst, max(math.hypot(p[0] - td[0], p[2] - td[2])
                                           for p in pos[j0:i]))
                    stances += 1
            else:
                i += 1
        per_foot[foot] = rnd(worst, 4)
    if stances == 0:
        raise NotAssessed("no stance phases found")
    worst = max(per_foot.values())
    return [metric("hoof_stance_slip_m", worst, f"≤ {a.max}", worst <= a.max,
                   per_foot=per_foot, stances=stances)]


def fit_circle(xs, zs):
    n = len(xs)
    sx, sz = sum(xs), sum(zs)
    sxx = sum(x * x for x in xs)
    szz = sum(z * z for z in zs)
    sxz = sum(x * z for x, z in zip(xs, zs))
    r2 = [x * x + z * z for x, z in zip(xs, zs)]
    b = [sum(r * x for r, x in zip(r2, xs)), sum(r * z for r, z in zip(r2, zs)), sum(r2)]
    m = [[sxx, sxz, sx], [sxz, szz, sz], [sx, sz, n]]

    def det(q):
        return (q[0][0] * (q[1][1] * q[2][2] - q[1][2] * q[2][1])
                - q[0][1] * (q[1][0] * q[2][2] - q[1][2] * q[2][0])
                + q[0][2] * (q[1][0] * q[2][1] - q[1][1] * q[2][0]))
    d = det(m)
    if abs(d) < 1e-9:
        raise NotAssessed("positions do not describe a circle")
    sol = []
    for i in range(3):
        mi = [row[:] for row in m]
        for r in range(3):
            mi[r][i] = b[r]
        sol.append(det(mi) / d)
    cx, cz = sol[0] / 2, sol[1] / 2
    return cx, cz, math.sqrt(sol[2] + cx * cx + cz * cz)


def lean_deg(value):
    if isinstance(value, (int, float)):
        return abs(float(value))
    if isinstance(value, list) and len(value) >= 3:
        norm = math.sqrt(sum(c * c for c in value[:3]))
        if norm > 0:
            return math.degrees(math.acos(max(-1.0, min(1.0, value[1] / norm))))
    return None


def lean(a):
    times, samples = load_recording(a.dump)
    rows = [(t, p, lean_deg(q)) for t, p, q in zip(times, probe(samples, a.pos),
                                                     probe(samples, a.lean))
            if is_pos(p) and lean_deg(q) is not None]
    if len(rows) < 10:
        raise NotAssessed("fewer than 10 samples with a position and a lean")
    _, _, radius = fit_circle([p[0] for _, p, _ in rows], [p[2] for _, p, _ in rows])
    dist = sum(math.hypot(q[1][0] - p[1][0], q[1][2] - p[1][2]) for p, q in zip(rows, rows[1:]))
    v = dist / (rows[-1][0] - rows[0][0])
    predicted = math.degrees(math.atan(v * v / (G * radius)))
    measured = sum(x for _, _, x in rows) / len(rows)
    err = abs(measured - predicted)
    return [metric("lean_error_deg", rnd(err, 3), f"≤ {a.tol}", err <= a.tol,
                   measured_deg=rnd(measured, 3), predicted_deg=rnd(predicted, 3),
                   radius_m=rnd(radius, 3), speed_m_s=rnd(v, 3))]


def grip(a):
    times, samples = load_recording(a.dump)
    rows = [(t, p) for t, p in zip(times, probe(samples, a.pos)) if is_pos(p)]
    if len(rows) < 10:
        raise NotAssessed("fewer than 10 samples")
    worst, worst_rate, checked = 0.0, 0.0, 0
    for (t0, p0), (t1, p1), (t2, p2) in zip(rows, rows[1:], rows[2:]):
        h0, h1 = t1 - t0, t2 - t1
        if h0 <= 0 or h1 <= 0:
            continue
        vx, vz = (p2[0] - p0[0]) / (h0 + h1), (p2[2] - p0[2]) / (h0 + h1)
        speed = math.hypot(vx, vz)
        if speed < a.min_speed:
            continue
        ax = 2 * ((p2[0] - p1[0]) / h1 - (p1[0] - p0[0]) / h0) / (h0 + h1)
        az = 2 * ((p2[2] - p1[2]) / h1 - (p1[2] - p0[2]) / h0) / (h0 + h1)
        lat = abs(vx * az - vz * ax) / speed
        worst = max(worst, lat)
        worst_rate = max(worst_rate, math.degrees(lat / speed))
        checked += 1
    if checked == 0:
        raise NotAssessed(f"no ticks faster than {a.min_speed} m/s")
    limit = a.mu * G * (1 + a.tol)
    return [metric("max_lateral_g", rnd(worst / G, 4), f"≤ {rnd(limit / G, 4)}", worst <= limit,
                   max_heading_rate_deg_s=rnd(worst_rate, 2), ticks=checked)]


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("predict")
    pr.add_argument("case", choices=["gait", "stride", "scale", "turn", "stop", "load"])
    for name in ("v", "f", "r", "decel", "rider", "horse", "tack", "gear"):
        pr.add_argument(f"--{name}", type=float)
    pr.add_argument("--to-leg", type=float)
    pr.add_argument("--gait", choices=list(BEATS))
    pr.add_argument("--leg", type=float, default=1.25)
    pr.add_argument("--mass", type=float, default=500.0)
    pr.add_argument("--mu", type=float, default=0.6)
    pr.add_argument("--delay", type=float, default=0.0)
    pr.add_argument("--g", type=float, default=G)
    pr.add_argument("--fr-trot", type=float, default=0.34)
    pr.add_argument("--fr-canter", type=float, default=1.3)
    pr.add_argument("--fr-gallop", type=float, default=5.0)
    pr.add_argument("--fr-trot-max", type=float, default=2.8)
    s = sub.add_parser("seat")
    s.add_argument("dump")
    s.add_argument("--rider", required=True)
    s.add_argument("--saddle", required=True)
    s.add_argument("--when")
    s.add_argument("--max", type=float, default=0.02)
    f = sub.add_parser("follow")
    f.add_argument("dump")
    f.add_argument("--rider", required=True)
    f.add_argument("--saddle", required=True)
    f.add_argument("--mode", choices=["sitting", "posting", "two-point"], default="sitting")
    f.add_argument("--when")
    f.add_argument("--search", type=float, default=0.25)
    f.add_argument("--max-lag", type=float, default=0.05)
    f.add_argument("--min-corr", type=float, default=0.8)
    h = sub.add_parser("hooves")
    h.add_argument("dump")
    h.add_argument("--feet", required=True)
    h.add_argument("--contact")
    h.add_argument("--height-tol", type=float, default=0.02)
    h.add_argument("--max", type=float, default=0.02)
    le = sub.add_parser("lean")
    le.add_argument("dump")
    le.add_argument("--pos", required=True)
    le.add_argument("--lean", required=True)
    le.add_argument("--tol", type=float, default=3.0)
    gr = sub.add_parser("grip")
    gr.add_argument("dump")
    gr.add_argument("--pos", required=True)
    gr.add_argument("--mu", type=float, default=0.6)
    gr.add_argument("--min-speed", type=float, default=1.0)
    gr.add_argument("--tol", type=float, default=0.1)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "predict":
            print(json.dumps(predict(a), ensure_ascii=False))
            return 0
        metrics = {"seat": seat, "follow": follow, "hooves": hooves, "lean": lean,
                   "grip": grip}[a.cmd](a)
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
