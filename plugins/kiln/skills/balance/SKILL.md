---
name: balance
description: Balancing game numbers with evidence — tuning tables in data not code, progression curves (linear, triangular, polynomial, exponential, logistic) and when to use each, XP and level pacing measured in time per level, damage/HP/DPS/time-to-kill math with accuracy and armour, difficulty curve and flow, economy sources and sinks with inflation and scarcity checks, drop rates and pity, the telemetry-to-tuning loop and A/B of numbers with the user, with a simulator for TTK, economy, drops and curves. Use when writing or changing tuning tables, weapons, enemies, progression, rewards, prices or drop rates, and when a playtest says too easy, too hard, too grindy or too long to kill.
user-invocable: false
---

# Balance

Balance = numbers in data + a model that predicts what they do + playtests that check the
prediction. Simulate first, tune one parameter group at a time, record why. Values marked
(working) are starting points. Simulator `${CLAUDE_SKILL_DIR}/scripts/balance_sim.py` (numpy,
Bash): `ttk`, `economy`, `drops`, `curve`; input formats and worked examples in
`${CLAUDE_SKILL_DIR}/references/models.md`.

## 1. Tuning tables in data, not code

- Every number a designer may change lives in data the editor shows: Godot `Resource` `.tres` in
  `data/` (`@export` fields, `Curve` resources), Unity ScriptableObjects (`AnimationCurve`), Unreal
  DataTables, CurveTables, Data Assets. Gameplay code holds no tuning literals.
- One table per concern (weapons, enemies, progression, economy, loot), one row per thing, units
  in field names (`damage_hp`, `rate_rps`, `reload_s`, `range_m`).
