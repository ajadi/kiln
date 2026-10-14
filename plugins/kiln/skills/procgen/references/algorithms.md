# Procgen algorithms

Each algorithm below lists when to use it, parameters with defaults, failure modes and cost.
Values marked (working) are Kiln starting points; the rest come from the numbered sources at the
end. Every algorithm draws from its own RNG stream (§9) and is accepted only after a seed sweep
(§10). C = cells, R = rooms, T = tiles/patterns, D = neighbour directions.

## 1. Critical path, then branches (Spelunky)

**Use for** linear runs and platformers with side rooms; up to ~30 room slots.

Spelunky [5]: 16 rooms in a 4×4 grid. Start in a random top-row room; roll 1–5 each step: 1–2
move left, 3–4 move right, 5 move down; at the side wall, move down instead. A room left
downward needs a bottom exit (type 2), the room entered from above needs a top exit (type 3),
other path rooms are type 1 (left + right). Reaching the bottom row places the exit. Slots off
the path get type 0 (no guaranteed exits). Each slot is filled with a random hand-made template
for its type; templates contain probabilistic tiles and obstacle blocks.

Generalised (working): path length 6–14 rooms; branch from a path room with p = 0.3, branch length
1–3; every branch end pays off (reward, key, secret, shortcut); keys sit on branches that start
before their lock; difficulty = f(path index), rising.

**Failure modes**: a template that does not honour its type's exits (check each template once in
the editor, not per seed); a path that drops straight down (enforce the minimum length or reject);
sealed side rooms with floor (the checker reports unreachable floor).
**Cost**: O(R).

## 2. Graph grammars, authored flows, cycles

**Use for** dungeons with keys and locks, backtracking, pacing that must read as designed.

- **Mission graph → space** (Dormans, via [2]): a find-and-replace rule set rewrites a start
  graph, then the graph is embedded in space. Example rules (working probabilities):

```
S                 → entrance — T — boss — exit
T                 → T — T                      p 0.4 while rooms < budget
T                 → room                       p 0.6
X — Y             → X — lock(k) — Y,  key(k) on a new branch off a node before X
room              → room + one-way edge back to an earlier node    (shortcut, ≤ 1 per level)
```

- **Authored flows** (Enter the Gungeon [3]): a few hand-made graphs per stage (4 in the first
  stage, 8 in the second), ~300 rooms for stage 1, special rooms injected by metadata (what,
  where, probability, preconditions). Layout attaches rooms at predefined exits, retries a
  failing part up to 3 times, and falls back to corridors 4–30 units long.
- **Cycles** (Unexplored [4]): start from a loop with the entrance and goal on it; the two arcs
  get roles from a cycle type (two alternative routes, lock and key, hidden shortcut back).

Embedding: per node pick a chunk with matching tags, door count and difficulty (§ assembly.md),
place by depth-first search with backtracking, count attempts; give up on the sub-seed after a
cap (20 (working)) and take the next one.

Parameters (working): room budget 8–14; keys 0–3; cycles 1–2; one-way edges ≤ 2.
**Failure modes**: key behind its own lock, one-way drop into a pit (softlock), embedding that
does not fit (rising retry count), sameness when there are too few authored flows.
**Cost**: rewriting is cheap; embedding is exponential in the worst case — cap attempts.

## 3. Wave Function Collapse

**Use for** tile or module adjacency (simple tiled), or decoration that resembles an example
(overlapping). It gives local consistency only: no connectivity, no pacing.

Algorithm [1][6]: every cell holds the set of allowed tiles; observe the cell with the lowest
entropy (fewest options, ties broken by the RNG), collapse it to a weighted choice, propagate
removals to neighbours (arc consistency) until stable; repeat.

| | Simple tiled | Overlapping |
|---|---|---|
| Input | tile set with a socket per side (`wall`, `door`, `floor`; asymmetric `a`/`a'`), weights | sample bitmap |
| Defaults (reference program) | output 24×24 | N = 3, symmetry 8, periodicInput true, output 48×48 |
| Ground / borders | pre-constrain borders, doors, path cells before the first observation | `ground` pins the bottom row |
| Cost | lower: T = tile variants | T = distinct N×N patterns (hundreds+) |

