extends SceneTree
## Kiln headless probe base (Godot 4.6/4.7). Copy to `tests/probes/probe_base.gd` once; each probe
## extends it and overrides `_run()`:
##
##   extends "res://tests/probes/probe_base.gd"
##   func _run() -> void:
##       var level: Node = load("res://scenes/plaza.tscn").instantiate()
##       root.add_child(level)
##       await ticks(2)
##       var hero: CharacterBody3D = level.get_node("Hero")
##       press("move_forward")
##       await ticks(120)
##       release("move_forward")
##       check("walk-1", hero.velocity.length(), ">=", 3.5, "GAME.md move speed")
##
## Run (allowed by the guard for scripts under tests/ or .kiln/tmp/):
##   godot --headless --fixed-fps 60 --path . -s res://tests/probes/probe_walk.gd -- --task TASK-017
##
## What it fixes (g2 reports):
## - `--fixed-fps 60`: 1 frame = 1 physics tick = 1/60 s, runs ~100x real time; scripted input
##   needs `Input.use_accumulated_input = false` (set here) or presses merge (row 30).
## - A script error inside `_run` stops the coroutine and `quit()` never comes: the console
##   process hung until the tool timeout. The wall-clock watchdog writes NOT ASSESSED and exits 2
##   (row 151).
## - Results go to `production/captures/<task>/` when the probe names its task (`--task` or
##   `task_id`), else to `.kiln/tmp/`, or to `KILN_PROBE_DIR` / `--out` (row 143).
## - Headless has no real renderer, GPU timing or audio device: `Performance` TIME_* monitors read
##   0 (rows 82, 137) - time code with `time_usec()`; draw calls read 0 (row 103); the Dummy audio
##   driver mixes in real time while `--fixed-fps` runs faster, so audio time is not game time
##   (row 109) - use `pace_realtime()` per frame when audio timing matters; sounds still playing
##   at quit are reported as leaked ObjectDB instances (row 123) - in headless runs count play
##   requests instead of playing (`headless` is true here).
## Output: JSON {probe, task, verdict PASS|FAIL|NOT ASSESSED, rows [{id, value, op, threshold,
## source, verdict}], notes, wall_s}; prints `PROBE <name> <verdict> -> <file>`; exit 0 / 1 / 2.

var probe_name := ""
var task_id := ""
var out_dir := ""
var watchdog_s := 120.0
var headless := false
var rows: Array = []
var notes: Array = []
var _finished := false
var _start_ms := 0
var _pace_origin_us := 0
var _pace_frame := 0
var _errors := _ErrorCounter.new()
var _tick_end: Node


## Script errors while the probe runs (Godot 4.5+ Logger). A script error ends `_run` early, and
## the rows it had written so far would read PASS (bug hunt 2026-10-20), so any script error
## makes the verdict NOT ASSESSED.
class _ErrorCounter extends Logger:
	var script_errors: Array = []
	var mutex := Mutex.new()

	func _log_error(function: String, file: String, line: int, code: String, rationale: String,
			_editor_notify: bool, error_type: int, _script_backtraces: Array) -> void:
		if error_type == ERROR_TYPE_SCRIPT:
			mutex.lock()
			script_errors.append("%s:%d %s: %s" % [file.get_file(), line, function,
				rationale if rationale != "" else code])
			mutex.unlock()


func _initialize() -> void:
	OS.add_logger(_errors)
	Input.use_accumulated_input = false
	headless = DisplayServer.get_name() == "headless"
	_start_ms = Time.get_ticks_msec()
	probe_name = get_script().resource_path.get_file().get_basename()
	var args := OS.get_cmdline_user_args()
	for i in args.size():
		if args[i] == "--task" and i + 1 < args.size():
			task_id = args[i + 1]
		elif args[i] == "--out" and i + 1 < args.size():
			out_dir = args[i + 1]
		elif args[i] == "--watchdog" and i + 1 < args.size():
			watchdog_s = float(args[i + 1])
	_begin.call_deferred()


func _begin() -> void:
	_tick_end = _TickEnd.new()  # kiln:runtime-node probe timing helper
	root.add_child(_tick_end)
	await _run()
	finish()


## Runs last in every physics tick. `ticks()` waits for it, so a probe resumes after the tick's
## nodes have run, and a press made then is seen by the next tick. Godot 4.7 shows a press made
## inside a tick (as after `await physics_frame`, before the nodes) to is_action_just_pressed one
## tick late, which moved every measured window by a frame (bug hunt 2026-10-20, checked live).
class _TickEnd extends Node:
	signal tick_done

	func _init() -> void:
		process_physics_priority = 2147483647
		process_mode = Node.PROCESS_MODE_ALWAYS

	func _physics_process(_delta: float) -> void:
		tick_done.emit()


