---
name: shaders
description: Writing and reviewing shaders and materials for games — built-in material first and a shader only when it cannot do the job, recipes with starting parameters (hit flash, dissolve, rim/fresnel, triplanar, toon ramp, outlines by inverted hull, stencil, post-process edges or jump flood, scrolling UVs and flowmaps, vertex wind, damage masks, palette swap), authoring through the engine MCP (Godot shading language and visual shaders, Unity URP HLSL and Shader Graph, Unreal material graphs and instances), performance rules (texture fetches, branching, overdraw, precision, variant explosion, per-instance parameters that keep batching) and measurable checks (clean compile logs, GPU ms delta, parameters in the inspector). Use for any shader, material or material-instance task.
user-invocable: false
---

# Shaders and materials

A shader runs for every vertex and pixel of everything that uses it, so a small mistake is
multiplied by pixels × layers × objects. Use the built-in material when it can do the job, write
a shader when it cannot, expose every tunable as a parameter, and prove the cost in GPU ms.
Values marked (working) are starting points to tune. Code for every recipe:
`${CLAUDE_SKILL_DIR}/references/recipes.md`; per-engine authoring details and pitfalls:
`${CLAUDE_SKILL_DIR}/references/engines.md`. 2D light and CanvasItem basics: art-2d skill §6.

## 1. Built-in first

| Need | Built-in route (Godot / Unity URP / Unreal) | Write a shader when |
|---|---|---|
| PBR surface, emission, transparency, billboard, soft/proximity/distance fade | StandardMaterial3D / URP Lit, Unlit, Particles / parent material + instances | never for plain surfaces |
| Triplanar | `uv1_triplanar` + `uv1_triplanar_sharpness` / Triplanar node / WorldAlignedTexture | different texture per axis, blended normal maps |
| Rim | `rim_enabled`, `rim`, `rim_tint` / Fresnel Effect node / Fresnel | coloured, masked or animated rim |
| Toon | `diffuse_mode` and `specular_mode` = Toon / — / — | custom ramp, band count, shadow tint |
| Outline | 4.5+ `stencil_mode = Outline` or `grow` + front-cull next pass / — / Custom Depth-Stencil post | wide or constant-pixel-width lines |
| Hit flash, dissolve, wind, damage masks, palette swap, flowmaps | — | always: a small parameterised shader |

## 2. Authoring through the MCP (scene_first covers materials)

Shaders and materials are editor resources; create, validate and assign them through the engine
MCP, never by writing `.tres`, `.mat` or `.uasset` text.

- **Godot** (`material_manage`): `shader_validate` → `shader_create` (`res://shaders/<name>.gdshader`,
  shared code in `.gdshaderinc`) → `create(type="shader", shader_path)` → `set_shader_param` →
  `assign` / `apply_to_node`; edit with `shader_patch`. Visual shaders: `visual_shader_node_catalog`
  → `visual_shader_create_graph` / `visual_shader_edit` (compiled by the engine before saving).
  Ramps and noise: `resource_manage` `gradient_texture_create` / `noise_texture_create`.
- **Unity** (MCP for Unity): `manage_shader` create/update for URP HLSL `.shader` files;
  `manage_material` create / `set_material_shader_property` / `assign_material_to_renderer`;
  check `read_console` after `refresh_unity`. No tool edits Shader Graph nodes — when the team
  wants a graph, keep the logic in a Custom Function `.hlsl` file (File mode) the graph calls.
- **Unreal** (`MaterialTools`, `MaterialInstanceTools`; `describe_toolset` first): one parent
  `M_` with parameters, children `MI_`; compile and read the log.

## 3. Recipes (starting parameters)

| Recipe | Core | Parameters | Cost |
|---|---|---|---|
| Wet surfaces, puddles, ripples, snow cover | darken albedo and lower roughness with wetness; puddles from a height/porosity mask; ripple normals; snow by surface normal and the roof occlusion map | global weather shader parameters; recipes in the weather skill's `references/recipes.md` | ALU + one occlusion-map sample |
| Hit flash | mix albedo → flash colour, add emission | `flash` 0→1 per instance, decays to 0 in 80–120 ms; HDR ×2–4 in 3D; pixel art: 0 or 1 only, 1–2 frames | ALU only |
| Dissolve | noise vs threshold → alpha scissor; glowing edge band | `dissolve` 0→1 in 0.6–1.5 s; edge 0.03–0.08; edge HDR ×3–6; noise 0.5–3 tiles/m | +1 fetch; alpha test |
| Rim / fresnel | `pow(1 − saturate(dot(N, V)), p)` | p 2–5; intensity 0.5–2; mask | ALU only |
| Triplanar | 3 planar samples, weights `pow(abs(n), k)` normalised | k 4–8; scale in tiles/m; world or object space | ×3 fetches per map |
| Toon ramp | `N·L × attenuation` → ramp in `light()` | 2–3 bands; edge softness 0.01–0.05; shadow tint | per light per pixel |
| Scroll / flowmap | UV + t·speed; flowmap: two phases offset 0.5, triangle weights | speed 0.05–0.5 UV/s; strength 0.1–0.3; noise in flowmap A | 2 fetches + flowmap |
| Vertex wind | offset = dir · sin(t·f·2π + phase(world xz)) · amp · mask | amp 0.02–0.15 m; f 0.5–2 Hz; mask = vertex colour R | vertex only; widen cull margin |
| Damage mask | painted threshold map vs `damage` → damaged albedo, roughness, hot edge | `damage` 0–1 per part; sharpness 8–20; edge heat decays 0.5–1 s | +1–2 fetches |
| Palette swap | index in R → `texelFetch` LUT row | LUT width = colours, row = variant; nearest, no mipmaps, lossless | +1 fetch |