Reference defaults [1]: heuristic Entropy (MRV and Scanline also offered), periodic output off,
up to 10 attempts per sample. Licence MIT.

**Contradictions**: a cell can lose all options; the problem is NP-hard, so no algorithm always
finishes fast [1]. Options: restart with the next sub-seed (≤ 20 (working); count retries — the
gate is ≤ 5% of seeds retried); backtracking (DeBroglie, MIT, C# [7]); generate large maps in
blocks. Pre-constraints (fixed tile, border, path, count, separation — DeBroglie's constraint
list [7]) move structure out of luck; a different technique should give large structure —
WFC fills it in [6].
**Failure modes**: overlapping with a small sample copies it verbatim; pattern counts explode
with N = 4+; no connectivity — use a path constraint or reject the seed after the checker.
**Cost**: propagation with support counts O(C·T·D) per run; naive lowest-entropy search adds
O(C) per step (use a heap).

## 4. BSP rooms and corridors

**Use for** roguelike floors of rectangular rooms.

RogueBasin [9]: split the rectangle recursively in a random direction; position 0.45–0.55 for
regular, 0.1–0.9 for varied layouts; stop when leaves are about room size; one random room per
leaf; connect siblings bottom-up with a straight corridor when their walls face each other,
otherwise a Z-shaped one.
Parameters (working): minimum leaf = minimum room + 2 walls; depth 4–5; room fills 60–90% of
the leaf; add 1–2 extra connections between neighbouring leaves for loops.
**Failure modes**: a tree with no loops (all backtracking), grid-like sameness, long corridors.
**Cost**: O(R log R).

## 5. Cellular automata caves

**Use for** organic caves and blobs.

RogueBasin [10]: fill 40% walls (older examples 45%), border cells walls; 4 passes of
`wall if R1 ≥ 5 or R2 ≤ 2` (R1 = walls in the 3×3 block, R2 = walls in the 5×5 block), then
3 passes of `wall if R1 ≥ 5`; flood fill from a floor cell and turn unreached floor into wall
(Kiln keeps the largest region); accept maps whose connected floor is ≥ ~45% of the area.
Start and exit: BFS from the start, exit on a cell ≥ 70% of the maximum distance (working).
**Failure modes**: disconnected pockets (fill or tunnel them), too open or too closed (reject),
no landmarks — stamp authored chunks into the cave.
**Cost**: O(C · passes).

## 6. Noise terrain and biomes

**Use for** heightfields, biome and density maps.

Red Blob [8]: octaves with amplitudes 1, ½, ¼ at frequencies 1, 2, 4; divide by the amplitude sum
(1.75) to stay in 0–1; redistribute with `pow(e, exponent)` (higher exponent = flatter valleys);
elevation and moisture use different seeds or they repeat each other; biome = lookup on
(elevation, moisture). Wavelength = map size / frequency.
Godot `FastNoiseLite` defaults [11]: Simplex Smooth, fractal FBM, 5 octaves, lacunarity 2.0,
gain 0.5, frequency 0.01 (wavelength 100 units), seed 0; output mostly in [-1, 1] — remap with
`(n + 1) / 2`.
Parameters (working): 3–6 octaves; frequency = 1 / feature size; exponent 1–3.
**Failure modes**: one seed for every layer (correlated maps); seed 0 everywhere; slopes or
water that block the route — noise guarantees nothing, validate walkability; float results
may differ across platforms (UNVERIFIED for bitwise identity) — bake terrain that must match.
**Cost**: O(C · octaves).

## 7. Poisson-disk scatter (Bridson)

**Use for** props, foliage, pickups, spawn candidates — even spacing without a grid look.

Bridson 2007 [12]: inputs minimum distance r and k (typically 30). Background grid with cell
r/√d (one sample per cell); first sample random; while the active list is not empty, pick a
random active sample and try up to k points in the annulus r–2r around it; accept a point with
no sample closer than r, add it to the active list; after k failures remove the sample from the
list. O(N) for N samples.
Kiln rules: sample only inside authored areas (a mask or polygon from the chunk), choose the
active index with the system's own RNG, variable density via r(x) from a noise or painted map
(grid cell from the smallest r).
**Failure modes**: k too small leaves holes; samples on blocked ground (test against the mask and
collision); identical results across systems sharing one RNG.

## 8. Choosing and combining

Structure first, detail second: a graph or path (§1–2) fixes topology and pacing; chunks give
the authored quality; WFC, CA or noise fill inside chunk bounds; Poisson places dressing. Each
stage reads the previous stage's data, never the scene tree.

## 9. Determinism rules

1. **One RNG instance per system**, seeded with `sub_seed(run_seed, "layout")`,
   `"encounters"`, `"loot"`, `"cosmetic"`; retries use `"layout:<attempt>"`. Sub-seed = a
   stable hash written in game code (FNV-1a 32 over the UTF-8 of `"<seed>:<system>"`; code in
   assembly.md). Never engine hashes: Godot's RNG has no avalanche, so similar seeds give
   similar streams [13]; .NET `string.GetHashCode()` is not stable across versions and
   processes.
2. **Seed shown and replayable**: run seed on pause and death screens and in logs; a debug menu
   and command-line flag replay it; generator version stored beside it.
3. **Never `%` on raw output**: `raw % n` adds modulo bias, and an LCG's low bits are weak —
   Unreal's `FRandomStream` says "Very bad quality in the lower bits. Don't use the modulus (%)
   operator" [14]. Use bounded calls (Godot `randi_range` inclusive, .NET `Next(min, max)` and
   Unity.Mathematics `NextInt(min, max)` exclusive max, `FRandomStream::RandRange` inclusive) or,
   in a game-owned PRNG, Lemire's multiply-shift with rejection [15].
