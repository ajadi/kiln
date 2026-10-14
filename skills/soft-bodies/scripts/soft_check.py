"""Checks for cloth, ropes, hair and soft bodies against exact answers (Python 3.12+, stdlib only).

Prediction (design time):
  python soft_check.py predict pendulum --length 1 [--amplitude 30] [--g 9.81]
  python soft_check.py predict catenary --span 10 --length 12
  python soft_check.py predict spring   --k 400 --mass 1 [--c 4] [--dt 0.0167]

  pendulum: small-angle period 2*pi*sqrt(L/g) and the exact large-amplitude period
  2*pi*sqrt(L/g)/AGM(1, cos(theta0/2)). catenary: a rope of --length hung between level supports
  --span apart: parameter a from L = 2a*sinh(S/(2a)), sag a*(cosh(S/(2a)) - 1), end slope. spring:
  natural frequency f = sqrt(k/m)/(2*pi), damping ratio c/(2*sqrt(k*m)), and the explicit-
  integration limit dt < 2/omega (symplectic Euler) — above it a stiff spring explodes; PBD/XPBD
  stay stable but lose stiffness instead.

Measurement (recordings and exports from the running game):
  python soft_check.py period <dump> --probe angle --expected 2.006 [--tol 0.03]
  python soft_check.py strain <edges.json> [--max 0.02]
  python soft_check.py sag    <rope.json> [--tol 0.05]
  python soft_check.py energy <dump> --total E [--after-s 0.5] [--tol 0.01]
  python soft_check.py settle <dump> --speed v [--below 0.05] [--max-s 10]

  period: mean time between upward zero crossings of a scalar probe (an angle, or one coordinate
  of the bob; vectors use x) against --expected. strain: edges of the simulated mesh/rope —
  (current - rest)/rest; max and p95 must stay under --max (cloth reads stretchy above ~2-5 %,
  working). sag: the lowest point of an exported rope below the support line against the catenary
  for its rest length and span (relative --tol). energy: after --after-s (the last input or pin
  release) the total must never rise by more than --tol relative. settle: first time after which
  the speed probe stays below --below, must be <= --max-s.

Exports: edges {"edges": [{"rest": 0.1, "a": [x,y,z], "b": [x,y,z]}, ...]};
rope {"points": [[x,y,z], ...], "rest_length": 12} (ordered from one support to the other).
Recordings: the acceptance recorder JSON or JSON Lines.
Prints one JSON object {"verdict", "metrics": [...]} (predict: {"prediction": {...}}); exit code 1
on FAIL, 2 on bad input.
"""

import argparse
import json
import math
import sys

G = 9.81


class NotAssessed(Exception):
    """The input cannot answer the question."""


def metric(name, value, threshold, ok, **extra):
    return {"metric": name, "value": value, "threshold": threshold,
            "verdict": "PASS" if ok else "FAIL", **extra}


def rnd(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, n)


def load_recording(path):
    """(times in s, samples {name: [values]}) from the recorder JSON or JSON Lines."""
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


def scalar(v):
    if isinstance(v, list) and v:
        return float(v[0])
    if isinstance(v, (int, float)):
        return float(v)
    return None


def agm(a, b):
    for _ in range(60):
        a, b = (a + b) / 2, math.sqrt(a * b)
    return a


def catenary_a(span, length):
    """Solve length = 2a*sinh(span/(2a)) for a (bisection on log a)."""
    if length <= span:
        raise ValueError("rope length must exceed the span")
    lo, hi = 1e-6 * span, 1e6 * span
    for _ in range(200):
        mid = math.sqrt(lo * hi)
        x = span / (2 * mid)
        val = 2 * mid * math.sinh(x) if x < 700 else math.inf
        if val > length:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


# ---------- predictions ----------

def predict(a):
    out = {"case": a.case}
    if a.case == "pendulum":
        if not a.length:
            raise ValueError("pendulum needs --length")
        t0 = 2 * math.pi * math.sqrt(a.length / a.g)
        th = math.radians(a.amplitude or 0.0)
        out.update(small_angle_period_s=rnd(t0, 5),
                   period_s=rnd(t0 / agm(1.0, math.cos(th / 2)), 5))
    elif a.case == "catenary":
        if not (a.span and a.length):
            raise ValueError("catenary needs --span and --length")
        c = catenary_a(a.span, a.length)
        x = a.span / (2 * c)
        out.update(parameter_a=rnd(c, 5), sag_m=rnd(c * (math.cosh(x) - 1), 5),
                   end_slope_deg=rnd(math.degrees(math.atan(math.sinh(x))), 3),
                   sag_over_span=rnd(c * (math.cosh(x) - 1) / a.span, 5))
    elif a.case == "spring":
        if not (a.k and a.mass):
            raise ValueError("spring needs --k and --mass")
        w = math.sqrt(a.k / a.mass)
        out.update(frequency_hz=rnd(w / (2 * math.pi), 5), omega_rad_s=rnd(w, 5),
                   damping_ratio=rnd((a.c or 0.0) / (2 * math.sqrt(a.k * a.mass)), 5),
                   explicit_dt_max_s=rnd(2 / w, 6))
        if a.dt:
            out.update(explicit_stable=a.dt < 2 / w)
    return {"prediction": out}


# ---------- measurements ----------

