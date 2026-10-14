"""Checks for hands — grips, finger poses, two-handed holds, wrists (Python 3.12+, stdlib only).

Prediction (design time):
  python hands_check.py predict handle --hand-length 191
  python hands_check.py predict grip   --object rifle

  handle: comfortable power-grip handle diameter = 19.7 % of hand length (Kong & Lowe; 30-40 mm
  range), with the 5th-95th percentile hands. grip: the grip type and notes for a common object
  from the skill's table.

Measurement (recordings from the running game):
  python hands_check.py rom   <dump> --joints index_mcp=mcp,index_pip=pip,... [--crimp]
  python hands_check.py drift <dump> --hand hand_l --grip grip_l [--when held] [--max-mm 5]
  python hands_check.py wrist <dump> --radial wrist_rad --ulnar wrist_uln [--support]

  rom: each probe (flexion in degrees, negative = extension) within the joint type's active range:
  mcp -45..90, pip 0..115, dip -20..90 (to -28 with --crimp), thumb_cmc 0..50, thumb_mcp 0..55,
  thumb_ip -5..90. drift: the support hand stays on its grip socket (distance <= --max-mm while
  --when is true) — two-handed weapons, wheels, bars. wrist: radial deviation <= 15 deg, ulnar
  <= 45 deg (support hand on a rifle: <= 58 deg with --support, measured shooters).

Recordings: the acceptance recorder JSON or JSON Lines.
Prints one JSON object {"verdict", "metrics": [...]} (predict: {"prediction": {...}}); exit code 1
on FAIL, 2 on bad input.
"""

import argparse
import json
import math
import sys

ROM = {"mcp": (-45, 90), "pip": (0, 115), "dip": (-20, 90), "thumb_cmc": (0, 50),
       "thumb_mcp": (0, 55), "thumb_ip": (-5, 90)}
GRIPS = {
    "pistol": "strong hand high on the grip; support heel fills the gap, support thumb forward along "
              "the slide, fingers over the strong fingers; trigger finger straight on the frame "
              "when not firing",
    "rifle": "strong hand power grip on the pistol grip; support hand on the handguard or foregrip "
             "(IK target on the weapon); trigger wrist ~21 deg ulnar, support ~47 deg",
    "sword": "one hand: hammer grip; two hands: lead hand under the guard, rear hand at the pommel, "
             "last three fingers grip, index and thumb relaxed",
    "knife": "hammer, saber (thumb on top) or reverse (icepick) grip",
    "axe": "cylindrical power grip sized by handle diameter",
    "shield": "forearm through the enarmes strap, hand on the grip strap; guige sling to carry",
    "lantern": "hook grasp, fingers lightly flexed, arm hanging",
    "bucket": "hook grasp, arm hanging, trunk leans away (traversal: one-hand load)",
    "ledge": "crimp (PIP ~87 deg, DIP hyperextended), half-crimp (PIP ~70) or open hand (PIP ~39)",
    "ladder": "power grip on rungs, three points of contact",
    "rope": "both hands overhand, power grip, foot lock",
    "wheel": "hands at 9 and 3, wrists straight, push-pull",
    "motorbike": "all four fingers on the throttle, thumb under, wrist straight; 1-2 fingers may "
                 "cover the brake",
    "door": "lever or pull handle (no tight grasp or wrist twist needed for levers)",
    "small": "tip pinch, palmar pinch, tripod or lateral pinch by size",
}


class NotAssessed(Exception):
    """The input cannot answer the question."""


def metric(name, value, threshold, ok, **extra):
    return {"metric": name, "value": value, "threshold": threshold,
            "verdict": "PASS" if ok else "FAIL", **extra}


def load_recording(path):
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("samples"), dict):
        return data["samples"]
    rows = data if isinstance(data, list) else [json.loads(x) for x in text.splitlines()
                                                 if x.strip()]
    rows = [r for r in rows if r.get("type", "tick") in ("tick", "sample")]
    keys = []
    for row in rows:
        keys.extend(k for k in row if k not in keys and k not in ("type", "t", "tick"))
    return {k: [row.get(k) for row in rows] for k in keys}


def probe(samples, name):
    if name not in samples:
        raise NotAssessed(f"probe '{name}' not in recording; probes: " + ", ".join(sorted(samples)))
    return samples[name]


