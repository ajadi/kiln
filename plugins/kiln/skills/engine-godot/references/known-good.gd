extends CharacterBody3D
## Known-good Godot 4.6/4.7 GDScript: keep it next to new code as the pattern to match. Models
## copy the API of nearby code, and public code leans to Godot 3; this file is all Godot 4.
## Every form here is checked by engine-godot godot_lint.py (no Godot 3 API).

signal landed(fall_speed: float)                # typed signal; emit with landed.emit(x)

@export var move_speed: float = 5.0             # @export, typed: tuned in the inspector
@export var jump_velocity: float = 4.5
@export_range(0.0, 0.3, 0.01) var coyote_time: float = 0.1

@onready var anim: AnimationPlayer = $AnimationPlayer    # @onready, node from the scene
@onready var ray: RayCast3D = $RayCast3D                 # 3D names: RayCast3D, not RayCast

var _since_floor: float = 0.0
var _was_on_floor: bool = true


func _ready() -> void:
	ray.target_position = Vector3.DOWN * 2.0     # target_position, not cast_to
	anim.animation_finished.connect(_on_animation_finished)   # signal.connect(callable)


func _physics_process(delta: float) -> void:
	var gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")
	if not is_on_floor():
		velocity.y -= gravity * delta
		_since_floor += delta
	else:
		_since_floor = 0.0
	if Input.is_action_just_pressed(&"jump") and _since_floor <= coyote_time:
		velocity.y = jump_velocity
		_since_floor = coyote_time + 1.0         # one jump per coyote window, no air jump
	var input := Input.get_vector(&"move_left", &"move_right", &"move_forward", &"move_back")
	var direction := (transform.basis * Vector3(input.x, 0.0, input.y)).normalized()
	velocity.x = direction.x * move_speed
	velocity.z = direction.z * move_speed
	var fall_speed := -velocity.y
	move_and_slide()                             # no arguments; returns bool
	if is_on_floor() and not _was_on_floor:
		landed.emit(fall_speed)
	_was_on_floor = is_on_floor()


func spawn(scene: PackedScene) -> Node3D:
	var node := scene.instantiate() as Node3D     # instantiate(), not instance()
	get_parent().add_child(node)
	return node


func wait_a_frame() -> void:
	await get_tree().process_frame               # await, not yield


func _on_animation_finished(anim_name: StringName) -> void:
	if anim_name == &"land":
		anim.play(&"idle")
