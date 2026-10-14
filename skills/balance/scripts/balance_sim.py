"""Balance simulations over tuning tables (numpy). Every result carries a verdict; exit 1 on fail.

  python balance_sim.py ttk --weapons data/balance/weapons.json --enemies data/balance/enemies.json
                            [--ranges 10 25 50] [--trials 20000] [--seed 1]
  python balance_sim.py economy design/balance/economy.json [--players 2000] [--seed 1]
                            [--csv production/balance/economy.csv]
  python balance_sim.py drops --p 0.006 --hard-pity 90 --soft-start 74 --soft-step 0.06
  python balance_sim.py drops --p 0.25 --prd [--max-p90 8]
  python balance_sim.py curve design/balance/xp_curve.json

ttk — weapons {"weapons": [{name, damage, rpm | rate (shots/s), pellets=1, magazine, reload_s,
  multipliers {zone: x}, falloff [[m, factor], ...], accuracy}]}; accuracy = hit chance (number,
  all "body"), {zone: chance} (rest misses) or [[from_m, {zone: chance}], ...] by range.
  Enemies {"enemies": [{name, hp, armor_flat=0, armor_pct=0, min_damage_frac=0, zones {zone: x},
  ttk_target [lo, hi] s or {weapon|"*": [lo, hi]}}]}. Per hit: raw = damage * falloff * zone
  multipliers; dealt = max(raw * min_damage_frac, raw * (1 - armor_pct) - armor_flat). Shot k fires
  at k / rate plus a reload per emptied magazine; TTK is the time of the killing shot. Fails when
  the median TTK leaves a target band.

economy — {"sessions": 40, "start_balance": 0,
  "sources": [{name, amount, per_session (Poisson events), cv=0 (lognormal spread of the
               session total), growth=1 (per session), start=1, end}],
  "sinks": [{name, kind, priority, need}]  paid in priority order; kinds: repeatable {cost,
            per_session, growth}, upkeep {cost, growth}, tax {rate, of: income|balance} (needs
            by default), upgrade {cost, growth (per level), max, per_session, plan [[session,
            level], ...]}, items {items: [{name, cost, planned, wanted_from}]} (wants),
  "targets": {"max_hoard_sessions": 5, "max_unmet": 0.35, "plan_tolerance": 0.3}}.
  Fails on inflation (balance keeps piling up: hoard > max_hoard_sessions of income and still
  growing > 10% of income per session in the last third), scarcity (share of needs left unpaid in
  the last third > max_unmet) or pacing (an item's median purchase session or an upgrade's median
  level off its plan by more than plan_tolerance, at least 1).

drops — exact distribution of attempts until the first success: base chance, soft pity (+step per
  attempt from soft-start), hard pity, or a pseudo-random distribution (chance C*n after n fails).

curve — {"levels": 30, "xp": {curve}, "rate": {curve}, "rate_unit": "hour",
  "targets": [[level, min, max], ...], "max_step": 1.5}; curve kinds: linear {a, b}: a + b(n-1);
  poly {a, k, c=0}: a (n+c)^k; exp {a, r}: a r^(n-1); triangular {a}: a n(n+1)/2; logistic {floor, cap,
  mid, s}; table {values}. Time per level = xp(n) / rate(n). Fails on level-time jumps above
  max_step x the previous level or times outside the interpolated target band.
"""

import argparse
import csv
import json
import math
import os
import sys

import numpy as np


def load(path):
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def entries(data, key):
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return data[key]
    raise ValueError(f"expected a list or an object with '{key}'")


def pct(values, q):
    """Percentile where 'never' (inf) counts as the slowest outcome; None if it lands there."""
    value = float(np.percentile(values, q, method="nearest"))
    return value if math.isfinite(value) else None


def rnd(x, n=3):
    return None if x is None or not math.isfinite(x) else round(float(x), n)


# ---------------------------------------------------------------- ttk

def interp(points, x):
    pts = sorted((float(a), float(b)) for a, b in points)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return float(np.interp(x, xs, ys))


