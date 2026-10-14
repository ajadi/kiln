"""Checks for element/material systems (heat, cold, fire, water, electricity) against exact answers
(Python 3.12+, stdlib only).

Prediction (design time, no game needed):
  python element_check.py predict melt   --mass 1 --c 2100 --t0 -10 --t-melt 0 --latent 334000
                                          --power 500 [--time-scale 1]
  python element_check.py predict cool   --t0 90 --ambient 20 --tau 60 --target 30
  python element_check.py predict tau    --mass 1 --c 900 --h 10 --area 0.06
  python element_check.py predict ignite --mass 0.5 --c 1700 --t0 20 --t-ignite 300 --power 2000
  python element_check.py predict stable --alpha 1e-4 --dx 0.5 --dt 0.1 [--dims 2]
  python element_check.py predict front  --p 0.3 --dx 0.5 --hz 10 [--burn 3]

  melt/ignite: time to bring a lump to the threshold (and through the latent heat) at a constant
  net power, t = m*(c*dT + L)/P; --time-scale divides real seconds into game seconds. cool: time
  for Newton cooling T(t) = Ta + (T0 - Ta)*exp(-t/tau) to reach --target. tau: tau = m*c/(h*A).
  stable: explicit heat diffusion is stable when alpha*dt/dx^2 <= 1/(2*dims). front: lower bound
  of a probabilistic fire front, 1-D chain, p per tick per neighbour: v = p*dx*hz m/s; with
  --burn B (ticks a cell burns) the chance to pass a cell on is q = 1 - (1 - p)^B, the mean 1-D
  run is q/(1 - q) cells, and q against the 2-D bond percolation threshold 0.5 says whether
  fires die out or cross the map.

Measurement (recordings and grid exports from the running game):
  python element_check.py cooling   <dump> --temp T --ambient 20 --tau 60 [--tol 0.15]
  python element_check.py threshold <dump> --temp T --state S --to frozen --at 0 [--tol 1]
                                    [--from wet] [--above]
  python element_check.py conserve  <dump> --total E [--tol 0.01]
  python element_check.py diffusion <grid.json> --alpha 1e-4 [--tol 0.2]
  python element_check.py spread    <cells.json> --speed 0.5 [--tol 0.3] [--max-burn 30]
                                    [--cap 400] [--origin x,y]
  python element_check.py conduction <graph.json>

  cooling: fits ln((T - Ta)/(T0 - Ta)) against time; PASS when the fitted tau is within --tol
  (relative) of --tau. threshold: the first tick the state probe becomes --to; the temperature on
  that tick must sit within --tol of --at, and the state must not change before the temperature
  crossed --at (below it by default, --above for heating: melt, ignite, boil). conserve: the total
  of a closed system (heat energy, water volume, charge) drifts less than --tol relative.
  diffusion: grid snapshots of a hot spot; the spatial variance grows by 2*alpha*t per axis.
  spread: per-cell ignition times; regresses distance from the origin on ignition time (front
  speed, within --tol of --speed), checks that non-flammable cells never ignite, every cell burns
  out within --max-burn s and concurrent burning cells stay under --cap. conduction: powered nodes
  must be exactly the conductors reachable from a source through conductive nodes.

Recordings: the acceptance recorder JSON ({"physics_ticks_per_second", "samples": {...}}) or JSON
Lines with one object per tick ("t" seconds or "tick"). Grid exports:
  diffusion  {"dx": 0.5, "frames": [{"t": 0.0, "temp": [[...], ...]}, ...]}  (1-D: "temp": [...])
  spread     {"dx": 0.5, "cells": [{"x": 0, "y": 0, "flammable": true, "ignite_t": 0.0,
             "out_t": 6.2}, ...]}   (ignite_t null = never ignited; "material" is optional)
  conduction {"nodes": [{"id": "a", "conductive": true, "powered": true, "source": false}, ...],
             "edges": [["a", "b"], ...]}
Prints one JSON object {"verdict", "metrics": [...]} (predict: {"prediction": {...}}); verdict FAIL
if any metric fails, NOT ASSESSED if nothing could be measured. Exit code 1 on FAIL, 2 on bad input.
"""

import argparse
import json
import math
import sys


class NotAssessed(Exception):
    """The input cannot answer the question (missing probe, too few samples)."""


def metric(name, value, threshold, ok, **extra):
    return {"metric": name, "value": value, "threshold": threshold,
            "verdict": "PASS" if ok else "FAIL", **extra}


def rnd(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, n)


