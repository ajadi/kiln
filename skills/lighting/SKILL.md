---
name: lighting
description: Lighting game spaces for gameplay and mood — workflow with checkpoints, rules (one motivated key, lighting hierarchy, players follow light, enemies out-contrast their surroundings, peak contrast on gameplay information), per-zone colour scripts and key:fill ratios, objective acceptance numbers measured from screenshots (luminance, contrast, saliency, exposure), GI/shadow/fog choices and costs, and Godot 4.6/4.7 settings (Unity/Unreal settings in their engine skills). Use when lighting, relighting or reviewing any scene.
user-invocable: false
---

# Lighting

Lighting is gameplay first (where to go, what to shoot, what threatens), mood second, and it is
judged with numbers, because image models read brightness imprecisely. Values marked (working)
are starting points to tune per project. The rules apply to 2D as well; 2D light nodes, normal
maps and quantised pixel-art lighting are in the art-2d skill §6.

## Workflow and checkpoints

0. **Preflight**: renderer and version; GPU timing on; auto-exposure **off** while lighting; three
   camera bookmarks per zone (entry, mid, combat); a calibration kit (18% grey sphere, chrome
   sphere, enemy proxy). Checkpoint: baseline screenshots, histogram stats and GPU ms saved.
1. **Colour script per zone**: function (corridor = guide, arena = read), motivating light (sun,
   moon, fire, neon), warm/cool pair, key:fill target, median lightness target, fog. Approved
   before lighting.
2. **Neutral pass**: audit albedo unlit — no albedo outside 30/50–240 sRGB (dark rooms are often an
   albedo problem, not a lighting one).
3. **Global key**: sun/moon, sky, ambient, tonemapper; choose GI. Checkpoint: key:fill measured on
   the grey ball, histogram, light-leak check. A moving sun or moon, day/night curves and the sky
   model: `kiln:sky`; fog and lighting per weather preset: `kiln:weather`.
4. **Path pass**: practical lights and spots on exits, landmarks via emissive signage.
   Checkpoint: saliency, squint test, path vs dead-end brightness.
5. **Combat pass per arena**: even baseline fill, commonly peeked corners lit, enemies against
   bright backdrops or with rim light, weak points emissive, telegraph lights dynamic.
   Checkpoint: enemy contrast at 10, 25, 50 m.
6. **Atmosphere**: fog, volumetrics, glow, wet reflections — then re-run the metrics (fog lowers
   contrast).
7. **GI quality**: bake, inspect GI debug views, look from interiors toward openings — no leaks,
   no splotches.
8. **Exposure**: clamped auto-exposure on last; walk the route in the running game, capture every
   N metres, check metrics over the whole sequence.
9. **Performance**: toggle each feature ≥ 120 frames, median GPU ms; within budget on minimum spec.
10. **Regression**: screenshots and metrics per bookmark, re-run after every change.

## Rules

