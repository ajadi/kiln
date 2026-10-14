# Feel in numbers

Translate the user's words into numbers before tuning. "No adjective without a number."

| The user says | Measure | Typical target / fix |
|---|---|---|
| sluggish, laggy, unresponsive | input → visible response | next physics tick for movement/camera; feedback ≤ 2 rendered frames; ≤ 100 ms end to end (Swink), aim degrades from ~41 ms added latency; camera driven by input, never by animation |
| floaty (jumps) | jump height h, time to apex t | gravity g = 2h/t², launch v₀ = 2h/t; stronger fall gravity (×1.5–2.5) and apex gravity reduction; variable jump height; max fall speed |
| floaty (movement) | acceleration / deceleration time to full speed | shorter accel/decel (e.g. 0.05–0.15 s on foot); turnaround faster than start |
| slippery | deceleration distance, friction | higher ground friction; snap stop below a speed threshold |
| unfair jumps / missed inputs | forgiveness windows | coyote time 0.10–0.15 s, jump buffer 0.10–0.15 s, corner correction |
| weak hits | feedback within the hit tick | hit flash, sound and marker on the hit tick; hit-stop 40–80 ms (heavy 100–200 ms, scaled; none on rapid fire); target reaction escalating twitch → falter → stagger; decals and debris persist |
| weapon feels like a toy | recoil, sound layers, muzzle flash | camera kick + recovery spring, low layer 60–120 Hz, muzzle flash 16–33 ms + light 30–50 ms, shake decaying within ~0.5 s |
| enemy attacks feel cheap | telegraph on screen | ≥ 400–600 ms multi-sense wind-up for avoidable attacks (≥ 2× human reaction 190 ms + latency); longer when more attack types are possible (Hick) |
| AI is a sniper / unfair | first accurate shot after exposure | ≥ 0.4–0.7 s (detection + gaze shift + aim); no fire without line of sight; attack tokens |
| heavy enemy feels light | speed vs size, timing | Froude ≤ 0.5 when walking (v ≤ √(0.5·g·h)); timings scale √(h/0.9); long anticipation; slow topple (8 m body ≥ 1.5–2.7 s to the ground) |
| skating feet | slip per stance in the running game | ≤ 10 mm in engine (perception ≈ 21 mm); play rate within 0.85–1.15 of authored speed |
| camera makes me sick | FOV, bob, shake | FOV 80–100° on PC (setting), head bob small or off by option, shake rotation-only with a disable setting |
| too long to kill | TTK per weapon × enemy | compare with the design table; adjust HP/armour data, not damage formulas |
| can't see what's happening | contrast and clutter | enemy vs background ≥ 3:1, weak points ≥ 4.5:1; effects never cover the centre of the screen > 300 ms |

Sources are in the acceptance agents (qa-feel, qa-locomotion, qa-readability) and the
human-biomechanics, creature-locomotion and lighting skills.

## 2D movement (platformers, top-down)

Jump from design numbers (Pittman): apex height h, time to apex tₕ, horizontal speed vₓ, distance
to apex xₕ → g = 2h/tₕ², v₀ = 2h/tₕ; or from distance: v₀ = 2h·vₓ/xₕ, g = 2h·vₓ²/xₕ². Use a
separate (larger) g after the apex or on early release.

Reference set — Celeste (pixels at 320×180, 8 px tiles, per second):

| Constant | Value | Constant | Value |
|---|---|---|---|
| gravity | 900 | max run | 90 |
| jump speed | −105 | run accel / decel | 1000 / 400 |
| variable jump time | 0.2 s (hold to keep jump speed) | air control multiplier | 0.65 |
| coyote (jump grace) | 0.1 s | apex half-gravity | ×0.5 while \|vy\| < 40 and jump held |
| max fall / fast fall | 160 / 240 | corner correction | 4 px |
| jump buffer | ≈ 0.08 s (unverified) | | |

- Scale by tile size and resolution, not by feel: keep the jump in tiles (Celeste ≈ 3 tiles high).
- Top-down: `move_toward` velocity, 0.05–0.15 s to top speed, normalise diagonals, floating
  motion mode, collider at the feet.
- Godot `CharacterBody2D`: floor_max_angle 0.785 default; raise `floor_snap_length` from 1 to 4–8
  px for slopes; `floor_constant_speed = true`; safe_margin 0.08; one-way platforms with
  drop-through by clearing a mask bit for a few frames; colliders in whole pixels.
- Camera: drag margins, smoothing, look-ahead in the move direction; shake from a trauma value,
  offset rounded to whole pixels in pixel art; hit-stop per entity 2–6 frames.
- Acceptance: jump apex within ±1 px and time to apex within ±1 tick of the design; input to
  first moved pixel 1–2 frames; no sub-pixel camera jitter.
