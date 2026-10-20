---
name: procgen
description: Procedural generation within scene_first — when it pays off, hand-made chunks (rooms, tiles, prefabs, level instances) with connection metadata assembled by a seeded generator that instances them and edits tile or grid cells, algorithms with default parameters (critical path then branches, graph grammars and lock-key flows, Wave Function Collapse tiled vs overlapping, noise terrain, Poisson-disk scatter, BSP rooms, cellular caves), determinism (one seed per system, seed shown and replayable), validation over many seeds (reachability with keys, softlocks, critical path, dead ends, difficulty pacing) with a layout checker, and Godot 4.6/4.7, Unity 6, Unreal 5.8 notes including PCG authored in the editor. Use before building or changing any generator of levels, rooms, encounters, loot placement or scatter.
user-invocable: false
---

# Procedural generation

Generated content is assembled from hand-made pieces by seeded code, validated over hundreds of
seeds, and replayable from its seed. Values marked (working) are starting points. Algorithm
details: `${extensionPath}${/}skills${/}procgen/references/algorithms.md`; chunk metadata, layout export and engine
code: `${extensionPath}${/}skills${/}procgen/references/assembly.md`; checker:
`${extensionPath}${/}skills${/}procgen/scripts/procgen_check.py` (stdlib, Bash).

## 1. When it pays off