- Beside each table, `design/balance/<table>.md`: the target ("light mech dies in 1–1.5 s of SMG
  fire at 10 m"), the formula, each change with its reason; locked values in
  `memory/decisions.md`.
- The simulator reads a JSON export of the engine tables (`design/balance/export/`, written by a
  probe or MCP eval; Unreal DataTables export JSON). Results go back into the engine data through
  the MCP — never a second hand-kept copy.

## 2. Progression curves — judge them by time, not by their own numbers

| Curve | f(n) | Use | Watch |
|---|---|---|---|
| linear | a + b(n−1) | short games, fixed content, flat-feel costs | late game trivial if rewards outgrow it |
| triangular | a·n(n+1)/2 | first guess for rising costs; steps grow linearly | — |
| polynomial | a·(n+c)^k, k 1.5–2.5 | XP to next level, upgrade costs | f(2)/f(1) = 2^k at c = 0: early steps jump hardest; c ≥ 2 smooths them |
| exponential | a·r^(n−1), r 1.05–1.25 | incremental games, rewards that also grow exponentially | needs exponential sinks; unbounded |
| logistic | floor + (cap−floor)/(1+e^(−s(n−mid))) | stats approaching a ceiling (crit, resist, speed) | flat at both ends |
| diminishing | x/(x+K) | armour or resist from a rating | 50% at x = K, never 100% |

Time per level = xp(n) / xp_rate(n). Two stacked triangular relations (XP→level, level→points)
give linear point gain (Schreiber).

## 3. XP and level pacing

- First level-up in 2–5 min, time per level on a slightly increasing curve, late levels 20–60 min
  (working); never more than 1.5× the previous level (`curve` flags grind walls).
- Perceived difficulty = (skill challenge + power challenge) − (player skill + player power)
  (Schreiber): challenge steps up ahead of player power, then a power reward overtakes it — a
  sawtooth, not a straight line.
- Spread rewards: a level-up, a new weapon and a new area do not land in the same minute.

## 4. Damage, HP, DPS, TTK

- STK = ceil(HP / damage per hit after armour); TTK = (STK − 1) / rate + reloads (first shot at
  t = 0). DPS = damage × pellets × rate × hit chance; sustained = DPS × mag / (mag + reload × rate).
- Armour: flat −x per hit (crushes fast weak weapons — add a floor of 10–20% of raw), percent
  × (1 − p), or a rating x/(x+K). Weak points multiply ×1.5–3 and change behaviour when broken.
- Ideal TTK hides accuracy: balance on the median of the TTK distribution at combat ranges with
  per-range hit tables, and check p90 for frustration (`ttk`).
- Targets (working, shooter): fodder 0.3–1 s, line enemies 1–3 s, elites 3–8 s focused fire,
  bosses 60–180 s in phases; the player survives ≥ 1.5–2 s from the first hit, so danger can be
  read and answered.
- Per iteration change damage or HP or rate, not all three; re-run the table.

## 5. Difficulty and flow

- Too hard frustrates, too easy bores; challenge rises with skill. Teach → test → twist per
  mechanic; intensity is a sawtooth (level-design beat chart).
- A new enemy or mechanic first appears alone at low pressure; a boss is a spike followed by a
  power reward.
- Dynamic difficulty: prefer invisible supply adjustments (ammo, health drops) over enemy stat
  changes (Hunicke, Hamlet); never punish skill; offer explicit difficulty and assist options; log
  every adjustment.

## 6. Economy: sources and sinks

- Map each currency: sources (capped, trickle, grind, investment, random) and sinks (fixed,
  repeatable, exponential, competitive). Feed sources into sinks of equal or higher power; a big
  desirable sink at the end of the chain keeps the economy taut (Lost Garden value chains).
- Needs (ammo, repairs, upkeep) must stay affordable; wants (upgrades, unlocks) are paced to a
  plan ("shotgun around session 4").
- Healthy (working): sink/source 0.85–1.0 in the last third; median balance ≤ 3–5 sessions of
  income and not still climbing; ≤ 35% of needs unpaid; planned purchases within ±30% of plan.
- Inflation (currency piles up, prices stop mattering) → add a desirable sink or cut a source.
  Scarcity (needs unaffordable, grind) → raise a source or cut a cost. `economy` simulates N
  players × sessions with Poisson events and spread, and reports both.

## 7. Drop rates and pity

- P(≥ 1 in n tries) = 1 − (1 − p)^n. At 1%: 63% after 100 tries; 95% needs 299 — one player in 20
  waits three times the "expected" 100.
- Correct streaks still feel unfair: hard pity (guaranteed at N), soft pity (chance ramps after
  N₀), pseudo-random distribution (chance C·n after n − 1 failures; 25% → C = 0.0847, at most 12
  tries), shuffle bags for short-run fairness. `drops` gives expected attempts, p50/p90/p99 and
  the effective rate.
- Show odds honestly; paid random items must disclose odds (Apple App Store Review Guideline
  3.1.1; check each target store and market).

## 8. Telemetry → tuning loop

1. Decide the question and metric before the playtest: deaths per arena and cause, time per
   level, observed TTK, currency in/out per session, weapon use share, quit points.
2. Log events with the build and tuning-table version (JSON Lines, like the acceptance recorder).
3. Compare with the targets using distributions (median, p90) and outliers, not means; ≥ 10 runs
   per variant in a gym (working). Correlation is not cause — ask the player why.
4. One hypothesis, one parameter group, re-simulate, re-test, record.

## 9. A/B of numbers with the user

- Two gym presets (keys `1`/`2`, gym standard): A = current, B = one changed group, neutral
  labels, played A-B-B-A; then the playtest-with-user questions plus "which felt better, why".
- Describe the pair by consequence ("SMG kills the light mech in ~1.0 s instead of ~1.6 s at
  10 m"), with the measured numbers from the session.
- Lock the winner (`decide`), update the table and its rationale.

## 10. Engine notes

- **Godot 4.6/4.7**: tables as custom `Resource` classes in `data/*.tres` (`duplicate()` per
  instance); `Curve` for authored curves (`sample()`); `RandomNumberGenerator.rand_weighted()`
  for weighted drops on a seeded instance.
- **Unity 6**: ScriptableObject tables, `AnimationCurve.Evaluate`; seeded `System.Random` per
  system for loot.
- **Unreal 5.8**: DataTables (CSV/JSON import and export), CurveTables, `UCurveFloat`; GAS
  attribute sets and GameplayEffects for stats with modifiers; `FRandomStream` per system.
