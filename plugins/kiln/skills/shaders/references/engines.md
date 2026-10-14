# Shader authoring per engine

Details behind the shaders skill §2 and §5. Every file below is created and changed through the
engine MCP named in the engine profile; the guard refuses hand-written scene/resource text.

## Godot 4.6/4.7

**Files and MCP.** `res://shaders/<name>.gdshader`, shared code in `res://shaders/inc/*.gdshaderinc`
(`#include "res://shaders/inc/noise.gdshaderinc"`). `material_manage`:
`shader_validate(code, shader_type, base_dir)` → `shader_create(resource_path, code, shader_type)`
(parsed before writing; rejects on errors) → `create(path, type="shader", shader_path)` →
`set_shader_param` → `assign(node_path, resource_path, slot)` (`override`, `surface_<N>`,
`canvas`, `process`). Edit with `shader_patch(path, old_text, new_text)`; read with `shader_get`.
Validation is parse/type checking — run the scene and read `logs_read` for renderer-specific
errors.

**Visual shaders.** The graph is converted to shader code, so runtime cost equals a text shader.
`visual_shader_node_catalog` → `visual_shader_create_graph(resource_path, stages, shader_type)` →
`visual_shader_edit(operations)`. Use them when the user wants to tweak the graph by hand; text
cannot be converted back into a graph. An Expression node holds inline shader code.

**Uniforms.**
- `source_color` on every colour and albedo texture (required in Forward+/Mobile).
- `hint_range(min, max[, step])`, `hint_enum("A", "B")` for ints, `filter_nearest` /
  `filter_linear_mipmap`, `repeat_enable` / `repeat_disable`, `hint_default_white|black`.
- `group_uniforms Name;` groups parameters in the inspector.
- `instance uniform` — per GeometryInstance3D, and per CanvasItem since 4.4; ≤ 16 per shader
  (`instance_index` hint 0–15 avoids collisions); no textures or arrays; on MultiMesh one value
  for the whole MultiMeshInstance3D (per-instance data: `INSTANCE_CUSTOM`);
  with several materials on one mesh the first material's value wins.
- `global uniform` — defined in Project Settings → Shader Globals first (`project_manage`), set
  with `RenderingServer.global_shader_parameter_set`; available in every shader type.
- Uniform buffer limit: 65,536 bytes (4,096 vec4) on most desktops, 16,384 bytes on mobile.

**Materials.** One shared material per look. `resource_local_to_scene` or `duplicate()` makes a
copy per instance — use instance uniforms instead. `next_pass` for an extra pass on one material;
`GeometryInstance3D.material_overlay` draws over all surfaces (good for hit flash on multi-surface
meshes). BaseMaterial3D `stencil_mode` (4.5+) owns `next_pass` and overwrites manual changes.

**Render modes that change cost.** `unshaded` (no lighting), `blend_add` / transparency (sorted,
no depth prepass, no shadows for blend), `depth_prepass_alpha`, `cull_disabled` (double the
pixels on thin geometry), `shadows_disabled`, `fog_disabled`, `diffuse_toon` / `specular_toon`.
A custom `light()` runs per light per pixel and replaces built-in lighting for that material.

**Screen reads.** `hint_screen_texture` (2D: whole screen copied before the first node using it;
BackBufferCopy adds copies; 3D: copied after opaques, transparents absent and screen-reading
materials count as transparent). `hint_depth_texture` everywhere; `hint_normal_roughness_texture`
Forward+ only. Depth is reversed-z since 4.3 — linearise with `INV_PROJECTION_MATRIX`.

**Stutter.** Ubershaders + pipeline precompilation (4.4+, Forward+/Mobile only) cover materials
present when a scene or mesh loads. Not covered: material overrides set at runtime, materials created after load, render
modes changed mid-game, and all 2D canvas pipelines. Prewarm: keep a hidden instance of every
effect/material in the loaded scene. Watch `PIPELINE_COMPILATIONS_DRAW` and `_CANVAS`.

**Debug views.** `Viewport.debug_draw` OVERDRAW, UNSHADED, LIGHTING, NORMAL_BUFFER; editor
Perspective → Display Advanced. GPU ms via `RenderingServer.viewport_set_measure_render_time` +
`viewport_get_measured_render_time_gpu` (optimization skill).

**Compatibility renderer (web, low-end, many 2D games).** No `hint_normal_roughness_texture`, no
compute (CompositorEffect), no ubershaders/pipeline precompilation (same 16 instance uniforms);
test shaders under the renderer the project ships with.

## Unity 6 (URP)

**HLSL shader skeleton** (created with `manage_shader` create/update; Unity compiles on import):

