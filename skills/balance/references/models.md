# Balance models — simulator inputs, worked examples, reference numbers

Read with the balance skill. All commands run from the project root; every mode prints JSON with
`verdict` and `problems`, exits 1 on fail, and takes `--out <file>` to keep the report (e.g.
`production/balance/<name>.json` as task evidence).

## ttk — time-to-kill table

```json
{"weapons": [
  {"name": "smg", "damage": 22, "rpm": 900, "magazine": 30, "reload_s": 2.0,
   "multipliers": {"head": 1.5, "limb": 0.8},
   "falloff": [[0, 1.0], [15, 1.0], [35, 0.6]],
   "accuracy": [[0, {"body": 0.7, "head": 0.1}], [25, {"body": 0.45, "head": 0.05}]]},
  {"name": "shotgun", "damage": 12, "rate": 1.2, "pellets": 8, "accuracy": 0.6,
   "falloff": [[0, 1.0], [8, 1.0], [20, 0.3]]}]}
```

```json
{"enemies": [
  {"name": "light_mech", "hp": 300, "armor_flat": 2, "zones": {"head": 2.0},
   "ttk_target": [0.5, 2.0]},
  {"name": "heavy_mech", "hp": 2500, "armor_pct": 0.3, "min_damage_frac": 0.15,
   "ttk_target": {"smg": [6, 14], "*": [4, 12]}}]}
```

`python balance_sim.py ttk --weapons w.json --enemies e.json --ranges 10 25 50 --trials 20000`

- `accuracy`: a number (hit chance, all hits "body"), a zone table (rest = misses), or a list of
  `[from_m, table]` steps by range. Measure hit tables in the gym from probe logs (shots fired vs
  hits per zone per distance band) — do not guess them.
- Per hit: raw = damage × falloff(range) × weapon multiplier × enemy zone multiplier;
  dealt = max(raw × min_damage_frac, raw × (1 − armor_pct) − armor_flat).
- Output per weapon × enemy × range: `stk_body`, `ttk_ideal_s` (every pellet on the body),
  `ttk_p10/p50/p90_s`, `kill_rate` (share of trials that killed within the shot cap),
  `dps_expected`, `dps_sustained` (with reloads). The verdict checks the median against
  `ttk_target`.
- Read it: p50 far above ideal → accuracy dominates (spread, recoil, target size); p90 ≫ p50 →
  streaky (pellet count, headshot dependence); sustained ≪ expected → reload dominates.

Example (hand check): 25 damage, 600 rpm, always hits, 100 HP → 4 shots, 3 intervals of 0.1 s →
TTK 0.3 s; DPS 250.

## economy — currency over sessions

```json
{"sessions": 30, "start_balance": 0,
 "sources": [
   {"name": "enemy_drops", "amount": 5, "per_session": 60, "cv": 0.3, "growth": 1.03},
   {"name": "quest", "amount": 150, "per_session": 1, "start": 2}],
 "sinks": [
   {"name": "ammo", "kind": "repeatable", "cost": 2, "per_session": 40, "priority": 0},
   {"name": "repair", "kind": "tax", "rate": 0.05},
   {"name": "unlocks", "kind": "items", "priority": 1, "items": [
     {"name": "shotgun", "cost": 600, "planned": 4},
     {"name": "railgun", "cost": 2500, "planned": 15, "wanted_from": 8}]},
   {"name": "weapon_upgrades", "kind": "upgrade", "cost": 100, "growth": 1.35, "max": 12,
    "priority": 2, "plan": [[10, 6], [30, 12]]}],
 "targets": {"max_hoard_sessions": 4, "max_unmet": 0.35, "plan_tolerance": 0.3}}
```

`python balance_sim.py economy design/balance/economy.json --players 2000 --csv production/balance/economy.csv`

- Sources: `per_session` events per session (Poisson), `amount` each, `growth` per session
  (scaling with progression), `cv` = spread of the session total (lognormal), `start`/`end`.
- Sinks are paid in `priority` order (lower first, then file order). Needs (`repeatable`,
  `upkeep`, `tax`) count towards "unmet" when unaffordable; wants (`upgrade`, `items`) are checked
  against their plans. Set `"need": true/false` to override. The simulated player is greedy (buys
  whatever is affordable at once); real players also save — check against telemetry.
