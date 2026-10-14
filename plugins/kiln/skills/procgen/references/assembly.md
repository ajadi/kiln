# Chunk assembly, layout export and engine code

Chunks are built by hand in the editor through the engine MCP; the generator only plans with
data, instances prepared chunks, edits tile/grid cells and spawns prepared scenes at markers.
Values marked (working) are starting points.

## 1. Chunk contract

| Field | Rule |
|---|---|
| `chunk_id` | stable id used in layouts and saves; never reused |
| `size_cells` | footprint in generator cells (8 m or 16 tiles (working)); origin at the minimum corner |
| door sockets | side N/E/S/W, cell along it, width, tags (`locked:red`, `oneway_out`); on the boundary, floor and nav meet the socket line |
| `tags`, `difficulty` 1–5, `biome`, `weight`, `max_per_run` | the planner matches nodes by them |
| markers | enemy, pickup, key, reward, player start — the only places the generator spawns |
| door caps | wall plug per socket inside the chunk, freed when the socket connects |

- **Godot**: `.tscn` rooted at `Node3D`/`Node2D` with `room_chunk.gd` (`class_name RoomChunk`,
  exported fields), `Doors/` (`Marker3D` + `door_socket.gd`: side, cell, width, tags, `@export
  var cap: Node3D`), `Spawns/`, collision, optional baked `NavigationRegion3D`; built with
  `scene_manage`, `node_create`, `node_set_property`, `scene_save`.
- **Unity**: prefab with a `RoomChunk` component (`DoorSocket[]`, tags, difficulty), edited in a
  prefab stage via `manage_prefabs`. **Unreal**: a Level Instance level or a `BP_Chunk_*`
  derived from `ARoomChunk` with door scene components; Packed Level Actors for dressing.
- **Library**: one asset with every chunk's metadata copied out (Godot `ChunkEntry` resources in
  `data/procgen/chunk_library.tres` via `resource_manage`; ScriptableObject; `UPrimaryDataAsset`)
  so planning never instances a scene; a test asserts it matches the chunks.

## 2. Pipeline

Sub-seeds (algorithms.md §9) → **plan** (pure data: rooms with chunk ids, grid positions,
quarter turns, connected sockets; retry with `layout:<attempt>`, count attempts) → **place**
(clear the container, instance chunks, free used caps, set tiles) → **populate** (`encounters`,
`loot` streams, chunk markers only) → **navigation** (§5) → export (§3) → `generated` signal.

## 3. Layout JSON (checker input)

Debug and editor builds write `production/procgen/layouts/<seed>.json` (exported debug builds:
`user://procgen/layouts/`, copied by the sweep). The checker reads `seed`, `type`, `rooms[].id
/tags/key/difficulty`, `edges[].a/b/lock/oneway/length` (grid: `cells`, `legend`, `diagonal`);
extra fields are ignored and help debugging. `start` exactly one, `exit` one or more, `boss`/
`goal` must be reachable, `key` on a room, `lock` on an edge, `length` weights the path.

This graph passes `procgen_check.py layouts/1234.json --min-path 6 --max-path 14
--strict-dead-ends` (critical path r0 r1 r2 r3 r2 r4 r5 r6 = 8 rooms, 1 loop, dead-end ratio
0.25, verified):

```json
{"seed": 1234, "type": "graph", "generator": "crypt", "version": 3, "attempts": 1, "gen_ms": 41.7,
 "rooms": [
  {"id": "r0", "chunk": "crypt_start_a", "pos": [0, 0], "tags": ["start"], "difficulty": 1},
  {"id": "r1", "chunk": "crypt_hall_b", "pos": [1, 0], "tags": ["combat"], "difficulty": 1},
  {"id": "r2", "chunk": "crypt_cross_a", "pos": [2, 0], "tags": ["combat"], "difficulty": 2},
  {"id": "r3", "chunk": "crypt_vault_a", "pos": [2, 1], "tags": ["treasure"], "difficulty": 2, "key": "red"},
  {"id": "r4", "chunk": "crypt_hall_c", "pos": [3, 0], "tags": ["combat"], "difficulty": 3},
  {"id": "r5", "chunk": "crypt_boss_a", "pos": [4, 0], "tags": ["boss"], "difficulty": 4},
  {"id": "r6", "chunk": "crypt_exit_a", "pos": [5, 0], "tags": ["exit"], "difficulty": 4},
  {"id": "r7", "chunk": "crypt_shrine_a", "pos": [3, -1], "tags": ["reward"], "difficulty": 3}],
 "edges": [
  {"a": "r0", "b": "r1"}, {"a": "r1", "b": "r2"}, {"a": "r2", "b": "r3"},
  {"a": "r2", "b": "r4", "lock": "red"}, {"a": "r4", "b": "r5", "length": 2},
  {"a": "r5", "b": "r6"}, {"a": "r4", "b": "r7"}, {"a": "r5", "b": "r1", "oneway": true}]}
```

Grid generators (caves, WFC) export cells; bounds count cells, so run them with their own
`--min-path/--max-path`. This one passes with `--min-path 10 --max-path 40` (path 15 cells):

