# Godot 3 habits that break Godot 4.6/4.7 code

Language models mix Godot 3 and 4 APIs. Check this table before writing GDScript; confirm
anything not listed with `api_manage` in the running editor. Sources: the engine's 3→4 converter
(`editor/project_upgrade/renames_map_3_to_4.cpp`), the upgrade guide, class reference.

| Wrong (Godot 3 / habit) | Right (Godot 4) |
|---|---|
| `yield(obj, "sig")` | `await obj.sig` |
| `yield(get_tree(), "idle_frame")` | `await get_tree().process_frame` |
| `KinematicBody` | `CharacterBody3D` |
| `velocity = move_and_slide(v, Vector3.UP)` | set `velocity`, `up_direction`; `move_and_slide()` returns bool |
| `move_and_slide_with_snap(v, snap)` | `floor_snap_length` (float) / `apply_floor_snap()` |
| `export(float) var x` | `@export var x: float` |
| `onready var` / `tool` | `@onready` / `@tool` |
| `setget s, g` | `var x: T: set = s, get = g` |
| `connect("sig", self, "_m", [a])` | `sig.connect(_m.bind(a))` |
| `emit_signal("sig", a)` | `sig.emit(a)` |
| `.foo()` / `_init().(a)` | `super.foo()` / `super(a)` |
| parent `_ready()` runs automatically in overrides | call `super()` explicitly |
| `scene.instance()` | `scene.instantiate()` |
| Tween node + `interpolate_property` + `start()` | `create_tween().tween_property(...)`; `Tween.new()` is invalid; tweens start immediately and are not reusable |
| `rand_range` + `randomize()` | `randf_range` / `randi_range`; seeding is automatic |
| `deg2rad`, `stepify`, `range_lerp`, `str2var` | `deg_to_rad`, `snapped`, `remap`, `str_to_var` |
| `to_json` / `parse_json` | `JSON.stringify` / `JSON.parse_string` |
| `File`, `Directory` | `FileAccess.open()`, `DirAccess` |
| `OS.get_ticks_msec()` | `Time.get_ticks_msec()` |
| `change_scene(path)` | `change_scene_to_file(path)` / `change_scene_to_packed` |
| `Spatial`, `.translation`, `Position3D`, `Transform`, `Quat` | `Node3D`, `.position`, `Marker3D`, `Transform3D`, `Quaternion` |
| `get_world().direct_space_state.intersect_ray(a, b, [self])` | `get_world_3d().direct_space_state.intersect_ray(PhysicsRayQueryParameters3D.create(a, b, mask, [get_rid()]))` in `_physics_process` |
| `RayCast.cast_to` | `RayCast3D.target_position` |
| `PoolStringArray`, `PoolVector3Array` | `PackedStringArray`, `PackedVector3Array` |
| `NavigationMeshInstance`, `set_target_location` | `NavigationRegion3D`, `target_position` |
| `GIProbe`, `BakedLightmap` | `VoxelGI`, `LightmapGI` |
| `arr.empty()` | `arr.is_empty()` |
| `ResourceLoader.load_interactive` | `ResourceLoader.load_threaded_request` |
| `call_group()` assumed deferred | immediate in 4; `call_group_flags(SceneTree.GROUP_CALL_DEFERRED, …)` |
| `event.relative` for captured mouse look | `event.screen_relative` |
| editing a loaded `.tres` at runtime | shared by all users of it: `duplicate()` / `resource_local_to_scene` |
| `Engine.editor_hint` | `Engine.is_editor_hint()` |
| `SkeletonIK3D` | `TwoBoneIK3D` / `FABRIK3D` / `CCDIK3D` (SkeletonModifier3D family, 4.6+) |
| `physical_bones_start_simulation()` on Skeleton3D | on `PhysicalBoneSimulator3D` (4.3+) |
