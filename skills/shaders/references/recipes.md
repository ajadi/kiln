# Shader recipes

Starting code for the recipes in the shaders skill §3–4. Godot 4.6/4.7 shading language first
(create with `material_manage` `shader_validate` → `shader_create`; every snippet is a starting
point — validate before saving), then the Unity Shader Graph / URP HLSL and Unreal material-graph
equivalents. Parameter values are (working) starting points.

Conventions in all recipes:

- Colours are `source_color` (sRGB → linear; required in Forward+/Mobile); ranges get `hint_range`.
- Per-object values are `instance uniform` (≤ 16 per shader, scalars/vectors only, not on
  MultiMesh — there use `INSTANCE_CUSTOM` / `COLOR`), set from scripts with
  `set_instance_shader_parameter(&"name", value)` on the GeometryInstance3D or (4.4+) CanvasItem.
  The material stays shared, so batching is kept.
- Tween parameters from behaviour scripts; never `duplicate()` a material per hit.

## Hit flash

```glsl
// 3D: add to the object's shader (or a next_pass/overlay material)
shader_type spatial;
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap;
uniform vec4 flash_color : source_color = vec4(1.0);
uniform float flash_energy : hint_range(0.0, 8.0) = 3.0;
instance uniform float flash : hint_range(0.0, 1.0) = 0.0;
void fragment() {
	vec3 base = texture(albedo_tex, UV).rgb;
	ALBEDO = mix(base, flash_color.rgb, flash * 0.6);
	EMISSION = flash_color.rgb * flash * flash_energy;
}
```

```glsl
// 2D (Godot 4.4+ for instance uniforms). COLOR already holds texture × modulate.
shader_type canvas_item;
uniform vec4 flash_color : source_color = vec4(1.0);
instance uniform float flash : hint_range(0.0, 1.0) = 0.0;
void fragment() {
	COLOR.rgb = mix(COLOR.rgb, flash_color.rgb, flash);
}
```

Timing: set `flash = 1` on the hit frame, tween to 0 over 80–120 ms (3D/HD 2D). Pixel art: 0 or 1
only (a partial mix leaves the palette), held 1–2 frames, flash colour from the palette.
Unity: Shader Graph Lerp(Base, FlashColor, Flash) → Base Color, FlashColor × Flash × Energy →
Emission; set the float on the renderer's cached material instance. Unreal: Lerp + Emissive with
`Flash` read from Custom Primitive Data index 0 (`SetCustomPrimitiveDataFloat`).

## Dissolve

```glsl
shader_type spatial;
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap;
uniform sampler2D noise_tex : hint_default_white;      // seamless NoiseTexture2D
uniform float noise_scale : hint_range(0.1, 8.0) = 1.0;  // noise tiles per metre
uniform float edge_width : hint_range(0.0, 0.2) = 0.05;
uniform vec4 edge_color : source_color = vec4(1.0, 0.45, 0.1, 1.0);
uniform float edge_energy : hint_range(0.0, 16.0) = 4.0;
instance uniform float dissolve : hint_range(0.0, 1.0) = 0.0;
varying vec3 world_pos;
void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}
void fragment() {
	vec2 p = world_pos.xz + vec2(world_pos.y * 0.7, -world_pos.y * 0.4);  // cheap 3D-ish projection
	float n = texture(noise_tex, p * noise_scale).r;
	float d = mix(-edge_width, 1.0, dissolve);        // 0 = intact, 1 = gone
	ALBEDO = texture(albedo_tex, UV).rgb;
	ALPHA = step(d, n);
	ALPHA_SCISSOR_THRESHOLD = 0.5;                     // alpha test, stays in the opaque pass
	EMISSION = edge_color.rgb * edge_energy * (1.0 - smoothstep(0.0, edge_width, n - d));
}
```

Sample noise in world or object space so the pattern does not stretch with UV seams; UV is fine
for 2D. Pixel-art dissolve: threshold an ordered (Bayer) dither or a hand-made index map, no edge
glow gradient, step in 3–6 discrete stages. Unity: Simple/Gradient Noise → Step against the
threshold → Alpha with Alpha Clipping on; edge = Smoothstep band × colour → Emission. Unreal:
Masked blend mode, Opacity Mask = noise − threshold; edge band into Emissive (masked materials
cost more under Nanite).

## Rim / fresnel