- Outputs: `sink_source_ratio` (all / last third), `hoard_sessions_of_income`,
  `balance_growth_share_last_third`, `needs_unmet_share_last_third`, per-source income and
  per-sink spend per player, item purchase sessions, upgrade levels by session, a sampled
  per-session table (full table with `--csv`).
- Verdicts: inflation, scarcity, pacing. The example above fails pacing: while the railgun is
  unaffordable, cheap upgrades drain the balance every session, so the railgun lands at session
  23 instead of 15 and upgrades run ahead of plan — the simulated player never saves. Fix the plan,
  the prices, or give saving a reason (a visible goal, upgrade caps per area).

Source and sink types (Lost Garden value chains):

| Sources | Power | Sinks | Power |
|---|---|---|---|
| capped (one-off rewards) | fixed | fixed (one-off purchases) | fixed |
| trickle (per time) | linear | repeatable (ammo, repairs) | linear |
| grind (player-driven repeats) | linear, player-controlled | exponential (upgrade tiers) | exponential |
| investment (income that buys income) | exponential | competitive (auctions, PvP) | adaptive |
| random (drops) | noise on the above | — | — |

## drops — attempts until success

`python balance_sim.py drops --p 0.006 --hard-pity 90 --soft-start 74 --soft-step 0.06`
→ expected 62.3 attempts, effective rate 1.6%, p90 80, guaranteed by 90.

`python balance_sim.py drops --p 0.25 --prd` → C = 0.0847, p99 9 attempts (plain 25%: p99 17).

Pseudo-random distribution constants (chance after n − 1 failures = C·n), computed by the script:

| nominal | 5% | 10% | 15% | 20% | 25% | 30% | 40% | 50% |
|---|---|---|---|---|---|---|---|---|
| C | 0.00380 | 0.01475 | 0.03222 | 0.05570 | 0.08474 | 0.11895 | 0.20155 | 0.30210 |
| max tries | 264 | 68 | 32 | 18 | 12 | 9 | 5 | 4 |

Shuffle bag: put k successes and m failures in a bag, draw without replacement, refill when
empty — exact rate over every k + m draws, bounded streaks. Use a seeded generator per system,
never the engine's global one.

## curve — XP and level pacing

```json
{"levels": 30, "xp": {"kind": "poly", "a": 8, "k": 1.8, "c": 3},
 "rate": {"kind": "exp", "a": 1200, "r": 1.04}, "rate_unit": "hour",
 "targets": [[1, 0.03, 0.1], [10, 0.3, 0.8], [30, 0.8, 2.0]], "max_step": 1.5}
```

`python balance_sim.py curve design/balance/xp_curve.json` → a table per level (XP to next,
total XP, rate, hours, cumulative hours, step ratio); fails on steps > `max_step` and on times
outside the interpolated targets. This example passes: level 1 takes 0.08 h (5 min), level 10
0.47 h, level 30 1.16 h, 20 h to the cap. With `c` = 0 the same curve fails at level 2 (step
×3.35, and level 1 takes 24 s) — polynomial curves jump hardest at the start. `rate` is the XP the player earns per unit of time at that
level — measure it in playtests (XP per minute of play), then re-run.

## Telemetry events (JSON Lines, one object per line)

```
{"t": 812.4, "build": "a1b2c3", "tables": "weapons@14", "ev": "kill", "weapon": "smg",
 "enemy": "light_mech", "range_m": 12.3, "ttk_s": 1.21, "shots": 19, "hits": {"body": 13, "head": 2}}
{"t": 830.0, "ev": "death", "arena": "arena_2", "cause": "heavy_mech.cannon", "pos": [12.1, 0, -4.3]}
{"t": 900.0, "ev": "currency", "session": 3, "in": {"drops": 310}, "out": {"ammo": 96}}
```

Aggregate per arena / weapon / session; compare medians and p90 with the targets in
`design/balance/<table>.md`; feed measured hit tables and earn rates back into the simulator.
