"""Camera and stick acceptance metrics over probe recordings (Python 3.12+, stdlib only).

  python camera_probe.py camera <dump> --cam-pos P --cam-fwd F --target T [--occluded O]
         [--inside I] [--fov V [--fov-range MIN MAX]] [--look L] [--cut C] [--zoom Z]
         [--lock-on] [--unit-scale S] [--hz HZ] [threshold flags]
      camera-in-geometry ticks, target occlusion ratio and longest run, target in view,
      automatic angular speed and acceleration, pops, FOV range and rate, look input latency.
  python camera_probe.py stick <dump> --input STICK --response R [--inner 0.15]
      no output inside the dead zone, continuity at its edge, diagonal vs cardinal maximum,
      monotonic response.

<dump> is the acceptance recorder JSON ({"physics_ticks_per_second", "samples": {name: [...]}})
or JSON Lines with one object per tick (Unity/Unreal probes; optional "dt" per row). Vectors are
[x, y, z] lists, {"x", "y", "z"} objects or "(x, y, z)" strings. P, F, T, ... are probe names.
Prints one JSON object {"verdict", "metrics": [{metric, value, threshold, verdict, ...}]};
verdict FAIL if any metric fails, NOT ASSESSED if nothing could be measured; exit code 1 on FAIL.
Defaults are the (working) thresholds of the controls-camera skill; override them with flags.
"""

import argparse
import json
import math
import re
import sys

NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


# ---------------------------------------------------------------- loading

