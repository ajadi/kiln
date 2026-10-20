extends Resource
## Kiln feel constants (Godot 4.6/4.7): one resource the controller reads and the feel probe
## tests (feel_windows.gd), so a tuned value is a named number with its source, never a literal
## buried in a script. Copy to `scripts/feel/feel_constants.gd`, create `data/feel.tres` from it
## in the editor (resource_manage), and read it with `@export var feel: Resource`.
## Defaults: Celeste Player.cs (github.com/NoelFB/Celeste, read 2026-10-19) where it states them;
## the jump buffer is a commonly quoted value, not found in a primary source (working).

@export_group("Jump forgiveness")
@export_range(0.0, 0.3, 0.01) var coyote_time: float = 0.1     ## Celeste JumpGraceTime 0.1 s
@export_range(0.0, 0.3, 0.01) var jump_buffer: float = 0.08    ## working value (unverified)
@export_range(0.0, 0.5, 0.01) var variable_jump_time: float = 0.2  ## Celeste VarJumpTime 0.2 s

@export_group("Hit feedback")
@export_range(0.0, 0.3, 0.01) var hit_stop_light: float = 0.05  ## Celeste Freeze(.05) on dash
@export_range(0.0, 0.5, 0.01) var hit_stop_heavy: float = 0.1   ## Celeste Freeze(.1) on launch

@export_group("Response")
@export_range(0, 6) var max_input_latency_frames: int = 2       ## feel-numbers: next tick, <= 2
@export_range(0, 6) var max_input_jitter_frames: int = 1        ## jitter hurts more than delay
