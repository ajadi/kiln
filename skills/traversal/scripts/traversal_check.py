"""Checks for character traversal and body–object interaction — jumps, falls and landings,
obstacle moves (step, vault, mantle, climb, hang), openings and crawl, balance, load carriage,
seated and riding poses — against exact answers and the design's thresholds
(Python 3.12+, stdlib only).

Prediction (design time):
  python traversal_check.py predict jump      --height 0.5 | --v0 3.13
  python traversal_check.py predict runjump   --run-speed 6 --vy 2.0 [--keep 0.9]
  python traversal_check.py predict longjump  --run-speed 7 --angle 20 [--com 1.0]
  python traversal_check.py predict fall      --height 3 [--max-bw 6] [--mass 80]
  python traversal_check.py predict move      --obstacle 1.2 [--tiers move-tiers.json]
  python traversal_check.py predict capture   --speed 0.6 [--com 1.0]
  python traversal_check.py predict fit       --radius 0.3 --height 1.8 --gap-w 0.6 --gap-h 0.9
                                              [--crouch 1.2] [--crawl 0.5]
  python traversal_check.py predict load      --mass 80 --load 20 --speed 1.34 [--grade 0]
                                              [--terrain 1.0]
  python traversal_check.py predict float     --mass 75 --fat 15 [--lungs 2.4] [--gear-mass 20]
  python traversal_check.py predict wade      --depth 0.5 [--current 0.5] [--land-speed 1.4]
  python traversal_check.py predict packbounce --load 20 --k 5 [--zeta 0.1] [--cadence 2.8]
  python traversal_check.py predict packlean  --mass 75 --load 20 --offset 0.18
  python traversal_check.py predict lean      --v-kmh 50 --radius 30
  python traversal_check.py predict steer     --road-deg 10 --ratio 15

  jump: v0 = sqrt(2*g*h), airtime 2*v0/g. runjump: a jump from locomotion keeps --keep of the
  approach speed and adds --vy; the jump type the speed selects, takeoff angle, flight. longjump: centre-of-mass flight from a takeoff at --com
  height landing at the same height (vacuum). fall: impact speed sqrt(2*g*h), energy, the stopping
  distance that keeps the peak ground force under --max-bw body weights, d = v^2/(2*g*(N - 1)),
  and the landing tier from the tier table. move: which obstacle move a height selects
  (step-up / vault / mantle / climb-up / jump-grab / blocked) from the tier table (defaults below,
  working). capture: capture point x = v*sqrt(z/g) — the step length needed to stop a push.
  fit: does a standing / crouched / crawling capsule pass a gap of --gap-w x --gap-h. load:
  Pandolf metabolic rate M = 1.5W + 2(W + L)(L/W)^2 + eta(W + L)(1.5V^2 + 0.35*V*G) (W).
  float: body buoyancy from fat % (Siri) plus air in the lungs, fresh and sea water, what shows
  above water, and whether gear (density 7.85 steel by default) sinks it. wade: walking speed in
  water by depth and current (Postacchini 2018). packbounce: pack natural frequency and pack/body
  motion ratio at the step rate (mass on a spring). packlean: trunk lean that balances a pack.
  lean: motorcycle lean tan(phi) = v^2/(g*r). steer: steering-wheel angle = road-wheel angle *
  ratio.

Measurement (recordings and event exports from the running game):
  python traversal_check.py jump    <dump> --pos hero --apex 0.5 [--tol 0.05]
  python traversal_check.py moves   <events.json> [--tiers move-tiers.json]
  python traversal_check.py landings <events.json> [--tiers landing-tiers.json]
  python traversal_check.py jumps   <events.json> [--tiers jump-tiers.json] [--keep 0.85]
  python traversal_check.py rom     <gear.json> [--moves run,crouch,climb,kneel,guard]
  python traversal_check.py rom     <gear.json> [--moves run,crouch,climb,kneel,guard]
  python traversal_check.py contact <dump> --a hand_l --b grip_l [--when hold] [--max-m 0.02]
  python traversal_check.py balance <dump> --com com --support support [--margin 0.0]
  python traversal_check.py penetration <dump> --depth pen [--max-m 0.02]

  jump: apex height above the takeoff (y of the probe) against --apex. moves: every obstacle
  event {"height": h, "move": "vault"} must use the move the tier table selects for h. landings:
  every landing event {"fall_height": h, "landing": "roll"} must use the tier for h. jumps: every
  jump event {"approach_speed", "type", "takeoff_foot", "stance_foot", "speed_before",
  "speed_after"} must use the type the speed selects (standing / walking / running / sprinting),
  one-foot jumps take off from the stance foot, and running jumps keep >= --keep of their speed.
  rom: joint stops measured on the dressed model ({"stops": {"elbow_flex": 56, ...}} in degrees)
  against what the move sets need (base everyday reach always included) — the live failure was an
  armour elbow stopping at 56° and a pauldron at 60° shoulder flexion.
  contact: while --when is true (or always), the distance between two position probes (a hand and its grip, a
  foot and a peg, a hip and a seat) stays under --max-m. balance: the centre-of-mass ground
  projection [x, z] stays inside the support polygon (list of [x, z]) by --margin, except on ticks
  flagged "stepping": true. penetration: a depth probe (capsule or limb into geometry) stays under
  --max-m.

Tier tables (JSON): moves [{"max": 0.5, "move": "step-up"}, {"max": 1.1, "move": "vault"}, ...]
sorted by "max" (metres, top of obstacle above the feet); landings [{"max": 1.0, "landing":
"none"}, ...] (fall height in metres). Defaults are working values for a 1.80 m adult — set the
game's own table in data and pass it.
Prints one JSON object {"verdict", "metrics": [...]} (predict: {"prediction": {...}}); exit code 1
on FAIL, 2 on bad input.
"""