Procgen trades authored quality for variety and volume. Use it when:
- replay is the core loop (runs, roguelikes, daily seeds) and layouts must not be memorised;
- the content volume needed exceeds what the team can build, and the variation is perceptible —
  a thousand levels that feel alike are worth one (Compton's "10,000 bowls of oatmeal");
- systemic play needs fresh configurations (encounters, loot, scatter).

Author by hand instead: story levels, a handful of levels, teaching beats, set pieces. Hybrids still
author a lot — Spelunky fills a generated path with room templates, Dead Cells places hand-made
chunks inside a fixed frame and a per-level concept graph, Enter the Gungeon fits ~300 authored
rooms (first floor) to authored flow graphs. Cost = generator + validator + chunk library +
tests; decide in a tech-design note with a spike ("200 seeds, 100% valid, ≤ 200 ms per level").

## 2. The pattern: hand-made chunks, seeded assembly

1. **Chunks** are scenes / prefabs / level instances built in the editor through the MCP:
   geometry, collision, lights, navigation, spawn markers. Each carries its metadata as nodes and
   exported fields: door markers (position on the grid, facing, width, tags), bounds, tags
   (`combat`, `treasure`, `shop`, `start`, `exit`), difficulty 1–5, biome.
2. **Generator** (a script, behaviour only): seeded choices → instantiates prepared chunk scenes
   under a container node that already exists in the level scene, aligned door to door; edits
   tile/grid cells; spawns prepared enemies and pickups at the chunk's markers. It never builds
   meshes, colliders, lights, navigation or containers node by node — the guard rejects
   `Node3D.new()`, `MeshInstance3D.new()` and similar; a genuine exception carries
   `kiln:runtime-node <reason>` on the line.
3. **Layout export** in debug builds: seed, generator version, rooms (id, chunk, tags, difficulty,
   key), edges (lock, one-way) → `production/procgen/layouts/<seed>.json`, the checker's input.
4. **Bake mode** for curated content: run the generator in the editor through the MCP, save the
   result as an ordinary level, then edit by hand. Unreal PCG works this way by default.

## 3. Algorithms (defaults; details in references/algorithms.md)

| Need | Algorithm | Defaults |
|---|---|---|
| linear run + side rooms | critical path, then branches (Spelunky) | 4×4 room slots; walk from the top row: 2/5 left, 2/5 right, 1/5 down; fill the rest; rewards on dead ends |
| dungeons with keys | mission graph → space (graph grammar, Dormans), authored flow graphs (Gungeon), cycles (Unexplored) | rewrite a start-lock-key-boss-exit graph, then fit rooms to nodes; key and lock stay linked; cycles give a second route and shortcuts |
| tile/module adjacency | WFC simple tiled | sockets per tile side; pre-constrain borders, doors, path; contradiction → restart with the next sub-seed (≤ 20 tries (working)); no connectivity guarantee — constrain or reject |
| decoration from an example | WFC overlapping | N = 3; slower; reproduces small samples verbatim |
| terrain, biomes | noise (fBm) | octaves amp 1, ½, ¼, freq ×2, normalise; redistribute e^k; separate seeds for elevation and moisture |
| even scatter | Poisson disk (Bridson) | min distance r, k = 30 tries, cell r/√d; only inside authored areas |
| rooms and corridors | BSP | split 0.45–0.55 regular, 0.1–0.9 varied; room per leaf; connect siblings |
| caves | cellular automata | 40% walls, 4 + 3 smoothing passes, keep the largest region, reject < 45% open |

## 4. Determinism

- One run seed, shown to the player (pause and death screens) and logged; a debug menu or command
  line replays it.
- One sub-seed per system (layout, encounters, loot, cosmetics) = hash(run seed, system name),
  each with its own RNG instance, so changing loot code leaves layouts unchanged.
- Never the global RNG in generation (Godot `randi()`, `Array.shuffle()`, `pick_random()`; Unity
  `UnityEngine.Random`): any other caller shifts it.
- Engine RNG algorithms are not promised stable across versions (Godot calls PCG32 an
  implementation detail; .NET `System.Random` sequences may differ between versions). Seeds that
  must replay across patches (daily runs, shared seeds, saves that regenerate) need a game-owned
  PRNG (PCG32 or SplitMix64) and the generator version stored next to the seed.
- Iterate in a defined order (sorted ids, arrays, not hash-map order); integer grid maths; nothing
  from physics, frame time or threads.

## 5. Validation — many seeds, not one

Export layouts for 200+ seeds per generator change (1000 before release, (working)) and run
`python "${extensionPath}${/}skills${/}procgen/scripts/procgen_check.py" "production/procgen/layouts/*.json"
--min-path 6 --max-path 14 --out production/procgen/check.json`. It checks:

- every exit, goal and key reachable from the start, collecting keys on the way; no lock without
  a reachable key;
- no softlock: from every reachable state an exit stays reachable (one-way drops included; with
  `"keys": "consumed"` a key spent on the wrong door; in a platformer a pit deeper than the
  jump);
- platformer layouts (`"type": "platformer"`, side view): reachability with the controller's
  jump (`"jump": {"height", "width"}` in tiles, from the feel constants), falls, ladders,
  one-way platforms and hazards; the model is optimistic, so a fail is a dead level for sure;
- push-box puzzles (`"type": "sokoban"`): solved by search over pushes with dead squares pruned;
  "unknown" past `--max-states` is a warning, a proven unsolvable level fails (live: a naive
  generator made 152 of 200 seeds unsolvable, found in 2 s);
- `"return": true`: the start is reachable again from every goal and exit (hubs, fetch
  quests: generated content is checked start → goal and goal → start);
- critical path (start → nearest exit, key detours included) within bounds;
- dead ends ≤ 40% of rooms, each paying off (reward, key, secret, shortcut); `--strict-dead-ends`
  makes empty ones fail;
- no unreachable rooms or floor pockets;
- difficulty along the critical path: no step up larger than +2, the last third not easier than
  the first.

Gate: 100% of seeds pass; internal reject-and-retry counted (> 5% of seeds retried = a weak
generator (working)); generation time p95 within budget, measured in the engine; every failing
seed is added to `tests/procgen/seeds.txt` as a regression case. The checker sees topology, not
physics: playtest generated levels in the engine against the level metrics (jumps, gaps,
sightlines).

## 6. Engine notes (code in references/assembly.md)

- **Godot 4.6/4.7**: chunk `.tscn` with `Marker3D`/`Marker2D` doors; `PackedScene.instantiate()`
  under an exported container; `TileMapLayer.set_cell()` / `set_cells_terrain_connect()`,
  `GridMap.set_cell_item()`; `RandomNumberGenerator` per system; `FastNoiseLite` resource with its
  seed in the inspector; baked `NavigationRegion3D` per chunk, edges meeting on the grid.
- **Unity 6**: chunk prefabs with a `RoomChunk` component listing door transforms;
  `Instantiate(prefab, parent)`; `Tilemap.SetTile`/`SetTilesBlock`; `System.Random` or
  `Unity.Mathematics.Random` (seed ≠ 0) per system; `NavMeshSurface.BuildNavMesh()` after assembly.
- **Unreal 5.8**: PCG graphs authored in the editor, component `Seed`, Generation Trigger
  (Generate On Load / On Demand / At Runtime with the runtime scheduler); prefer generating in the
  editor and saving (flag it in the handoff); chunks as Level Instances or Packed Level Actors;
  `FRandomStream` per system, never `%` on its raw output (weak low bits).
