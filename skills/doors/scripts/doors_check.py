"""Checks for doors and entries — hinged and sliding doors, strip curtains, car doors and getting
into a car — against exact answers (Python 3.12+, stdlib only).

Prediction (design time):
  python doors_check.py predict clear    --leaf 0.9 [--angle 90] [--opening W] [--thickness 0.04]
                                         [--hardware 0] [--radius 0.3] [--margin 0.05]
                                         [--stature 1.75] [--cell 0.1]
  python doors_check.py predict swing    [--angle 90] (--speed 90 | --torque 18.7 | --force 22.2)
                                         [--leaf 0.9] [--mass 30] [--backset 0.065] [--hz 60]
  python doors_check.py predict standoff --side push|pull [--leaf 0.9] [--handle-height 1.0]
                                         [--stature 1.75] [--backset 0.065] [--proj 0.06]
                                         [--reach 0.8] [--radius 0.3] [--margin 0.05]
  python doors_check.py predict strips   --width 1.0 [--strip 0.2] [--overlap 0.5] [--body 0.47]
                                         [--length 2.2] [--thickness 0.002] [--density 1250]
  python doors_check.py predict car      --roof 1.33 --hpoint 0.595 --sill 0.40 [--stature 1.80]
                                         [--clearance 0.03] [--group control|older|high-bmi]
  python doors_check.py predict cardoor  --length 1.1 --angle 70 [--time 0.7] [--body 0.6]

  Plan view, hinge at the origin, the closed leaf along +x to the latch edge at x = leaf, the
  character on the side y > 0. Body proportions (Drillis-Contini, human-biomechanics skill):
  shoulder height 0.818H, hip 0.530H, thigh 0.245H, shoulder width 0.259H, shoulder to mid-grip
  0.386H; hip joint to head top 0.470H.

  clear: clear width of a hinged leaf (rotating about its hinge-side corner) at angle a:
  W - max(0, leaf*cos a) - thickness*sin a - hardware (W = opening, default the leaf); whether a
  capsule of diameter 2r + margin fits; the smallest angle at which it fits (closed form
  a = d + acos(K/R), K = W - hardware - 2r - margin, R = hypot(leaf, thickness), d = atan2(t, leaf));
  clear / shoulder width (< 1.3 turns the shoulders, Warren & Whang); with --cell, the navmesh
  corridor left after Godot rounds the agent radius up to a multiple of the cell size.
  swing: --speed: time = angle/speed, edge speed, ADA closer (90 -> 12 deg >= 5 s) and spring hinge
  (70 -> 0 deg >= 1.5 s), ANSI A156.10 full-power (to 80 deg >= 1.5 s) and A156.19 low-energy
  (>= 3 s) times. --torque / --force (at leaf - backset): from rest, I = m*leaf^2/3,
  t = sqrt(2a/(tau/I)), end speed, kinetic energy, and the Godot hinge motor max_impulse = tau/hz.
  standoff: where the character stands to reach the handle (horizontal reach
  sqrt((0.8*0.386H)^2 - (0.818H - handle)^2)); push: in front of the opening, latch-side hand;
  pull: the same front spot plus the angle at which the opening leaf hits the body and how far it
  must step back (outside a circle of leaf + r + margin round the hinge), and the clear spot beside
  the latch edge (hinge-side hand) if the handle is reachable from there.
  strips: strip pitch w*(1 - overlap), strips edge to edge ceil((W - w)/pitch) + 1, strips a body
  pushes (B + w)/pitch, mass per strip, swing period of a strip (rod about its top,
  2*pi*sqrt(2L/(3g))) and of a bead string (hanging chain, 4*pi/2.4048*sqrt(L/g)).
  car: head drop standing H + clearance - roof; trunk lean with the hips at the H-point
  acos((roof - clearance - hpoint)/0.47H); H-point vs standing hip (deep / sit / slide / climb,
  working bands); foot lift over the sill and the hip flexion with a vertical shank
  acos(1 - lift/thigh); a step when the sill is above 0.609 m (49 CFR 399.207); measured mean
  ingress and egress times by group (Xsens IMU study).
  cardoor: a front-hinged car door of length L at angle a: narrowest gap to the B-pillar and side
  space both L*sin a (L beyond 90 deg), edge arc, angular and edge speed, smallest angle for a body
  width asin(b/L).

Measurement (recordings from the running game):
  python doors_check.py grab        <dump> --hand hand_r --handle door.handle [--when grabbing]
                                    [--max 0.02]
  python doors_check.py follow      <dump> --hand hand_r --edge door.edge --hinge X,Z
                                    [--when holding] [--tol 5]
  python doors_check.py penetration <dump> (--depth P | --body B --edge door.edge --hinge X,Z
                                    --radius 0.3 [--thickness 0.04]) [--max 0.02]
  python doors_check.py passage     <dump> --body B --edge door.edge --hinge X,Z --closed X,Z
                                    --radius 0.3 [--thickness 0.04] [--margin 0.05] [--min-angle A]
  python doors_check.py aipass      <dump> --agents npc_1,npc_2 --door X,Z [--zone 2.0]
                                    [--max-stop 3.0] [--still 0.1]
  python doors_check.py swing       <dump> --angle door.angle --from 90 --to 12 --min-s 5 [--max-s S]

  grab: hand-to-handle distance on every tick where --when is true (the grab and hold), max <= --max.
  follow: while held, the angle round the hinge between the hand and the leaf's free edge stays
  constant (door follows the hand) within --tol degrees. penetration: deepest overlap of the body
  capsule (radius r) with the leaf segment hinge -> edge (thickness/2 each side), or a depth probe.
  passage: each time the body centre crosses the doorway line inside the opening, the door is open
  at least --min-angle (default: the smallest angle at which the capsule fits, from `clear`).
  aipass: per agent, the longest time it stands still (speed < --still m/s) inside --zone m of the
  door, <= --max-stop; it must enter the zone and leave it on the other side. swing: time for the
  door angle to go from --from to --to, between --min-s and --max-s.

Recordings: the acceptance recorder JSON or JSON Lines; positions [x, y, z] metres, Y up (the
plan view uses x and z); angles in degrees. Prints one JSON object {"verdict", "metrics": [...]}
(predict: {"prediction": {...}}); exit code 1 on FAIL, 2 on bad input, 0 for NOT ASSESSED.
"""