import argparse
import json
import math
import sys

G = 9.81

MOVE_TIERS = [  # working values, 1.80 m adult, top of obstacle above the feet
    {"max": 0.5, "move": "step-up"},
    {"max": 1.2, "move": "vault"},
    {"max": 1.5, "move": "mantle"},
    {"max": 2.2, "move": "climb-up"},
    {"max": 2.8, "move": "jump-grab"},
    {"max": math.inf, "move": "blocked"},
]
JUMP_TIERS = [  # working values: horizontal approach speed in m/s -> jump type
    {"max": 0.3, "type": "standing"},       # two-foot countermovement, vertical (or broad if aimed)
    {"max": 2.2, "type": "walking"},        # one-foot takeoff from the stance foot, small hop
    {"max": 6.0, "type": "running"},        # one-foot takeoff, stride leap, lands into the run
    {"max": math.inf, "type": "sprinting"},  # long-jump-like leap, longest flight
]
ONE_FOOT = {"walking", "running", "sprinting"}
LANDING_TIERS = [  # working values: fall height in metres
    {"max": 1.0, "landing": "none"},
    {"max": 2.5, "landing": "soft"},
    {"max": 4.0, "landing": "roll"},
    {"max": 8.0, "landing": "hard"},
    {"max": math.inf, "landing": "lethal"},
]


ROM_NEEDS = {  # degrees a dressed character must still reach, by move set (working where noted)
    "base": {"elbow_flex": 130, "shoulder_flex": 130, "shoulder_abd": 130, "hip_flex": 95,
             "knee_flex": 120},              # everyday tasks (Morrey; Oosterwijk); knee working
    "run": {"elbow_flex": 100, "hip_flex": 60, "knee_flex": 120},
    "crouch": {"knee_flex": 140, "hip_flex": 110, "ankle_dorsi": 10},   # squat (working)
    "climb": {"shoulder_flex": 160, "shoulder_abd": 150, "hip_flex": 110},  # (working)
    "kneel": {"knee_flex": 140},                                          # (working)
    "guard": {"elbow_flex": 130, "shoulder_flex": 90},                    # fists up, punches
}
NORMAL_ROM = {"elbow_flex": 145, "shoulder_flex": 169, "shoulder_abd": 180, "hip_flex": 130,
              "knee_flex": 138, "ankle_dorsi": 13, "neck_rot": 80}        # CDC men 20-44, AAOS