def load(path, hz=None):
    """Return (samples dict name -> list, ticks per second)."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("samples"), dict):
        return data["samples"], float(hz or data.get("physics_ticks_per_second") or 60)
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = [data]
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    keys = []
    for row in rows:
        keys.extend(k for k in row if k not in keys)
    samples = {k: [row.get(k) for row in rows] for k in keys}
    if hz is None and "dt" in samples:
        dts = sorted(float(x) for x in samples["dt"] if isinstance(x, (int, float)) and x > 0)
        if dts:
            hz = 1.0 / dts[len(dts) // 2]
    return samples, float(hz or 60)


def series(samples, name):
    if name not in samples:
        print(json.dumps({"verdict": "NOT ASSESSED", "error": f"probe '{name}' not in dump",
                          "probes": sorted(samples)}))
        sys.exit(2)
    return samples[name]


def vec(v, scale=1.0):
    if v is None:
        return None
    if isinstance(v, dict):
        v = [v.get("x", 0.0), v.get("y", 0.0), v.get("z", 0.0)]
    elif isinstance(v, str):
        v = [float(x) for x in NUM.findall(v)]
    elif isinstance(v, (int, float)):
        v = [v]
    out = [float(x) * scale for x in v]
    while len(out) < 3:
        out.append(0.0)
    return out


def flag(v):
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "on")
    return bool(v)


def num(v):
    if isinstance(v, (list, tuple, dict, str)):
        return norm(vec(v))
    return float(v or 0.0)


def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return [x / n for x in a] if n > 1e-12 else [0.0, 0.0, 0.0]


def angle_deg(a, b):
    na, nb = norm(a), norm(b)
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    # atan2 form is accurate for tiny angles, unlike acos
    return math.degrees(math.atan2(norm(cross(a, b)), dot(a, b)))


def metric(name, value, threshold, ok, **extra):
    verdict = "INFO" if ok is None else ("PASS" if ok else "FAIL")
    if isinstance(value, float):
        value = round(value, 4)
    return {"metric": name, "value": value, "threshold": threshold, "verdict": verdict, **extra}


def runs(flags):
    """Lengths of consecutive True runs."""
    out, cur = [], 0
    for f in flags:
        if f:
            cur += 1
        elif cur:
            out.append(cur)
            cur = 0
    if cur:
        out.append(cur)
    return out


def finish(metrics):
    verdicts = [m["verdict"] for m in metrics]
    if "FAIL" in verdicts:
        overall = "FAIL"
    elif "PASS" in verdicts:
        overall = "PASS"
    else:
        overall = "NOT ASSESSED"
    print(json.dumps({"verdict": overall, "metrics": metrics}, ensure_ascii=False))
    return 1 if overall == "FAIL" else 0


# ---------------------------------------------------------------- camera

def camera(a):
    samples, hz = load(a.dump, a.hz)
    pos = [vec(v, a.unit_scale) for v in series(samples, a.cam_pos)]
    fwd = [unit(vec(v)) for v in series(samples, a.cam_fwd)]
    tgt = [vec(v, a.unit_scale) for v in series(samples, a.target)]
    n = min(len(pos), len(fwd), len(tgt))
    cut = [flag(v) for v in series(samples, a.cut)][:n] if a.cut else [False] * n
    zoom = [flag(v) for v in series(samples, a.zoom)][:n] if a.zoom else [False] * n
    metrics = []
    if n < 2:
        return finish([metric("ticks", n, ">= 2", False, note="too few samples")])

    if a.inside:
        inside = [flag(v) for v in series(samples, a.inside)][:n]
        bad = [i for i, f in enumerate(inside) if f]
        metrics.append(metric("camera_inside_geometry_ticks", len(bad), 0, not bad,
                              first_ticks=bad[:5]))

    if a.occluded:
        occ = [flag(v) for v in series(samples, a.occluded)][:n]
        ratio = sum(occ) / n
        longest = max(runs(occ), default=0) / hz
        metrics.append(metric("target_occluded_ratio", ratio, a.max_occluded,
                              ratio <= a.max_occluded))
        metrics.append(metric("target_occluded_longest_s", longest, a.max_occluded_run,
                              longest <= a.max_occluded_run))

    fov = [num(v) for v in series(samples, a.fov)][:n] if a.fov else None
    off_axis = [angle_deg(fwd[i], sub(tgt[i], pos[i])) for i in range(n)]
    halves = [f / 2.0 for f in fov] if fov else [a.view_half_angle] * n
    in_view = sum(1 for i in range(n) if off_axis[i] <= halves[i]) / n
    metrics.append(metric("target_in_view_ratio", in_view, 1.0 if a.lock_on else None,
                          (in_view >= 1.0) if a.lock_on else None,
                          max_off_axis_deg=round(max(off_axis), 2),
                          note="cone of half the vertical FOV (conservative)"))

    # per-tick rotation (tick i = change from i-1 to i)
    turn = [0.0] + [angle_deg(fwd[i - 1], fwd[i]) for i in range(1, n)]
    omega = [[0.0, 0.0, 0.0]]
    for i in range(1, n):
        axis = unit(cross(fwd[i - 1], fwd[i]))
        omega.append([c * turn[i] * hz for c in axis])

    if a.look:
        look = [num(v) for v in series(samples, a.look)][:n]
        active = [abs(x) > a.look_deadzone for x in look]
        grace = int(round(a.input_grace * hz))
        auto, last = [], -10 ** 9
        for i in range(n):
            if active[i]:
                last = i
            auto.append(not active[i] and i - last > grace)
    else:
        look, active = None, [False] * n
        auto = [True] * n
    graded = a.look is not None

    speeds = [turn[i] * hz for i in range(1, n) if auto[i] and not cut[i]]
    accels = [norm(sub(omega[i], omega[i - 1])) * hz for i in range(2, n)
              if auto[i] and auto[i - 1] and not (cut[i] or cut[i - 1])]
    note = None if graded else "no --look probe: all rotation treated as automatic, not graded"
    if speeds:
        top = max(speeds)
        metrics.append(metric("auto_angular_speed_max_deg_s", top, a.max_auto_deg_s,
                              (top <= a.max_auto_deg_s) if graded else None, note=note))
    if accels:
        top = max(accels)
        metrics.append(metric("auto_angular_accel_max_deg_s2", top, a.max_auto_deg_s2,
                              (top <= a.max_auto_deg_s2) if graded else None, note=note))

    pops = []
    for i in range(1, n):
        if cut[i]:
            continue
        if auto[i] and turn[i] > a.pop_deg:
            pops.append({"tick": i, "turn_deg": round(turn[i], 2)})
            continue
        d = sub(pos[i], pos[i - 1])
        to_t = unit(sub(tgt[i - 1], pos[i - 1]))
        along = dot(d, to_t)                      # > 0: toward the target (pull-in)
        lateral = norm(sub(d, [c * along for c in to_t]))
        if lateral > a.pop_m or -along > a.pop_m:
            pops.append({"tick": i, "lateral_m": round(lateral, 3), "outward_m": round(-along, 3)})
    metrics.append(metric("camera_pops", len(pops), 0, not pops, first=pops[:5]))

    if fov:
        lo, hi = min(fov), max(fov)
        if a.fov_range:
            ok = a.fov_range[0] - 1e-6 <= lo and hi <= a.fov_range[1] + 1e-6
            metrics.append(metric("fov_range_deg", [round(lo, 2), round(hi, 2)], a.fov_range, ok))
        else:
            metrics.append(metric("fov_range_deg", [round(lo, 2), round(hi, 2)], None, None))
        rates = [abs(fov[i] - fov[i - 1]) * hz for i in range(1, n) if not (zoom[i] or cut[i])]
        top = max(rates, default=0.0)
        metrics.append(metric("fov_rate_max_deg_s", top, a.max_fov_rate, top <= a.max_fov_rate))

    if look is not None:
        idle = int(round(a.input_grace * hz))
        onsets = [i for i in range(n) if active[i] and not any(active[max(0, i - idle):i])]
        lat = []
        for k in onsets:
            hit = next((j for j in range(k, min(n, k + a.search_ticks)) if turn[j] > a.min_turn_deg),
                       None)
            lat.append(None if hit is None else hit - k)
        if onsets:
            worst = None if None in lat else max(lat)
            ok = worst is not None and worst <= a.max_latency_ticks
            metrics.append(metric("look_latency_ticks", worst, a.max_latency_ticks, ok,
                                  ms=None if worst is None else round(1000.0 * worst / hz, 1),
                                  onsets=len(onsets)))
    return finish(metrics)


# ---------------------------------------------------------------- stick

def stick(a):
    samples, _ = load(a.dump, None)
    raw = [vec(v) for v in series(samples, a.input)]
    resp = [num(v) for v in series(samples, a.response)]
    n = min(len(raw), len(resp))
    inp = [(raw[i][0], raw[i][1]) for i in range(n)]
    mag = [math.hypot(x, y) for x, y in inp]
    r = [abs(x) for x in resp[:n]]
    rmax = max(r, default=0.0)
    metrics = []
    if n == 0 or rmax <= 0:
        return finish([metric("response_max", rmax, "> 0", False, note="no response recorded")])

    inner = [r[i] for i in range(n) if mag[i] < a.inner - 0.01]
    if inner:
        leak = max(inner) / rmax
        metrics.append(metric("dead_zone_leak_ratio", leak, a.leak, leak <= a.leak,
                              samples=len(inner)))

    edge = [r[i] for i in range(n) if a.inner + 0.005 < mag[i] <= a.inner + a.edge_band]
    if edge:
        jump = max(edge) / rmax
        metrics.append(metric("edge_output_ratio", jump, a.max_edge, jump <= a.max_edge,
                              band=[a.inner, round(a.inner + a.edge_band, 3)]))
    else:
        metrics.append(metric("edge_output_ratio", None, a.max_edge, None,
                              note="no samples just outside the dead zone"))

    card, diag = [], []
    for i in range(n):
        if mag[i] < a.full:
            continue
        ang = math.degrees(math.atan2(inp[i][1], inp[i][0])) % 90.0
        if min(ang, 90.0 - ang) <= 10.0:
            card.append(r[i])
        elif abs(ang - 45.0) <= 10.0:
            diag.append(r[i])
    if card and diag:
        ratio = max(diag) / max(card)
        metrics.append(metric("diagonal_vs_cardinal_ratio", ratio, [1 - a.radial_tol, 1 + a.radial_tol],
                              abs(ratio - 1.0) <= a.radial_tol))
    else:
        metrics.append(metric("diagonal_vs_cardinal_ratio", None, None, None,
                              note="need full deflection samples on axes and diagonals"))

    bins = {}
    for i in range(n):
        if a.inner <= mag[i] <= 1.0:
            b = min(int((mag[i] - a.inner) / ((1.0 - a.inner) / 8.0)), 7)
            bins.setdefault(b, []).append(r[i])
    means = [sum(bins[b]) / len(bins[b]) for b in sorted(bins)]
    if len(means) >= 3:
        drops = [i for i in range(1, len(means)) if means[i] < means[i - 1] - 0.02 * rmax]
        metrics.append(metric("monotonic_bins", len(means) - len(drops), len(means), not drops))
    return finish(metrics)


# ---------------------------------------------------------------- cli

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub_ = ap.add_subparsers(dest="cmd", required=True)

    c = sub_.add_parser("camera", help="camera metrics")
    c.add_argument("dump")
    c.add_argument("--cam-pos", required=True)
    c.add_argument("--cam-fwd", required=True)
    c.add_argument("--target", required=True)
    c.add_argument("--occluded")
    c.add_argument("--inside")
    c.add_argument("--fov", help="FOV probe in degrees (vertical)")
    c.add_argument("--fov-range", type=float, nargs=2, metavar=("MIN", "MAX"))
    c.add_argument("--look", help="look input magnitude probe (stick length or mouse delta)")
    c.add_argument("--cut", help="bool probe: deliberate cut/teleport on this tick")
    c.add_argument("--zoom", help="bool probe: ADS/zoom FOV change on this tick")
    c.add_argument("--lock-on", action="store_true", help="target must stay in view")
    c.add_argument("--unit-scale", type=float, default=1.0, help="0.01 for Unreal centimetres")
    c.add_argument("--hz", type=float)
    c.add_argument("--view-half-angle", type=float, default=30.0)
    c.add_argument("--max-occluded", type=float, default=0.05)
    c.add_argument("--max-occluded-run", type=float, default=0.5)
    c.add_argument("--max-auto-deg-s", type=float, default=180.0)
    c.add_argument("--max-auto-deg-s2", type=float, default=720.0)
    c.add_argument("--pop-deg", type=float, default=30.0)
    c.add_argument("--pop-m", type=float, default=1.0)
    c.add_argument("--max-fov-rate", type=float, default=60.0)
    c.add_argument("--look-deadzone", type=float, default=0.05)
    c.add_argument("--input-grace", type=float, default=0.25,
                   help="seconds after look input still counted as player-driven")
    c.add_argument("--max-latency-ticks", type=int, default=1)
    c.add_argument("--min-turn-deg", type=float, default=0.01)
    c.add_argument("--search-ticks", type=int, default=30)

    s = sub_.add_parser("stick", help="dead zone and response-curve checks")
    s.add_argument("dump")
    s.add_argument("--input", required=True, help="raw stick vector probe")
    s.add_argument("--response", required=True, help="output probe (scalar or vector)")
    s.add_argument("--inner", type=float, default=0.15)
    s.add_argument("--leak", type=float, default=0.01)
    s.add_argument("--edge-band", type=float, default=0.05)
    s.add_argument("--max-edge", type=float, default=0.10)
    s.add_argument("--full", type=float, default=0.95)
    s.add_argument("--radial-tol", type=float, default=0.05)

    args = ap.parse_args(argv)
    return {"camera": camera, "stick": stick}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