import argparse
import json
import math
import sys

G = 9.81
J01 = 2.404825557695773          # first zero of the Bessel function J0 (hanging chain)
CFR_FIRST_STEP_M = 0.609         # 49 CFR 399.207: first step no more than 609 mm above ground
# Xsens IMU study (93 participants), mean seconds: (ingress, egress)
CAR_TIMES = {"control": (2.97, 2.95), "high-bmi": (2.71, 4.42), "older": (4.33, 5.26)}


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


def xz(p):
    """Plan-view (x, z) of a recorded position [x, y, z] (or [x, z])."""
    if not isinstance(p, (list, tuple)) or len(p) < 2:
        return None
    return (float(p[0]), float(p[2])) if len(p) >= 3 else (float(p[0]), float(p[1]))


def parse_xz(text):
    parts = [float(v) for v in str(text).split(",")]
    if len(parts) != 2:
        raise ValueError(f"expected 'x,z', got '{text}'")
    return parts[0], parts[1]


def wrap180(deg):
    return (deg + 180.0) % 360.0 - 180.0


def seg_dist(p, a, b):
    """Distance from point p to segment a-b in the plane."""
    ax, az = a
    bx, bz = b
    dx, dz = bx - ax, bz - az
    ll = dx * dx + dz * dz
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - az) * dz) / ll))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (az + t * dz))


# ---------- geometry shared by predictions and measurements ----------

def clear_width(opening, leaf, thickness, angle_deg, hardware=0.0):
    a = math.radians(angle_deg)
    return opening - max(0.0, leaf * math.cos(a)) - thickness * math.sin(a) - hardware


def min_angle(opening, leaf, thickness, need, hardware=0.0):
    """Smallest opening angle (deg) at which the clear width reaches `need`; None if never."""
    k = opening - hardware - need
    if k < 0:
        return None
    if k >= leaf:
        return 0.0
    if k >= thickness:
        r = math.hypot(leaf, thickness)
        return math.degrees(math.atan2(thickness, leaf) + math.acos(k / r))
    return 180.0 - math.degrees(math.asin(k / thickness))  # only past 90 deg