class NotAssessed(Exception):
    """The input cannot answer the question."""


def metric(name, value, threshold, ok, **extra):
    return {"metric": name, "value": value, "threshold": threshold,
            "verdict": "PASS" if ok else "FAIL", **extra}


def rnd(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, n)


def load_json(path):
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


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


def tiers(path, default, key):
    rows = load_json(path) if path else default
    rows = sorted(rows, key=lambda r: float(r["max"]))
    if not rows or any(key not in r for r in rows):
        raise ValueError(f"tier table needs rows with 'max' and '{key}'")
    return rows


def pick(rows, value, key):
    for r in rows:
        if value <= float(r["max"]):
            return r[key]
    return rows[-1][key]


# ---------- predictions ----------

def predict(a):
    out = {"case": a.case}
    if a.case == "jump":
        if a.v0 is None and a.height is None:
            raise ValueError("jump needs --height or --v0")
        v0 = a.v0 if a.v0 is not None else math.sqrt(2 * G * a.height)
        out.update(v0_m_s=rnd(v0, 4), apex_m=rnd(v0 * v0 / (2 * G), 4),
                   airtime_s=rnd(2 * v0 / G, 4))
    elif a.case == "runjump":
        if a.run_speed is None or a.vy is None:
            raise ValueError("runjump needs --run-speed and --vy")
        vx = a.run_speed * a.keep
        t = 2 * a.vy / G
        out.update(jump_type=pick(tiers(a.tiers, JUMP_TIERS, "type"), a.run_speed, "type"),
                   takeoff_angle_deg=rnd(math.degrees(math.atan2(a.vy, vx)), 2),
                   flight_s=rnd(t, 4), com_distance_m=rnd(vx * t, 3),
                   com_rise_m=rnd(a.vy ** 2 / (2 * G), 3), horizontal_kept=a.keep,
                   note="running jumps keep most of the approach speed and add vertical speed; "
                        "they do not stop, squat and launch")
    elif a.case == "longjump":
        if a.run_speed is None or a.angle is None:
            raise ValueError("longjump needs --run-speed and --angle")
        vx = a.run_speed * math.cos(math.radians(a.angle))
        vy = a.run_speed * math.sin(math.radians(a.angle))
        t = 2 * vy / G
        out.update(flight_s=rnd(t, 4), com_distance_m=rnd(vx * t, 3),
                   com_rise_m=rnd(vy * vy / (2 * G), 3),
                   note="centre of mass only; real jumpers add ~0.3-0.6 m with leg reach at "
                        "takeoff and landing (working)")
    elif a.case == "fall":
        if a.height is None:
            raise ValueError("fall needs --height")
        v = math.sqrt(2 * G * a.height)
        out.update(impact_speed_m_s=rnd(v, 3), energy_j=rnd(0.5 * a.mass * v * v, 1),
                   stop_distance_m=rnd(v * v / (2 * G * (a.max_bw - 1)), 3) if a.max_bw > 1
                   else None,
                   landing=pick(tiers(a.tiers, LANDING_TIERS, "landing"), a.height, "landing"))
    elif a.case == "move":
        if a.obstacle is None:
            raise ValueError("move needs --obstacle")
        out.update(move=pick(tiers(a.tiers, MOVE_TIERS, "move"), a.obstacle, "move"))
    elif a.case == "capture":
        if a.speed is None:
            raise ValueError("capture needs --speed")
        out.update(capture_point_m=rnd(a.speed * math.sqrt(a.com / G), 4),
                   note="a push that moves the capture point outside the feet forces a step")
    elif a.case == "fit":
        if not (a.radius and a.height and a.gap_w and a.gap_h):
            raise ValueError("fit needs --radius --height --gap-w --gap-h")
        width = 2 * a.radius
        res = {}
        for pose, h in (("stand", a.height), ("crouch", a.crouch), ("crawl", a.crawl)):
            if h:
                res[pose] = {"fits": width <= a.gap_w and h <= a.gap_h,
                             "margin_w_m": rnd(a.gap_w - width, 3), "margin_h_m": rnd(a.gap_h - h, 3)}
        out.update(poses=res, best=next((p for p in ("stand", "crouch", "crawl")
                                         if p in res and res[p]["fits"]), None))
    elif a.case == "load":
        if not (a.mass and a.speed is not None):
            raise ValueError("load needs --mass and --speed (and --load)")
        w, l, v = a.mass, a.load or 0.0, a.speed
        m = (1.5 * w + 2.0 * (w + l) * (l / w) ** 2
             + a.terrain * (w + l) * (1.5 * v * v + 0.35 * v * a.grade))
        out.update(metabolic_w=rnd(m, 1), per_kg_body=rnd(m / w, 3),
                   load_share_of_body=rnd(l / w, 3),
                   note="Pandolf 1977; valid ~0.7-1.6 m/s walking; underestimates at slow speeds")
    elif a.case == "float":
        # body density from Siri (fat %) plus lung and gut air; buoyancy in fresh/sea water
        if not (a.mass and a.fat is not None):
            raise ValueError("float needs --mass and --fat (percent)")
        tissue_density = 4.95 / (a.fat / 100 + 4.50)          # Siri: fat% = (4.95/D - 4.50)*100
        volume = a.mass / tissue_density + (a.lungs or 0.0) + 0.1   # L; 0.1 L gut gas
        res = {}
        for name, rho in (("fresh", 0.998), ("sea", 1.025)):
            res[name] = {"buoyancy_kg": rnd(volume * rho - a.mass, 2),
                         "above_water_l": rnd(max(0.0, volume - a.mass / rho), 2)}
        gear = (a.gear_mass or 0.0) * (1 - 1 / (a.gear_density or 7.85))
        out.update(density=rnd(a.mass / volume, 4), volume_l=rnd(volume, 2), water=res,
                   gear_weight_in_water_kg=rnd(gear, 2),
                   floats_with_gear_fresh=volume * 0.998 - a.mass - gear > 0,
                   note="buoyancy from lungs: full ~ +2-3 L, normal exhale ~ +2.4 L men, residual"
                        " ~1.2 L; one breath (0.5 L) bobs ~0.5 kg")
    elif a.case == "wade":
        if a.depth is None:
            raise ValueError("wade needs --depth (m) [--current m/s]")
        u = a.current or 0.0
        m = u * u * a.depth / G + a.depth ** 2 / 2
        v = 0.53 * m ** -0.19 if m > 0 else math.inf
        out.update(speed_m_s=rnd(min(v, a.land_speed), 3), land_speed=a.land_speed,
                   hazard=rnd((u + 0.5) * a.depth, 3),
                   note="Postacchini 2018 flood walking; use land speed below ~0.11 m")
    elif a.case == "packbounce":
        if not (a.load and a.k):
            raise ValueError("packbounce needs --load (kg) and --k (N/mm) [--zeta] [--cadence]")
        k = a.k * 1000
        wn = math.sqrt(k / a.load)
        f = wn / (2 * math.pi)
        r = (a.cadence * 2 * math.pi) / wn
        z = a.zeta
        amp = math.sqrt((1 + (2 * z * r) ** 2) / ((1 - r * r) ** 2 + (2 * z * r) ** 2))
        out.update(natural_hz=rnd(f, 3), bounce_ratio=rnd(amp, 3),
                   note="pack motion / body motion at the step frequency; tighter straps = higher k")
    elif a.case == "packlean":
        if not (a.mass and a.load and a.offset):
            raise ValueError("packlean needs --mass (body) --load (pack) --offset (m behind spine)")
        # statics: lean the upper body (~62% of body mass, CoM ~0.30 m above the hips) and the pack
        # (CoM ~0.33 m above the hips) until the pack's moment is balanced:
        # tan(lean) = load*offset / (0.62*mass*0.30 + load*0.33)
        lean = math.degrees(math.atan(a.load * a.offset / (0.62 * a.mass * 0.30 + a.load * 0.33)))
        out.update(trunk_lean_deg=rnd(lean, 2),
                   note="reproduces 6/10/13 deg for 10/20/30 kg at 0.18 m on a 75 kg man (research "
                        "statics); real carriers lean more with fatigue (working)")
    elif a.case == "lean":
        if a.v_kmh is None or not a.radius:
            raise ValueError("lean needs --v-kmh and --radius")
        v = a.v_kmh / 3.6
        out.update(lean_deg=rnd(math.degrees(math.atan(v * v / (G * a.radius))), 3),
                   lateral_g=rnd(v * v / (G * a.radius), 4))
    elif a.case == "steer":
        if a.road_deg is None or not a.ratio:
            raise ValueError("steer needs --road-deg and --ratio")
        out.update(wheel_deg=rnd(a.road_deg * a.ratio, 3))
    return {"prediction": out}