4. **Own RNG for every random call** in generation: no global `randi()`, `Array.shuffle()`,
   `pick_random()`, `UnityEngine.Random`, `FMath::Rand`. Fisher–Yates with the system RNG;
   weighted picks with Godot `rand_weighted` or cumulative weights in sorted-id order.
5. **Stable order and maths**: iterate arrays or sorted ids; integer grid coordinates; no frame
   time, physics results or thread scheduling in decisions; one thread per RNG stream.
6. **Cross-patch replay** (daily seeds, shared seeds, saves that regenerate) needs a game-owned
   PRNG (PCG32 or SplitMix64) — engine RNGs are not promised stable (procgen SKILL §4).

## 10. Validation over many seeds

1. Sweep seeds 1..N (N ≥ 200 per generator change, 1000 before release (working)) plus every
   seed in `tests/procgen/seeds.txt`; export one layout JSON per seed (assembly.md §3).
2. Run `procgen_check.py` — topology gate: 100% pass. Its report gives min/median/max of the
   critical path, dead-end ratio and loops; a narrow spread means sameness.
3. Algorithm metrics from the generator's stats: retries per seed (WFC contradictions, failed
   embeddings), CA connected-floor ratio, BSP room count, Poisson sample count per area,
   generation time p50/p95 measured in the engine.
4. Variety: chunk-usage histogram (no chunk > 3× its weight share (working)), distinct
   chunk sequences along the critical path.
5. Every failing seed becomes a regression case; fix the generator, not the seed.

## Sources

1. M. Gumin, WaveFunctionCollapse README and `Program.cs` defaults, github.com/mxgmn (MIT).
2. Boris the Brave, "Graph Rewriting for Procedural Level Generation" (2021), on Dormans' work.
3. Boris the Brave, "Dungeon Generation in Enter The Gungeon" (2019).
4. Boris the Brave, "Dungeon Generation in Unexplored" (2021).
5. D. Kazemi, "Spelunky Generator Lessons", tinysubversions.com/spelunkyGen.
6. Boris the Brave, "Wave Function Collapse Explained" (2020).
7. DeBroglie README and constraints docs (MIT, C#), github.com/BorisTheBrave/DeBroglie.
8. Red Blob Games, "Making maps with noise functions".
9. RogueBasin, "Basic BSP Dungeon generation".
10. RogueBasin, "Cellular Automata Method for Generating Random Cave-Like Levels".
11. Godot 4.7 class reference, FastNoiseLite.
12. R. Bridson, "Fast Poisson Disk Sampling in Arbitrary Dimensions", SIGGRAPH 2007 sketch.
13. Godot 4.7 class reference, RandomNumberGenerator.
14. Unreal Engine 5.8 API, FRandomStream.
15. D. Lemire, "Fast Random Integer Generation in an Interval", ACM TOMACS 2019.