def hit_angle(body, leaf, radius):
    """Opening angle (deg) at which a leaf swinging toward the body touches a circle of `radius`
    at `body` (x, y), hinge at the origin, leaf closed along +x; None if it never does."""
    r0 = math.hypot(*body)
    if r0 >= leaf + radius:
        return None
    if r0 <= radius:
        return 0.0
    beta = math.atan2(body[1], body[0])
    if math.sqrt(r0 * r0 - radius * radius) <= leaf:   # touches the leaf face
        theta = beta - math.asin(radius / r0)
    else:                                              # touches the leaf's free edge
        c = (r0 * r0 + leaf * leaf - radius * radius) / (2 * r0 * leaf)
        theta = beta - math.acos(max(-1.0, min(1.0, c)))
    return max(0.0, math.degrees(theta))


# ---------- predictions ----------

def predict(a):
    out = {"case": a.case}
    h = a.stature
    if a.case == "clear":
        if not a.leaf:
            raise ValueError("clear needs --leaf (m)")
        opening = a.opening or a.leaf
        angle = 90.0 if a.angle is None else a.angle
        clear = clear_width(opening, a.leaf, a.thickness, angle, a.hardware)
        need = 2 * a.radius + a.margin
        shoulder = 0.259 * h
        ang = min_angle(opening, a.leaf, a.thickness, need, a.hardware)
        out.update(clear_m=rnd(clear), capsule_needs_m=rnd(need), fits=clear >= need,
                   spare_m=rnd(clear - need), min_angle_deg=rnd(ang, 2),
                   shoulder_m=rnd(shoulder), shoulder_ratio=rnd(clear / shoulder, 3),
                   turns_shoulders=clear < 1.3 * shoulder)
        if a.cell:
            r_nav = math.ceil(a.radius / a.cell - 1e-9) * a.cell
            corridor = clear - 2 * r_nav
            out.update(nav_radius_m=rnd(r_nav), nav_corridor_m=rnd(corridor),
                       nav_passable=corridor > 0)
    elif a.case == "swing":
        angle = 90.0 if a.angle is None else a.angle
        if a.speed:
            w = a.speed
            out.update(time_s=rnd(angle / w, 3), edge_speed_m_s=rnd(math.radians(w) * a.leaf),
                       time_90_to_12_s=rnd(78.0 / w, 3), ada_closer_ok=78.0 / w >= 5.0,
                       time_70_to_0_s=rnd(70.0 / w, 3), ada_spring_hinge_ok=70.0 / w >= 1.5,
                       time_to_80_s=rnd(80.0 / w, 3), a156_full_power_ok=80.0 / w >= 1.5,
                       a156_low_energy_ok=80.0 / w >= 3.0)
            if a.mass:
                inertia = a.mass * a.leaf ** 2 / 3
                out.update(inertia_kg_m2=rnd(inertia),
                           kinetic_energy_j=rnd(0.5 * inertia * math.radians(w) ** 2))
        elif a.torque or a.force:
            if not a.mass:
                raise ValueError("swing with --torque/--force needs --mass (kg)")
            arm = a.leaf - a.backset
            tau = a.torque if a.torque else a.force * arm
            inertia = a.mass * a.leaf ** 2 / 3
            alpha = tau / inertia
            t = math.sqrt(2 * math.radians(angle) / alpha)
            w_end = alpha * t
            out.update(torque_n_m=rnd(tau), inertia_kg_m2=rnd(inertia), time_s=rnd(t, 3),
                       end_speed_deg_s=rnd(math.degrees(w_end), 2),
                       end_edge_speed_m_s=rnd(w_end * a.leaf),
                       kinetic_energy_j=rnd(0.5 * inertia * w_end ** 2),
                       force_at_handle_n=rnd(tau / arm, 2),
                       godot_motor_max_impulse=rnd(tau / a.hz, 4))
        else:
            raise ValueError("swing needs --speed (deg/s), --torque (N*m) or --force (N)")
    elif a.case == "standoff":
        if a.side not in ("push", "pull"):
            raise ValueError("standoff needs --side push or pull")
        shoulder_h, arm = 0.818 * h, 0.386 * h
        reach = a.reach * arm
        dh = shoulder_h - a.handle_height
        horiz = math.sqrt(reach * reach - dh * dh) if reach > abs(dh) else 0.0
        half_sh = 0.259 * h / 2
        x_handle = a.leaf - a.backset
        front = (x_handle - half_sh, max(a.proj + horiz, a.radius))
        out.update(side=a.side, horizontal_reach_m=rnd(horiz),
                   needs_lean=a.proj + horiz < a.radius,
                   handle_x_m=rnd(x_handle),
                   front_spot={"x": rnd(front[0]), "y": rnd(front[1]), "hand": "latch-side"})
        if a.side == "pull":
            hit = hit_angle(front, a.leaf, a.radius)
            step = max(0.0, a.leaf + a.radius + a.margin - math.hypot(*front))
            out["front_spot"].update(door_hits_body_deg=rnd(hit, 2), step_back_m=rnd(step))
            x_c = a.leaf + a.radius + a.margin
            dx = (x_c - half_sh) - x_handle
            spot = None
            if horiz > abs(dx):
                y_c = a.proj + math.sqrt(horiz * horiz - dx * dx)
                if y_c >= a.radius:
                    spot = {"x": rnd(x_c), "y": rnd(y_c), "hand": "hinge-side"}
            out.update(clear_spot=spot)
    elif a.case == "strips":
        if not a.width:
            raise ValueError("strips needs --width (m)")
        pitch = a.strip * (1 - a.overlap)
        if pitch <= 0:
            raise ValueError("--overlap must be below 1")
        count = 1 if a.width <= a.strip else math.ceil((a.width - a.strip) / pitch - 1e-9) + 1
        mass = a.strip * a.thickness * a.length * a.density
        out.update(pitch_m=rnd(pitch), strips=count, strips_pushed=rnd((a.body + a.strip) / pitch, 2),
                   strip_mass_kg=rnd(mass, 3), curtain_mass_kg=rnd(mass * count, 2),
                   strip_period_s=rnd(2 * math.pi * math.sqrt(2 * a.length / (3 * G)), 3),
                   bead_string_period_s=rnd(4 * math.pi / J01 * math.sqrt(a.length / G), 3))
    elif a.case == "car":
        if a.roof is None or a.hpoint is None or a.sill is None:
            raise ValueError("car needs --roof, --hpoint and --sill (m above ground)")
        if a.group not in CAR_TIMES:
            raise ValueError("--group is control, older or high-bmi")
        hip, trunk, thigh = 0.530 * h, 0.470 * h, 0.245 * h
        avail = a.roof - a.clearance - a.hpoint
        if avail >= trunk:
            lean = 0.0
        elif avail <= 0:
            lean = None
        else:
            lean = math.degrees(math.acos(avail / trunk))
        d = a.hpoint - hip
        mode = "deep" if d < -0.45 else "sit" if d < -0.2 else "slide" if d <= 0.05 else "climb"
        lift = a.sill + 0.05
        flex = math.degrees(math.acos(1 - lift / thigh)) if lift <= 2 * thigh else None
        ingress, egress = CAR_TIMES[a.group]
        out.update(head_drop_standing_m=rnd(max(0.0, h + a.clearance - a.roof)),
                   trunk_lean_seated_deg=rnd(lean, 2), hpoint_minus_hip_m=rnd(d),
                   entry=mode, foot_lift_m=rnd(lift), step_over_hip_flex_deg=rnd(flex, 2),
                   needs_step=a.sill > CFR_FIRST_STEP_M, ingress_s=ingress, egress_s=egress)
    elif a.case == "cardoor":
        if not (a.length and a.angle):
            raise ValueError("cardoor needs --length (m) and --angle (deg)")
        th = math.radians(a.angle)
        gap = a.length * math.sin(th) if a.angle <= 90 else a.length
        out.update(gap_m=rnd(gap), side_space_m=rnd(gap),
                   edge_arc_m=rnd(a.length * th))
        if a.time:
            out.update(angular_speed_deg_s=rnd(a.angle / a.time, 2),
                       edge_speed_m_s=rnd(th / a.time * a.length))
        if a.body:
            out.update(min_angle_for_body_deg=rnd(math.degrees(math.asin(a.body / a.length)), 2)
                       if a.body <= a.length else None)
    return {"prediction": out}


