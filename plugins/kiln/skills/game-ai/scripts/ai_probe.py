"""Enemy AI fairness and movement metrics over probe recordings (Python 3.12+, stdlib only).

  python ai_probe.py <dump> [--agents grunt1,grunt2] [--tokens 2 | --tokens melee=1,ranged=2]
         [--min-reaction-ms 250] [--reacquire-s 1.0] [--stuck-s 3 --stuck-m 0.5]
         [--dither-s 0.3] [--unit-scale 0.01] [--hz 60]

Probes per agent, named "<agent>.<field>" (agents are auto-detected from the names):
  pos        world position (stuck check)
  los        bool: a world-only ray from the agent's eyes to the player's chest is clear
  fired      bool or number of shots fired on this tick
  attacking  bool, or attack type string ("" / null when not attacking): holds a token
  moving     bool: the agent wants to move along a path on this tick
  state      state name (dithering check)

Metrics: shots without line of sight (must be 0); reaction from a new sighting to the first
shot (minimum over sightings, >= --min-reaction-ms); most concurrent attackers per type vs
--tokens; stuck episodes (moving for --stuck-s with less than --stuck-m progress, must be 0);
A -> B -> A state flips where B lasted less than --dither-s (must be 0).

<dump> is the acceptance recorder JSON ({"physics_ticks_per_second", "samples": {...}}) or JSON
Lines with one object per tick (Unity/Unreal probes; optional "dt"). Prints one JSON object
{"verdict", "metrics": [...]}; verdict FAIL if any metric fails, NOT ASSESSED if nothing could be
measured; exit code 1 on FAIL.
"""

import argparse
import json
import math
import re
import sys

FIELDS = ("pos", "los", "fired", "attacking", "moving", "state")
NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def load(path, hz=None):
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


def vec(v, scale=1.0):
    if v is None:
        return None
    if isinstance(v, dict):
        v = [v.get("x", 0.0), v.get("y", 0.0), v.get("z", 0.0)]
    elif isinstance(v, str):
        v = [float(x) for x in NUM.findall(v)]
    out = [float(x) * scale for x in v]
    while len(out) < 3:
        out.append(0.0)
    return out


def flag(v):
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "on")
    return bool(v)


def shots(v):
    if isinstance(v, bool) or v is None:
        return int(bool(v))
    if isinstance(v, (int, float)):
        return int(v)
    return int(flag(v))


def attack_type(v):
    """None when not attacking; '*' for a plain bool; the type string otherwise."""
    if v is None or v is False or v == "" or v == 0:
        return None
    if isinstance(v, str):
        low = v.strip().lower()
        if low in ("false", "0", "no", "none", "off", ""):
            return None
        return "*" if low in ("true", "1", "yes", "on") else v.strip()
    return "*"


def metric(name, value, threshold, ok, **extra):
    verdict = "INFO" if ok is None else ("PASS" if ok else "FAIL")
    if isinstance(value, float):
        value = round(value, 3)
    return {"metric": name, "value": value, "threshold": threshold, "verdict": verdict, **extra}


def finish(metrics, **extra):
    verdicts = [m["verdict"] for m in metrics]
    overall = "FAIL" if "FAIL" in verdicts else ("PASS" if "PASS" in verdicts else "NOT ASSESSED")
    print(json.dumps({"verdict": overall, **extra, "metrics": metrics}, ensure_ascii=False))
    return 1 if overall == "FAIL" else 0


def parse_tokens(text):
    if text is None:
        return None
    if "=" not in text:
        return {"*": int(text)}
    out = {}
    for part in text.split(","):
        key, _, val = part.partition("=")
        out[key.strip()] = int(val)
    return out


