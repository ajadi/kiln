# Art bible — <game>

## Identity
<one sentence: what the game looks like and why>

## Palette
| colour | hex | role |
|---|---|---|
| <name> | <#hex> | <e.g. enemy weak points / player UI / environment base> |

Value rules: <what is darkest / lightest; where the eye goes first>
Saturation budget: <what may be saturated; what never is>

## Shape language
- Hero: <shapes, silhouette rule>
- Enemies / creatures (per type): <shapes, silhouette at 128 px in grayscale>
- Environment: <shapes>

## Lighting and atmosphere
<key/fill ratio, colour temperature contrast, fog, time of day, emissive signage>

## Materials and wear
<metal, paint, concrete; wear rules; roughness ranges>

## Signature techniques (visible in one still frame)
1. <technique>
2. <technique>
3. <technique>

## UI and VFX direction
<style, colour coding, readability rules>

## Forbidden
- <what never appears>

## 2D (delete this section in a 3D game)
- Base resolution and scale: <e.g. 320×180 ×6>
- Method: <pixel by hand / pre-rendered from Blender / SVG vector / painterly>
- Palette: <N colours, ramps of N, hue shift rule>; file `art/palette.hex`
- Sprite sizes: <player / enemies / tiles in px>; outline rule: <...>
- Animation: <fps, frame counts for idle / run / attack>

## Requires from the tech
- <shaders, GI, fog, effects the look depends on>
