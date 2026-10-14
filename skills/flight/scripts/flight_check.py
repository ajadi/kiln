"""Checks for flight — jetpacks, gliders, wingsuits, aircraft, helicopters, drones — against exact
answers (Python 3.12+, stdlib only).

Prediction (design time):
  python flight_check.py predict hover  --mass 100 --thrust 1300 [--g 9.81]
  python flight_check.py predict stall  --mass 1111 --area 16.2 --clmax 1.6 [--rho 1.225]
  python flight_check.py predict turn   --v 60 --bank 30 [--vs 27]
  python flight_check.py predict glide  --ratio 9 --height 1000 --v 10
  python flight_check.py predict rotor  --mass 2000 --diameter 11 [--fm 0.75] [--rho 1.225]
  python flight_check.py predict fuel   --capacity 40 --burn 4
  python flight_check.py predict loadout --dry 30.6 --pilot 80 --gadgets 5 --fuel 26.4 --thrust 1334
                                        [--isp 140 | --tsfc 2.8e-5]

  hover: thrust-to-weight T/W, net climb acceleration (T - W)/m, the steepest lean that still holds
  altitude acos(W/T), and the lean acceleration g*tan(lean). stall: Vs = sqrt(2W/(rho*S*CLmax)),
  wing loading. turn: radius v^2/(g*tan(bank)), turn rate, load factor n = 1/cos(bank), stall
  speed in the turn Vs*sqrt(n). glide: distance = ratio*height, sink = v/ratio (v along the path,
  small angle), time to ground. rotor (momentum theory): induced velocity sqrt(T/(2*rho*A)),
  ideal hover power sqrt(T^3/(2*rho*A)), real power ideal/FM, disk loading. fuel: endurance.
  loadout: the weight of fuel and gadgets — T/W with a full and an empty tank, whether it can
  take off, the most gadget mass it can lift, and hover endurance while fuel burns off
  (t = c/g * ln(m0/m1), c = Isp*g0 for rockets or 1/TSFC for turbines).

Measurement (recordings from the running game):
  python flight_check.py hover <dump> --pos body [--when hovering] [--tol 0.25]
  python flight_check.py glide <dump> --pos body --ratio 9 [--tol 0.15]
  python flight_check.py turn  <dump> --pos body --bank 30 [--tol 0.15]

  hover: while --when is true (or always), the altitude stays within ±tol m of its mean (no bob or
  drift). glide: horizontal distance / altitude lost against the design glide ratio. turn: a steady
  circle's radius (fitted) against v^2/(g*tan(bank)) at the recorded mean speed.

Recordings: the acceptance recorder JSON or JSON Lines; positions [x, y, z] metres, Y up.
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


def positions(samples, name):
    if name not in samples:
        raise NotAssessed(f"probe '{name}' not in recording; probes: " + ", ".join(sorted(samples)))
    return samples[name]


# ---------- predictions ----------

def predict(a):
    out = {"case": a.case}
    if a.case == "hover":
        if not (a.mass and a.thrust):
            raise ValueError("hover needs --mass and --thrust (N)")
        w = a.mass * a.g
        tw = a.thrust / w
        out.update(thrust_to_weight=rnd(tw, 4), hovers=tw >= 1,
                   climb_accel=rnd((a.thrust - w) / a.mass, 4),
                   max_level_lean_deg=rnd(math.degrees(math.acos(1 / tw)), 2) if tw >= 1 else None,
                   lean_accel_at_max=rnd(a.g * math.sqrt(tw * tw - 1), 4) if tw >= 1 else None)
    elif a.case == "stall":
        if not (a.mass and a.area and a.clmax):
            raise ValueError("stall needs --mass --area --clmax")
        vs = math.sqrt(2 * a.mass * a.g / (a.rho * a.area * a.clmax))
        out.update(stall_m_s=rnd(vs, 3), stall_kn=rnd(vs * 1.94384, 2),
                   wing_loading_kg_m2=rnd(a.mass / a.area, 2))
    elif a.case == "turn":
        if not (a.v and a.bank):
            raise ValueError("turn needs --v and --bank")
        b = math.radians(a.bank)
        r = a.v ** 2 / (a.g * math.tan(b))
        n = 1 / math.cos(b)
        out.update(radius_m=rnd(r, 2), rate_deg_s=rnd(math.degrees(a.v / r), 3),
                   load_factor=rnd(n, 4),
                   stall_in_turn_m_s=rnd(a.vs * math.sqrt(n), 3) if a.vs else None)
    elif a.case == "glide":
        if not (a.ratio and a.height):
            raise ValueError("glide needs --ratio and --height")
        out.update(distance_m=rnd(a.ratio * a.height, 1))
        if a.v:
            sink = a.v / a.ratio
            out.update(sink_m_s=rnd(sink, 4), time_s=rnd(a.height / sink, 1))
    elif a.case == "rotor":
        if not (a.mass and a.diameter):
            raise ValueError("rotor needs --mass and --diameter")
        area = math.pi * (a.diameter / 2) ** 2
        thrust = a.mass * a.g
        vi = math.sqrt(thrust / (2 * a.rho * area))
        ideal = math.sqrt(thrust ** 3 / (2 * a.rho * area))
        out.update(disk_area_m2=rnd(area, 2), induced_m_s=rnd(vi, 3),
                   ideal_power_kw=rnd(ideal / 1000, 2), power_kw=rnd(ideal / a.fm / 1000, 2),
                   disk_loading_kg_m2=rnd(a.mass / area, 2))
    elif a.case == "fuel":
        if not (a.capacity and a.burn):
            raise ValueError("fuel needs --capacity and --burn (same units per minute)")
        out.update(endurance_min=rnd(a.capacity / a.burn, 3))
    elif a.case == "loadout":
        # everything that flies: device dry mass + pilot + gadgets + fuel; fuel burns off
        if not (a.dry is not None and a.pilot is not None and a.fuel is not None and a.thrust):
            raise ValueError("loadout needs --dry --pilot --fuel --thrust [--gadgets]")
        full = a.dry + a.pilot + (a.gadgets or 0.0) + a.fuel
        empty = full - a.fuel
        tw_full, tw_empty = a.thrust / (full * a.g), a.thrust / (empty * a.g)
        out.update(mass_full_kg=rnd(full, 2), mass_empty_kg=rnd(empty, 2),
                   tw_full=rnd(tw_full, 4), tw_empty=rnd(tw_empty, 4),
                   hovers_at_takeoff=tw_full >= 1,
                   max_gadgets_kg=rnd(a.thrust / a.g - (a.dry + a.pilot + a.fuel), 2))
        # hover endurance with mass falling as fuel burns, mdot = T / (Isp * g0) for rockets
        # or T * TSFC for turbines (kg per N per s): t = c / g * ln(m0 / m1) with c = Isp * g0
        if a.isp or a.tsfc:
            c = a.isp * 9.80665 if a.isp else 1.0 / a.tsfc
            hover_from = full if tw_full >= 1 else None
            if hover_from is None:  # burn until light enough to hover, then hover
                m_hover = a.thrust / a.g
                hover_from = m_hover if m_hover > empty else None
            out.update(hover_endurance_s=rnd(c / a.g * math.log(hover_from / empty), 2)
                       if hover_from else 0.0,
                       note="constant-fraction throttle to hover; real devices lose 10-40 % "
                            "to transients and reserve (working)")
    return {"prediction": out}


# ---------- measurements ----------

def hover(a):
    times, samples = load_recording(a.dump)
    pos = positions(samples, a.pos)
    when = samples.get(a.when) if a.when else [True] * len(pos)
    if a.when and when is None:
        raise NotAssessed(f"probe '{a.when}' not in recording")
    ys = [p[1] for p, w in zip(pos, when) if w and isinstance(p, list)]
    if len(ys) < 10:
        raise NotAssessed("fewer than 10 hovering samples")
    mean = sum(ys) / len(ys)
    dev = max(abs(y - mean) for y in ys)
    return [metric("hover_altitude_dev_m", rnd(dev, 4), f"≤ {a.tol}", dev <= a.tol,
                   mean_altitude=rnd(mean, 3), samples=len(ys))]


def glide(a):
    times, samples = load_recording(a.dump)
    pts = [p for p in positions(samples, a.pos) if isinstance(p, list)]
    if len(pts) < 10:
        raise NotAssessed("fewer than 10 samples")
    horiz = sum(math.hypot(b[0] - p[0], b[2] - p[2]) for p, b in zip(pts, pts[1:]))
    lost = pts[0][1] - pts[-1][1]
    if lost <= 0:
        return [metric("glide_ratio", None, a.ratio, False, note="no altitude lost")]
    ratio = horiz / lost
    err = abs(ratio - a.ratio) / a.ratio
    return [metric("glide_ratio", rnd(ratio, 3), f"{a.ratio} ± {a.tol:.0%}", err <= a.tol,
                   distance_m=rnd(horiz, 2), altitude_lost_m=rnd(lost, 2))]


def turn(a):
    times, samples = load_recording(a.dump)
    rows = [(t, p) for t, p in zip(times, positions(samples, a.pos)) if isinstance(p, list)]
    if len(rows) < 10:
        raise NotAssessed("fewer than 10 samples")
    xs = [p[0] for _, p in rows]
    zs = [p[2] for _, p in rows]
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
    if abs(d) < 1e-12:
        raise NotAssessed("positions do not describe a circle")
    sol = []
    for i in range(3):
        mi = [row[:] for row in m]
        for r in range(3):
            mi[r][i] = b[r]
        sol.append(det(mi) / d)
    cx, cz = sol[0] / 2, sol[1] / 2
    radius = math.sqrt(sol[2] + cx * cx + cz * cz)
    dist = sum(math.hypot(q[1][0] - p[1][0], q[1][2] - p[1][2]) for p, q in zip(rows, rows[1:]))
    v = dist / (rows[-1][0] - rows[0][0])
    expected = v * v / (G * math.tan(math.radians(a.bank)))
    err = abs(radius - expected) / expected
    return [metric("turn_radius_m", rnd(radius, 2), f"{rnd(expected, 2)} ± {a.tol:.0%}",
                   err <= a.tol, speed_m_s=rnd(v, 3), relative_error=rnd(err, 4))]


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("predict")
    pr.add_argument("case", choices=["hover", "stall", "turn", "glide", "rotor", "fuel",
                                     "loadout"])
    for name in ("mass", "thrust", "area", "clmax", "v", "bank", "vs", "ratio", "height",
                 "diameter", "capacity", "burn", "dry", "pilot", "gadgets", "fuel", "isp", "tsfc"):
        pr.add_argument(f"--{name}", type=float)
    pr.add_argument("--g", type=float, default=G)
    pr.add_argument("--rho", type=float, default=1.225)
    pr.add_argument("--fm", type=float, default=0.75)
    h = sub.add_parser("hover")
    h.add_argument("dump")
    h.add_argument("--pos", required=True)
    h.add_argument("--when")
    h.add_argument("--tol", type=float, default=0.25)
    gl = sub.add_parser("glide")
    gl.add_argument("dump")
    gl.add_argument("--pos", required=True)
    gl.add_argument("--ratio", type=float, required=True)
    gl.add_argument("--tol", type=float, default=0.15)
    t = sub.add_parser("turn")
    t.add_argument("dump")
    t.add_argument("--pos", required=True)
    t.add_argument("--bank", type=float, required=True)
    t.add_argument("--tol", type=float, default=0.15)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "predict":
            print(json.dumps(predict(a), ensure_ascii=False))
            return 0
        metrics = {"hover": hover, "glide": glide, "turn": turn}[a.cmd](a)
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
