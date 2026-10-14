"""Checks for wheeled vehicles — braking, cornering, suspension, top speed, launch, weight
transfer — against exact answers (Python 3.12+, stdlib only).

Prediction (design time):
  python vehicle_check.py predict stop     --v-kmh 100 --mu 0.8 [--reaction-s 1.0]
  python vehicle_check.py predict corner   --mu 0.9 --radius 50
  python vehicle_check.py predict ride     --k 30000 --mass 375 [--c 2500]
  python vehicle_check.py predict topspeed --power 100000 --cd 0.3 --area 2.2 --crr 0.012
                                           --mass 1500 [--rho 1.225] [--eff 1.0]
  python vehicle_check.py predict launch   --v-kmh 100 --mu 1.0 --driven-share 0.5
                                           [--power 100000 --mass 1500]
  python vehicle_check.py predict transfer --mass 1500 --a-g 0.8 --h 0.55 --wheelbase 2.7

  stop: braking distance v^2/(2*mu*g) plus reaction distance. corner: v_max = sqrt(mu*g*r),
  lateral acceleration mu*g. ride: per-corner natural frequency sqrt(k/m)/(2*pi) (m = sprung mass
  on that corner) and damping ratio c/(2*sqrt(k*m)). topspeed: solves P*eff = (0.5*rho*Cd*A*v^2 +
  Crr*m*g)*v. launch: acceleration limited by traction mu*g*driven_share (no weight transfer) and,
  with --power and --mass, by power P/(m*v); integrated to the target speed. transfer:
  longitudinal load transfer m*a*h/L (N and share of weight).

Measurement (recordings from the running game):
  python vehicle_check.py stop   <dump> --speed v --brake brake --expected-m 49.2 [--tol 0.1]
  python vehicle_check.py corner <dump> --pos car --speed v --expected-g 0.9 [--tol 0.1]
                                 [--last-s 3]
  python vehicle_check.py ride   <dump> --height body_y --expected-hz 1.4 [--tol 0.1]
                                 [--zeta 0.3 --zeta-tol 0.1]
  python vehicle_check.py launch <dump> --speed v --target-kmh 100 --expected-s 6.5 [--tol 0.1]

  stop: distance travelled (speed integrated) from the first tick the brake probe is on until the
  speed falls under 0.1 m/s. corner: radius from a circle fitted to the last --last-s of positions
  (X/Z plane), lateral acceleration v^2/r in g. ride: after a bump, frequency from the zero
  crossings of the body height about its final value, damping ratio from the logarithmic decrement
  of successive peaks. launch: time from the first moving tick to the target speed.

Recordings: the acceptance recorder JSON or JSON Lines; speed probes in m/s (scalar or vector),
positions [x, y, z] metres, Y up.
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


def speed_of(v):
    if isinstance(v, list):
        return math.sqrt(sum(c * c for c in v[:3]))
    if isinstance(v, (int, float)):
        return abs(float(v))
    return None


def height_of(v):
    if isinstance(v, list) and len(v) >= 2:
        return float(v[1])
    if isinstance(v, (int, float)):
        return float(v)
    return None


# ---------- predictions ----------

def launch_time(target, mu, share, power=None, mass=None, dt=0.001):
    v, t = 0.0, 0.0
    while v < target:
        a = mu * G * share
        if power and mass and v > 0:
            a = min(a, power / (mass * v))
        v += a * dt
        t += dt
        if t > 600:
            raise ValueError("target speed not reached within 10 minutes")
    return t


def predict(a):
    out = {"case": a.case}
    if a.case == "stop":
        if a.v_kmh is None or not a.mu:
            raise ValueError("stop needs --v-kmh and --mu")
        v = a.v_kmh / 3.6
        brake = v * v / (2 * a.mu * G)
        out.update(braking_m=rnd(brake, 3), reaction_m=rnd(v * a.reaction_s, 3),
                   total_m=rnd(brake + v * a.reaction_s, 3), decel_g=a.mu,
                   braking_s=rnd(v / (a.mu * G), 3))
    elif a.case == "corner":
        if not (a.mu and a.radius):
            raise ValueError("corner needs --mu and --radius")
        v = math.sqrt(a.mu * G * a.radius)
        out.update(v_max_m_s=rnd(v, 4), v_max_kmh=rnd(v * 3.6, 3), lateral_g=a.mu)
    elif a.case == "ride":
        if not (a.k and a.mass):
            raise ValueError("ride needs --k and --mass (sprung mass on that corner)")
        out.update(frequency_hz=rnd(math.sqrt(a.k / a.mass) / (2 * math.pi), 4),
                   damping_ratio=rnd((a.c or 0.0) / (2 * math.sqrt(a.k * a.mass)), 4))
    elif a.case == "topspeed":
        if not (a.power and a.cd and a.area and a.mass):
            raise ValueError("topspeed needs --power --cd --area --mass (and --crr)")
        p = a.power * a.eff

        def need(v):
            return (0.5 * a.rho * a.cd * a.area * v * v + (a.crr or 0.0) * a.mass * G) * v
        lo, hi = 0.0, 1000.0
        for _ in range(200):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if need(mid) < p else (lo, mid)
        out.update(v_max_m_s=rnd(lo, 4), v_max_kmh=rnd(lo * 3.6, 3),
                   drag_share_at_vmax=rnd(0.5 * a.rho * a.cd * a.area * lo ** 3 / p, 4))
    elif a.case == "launch":
        if a.v_kmh is None or not a.mu or not a.driven_share:
            raise ValueError("launch needs --v-kmh --mu --driven-share")
        target = a.v_kmh / 3.6
        out.update(traction_limited_s=rnd(target / (a.mu * G * a.driven_share), 3))
        if a.power and a.mass:
            out.update(time_s=rnd(launch_time(target, a.mu, a.driven_share, a.power, a.mass), 3))
    elif a.case == "transfer":
        if not (a.mass and a.a_g and a.h and a.wheelbase):
            raise ValueError("transfer needs --mass --a-g --h --wheelbase")
        dw = a.mass * a.a_g * G * a.h / a.wheelbase
        out.update(load_transfer_n=rnd(dw, 2), share_of_weight=rnd(dw / (a.mass * G), 4))
    return {"prediction": out}


# ---------- measurements ----------

def stop(a):
    times, samples = load_recording(a.dump)
    speeds = [speed_of(v) for v in probe(samples, a.speed)]
    brakes = probe(samples, a.brake)
    start = next((k for k, b in enumerate(brakes) if b not in (None, False, 0, 0.0, "")), None)
    if start is None:
        raise NotAssessed("brake never applied")
    dist, end = 0.0, None
    for k in range(start, len(times) - 1):
        if speeds[k] is None or speeds[k + 1] is None:
            continue
        dist += 0.5 * (speeds[k] + speeds[k + 1]) * (times[k + 1] - times[k])
        if speeds[k + 1] < 0.1:
            end = k + 1
            break
    if end is None:
        if dist > a.expected_m * (1 + a.tol):  # already too long, stopping or not
            return [metric("stopping_distance_m", rnd(dist, 3), f"{a.expected_m} ± {a.tol:.0%}",
                           False, v0_m_s=rnd(speeds[start], 3),
                           note="still moving at the end of the recording")]
        raise NotAssessed("the vehicle never stopped in the recording")
    err = abs(dist - a.expected_m) / a.expected_m
    return [metric("stopping_distance_m", rnd(dist, 3), f"{a.expected_m} ± {a.tol:.0%}",
                   err <= a.tol, v0_m_s=rnd(speeds[start], 3),
                   time_s=rnd(times[end] - times[start], 3), relative_error=rnd(err, 4))]


def fit_circle(pts):
    """Least-squares circle through (x, z) points (Kasa fit)."""
    n = len(pts)
    sx = sum(p[0] for p in pts)
    sz = sum(p[1] for p in pts)
    sxx = sum(p[0] ** 2 for p in pts)
    szz = sum(p[1] ** 2 for p in pts)
    sxz = sum(p[0] * p[1] for p in pts)
    r2 = [p[0] ** 2 + p[1] ** 2 for p in pts]
    b = [sum(r * p[0] for r, p in zip(r2, pts)), sum(r * p[1] for r, p in zip(r2, pts)), sum(r2)]
    m = [[sxx, sxz, sx], [sxz, szz, sz], [sx, sz, n]]

    def det(q):
        return (q[0][0] * (q[1][1] * q[2][2] - q[1][2] * q[2][1])
                - q[0][1] * (q[1][0] * q[2][2] - q[1][2] * q[2][0])
                + q[0][2] * (q[1][0] * q[2][1] - q[1][1] * q[2][0]))
    d = det(m)
    if abs(d) < 1e-12:
        raise NotAssessed("positions do not describe a circle")
    sol = []
    for i in range(3):
        mi = [row[:] for row in m]
        for r in range(3):
            mi[r][i] = b[r]
        sol.append(det(mi) / d)
    cx, cz = sol[0] / 2, sol[1] / 2
    return cx, cz, math.sqrt(sol[2] + cx * cx + cz * cz)


def corner(a):
    times, samples = load_recording(a.dump)
    t_end = times[-1] if times else 0
    rows = [(t, p, speed_of(v)) for t, p, v in zip(times, probe(samples, a.pos),
                                                   probe(samples, a.speed))
            if t >= t_end - a.last_s and isinstance(p, list)]
    if len(rows) < 10:
        raise NotAssessed("fewer than 10 samples in the steady-state window")
    cx, cz, r = fit_circle([(p[0], p[2]) for _, p, _ in rows])
    vs = [v for _, _, v in rows if v is not None]
    v = sum(vs) / len(vs)
    lat_g = v * v / r / G
    err = abs(lat_g - a.expected_g) / a.expected_g
    return [metric("lateral_g", rnd(lat_g, 4), f"{a.expected_g} ± {a.tol:.0%}", err <= a.tol,
                   radius_m=rnd(r, 3), speed_m_s=rnd(v, 3), relative_error=rnd(err, 4))]


def ride(a):
    times, samples = load_recording(a.dump)
    pts = [(t, height_of(v)) for t, v in zip(times, probe(samples, a.height))]
    pts = [(t, y) for t, y in pts if y is not None]
    if len(pts) < 20:
        raise NotAssessed("fewer than 20 samples")
    rest = sum(y for _, y in pts[-max(5, len(pts) // 10):]) / max(5, len(pts) // 10)
    dev = [(t, y - rest) for t, y in pts]
    crossings = [t0 + (t1 - t0) * (-y0) / (y1 - y0)
                 for (t0, y0), (t1, y1) in zip(dev, dev[1:]) if y0 < 0 <= y1]
    if len(crossings) < 2:
        raise NotAssessed("fewer than 2 upward crossings — overdamped or no bump")
    freq = (len(crossings) - 1) / (crossings[-1] - crossings[0])
    peaks = [y for (_, y0), (_, y), (_, y1) in zip(dev, dev[1:], dev[2:]) if y > y0 and y >= y1
             and y > 0]
    out = []
    err = abs(freq - a.expected_hz) / a.expected_hz
    out.append(metric("ride_frequency_hz", rnd(freq, 4), f"{a.expected_hz} ± {a.tol:.0%}",
                      err <= a.tol, relative_error=rnd(err, 4)))
    if a.zeta is not None:
        if len(peaks) >= 2 and peaks[1] > 0:
            delta = math.log(peaks[0] / peaks[1])
            zeta = delta / math.sqrt(4 * math.pi ** 2 + delta ** 2)
            out.append(metric("damping_ratio", rnd(zeta, 4), f"{a.zeta} ± {a.zeta_tol}",
                              abs(zeta - a.zeta) <= a.zeta_tol))
        else:
            out.append(metric("damping_ratio", None, a.zeta, False,
                              note="fewer than 2 positive peaks"))
    return out


def launch(a):
    times, samples = load_recording(a.dump)
    speeds = [speed_of(v) for v in probe(samples, a.speed)]
    target = a.target_kmh / 3.6
    start = next((k for k, v in enumerate(speeds) if v is not None and v > 0.1), None)
    reach = next((k for k, v in enumerate(speeds) if v is not None and v >= target), None)
    if start is None or reach is None:
        raise NotAssessed("the vehicle never reached the target speed")
    t = times[reach] - times[start]
    err = abs(t - a.expected_s) / a.expected_s
    return [metric("launch_time_s", rnd(t, 3), f"{a.expected_s} ± {a.tol:.0%}", err <= a.tol,
                   relative_error=rnd(err, 4))]


# ---------- cli ----------

def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("predict")
    pr.add_argument("case", choices=["stop", "corner", "ride", "topspeed", "launch", "transfer"])
    for name in ("v-kmh", "mu", "radius", "k", "mass", "c", "power", "cd", "area", "crr",
                 "driven-share", "a-g", "h", "wheelbase"):
        pr.add_argument(f"--{name}", type=float)
    pr.add_argument("--reaction-s", type=float, default=0.0)
    pr.add_argument("--rho", type=float, default=1.225)
    pr.add_argument("--eff", type=float, default=1.0)

    s = sub.add_parser("stop")
    s.add_argument("dump")
    s.add_argument("--speed", required=True)
    s.add_argument("--brake", required=True)
    s.add_argument("--expected-m", type=float, required=True)
    s.add_argument("--tol", type=float, default=0.1)

    c = sub.add_parser("corner")
    c.add_argument("dump")
    c.add_argument("--pos", required=True)
    c.add_argument("--speed", required=True)
    c.add_argument("--expected-g", type=float, required=True)
    c.add_argument("--tol", type=float, default=0.1)
    c.add_argument("--last-s", type=float, default=3.0)

    r = sub.add_parser("ride")
    r.add_argument("dump")
    r.add_argument("--height", required=True)
    r.add_argument("--expected-hz", type=float, required=True)
    r.add_argument("--tol", type=float, default=0.1)
    r.add_argument("--zeta", type=float)
    r.add_argument("--zeta-tol", type=float, default=0.1)

    la = sub.add_parser("launch")
    la.add_argument("dump")
    la.add_argument("--speed", required=True)
    la.add_argument("--target-kmh", type=float, required=True)
    la.add_argument("--expected-s", type=float, required=True)
    la.add_argument("--tol", type=float, default=0.1)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "predict":
            print(json.dumps(predict(a), ensure_ascii=False))
            return 0
        metrics = {"stop": stop, "corner": corner, "ride": ride, "launch": launch}[a.cmd](a)
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