# ---------- measurements ----------

def jump(a):
    times, samples = load_recording(a.dump)
    ys = [v[1] for v in probe(samples, a.pos) if isinstance(v, list) and len(v) >= 2]
    if len(ys) < 5:
        raise NotAssessed("fewer than 5 position samples")
    apex = max(ys) - ys[0]
    err = abs(apex - a.apex) / a.apex
    return [metric("jump_apex_m", rnd(apex, 4), f"{a.apex} ± {a.tol:.0%}", err <= a.tol,
                   relative_error=rnd(err, 4))]


def moves(a):
    events = load_json(a.events).get("events") or []
    rows = tiers(a.tiers, MOVE_TIERS, "move")
    obs = [e for e in events if "height" in e and "move" in e]
    if not obs:
        raise NotAssessed("no obstacle events with height and move")
    wrong = [{"height": e["height"], "move": e["move"], "expected": pick(rows, e["height"], "move")}
             for e in obs if e["move"] != pick(rows, e["height"], "move")]
    return [metric("obstacle_move_mismatches", len(wrong), 0, not wrong, events=len(obs),
                   examples=wrong[:10])]


def jumps(a):
    events = load_json(a.events).get("events") or []
    rows = tiers(a.tiers, JUMP_TIERS, "type")
    obs = [e for e in events if "approach_speed" in e and "type" in e]
    if not obs:
        raise NotAssessed("no jump events with approach_speed and type")
    wrong_type, wrong_foot, slowed = [], [], []
    for e in obs:
        expected = pick(rows, float(e["approach_speed"]), "type")
        if e["type"] != expected:
            wrong_type.append({"approach_speed": e["approach_speed"], "type": e["type"],
                               "expected": expected})
        if e["type"] in ONE_FOOT and e.get("takeoff_foot") and e.get("stance_foot") \
                and e["takeoff_foot"] != e["stance_foot"]:
            wrong_foot.append({"type": e["type"], "takeoff_foot": e["takeoff_foot"],
                               "stance_foot": e["stance_foot"]})
        if e["type"] in ("running", "sprinting") and e.get("speed_before") and \
                e.get("speed_after") is not None and \
                e["speed_after"] < a.keep * e["speed_before"]:
            slowed.append({"type": e["type"], "speed_before": e["speed_before"],
                           "speed_after": e["speed_after"]})
    return [metric("jump_type_mismatches", len(wrong_type), 0, not wrong_type, events=len(obs),
                   examples=wrong_type[:10]),
            metric("takeoff_foot_not_stance_foot", len(wrong_foot), 0, not wrong_foot,
                   examples=wrong_foot[:10],
                   note="one-foot jumps take off from the foot on the ground at the input frame"),
            metric("run_jumps_losing_speed", len(slowed), 0, not slowed, keep=a.keep,
                   examples=slowed[:10],
                   note="running jumps keep horizontal speed; a stop-and-launch reads wrong")]