```glsl
uniform vec4 rim_color : source_color = vec4(0.4, 0.7, 1.0, 1.0);
uniform float rim_power : hint_range(0.5, 8.0) = 3.0;
uniform float rim_energy : hint_range(0.0, 8.0) = 1.5;
void fragment() {
	// NORMAL and VIEW are both view space in Godot
	float fres = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), rim_power);
	EMISSION += rim_color.rgb * rim_energy * fres;
}
```

Use for enemy separation (lighting skill rule 6) and shields. Unity: Fresnel Effect node (Power).
Unreal: Fresnel (ExponentIn, BaseReflectFractionIn = 0).

## Triplanar

Try `uv1_triplanar` (+ `uv1_world_triplanar`, `uv1_triplanar_sharpness`) on StandardMaterial3D
first. Custom version when each axis needs its own texture:

```glsl
uniform sampler2D side_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D top_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform float tiles_per_m : hint_range(0.05, 4.0) = 0.5;
uniform float sharpness : hint_range(1.0, 16.0) = 6.0;
varying vec3 wpos;
varying vec3 wnrm;
void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	wnrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}
void fragment() {
	vec3 w = pow(abs(wnrm), vec3(sharpness));
	w /= (w.x + w.y + w.z);
	vec3 x = texture(side_tex, wpos.zy * tiles_per_m).rgb;
	vec3 y = texture(top_tex, wpos.xz * tiles_per_m).rgb;
	vec3 z = texture(side_tex, wpos.xy * tiles_per_m).rgb;
	ALBEDO = x * w.x + y * w.y + z * w.z;
}
```

Cost is 3 fetches per map (albedo + normal + ORM = 9). Normal maps need a per-projection swizzle
and a proper blend (whiteout or reoriented normal mapping), not a plain weighted sum. For moving
objects use object space or the texture swims. Unity: Triplanar node (Type Normal for normal
maps). Unreal: WorldAlignedTexture / WorldAlignedNormal.

## Toon ramp

```glsl
uniform sampler2D ramp : filter_nearest, repeat_disable;   // GradientTexture1D, constant interpolation
uniform vec4 shadow_tint : source_color = vec4(0.55, 0.6, 0.8, 1.0);
void light() {
	float ndl = clamp(dot(NORMAL, LIGHT), 0.0, 1.0) * ATTENUATION;
	vec3 band = texture(ramp, vec2(ndl, 0.5)).rgb;
	DIFFUSE_LIGHT += mix(shadow_tint.rgb * 0.2, vec3(1.0), band) * LIGHT_COLOR / PI;
}
```

Make the ramp with `resource_manage gradient_texture_create` (2–3 stops, constant
interpolation). A custom `light()` replaces built-in diffuse and specular for that material and
runs per light per pixel — keep lights few. Unity URP: Shader Graph has no light loop; use a
Custom Function (`GetMainLight()`, additional lights loop) guarded by `#ifdef SHADERGRAPH_PREVIEW`.
Unreal: usually a post-process toon pass or a Substrate/custom shading model — a tech-design
decision.

## Outlines

### Inverted hull, constant pixel width (next_pass material, `cull_front`)

```glsl
shader_type spatial;
render_mode unshaded, cull_front, shadows_disabled, fog_disabled;
uniform vec4 outline_color : source_color = vec4(0.05, 0.05, 0.08, 1.0);
uniform float width_px : hint_range(0.0, 8.0) = 2.0;
uniform bool smoothed_normal_in_color = false;   // smoothed normal baked into COLOR.rgb
void vertex() {
	vec3 n = smoothed_normal_in_color ? COLOR.rgb * 2.0 - 1.0 : NORMAL;
	vec4 clip = PROJECTION_MATRIX * (MODELVIEW_MATRIX * vec4(VERTEX, 1.0));
	vec3 nv = normalize(MODELVIEW_NORMAL_MATRIX * n);
	vec2 dir = normalize((PROJECTION_MATRIX * vec4(nv, 0.0)).xy);
	clip.xy += dir / VIEWPORT_SIZE * 2.0 * width_px * clip.w;
	POSITION = clip;
}
void fragment() {
	ALBEDO = outline_color.rgb;
}
```

Hard-edged meshes split normals and open gaps: bake averaged normals into a vertex colour
attribute in Blender (through the Blender MCP) and turn on `smoothed_normal_in_color`. Outline
colour = the darkest colour of the object's ramp, not pure black. Godot 4.5+ alternative for
highlights: `stencil_mode = Outline`, `stencil_outline_thickness` on the material (it manages
`next_pass` itself). Unity URP: a second material/pass via a Renderer Feature (Render Objects)
with front-face culling. Unreal: post-process outline from Custom Depth-Stencil (mark actors
with Render CustomDepth Pass + stencil value).

