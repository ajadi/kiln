# Sky formulas

Port these to the engine's language. Angles in degrees unless marked; `rad()` converts. Every
formula here is implemented in `scripts/sky_check.py` and checked against JPL Horizons, the NOAA
tables or Espenak's phase table in `tests/test_sky_check.py`.

## Time

- Julian day (UT): `JD = 2440587.5 + days_since_1970_01_01 + (local_hours - tz) / 24`.
- Julian centuries: `T = (JD - 2451545.0) / 36525`.
- Keep the game clock as int64 or float64 game seconds since a start date. A float32 clock in
  seconds loses 1 s resolution after 2^24 s = 194 game days.

## Sun: NOAA calculator chain (Meeus, ~0.01°)

```
L0  = (280.46646 + T*(36000.76983 + 0.0003032*T)) mod 360      # mean longitude
M   = 357.52911 + T*(35999.05029 - 0.0001537*T)                 # mean anomaly
e   = 0.016708634 - T*(0.000042037 + 0.0000001267*T)            # orbit eccentricity
C   = sin(M)*(1.914602 - T*(0.004817 + 0.000014*T)) + sin(2M)*(0.019993 - 0.000101*T)
      + sin(3M)*0.000289                                        # equation of centre
Om  = 125.04 - 1934.136*T
lam = L0 + C - 0.00569 - 0.00478*sin(Om)                        # apparent longitude
eps = 23 + (26 + (21.448 - T*(46.815 + T*(0.00059 - T*0.001813)))/60)/60 + 0.00256*cos(Om)
decl = asin(sin(eps)*sin(lam))
y   = tan(eps/2)^2
eqtime = 4*deg( y*sin(2L0) - 2e*sin(M) + 4e*y*sin(M)*cos(2L0) - 0.5*y^2*sin(4L0)
                - 1.25*e^2*sin(2M) )                            # minutes
```

## Sun: NOAA short series (~0.5°)

`g = 2π/365 * (doy - 1 + (hour - 12)/24)` (366 in leap years), radians:

```
eqtime = 229.18*(0.000075 + 0.001868cos g - 0.032077sin g - 0.014615cos 2g - 0.040849sin 2g)
decl   = 0.006918 - 0.399912cos g + 0.070257sin g - 0.006758cos 2g + 0.000907sin 2g
         - 0.002697cos 3g + 0.00148sin 3g
```

In 2026 its declination runs about one day early near the equinoxes (0.42° off on 20 March), so
the sun's direction is off by up to 0.45°. That is fine for a game sky, not for a "real place" check.
The one-cosine shortcut `decl = -23.44*cos(360/365*(N + 10))` can be off by about 2°.

## Hour angle, elevation, azimuth

```
tst = ut_minutes + eqtime + 4*lon          # = local minutes + eqtime + 4*lon - 60*tz
ha  = tst/4 - 180                          # wrap to (-180, 180]; negative = morning
sin(el) = sin(lat)sin(decl) + cos(lat)cos(decl)cos(ha)
az  = atan2(sin(ha), cos(ha)sin(lat) - tan(decl)cos(lat)) + 180     # clockwise from north
```

Refraction (NOAA spreadsheet), arcseconds, added to the geometric elevation for display only:
`el > 85: 0`; `el > 5: 58.1/tan e - 0.07/tan³e + 0.000086/tan⁵e`;
`el > -0.575: 1735 + e(-518.2 + e(103.4 + e(-12.79 + 0.711e)))`; else `-20.772/tan e`.

Stylised arc: `decl` fixed, `eqtime = 0`, `ha = 15*(local_hours - noon)`; latitude is the tilt.

## Rise, set, noon, twilight

- Solar noon (local minutes): `720 - 4*lon - eqtime + 60*tz` (mod 1440); iterate eqtime at noon.
- Hour angle where the sun centre reaches elevation `h0`:
  `cos H0 = (sin h0 - sin lat sin decl) / (cos lat cos decl)`. `cos H0 < -1`: always above
  (polar day for that threshold); `> 1`: never reaches it. Event = noon ∓ 4·H0 minutes; recompute
  decl and eqtime at the event time once more (or bisect on elevation as `sky_check.py` does).
- `h0`: sunrise/sunset -0.833 (34′ refraction + 16′ radius), civil -6, nautical -12,
  astronomical -18, golden hour end +6 (working).
- Noon elevation `90 - |lat - decl|`; lowest sun (solar midnight) `|lat + decl| - 90`
  (60°N in June: -6.56°, so nautical twilight lasts all night).
- Day length = `2*H0/15` hours.

## Direction vector and engine frames

Toward the body (unit): `east = cos el sin az`, `up = sin el`, `north = cos el cos az`.

| Engine | x | y | z | The light shines along |
|---|---|---|---|---|
| Godot | east | up | south (−z north) | −basis.z, so `basis.z` = toward the sun |
| Unity | east | up | north | `transform.forward` = −toward |
| Unreal | north (forward) | east | up | actor forward = −toward |

