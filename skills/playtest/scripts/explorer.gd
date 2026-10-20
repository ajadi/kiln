extends RefCounted
## Kiln explorer bot (Godot 4.6/4.7): wander the level toward the least-visited places and
## record where the player can go and where it gets stuck - coverage and stuck heatmaps for an
## autoplay scenario. Copy to `tests/autoplay/explorer.gd`; from a scenario's `_play()`:
##
##   var ex = load("res://tests/autoplay/explorer.gd").new(self,
##       func(): return hero.global_position,
##       {Vector2.LEFT: &"move_left", Vector2.RIGHT: &"move_right",
##        Vector2.UP: &"move_forward", Vector2.DOWN: &"move_back"}, 1.0)   # cell size (m or px)
##   ex.plane = "xz"               # 3D: the ground plane; 2D games keep "xy"
##   ex.jump_action = &"jump"      # optional: tried when moving does not move the player
##   await ex.explore(300.0)       # game seconds
##   ex.save(out_dir + "/explore.json")      # then playtest explore_report.py
##
## Each step holds one direction for `hold_s` toward the neighbouring cell visited least (a
## seeded random step with `epsilon`); a step that moves the player less than `min_move` of a
## cell counts as stuck in that cell - walls are expected, the heatmap shows where stuck counts
## pile up (snags, corners, lips the controller cannot climb). Novelty-seeking exploration finds
## reachability bugs that scripted routes miss (Go-Explore, EA SEED; research 2026-10-19).

var probe                      # the autoplay scenario (autoplay_base.gd): seconds(), press(), release()
var position_of: Callable
var moves: Dictionary          # Vector2 direction -> action
var cell: float
var plane := "xy"
var jump_action: StringName = &""
var hold_s := 0.35
var epsilon := 0.2
var min_move := 0.15
var visits := {}
var stuck := {}
var path: Array = []
var rng := RandomNumberGenerator.new()


func _init(p, getter: Callable, directions: Dictionary, cell_size: float) -> void:
	probe = p
	position_of = getter
	moves = directions
	cell = cell_size
	rng.seed = int(p.get("seed_value")) if p.get("seed_value") != null else 1


func _flat(v) -> Vector2:
	if v is Vector3:
		return Vector2(v.x, v.z) if plane == "xz" else Vector2(v.x, v.y)
	return v


func key_of(v) -> Vector2i:
	var f := _flat(v)
	return Vector2i(floori(f.x / cell), floori(f.y / cell))


func _visits(c: Vector2i) -> int:
	return int(visits.get(c, 0))


func explore(game_seconds: float) -> Dictionary:
	var t := 0.0
	while t < game_seconds:
		var here: Vector2i = key_of(position_of.call())
		visits[here] = _visits(here) + 1
		var dirs: Array = moves.keys()
		var pick: Vector2
		if rng.randf() < epsilon:
			pick = dirs[rng.randi_range(0, dirs.size() - 1)]
		else:
			dirs.sort_custom(func(a, b): return _visits(here + Vector2i(a)) < _visits(here + Vector2i(b)))
			var low := _visits(here + Vector2i(dirs[0]))
			var best := dirs.filter(func(d): return _visits(here + Vector2i(d)) == low)
			pick = best[rng.randi_range(0, best.size() - 1)]
		var before := _flat(position_of.call())
		probe.press(moves[pick])
		await probe.seconds(hold_s)
		probe.release(moves[pick])
		t += hold_s
		var after := _flat(position_of.call())
		if before.distance_to(after) < min_move * cell:
			if jump_action != &"":
				probe.press(moves[pick])
				probe.press(jump_action)
				await probe.seconds(hold_s)
				probe.release(jump_action)
				probe.release(moves[pick])
				t += hold_s
				after = _flat(position_of.call())
			if before.distance_to(after) < min_move * cell:
				stuck[here] = int(stuck.get(here, 0)) + 1
		path.append([snappedf(after.x, 0.01), snappedf(after.y, 0.01)])
	return summary()


func summary() -> Dictionary:
	return {"cells_visited": visits.size(), "stuck_cells": stuck.size(),
		"stuck_events": stuck.values().reduce(func(a, b): return a + b, 0)}


func save(path_out: String) -> void:
	var v := {}
	for c in visits:
		v["%d,%d" % [c.x, c.y]] = visits[c]
	var s := {}
	for c in stuck:
		s["%d,%d" % [c.x, c.y]] = stuck[c]
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path_out.get_base_dir()))
	var f := FileAccess.open(path_out, FileAccess.WRITE)
	f.store_string(JSON.stringify({"format": "kiln-explore/1", "cell": cell, "plane": plane,
		"visits": v, "stuck": s, "path": path, "summary": summary()}, " "))