### Post-process edges (whole scene, Forward+)

Full-screen quad: MeshInstance3D + QuadMesh 2×2, Flip Faces on, child of the camera or maximum
`extra_cull_margin`, built in the scene through the MCP.

```glsl
shader_type spatial;
render_mode unshaded, fog_disabled;
uniform sampler2D depth_tex : hint_depth_texture, filter_nearest;
uniform sampler2D nr_tex : hint_normal_roughness_texture, filter_nearest;  // Forward+ only
uniform sampler2D screen_tex : hint_screen_texture, filter_nearest;
uniform vec4 line_color : source_color = vec4(0.05, 0.05, 0.08, 1.0);
uniform float depth_threshold : hint_range(0.0, 2.0) = 0.15;   // metres, scale per scene
uniform float normal_threshold : hint_range(0.0, 2.0) = 0.4;
void vertex() {
	POSITION = vec4(VERTEX.xy, 1.0, 1.0);
}
float lin_depth(vec2 uv, mat4 inv_proj) {
	float d = texture(depth_tex, uv).x;                  // reversed-z since 4.3
	vec4 v = inv_proj * vec4(uv * 2.0 - 1.0, d, 1.0);
	return -v.z / v.w;
}
void fragment() {
	vec2 px = 1.0 / VIEWPORT_SIZE;
	float dc = lin_depth(SCREEN_UV, INV_PROJECTION_MATRIX);
	vec3 nc = texture(nr_tex, SCREEN_UV).xyz * 2.0 - 1.0;
	float de = 0.0;
	float ne = 0.0;
	for (int i = 0; i < 4; i++) {
		vec2 o = vec2(float(i % 2) * 2.0 - 1.0, float(i / 2) * 2.0 - 1.0) * px;
		de = max(de, abs(lin_depth(SCREEN_UV + o, INV_PROJECTION_MATRIX) - dc) / max(dc, 0.1));
		ne = max(ne, 1.0 - dot(nc, texture(nr_tex, SCREEN_UV + o).xyz * 2.0 - 1.0));
	}
	float edge = max(step(depth_threshold * 0.1, de), step(normal_threshold, ne));
	ALBEDO = mix(texture(screen_tex, SCREEN_UV).rgb, line_color.rgb, edge);
}
```

Fixed cost per pixel (5 depth + 5 normal + 1 screen fetch here) regardless of object count.
Functions cannot read processor built-ins, so `INV_PROJECTION_MATRIX` is passed in. Godot 4.3+
also offers CompositorEffect (compute) for heavier passes.

### Jump flood (wide outlines)

Render the outlined objects' silhouette to a mask, initialise seeds at edge pixels, run
ceil(log2(width)) flood passes (offsets 2^(k−1) … 1 px; a 14 px outline needs 4 passes), then
composite where distance ≤ width. Cost is nearly independent of width (Golus measured < 1 ms full
screen at 1080p on an RTX 2080 Super). Needs multipass control: Godot CompositorEffect, Unity URP
Renderer Feature with `RecordRenderGraph`, Unreal SceneViewExtension / RDG in C++. Use only when
outlines must be wider than ~8 px or many objects need them; record the choice in
`memory/decisions.md`.

## Scrolling UVs and flowmaps

```glsl
uniform sampler2D main_tex : source_color, repeat_enable;
uniform sampler2D flow_map : repeat_enable;   // RG = direction * 0.5 + 0.5, A = noise
uniform float speed : hint_range(0.0, 2.0) = 0.25;
uniform float strength : hint_range(0.0, 1.0) = 0.2;
vec3 flow_uvw(vec2 uv, vec2 flow, float t, float phase_offset) {
	float p = fract(t + phase_offset);
	return vec3(uv - flow * p + phase_offset, 1.0 - abs(1.0 - 2.0 * p));
}
void fragment() {
	vec4 f = texture(flow_map, UV);
	vec2 flow = (f.rg * 2.0 - 1.0) * strength;
	float t = TIME * speed + f.a;                     // noise offset removes pulsing
	vec3 a = flow_uvw(UV, flow, t, 0.0);
	vec3 b = flow_uvw(UV, flow, t, 0.5);
	ALBEDO = texture(main_tex, a.xy).rgb * a.z + texture(main_tex, b.xy).rgb * b.z;
}
```

Plain scrolling: `UV + TIME * scroll_speed`; for lasers scale by beam length so texel speed stays
constant (destruction-vfx recipes). Unity: Time + Tiling And Offset, Flipbook node for sheets.
Unreal: Panner; flowmaps with the same two-phase math in material functions.