def period(a):
    times, samples = load_recording(a.dump)
    pts = [(t, scalar(v)) for t, v in zip(times, probe(samples, a.probe))]
    pts = [(t, y) for t, y in pts if y is not None]
    if len(pts) < 10:
        raise NotAssessed("fewer than 10 samples")
    mean = sum(y for _, y in pts) / len(pts)
    ups = [t0 + (t1 - t0) * (mean - y0) / (y1 - y0)
           for (t0, y0), (t1, y1) in zip(pts, pts[1:]) if y0 < mean <= y1]
    if len(ups) < 3:
        raise NotAssessed("fewer than 3 upward crossings")
    per = (ups[-1] - ups[0]) / (len(ups) - 1)
    err = abs(per - a.expected) / a.expected
    return [metric("period_s", rnd(per, 5), f"{a.expected} ± {a.tol:.0%}", err <= a.tol,
                   relative_error=rnd(err, 5), cycles=len(ups) - 1)]


def strain(a):
    with open(a.edges, encoding="utf-8-sig") as fh:
        edges = json.load(fh).get("edges") or []
    vals = []
    for e in edges:
        cur = math.dist(e["a"][:3], e["b"][:3])
        if e["rest"] > 0:
            vals.append((cur - e["rest"]) / e["rest"])
    if not vals:
        raise NotAssessed("no edges")
    vals.sort()
    p95 = vals[min(len(vals) - 1, int(len(vals) * 0.95))]
    worst = max(vals)
    return [metric("edge_strain_max", rnd(worst, 5), f"≤ {a.max}", worst <= a.max,
                   p95=rnd(p95, 5), most_compressed=rnd(vals[0], 5), edges=len(vals))]


def sag(a):
    with open(a.rope, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    pts = data["points"]
    if len(pts) < 3:
        raise NotAssessed("rope needs at least 3 points")
    p0, p1 = pts[0], pts[-1]
    span = math.dist([p0[0], p0[2]], [p1[0], p1[2]])
    support_y = (p0[1] + p1[1]) / 2
    lowest = min(p[1] for p in pts)
    measured = support_y - lowest
    c = catenary_a(span, float(data["rest_length"]))
    expected = c * (math.cosh(span / (2 * c)) - 1)
    err = abs(measured - expected) / expected
    return [metric("rope_sag_m", rnd(measured, 4), f"{rnd(expected, 4)} ± {a.tol:.0%}",
                   err <= a.tol, relative_error=rnd(err, 4), span_m=rnd(span, 4),
                   note="assumes level supports; a stretchy rope sags more than its rest length "
                        "predicts")]


def energy(a):
    times, samples = load_recording(a.dump)
    vals = [(t, v) for t, v in zip(times, probe(samples, a.total))
            if isinstance(v, (int, float)) and t >= a.after_s]
    if len(vals) < 5:
        raise NotAssessed("fewer than 5 samples after --after-s")
    running_min = vals[0][1]
    scale = max(abs(v) for _, v in vals) or 1.0
    worst_rise, at = 0.0, None
    for t, v in vals:
        if v - running_min > worst_rise:
            worst_rise, at = v - running_min, t
        running_min = min(running_min, v)
    rel = worst_rise / scale
    return [metric("energy_rise", rnd(rel, 6), f"≤ {a.tol}", rel <= a.tol,
                   at_s=rnd(at, 3) if at is not None else None,
                   note="largest rise above the running minimum, relative to the peak energy")]


def settle(a):
    times, samples = load_recording(a.dump)
    vals = [(t, scalar(v) if not isinstance(v, list) else math.sqrt(sum(c * c for c in v[:3])))
            for t, v in zip(times, probe(samples, a.speed))]
    vals = [(t, abs(v)) for t, v in vals if v is not None]
    if not vals:
        raise NotAssessed("no speed samples")
    t_rest = None
    for k in range(len(vals)):
        if all(v < a.below for _, v in vals[k:]):
            t_rest = vals[k][0]
            break
    return [metric("settle_time_s", rnd(t_rest, 3), f"≤ {a.max_s}",
                   t_rest is not None and t_rest <= a.max_s,
                   note=None if t_rest is not None else "never settled in the recording")]


# ---------- cli ----------

def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("predict")
    pr.add_argument("case", choices=["pendulum", "catenary", "spring"])
    for name in ("length", "amplitude", "span", "k", "mass", "c", "dt"):
        pr.add_argument(f"--{name}", type=float)
    pr.add_argument("--g", type=float, default=G)

    pe = sub.add_parser("period")
    pe.add_argument("dump")
    pe.add_argument("--probe", required=True)
    pe.add_argument("--expected", type=float, required=True)
    pe.add_argument("--tol", type=float, default=0.03)

    st = sub.add_parser("strain")
    st.add_argument("edges")
    st.add_argument("--max", type=float, default=0.02)

    sg = sub.add_parser("sag")
    sg.add_argument("rope")
    sg.add_argument("--tol", type=float, default=0.05)

    en = sub.add_parser("energy")
    en.add_argument("dump")
    en.add_argument("--total", required=True)
    en.add_argument("--after-s", type=float, default=0.5)
    en.add_argument("--tol", type=float, default=0.01)

    se = sub.add_parser("settle")
    se.add_argument("dump")
    se.add_argument("--speed", required=True)
    se.add_argument("--below", type=float, default=0.05)
    se.add_argument("--max-s", type=float, default=10.0)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "predict":
            print(json.dumps(predict(a), ensure_ascii=False))
            return 0
        metrics = {"period": period, "strain": strain, "sag": sag, "energy": energy,
                   "settle": settle}[a.cmd](a)
    except NotAssessed as exc:
        print(json.dumps({"verdict": "NOT ASSESSED", "reason": str(exc), "metrics": []},
                         ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"verdict": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    verdict = "FAIL" if any(m["verdict"] == "FAIL" for m in metrics) else "PASS"
    print(json.dumps({"verdict": verdict, "metrics": metrics}, ensure_ascii=False))
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