# ---------- measurements ----------

def grab(a):
    _, samples = load_recording(a.dump)
    hand, handle = probe(samples, a.hand), probe(samples, a.handle)
    when = probe(samples, a.when) if a.when else [True] * len(hand)
    dists = [math.dist(p[:3], q[:3]) for p, q, w in zip(hand, handle, when)
             if w and isinstance(p, list) and isinstance(q, list)]
    if not dists:
        raise NotAssessed("no ticks with hand and handle positions while grabbing")
    grabs = sum(1 for i, w in enumerate(when) if w and (i == 0 or not when[i - 1]))
    worst = max(dists)
    return [metric("hand_to_handle_m", rnd(worst), f"≤ {a.max}", worst <= a.max,
                   mean_m=rnd(sum(dists) / len(dists)), ticks=len(dists), grabs=grabs)]


def follow(a):
    _, samples = load_recording(a.dump)
    hand, edge = probe(samples, a.hand), probe(samples, a.edge)
    when = probe(samples, a.when) if a.when else [True] * len(hand)
    hx, hz = parse_xz(a.hinge)
    offsets, dirs = [], []
    for p, e, w in zip(hand, edge, when):
        p, e = xz(p), xz(e)
        if not w or p is None or e is None:
            continue
        dh = math.degrees(math.atan2(p[1] - hz, p[0] - hx))
        de = math.degrees(math.atan2(e[1] - hz, e[0] - hx))
        offsets.append(wrap180(de - dh))
        dirs.append(de)
    if len(offsets) < 2:
        raise NotAssessed("fewer than 2 ticks with the door held")
    travel = max(abs(wrap180(d - dirs[0])) for d in dirs)
    if travel < 2.0:
        raise NotAssessed("the door did not move while held (< 2 deg)")
    err = max(abs(wrap180(o - offsets[0])) for o in offsets)
    return [metric("door_follow_error_deg", rnd(err, 2), f"≤ {a.tol}", err <= a.tol,
                   door_travel_deg=rnd(travel, 2), ticks=len(offsets))]