def landings(a):
    events = load_json(a.events).get("events") or []
    rows = tiers(a.tiers, LANDING_TIERS, "landing")
    obs = [e for e in events if "fall_height" in e and "landing" in e]
    if not obs:
        raise NotAssessed("no landing events with fall_height and landing")
    wrong = [{"fall_height": e["fall_height"], "landing": e["landing"],
              "expected": pick(rows, e["fall_height"], "landing")}
             for e in obs if e["landing"] != pick(rows, e["fall_height"], "landing")]
    return [metric("landing_tier_mismatches", len(wrong), 0, not wrong, events=len(obs),
                   examples=wrong[:10])]


def rom(a):
    """Joint stops measured on the dressed model (ROM sweep in Blender) against what the
    character's move set needs."""
    gear = load_json(a.gear)
    stops = gear.get("stops") or gear
    moves = ["base"] + [m.strip() for m in (a.moves or "").split(",") if m.strip()]
    unknown = [m for m in moves if m not in ROM_NEEDS]
    if unknown:
        raise ValueError(f"unknown move set(s) {unknown}; known: {', '.join(ROM_NEEDS)}")
    need = {}
    for m in moves:
        for joint, deg in ROM_NEEDS[m].items():
            if deg > need.get(joint, (0, ""))[0]:
                need[joint] = (deg, m)
    rows, short = [], []
    for joint, (deg, why) in sorted(need.items()):
        have = stops.get(joint)
        if have is None:
            rows.append({"joint": joint, "needed": deg, "for": why, "measured": None})
            short.append(joint + " (not measured)")
            continue
        row = {"joint": joint, "needed": deg, "for": why, "measured": have,
               "share_of_normal": rnd(have / NORMAL_ROM[joint], 3) if joint in NORMAL_ROM
               else None}
        rows.append(row)
        if have < deg:
            short.append(f"{joint} {have}° < {deg}° ({why})")
    return [metric("gear_rom_shortfalls", len(short), 0, not short, moves=moves, joints=rows,
                   shortfalls=short,
                   note="fix the model (relief cuts, lames, gaps, softer joint pits) before "
                        "rigging, or drop the move")]


