"""Checks for force fields — gravity, orbits, drag and wind, projectiles, large-world precision,
reflection and refraction — against exact answers (Python 3.12+, stdlib only).

Prediction (design time):
  python field_check.py predict orbit      --mu 3.986e14 --r 6.771e6
  python field_check.py predict kepler     --a1 1.0 --t1 365.25 --a2 1.524
  python field_check.py predict projectile --v 30 --angle 45 [--g 9.81] [--h0 0]
                                           [--mass 0.43 --cd 0.25 --area 0.038 --rho 1.225]
  python field_check.py predict terminal   --mass 80 --cd 1.0 --area 0.7 [--rho 1.225] [--g 9.81]
  python field_check.py predict ulp        --distance 10000
  python field_check.py predict refract    --n1 1.0 --n2 1.33 --angle 30

  orbit: circular speed sqrt(mu/r), period 2*pi*sqrt(r^3/mu), escape speed sqrt(2*mu/r)
  (mu = G*M). kepler: T2 = T1*(a2/a1)^1.5. projectile: range, flight time and apex in vacuum,
  and with quadratic drag F = 0.5*rho*Cd*A*v^2 integrated with RK4 (dt 1 ms) when drag is given.
  terminal: v_t = sqrt(2*m*g/(rho*Cd*A)), v(t) = v_t*tanh(g*t/v_t), time to 95 % of v_t.
  ulp: spacing of float32 (and float64) at a coordinate — the position step an object far from
  the origin can move by. refract: Snell n1*sin(a1) = n2*sin(a2), or total internal reflection
  past the critical angle.

Measurement (recordings and exports from the running game):
  python field_check.py orbit      <dump> --pos body --mu 1000 [--center 0,0,0] [--tol 0.02]
                                   [--drift 1e-4]
  python field_check.py fall       <dump> --pos body [--g 9.81] [--tol 0.05]
  python field_check.py terminal   <dump> --vel body_v --vt 55 [--tol 0.05]
  python field_check.py jitter     <dump> --pos body [--max-mm 1]
  python field_check.py beams      <beams.json> [--tol-deg 0.5]

  orbit: unwraps the angle around --center for the period (against 2*pi*sqrt(r^3/mu) at the mean
  radius) and tracks the specific energy v^2/2 - mu/r (velocity from positions) — relative drift
  must stay under --drift. fall: fits y = y0 + v0*t - g*t^2/2 to the samples before the first
  contact (y velocity reversal) and compares g. terminal: the plateau of the speed probe (last 20 %)
  against --vt. jitter: residual of each axis from a local quadratic fit (window 9) — a resting
  or smoothly moving object far from the origin must stay under --max-mm. beams: every segment
  pair at a surface obeys reflection (angle in = angle out) or Snell refraction with the n1/n2
  given in the export.

Recordings: the acceptance recorder JSON ({"physics_ticks_per_second", "samples": {...}}) or JSON
Lines with one object per tick ("t" seconds or "tick"); position probes are [x, y, z] in metres,
Y up. Beam export: {"hits": [{"normal": [x,y,z], "in": [dx,dy,dz], "out": [dx,dy,dz],
"kind": "reflect" | "refract", "n1": 1.0, "n2": 1.33}, ...]} (directions need not be unit length).
Prints one JSON object {"verdict", "metrics": [...]} (predict: {"prediction": {...}}); exit code 1
on FAIL, 2 on bad input.
"""

import argparse
import json
import math
import struct
import sys

G0 = 9.81


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


def probe(samples, name, vector=False):
    if name not in samples:
        raise NotAssessed(f"probe '{name}' not in recording; probes: " + ", ".join(sorted(samples)))
    vals = samples[name]
    if vector and not any(isinstance(v, list) for v in vals):
        raise NotAssessed(f"probe '{name}' is not a position vector")
    return vals


def linsolve3(m, b):
    """Solve a 3x3 system (Cramer)."""
    def det(a):
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    d = det(m)
    if abs(d) < 1e-300:
        raise NotAssessed("degenerate fit")
    out = []
    for i in range(3):
        mi = [row[:] for row in m]
        for r in range(3):
            mi[r][i] = b[r]
        out.append(det(mi) / d)
    return out


def quadfit(ts, ys):
    """y = c0 + c1*t + c2*t^2 least squares."""
    s = [sum(t ** k for t in ts) for k in range(5)]
    m = [[s[0], s[1], s[2]], [s[1], s[2], s[3]], [s[2], s[3], s[4]]]
    b = [sum(y * t ** k for t, y in zip(ts, ys)) for k in range(3)]
    return linsolve3(m, b)


# ---------- predictions ----------