## Override in the probe. May await (ticks(), process_frame, timers).
func _run() -> void:
	note("probe_base: _run() not overridden")


func _process(_delta: float) -> bool:
	# Wall clock, not game time: --fixed-fps runs game time far faster than real time.
	if not _finished and (Time.get_ticks_msec() - _start_ms) / 1000.0 > watchdog_s:
		note("watchdog: no finish() after %.0f s wall time (script error in _run, or a wait that never ends)" % watchdog_s)
		_write("NOT ASSESSED")
		quit(2)
	return false


## Wait for n whole physics ticks: returns after the n-th tick's nodes ran (state is that tick's
## result); press() then lands on the next tick.
func ticks(n: int = 1) -> void:
	for i in n:
		await _tick_end.tick_done


func press(action: StringName, strength: float = 1.0) -> void:
	Input.action_press(action, strength)


func release(action: StringName) -> void:
	Input.action_release(action)


func tap(action: StringName, hold_ticks: int = 1) -> void:
	Input.action_press(action)
	await ticks(hold_ticks)
	Input.action_release(action)


## Microseconds one call takes (headless CPU budgets: the Performance TIME_* monitors read 0).
func time_usec(work: Callable, repeats: int = 1) -> float:
	var t0 := Time.get_ticks_usec()
	for i in repeats:
		work.call()
	return float(Time.get_ticks_usec() - t0) / repeats


## Sleep until wall time catches up with game frame `_pace_frame` at `fps`: keeps the Dummy
## audio driver (real time) and game time in step for audio probes.
func pace_realtime(fps: int = 60) -> void:
	if _pace_origin_us == 0:
		_pace_origin_us = Time.get_ticks_usec()
	_pace_frame += 1
	var due := _pace_origin_us + int(_pace_frame * 1000000.0 / fps)
	var now := Time.get_ticks_usec()
	if due > now:
		OS.delay_usec(due - now)


func note(text: String) -> void:
	notes.append(text)


## One acceptance row. op: "<", "<=", ">", ">=", "==", "!=", or "~" (abs(value - threshold) <=
## tolerance; the distance for vectors). A row whose value comes from the formula under test cannot fail: measure the
## world, not the implementation.
func check(id: String, value, op: String, threshold, source: String = "", tolerance: float = 0.0) -> bool:
	var ok := false
	match op:
		"<": ok = value < threshold
		"<=": ok = value <= threshold
		">": ok = value > threshold
		">=": ok = value >= threshold
		"==": ok = value == threshold
		"!=": ok = value != threshold
		"~":
			if (value is Vector2 or value is Vector3) and typeof(value) == typeof(threshold):
				ok = value.distance_to(threshold) <= tolerance
			else:
				ok = absf(float(value) - float(threshold)) <= tolerance
		_: note("unknown op %s in %s" % [op, id])
	rows.append({"id": id, "value": _plain(value), "op": op, "threshold": _plain(threshold),
		"source": source, "verdict": "PASS" if ok else "FAIL"})
	return ok


func finish() -> void:
	if _finished:
		return
	if rows.is_empty():
		note("no check rows: _run ended before its checks (script error above, or no check() calls)")
	for e in _errors.script_errors:
		note("script error: " + e)
	var failed := rows.any(func(r): return r["verdict"] == "FAIL")
	var verdict := "NOT ASSESSED" if rows.is_empty() or not _errors.script_errors.is_empty() \
		else ("FAIL" if failed else "PASS")
	_write(verdict)
	quit(0 if verdict == "PASS" else (1 if verdict == "FAIL" else 2))


func _write(verdict: String) -> void:
	_finished = true
	var dir := out_dir
	if dir == "":
		dir = OS.get_environment("KILN_PROBE_DIR")
	if dir == "":
		dir = "res://production/captures/%s" % task_id if task_id != "" else "res://.kiln/tmp"
	var abs_dir := ProjectSettings.globalize_path(dir) if dir.begins_with("res://") else dir
	DirAccess.make_dir_recursive_absolute(abs_dir)
	var path := abs_dir.path_join(probe_name + ".json")
	var data := {"probe": probe_name, "task": task_id, "verdict": verdict, "rows": rows,
		"notes": notes, "wall_s": (Time.get_ticks_msec() - _start_ms) / 1000.0,
		"physics_ticks_per_second": Engine.physics_ticks_per_second, "headless": headless}
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(data, "  "))
		f.close()
	print("PROBE %s %s -> %s" % [probe_name, verdict, path])


func _plain(v):
	if v is Vector2 or v is Vector3:
		var out := []
		for i in (2 if v is Vector2 else 3):
			out.append(v[i])
		return out
	if v is float and (is_nan(v) or is_inf(v)):
		return null
	return v