```json
{"seed": 1235, "type": "grid", "generator": "cave", "version": 3,
 "cells": ["##########", "#@...#...#", "#.##.#.#.#", "#..a...#A#", "####.###>#", "##########"]}
```

## 4. Seeded assemblers

**Godot 4.6/4.7** (behaviour only; `RandomNumberGenerator.new()` is not a node and passes the
guard; `Planner`/`Encounters` are static data functions):

```gdscript
class_name Seeds
## FNV-1a 32 over "<run_seed>:<system>"; values stay below 2^56, no overflow.
static func sub_seed(run_seed: int, system: String) -> int:
	var h := 2166136261
	for b in ("%d:%s" % [run_seed, system]).to_utf8_buffer():
		h = ((h ^ b) * 16777619) & 0xFFFFFFFF
	return h
```

```gdscript
class_name DungeonGenerator
extends Node

signal generated(run_seed: int, stats: Dictionary)

const VERSION := 3
@export var library: ChunkLibrary
@export var rooms_root: Node3D               # empty node placed in the level scene
@export var nav_region: NavigationRegion3D   # optional: level-wide region baking its children
@export var floor_layer: TileMapLayer        # 2D projects; GridMap: set_cell_item()
@export var max_attempts := 20

func generate(run_seed: int) -> void:
	var t0 := Time.get_ticks_usec()
	var plan := {}
	var attempts := 0
	while plan.is_empty() and attempts < max_attempts:
		var rng := RandomNumberGenerator.new()
		rng.seed = Seeds.sub_seed(run_seed, "layout:%d" % attempts)
		attempts += 1
		plan = Planner.plan(rng, library)    # plain Strings/ints; {} when invalid
	assert(not plan.is_empty(), "seed %d: no layout in %d attempts" % [run_seed, attempts])
	for child in rooms_root.get_children():
		rooms_root.remove_child(child)
		child.queue_free()
	for room: Dictionary in plan.rooms:      # array order: deterministic
		var chunk := library.scene(room.chunk).instantiate() as RoomChunk
		chunk.name = room.id
		chunk.position = Vector3(room.pos[0], 0, room.pos[1]) * library.cell_size
		chunk.rotation.y = room.turns * PI / 2.0
		rooms_root.add_child(chunk)
		chunk.connect_doors(room.open_doors) # frees the caps of used sockets
	if floor_layer:
		floor_layer.set_cells_terrain_connect(plan.floor_cells, 0, 0)
	var enc := RandomNumberGenerator.new()
	enc.seed = Seeds.sub_seed(run_seed, "encounters")
	Encounters.populate(enc, rooms_root, plan)   # instances prepared enemy scenes at markers
	await get_tree().process_frame               # freed caps are gone before baking
	if nav_region:
		nav_region.bake_navigation_mesh()        # background thread by default
		await nav_region.bake_finished
	var stats := {"attempts": attempts, "gen_ms": (Time.get_ticks_usec() - t0) / 1000.0}
	if OS.is_debug_build():
		LayoutExport.write(run_seed, VERSION, plan, stats)  # JSON.stringify → FileAccess
	generated.emit(run_seed, stats)
```

