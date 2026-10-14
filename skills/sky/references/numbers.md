# Sky numbers

Computed with `sky_check.py` (NOAA chain, 2026 dates) unless a source is named. Sources and
corrections: the research notes for this skill (kept in Kiln's development repository).

## Day length and noon sun (sunrise to sunset at -0.833°)

| Latitude | June solstice | Equinox (20 Mar) | December solstice |
|---|---|---|---|
| 0° | 12.12 h, noon 66.6° | 12.11 h, 90° | 12.13 h, 66.6° |
| 20°N | 13.34 h, 86.6° | 12.11 h, 70.0° | 10.92 h, 46.6° |
| 30°N | 14.08 h, 83.4° | 12.12 h, 60.0° | 10.22 h, 36.6° |
| 45°N | 15.62 h, 68.4° | 12.15 h, 45.0° | 8.77 h, 21.6° |
| 50°N | 16.37 h, 63.4° | 12.16 h, 40.0° | 8.07 h, 16.6° |
| 60°N | 18.87 h, 53.4° | 12.21 h, 30.0° | 5.87 h, 6.6° |
| 70°N | 24 h (polar day) | 12.31 h, 20.0° | 0 h (polar night), noon -3.4° |

Southern latitudes mirror this with the seasons swapped. Equinox days are slightly longer than 12 h
because sunrise and sunset use the sun's upper limb plus refraction.

## Twilight per side (minutes, morning; evening is within a minute)

Civil = sunrise back to -6°; nautical and astronomical are cumulative from sunrise (to -12°, -18°).

| Latitude, date | Civil | Nautical | Astronomical | Golden hour (0.833° to +6°, working) | Darkest |
|---|---|---|---|---|---|
| 0°, equinox | 20.7 | 44.7 | 68.7 | 27 | full night |
| 0°, solstice | 22.5 | 48.8 | 75.1 | 30 | full night |
| 30°N, June | 27.5 | 60.9 | 96.6 | 35 | full night |
| 45°N, equinox | 29.3 | 63.6 | 98.7 | 39 | full night |
| 45°N, June | 37.5 | 87.3 | 153.5 | 45 | full night |
| 50°N, June | 44.7 | 110.4 | never ends | 52 | astronomical twilight all night |
| 60°N, equinox | 41.5 | 91.3 | 145.4 | 55 | full night |
| 60°N, December | 57.8 | 114.7 | 166.3 | 129 | full night |
| 60°N, June | 106.7 | never ends | never ends | 80 | nautical twilight all night |

Wikipedia (Twilight) gives civil twilight ≈ 24 min at the equator and 33–48 min at Greenwich when
measured from 0°. Blue hour: sun 4–8° below the horizon, 20–96 min (Wikipedia, Blue hour).

## Illuminance and exposure ladder

| Scene | Illuminance | EV100 (scene) | Source |
|---|---|---|---|
| Sun outside the atmosphere | 128,000 lx | — | Wikipedia Sunlight |
| Direct sun at zenith, sea level | ~98,000 lx | 15 (sunny) | Wikipedia Sunlight, Exposure value |
| Blue sky alone at midday | ~20,000 lx | — | Unity HDRP Physical Light Units |
| Sun 30° (direct on the ground, model) | ~37,600 lx | 14 | this skill, c = 0.267 |
| Sun 10° (direct, model) | ~4,000–5,000 lx | — | research spectral model / c = 0.267 |
| Sun 5° (direct, model) | ~500–700 lx | 12 (sunset scene) | same |
| End of civil twilight (-6°) | 3.4 lx | 9–11 just after sunset | Wikipedia Lux, Exposure value |
| Full moon, clear | 0.05–0.3 lx (0.32 tropical perigee) | -3 to -2 | Wikipedia Moonlight, Exposure value |
| Quarter moon | ~0.005–0.03 lx (calc: full × 0.091) | -6 | K&S 1991, Exposure value |
| Starlight + airglow, no moon | ~0.002 lx | -11 to -9 (Milky Way) | Wikipedia Lux, Exposure value |

Noon sun to full moon: 19.9 stops. Godot's Light3D docs: direct sun ~100,000 lx, moonlit ground
~0.1 lx. The full moon is about 1/380,000 as bright as the sun (Wikipedia, Moonlight).

## Direct sun by elevation (clear sky, model, working)

| Elevation | Air mass | Direct normal | On the ground | Colour temperature (direct beam) |
|---|---|---|---|---|
| 0° | 37.9 | — | 0 | ~1850 K (Godot docs, sunrise/sunset) |
| 5° | 10.3 | ~8,200 lx | ~500–700 lx | ~2300 K |
| 10° | 5.59 | ~28,800 lx | ~4,000–5,000 lx | ~3100 K |
| 20° | 2.90 | ~59,000 lx | ~17,800–20,200 lx | ~3950 K |
| 30° | 1.99 | ~75,000 lx | ~34,400–37,600 lx | ~4350 K |
| 60° | 1.15 | ~94,000 lx | ~77,300–81,500 lx | ~4850 K |
| 90° | 1.00 | ~98,000 lx | ~93,600–98,000 lx | ~4950 K |

Published colour temperatures: sunrise/sunset ~1850 K, clear-day sun 5500–6000 K, overcast ~6500 K
(Godot Light3D docs); horizon daylight 5000 K, clear blue sky 15,000–27,000 K (Wikipedia, Color
temperature). Moonlight is reflected sunlight with slightly more red than daylight; it looks
bluish or silvery only because of the Purkinje effect in dim light (Wikipedia, Moonlight).
At low sun the sky gives about half or more of the total light (working), so ambient must not
fade with the direct sun.

## Moon

| Phase angle | Lit fraction | Light vs full (K&S 1991) |
|---|---|---|
| 0° (full) | 1.00 | 1.00 |
| 10° | 0.99 | 0.79 |
| 30° | 0.93 | 0.49 |
| 60° | 0.75 | 0.23 |
| 90° (quarter) | 0.50 | 0.091 |
| 120° | 0.25 | 0.026 |
| 150° | 0.07 | 0.004 |

Synodic month 29.530589 d; moonrise ~50.5 min later each day (calc); full moon rises near sunset,
first quarter near noon (Wikipedia, Lunar phase). Declination swings ±18.3° to ±28.6° over 18.6
years (lunar standstill). Earthshine lights the dark part of a crescent for a few days around new
moon.

## Stars

Sidereal day 23 h 56 min 4.09 s (86164.0905 s); stars rise 3 min 56 s earlier each night; the sky
turns 360.9856° per solar day. The celestial pole stands at altitude = latitude; Polaris is within
1° of the north pole. Facing the pole, the sky turns counter-clockwise in the north and clockwise
in the south.

## Shadow length (2 m tall object, 2/tan(el))

| Sun | 45° | 30° | 20° | 10° | 5° | 2° | 1° |
|---|---|---|---|---|---|---|---|
| Shadow | 2.0 m | 3.5 m | 5.5 m | 11.3 m | 22.9 m | 57.3 m | 114.6 m |

Godot's default `directional_shadow_max_distance` is 100 m: below ~1° even a person's shadow runs
past it.

## Game time in shipped games

| Game | Real time per game day | Scale (game s / real s) | Notes | Source |
|---|---|---|---|---|
| Minecraft | 20 min | 72 | day 10 min, sunset 50 s, night 8 min 20 s, sunrise 50 s; sun and moon pass directly overhead; 8 moon phases, one per night; sky light never below 4 of 15; sleep skips to dawn when all players are in bed | Minecraft wiki |
| Zelda BotW / TotK | 24 min | 60 | 1 game hour per real minute; Blood Moon; enemies sleep at night; resting skips to morning, noon or night | Zelda wiki |
| GTA V, Red Dead Redemption 2 | ~48 min | 30 | 2 real s per game minute; RDR2 nights reported to pass ~2× faster | community guides (UNVERIFIED) |
| Skyrim | 72 min | 20 (timescale) | waiting and sleeping count against timed effects; NPC and shop schedules | UESP |
| Stardew Valley | ~14 min (06:00–02:00) | 85.7 | 10 game minutes per 7 real s; clock pauses in menus (single player) | Stardew wiki |
| Valheim | 30 min | 48 | 21 min day, 9 min night | mein-mmo (UNVERIFIED) |
| Animal Crossing: New Horizons | 24 h | 1 | follows the console clock | widely documented |

At 72× the sun moves 0.30°/s; a ±0.5° check needs the game clock to 2 game minutes (1.7 real s).