def accuracy_at(acc, distance):
    if isinstance(acc, (int, float)):
        return {"body": float(acc)}
    if isinstance(acc, dict):
        return {k: float(v) for k, v in acc.items()}
    if isinstance(acc, list) and acc:
        chosen = sorted(acc, key=lambda e: float(e[0]))[0][1]
        for start, table in sorted(acc, key=lambda e: float(e[0])):
            if distance >= float(start):
                chosen = table
        return accuracy_at(chosen, distance)
    return {"body": 1.0}


def shot_times(n, rate, magazine, reload_s):
    k = np.arange(n, dtype=float)
    t = k / rate
    if magazine and reload_s:
        t += (np.arange(n) // int(magazine)) * float(reload_s)
    return t


def ttk_pair(w, e, distance, trials, rng):
    rate = float(w["rate"]) if "rate" in w else float(w["rpm"]) / 60.0
    if rate <= 0:
        raise ValueError(f"{w.get('name')}: rate must be > 0")
    pellets = int(w.get("pellets", 1))
    acc = accuracy_at(w.get("accuracy", 1.0), distance)
    hit_total = sum(acc.values())
    if hit_total > 1 + 1e-9:
        raise ValueError(f"{w.get('name')}: accuracy chances sum to {hit_total:.3f} > 1")
    zones = list(acc)
    probs = np.array([acc[z] for z in zones] + [max(0.0, 1 - hit_total)])
    probs = probs / probs.sum()
    raw = float(w["damage"]) * interp(w.get("falloff", [[0, 1.0]]), distance)
    floor = float(e.get("min_damage_frac", 0.0))
    armor_pct, armor_flat = float(e.get("armor_pct", 0.0)), float(e.get("armor_flat", 0.0))

    def dealt(zone):
        hit = raw * float(w.get("multipliers", {}).get(zone, 1.0)) * \
            float(e.get("zones", {}).get(zone, 1.0))
        return max(hit * floor, hit * (1 - armor_pct) - armor_flat)

    dmg = np.array([dealt(z) for z in zones] + [0.0])
    hp = float(e["hp"])
    body = dealt("body")
    stk = math.ceil(hp / (body * pellets)) if body > 0 else None
    mag, reload_s = w.get("magazine"), w.get("reload_s")
    ideal = float(shot_times(stk, rate, mag, reload_s)[-1]) if stk else math.inf
    per_shot = pellets * float(probs @ dmg)
    sustain = 1.0
    if mag and reload_s:
        sustain = float(mag) / (float(mag) + float(reload_s) * rate)
    row = {"weapon": w.get("name"), "enemy": e.get("name"), "range_m": distance,
           "damage_per_hit_body": rnd(body, 2), "stk_body": stk, "ttk_ideal_s": rnd(ideal),
           "dps_expected": rnd(per_shot * rate, 1),
           "dps_sustained": rnd(per_shot * rate * sustain, 1)}
    if per_shot <= 0:
        ttk = np.full(trials, np.inf)
        shots = np.full(trials, np.inf)
    else:
        max_shots = int(min(5000, math.ceil(hp / per_shot) * 4 + 30))
        times = shot_times(max_shots, rate, mag, reload_s)
        batch = max(1, min(trials, 4_000_000 // (max_shots * len(probs))))
        ttk, shots = np.empty(trials), np.empty(trials)
        for lo in range(0, trials, batch):
            n = min(batch, trials - lo)
            counts = rng.multinomial(pellets, probs, size=(n, max_shots))
            cum = np.cumsum(counts @ dmg, axis=1)
            killed = cum >= hp - 1e-9
            first = killed.argmax(axis=1)
            ok = killed[np.arange(n), first]
            ttk[lo:lo + n] = np.where(ok, times[first], np.inf)
            shots[lo:lo + n] = np.where(ok, first + 1, np.inf)
    kill_rate = float(np.isfinite(ttk).mean())
    row.update(kill_rate=rnd(kill_rate),
               ttk_mean_s=rnd(float(ttk[np.isfinite(ttk)].mean())) if kill_rate else None,
               ttk_p10_s=rnd(pct(ttk, 10)), ttk_p50_s=rnd(pct(ttk, 50)),
               ttk_p90_s=rnd(pct(ttk, 90)),
               shots_p50=rnd(pct(shots, 50), 1))
    target = e.get("ttk_target")
    if isinstance(target, dict):
        target = target.get(w.get("name"), target.get("*"))
    problems = []
    if target:
        lo_t, hi_t = float(target[0]), float(target[1])
        p50 = row["ttk_p50_s"]
        row["ttk_target_s"] = [lo_t, hi_t]
        if p50 is None or not lo_t <= p50 <= hi_t:
            problems.append(f"{w.get('name')} vs {e.get('name')} at {distance} m: median TTK "
                            f"{p50} s outside {lo_t}-{hi_t} s")
    row["problems"] = problems
    return row


def run_ttk(weapons, enemies, ranges, trials, seed):
    rng = np.random.default_rng(seed)
    rows = [ttk_pair(w, e, float(d), trials, rng) for w in weapons for e in enemies
            for d in ranges]
    problems = [p for r in rows for p in r["problems"]]
    return {"mode": "ttk", "trials": trials, "seed": seed, "table": rows, "problems": problems,
            "verdict": "fail" if problems else "pass"}


# ---------------------------------------------------------------- economy

def run_economy(cfg, players, seed, csv_path=None):
    rng = np.random.default_rng(seed)
    sessions = int(cfg.get("sessions", 30))
    targets = {"max_hoard_sessions": 5.0, "max_unmet": 0.35, "plan_tolerance": 0.3,
               **(cfg.get("targets") or {})}
    balance = np.full(players, float(cfg.get("start_balance", 0.0)))
    sinks = sorted(enumerate(cfg.get("sinks") or []),
                   key=lambda e: (float(e[1].get("priority", 0)), e[0]))
    levels = {i: np.zeros(players, dtype=int) for i, s in sinks if s.get("kind") == "upgrade"}
    bought = {(i, j): np.full(players, np.inf) for i, s in sinks if s.get("kind") == "items"
              for j in range(len(s.get("items") or []))}
    level_history = {i: [] for i in levels}
    per_session, spent_by_sink = [], {s.get("name", f"sink{i}"): 0.0 for i, s in sinks}
    income_by_source = {s.get("name", f"source{i}"): 0.0
                        for i, s in enumerate(cfg.get("sources") or [])}
    for s in range(1, sessions + 1):
        income = np.zeros(players)
        for i, src in enumerate(cfg.get("sources") or []):
            if s < int(src.get("start", 1)) or (src.get("end") and s > int(src["end"])):
                continue
            events = rng.poisson(float(src.get("per_session", 1.0)), players)
            amount = float(src["amount"]) * float(src.get("growth", 1.0)) ** (s - 1)
            cv = float(src.get("cv", 0.0))
            spread = 1.0
            if cv > 0:
                sigma = math.sqrt(math.log(1 + cv * cv))
                spread = rng.lognormal(-sigma * sigma / 2, sigma, players)
            got = events * amount * spread
            income += got
            income_by_source[src.get("name", f"source{i}")] += float(got.sum())
        balance += income
        spend, unmet, need_paid = np.zeros(players), np.zeros(players), np.zeros(players)
        for i, sink in sinks:
            kind, name = sink.get("kind", "repeatable"), sink.get("name", f"sink{i}")
            growth = float(sink.get("growth", 1.0))
            # needs (ammo, repairs, upkeep) must be paid; wants (upgrades, items) are paced
            need = bool(sink.get("need", kind in ("tax", "upkeep", "repeatable")))
            paid, short = np.zeros(players), np.zeros(players)
            if kind == "tax":
                base = balance if sink.get("of") == "balance" else income
                paid = np.minimum(balance, float(sink["rate"]) * base)
            elif kind == "upkeep":
                cost = float(sink["cost"]) * growth ** (s - 1)
                paid = np.minimum(balance, cost)
                short = cost - paid
            elif kind == "repeatable":
                unit = float(sink["cost"]) * growth ** (s - 1)
                want = rng.poisson(float(sink.get("per_session", 1.0)), players)
                buys = np.minimum(want, np.floor(balance / unit)) if unit > 0 else want
                paid = buys * unit
                short = (want - buys) * unit
            elif kind == "upgrade":
                cap, limit = int(sink.get("max", 10 ** 6)), int(sink.get("per_session", 10 ** 6))
                lvl = levels[i]
                for _ in range(min(limit, cap)):
                    cost = float(sink["cost"]) * growth ** lvl
                    can = (lvl < cap) & (balance - paid >= cost)
                    if not can.any():
                        break
                    paid += np.where(can, cost, 0.0)
                    lvl += can
                short = np.where((lvl < cap) & (paid == 0), float(sink["cost"]) * growth ** lvl,
                                 0.0)
                level_history[i].append(float(np.median(lvl)))
            elif kind == "items":
                for j, item in enumerate(sink.get("items") or []):
                    if s < int(item.get("wanted_from", 1)):
                        continue
                    owned = bought[(i, j)]
                    want = ~np.isfinite(owned)
                    can = want & (balance - paid >= float(item["cost"]))
                    paid += np.where(can, float(item["cost"]), 0.0)
                    owned[can] = s
                    short += np.where(want & ~can, float(item["cost"]), 0.0)
            else:
                raise ValueError(f"sink {name}: unknown kind {kind!r}")
            if need:
                unmet += short
                need_paid += paid
            balance -= paid
            spend += paid
            spent_by_sink[name] += float(paid.sum())
        per_session.append({"session": s, "income_mean": float(income.mean()),
                            "spend_mean": float(spend.mean()),
                            "needs_paid_mean": float(need_paid.mean()),
                            "needs_unmet_mean": float(unmet.mean()),
                            "balance_p10": float(np.percentile(balance, 10)),
                            "balance_p50": float(np.percentile(balance, 50)),
                            "balance_p90": float(np.percentile(balance, 90))})
    step = max(1, sessions // 10)
    third = per_session[-max(1, sessions // 3):]
    inc = sum(r["income_mean"] for r in third)
    spd = sum(r["spend_mean"] for r in third)
    unm = sum(r["needs_unmet_mean"] for r in third)
    needs = sum(r["needs_paid_mean"] for r in third)
    total_inc = sum(r["income_mean"] for r in per_session)
    total_spd = sum(r["spend_mean"] for r in per_session)
    income_per_session = inc / len(third) if third else 0.0
    end = per_session[-1]["balance_p50"]
    start_window = per_session[-len(third) - 1]["balance_p50"] if len(third) < sessions else \
        float(cfg.get("start_balance", 0.0))
    hoard = end / income_per_session if income_per_session > 0 else math.inf if end > 0 else 0.0
    growth_share = (end - start_window) / (len(third) * income_per_session) \
        if income_per_session > 0 else 0.0
    unmet_share = unm / (needs + unm) if needs + unm > 0 else 0.0
    problems = []
    if hoard > float(targets["max_hoard_sessions"]) and growth_share > 0.10:
        problems.append(f"inflation: median balance = {hoard:.1f} sessions of income and still "
                        f"growing {growth_share:.0%} of income per session in the last third — "
                        "add a desirable sink or cut a source")
    if unmet_share > float(targets["max_unmet"]):
        problems.append(f"scarcity: {unmet_share:.0%} of needed spending (ammo, repairs, "
                        "upkeep) unaffordable in the last third — raise a source or cut a cost")
    tol_share = float(targets["plan_tolerance"])
    upgrades = []
    for i, history in level_history.items():
        sink = cfg["sinks"][i]
        entry = {"upgrade": sink.get("name", f"sink{i}"),
                 "median_level_by_session": {str(s + 1): history[s]
                                             for s in range(step - 1, sessions, step)}}
        for session, level in sink.get("plan") or []:
            session, level = int(session), float(level)
            if 1 <= session <= sessions:
                got = history[session - 1]
                if abs(got - level) > max(1.0, tol_share * level):
                    problems.append(f"pacing: {entry['upgrade']} at level {got:g} by session "
                                    f"{session}, planned {level:g}")
        upgrades.append(entry)
    timeline = []
    for (i, j), owned in bought.items():
        item = cfg["sinks"][i]["items"][j]
        share = float(np.isfinite(owned).mean())
        median = float(np.median(owned)) if share >= 0.5 else None
        entry = {"item": item.get("name", f"item{j}"), "cost": item["cost"],
                 "planned": item.get("planned"), "median_session": median,
                 "bought_share": round(share, 3)}
        planned = item.get("planned")
        if planned is not None:
            tol = max(1.0, float(targets["plan_tolerance"]) * float(planned))
            if median is None:
                problems.append(f"pacing: {entry['item']} bought by only {share:.0%} of players "
                                f"(planned for session {planned})")
            elif abs(median - float(planned)) > tol:
                problems.append(f"pacing: {entry['item']} bought at session {median:g}, "
                                f"planned {planned} (±{tol:g})")
        timeline.append(entry)
    if csv_path:
        os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(per_session[0]))
            writer.writeheader()
            writer.writerows(per_session)
    return {"mode": "economy", "players": players, "sessions": sessions, "seed": seed,
            "sink_source_ratio": rnd(total_spd / total_inc if total_inc else 0.0),
            "sink_source_ratio_last_third": rnd(spd / inc if inc else 0.0),
            "hoard_sessions_of_income": rnd(hoard, 2),
            "balance_growth_share_last_third": rnd(growth_share),
            "needs_unmet_share_last_third": rnd(unmet_share),
            "income_by_source": {k: rnd(v / players, 1) for k, v in income_by_source.items()},
            "spend_by_sink": {k: rnd(v / players, 1) for k, v in spent_by_sink.items()},
            "items": timeline, "upgrades": upgrades,
            "sessions_sample": [{k: rnd(v, 1) for k, v in r.items()}
                                for r in per_session[step - 1::step]],
            "problems": problems, "verdict": "fail" if problems else "pass"}


# ---------------------------------------------------------------- drops

def prd_constant(p):
    """C with mean chance p when the chance after n-1 failures is C*n."""
    def nominal(c):
        fail, expected, n = 1.0, 0.0, 1
        while True:
            pn = min(1.0, c * n)
            expected += n * fail * pn
            fail *= 1 - pn
            if pn >= 1.0:
                return 1.0 / expected
            n += 1
    lo, hi = 0.0, p
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if nominal(mid) < p else (lo, mid)
    return (lo + hi) / 2


def run_drops(p, hard_pity, soft_start, soft_step, prd, attempts, max_p90):
    if not 0 < p <= 1:
        raise ValueError("--p must be in (0, 1]")
    c = prd_constant(p) if prd else None
    fail, dist, n = 1.0, [], 0
    while fail > 1e-12 and n < 1_000_000:
        n += 1
        if prd:
            pn = min(1.0, c * n)
        else:
            pn = p
            if soft_start and n >= soft_start:
                pn = min(1.0, p + soft_step * (n - soft_start + 1))
            if hard_pity and n >= hard_pity:
                pn = 1.0
        dist.append(fail * pn)
        fail *= 1 - pn
    dist = np.array(dist)
    cdf = np.cumsum(dist)
    expected = float((np.arange(1, len(dist) + 1) * dist).sum() / dist.sum())

    def quantile(q):
        return int(np.searchsorted(cdf, q - 1e-12) + 1)

    res = {"mode": "drops", "base_p": p, "prd_constant": rnd(c, 6) if c else None,
           "hard_pity": hard_pity, "soft_start": soft_start, "soft_step": soft_step,
           "expected_attempts": rnd(expected, 2), "effective_rate": rnd(1 / expected, 5),
           "attempts_p50": quantile(0.5), "attempts_p90": quantile(0.9),
           "attempts_p99": quantile(0.99),
           "p_by_attempts": {str(a): rnd(float(cdf[min(a, len(cdf)) - 1]), 4)
                             for a in attempts}}
    problems = []
    if max_p90 is not None and res["attempts_p90"] > max_p90:
        problems.append(f"90% of players need up to {res['attempts_p90']} attempts "
                        f"(limit {max_p90})")
    res.update(problems=problems, verdict="fail" if problems else "pass")
    return res


# ---------------------------------------------------------------- curve

def curve_values(spec, n):
    kind = spec.get("kind", "poly")
    lv = np.arange(1, n + 1, dtype=float)
    if kind == "linear":
        return float(spec["a"]) + float(spec.get("b", 0)) * (lv - 1)
    if kind == "poly":
        return float(spec["a"]) * (lv + float(spec.get("c", 0))) ** float(spec.get("k", 2))
    if kind == "exp":
        return float(spec["a"]) * float(spec["r"]) ** (lv - 1)
    if kind == "triangular":
        return float(spec["a"]) * lv * (lv + 1) / 2
    if kind == "logistic":
        lo, hi = float(spec.get("floor", 0)), float(spec["cap"])
        return lo + (hi - lo) / (1 + np.exp(-float(spec["s"]) * (lv - float(spec["mid"]))))
    if kind == "table":
        values = [float(v) for v in spec["values"]]
        if len(values) < n:
            raise ValueError(f"table has {len(values)} values, {n} levels needed")
        return np.array(values[:n])
    raise ValueError(f"unknown curve kind {kind!r}")


def run_curve(cfg):
    n = int(cfg.get("levels", 20))
    xp, rate = curve_values(cfg["xp"], n), curve_values(cfg["rate"], n)
    if (rate <= 0).any():
        raise ValueError("rate must be > 0 at every level")
    t = xp / rate
    unit = cfg.get("rate_unit", "hour")
    max_step = float(cfg.get("max_step", 1.5))
    targets = sorted(cfg.get("targets") or [])
    rows, problems = [], []
    for i in range(n):
        level = i + 1
        ratio = t[i] / t[i - 1] if i else None
        row = {"level": level, "xp_to_next": rnd(xp[i], 1),
               "xp_total": rnd(float(xp[:i + 1].sum()), 1), "rate": rnd(rate[i], 2),
               f"{unit}s": rnd(t[i], 3), f"{unit}s_total": rnd(float(t[:i + 1].sum()), 3),
               "step": rnd(ratio, 2)}
        if ratio is not None and ratio > max_step:
            problems.append(f"level {level}: time per level jumps x{ratio:.2f} (> {max_step}) — "
                            "a grind wall")
        if targets and targets[0][0] <= level <= targets[-1][0]:
            levels = [tg[0] for tg in targets]
            lo = float(np.interp(level, levels, [tg[1] for tg in targets]))
            hi = float(np.interp(level, levels, [tg[2] for tg in targets]))
            row["target"] = [rnd(lo), rnd(hi)]
            if not lo <= t[i] <= hi:
                problems.append(f"level {level}: {t[i]:.3g} {unit}s outside {lo:.3g}-{hi:.3g}")
        rows.append(row)
    return {"mode": "curve", "levels": n, "unit": unit, "table": rows, "problems": problems,
            "verdict": "fail" if problems else "pass"}


# ---------------------------------------------------------------- cli

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("ttk", help="time-to-kill table (Monte Carlo)")
    t.add_argument("--weapons", required=True)
    t.add_argument("--enemies", required=True)
    t.add_argument("--ranges", type=float, nargs="+", default=[10.0])
    t.add_argument("--trials", type=int, default=20000)
    t.add_argument("--seed", type=int, default=1)
    e = sub.add_parser("economy", help="currency over N sessions from sources/sinks")
    e.add_argument("config")
    e.add_argument("--players", type=int, default=2000)
    e.add_argument("--seed", type=int, default=1)
    e.add_argument("--csv", default=None, help="per-session table for plotting")
    d = sub.add_parser("drops", help="attempts-until-drop distribution with pity")
    d.add_argument("--p", type=float, required=True, help="base chance per attempt")
    d.add_argument("--hard-pity", type=int, default=None)
    d.add_argument("--soft-start", type=int, default=None)
    d.add_argument("--soft-step", type=float, default=0.0)
    d.add_argument("--prd", action="store_true", help="pseudo-random distribution with mean --p")
    d.add_argument("--attempts", type=int, nargs="+", default=[10, 50, 100])
    d.add_argument("--max-p90", type=int, default=None)
    c = sub.add_parser("curve", help="XP / level pacing table")
    c.add_argument("config")
    for p in (t, e, d, c):
        p.add_argument("--out", default=None, help="also write the JSON report here")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "ttk":
            res = run_ttk(entries(load(args.weapons), "weapons"),
                          entries(load(args.enemies), "enemies"), args.ranges, args.trials,
                          args.seed)
        elif args.cmd == "economy":
            res = run_economy(load(args.config), args.players, args.seed, args.csv)
        elif args.cmd == "drops":
            res = run_drops(args.p, args.hard_pity, args.soft_start, args.soft_step, args.prd,
                            args.attempts, args.max_p90)
        else:
            res = run_curve(load(args.config))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        res = {"mode": args.cmd, "problems": [f"input error: {exc!r}"], "verdict": "fail"}
    text = json.dumps(res, indent=1, ensure_ascii=False)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0 if res["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