def detect_agents(samples):
    agents = []
    for key in samples:
        base, dot_, field = key.rpartition(".")
        if dot_ and field in FIELDS and base not in agents:
            agents.append(base)
    return agents


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dump")
    ap.add_argument("--agents", help="comma-separated agent prefixes (default: auto-detect)")
    ap.add_argument("--tokens", help="N for all attacks, or type=N,type=N")
    ap.add_argument("--min-reaction-ms", type=float, default=250.0)
    ap.add_argument("--reacquire-s", type=float, default=1.0,
                    help="LOS must have been lost this long for a sighting to count as new")
    ap.add_argument("--stuck-s", type=float, default=3.0)
    ap.add_argument("--stuck-m", type=float, default=0.5)
    ap.add_argument("--dither-s", type=float, default=0.3)
    ap.add_argument("--unit-scale", type=float, default=1.0, help="0.01 for Unreal centimetres")
    ap.add_argument("--hz", type=float)
    a = ap.parse_args(argv)

    samples, hz = load(a.dump, a.hz)
    agents = a.agents.split(",") if a.agents else detect_agents(samples)
    if not agents:
        print(json.dumps({"verdict": "NOT ASSESSED", "error": "no '<agent>.<field>' probes",
                          "probes": sorted(samples)}))
        return 2

    def field(agent, name):
        return samples.get(f"{agent}.{name}")

    metrics = []

    # shots without line of sight
    bad, total, seen = [], 0, False
    for ag in agents:
        los, fired = field(ag, "los"), field(ag, "fired")
        if los is None or fired is None:
            continue
        seen = True
        for i in range(min(len(los), len(fired))):
            k = shots(fired[i])
            total += k
            if k and not flag(los[i]):
                bad.append({"agent": ag, "tick": i, "shots": k})
    if seen:
        metrics.append(metric("shots_without_los", sum(b["shots"] for b in bad), 0, not bad,
                              shots_total=total, first=bad[:5]))

    # reaction from a new sighting to the first shot
    delays = []
    reacquire = int(round(a.reacquire_s * hz))
    for ag in agents:
        los, fired = field(ag, "los"), field(ag, "fired")
        if los is None or fired is None:
            continue
        n = min(len(los), len(fired))
        vis = [flag(los[i]) for i in range(n)]
        last_seen = None
        onsets = []
        for i in range(n):
            if vis[i]:
                if i > 0 and not vis[i - 1] and (last_seen is None or i - last_seen > reacquire):
                    onsets.append(i)
                last_seen = i
        for k, start in enumerate(onsets):
            end = onsets[k + 1] if k + 1 < len(onsets) else n
            first = next((j for j in range(start, end) if shots(fired[j])), None)
            if first is not None:
                delays.append({"agent": ag, "tick": start, "ms": round(1000.0 * (first - start) / hz, 1)})
    if delays:
        worst = min(delays, key=lambda d: d["ms"])
        metrics.append(metric("reaction_min_ms", worst["ms"], a.min_reaction_ms,
                              worst["ms"] >= a.min_reaction_ms, agent=worst["agent"],
                              sighting_tick=worst["tick"], sightings_with_shots=len(delays)))

    # concurrent attackers vs tokens
    limits = parse_tokens(a.tokens)
    series = [(ag, field(ag, "attacking")) for ag in agents if field(ag, "attacking") is not None]
    if series:
        n = min(len(s) for _, s in series)
        peak, over = {}, []
        for i in range(n):
            count = {}
            for _, s in series:
                t = attack_type(s[i])
                if t is not None:
                    count[t] = count.get(t, 0) + 1
            if limits and "*" in limits:
                count = {"*": sum(count.values())} if count else {}
            for t, c in count.items():
                peak[t] = max(peak.get(t, 0), c)
                if limits and t in limits and c > limits[t]:
                    over.append({"tick": i, "type": t, "attackers": c})
        if limits:
            metrics.append(metric("max_concurrent_attackers", peak, limits, not over,
                                  first_over=over[:5]))
        else:
            metrics.append(metric("max_concurrent_attackers", peak, None, None,
                                  note="pass --tokens to grade"))

    # stuck episodes
    window = max(1, int(round(a.stuck_s * hz)))
    episodes = []
    graded_stuck = False
    for ag in agents:
        pos, moving = field(ag, "pos"), field(ag, "moving")
        if pos is None or moving is None:
            continue
        graded_stuck = True
        p = [vec(v, a.unit_scale) for v in pos]
        mv = [flag(v) for v in moving]
        n = min(len(p), len(mv))
        run_start = None
        stuck_prev = False
        for i in range(window, n):
            stuck = all(mv[i - window:i + 1]) and math.dist(p[i - window], p[i]) < a.stuck_m
            if stuck and not stuck_prev:
                run_start = i - window
                episodes.append({"agent": ag, "from_tick": run_start})
            stuck_prev = stuck
    if graded_stuck:
        metrics.append(metric("stuck_episodes", len(episodes), 0, not episodes, first=episodes[:5],
                              window_s=a.stuck_s, min_progress_m=a.stuck_m))

    # dithering: A -> B -> A with B shorter than dither_s
    flips = []
    graded_states = False
    short = a.dither_s * hz
    for ag in agents:
        st = field(ag, "state")
        if st is None:
            continue
        graded_states = True
        segs = []
        for i, s in enumerate(st):
            s = "" if s is None else str(s)
            if segs and segs[-1][0] == s:
                segs[-1][2] += 1
            else:
                segs.append([s, i, 1])
        for k in range(1, len(segs) - 1):
            if segs[k][2] < short and segs[k - 1][0] == segs[k + 1][0]:
                flips.append({"agent": ag, "tick": segs[k][1],
                              "flip": f"{segs[k - 1][0]}>{segs[k][0]}>{segs[k + 1][0]}"})
    if graded_states:
        metrics.append(metric("state_flips", len(flips), 0, not flips, first=flips[:5],
                              shorter_than_s=a.dither_s))

    return finish(metrics, agents=agents)


if __name__ == "__main__":
    sys.exit(main())