## 4. Outlines — choose by width and count

| Method | Width / look | Cost | Watch for |
|---|---|---|---|
| Inverted hull (front-cull pass grown along normals, width scaled by clip w) | 1–4 px, per object | +1 draw per object | gaps on hard edges — bake smoothed normals into a vertex channel |
| Godot 4.5+ stencil outline | per material | extra pass | overrides manual `next_pass` |
| Post-process edges (depth + normal Sobel) | 1–2 px, whole scene | one full-screen pass, flat cost | thresholds per scene scale |
| Jump flood | any width; passes = ceil(log2 width) | < 1 ms full screen at 1080p (Golus, RTX 2080 Super) | multipass setup — a tech-design decision |

## 5. Performance rules

1. Cost ≈ covered pixels × layers × per-pixel work. Large transparent quads and full-screen passes
   dominate; measure instead of guessing.
2. Count texture fetches. Pack masks into the RGBA channels of one texture; compute simple
   gradients and shapes instead of sampling them.
3. Branches on a uniform are cheap; per-pixel divergent branches pay for both sides.
4. Variants multiply: N on/off keywords or static switches → 2^N shaders (10 → 1024). Prefer
   uniforms; Unity `shader_feature` (unused variants stripped) or `dynamic_branch` over
   `multi_compile`; Unreal: few static switches, check the Material Analyzer.
5. Opaque < alpha scissor / hash < alpha blend in cost (blend is slowest and casts no shadows in
   Godot). `discard` / alpha test defeats the depth prepass and early-z, worst on tile GPUs.
6. Precision: half/mediump for colours and UVs on mobile; full for world positions and depth.
   Godot: do not write precision qualifiers unless needed (drivers differ).
7. Move work up: per-vertex instead of per-pixel; per-frame constants from the CPU.
8. Per-object variation must not multiply materials: Godot `instance uniform` (≤ 16 per shader,
   no textures, not on MultiMesh — use `INSTANCE_CUSTOM`; canvas_item since 4.4); Unity: no
   MaterialPropertyBlock in URP (breaks the SRP Batcher), cache one material instance per renderer
   at spawn; Unreal: Custom Primitive Data (32 floats, keeps instancing) before per-object MIDs.
9. Screen reads cost a copy: Godot 2D copies the screen before the first node reading
   `hint_screen_texture` (each BackBufferCopy is another); 3D copies after opaques, so
   transparents are missing from it.
10. Materials created or changed in render state at runtime compile mid-game: prewarm (destruction-vfx
    skill, shader stutter).
11. Phase = rate x absolute time is a bug whenever the rate can change. `offset = speed * TIME`
    is right only while speed is constant: when the weather thickens or the wind picks up,
    `speed * TIME` jumps by `delta_speed * TIME`, which after ten minutes of play is thousands
    of units, so the texture sweeps or flickers through the whole transition. Integrate instead:
    keep `phase += speed * delta` on the CPU (wrap it to the texture period) and pass `phase` as
    the uniform; the same for oscillators (`sin(freq * TIME)` with a changing `freq`). Caught by
    `frames.py ramp` (acceptance skill); a phase that never advances is caught by `frames.py
    anim`.

## 6. Checks before handoff

| Check | Gate |
|---|---|
| Compile | validator clean (Godot `shader_validate`/`shader_create`; Unity `read_console` 0 shader errors/warnings; Unreal compile log) and 0 shader errors/warnings in editor and game logs after running the scene |
| Parameters | every tunable is a uniform/parameter with a range hint and default, visible in the inspector or material instance; no magic numbers in code |
| Per-instance | changing one object's parameter leaves others unchanged; material count does not grow at runtime |
| GPU cost | Δ GPU ms = N instances in front of a fixed camera minus baseline, median of ≥ 120 frames; per-object shader ≤ 0.1 ms, full-screen pass ≤ 0.5 ms at 1080p (working) unless GAME.md says otherwise |
| Batching | draw calls unchanged or explained (Godot RENDER_TOTAL_DRAW_CALLS_IN_FRAME, Unity Frame Debugger / SRP Batcher compatible, Unreal `stat rhi`) |
| Stutter | first appearance compiles nothing (Godot PIPELINE_COMPILATIONS_DRAW stays 0) |
| Variants | variant/permutation count reported; a feature does not double it |
| Look | screenshots at parameter 0, 0.5, 1 under game lighting, looked at; grayscale read per the lighting skill |

Evidence in the handoff: shader path, parameter list with defaults, the GPU ms table and what the
screenshots showed.