def rk4_projectile(v, angle, g, h0, k_over_m, dt=0.001):
    vx, vy = v * math.cos(math.radians(angle)), v * math.sin(math.radians(angle))
    x, y, t, apex = 0.0, h0, 0.0, h0

    def acc(vx_, vy_):
        sp = math.hypot(vx_, vy_)
        return -k_over_m * sp * vx_, -g - k_over_m * sp * vy_

    while True:
        ax1, ay1 = acc(vx, vy)
        ax2, ay2 = acc(vx + ax1 * dt / 2, vy + ay1 * dt / 2)
        ax3, ay3 = acc(vx + ax2 * dt / 2, vy + ay2 * dt / 2)
        ax4, ay4 = acc(vx + ax3 * dt, vy + ay3 * dt)
        nx = x + dt * (vx + dt / 6 * (ax1 + ax2 + ax3))
        ny = y + dt * (vy + dt / 6 * (ay1 + ay2 + ay3))
        vx += dt / 6 * (ax1 + 2 * ax2 + 2 * ax3 + ax4)
        vy += dt / 6 * (ay1 + 2 * ay2 + 2 * ay3 + ay4)
        t += dt
        if ny < 0 and t > dt:
            frac = y / (y - ny) if y != ny else 1.0
            return x + (nx - x) * frac, t - dt + dt * frac, apex
        x, y = nx, ny
        apex = max(apex, y)
        if t > 3600:
            raise ValueError("projectile did not land within an hour")


def f32_spacing(x):
    """Distance from |x| (as float32) to the next float32."""
    x = abs(float(x))
    a = struct.unpack("<f", struct.pack("<f", x))[0]
    bits = struct.unpack("<I", struct.pack("<f", a))[0]
    nxt = struct.unpack("<f", struct.pack("<I", bits + 1))[0]
    return nxt - a


def predict(a):
    out = {"case": a.case}
    if a.case == "orbit":
        if not (a.mu and a.r):
            raise ValueError("orbit needs --mu and --r")
        out.update(v_circular=rnd(math.sqrt(a.mu / a.r), 4),
                   period_s=rnd(2 * math.pi * math.sqrt(a.r ** 3 / a.mu), 3),
                   v_escape=rnd(math.sqrt(2 * a.mu / a.r), 4))
    elif a.case == "kepler":
        if not (a.a1 and a.t1 and a.a2):
            raise ValueError("kepler needs --a1 --t1 --a2")
        out.update(t2=rnd(a.t1 * (a.a2 / a.a1) ** 1.5, 4))
    elif a.case == "projectile":
        if a.v is None or a.angle is None:
            raise ValueError("projectile needs --v and --angle")
        g, h0 = a.g, a.h0
        vy = a.v * math.sin(math.radians(a.angle))
        vx = a.v * math.cos(math.radians(a.angle))
        t_flight = (vy + math.sqrt(vy * vy + 2 * g * h0)) / g
        out.update(vacuum_range_m=rnd(vx * t_flight, 3), vacuum_flight_s=rnd(t_flight, 4),
                   vacuum_apex_m=rnd(h0 + vy * vy / (2 * g), 3))
        if a.cd and a.area and a.mass:
            k = 0.5 * a.rho * a.cd * a.area / a.mass
            rng, t, apex = rk4_projectile(a.v, a.angle, g, h0, k)
            out.update(drag_range_m=rnd(rng, 3), drag_flight_s=rnd(t, 3), drag_apex_m=rnd(apex, 3),
                       terminal_v=rnd(math.sqrt(g / k), 3))
    elif a.case == "terminal":
        if not (a.mass and a.cd and a.area):
            raise ValueError("terminal needs --mass --cd --area")
        vt = math.sqrt(2 * a.mass * a.g / (a.rho * a.cd * a.area))
        out.update(v_terminal=rnd(vt, 3), t95_s=rnd(vt / a.g * math.atanh(0.95), 3),
                   fall_distance_to_95_m=rnd(vt * vt / a.g * math.log(math.cosh(math.atanh(0.95))),
                                             2))
    elif a.case == "ulp":
        if a.distance is None:
            raise ValueError("ulp needs --distance")
        out.update(float32_step_m=f32_spacing(a.distance),
                   float32_step_mm=rnd(f32_spacing(a.distance) * 1000, 6),
                   float64_step_m=math.ulp(abs(float(a.distance))))
    elif a.case == "refract":
        if a.n1 is None or a.n2 is None or a.angle is None:
            raise ValueError("refract needs --n1 --n2 --angle")
        s = a.n1 / a.n2 * math.sin(math.radians(a.angle))
        crit = math.degrees(math.asin(a.n2 / a.n1)) if a.n1 > a.n2 else None
        if abs(s) > 1:
            out.update(total_internal_reflection=True, critical_angle_deg=rnd(crit, 4))
        else:
            out.update(total_internal_reflection=False,
                       refracted_deg=rnd(math.degrees(math.asin(s)), 4),
                       critical_angle_deg=rnd(crit, 4))
    return {"prediction": out}


