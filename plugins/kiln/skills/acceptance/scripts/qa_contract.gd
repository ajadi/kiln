extends "res://tests/probes/probe_base.gd"
## Kiln scene QA contract (Godot 4.6/4.7): a scene lists named QA states, one command records
## them all. Copy this file to `tests/qa/qa_contract.gd` and probe_base.gd to
## `tests/probes/probe_base.gd` once; each scene gets a contract that extends this one:
##
##   extends "res://tests/qa/qa_contract.gd"
##   func scene_path() -> String:
##       return "res://scenes/plaza.tscn"
##   func states() -> Array:
##       return [
##           {"name": "hud_longest", "kind": "ui",
##            "apply": func(s): s.get_node("HUD/Gold").text = "999 999 999"},
##           {"name": "torch_fire", "kind": "anchor", "frames": 60, "tolerance": 0.05,
##            "track": {"emitter": "Hero/Torch/Fire", "holder": "Hero/Torch/Tip"}},
##           {"name": "idle_loop", "kind": "loop", "frames": 120, "root": "hips",
##            "apply": func(s): s.get_node("Hero/AnimationPlayer").play("idle"),
##            "track": {"hips": "Hero/Skeleton3D:hips", "head": "Hero/Skeleton3D:head", ...}},
##           {"name": "rain_on", "kind": "frames", "frames": 30, "check": "anim", "off": "rain_off",
##            "apply": func(s): s.get_node("Rain").emitting = true},
##       ]
##
## Kinds and what `qa_contract.py report` runs on them:
##   ui          the visible Controls (path, type, text, rect, text width, parent rect): overflow
##               out of the control or its container, ui_check.py layout (overlaps, safe area).
##   anchor      `track` {emitter, holder} per frame: distance <= `tolerance` (m in 3D, px in 2D).
##   loop        `track` joints per frame: analyze.py rigid (K01).
##   transition  `track` joints per frame across a transition: analyze.py pops.
##   attack      `track` with the weapon's two ends and the targets: analyze.py hits
##               (`segment` "hilt,tip", `targets` "name@impact_frame,...", `radius`).
##   frames      PNG per frame (needs a window: not headless): frames.py anim (`check` "anim",
##               `off` = the matching OFF state) or ramp (`check` "ramp", `steady` = the held state).
## A track spec is a node path from the scene root (Node3D, Node2D: global position; Control:
## its centre) or "SkeletonPath:bone" for a bone. Each state gets a fresh instance of the scene;
## `apply(scene)` sets it up and may await. Output: <out>/<state>/ files and <out>/qa_run.json.
##
## Run: python qa_contract.py run --contract res://tests/qa/plaza_qa.gd (acceptance skill), or
##   godot [--headless] --fixed-fps 60 --path . -s res://tests/qa/plaza_qa.gd -- --out <dir>

var run_dir := ""


## Override: the scene the states run on.
func scene_path() -> String:
	return ""


## Override: the named QA states (see above).
func states() -> Array:
	return []


func _run() -> void:
	run_dir = _qa_dir()
	if scene_path() == "" or not ResourceLoader.exists(scene_path()):
		note("scene_path() missing or not found: %s" % scene_path())
		return
	var listed := []
	for state in states():
		var entry: Dictionary = await _record(state)
		listed.append(entry)
		check("recorded-" + String(state.get("name", "?")), entry.get("recorded", false), "==", true,
			"qa contract")
	var f := FileAccess.open(run_dir.path_join("qa_run.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify({"contract": probe_name, "scene": scene_path(),
		"headless": headless, "fps": Engine.physics_ticks_per_second, "states": listed}, "  "))
	f.close()


func _qa_dir() -> String:
	var dir := out_dir
	if dir == "":
		dir = OS.get_environment("KILN_PROBE_DIR")
	if dir == "":
		dir = "res://production/qa/%s" % probe_name
	var abs_dir := ProjectSettings.globalize_path(dir) if dir.begins_with("res://") else dir
	DirAccess.make_dir_recursive_absolute(abs_dir)
	return abs_dir