def contact(a):
    _, samples = load_recording(a.dump)
    pa, pb = probe(samples, a.a), probe(samples, a.b)
    when = probe(samples, a.when) if a.when else [True] * len(pa)
    dists = [math.dist(x[:3], y[:3]) for x, y, w in zip(pa, pb, when)
             if w and isinstance(x, list) and isinstance(y, list)]
    if not dists:
        raise NotAssessed("no ticks with both positions while the condition holds")
    worst = max(dists)
    return [metric("contact_error_m", rnd(worst, 4), f"≤ {a.max_m}", worst <= a.max_m,
                   mean_m=rnd(sum(dists) / len(dists), 4), ticks=len(dists))]


def inside_margin(p, poly):
    """Signed distance from p to the boundary of a convex polygon (positive inside)."""
    n = len(poly)
    if n < 3:
        return -math.inf
    area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
               for i in range(n))
    sign = 1 if area > 0 else -1
    best = math.inf
    for i in range(n):
        (x1, z1), (x2, z2) = poly[i][:2], poly[(i + 1) % n][:2]
        ex, ez = x2 - x1, z2 - z1
        length = math.hypot(ex, ez) or 1e-12
        d = sign * (ex * (p[1] - z1) - ez * (p[0] - x1)) / length
        best = min(best, d)
    return best


