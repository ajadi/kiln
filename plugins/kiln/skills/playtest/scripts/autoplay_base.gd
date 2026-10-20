extends SceneTree
## Kiln autoplay base (Godot 4.6/4.7): plays the game toward objectives and records what a
## playthrough needs. Copy to `tests/autoplay/autoplay_base.gd`; a scenario extends it:
##
##   extends "res://tests/autoplay/autoplay_base.gd"
##   var hero: CharacterBody3D
##   func _setup() -> void:                      # build the world, declare goals
##       var main: Node = load(ProjectSettings.get_setting("application/run/main_scene")).instantiate()
##       root.add_child(main)
##       hero = main.get_node("Hero")
##       add_objective("talk_all_merchants", func(): return main.talked.size() >= 5, 600.0)
##       set_progress(func(): return hero.global_position)     # stuck detection
##   func _play() -> void:                       # drive it: input actions, waits, nav paths
##       for target in route:
##           await walk_to(hero, target, &"move_forward")       # your steering helper
##       await seconds(2.0)
##
## Run (windowed when the user is away, or --headless for logic-only runs):
##   godot --path . -s res://tests/autoplay/run_full.gd -- --seed 7 --out production/autoplay/n1/run_001
##   options: --minutes 15 (wall-clock limit), --stuck-s 8, --shots-every 20 (s, 0 = off),
##            --watch res://scenes/plaza.tscn,... (mtimes into the summary),
##            --viewport msaa_3d=2 (root Viewport property for A/B runs of the same seed)
## Writes <out>/trace.csv (one row per frame: frame time, draw calls, primitives, objects, video
## memory, node and object counts, pipeline compilations, after_shot flag), <out>/shots/*.png,
## <out>/summary.json (seed, scenario, commit, watched mtimes, objectives -> first time reached or
## null, stuck events, hitches, verdict), prints "AUTOPLAY done <verdict>" and exits 0 PASS / 1 FAIL.
## The frame after a screenshot is flagged and its hitch counted apart (a shot costs 30-55 ms and
## the next frame too; g2 row 104). A stop file `.kiln/autoplay-stop` ends the run early (the user
## is back). Mark nodes a scenario creates with `# kiln:runtime-node <reason>`.

var seed_value := 1
var out_dir := "res://production/autoplay/run"
var minutes := 15.0
var stuck_s := 8.0
var shots_every := 20.0
var watch: PackedStringArray = []
var objectives: Dictionary = {}       # name -> {check, timeout_s, t}
var stuck: Array = []
var hitches := 0
var hitches_after_shot := 0
var _headless := false
var _progress: Callable
var _history: Array = []              # [t, value]
var _in_stuck := false
var _trace: FileAccess
var _t0_ms := 0
var _last_us := 0
var _next_shot := 0.0
var _after_shot := false
var _frame_times: Array = []
var _finished := false
var _overrides: Dictionary = {}
var _game_t := 0.0                    # game time (sum of frame deltas): objectives, stuck, shots


func _initialize() -> void:
	Input.use_accumulated_input = false
	var args := OS.get_cmdline_user_args()
	for i in args.size():
		var v: String = args[i + 1] if i + 1 < args.size() else ""
		match args[i]:
			"--seed": seed_value = int(v)
			"--out": out_dir = v
			"--minutes": minutes = float(v)
			"--stuck-s": stuck_s = float(v)
			"--shots-every": shots_every = float(v)
			"--watch": watch = v.split(",", false)
			"--viewport":
				var kv := v.split("=", true, 1)
				if kv.size() == 2:
					_overrides[kv[0]] = str_to_var(kv[1])
	seed(seed_value)
	# headless renders nothing: no shots (each one printed an engine error and skipped the frame's
	# stop and time checks), and frame times are wall-clock noise, not hitches (bug hunt 2026-10-20)
	_headless = DisplayServer.get_name() == "headless"
	if _headless:
		shots_every = 0.0
	var abs_out := ProjectSettings.globalize_path(out_dir) if out_dir.begins_with("res://") else out_dir
	out_dir = abs_out
	DirAccess.make_dir_recursive_absolute(out_dir.path_join("shots"))
	_trace = FileAccess.open(out_dir.path_join("trace.csv"), FileAccess.WRITE)
	_trace.store_line("t,frame_ms,draw_calls,primitives,objects,video_mem,node_count,object_count,pipeline_compilations,after_shot")
	for key in _overrides:
		root.set(key, _overrides[key])
	_t0_ms = Time.get_ticks_msec()
	_next_shot = shots_every
	print("AUTOPLAY start seed=%d" % seed_value)
	_begin.call_deferred()


func _begin() -> void:
	await _setup()
	await _play()
	finish("played")


## Override: build the world, add objectives, set_progress().
func _setup() -> void:
	pass


## Override: drive the game.
func _play() -> void:
	pass


func add_objective(objective: String, check: Callable, timeout_s: float = 600.0) -> void:
	objectives[objective] = {"check": check, "timeout_s": timeout_s, "t": null}


func set_progress(getter: Callable) -> void:
	_progress = getter


## Game time in seconds (with --fixed-fps this runs faster than the wall clock).
func elapsed() -> float:
	return _game_t


func wall_s() -> float:
	return (Time.get_ticks_msec() - _t0_ms) / 1000.0


func seconds(s: float) -> void:
	await create_timer(s).timeout


func press(action: StringName) -> void:
	Input.action_press(action)


