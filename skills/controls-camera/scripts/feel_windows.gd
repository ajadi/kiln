extends RefCounted
## Kiln feel windows (Godot 4.6/4.7): measure forgiveness windows and input latency in physics
## frames from a headless probe, so feel constants are tested values, not comments.
## Copy to `tests/probes/feel_windows.gd` next to acceptance `probe_base.gd`; use it from a probe:
##
##   extends "res://tests/probes/probe_base.gd"
##   const Feel = preload("res://tests/probes/feel_windows.gd")
##   func _run() -> void:
##       var fw = Feel.new(self)
##       var feel: Resource = load("res://data/feel.tres")          # feel_constants.gd
##       # coyote: walk off the ledge, press jump k frames later; did the jump start?
##       var coyote := await fw.window_after(_put_on_ledge, func(): return not hero.is_on_floor(),
##           &"jump", func(): return hero.velocity.y < -50.0)
##       check("coyote", coyote, "~", fw.frames(feel.coyote_time), "data/feel.tres", 1)
##       # buffer: press jump k frames before landing; does it jump on landing?
##       var buffer := await fw.window_before(_drop_from_height, func(): return hero.is_on_floor(),
##           &"jump", func(): return hero.velocity.y < -50.0)
##       check("buffer", buffer, "~", fw.frames(feel.jump_buffer), "data/feel.tres", 1)
##       # latency: frames from each press to the first response; jitter = max - min
##       var lat: Dictionary = await fw.latency(_stand, &"move_right",
##           func(): return hero.velocity.x > 0.0, 20)
##       check("latency_max", lat.max, "<=", 2, "feel-numbers: next physics tick")
##       check("latency_jitter", lat.jitter, "<=", 1, "research: jitter hurts, constant latency less")
##
## A window is how many frames the action still works: pressing it k = 0, 1, 2, ... frames after
## (or before) the event, the count of k that work in a row (0 = never). Each k is a fresh run from `reset`, so one
## attempt never leaks into the next. Run with `--fixed-fps 60` (1 frame = 1 physics tick).

var probe        # the running probe (acceptance probe_base.gd): ticks(), press(), release()


func _init(p) -> void:
	probe = p


func frames(seconds: float) -> int:
	return int(round(seconds * Engine.physics_ticks_per_second))


func _wait_until(cond: Callable, limit: int) -> int:
	## Frames until cond() is true (0 = already), or -1 after `limit` frames.
	for i in limit:
		if cond.call():
			return i
		await probe.ticks(1)
	return limit if cond.call() else -1


func _attempt_after(reset: Callable, trigger: Callable, action: StringName, success: Callable,
		k: int, settle: int) -> bool:
	await reset.call()
	if await _wait_until(trigger, 600) < 0:
		return false
	await probe.ticks(k)
	probe.press(action)
	var ok := false
	for i in settle:
		await probe.ticks(1)
		if i == 0:
			probe.release(action)
		if success.call():
			ok = true
			break
	probe.release(action)
	return ok


func window_after(reset: Callable, trigger: Callable, action: StringName, success: Callable,
		max_frames: int = 30, settle: int = 6) -> int:
	## Frames (count of k from 0) for which pressing `action` 0..k frames after `trigger` first holds still works
	## (coyote time: trigger = left the ground, success = a jump started).
	var last := -1
	for k in max_frames + 1:
		if await _attempt_after(reset, trigger, action, success, k, settle):
			last = k
		else:
			break
	return last + 1


func window_before(reset: Callable, event: Callable, action: StringName, success: Callable,
		max_frames: int = 30, settle: int = 6) -> int:
	## Frames (count of k from 0) for which pressing `action` k frames before `event` (and releasing it) still acts
	## when the event comes (jump buffer: event = landed, success = a jump started).
	await reset.call()
	var lead := await _wait_until(event, 600)
	if lead < 0:
		return -1
	var last := -1
	for k in range(0, mini(max_frames, lead) + 1):
		await reset.call()
		await probe.ticks(lead - k)
		probe.press(action)
		await probe.ticks(1)
		probe.release(action)
		var ok := false
		for i in k + settle:
			if success.call():
				ok = true
				break
			await probe.ticks(1)
		if ok:
			last = k
		else:
			break
	return last + 1


func latency(reset: Callable, action: StringName, responded: Callable, presses: int = 20,
		gap: int = 7, limit: int = 30) -> Dictionary:
	## Frames from each press to the first response; constant latency is tolerated far better
	## than jitter (latency research), so max - min is reported apart. The press lands on a varied
	## frame (gap + i % 3) so a response tied to a fixed cadence shows up as jitter.
	var samples: Array = []
	for i in presses:
		await reset.call()
		await probe.ticks(gap + i % 3)
		probe.press(action)
		var n := await _wait_until(responded, limit)
		probe.release(action)
		samples.append(n)
	var valid := samples.filter(func(s): return s >= 0)
	if valid.is_empty():
		return {"samples": samples, "min": -1, "max": -1, "mean": -1.0, "jitter": -1, "missed": presses}
	var lo: int = valid.min()
	var hi: int = valid.max()
	var total := 0
	for s in valid:
		total += s
	return {"samples": samples, "min": lo, "max": hi, "mean": float(total) / valid.size(),
			"jitter": hi - lo, "missed": presses - valid.size()}
