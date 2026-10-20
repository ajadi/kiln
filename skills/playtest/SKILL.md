---
name: playtest
description: How to verify a game change in the running game through the engine's MCP — preconditions, deterministic launch, scripted input, in-game probes, captures saved to files, structured state dumps, scene lint, logs and performance, and how to record evidence that others can re-run. Engine-neutral; the engine profile lists the exact MCP tools. Use whenever a task claims something works in the game, and for every gym or level check.
user-invocable: false
---

# Playtest protocol

"It compiles" and "the files exist" are not evidence. Evidence is what the running game showed:
numbers sampled at runtime, captures from the game camera, a clean log — recorded so the verifier
can re-run it. The engine profile (injected at spawn, skill `kiln:engine-<engine>`) maps each step
below to its MCP tools.

## 1. Preconditions

1. Editor state: ready, correct project, no unsaved changes you did not make; with several editors
   connected, select the right session.
2. Editor log: no import or compile errors for what you are about to test.
3. The checks, written as observations ("mech stops firing when its gun part is destroyed", not
   "damage works"), with the scenario: scene, start state, seed, input sequence, duration.

### Shared workstation (`on_screen` in manifest.md)

An on-screen run takes the user's screen: Godot's embedded run still raises the editor window
(fullscreen once happened), `--minimized` does not render at all (gpu_ms NaN), and Windows clamps
`--position -3000,0` back onto the screen. Frame-time measurements also need a focused window
and an idle machine. With `on_screen=slot` (the user works on the same PC) agents never start
on-screen runs on their own: they work headless (probes, cinematic captures, the acceptance
skill's methods) and append every on-screen check they need to `production/MEASUREMENT_SLOT.md`
(scene, what to measure, script or input sequence, minutes). The producer batches them and asks
the user once for a slot ("I need the screen for ~20 min"), or runs them when the user says they
are away. The guard enforces it: with `on_screen=slot` a windowed game run (MCP `project_run`,
Unity Play, Unreal PIE, a Godot command line without `--headless`) is denied unless
`.kiln/slot` exists (the producer writes it when the user grants a slot, optionally
`until=2026-10-14T23:00`) or `.kiln/away` does. `perf_gate=informational` turns qa-performance into advice that does not block a
task's gates; `off` drops it (g2 rows 7, 19).

## 2. Run

- Start the gym scene first (`scenes/gyms/<mechanic>_gym`), the level only after the gym passes.
- Fixed seed; fixed physics rate; wait for a "ready" signal (state or log line), not a sleep.

## 3. Drive and sample

- Input by action name through the MCP's input simulation or a game-eval call — never raw keys,
  so tests survive rebinding.
- Sample over time inside the game with the acceptance harness's recorder (one MCP round trip is
  slower than a physics tick — polling from outside aliases), then pull the dump once.
- Give image judgements a structured state dump alongside (positions, HP tables, animation states,
  layer masks) — models read numbers far better than small on-screen details.
- Reusable probes go to `tests/probes/` so the verifier and later regressions repeat them.

## 4. Look

- Captures from the game camera at the decisive moments, **saved to files** in
  `production/captures/<task>/` (engine profile: how to save a viewport image from game eval) and
  named by tick or time. Look at them; for small details or on-screen text take a tighter capture
  or crop ×3 before reading.
- Describe what each capture shows in one sentence — what you see, not what the task says should
  be there.

## 5. Scene lint (the most common engine failures)

Misplaced nodes, dropped signal connections, wrong resource assignments, broken node paths and
asset keys are the most frequent agent mistakes in engine work. After changing a scene, check:
the expected nodes exist at the expected paths with the expected types; signals listed in the spec
are connected; resources the scene needs are assigned and load; no missing-dependency warnings.

## 6. Health

- Game log: zero new errors; warnings listed.
- Performance at the heaviest moment (frame time, physics time, draw calls) vs the budget.
- Stop the game; leave the editor as you found it.

## 7. Record