**Unity 6** (coroutine on a scene object; `Planner` is plain C# with edit-mode tests):

```csharp
public IEnumerator Generate(int runSeed)
{
    var sw = System.Diagnostics.Stopwatch.StartNew();
    Plan plan = null; int attempts = 0;
    while (plan == null && attempts < maxAttempts)
        plan = Planner.Build(new System.Random(Seeds.Sub(runSeed, $"layout:{attempts++}")), library);
    foreach (Transform c in roomsRoot) Destroy(c.gameObject);
    yield return null;                                     // destroyed rooms are gone
    foreach (var room in plan.Rooms)
    {
        RoomChunk chunk = Instantiate(library.Prefab(room.Chunk), roomsRoot);
        chunk.transform.SetLocalPositionAndRotation(room.Position(library.CellSize),
            Quaternion.Euler(0f, 90f * room.Turns, 0f));
        chunk.name = room.Id;
        chunk.ConnectDoors(room.OpenDoors);
    }
    floorMap.SetTiles(plan.FloorCells, plan.FloorTiles);  // batch, not SetTile per cell
    Encounters.Populate(new System.Random(Seeds.Sub(runSeed, "encounters")), plan, roomsRoot);
    yield return null;
    navSurface.BuildNavMesh();     // Collect Objects: Current Object Hierarchy, Physics Colliders
    LayoutExport.Write(runSeed, plan, attempts, sw.Elapsed.TotalMilliseconds); // editor/dev only
}
```

`Seeds.Sub` is the same FNV-1a with `unchecked` `uint` maths over the UTF-8 of
`runSeed.ToString(CultureInfo.InvariantCulture) + ":" + system` (culture-free digits).
`System.Random` is not thread-safe and may change sequence between .NET versions;
`Unity.Mathematics.Random` needs a non-zero seed and is a struct (store it back after use).

**Unreal 5.8** (C++ system, chunks as content):

```cpp
void ADungeonGenerator::Generate(int32 RunSeed)
{
    FDungeonPlan Plan; int32 Attempts = 0;
    while (Attempts < MaxAttempts)
    {
        FRandomStream Rng(Seeds::Sub(RunSeed, FString::Printf(TEXT("layout:%d"), Attempts++)));
        if (FPlanner::Build(Rng, *Library, Plan)) break;           // pure data
    }
    for (const FPlannedRoom& Room : Plan.Rooms)
    {
        const FTransform Xf(FRotator(0.f, 90.f * Room.Turns, 0.f), Room.Position(Library->CellSize));
        const FChunkEntry& Entry = Library->Get(Room.Chunk);
        if (Entry.ActorClass)                                       // BP chunk authored in the editor
        {
            GetWorld()->SpawnActor<ARoomChunk>(Entry.ActorClass, Xf)->ConnectDoors(Room.OpenDoors);
        }
        else                                                        // level asset as a streamed instance
        {
            bool bOk = false;
            ULevelStreamingDynamic::LoadLevelInstanceBySoftObjectPtr(this, Entry.Level, Xf, bOk,
                FString::Printf(TEXT("%s_%d"), *Room.Id, RunSeed), nullptr, false);
        }
    }
}
```

`Seeds::Sub`: the same FNV-1a over `FTCHARToUTF8`. Streaming is asynchronous — populate after
each level's `OnLevelShown`. Blueprint: Random Stream variable, "Random Integer in Range from
Stream", "Spawn Actor from Class", "Load Level Instance (by Object Reference)". Spawning
`ALevelInstance` or Packed Level Actor Blueprints at runtime is UNVERIFIED — prove it in the
spike. PCG: generate in the editor through the MCP and save (Generation Trigger On Load / On
Demand / At Runtime; output fixed by the component Seed); flag it in the handoff.

## 5. Navigation after assembly

- **Preferred**: each chunk carries its own navigation baked in the editor, edges on the socket
  lines so neighbouring regions share exact vertices or lie within `edge_connection_margin`
  (Godot: baking bounds + `border_size`); nothing to bake at runtime.
- **Runtime bake**: Godot `bake_navigation_mesh()` parses source geometry on the main thread
  (prefer static colliders; visual meshes stall the renderer) and bakes on a thread. Unity
  `BuildNavMesh()` is synchronous; `UpdateNavMesh(data)` is async. Unreal: Navigation Mesh
  Runtime Generation = Dynamic with a NavMeshBoundsVolume over the generation area;
  prebuilt nav inside instanced levels at arbitrary transforms is UNVERIFIED.
- **Check per seed**: path start → exit (`NavigationServer3D.map_get_path` after the map syncs,
  `NavMesh.CalculatePath` = PathComplete, `FindPathToLocationSynchronously`).

## 6. Performance

- Budget ≤ 200 ms per level behind a loading screen: plan ≤ 20, place ≤ 100, navigation ≤ 80 ms
  (working); measured in the engine over the sweep, p50/p95 reported.
- Plan on a worker (`WorkerThreadPool.add_task`, `Task.Run`, `UE::Tasks`): data only, one RNG
  per thread, so results stay deterministic. Preload chunks (`load_threaded_request`,
  `InstantiateAsync` — clone on a worker, Awake on main). Tree changes on the main thread
  (Godot: a subtree built in one thread may be added on the main). Over budget: spread
  instancing across frames.

## 7. Debug views

A prepared overlay toggled by a debug key: seed + version, room ids, edges with locks and
one-ways, critical path, sockets open/capped, spawn markers. Godot: a `CanvasLayer` Control
drawing in `_draw()`, 3D lines via an `ImmediateMesh` resource assigned in the inspector; Unity:
`OnDrawGizmos` + UI Toolkit; Unreal: `DrawDebugLine/String` (non-shipping). Seed from the
command line: `OS.get_cmdline_user_args()`, `Environment.GetCommandLineArgs()`, `FParse::Value`.

## 8. How qa and playtest verify

1. **Sweep**: a test scene/test loops seeds from `tests/procgen/seeds.txt` plus 1..N, generates,
   exports layouts and stats, and saves a top-down capture per seed from a prepared overview
   camera to `production/captures/procgen/<seed>.png`. Godot: `tests/procgen/seed_sweep.tscn`
   run with `project_run`, or headless (`godot --headless -s res://tests/procgen/sweep.gd`;
   headless scripts are allowed under `tests/` and `.kiln/tmp/` only); Unity: a PlayMode test via
   `run_tests`; Unreal: an automation test via `RunTests`.
2. **Checker**: `procgen_check.py "production/procgen/layouts/*.json" --min-path 6 --max-path 14
   --out production/procgen/check.json` — 100% pass; failing seeds appended to `seeds.txt`.
3. **qa-performance**: generation p95 from the sweep stats within budget.
4. **Playtester**: plays the shortest and longest critical path, the most-retried seed and three
   random seeds; checks level metrics (jumps, gaps, sightlines); every bug names its seed.
5. **Verifier**: checker verdict, captures present, regression seeds pass, every
   `kiln:runtime-node` marker justified.