1. One motivated key light per space; add a light only to fix a named problem ("the key light
   is master").
2. Lighting hierarchy: critical path > alternate routes > dead ends. Never light everything the
   same.
3. Players follow light: exits brighter and/or framed by contrast; darkness means "not this way".
4. Limit competing high-contrast hotspots; simplify when they fight. "If everything draws
   attention, nothing will."
5. Enemies out-contrast their local surroundings; keep the environment desaturated and mid-value
   relative to combatants.
6. Separate dark silhouettes with backlight: light fog or particles behind them, or a
   complementary rim/kicker light (a cull-mask layer for enemies).
7. Peak contrast where the gameplay information is: weak points, weapons, damaged parts;
   telegraphs "loud and fast" with emissive and glow.
8. Arenas ~2–3:1 key:fill so fights read everywhere; corridors and transitions 4–8:1 for mood.
9. Spot entry points and commonly peeked corners; no black pockets where an enemy disappears.
10. One warm/cool complementary pair per area, consistent with the colour script.
11. Detail in the dark comes from wet or specular surfaces, not from raising exposure.
12. Shadows are a budget: only lights that change the read cast shadows; distance fade; prefer
    spots.
13. Choose GI by what changes: destructible pieces must not depend on baked direct light.
14. Seal geometry; walls thicker than one GI cell; interior flags set.
15. Light with exposure locked; clamped auto-exposure last; verify in the running game.
16. Judge exposure by numbers, grayscale and blur; use image judgement for meaning and pairwise A/B.

## Acceptance numbers (measure from screenshots)

Convert sRGB to linear, luminance Y = 0.2126R + 0.7152G + 0.0722B, lightness L* = 116·f(Y) − 16
(middle grey 0.18 ≈ L* 49.5), contrast ratio = (L1 + 0.05)/(L2 + 0.05). Enemy mask = screenshot
with and without the enemy. Tools: `contact_sheet.py values` / `contrast`, numpy.

| Check | Target |
|---|---|
| Clipped pixels (any channel ≥ 250) | ≤ 1% of a gameplay view, excluding flashes and signs (working) |
| Crushed pixels (luma ≤ 8) | ≤ 5% corridors, ≤ 2% arenas (working) |
| Median L* | corridors 25–45, arenas 35–55, daytime exteriors 45–60 (working) |
| P95 L* | ≥ 70 — some highlight in every view (working) |
| Enemy vs 10–20 px background ring | ≥ 3:1 at combat distances (XAG 102 large elements) |
| Weak point vs surrounding enemy surface | ≥ 4.5:1 (XAG 102) |
| Key:fill on the grey ball | arenas 2–4:1, corridors 4–8:1 |
| Exit vs dead-end luminance | ≥ 1.5–2× (working) |
| Saliency from the entry bookmark | exit/objective among the top-3 peaks (spectral residual) |
| Squint test (blur σ ≈ 1% width, 4 levels) | path and enemies in a different band from their neighbours |
| Exposure transitions | settle ≤ 1.5 s; no frame with median L* < 15 or > 75 |
| Shadowed positional lights in view | ≤ 6, mostly spots (working) |

## Godot 4.6/4.7 settings (starting values)

| Area | Start | Cost / note |
|---|---|---|
| Renderer | Forward+ | SDFGI, volumetric fog, auto-exposure, SSAO/SSIL/SSR are Forward+ only |
| Tonemap | AgX (4.6+), or Filmic white 6–8 | Environment default is Linear — change it |
| Auto-exposure | off while lighting; later scale ~0.4, speed ~0.5, clamp ±1.5 EV | — |
| GI choice | iterate with SDFGI; ship LightmapGI for the static shell with the sun in Dynamic bake mode, so direct light and shadows stay live when walls break | SDFGI is the most expensive; dynamic objects don't occlude it |
| SDFGI | cascades 4, min cell 0.2, y_scale 50–75%, bounce feedback 0.3–0.5, occlusion on | > 0.5 bounce feedback can run away; low ray count → splotches |
| VoxelGI (arenas, interiors) | two bounces, Interior, quality Low, half-resolution GI | `bake()` callable, 5–20 s |
| LightmapGI | texel 0.2 (0.5+ large areas), 3 bounces, shadowmask Replace, probe subdivision 8 | editor bake; bake CSG to meshes first |
| ReflectionProbe | Update Once, box projection, Interior | up to 4 blend at a point |
| Sun shadows | 4096 (2048 low-end), 4 splits (2 for performance), max distance ~60–100 m, raise normal bias first | 4 splits render large objects 5× |
| Positional shadows | atlas 4096, quadrants 4/4/16/64, distance fade on | turn shadows off wherever possible |
| Light bake modes | Static set dressing; Dynamic sun/keys reacting to destruction; Disabled muzzle flashes/explosions | Dynamic costs more |
| SSAO | radius 1.0, intensity 2.0, power 1.5, half-size | ambient only |
| SSR | wet streets | no transparents |
| Volumetric fog | density 0.01–0.03, anisotropy 0.2, short length, froxels 64×64 | transient lights fog energy 0; negative FogVolumes carve interiors |
| Glow | HDR threshold 1.0, signs emission > 1 | 4.6+: blends before tonemapping |
| Clustered limits | 512 elements in view (lights, decals, probes); ≤ 8 VoxelGI / LightmapGI in view | — |

Agent hooks: GPU time via `RenderingServer.viewport_set_measure_render_time(rid, true)` then
`viewport_get_measured_render_time_gpu(rid)`; `Viewport.debug_draw` LIGHTING, UNSHADED,
SCENE_LUMINANCE, SHADOW_ATLAS, PSSM_SPLITS, SDFGI_PROBES, VOXEL_GI_LIGHTING, CLUSTER_OMNI_LIGHTS,
OVERDRAW. All lights and environment are nodes in the scene, built in the open editor.