def penetration(a):
    _, samples = load_recording(a.dump)
    if a.depth:
        vals = [float(v) for v in probe(samples, a.depth) if isinstance(v, (int, float))]
    else:
        if not (a.body and a.edge and a.hinge and a.radius):
            raise ValueError("penetration needs --depth, or --body --edge --hinge --radius")
        hinge = parse_xz(a.hinge)
        vals = []
        for b, e in zip(probe(samples, a.body), probe(samples, a.edge)):
            b, e = xz(b), xz(e)
            if b is None or e is None:
                continue
            vals.append(max(0.0, a.radius + a.thickness / 2 - seg_dist(b, hinge, e)))
    if not vals:
        raise NotAssessed("no samples")
    worst = max(vals)
    return [metric("door_body_penetration_m", rnd(worst), f"≤ {a.max}", worst <= a.max,
                   ticks_over=sum(v > a.max for v in vals), ticks=len(vals))]


def passage(a):
    _, samples = load_recording(a.dump)
    hx, hz = parse_xz(a.hinge)
    cx, cz = parse_xz(a.closed)
    leaf = math.hypot(cx - hx, cz - hz)
    if leaf <= 0:
        raise ValueError("--closed must differ from --hinge")
    ux, uz = (cx - hx) / leaf, (cz - hz) / leaf
    closed_dir = math.degrees(math.atan2(uz, ux))
    need = 2 * a.radius + a.margin
    req = a.min_angle if a.min_angle is not None else min_angle(leaf, leaf, a.thickness, need)
    if req is None:
        return [metric("door_angle_at_crossing_deg", None, "capsule fits", False,
                       note="the capsule never fits this opening")]
    rows = []
    for b, e in zip(probe(samples, a.body), probe(samples, a.edge)):
        b, e = xz(b), xz(e)
        if b is None or e is None:
            continue
        rx, rz = b[0] - hx, b[1] - hz
        ang = abs(wrap180(math.degrees(math.atan2(e[1] - hz, e[0] - hx)) - closed_dir))
        rows.append((rx * ux + rz * uz, -rx * uz + rz * ux, ang))
    crossings = []
    for (s0, d0, a0), (s1, d1, a1) in zip(rows, rows[1:]):
        if (d0 < 0) == (d1 < 0):   # a sample exactly on the line counts once, on its far side
            continue
        f = d0 / (d0 - d1)
        s = s0 + f * (s1 - s0)
        if 0 <= s <= leaf:
            crossings.append(a0 + f * (a1 - a0))
    if not crossings:
        raise NotAssessed("the body never crossed the doorway")
    worst = min(crossings)
    return [metric("door_angle_at_crossing_deg", rnd(worst, 2), f"≥ {rnd(req, 2)}",
                   worst >= req - 1e-9, crossings=len(crossings), required_deg=rnd(req, 2))]