```markdown
## playtest: <scene> — <date>
verdict: PASS | FAIL | NOT ASSESSED
checks:
  - <observable check> — <measured value> (target <x>) — PASS|FAIL
captures: production/captures/<task>/<file> — <what it shows>
log: clean | <n errors: first line>
perf: frame <ms> / physics <ms> / draw calls <n> (budget <...>)
probe: tests/probes/<name> (re-runnable)
```

A FAIL names the smallest reproduction: scene, input sequence, tick or time, observed vs
expected. A probe must be able to fail: say what result would have meant FAIL.

A measured value that misses the expected one is a finding until proven otherwise. Do not write
it off as a "test artefact" until a second driver or an offline calculation reproduces the cause. Live:
two strike clips ran one tick long, and the builder blamed the test buffer. An independent
driver and a plain Python loop showed the real cause: a `timer -= delta` countdown that collects
float error and overruns by a tick for some durations. Count whole physics ticks for durations
that must be exact, or compare against half a tick.

## Gyms

Every mechanic gets an isolated gym scene before it goes into a level, with the minimum needed to
exercise it and on-screen debug readouts of the tuned values (see `/kiln:gym`). Gyms stay after
the mechanic ships — they are the regression tests for feel.

## Autoplay (role `kiln:autoplayer`)

Gameplay gates that need "seen working in the running game" should not wait for the user's
screen. The autoplayer plays toward objectives with scripts in `${extensionPath}${/}skills${/}playtest/scripts/`:

| Script | Use |
|---|---|
| `autoplay_base.gd` | copy to `tests/autoplay/`; a scenario `extends` it: `_setup()` adds objectives (state checks with a timeout) and a progress probe, `_play()` drives input and `nav_path()`; records `trace.csv` (frame time, draw calls, primitives, objects, video memory, node/object counts, pipeline compilations, the frame after a screenshot flagged), scheduled frames, stuck events, `summary.json` (seed, commit, watched mtimes, objectives, verdict); `--viewport msaa_3d=2` A/Bs one setting on the same seed |
| `presence.py` | exit 0 when the user is away (`.kiln/away` or OS idle ≥ `--min-idle` s) |
| `autoplay_loop.py` | N seeded runs while the user stays away, each with its log and exit code; stops when they return |
| `autoplay_report.py` | `REPORT.md`: objectives reached per seed, stuck runs, crashes mid-run vs at exit |
| `explorer.gd` | the agent plays its own level without a route: from a scenario's `_play()`, holds one direction at a time toward the least-visited neighbouring cell (seeded random steps, a jump when walking does not move), records visits and stuck steps per cell (`explore.json`); novelty-seeking bots find reachability bugs scripted routes miss |
| `explore_report.py` | merges explorer runs into `heatmap.png` (visited grey, stuck red) with the worst snags; with `--reachable <layout>` the coverage of the reachable cells and the cells never visited; gates on coverage and on a cell that eats a large share of steps (live: ≥ 90 % of a test maze in 120 game s) |
| `input_replay.gd` | records a session's input per physics frame (a human playing or a script) and plays it back exactly with state hashes every N frames: under `--fixed-fps` and one seed the replay matches the recording, so after a change `first_divergence()` names the first frame where behaviour changed (live: two replays identical; a 15 % slower controller diverged) |

Deterministic by default: `--fixed-fps 60` (one frame = one physics tick, same deltas every run),
one seeded RandomNumberGenerator per system, the seed in the summary; a failure is replayed with
its seed and input file, never "it happened once". Captures for review: Godot Movie Maker,
`godot --path . --fixed-fps 60 --write-movie production/captures/<task>/run.avi --quit-after N -s
<scenario>` (windowed: headless renders nothing; the user away or `on_screen=slot`), the same
frames every time.

Objectives and stuck time use game time (with `--fixed-fps` a headless run is far faster than the
wall clock); `--minutes` limits the wall clock. A crash after "AUTOPLAY done" is a shutdown crash
(engine teardown, audio driver, physics server): track it in `memory/known-issues.md` and keep it
out of the "0 crashes" soak count (g2: 2 of 5 chaos runs, access violation at exit).