def balance(a):
    _, samples = load_recording(a.dump)
    com, sup = probe(samples, a.com), probe(samples, a.support)
    stepping = samples.get("stepping") or [False] * len(com)
    margins, outside = [], 0
    for c, s, st in zip(com, sup, stepping):
        if st or not isinstance(c, list) or not isinstance(s, list) or len(s) < 3:
            continue
        p = [c[0], c[2]] if len(c) >= 3 else c[:2]
        m = inside_margin(p, s)
        margins.append(m)
        outside += m < a.margin
    if not margins:
        raise NotAssessed("no ticks with a centre of mass and a support polygon")
    return [metric("com_outside_support_ticks", outside, 0, outside == 0,
                   min_margin_m=rnd(min(margins), 4), ticks=len(margins))]


def penetration(a):
    _, samples = load_recording(a.dump)
    vals = [v for v in probe(samples, a.depth) if isinstance(v, (int, float))]
    if not vals:
        raise NotAssessed("no depth samples")
    worst = max(vals)
    return [metric("penetration_m", rnd(worst, 4), f"≤ {a.max_m}", worst <= a.max_m,
                   ticks_over=sum(v > a.max_m for v in vals))]


# ---------- cli ----------

def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("predict")
    pr.add_argument("case", choices=["jump", "runjump", "longjump", "fall", "move", "capture", "fit", "load",
                                     "float", "wade", "packbounce", "packlean",
                                     "lean", "steer"])
    for name in ("fat", "lungs", "gear-mass", "gear-density", "depth", "current", "k", "offset",
                 "height", "v0", "vy", "run-speed", "angle", "obstacle", "speed", "radius", "gap-w",
                 "gap-h", "crouch", "crawl", "load", "v-kmh", "road-deg", "ratio"):
        pr.add_argument(f"--{name}", type=float)
    pr.add_argument("--com", type=float, default=1.0)
    pr.add_argument("--mass", type=float, default=80.0)
    pr.add_argument("--max-bw", type=float, default=6.0)
    pr.add_argument("--grade", type=float, default=0.0)
    pr.add_argument("--terrain", type=float, default=1.0)
    pr.add_argument("--tiers")
    pr.add_argument("--keep", type=float, default=0.9)
    pr.add_argument("--land-speed", type=float, default=1.4)
    pr.add_argument("--zeta", type=float, default=0.1)
    pr.add_argument("--cadence", type=float, default=2.8, help="steps per second")

    j = sub.add_parser("jump")
    j.add_argument("dump")
    j.add_argument("--pos", required=True)
    j.add_argument("--apex", type=float, required=True)
    j.add_argument("--tol", type=float, default=0.05)

    for name in ("moves", "landings", "jumps"):
        s = sub.add_parser(name)
        s.add_argument("events")
        s.add_argument("--tiers")
        s.add_argument("--keep", type=float, default=0.85)

    r = sub.add_parser("rom")
    r.add_argument("gear")
    r.add_argument("--moves", help="comma list: run, crouch, climb, kneel, guard")

    c = sub.add_parser("contact")
    c.add_argument("dump")
    c.add_argument("--a", required=True)
    c.add_argument("--b", required=True)
    c.add_argument("--when")
    c.add_argument("--max-m", type=float, default=0.02)

    b = sub.add_parser("balance")
    b.add_argument("dump")
    b.add_argument("--com", required=True)
    b.add_argument("--support", required=True)
    b.add_argument("--margin", type=float, default=0.0)

    pe = sub.add_parser("penetration")
    pe.add_argument("dump")
    pe.add_argument("--depth", required=True)
    pe.add_argument("--max-m", type=float, default=0.02)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "predict":
            print(json.dumps(predict(a), ensure_ascii=False))
            return 0
        metrics = {"jump": jump, "moves": moves, "landings": landings, "jumps": jumps, "rom": rom,
                   "contact": contact,
                   "balance": balance, "penetration": penetration}[a.cmd](a)
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