# ---------- measurements ----------

def _vec_rows(times, vals):
    rows = [(t, v) for t, v in zip(times, vals) if isinstance(v, list) and len(v) >= 3
            and all(isinstance(c, (int, float)) for c in v[:3])]
    if len(rows) < 5:
        raise NotAssessed("fewer than 5 position samples")
    return rows


def orbit(a):
    times, samples = load_recording(a.dump)
    rows = _vec_rows(times, probe(samples, a.pos, vector=True))
    cx, cy, cz = (float(c) for c in a.center.split(","))
    rel = [(t, [p[0] - cx, p[1] - cy, p[2] - cz]) for t, p in rows]
    # orbital plane: use the two axes with the largest spread
    spread = [max(p[i] for _, p in rel) - min(p[i] for _, p in rel) for i in range(3)]
    i1, i2 = sorted(range(3), key=lambda i: -spread[i])[:2]
    ang, last, turns = [], None, 0.0
    for _, p in rel:
        th = math.atan2(p[i2], p[i1])
        if last is not None:
            d = th - last
            if d > math.pi:
                turns -= 2 * math.pi
            elif d < -math.pi:
                turns += 2 * math.pi
        ang.append(th + turns)
        last = th
    radii = [math.sqrt(sum(c * c for c in p)) for _, p in rel]
    r_mean = sum(radii) / len(radii)
    total_angle = abs(ang[-1] - ang[0])
    if total_angle < math.pi:
        raise NotAssessed("less than half an orbit recorded")
    span = rel[-1][0] - rel[0][0]
    period = 2 * math.pi * span / total_angle
    expected = 2 * math.pi * math.sqrt(r_mean ** 3 / a.mu)
    err = abs(period - expected) / expected
    energies = []
    for k in range(1, len(rel) - 1):
        dt = rel[k + 1][0] - rel[k - 1][0]
        if dt <= 0:
            continue
        v = [(rel[k + 1][1][i] - rel[k - 1][1][i]) / dt for i in range(3)]
        energies.append(0.5 * sum(c * c for c in v) - a.mu / radii[k])
    e0 = energies[0]
    drift = max(abs(e - e0) for e in energies) / abs(e0)
    return [metric("orbit_period_s", rnd(period, 4), f"{rnd(expected, 4)} ± {a.tol:.0%}",
                   err <= a.tol, relative_error=rnd(err, 5), mean_radius=rnd(r_mean, 4),
                   orbits=rnd(total_angle / (2 * math.pi), 3)),
            metric("orbit_energy_drift", rnd(drift, 6), f"≤ {a.drift}", drift <= a.drift,
                   note="specific energy v^2/2 - mu/r; velocity from central differences")]


def fall(a):
    times, samples = load_recording(a.dump)
    rows = _vec_rows(times, probe(samples, a.pos, vector=True))
    ys = [p[1] for _, p in rows]
    ts = [t for t, _ in rows]
    end = len(ys)
    for k in range(2, len(ys)):  # first contact: vertical velocity turns up
        if ys[k] - ys[k - 1] > 1e-6 and ys[k - 1] - ys[k - 2] < 0:
            end = k - 1
            break
    if end < 5:
        raise NotAssessed("fewer than 5 free-fall samples before contact")
    _, _, c2 = quadfit(ts[:end], ys[:end])
    g = -2 * c2
    err = abs(g - a.g) / a.g
    return [metric("gravity_m_s2", rnd(g, 4), f"{a.g} ± {a.tol:.0%}", err <= a.tol,
                   relative_error=rnd(err, 5), samples=end)]


def terminal(a):
    times, samples = load_recording(a.dump)
    vals = probe(samples, a.vel)
    speeds = []
    for v in vals:
        if isinstance(v, list):
            speeds.append(math.sqrt(sum(c * c for c in v[:3])))
        elif isinstance(v, (int, float)):
            speeds.append(abs(v))
    if len(speeds) < 10:
        raise NotAssessed("fewer than 10 speed samples")
    tail = speeds[int(len(speeds) * 0.8):]
    plateau = sum(tail) / len(tail)
    spread = (max(tail) - min(tail)) / plateau if plateau else math.inf
    err = abs(plateau - a.vt) / a.vt
    return [metric("terminal_speed_m_s", rnd(plateau, 4), f"{a.vt} ± {a.tol:.0%}",
                   err <= a.tol and spread <= a.tol, relative_error=rnd(err, 5),
                   tail_spread=rnd(spread, 5),
                   note="plateau = mean of the last 20 % of samples; must also be flat")]