def predict(a):
    out = {"case": a.case}
    if a.case == "handle":
        if not a.hand_length:
            raise ValueError("handle needs --hand-length (mm)")
        out.update(diameter_mm=round(0.197 * a.hand_length, 1),
                   women_5th_mm=round(0.197 * 160, 1), men_95th_mm=round(0.197 * 205, 1),
                   note="comfort peak 30-40 mm; finger force falls as the diameter grows")
    elif a.case == "grip":
        key = (a.object or "").lower()
        if key not in GRIPS:
            raise ValueError(f"unknown object '{a.object}'; known: {', '.join(GRIPS)}")
        out.update(object=key, grip=GRIPS[key])
    return {"prediction": out}


def rom(a):
    samples = load_recording(a.dump)
    bad = []
    for pair in a.joints.split(","):
        name, _, kind = pair.partition("=")
        kind = kind.strip()
        if kind not in ROM:
            raise ValueError(f"joint type '{kind}' unknown; known: {', '.join(ROM)}")
        lo, hi = ROM[kind]
        if kind == "dip" and a.crimp:
            lo = -28
        vals = [v for v in probe(samples, name.strip()) if isinstance(v, (int, float))]
        if not vals:
            raise NotAssessed(f"no samples for '{name}'")
        if min(vals) < lo or max(vals) > hi:
            bad.append({"joint": name.strip(), "type": kind, "min": round(min(vals), 2),
                        "max": round(max(vals), 2), "range": [lo, hi]})
    return [metric("finger_rom_violations", len(bad), 0, not bad, violations=bad)]


def drift(a):
    samples = load_recording(a.dump)
    hand, grip = probe(samples, a.hand), probe(samples, a.grip)
    when = samples.get(a.when) if a.when else [True] * len(hand)
    d = [math.dist(h[:3], g[:3]) * 1000 for h, g, w in zip(hand, grip, when)
         if w and isinstance(h, list) and isinstance(g, list)]
    if not d:
        raise NotAssessed("no ticks with both positions while held")
    return [metric("support_hand_drift_mm", round(max(d), 2), f"≤ {a.max_mm}", max(d) <= a.max_mm,
                   mean_mm=round(sum(d) / len(d), 2))]


def wrist(a):
    samples = load_recording(a.dump)
    rad = [v for v in probe(samples, a.radial) if isinstance(v, (int, float))]
    uln = [v for v in probe(samples, a.ulnar) if isinstance(v, (int, float))]
    if not rad or not uln:
        raise NotAssessed("no wrist samples")
    ulnar_max = 58 if a.support else 45
    ok = max(rad) <= 15 and max(uln) <= ulnar_max
    return [metric("wrist_deviation_deg", {"radial": round(max(rad), 2), "ulnar": round(max(uln), 2)},
                   f"radial ≤ 15, ulnar ≤ {ulnar_max}", ok)]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("predict")
    pr.add_argument("case", choices=["handle", "grip"])
    pr.add_argument("--hand-length", type=float)
    pr.add_argument("--object")
    r = sub.add_parser("rom")
    r.add_argument("dump")
    r.add_argument("--joints", required=True)
    r.add_argument("--crimp", action="store_true")
    d = sub.add_parser("drift")
    d.add_argument("dump")
    d.add_argument("--hand", required=True)
    d.add_argument("--grip", required=True)
    d.add_argument("--when")
    d.add_argument("--max-mm", type=float, default=5.0)
    w = sub.add_parser("wrist")
    w.add_argument("dump")
    w.add_argument("--radial", required=True)
    w.add_argument("--ulnar", required=True)
    w.add_argument("--support", action="store_true")
    a = p.parse_args(argv)
    try:
        if a.cmd == "predict":
            print(json.dumps(predict(a), ensure_ascii=False))
            return 0
        metrics = {"rom": rom, "drift": drift, "wrist": wrist}[a.cmd](a)
    except NotAssessed as exc:
        print(json.dumps({"verdict": "NOT ASSESSED", "reason": str(exc), "metrics": []}))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"verdict": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    verdict = "FAIL" if any(m["verdict"] == "FAIL" for m in metrics) else "PASS"
    print(json.dumps({"verdict": verdict, "metrics": metrics}, ensure_ascii=False))
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