func release(action: StringName) -> void:
	Input.action_release(action)


func hold(action: StringName, s: float) -> void:
	Input.action_press(action)
	await seconds(s)
	Input.action_release(action)


## Path on the default 3D navigation map; waits for the first map sync (before it the server
## answers (0,0,0) and prints an error).
func nav_path(from: Vector3, to: Vector3) -> PackedVector3Array:
	var map := root.get_world_3d().navigation_map
	while NavigationServer3D.map_get_iteration_id(map) == 0:
		await physics_frame
	return NavigationServer3D.map_get_path(map, from, to, true)


func _process(delta: float) -> bool:
	if _finished:
		return false
	_game_t += delta
	var t := elapsed()
	var now_us := Time.get_ticks_usec()
	var ms := (now_us - _last_us) / 1000.0 if _last_us else 0.0
	_last_us = now_us
	_record(t, ms)
	for objective in objectives:
		var o: Dictionary = objectives[objective]
		if o["t"] == null and t <= o["timeout_s"] and o["check"].call():
			o["t"] = snappedf(t, 0.01)
	_check_stuck(t)
	if shots_every > 0.0 and t >= _next_shot:
		_next_shot += shots_every
		var tex := root.get_texture()
		if tex:
			var img := tex.get_image()
			if img:
				img.save_png(out_dir.path_join("shots/t%06.1f.png" % t))
				_after_shot = true
	if FileAccess.file_exists("res://.kiln/autoplay-stop"):
		finish("stop file: the user is back")
	elif wall_s() > minutes * 60.0:
		finish("time limit (wall clock)")
	return false


func _record(t: float, ms: float) -> void:
	var comp := 0.0
	for m in [Performance.PIPELINE_COMPILATIONS_CANVAS, Performance.PIPELINE_COMPILATIONS_MESH,
			Performance.PIPELINE_COMPILATIONS_SURFACE, Performance.PIPELINE_COMPILATIONS_DRAW,
			Performance.PIPELINE_COMPILATIONS_SPECIALIZATION]:
		comp += Performance.get_monitor(m)
	var flagged := _after_shot
	_after_shot = false
	if ms > 0.0 and not _headless:
		_frame_times.append(ms)
		if _frame_times.size() > 120:
			_frame_times.pop_front()
		var sorted := _frame_times.duplicate()
		sorted.sort()
		var median: float = sorted[sorted.size() / 2]
		if ms > 50.0 or (sorted.size() > 30 and ms > 2.0 * median):
			if flagged:
				hitches_after_shot += 1
			else:
				hitches += 1
	_trace.store_line("%.3f,%.3f,%d,%d,%d,%d,%d,%d,%d,%d" % [t, ms,
		Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
		Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME),
		Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME),
		Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED),
		Performance.get_monitor(Performance.OBJECT_NODE_COUNT),
		Performance.get_monitor(Performance.OBJECT_COUNT), comp, 1 if flagged else 0])


func _check_stuck(t: float) -> void:
	if not _progress.is_valid():
		return
	var v = _progress.call()
	_history.append([t, v])
	while _history.size() > 2 and _history[1][0] <= t - stuck_s:
		_history.pop_front()
	if _history[0][0] > t - stuck_s:
		return
	var moved := 0.0
	var first = _history[0][1]
	for h in _history:
		moved = maxf(moved, _distance(first, h[1]))
	if moved < 0.05:
		if not _in_stuck:
			_in_stuck = true
			stuck.append({"t": snappedf(t, 0.1), "where": _plain(v)})
	else:
		_in_stuck = false


func _distance(a, b) -> float:
	if a is Vector3 or a is Vector2:
		return a.distance_to(b)
	return absf(float(a) - float(b))


func finish(reason: String) -> void:
	if _finished:
		return
	_finished = true
	_trace.close()
	var reached := {}
	var all_reached := true
	for objective in objectives:
		reached[objective] = objectives[objective]["t"]
		all_reached = all_reached and objectives[objective]["t"] != null
	var verdict := "PASS" if all_reached and stuck.is_empty() else "FAIL"
	var mtimes := {}
	for path in watch:
		mtimes[path] = FileAccess.get_modified_time(path)
	var summary := {"seed": seed_value, "scenario": get_script().resource_path.get_file(),
		"commit": _commit(), "watched_mtimes": mtimes, "reason": reason,
		"objectives": reached, "stuck": stuck,
		"hitches": null if _headless else hitches,          # not measured headless
		"hitches_after_shot": null if _headless else hitches_after_shot,
		"game_s": snappedf(elapsed(), 0.01),
		"wall_s": wall_s(),
		"viewport_overrides": _overrides, "headless": DisplayServer.get_name() == "headless",
		"verdict": verdict}
	var f := FileAccess.open(out_dir.path_join("summary.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify(summary, "  "))
	f.close()
	print("AUTOPLAY done %s" % verdict)
	quit(0 if verdict == "PASS" else 1)


func _commit() -> String:
	var head := FileAccess.get_file_as_string("res://.git/HEAD").strip_edges()
	if head.begins_with("ref: "):
		return FileAccess.get_file_as_string("res://.git/" + head.substr(5)).strip_edges()
	return head


func _plain(v):
	if v is Vector3:
		return [snappedf(v.x, 0.01), snappedf(v.y, 0.01), snappedf(v.z, 0.01)]
	if v is Vector2:
		return [snappedf(v.x, 0.01), snappedf(v.y, 0.01)]
	return v