# ---------- input ----------

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
    hz = 60.0
    times = []
    for i, row in enumerate(rows):
        if "t" in row:
            times.append(float(row["t"]))
        elif "tick" in row:
            times.append(float(row["tick"]) / hz)
        else:
            times.append(i / hz)
    if times:
        t0 = times[0]
        times = [t - t0 for t in times]
    keys = []
    for row in rows:
        keys.extend(k for k in row if k not in keys and k not in ("type", "t", "tick"))
    return times, {k: [row.get(k) for row in rows] for k in keys}


def probe(samples, name):
    if name not in samples:
        raise NotAssessed(f"probe '{name}' not in recording; probes: " + ", ".join(sorted(samples)))
    return samples[name]


def load_json(path):
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def linfit(xs, ys):
    """Least squares slope and intercept."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise NotAssessed("all samples at the same x")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return slope, my - slope * mx


# ---------- predictions ----------

def predict(a):
    out = {"case": a.case}
    if a.case in ("melt", "ignite"):
        threshold = a.t_melt if a.case == "melt" else a.t_ignite
        if threshold is None or a.power is None or a.power <= 0:
            raise ValueError(f"{a.case} needs the threshold temperature and --power > 0")
        heat = a.mass * a.c * max(0.0, threshold - a.t0) + a.mass * (a.latent or 0.0)
        out.update(energy_j=rnd(heat, 1), real_s=rnd(heat / a.power, 2),
                   game_s=rnd(heat / a.power / a.time_scale, 2))
    elif a.case == "cool":
        if a.tau is None or a.target is None:
            raise ValueError("cool needs --tau and --target")
        frac = (a.target - a.ambient) / (a.t0 - a.ambient)
        if not 0 < frac < 1:
            raise ValueError("--target must lie between --t0 and --ambient")
        t = -a.tau * math.log(frac)
        out.update(real_s=rnd(t, 2), game_s=rnd(t / a.time_scale, 2),
                   half_life_s=rnd(a.tau * math.log(2), 2))
    elif a.case == "tau":
        if not (a.h and a.area):
            raise ValueError("tau needs --h and --area")
        tau = a.mass * a.c / (a.h * a.area)
        out.update(tau_s=rnd(tau, 2), game_tau_s=rnd(tau / a.time_scale, 2))
    elif a.case == "stable":
        if not (a.alpha and a.dx and a.dt):
            raise ValueError("stable needs --alpha, --dx and --dt")
        r = a.alpha * a.dt / a.dx ** 2
        limit = 1.0 / (2 * a.dims)
        out.update(r=rnd(r, 6), limit=rnd(limit, 6), stable=r <= limit,
                   max_dt_s=rnd(limit * a.dx ** 2 / a.alpha, 6))
    elif a.case == "front":
        if not (a.p and a.dx and a.hz):
            raise ValueError("front needs --p, --dx and --hz")
        out.update(speed_m_s=rnd(a.p * a.dx * a.hz, 4), seconds_per_cell=rnd(1 / (a.p * a.hz), 4),
                   note="1-D lower bound; a 4-neighbour 2-D grid runs faster along the axes "
                        "(Monte Carlo: 0.184 / 0.507 / 0.698 cells per tick at p 0.1 / 0.3 / 0.5)")
        if a.burn:
            q = 1 - (1 - a.p) ** a.burn
            out.update(pass_probability=rnd(q, 4),
                       mean_run_cells_1d=rnd(q / (1 - q), 3) if q < 1 else None,
                       regime_2d="dies out" if q < 0.45 else "runs away" if q > 0.55
                       else "critical: tiny changes flip it",
                       percolation_note="square-lattice bond percolation threshold is 0.5: below "
                                        "it 2-D fires stay small, above it they cross the map")
    return {"prediction": out}


# ---------- measurements ----------

def cooling(a):
    times, samples = load_recording(a.dump)
    temps = probe(samples, a.temp)
    t0_val = next((v for v in temps if isinstance(v, (int, float))), None)
    if t0_val is None or t0_val == a.ambient:
        raise NotAssessed("no starting temperature different from ambient")
    xs, ys = [], []
    for t, v in zip(times, temps):
        if not isinstance(v, (int, float)):
            continue
        ratio = (v - a.ambient) / (t0_val - a.ambient)
        if ratio <= 0.02:  # the tail is noise against ambient
            break
        xs.append(t)
        ys.append(math.log(ratio))
    if len(xs) < 5:
        raise NotAssessed("fewer than 5 usable samples before the curve reached ambient")
    slope, icept = linfit(xs, ys)
    if slope >= 0:
        return [metric("cooling_tau_s", None, a.tau, False, note="temperature does not decay")]
    tau = -1.0 / slope
    resid = max(abs(y - (slope * x + icept)) for x, y in zip(xs, ys))
    err = abs(tau - a.tau) / a.tau
    return [metric("cooling_tau_s", rnd(tau, 3), f"{a.tau} ± {a.tol:.0%}", err <= a.tol,
                   relative_error=rnd(err, 4), samples=len(xs),
                   max_log_residual=rnd(resid, 4))]


def threshold(a):
    times, samples = load_recording(a.dump)
    temps, states = probe(samples, a.temp), probe(samples, a.state)
    crossed = False
    prev = None
    for i, (t, v, s) in enumerate(zip(times, temps, states)):
        if isinstance(v, (int, float)):
            crossed = crossed or (v >= a.at if a.above else v <= a.at)
        if s == a.to and prev != a.to and (a.from_state is None or prev == a.from_state):
            ok_value = isinstance(v, (int, float)) and abs(v - a.at) <= a.tol
            early = not crossed and isinstance(v, (int, float)) and abs(v - a.at) > a.tol
            return [metric("transition_temperature", rnd(v, 3), f"{a.at} ± {a.tol}",
                           ok_value and not early, tick=i, t_s=rnd(t, 3), from_state=prev,
                           to_state=a.to, early=early)]
        prev = s
    reached = crossed
    return [metric("transition_temperature", None, f"{a.at} ± {a.tol}", not reached,
                   note=("temperature crossed the threshold but the state never became "
                         f"'{a.to}'") if reached else "threshold never reached; no transition "
                   "expected", to_state=a.to)]


def conserve(a):
    times, samples = load_recording(a.dump)
    vals = [v for v in probe(samples, a.total) if isinstance(v, (int, float))]
    if len(vals) < 2:
        raise NotAssessed("fewer than 2 samples of the total")
    ref = vals[0]
    scale = abs(ref) if ref else max(abs(v) for v in vals) or 1.0
    drift = max(abs(v - ref) for v in vals) / scale
    return [metric("conservation_drift", rnd(drift, 6), f"≤ {a.tol}", drift <= a.tol,
                   start=rnd(ref, 6), end=rnd(vals[-1], 6), samples=len(vals))]


def _variance_1d(row, dx):
    total = sum(row)
    if total <= 0:
        raise NotAssessed("snapshot has no excess heat above its minimum")
    mean = sum(i * dx * v for i, v in enumerate(row)) / total
    return sum(((i * dx - mean) ** 2) * v for i, v in enumerate(row)) / total


def diffusion(a):
    data = load_json(a.grid)
    dx = float(data["dx"])
    frames = data.get("frames") or []
    if len(frames) < 3:
        raise NotAssessed("need at least 3 snapshots")
    ts, vs = [], []
    for fr in frames:
        grid = fr["temp"]
        if grid and isinstance(grid[0], list):  # 2-D: average the per-axis variances
            base = min(min(r) for r in grid)
            ex = [[v - base for v in r] for r in grid]
            vx = _variance_1d([sum(col) for col in zip(*ex)], dx)
            vy = _variance_1d([sum(r) for r in ex], dx)
            var = (vx + vy) / 2
        else:
            base = min(grid)
            var = _variance_1d([v - base for v in grid], dx)
        ts.append(float(fr["t"]))
        vs.append(var)
    slope, _ = linfit(ts, vs)
    alpha = slope / 2
    err = abs(alpha - a.alpha) / a.alpha
    return [metric("diffusivity_m2_s", rnd(alpha, 8), f"{a.alpha} ± {a.tol:.0%}", err <= a.tol,
                   relative_error=rnd(err, 4), snapshots=len(frames),
                   note="valid while the spot stays away from the grid edges")]


def spread(a):
    data = load_json(a.cells)
    dx = float(data.get("dx", 1.0))
    cells = data.get("cells") or []
    lit = [c for c in cells if c.get("ignite_t") is not None]
    if len(lit) < 3:
        raise NotAssessed("fewer than 3 cells ignited")
    if a.origin:
        ox, oy = (float(v) for v in a.origin.split(","))
    else:
        first = min(lit, key=lambda c: c["ignite_t"])
        ox, oy = first["x"], first["y"]
    xs = [math.hypot(c["x"] - ox, c.get("y", 0) - oy) * dx for c in lit]
    ts = [float(c["ignite_t"]) for c in lit]
    out = []
    try:
        slope, _ = linfit(ts, xs)
        err = abs(slope - a.speed) / a.speed
        out.append(metric("front_speed_m_s", rnd(slope, 4), f"{a.speed} ± {a.tol:.0%}",
                          err <= a.tol, relative_error=rnd(err, 4), cells_lit=len(lit)))
    except NotAssessed as exc:
        out.append(metric("front_speed_m_s", None, a.speed, False, note=str(exc)))
    wrong = [c for c in lit if c.get("flammable") is False]
    out.append(metric("non_flammable_ignited", len(wrong), 0, not wrong,
                      examples=[(c["x"], c.get("y", 0), c.get("material")) for c in wrong[:5]]))
    if a.max_burn is not None:
        never_out = [c for c in lit if c.get("out_t") is None]
        too_long = [c for c in lit if c.get("out_t") is not None
                    and c["out_t"] - c["ignite_t"] > a.max_burn]
        out.append(metric("burn_out", len(never_out) + len(too_long), 0,
                          not never_out and not too_long, max_burn_s=a.max_burn,
                          still_burning=len(never_out), over_limit=len(too_long)))
    if a.cap is not None:
        events = sorted([(c["ignite_t"], 1) for c in lit]
                        + [(c["out_t"], -1) for c in lit if c.get("out_t") is not None],
                        key=lambda e: (e[0], e[1]))
        live = peak = 0
        for _, d in events:
            live += d
            peak = max(peak, live)
        out.append(metric("concurrent_burning_peak", peak, f"≤ {a.cap}", peak <= a.cap))
    return out


def conduction(a):
    data = load_json(a.graph)
    nodes = {str(n["id"]): n for n in data.get("nodes") or []}
    if not nodes:
        raise NotAssessed("graph has no nodes")
    adj = {k: set() for k in nodes}
    for u, v in data.get("edges") or []:
        u, v = str(u), str(v)
        if u in adj and v in adj:
            adj[u].add(v)
            adj[v].add(u)
    sources = [k for k, n in nodes.items() if n.get("source")]
    if not sources:
        raise NotAssessed("no source node")
    reach = set()
    stack = [s for s in sources if nodes[s].get("conductive", True)]
    while stack:
        k = stack.pop()
        if k in reach:
            continue
        reach.add(k)
        stack.extend(m for m in adj[k] if m not in reach and nodes[m].get("conductive"))
    powered = {k for k, n in nodes.items() if n.get("powered")}
    extra = sorted(powered - reach)
    missing = sorted(reach - powered)
    return [metric("powered_not_reachable", len(extra), 0, not extra, nodes=extra[:10]),
            metric("reachable_not_powered", len(missing), 0, not missing, nodes=missing[:10])]


# ---------- cli ----------

def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("predict")
    pr.add_argument("case", choices=["melt", "cool", "tau", "ignite", "stable", "front"])
    for name in ("mass", "c", "t0", "latent", "power", "tau", "target", "h", "area", "alpha",
                 "dx", "dt", "p", "hz", "burn"):
        pr.add_argument(f"--{name}", type=float)
    pr.add_argument("--t-melt", type=float)
    pr.add_argument("--t-ignite", type=float)
    pr.add_argument("--ambient", type=float, default=20.0)
    pr.add_argument("--dims", type=int, default=1)
    pr.add_argument("--time-scale", type=float, default=1.0)

    c = sub.add_parser("cooling")
    c.add_argument("dump")
    c.add_argument("--temp", required=True)
    c.add_argument("--ambient", type=float, required=True)
    c.add_argument("--tau", type=float, required=True)
    c.add_argument("--tol", type=float, default=0.15)

    t = sub.add_parser("threshold")
    t.add_argument("dump")
    t.add_argument("--temp", required=True)
    t.add_argument("--state", required=True)
    t.add_argument("--to", required=True)
    t.add_argument("--from", dest="from_state")
    t.add_argument("--at", type=float, required=True)
    t.add_argument("--tol", type=float, default=1.0)
    t.add_argument("--above", action="store_true")

    k = sub.add_parser("conserve")
    k.add_argument("dump")
    k.add_argument("--total", required=True)
    k.add_argument("--tol", type=float, default=0.01)

    d = sub.add_parser("diffusion")
    d.add_argument("grid")
    d.add_argument("--alpha", type=float, required=True)
    d.add_argument("--tol", type=float, default=0.2)

    s = sub.add_parser("spread")
    s.add_argument("cells")
    s.add_argument("--speed", type=float, required=True)
    s.add_argument("--tol", type=float, default=0.3)
    s.add_argument("--max-burn", type=float)
    s.add_argument("--cap", type=int)
    s.add_argument("--origin")

    g = sub.add_parser("conduction")
    g.add_argument("graph")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "predict":
            print(json.dumps(predict(a), ensure_ascii=False))
            return 0
        metrics = {"cooling": cooling, "threshold": threshold, "conserve": conserve,
                   "diffusion": diffusion, "spread": spread, "conduction": conduction}[a.cmd](a)
    except NotAssessed as exc:
        print(json.dumps({"verdict": "NOT ASSESSED", "reason": str(exc), "metrics": []},
                         ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"verdict": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}),
              file=sys.stdout)
        return 2
    verdict = "FAIL" if any(m["verdict"] == "FAIL" for m in metrics) else "PASS"
    print(json.dumps({"verdict": verdict, "metrics": metrics}, ensure_ascii=False))
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