## Vertex wind

```glsl
uniform vec3 wind_dir_local = vec3(1.0, 0.0, 0.3);
uniform float amp : hint_range(0.0, 0.5) = 0.08;       // metres
uniform float freq : hint_range(0.0, 4.0) = 1.2;        // Hz
uniform float gust : hint_range(0.0, 1.0) = 0.3;
void vertex() {
	float phase = dot(NODE_POSITION_WORLD.xz, vec2(0.37, 0.61));
	float s = sin(TIME * freq * TAU + phase) + gust * sin(TIME * freq * 2.3 * TAU + phase * 1.7);
	VERTEX += normalize(wind_dir_local) * s * amp * COLOR.r;  // COLOR.r: 0 at root, 1 at tip
}
```

Set `extra_cull_margin` ≥ amp on the instance so it is not culled early; shadows move too
(vertex runs in the shadow pass). Many plants: MultiMesh with per-instance phase in
`INSTANCE_CUSTOM`. A shared wind direction across shaders: a global uniform added in Project
Settings first (`project_manage`). Unity: Position node (Object) + offset in the Vertex stage.
Unreal: World Position Offset (SimpleGrassWind, Pivot Painter); WPO invalidates virtual shadow
map pages and splits Nanite clusters — limit it to what is visible and clamp the offset.

## Damage mask (per mech part)

```glsl
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap;
uniform sampler2D damaged_tex : source_color, filter_linear_mipmap;  // scorched/dented albedo
uniform sampler2D damage_mask : hint_default_white;   // R = threshold: 0 breaks first (edges)
uniform float sharpness : hint_range(1.0, 40.0) = 12.0;
uniform vec4 heat_color : source_color = vec4(1.0, 0.35, 0.05, 1.0);
instance uniform float damage : hint_range(0.0, 1.0) = 0.0;  // part HP lost, from the part
instance uniform float heat : hint_range(0.0, 1.0) = 0.0;    // set to 1 on hit, decays 0.5–1 s
void fragment() {
	float m = texture(damage_mask, UV).r;
	float t = clamp((damage - m) * sharpness, 0.0, 1.0);
	ALBEDO = mix(texture(albedo_tex, UV).rgb, texture(damaged_tex, UV).rgb, t);
	ROUGHNESS = mix(0.45, 0.85, t);
	float rim = clamp(1.0 - abs(damage - m) * sharpness, 0.0, 1.0);
	EMISSION = heat_color.rgb * rim * heat * 4.0;
}
```

The part's HealthComponent sets `damage` from its own HP (local damage rule in destruction-vfx).
Paint the mask in Blender (through the MCP) or derive it from curvature/AO. Unity: same graph with
two Sample Texture 2D and a Lerp; Unreal: Custom Primitive Data for `damage`/`heat`.

## Palette swap (pixel art)

```glsl
shader_type canvas_item;
uniform sampler2D palette_lut : filter_nearest, repeat_disable;  // width = colours, height = variants
instance uniform float variant = 0.0;                              // row index; Godot 4.4+
varying vec4 tint;
void vertex() {
	tint = COLOR;                                    // modulate × vertex colour
}
void fragment() {
	vec4 src = texture(TEXTURE, UV);                 // sprite stores the palette index in R (0–255)
	int index = int(src.r * 255.0 + 0.5);
	vec4 c = texelFetch(palette_lut, ivec2(index, int(variant)), 0);
	COLOR = vec4(c.rgb, src.a) * tint;
}
```

Index sprites and the LUT import lossless, no mipmaps, filter Nearest; the LUT row 0 is the source
palette (`art/palette.hex`), one row per variant (team colours, damage states). Check the result
with `sprite_qa.py palette` on an in-game capture (art-2d skill).

## Sources

- Godot shading language, spatial and canvas_item shader references, screen-reading shaders,
  advanced post-processing, visual shaders, BaseMaterial3D (docs.godotengine.org, stable 4.x).
- Godot PR #99230 (2D instance uniforms, 4.4), #80710 (stencil, 4.5).
- Catlike Coding, Texture Distortion (flowmaps): catlikecoding.com/unity/tutorials/flow/texture-distortion/
- Ben Golus, The Quest for Very Wide Outlines (2020): bgolus.medium.com/the-quest-for-very-wide-outlines-ba82ed442cd9
- Unity Shader Graph Custom Function node; Unreal Custom Primitive Data, Instanced Materials.