def jitter(a):
    times, samples = load_recording(a.dump)
    rows = _vec_rows(times, probe(samples, a.pos, vector=True))
    w = 4
    worst = 0.0
    for k in range(w, len(rows) - w):
        ts = [rows[j][0] - rows[k][0] for j in range(k - w, k + w + 1)]
        for axis in range(3):
            ys = [rows[j][1][axis] for j in range(k - w, k + w + 1)]
            try:
                c0, _, _ = quadfit(ts, ys)
            except NotAssessed:
                continue
            worst = max(worst, abs(rows[k][1][axis] - c0))
    far = max(max(abs(c) for c in p[:3]) for _, p in rows)
    return [metric("position_jitter_mm", rnd(worst * 1000, 4), f"≤ {a.max_mm}",
                   worst * 1000 <= a.max_mm, distance_from_origin_m=rnd(far, 2),
                   float32_step_mm=rnd(f32_spacing(far) * 1000, 6))]


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    if n == 0:
        raise ValueError("zero-length direction")
    return [c / n for c in v]


def beams(a):
    with open(a.beams, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    hits = data.get("hits") or []
    if not hits:
        raise NotAssessed("no beam hits in the export")
    worst, bad = 0.0, []
    for i, h in enumerate(hits):
        n, d_in, d_out = _unit(h["normal"]), _unit(h["in"]), _unit(h["out"])
        cos_i = -sum(x * y for x, y in zip(d_in, n))
        if cos_i < 0:  # normal points away from the incoming ray
            n, cos_i = [-c for c in n], -cos_i
        a_in = math.degrees(math.acos(max(-1.0, min(1.0, cos_i))))
        if h.get("kind", "reflect") == "reflect":
            cos_o = sum(x * y for x, y in zip(d_out, n))
            expected = a_in
        else:
            cos_o = -sum(x * y for x, y in zip(d_out, n))
            s = h.get("n1", 1.0) / h.get("n2", 1.0) * math.sin(math.radians(a_in))
            if abs(s) > 1:
                bad.append({"hit": i, "error": "total internal reflection expected"})
                continue
            expected = math.degrees(math.asin(s))
        a_out = math.degrees(math.acos(max(-1.0, min(1.0, cos_o))))
        err = abs(a_out - expected)
        worst = max(worst, err)
        if err > a.tol_deg:
            bad.append({"hit": i, "kind": h.get("kind", "reflect"), "in_deg": rnd(a_in, 3),
                        "out_deg": rnd(a_out, 3), "expected_deg": rnd(expected, 3)})
    return [metric("beam_angle_error_deg", rnd(worst, 4), f"≤ {a.tol_deg}", not bad,
                   hits=len(hits), failures=bad[:10])]


# ---------- cli ----------

def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("predict")
    pr.add_argument("case", choices=["orbit", "kepler", "projectile", "terminal", "ulp",
                                     "refract"])
    for name in ("mu", "r", "a1", "t1", "a2", "v", "angle", "mass", "cd", "area", "distance",
                 "n1", "n2"):
        pr.add_argument(f"--{name}", type=float)
    pr.add_argument("--g", type=float, default=G0)
    pr.add_argument("--h0", type=float, default=0.0)
    pr.add_argument("--rho", type=float, default=1.225)

    o = sub.add_parser("orbit")
    o.add_argument("dump")
    o.add_argument("--pos", required=True)
    o.add_argument("--mu", type=float, required=True)
    o.add_argument("--center", default="0,0,0")
    o.add_argument("--tol", type=float, default=0.02)
    o.add_argument("--drift", type=float, default=1e-4)

    f = sub.add_parser("fall")
    f.add_argument("dump")
    f.add_argument("--pos", required=True)
    f.add_argument("--g", type=float, default=G0)
    f.add_argument("--tol", type=float, default=0.05)

    t = sub.add_parser("terminal")
    t.add_argument("dump")
    t.add_argument("--vel", required=True)
    t.add_argument("--vt", type=float, required=True)
    t.add_argument("--tol", type=float, default=0.05)

    j = sub.add_parser("jitter")
    j.add_argument("dump")
    j.add_argument("--pos", required=True)
    j.add_argument("--max-mm", type=float, default=1.0)

    b = sub.add_parser("beams")
    b.add_argument("beams")
    b.add_argument("--tol-deg", type=float, default=0.5)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "predict":
            print(json.dumps(predict(a), ensure_ascii=False))
            return 0
        metrics = {"orbit": orbit, "fall": fall, "terminal": terminal, "jitter": jitter,
                   "beams": beams}[a.cmd](a)
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