func _record(state: Dictionary) -> Dictionary:
	var name := String(state.get("name", "state"))
	var kind := String(state.get("kind", "ui"))
	var dir := run_dir.path_join(name)
	DirAccess.make_dir_recursive_absolute(dir)
	var entry := {"name": name, "kind": kind, "dir": dir, "recorded": true}
	for key in state:
		if key != "apply":
			entry[key] = _plain(state[key])
	var scene: Node = load(scene_path()).instantiate()
	root.add_child(scene)
	await process_frame
	if state.has("apply"):
		await state["apply"].call(scene)
	await process_frame
	await process_frame          # containers sort and labels resize on the next frame
	var frames := int(state.get("frames", 60))
	match kind:
		"ui":
			var vp := root.get_visible_rect().size
			entry["viewport"] = [vp.x, vp.y]
			_save(dir.path_join("elements.json"), {"elements": _ui(scene)})
		"anchor", "loop", "transition", "attack":
			var track: Dictionary = state.get("track", {})
			var samples := {}
			for probe in track:
				samples[probe] = []
			var ticks := []
			for i in frames:
				for probe in track:
					samples[probe].append(_pos(scene, String(track[probe])))
				ticks.append(i)
				await process_frame
			_save(dir.path_join("data.json"), {"format": "kiln-probe/2",
				"physics_ticks_per_second": Engine.physics_ticks_per_second, "ticks": ticks,
				"samples": samples})
		"frames":
			if headless:
				entry["recorded"] = false
				note("%s: frames need a window (run without --headless)" % name)
			else:
				for i in frames:
					await RenderingServer.frame_post_draw
					root.get_texture().get_image().save_png(dir.path_join("f%03d.png" % i))
		_:
			entry["recorded"] = false
			note("%s: unknown kind %s" % [name, kind])
	scene.queue_free()
	await process_frame
	return entry


func _pos(scene: Node, spec: String) -> Array:
	var parts := spec.split(":")
	var n := scene.get_node_or_null(NodePath(parts[0]))
	if n == null:
		return []
	if parts.size() > 1 and n is Skeleton3D:
		var bone: int = n.find_bone(parts[1])
		if bone < 0:
			return []
		var t: Transform3D = n.global_transform * n.get_bone_global_pose(bone)
		return [t.origin.x, t.origin.y, t.origin.z]
	if n is Node3D:
		var p: Vector3 = n.global_position
		return [p.x, p.y, p.z]
	if n is Node2D:
		var q: Vector2 = n.global_position
		return [q.x, q.y]
	if n is Control:
		var c: Vector2 = n.global_position + n.size / 2.0
		return [c.x, c.y]
	return []


func _ui(scene: Node) -> Array:
	var out := []
	var stack: Array = [scene]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		for c in n.get_children():
			stack.append(c)
		if not (n is Control) or not n.is_visible_in_tree():
			continue
		var r: Rect2 = n.get_global_rect()
		var e := {"path": String(scene.get_path_to(n)), "type": n.get_class(), "visible": true,
			"disabled": bool(n.get("disabled")) if "disabled" in n else false,
			"global_rect": {"position": {"x": r.position.x, "y": r.position.y},
				"size": {"x": r.size.x, "y": r.size.y}}}
		if "text" in n and n.get("text") is String:
			var text: String = n.get("text")
			e["text"] = text
			var wraps := "autowrap_mode" in n and int(n.get("autowrap_mode")) != 0
			e["autowrap"] = wraps
			if not wraps and text != "":
				var font: Font = n.get_theme_font("font")
				var fsize: int = n.get_theme_font_size("font_size")
				e["text_width"] = font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, fsize).x
		var p := n.get_parent()
		if p is Control:
			var pr: Rect2 = p.get_global_rect()
			e["parent_rect"] = [pr.position.x, pr.position.y, pr.size.x, pr.size.y]
		out.append(e)
	return out


func _save(path: String, data) -> void:
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(JSON.stringify(data, "  "))
	f.close()
