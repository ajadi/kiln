extends Node
## Kiln input replay (Godot 4.6/4.7): record the input of a session frame by frame, play it back
## exactly, and hash the game state on the way, so a run can be repeated, compared after a change
## and handed to the next session. Copy to `tests/autoplay/input_replay.gd`.
##
##   var rp = load("res://tests/autoplay/input_replay.gd").new()   # kiln:runtime-node test tool
##   rp.actions = PackedStringArray(["move_left", "move_right", "jump"])
##   rp.track = [func(): return hero.global_position, func(): return hero.velocity]
##   root.add_child(rp)
##   rp.record()                  # a human or a scripted session plays...
##   rp.save("res://production/autoplay/replays/level1.json")
##   ...
##   rp.load_file("res://production/autoplay/replays/level1.json"); rp.play()
##   await rp.finished            # then compare rp.hashes with the recording's: rp.first_divergence(other)
##
## Run with `--fixed-fps 60` and one seed (autoplay --seed): with fixed frames the same input
## gives the same state on the same machine, so hashes that differ name the first frame where a
## change altered behaviour. Recording samples the actions once per physics frame, before the
## game's nodes (process_physics_priority -1000), so a replay presses them on the same frames.

signal finished

var actions: PackedStringArray = []
var track: Array = []                  # Callables: the state that must repeat (positions, hp, ...)
var hash_every := 30                   # frames between state hashes
var events: Array = []                 # [frame, action, pressed, strength]
var hashes: Array = []                 # [frame, hash]
var mode := ""
var frame := 0
var _cursor := 0
var _last := {}
var _end_frame := -1


func _ready() -> void:
	process_physics_priority = -1000


func record() -> void:
	mode = "record"
	frame = 0
	events.clear()
	hashes.clear()
	_last.clear()


func play() -> void:
	mode = "play"
	frame = 0
	_cursor = 0
	hashes.clear()
	for a in actions:
		Input.action_release(a)


func stop() -> void:
	if mode == "record":
		_end_frame = frame
		for a in actions:                   # what is still held ends with the recording
			if _last.get(a, false):
				events.append([frame, String(a), false, 0.0])
				_last[a] = false
	mode = ""
	for a in actions:
		Input.action_release(a)
	finished.emit()


func _physics_process(_delta: float) -> void:
	if mode == "":
		return
	if mode == "play" and _end_frame >= 0 and frame >= _end_frame:
		stop()                              # before the game's nodes run this frame, as recorded
		return
	if mode == "play":
		while _cursor < events.size() and int(events[_cursor][0]) <= frame:
			var e: Array = events[_cursor]
			if e[2]:
				Input.action_press(StringName(e[1]), float(e[3]))
			else:
				Input.action_release(StringName(e[1]))
			_cursor += 1
	else:
		for a in actions:
			var pressed := Input.is_action_pressed(a)
			if pressed != _last.get(a, false):
				events.append([frame, String(a), pressed, Input.get_action_strength(a)])
				_last[a] = pressed
	if frame % hash_every == 0:
		hashes.append([frame, state_hash()])
	frame += 1


func state_hash() -> String:
	var parts: PackedStringArray = []
	for getter in track:
		var v = getter.call()
		if v is Vector2 or v is Vector3:
			v = v.snapped(Vector3.ONE * 0.001) if v is Vector3 else v.snapped(Vector2.ONE * 0.001)
		parts.append(var_to_str(v))
	return ";".join(parts).md5_text()


func save(path: String) -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(path.get_base_dir()))
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(JSON.stringify({"format": "kiln-replay/1", "actions": Array(actions),
		"physics_fps": Engine.physics_ticks_per_second, "frames": _end_frame if _end_frame >= 0 else frame,
		"hash_every": hash_every, "events": events, "hashes": hashes}, " "))


func load_file(path: String) -> void:
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	actions = PackedStringArray(data["actions"])
	events = data["events"]
	hash_every = int(data["hash_every"])
	_end_frame = int(data["frames"])
	recorded_hashes = data["hashes"]


var recorded_hashes: Array = []


## The first frame whose state hash differs from `other` (a list of [frame, hash]), or -1.
func first_divergence(other: Array = recorded_hashes) -> int:
	var theirs := {}
	for h in other:
		theirs[int(h[0])] = h[1]
	for h in hashes:
		if theirs.has(int(h[0])) and theirs[int(h[0])] != h[1]:
			return int(h[0])
	return -1
