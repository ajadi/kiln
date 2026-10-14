extends Node
## Kiln probe recorder — samples values inside the running game and dumps them to JSON.
## Acceptance roles attach it at runtime through the Godot AI MCP game eval, e.g.:
##
##   var rec = load("res://tests/probes/recorder.gd").new()
##   get_tree().root.add_child(rec)
##   var hero = get_tree().current_scene.get_node("Hero")
##   rec.add_probe("hero_pos", func(): return hero.global_position)       # every physics tick
##   rec.add_probe("hero_vel", func(): return hero.velocity)
##   rec.add_frame_probe("draw_calls", func(): return Performance.get_monitor(
##       Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME))                   # every rendered frame
##   rec.start(600)        # 600 physics ticks = 10 s at 60 Hz
##   ... drive input with game_manage / Input.action_press ...
##   rec.dump("res://.kiln/tmp/probe_hero.json")   (after rec.done is true)
##
## Polling through MCP every frame aliases (a round trip is slower than a physics tick), so the
## sampling happens here and is pulled once. The file lives in tests/probes, so it is exempt from
## the scene-first rule; it adds a throwaway node only while a probe runs and changes nothing in
## the game (it only turns on render-time measurement for the root viewport).
##
## Dump format (format "kiln-probe/2"; keys of format 1 kept, so old readers still work):
##   physics_ticks_per_second  int     Engine.physics_ticks_per_second
##   ticks                     [int]   Engine.get_physics_frames() at each physics sample
##   samples                   {name: [value per physics tick]}  (Vector3 -> [x,y,z], NaN -> null)
##   frame_ms                  [float] wall-clock time between consecutive rendered frames, ms,
##                                     one entry per frame while recording. (Format 1 wrote
##                                     Performance.TIME_PROCESS once per tick; that monitor is the
##                                     max process+draw time of the last second, updated once a
##                                     second, so it hid hitches.)
##   frames                    [int]   Engine.get_process_frames() for each frame_ms entry
##   frame_tick                [int]   physics tick count at each frame (aligns frames to ticks)
##   cpu_render_ms             [float] RenderingServer CPU render time of the root viewport +
##                                     frame setup, ms (0 when unavailable)
##   gpu_ms                    [float] RenderingServer GPU time of the root viewport, ms (0 when
##                                     unavailable, e.g. the first frames or unsupported drivers)
##   frame_samples             {name: [value per frame]} from add_frame_probe
##   time_scale, max_fps, vsync_mode   run conditions to report next to the numbers

var probes: Dictionary = {}        # name -> Callable, sampled every physics tick
var samples: Dictionary = {}       # name -> Array
var frame_probes: Dictionary = {}  # name -> Callable, sampled every rendered frame
var frame_samples: Dictionary = {} # name -> Array
var ticks: Array[int] = []
var frame_ms: Array[float] = []
var frames: Array[int] = []
var frame_tick: Array[int] = []
var cpu_render_ms: Array[float] = []
var gpu_ms: Array[float] = []
var recording := false
var done := false
var _left := 0
var _last_usec := 0
var _viewport_rid := RID()


func add_probe(probe_name: String, getter: Callable) -> void:
	probes[probe_name] = getter
	samples[probe_name] = []


func add_frame_probe(probe_name: String, getter: Callable) -> void:
	frame_probes[probe_name] = getter
	frame_samples[probe_name] = []


func start(tick_count: int = 600) -> void:
	for key in samples.keys():
		samples[key].clear()
	for key in frame_samples.keys():
		frame_samples[key].clear()
	for arr in [ticks, frame_ms, frames, frame_tick, cpu_render_ms, gpu_ms]:
		arr.clear()
	_viewport_rid = get_viewport().get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(_viewport_rid, true)
	_last_usec = 0
	_left = tick_count
	recording = true
	done = false


func stop() -> void:
	recording = false
	done = true


func _physics_process(_delta: float) -> void:
	if not recording:
		return
	ticks.append(Engine.get_physics_frames())
	for key in probes.keys():
		samples[key].append(_plain(probes[key].call()))
	_left -= 1
	if _left <= 0:
		stop()


func _process(_delta: float) -> void:
	# delta is scaled by Engine.time_scale and may be smoothed; frame time is measured directly.
	var now := Time.get_ticks_usec()
	if not recording:
		_last_usec = 0
		return
	if _last_usec != 0:
		frame_ms.append((now - _last_usec) / 1000.0)
		frames.append(Engine.get_process_frames())
		frame_tick.append(Engine.get_physics_frames())
		cpu_render_ms.append(RenderingServer.viewport_get_measured_render_time_cpu(_viewport_rid)
				+ RenderingServer.get_frame_setup_time_cpu())
		gpu_ms.append(RenderingServer.viewport_get_measured_render_time_gpu(_viewport_rid))
		for key in frame_probes.keys():
			frame_samples[key].append(_plain(frame_probes[key].call()))
	_last_usec = now


func _plain(value: Variant) -> Variant:
	match typeof(value):
		TYPE_VECTOR3, TYPE_VECTOR3I:
			return [_num(value.x), _num(value.y), _num(value.z)]
		TYPE_VECTOR2, TYPE_VECTOR2I:
			return [_num(value.x), _num(value.y)]
		TYPE_QUATERNION:
			return [_num(value.x), _num(value.y), _num(value.z), _num(value.w)]
		TYPE_TRANSFORM3D:
			return [_num(value.origin.x), _num(value.origin.y), _num(value.origin.z)]
		TYPE_TRANSFORM2D:
			return [_num(value.origin.x), _num(value.origin.y)]
		TYPE_COLOR:
			return [_num(value.r), _num(value.g), _num(value.b), _num(value.a)]
		TYPE_FLOAT:
			return _num(value)
		TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_STRING, TYPE_STRING_NAME:
			return value
		_:
			return str(value)


func _num(x: float) -> Variant:
	return null if is_nan(x) or is_inf(x) else x


func dump(path: String) -> String:
	var out := {
		"format": "kiln-probe/2",
		"engine": "godot",
		"physics_ticks_per_second": Engine.physics_ticks_per_second,
		"ticks": ticks,
		"samples": samples,
		"frame_ms": frame_ms,
		"frames": frames,
		"frame_tick": frame_tick,
		"cpu_render_ms": cpu_render_ms,
		"gpu_ms": gpu_ms,
		"frame_samples": frame_samples,
		"time_scale": Engine.time_scale,
		"max_fps": Engine.max_fps,
		"vsync_mode": DisplayServer.window_get_vsync_mode(),
	}
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path).get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return "error: cannot write " + path
	file.store_string(JSON.stringify(out))
	file.close()
	return ProjectSettings.globalize_path(path)