def aipass(a):
    times, samples = load_recording(a.dump)
    cx, cz = parse_xz(a.door)
    out = []
    for name in [n.strip() for n in a.agents.split(",") if n.strip()]:
        pts = probe(samples, name)
        rows = [(t, xz(p)) for t, p in zip(times, pts) if xz(p) is not None]
        inside = [math.hypot(p[0] - cx, p[1] - cz) <= a.zone for _, p in rows]
        if not any(inside):
            out.append(metric(f"{name}.longest_stop_at_door_s", None, f"≤ {a.max_stop}", False,
                              note="never reached the door zone"))
            continue
        first = inside.index(True)
        last = len(inside) - 1 - inside[::-1].index(True)
        longest = run = 0.0
        for i in range(first + 1, last + 1):
            (t0, p0), (t1, p1) = rows[i - 1], rows[i]
            dt = t1 - t0
            if dt <= 0:
                continue
            still = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / dt < a.still
            run = run + dt if (still and inside[i]) else 0.0
            longest = max(longest, run)
        passed = False
        if first > 0 and last < len(rows) - 1:
            pin, pout = rows[first - 1][1], rows[last + 1][1]
            passed = (pin[0] - cx) * (pout[0] - cx) + (pin[1] - cz) * (pout[1] - cz) < 0
        out.append(metric(f"{name}.longest_stop_at_door_s", rnd(longest, 3), f"≤ {a.max_stop}",
                          longest <= a.max_stop and passed, passed=passed,
                          transit_s=rnd(rows[last][0] - rows[first][0], 3)))
    if not out:
        raise NotAssessed("no agents given")
    return out