```hlsl
Shader "Kiln/HitFlash"
{
    Properties
    {
        _BaseMap ("Base Map", 2D) = "white" {}
        [HDR] _FlashColor ("Flash Color", Color) = (1,1,1,1)
        _Flash ("Flash", Range(0,1)) = 0
    }
    SubShader
    {
        Tags { "RenderType"="Opaque" "RenderPipeline"="UniversalPipeline" }
        Pass
        {
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            TEXTURE2D(_BaseMap); SAMPLER(sampler_BaseMap);
            CBUFFER_START(UnityPerMaterial)       // every material property here: SRP Batcher
                float4 _BaseMap_ST;
                half4 _FlashColor;
                half _Flash;
            CBUFFER_END
            struct Attributes { float4 positionOS : POSITION; float2 uv : TEXCOORD0; };
            struct Varyings { float4 positionHCS : SV_POSITION; float2 uv : TEXCOORD0; };
            Varyings vert (Attributes i)
            {
                Varyings o;
                o.positionHCS = TransformObjectToHClip(i.positionOS.xyz);
                o.uv = TRANSFORM_TEX(i.uv, _BaseMap);
                return o;
            }
            half4 frag (Varyings i) : SV_Target
            {
                half4 c = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, i.uv);
                c.rgb = lerp(c.rgb, _FlashColor.rgb, _Flash);
                return c;
            }
            ENDHLSL
        }
    }
}
```

Rules: `HLSLPROGRAM` and URP ShaderLibrary includes, never `CGPROGRAM` / `UnityCG.cginc`; all
material properties in one `UnityPerMaterial` CBUFFER, otherwise the SRP Batcher drops the
shader; `TEXTURE2D`/`SAMPLER` macros; lit shaders also include `Lighting.hlsl` and need
ShadowCaster/DepthOnly/DepthNormals passes to cast shadows and appear in depth.

**Keywords and variants.** `#pragma shader_feature_local _DISSOLVE_ON` for material toggles
(unused variants are stripped from builds); `multi_compile` only for keywords toggled at runtime
across materials; `#pragma dynamic_branch_local` when a toggle is cheap enough to branch. Limits:
65,534 local keywords per shader; each independent on/off keyword doubles variants. Check the
compiled variant count in the shader inspector or the build log.

**Shader Graph.** URP targets Lit, Unlit, Sprite Lit/Unlit (2D lights), Fullscreen (with the Full
Screen Pass Renderer Feature). Agents have no node-editing tool: create the graph asset (menu
item), put the logic in a Custom Function node in File mode — `.hlsl` file with an include guard
(`#ifndef KILN_FLASH_INCLUDED` / `#define`), function names with precision suffix (`Flash_float`,
`Flash_half`), URP-library calls wrapped in `#ifdef SHADERGRAPH_PREVIEW` fallbacks — and expose
properties on the Blackboard.

**Materials** (`manage_material`): Material Variants for families; runtime per-object values on
one cached material instance per renderer made at spawn (SRP Batcher batches by shader variant,
so many materials of one variant stay cheap). Do not use `mode = property_block`: a
MaterialPropertyBlock makes the renderer SRP-Batcher-incompatible. Particle shaders are not SRP
Batcher compatible.

**Verify.** `read_console` after `refresh_unity` (0 shader errors/warnings); inspector "SRP
Batcher: compatible"; `manage_profiler frame_debugger_get_events` to see batches and why they
break; Rendering Debugger overdraw view.

## Unreal 5.8

**MCP.** `MaterialTools` and `MaterialInstanceTools` toolsets (Epic Unreal MCP; run
`describe_toolset` first — exact tool names are not documented here). Compile the material and
read `GetLogEntries` for errors.

**Structure.** One parent `M_<Family>` per surface family with Scalar/Vector/Texture parameters
(grouped, with slider min/max); instances `MI_` per look (Material Instance Constant, no shader
compile). Shared logic in Material Functions (`MF_`). Runtime per-object values: Custom Primitive
Data (≤ 32 floats per primitive, keeps dynamic instancing — Epic's sample cut 94 to 46 draw calls)
before Material Instance Dynamic; create MIDs once at spawn, never per frame. Global values (wind,
storm intensity): Material Parameter Collection.

**Permutations.** Every used combination of static switches compiles a new shader; usage flags
(skeletal mesh, Niagara sprites, instanced, Nanite) and Quality Switch levels multiply further.
Use few static switches; find duplicates with the Material Analyzer and reparent instances that
share static overrides.

**Cost tools.** Material editor Stats (instruction and sampler counts; above 16 textures set
Sampler Source to Shared: Wrap/Clamp), view modes Shader Complexity and Quad Overdraw
(`viewmode ShaderComplexity`, `viewmode QuadOverdraw`), `stat gpu`, `ProfileGPU`.

**Nanite / shadows.** Nanite takes opaque and masked materials; masked, World Position Offset
and pixel depth offset need programmable rasterisation and cost more; WPO meshes split into
smaller clusters and invalidate virtual shadow map pages — clamp WPO and limit it to what moves.
Translucent materials are never Nanite.

**Stutter.** PSO precaching (5.1+) plus a bundled PSO cache for shipping; check the log for PSO
misses in a packaged build.