North offset: if true north is θ clockwise from the scene's north axis, use `az + θ`. Build the
light's basis from the vector (Godot `looking_at`, Unity `Quaternion.LookRotation`), not from
Euler pitch/yaw — Euler angles flip near the zenith.

## Moon: low-precision ephemeris (Astronomical Almanac; ~0.3° longitude, 0.2° latitude)

```
lam  = 218.32 + 481267.881T + 6.29 sin(135.0 + 477198.87T) - 1.27 sin(259.3 - 413335.36T)
       + 0.66 sin(235.7 + 890534.22T) + 0.21 sin(269.9 + 954397.74T) - 0.19 sin(357.5 + 35999.05T)
       - 0.11 sin(186.5 + 966404.03T)
beta = 5.13 sin(93.3 + 483202.02T) + 0.28 sin(228.2 + 960400.89T) - 0.28 sin(318.3 + 6003.15T)
       - 0.17 sin(217.6 - 407332.21T)
par  = 0.9508 + 0.0518 cos(135.0 + 477198.87T) + 0.0095 cos(259.3 - 413335.36T)
       + 0.0078 cos(235.7 + 890534.22T) + 0.0028 cos(269.9 + 954397.74T)   # horizontal parallax
x = cos beta cos lam;  y = 0.9175 cos beta sin lam - 0.3978 sin beta;  z = 0.3978 cos beta sin lam + 0.9175 sin beta
ra = atan2(y, x);  dec = asin(z);  distance = 1/sin(par) Earth radii
```

Topocentric (parallax up to ~1°, matters near the horizon): subtract the observer
`(cos lat cos LST, cos lat sin LST, sin lat)` from `distance*(x, y, z)` before converting to
RA/Dec, then `ha = LST - ra` and the elevation/azimuth formula above. Against Horizons at 45°N:
≤ 0.15° in 6 cases.

Phase: `phase = (lam_moon - lam_sun) mod 360` (0 new, 90 first quarter, 180 full, 270 last quarter),
elongation `cos psi = cos beta cos(lam_moon - lam_sun)`, phase angle
`i = atan2(R sin psi, D - R cos psi)` (R sun distance, D moon distance, km), lit fraction
`k = (1 + cos i)/2`. Next phase: bisect `phase - target` forward in time (phases within ~30 min of
Espenak in 2026).

Game method: `age = (JD - 2451550.09766) mod 29.530588853` days, `k = (1 - cos(2π age/29.530589))/2`;
the true phase differs from the mean by up to ~17 h. A stylised moon sits on the sun's arc with
hour angle `ha_sun - phase` (full moon opposite the sun, first quarter 90° east of it).

Brightness relative to full (Krisciunas & Schaefer 1991):
`10^(-0.4*(0.026|i| + 4e-9 i^4))` — 0.49 at i 30°, 0.23 at 60°, 0.091 at 90° (half lit).

## Stars

- Sidereal day 86164.0905 s: rotation angle `360 * t / 86164.0905`, 15.04107°/hour.
- GMST (deg) = `280.46061837 + 360.98564736629*(JD - 2451545) + 0.000387933T² - T³/38710000`;
  apparent: add `dpsi*cos(eps)/3600` with
  `dpsi = -17.20 sin Om - 1.32 sin 2Ls - 0.23 sin 2Lm + 0.21 sin 2Om` arcsec
  (`Ls = 280.4665 + 36000.7698T`, `Lm = 218.3165 + 481267.8813T`). LST = GMST + lon.
- Star dome: axis toward azimuth 0 (north; 180 in the south) at elevation |lat|. Hour angle of a
  star increases with time (west after transit); a dome texture in equatorial coordinates is
  rotated by `-LST` about that axis.

## Light

- Kasten & Young (1989) air mass: `m = 1/(cos z + 0.50572*(96.07995 - z)^-1.6364)`, z = 90 - el;
  37.9 at the horizon.
- Direct sun: `E_normal = 128000 * exp(-c*m)` lx; `c = 0.267` gives 98,000 lx at zenith; on
  the ground `E_horizontal = E_normal * sin(el)`.
- EV100 from illuminance: `E = 2.5 * 2^EV` lx; scene luminance `L = 2^(EV-3)` cd/m².
- Stops between two levels: `log2(E1/E2)`; noon sun (100,000 lx) to full moon (0.1 lx) is 19.9.

## Game time

```
scale_day   = game seconds per real second in daylight; night runs scale_day * k
day_h       = sunset - sunrise;  night_h = 24 - day_h
real_day_s  = day_h*3600/scale_day + night_h*3600/(scale_day*k)
sun_deg_per_real_s = 15 * scale / 3600            # 0.3 at 72x
clock resolution for a check of tol degrees = tol/15 game hours (0.5° -> 2 game minutes)
```