def swing(a):
    times, samples = load_recording(a.dump)
    vals = [(t, float(v)) for t, v in zip(times, probe(samples, a.angle))
            if isinstance(v, (int, float))]
    if len(vals) < 2:
        raise NotAssessed("fewer than 2 angle samples")
    sign = 1.0 if a.to >= a.frm else -1.0
    g = [((v - a.frm) * sign) for _, v in vals]
    k = next((i for i, x in enumerate(g) if x > 0), None)
    if k is None:
        raise NotAssessed(f"the door never moved past {a.frm} deg toward {a.to} deg")
    if k == 0:
        raise NotAssessed(f"the recording starts past {a.frm} deg")
    f = (0 - g[k - 1]) / (g[k] - g[k - 1])
    t_from = vals[k - 1][0] + f * (vals[k][0] - vals[k - 1][0])
    hh = [((v - a.to) * sign) for _, v in vals]
    m = next((i for i in range(k, len(hh)) if hh[i] >= 0), None)
    if m is None:
        raise NotAssessed(f"the door never reached {a.to} deg")
    f = (0 - hh[m - 1]) / (hh[m] - hh[m - 1]) if hh[m] != hh[m - 1] else 1.0
    t_to = vals[m - 1][0] + f * (vals[m][0] - vals[m - 1][0])
    dur = t_to - t_from
    ok = dur >= a.min_s and (a.max_s is None or dur <= a.max_s)
    thr = f"≥ {a.min_s}" + (f" and ≤ {a.max_s}" if a.max_s is not None else "")
    return [metric("swing_time_s", rnd(dur, 3), thr, ok, from_deg=a.frm, to_deg=a.to)]


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("predict")
    pr.add_argument("case", choices=["clear", "swing", "standoff", "strips", "car", "cardoor"])
    for name in ("angle", "opening", "cell", "speed", "torque", "force", "mass", "width", "roof",
                 "hpoint", "sill", "length", "time", "body"):
        pr.add_argument(f"--{name}", type=float)
    pr.add_argument("--leaf", type=float, default=0.9)
    pr.add_argument("--thickness", type=float)
    pr.add_argument("--hardware", type=float, default=0.0)
    pr.add_argument("--radius", type=float, default=0.3)
    pr.add_argument("--margin", type=float, default=0.05)
    pr.add_argument("--stature", type=float)
    pr.add_argument("--backset", type=float, default=0.065)
    pr.add_argument("--hz", type=float, default=60.0)
    pr.add_argument("--side")
    pr.add_argument("--handle-height", type=float, default=1.0)
    pr.add_argument("--proj", type=float, default=0.06)
    pr.add_argument("--reach", type=float, default=0.8)
    pr.add_argument("--strip", type=float, default=0.2)
    pr.add_argument("--overlap", type=float, default=0.5)
    pr.add_argument("--density", type=float, default=1250.0)
    pr.add_argument("--clearance", type=float, default=0.03)
    pr.add_argument("--group", default="control")
    gr = sub.add_parser("grab")
    gr.add_argument("dump")
    gr.add_argument("--hand", required=True)
    gr.add_argument("--handle", required=True)
    gr.add_argument("--when")
    gr.add_argument("--max", type=float, default=0.02)
    fo = sub.add_parser("follow")
    fo.add_argument("dump")
    fo.add_argument("--hand", required=True)
    fo.add_argument("--edge", required=True)
    fo.add_argument("--hinge", required=True)
    fo.add_argument("--when")
    fo.add_argument("--tol", type=float, default=5.0)
    pe = sub.add_parser("penetration")
    pe.add_argument("dump")
    pe.add_argument("--depth")
    pe.add_argument("--body")
    pe.add_argument("--edge")
    pe.add_argument("--hinge")
    pe.add_argument("--radius", type=float)
    pe.add_argument("--thickness", type=float, default=0.04)
    pe.add_argument("--max", type=float, default=0.02)
    pa = sub.add_parser("passage")
    pa.add_argument("dump")
    pa.add_argument("--body", required=True)
    pa.add_argument("--edge", required=True)
    pa.add_argument("--hinge", required=True)
    pa.add_argument("--closed", required=True)
    pa.add_argument("--radius", type=float, required=True)
    pa.add_argument("--thickness", type=float, default=0.04)
    pa.add_argument("--margin", type=float, default=0.05)
    pa.add_argument("--min-angle", type=float)
    ai = sub.add_parser("aipass")
    ai.add_argument("dump")
    ai.add_argument("--agents", required=True)
    ai.add_argument("--door", required=True)
    ai.add_argument("--zone", type=float, default=2.0)
    ai.add_argument("--max-stop", type=float, default=3.0)
    ai.add_argument("--still", type=float, default=0.1)
    sw = sub.add_parser("swing")
    sw.add_argument("dump")
    sw.add_argument("--angle", required=True)
    sw.add_argument("--from", dest="frm", type=float, required=True)
    sw.add_argument("--to", type=float, required=True)
    sw.add_argument("--min-s", type=float, default=0.0)
    sw.add_argument("--max-s", type=float)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "predict":
            if a.stature is None:
                a.stature = 1.80 if a.case == "car" else 1.75
            if a.thickness is None:
                a.thickness = 0.002 if a.case == "strips" else 0.04
            if a.case == "strips":
                a.body = 0.47 if a.body is None else a.body
                a.length = 2.2 if a.length is None else a.length
            print(json.dumps(predict(a), ensure_ascii=False))
            return 0
        metrics = {"grab": grab, "follow": follow, "penetration": penetration,
                   "passage": passage, "aipass": aipass, "swing": swing}[a.cmd](a)
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
