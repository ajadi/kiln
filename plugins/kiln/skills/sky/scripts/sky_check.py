"""Checks for the sky — sun, moon and stars, the day/night cycle and game time — against exact
answers (Python 3.12+, stdlib only).

Prediction (design time):
  python sky_check.py predict sun      --lat 45 --lon 0 --date 2026-06-21 --time 14:00 --tz 2
                                       [--model noaa|fourier|arc] [--decl 0] [--noon 12]
                                       [--frame godot|unity|unreal] [--north-offset 0]
  python sky_check.py predict twilight --lat 60 --lon 25 --date 2026-03-20 --tz 2 [--model ...]
  python sky_check.py predict moon     --date 2026-10-11 [--time 12:00] [--tz 0] [--lat 45 --lon 0]
  python sky_check.py predict stars    --elapsed-h 6 [--lat 45] [--scale 72]
                                       [--date 2026-06-21 --time 00:00 --tz 0 --lon 0]
  python sky_check.py predict light    --elev 10 [--extinction 0.267]
  python sky_check.py predict time     (--day-min 24 | --scale 60) [--sunrise 6 --sunset 18]
                                       [--night-speed 2] [--tol-deg 0.5] [--span-h 8] [--skip-s 3]

  sun: NOAA solar position (the Meeus chain behind the NOAA calculator; ~0.01 deg): declination,
  equation of time, hour angle, geometric and refracted elevation, azimuth (clockwise from north),
  the direction toward the sun in the engine frame, solar noon, sunrise and sunset (sun centre at
  -0.833 deg), day length, polar day/night. --model fourier is the short NOAA series (~0.5 deg);
  --model arc is a stylised sky: fixed --decl, solar noon at --noon local hours, --lat is the tilt.
  twilight: dawn and dusk for civil (-6), nautical (-12), astronomical (-18), golden hour (+6,
  working), twilight durations, the lowest and highest sun, and how dark the night gets.
  moon: phase from the Sun-Moon elongation (low-precision Astronomical Almanac moon, ~0.3 deg),
  illuminated fraction, phase name, next new/quarter/full moon (UTC), the mean-synodic-month age a
  game can use (29.530589 d), brightness relative to full (Krisciunas & Schaefer 1991), and with
  --lat/--lon the topocentric elevation/azimuth and moonlight on the ground (working).
  stars: sidereal rotation 360 deg per 86164.0905 s, the pole's altitude (= latitude) and axis,
  local apparent sidereal time for a date. light: Kasten-Young air mass, direct-sun lux
  E = 128000 * exp(-c * m) (c 0.267 gives 98,000 lx at zenith), colour temperature (model,
  working), EV100. time: time compression - scale, real minutes per game day and per day/night,
  sun degrees per real second, clock resolution needed for a check, real time of a game span.

Measurement (recordings from the running game; --clock is game time of day in --clock-unit
h|min|s, unwrapped at midnight, or game time since --date 00:00):
  python sky_check.py sun      <dump> --dir sun_dir --clock clock --lat 45 --lon 0 --date 2026-06-21
                               --tz 0 [--body sun|moon] [--model ...] [--travel] [--frame godot]
                               [--north-offset 0] [--min-elev 0] [--tol 0.5]
  python sky_check.py curve    <dump> --value sun_energy --clock clock [--mode abs|rel|stops]
                               [--max-rate 0.05] [--per game-min|real-s] [--window 1]
                               [--max-gap-min 10]
  python sky_check.py handover <dump> --sun sun_energy --moon moon_energy [--floor 0.02]
                               [--floor-frac 0.5] [--sun-shadow sun_sh --moon-shadow moon_sh]
                               [--max-overlap-s 0.5] [--min-hold-s 5]
  python sky_check.py clock    <dump> --clock clock --scale 72 [--sunrise 6 --sunset 18]
                               [--night-speed 1] [--tol 0.02]
  python sky_check.py stars    <dump> --star star_dir --clock clock --lat 45 [--frame godot]
                               [--period-h 23.9345] [--tol 0.001] [--tol-deg 0.5]

  sun: angle between the recorded direction toward the body (Godot: the light's
  global_transform.basis.z; --travel if you record the way the light shines) and the predicted one
  at the recorded game time, for samples with the body above --min-elev. curve: largest change of a
  light value per game minute (or per real second) over --window, so pops and steps show; skips
  longer than --max-gap-min are counted, not judged. handover: sun + moon key light never drops
  below the floor (default --floor-frac of the moon's median as night key), two directional
  shadows are not on together for longer than --max-overlap-s, and the shadow caster does not
  switch back within --min-hold-s (flicker). clock: game seconds per real second against --scale
  (night * --night-speed), no backward steps. stars: a star marker's hour angle advances 360 deg
  per --period-h game hours and its declination stays constant (the dome turns about the pole).

Frames: godot x east, y up, -z north; unity x east, y up, z north; unreal x north, y east, z up.
--north-offset: degrees clockwise from the scene's north axis to true north.
Recordings: the acceptance recorder JSON or JSON Lines. Prints one JSON object
{"verdict", "metrics": [...]} (predict: {"prediction": {...}}); exit code 1 on FAIL, 2 on bad input.
"""

import argparse
import datetime as dt
import json
import math
import sys

D2R = math.pi / 180.0
SIDEREAL_DAY_S = 86164.0905          # mean sidereal day
SYNODIC_MONTH_D = 29.530588853       # mean synodic month
MEAN_NEW_MOON_JD = 2451550.09766     # Meeus (49.1), k = 0: mean new moon 2000-01-06
SUN_LUX_TOP = 128000.0               # solar illuminance constant, lx
FULL_MOON_LUX_ZENITH = 0.25          # working: clear night, mean distance, moon at zenith
EPOCH_ORD = dt.date(1970, 1, 1).toordinal()
UNIX_JD = 2440587.5
PHASE_NAMES = ["new", "waxing crescent", "first quarter", "waxing gibbous", "full",
               "waning gibbous", "last quarter", "waning crescent"]
# direct-beam colour temperature by sun elevation (deg -> K); 0 deg from Godot's Light3D docs,
# the rest from a Rayleigh + aerosol model (research pass) - working values
CCT_TABLE = [(0, 1850), (5, 2300), (10, 3100), (20, 3950), (30, 4350), (60, 4850), (90, 4950)]


class NotAssessed(Exception):
    """The input cannot answer the question."""


def metric(name, value, threshold, ok, **extra):
    return {"metric": name, "value": value, "threshold": threshold,
            "verdict": "PASS" if ok else "FAIL", **extra}


def rnd(x, n=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, n)


# ---------- time ----------

def parse_date(text):
    if not text:
        raise ValueError("--date YYYY-MM-DD is required")
    return dt.date.fromisoformat(text)


def parse_hours(text):
    """'14:30', '14:30:15' or decimal hours '14.5' -> hours."""
    if text is None:
        return 12.0
    if ":" in str(text):
        parts = [float(p) for p in str(text).split(":")]
        while len(parts) < 3:
            parts.append(0.0)
        return parts[0] + parts[1] / 60 + parts[2] / 3600
    return float(text)


def day_start_jd(date, tz):
    """Julian day (UT) of local midnight that starts `date`."""
    return UNIX_JD + (date.toordinal() - EPOCH_ORD) - tz / 24.0


def fmt_local(jd, day0):
    """Local clock time of jd for the local day starting at day0, e.g. '04:13:16' or '00:49:10 +1d'."""
    secs = round((jd - day0) * 86400)
    days, rem = divmod(secs, 86400)
    text = f"{rem // 3600:02d}:{rem % 3600 // 60:02d}:{rem % 60:02d}"
    return text if days == 0 else f"{text} {days:+d}d"


def fmt_utc(jd):
    secs = round((jd - UNIX_JD) * 86400)
    return (dt.datetime(1970, 1, 1) + dt.timedelta(seconds=secs)).strftime("%Y-%m-%dT%H:%MZ")


# ---------- sun ----------

def sun_noaa(jd):
    """NOAA spreadsheet / Meeus low-precision chain: declination, equation of time (min),
    apparent ecliptic longitude (deg), distance (AU)."""
    t = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    mr = m * D2R
    c = (math.sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t))
         + math.sin(2 * mr) * (0.019993 - 0.000101 * t) + math.sin(3 * mr) * 0.000289)
    r_au = 1.000001018 * (1 - e * e) / (1 + e * math.cos((m + c) * D2R))
    omega = 125.04 - 1934.136 * t
    lam = l0 + c - 0.00569 - 0.00478 * math.sin(omega * D2R)
    eps0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * math.cos(omega * D2R)
    decl = math.degrees(math.asin(math.sin(eps * D2R) * math.sin(lam * D2R)))
    y = math.tan(eps / 2 * D2R) ** 2
    l0r = l0 * D2R
    eot = 4 * math.degrees(y * math.sin(2 * l0r) - 2 * e * math.sin(mr)
                           + 4 * e * y * math.sin(mr) * math.cos(2 * l0r)
                           - 0.5 * y * y * math.sin(4 * l0r) - 1.25 * e * e * math.sin(2 * mr))
    return decl, eot, lam % 360, r_au


def sun_fourier(jd):
    """NOAA 'General Solar Position Calculations' series: declination (deg), equation of time."""
    days = jd - UNIX_JD
    whole = math.floor(days)
    hour = (days - whole) * 24
    d = dt.date.fromordinal(EPOCH_ORD + whole)
    n = 366 if d.year % 4 == 0 and (d.year % 100 != 0 or d.year % 400 == 0) else 365
    g = 2 * math.pi / n * (d.timetuple().tm_yday - 1 + (hour - 12) / 24)
    eot = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    return math.degrees(decl), eot


def altaz(lat, decl, ha):
    """Elevation and azimuth (clockwise from north) for latitude, declination, hour angle (deg)."""
    la, de, h = lat * D2R, decl * D2R, ha * D2R
    s = math.sin(la) * math.sin(de) + math.cos(la) * math.cos(de) * math.cos(h)
    el = math.degrees(math.asin(max(-1.0, min(1.0, s))))
    az = math.degrees(math.atan2(math.sin(h), math.cos(h) * math.sin(la)
                                 - math.tan(de) * math.cos(la))) + 180
    return el, az % 360


def refraction(el):
    """NOAA spreadsheet approximation of atmospheric refraction (deg) at geometric elevation el."""
    if el > 85:
        return 0.0
    te = math.tan(el * D2R)
    if el > 5:
        r = 58.1 / te - 0.07 / te ** 3 + 0.000086 / te ** 5
    elif el > -0.575:
        r = 1735 + el * (-518.2 + el * (103.4 + el * (-12.79 + el * 0.711)))
    else:
        r = -20.772 / te
    return r / 3600


def wrap180(x):
    return (x + 180) % 360 - 180


def make_sun(model, lat, lon, tz, decl=0.0, noon=12.0):
    """f(jd) -> dict(decl, eot, ha, el, az) for the chosen model."""
    if model not in ("noaa", "fourier", "arc"):
        raise ValueError(f"unknown model {model}")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("--lat must be in [-90, 90] and --lon in [-180, 180]")

    def f(jd):
        if model == "arc":
            local_h = ((jd + 0.5) % 1) * 24 + tz
            d, eot, ha = decl, 0.0, wrap180(15 * (local_h - noon))
        else:
            d, eot = sun_noaa(jd)[:2] if model == "noaa" else sun_fourier(jd)
            ut_min = ((jd + 0.5) % 1) * 1440
            ha = wrap180((ut_min + eot + 4 * lon) / 4 - 180)
        el, az = altaz(lat, d, ha)
        return {"decl": d, "eot": eot, "ha": ha, "el": el, "az": az}
    return f


def solar_noon(f, day0):
    t = day0 + 0.5
    for _ in range(6):
        t -= f(t)["ha"] / 360.9856
    if t < day0:
        t += 1
    elif t >= day0 + 1:
        t -= 1
    for _ in range(3):
        t -= f(t)["ha"] / 360.9856
    return t


def crossing(f, lo, hi, alt):
    elo = f(lo)["el"] - alt
    ehi = f(hi)["el"] - alt
    if elo * ehi > 0:
        return None
    for _ in range(48):
        mid = (lo + hi) / 2
        em = f(mid)["el"] - alt
        if (em < 0) == (elo < 0):
            lo, elo = mid, em
        else:
            hi = mid
    return (lo + hi) / 2


def events(f, day0, alt):
    """(rise_jd, set_jd, state) for a threshold elevation on the local day; state is None,
    'above' (never goes below) or 'below' (never reaches it)."""
    noon = solar_noon(f, day0)
    if f(noon)["el"] < alt:
        return None, None, "below"
    rise = crossing(f, noon - 0.5, noon, alt)
    sett = crossing(f, noon, noon + 0.5, alt)
    return rise, sett, ("above" if rise is None and sett is None else None)


# ---------- moon and stars ----------

def moon_geo(jd):
    """Low-precision geocentric Moon (Astronomical Almanac): ecliptic longitude and latitude,
    horizontal parallax (deg), right ascension and declination (deg)."""
    t = (jd - 2451545.0) / 36525.0

    def s(a, b):
        return math.sin((a + b * t) * D2R)

    def c(a, b):
        return math.cos((a + b * t) * D2R)
    lam = (218.32 + 481267.881 * t + 6.29 * s(135.0, 477198.87) - 1.27 * s(259.3, -413335.36)
           + 0.66 * s(235.7, 890534.22) + 0.21 * s(269.9, 954397.74) - 0.19 * s(357.5, 35999.05)
           - 0.11 * s(186.5, 966404.03)) % 360
    beta = (5.13 * s(93.3, 483202.02) + 0.28 * s(228.2, 960400.89) - 0.28 * s(318.3, 6003.15)
            - 0.17 * s(217.6, -407332.21))
    par = (0.9508 + 0.0518 * c(135.0, 477198.87) + 0.0095 * c(259.3, -413335.36)
           + 0.0078 * c(235.7, 890534.22) + 0.0028 * c(269.9, 954397.74))
    cb, sb = math.cos(beta * D2R), math.sin(beta * D2R)
    cl, sl = math.cos(lam * D2R), math.sin(lam * D2R)
    x, y, z = cb * cl, 0.9175 * cb * sl - 0.3978 * sb, 0.3978 * cb * sl + 0.9175 * sb
    return lam, beta, par, math.degrees(math.atan2(y, x)) % 360, math.degrees(math.asin(z))


def gmst_deg(jd):
    t = (jd - 2451545.0) / 36525.0
    return (280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * t * t
            - t ** 3 / 38710000.0) % 360


def gast_deg(jd):
    """Greenwich apparent sidereal time: GMST + equation of the equinoxes (Meeus ch. 22)."""
    t = (jd - 2451545.0) / 36525.0
    om = (125.04452 - 1934.136261 * t) * D2R
    ls = (280.4665 + 36000.7698 * t) * D2R
    lm = (218.3165 + 481267.8813 * t) * D2R
    dpsi = (-17.20 * math.sin(om) - 1.32 * math.sin(2 * ls) - 0.23 * math.sin(2 * lm)
            + 0.21 * math.sin(2 * om))
    eps = (23.4392911 - 0.0130042 * t) * D2R
    return (gmst_deg(jd) + dpsi * math.cos(eps) / 3600) % 360


def moon_topo(jd, lat, lon):
    """Topocentric elevation and azimuth of the Moon (parallax applied, no refraction)."""
    _, _, par, ra, dec = moon_geo(jd)
    r = 1 / math.sin(par * D2R)
    lst = (gast_deg(jd) + lon) * D2R
    cd = math.cos(dec * D2R)
    x = r * cd * math.cos(ra * D2R) - math.cos(lat * D2R) * math.cos(lst)
    y = r * cd * math.sin(ra * D2R) - math.cos(lat * D2R) * math.sin(lst)
    z = r * math.sin(dec * D2R) - math.sin(lat * D2R)
    ra_t = math.degrees(math.atan2(y, x))
    dec_t = math.degrees(math.asin(z / math.sqrt(x * x + y * y + z * z)))
    return altaz(lat, dec_t, wrap180(math.degrees(lst) - ra_t))


def moon_phase(jd):
    """Elongation in longitude (0 new .. 180 full), phase angle i and illuminated fraction."""
    lam_m, beta, par, _, _ = moon_geo(jd)
    _, _, lam_s, r_au = sun_noaa(jd)
    phase = (lam_m - lam_s) % 360
    psi = math.acos(math.cos(beta * D2R) * math.cos((lam_m - lam_s) * D2R))
    big_r = r_au * 149597870.7
    delta = 6378.14 / math.sin(par * D2R)
    i = math.atan2(big_r * math.sin(psi), delta - big_r * math.cos(psi))
    return phase, math.degrees(i), (1 + math.cos(i)) / 2


def next_phase(jd, target):
    def f(t):
        return wrap180(moon_phase(t)[0] - target)
    t, ft = jd, f(jd)
    for _ in range(80):
        t2 = t + 0.5
        f2 = f(t2)
        if ft < 0 <= f2 and f2 - ft < 90:
            break
        t, ft = t2, f2
    lo, hi = t, t + 0.5
    for _ in range(40):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def moon_relative_to_full(phase_angle):
    """Krisciunas & Schaefer (1991): I* = 10^(-0.4 (3.84 + 0.026|a| + 4e-9 a^4)), relative to a=0."""
    a = abs(phase_angle)
    return 10 ** (-0.4 * (0.026 * a + 4e-9 * a ** 4))


def air_mass(el):
    """Kasten & Young (1989) relative optical air mass at elevation el (deg)."""
    z = 90.0 - el
    return 1.0 / (math.cos(z * D2R) + 0.50572 * (96.07995 - z) ** -1.6364)


# ---------- frames ----------

def to_frame(east, up, north, frame):
    if frame == "godot":
        return [east, up, -north]
    if frame == "unity":
        return [east, up, north]
    if frame == "unreal":
        return [north, east, up]
    raise ValueError(f"unknown frame {frame}")


def from_frame(v, frame):
    x, y, z = v
    if frame == "godot":
        return x, y, -z
    if frame == "unity":
        return x, y, z
    if frame == "unreal":
        return y, z, x
    raise ValueError(f"unknown frame {frame}")


def direction(el, az, frame, north_offset=0.0):
    """Unit vector toward a body at (el, az) in the engine frame."""
    a = (az + north_offset) * D2R
    ce = math.cos(el * D2R)
    return to_frame(ce * math.sin(a), math.sin(el * D2R), ce * math.cos(a), frame)


def unit(v):
    n = math.sqrt(sum(c * c for c in v))
    if n == 0:
        raise ValueError("zero vector")
    return [c / n for c in v]


def el_az(v, frame, north_offset=0.0):
    e, u, n = from_frame(unit(v), frame)
    return (math.degrees(math.asin(max(-1.0, min(1.0, u)))),
            (math.degrees(math.atan2(e, n)) - north_offset) % 360)


def interp(table, x):
    if x <= table[0][0]:
        return table[0][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


# ---------- predictions ----------

def need(a, *names):
    missing = [n for n in names if getattr(a, n) is None]
    if missing:
        raise ValueError(f"{a.case} needs " + " ".join("--" + m.replace("_", "-") for m in missing))


def predict_sun(a):
    need(a, "lat", "lon", "date")
    date = parse_date(a.date)
    day0 = day_start_jd(date, a.tz)
    f = make_sun(a.model, a.lat, a.lon, a.tz, a.decl, a.noon)
    jd = day0 + parse_hours(a.time) / 24
    p = f(jd)
    noon = solar_noon(f, day0)
    rise, sett, state = events(f, day0, -0.833)
    if state == "above":
        length, polar = 24.0, "day"
    elif state == "below":
        length, polar = 0.0, "night"
    else:
        length, polar = ((sett - rise) * 24 if rise and sett else None), None
    out = {"model": a.model, "utc": fmt_utc(jd), "declination_deg": rnd(p["decl"], 4),
           "eqtime_min": rnd(p["eot"], 3), "hour_angle_deg": rnd(p["ha"], 4),
           "elevation_deg": rnd(p["el"], 4),
           "elevation_refracted_deg": rnd(p["el"] + refraction(p["el"]), 4),
           "azimuth_deg": rnd(p["az"], 4),
           "toward_sun": [rnd(c, 5) for c in direction(p["el"], p["az"], a.frame, a.north_offset)],
           "frame": a.frame, "solar_noon": fmt_local(noon, day0),
           "noon_elevation_deg": rnd(f(noon)["el"], 3),
           "sunrise": fmt_local(rise, day0) if rise else None,
           "sunset": fmt_local(sett, day0) if sett else None,
           "day_length_h": rnd(length, 4), "polar": polar}
    return out


def predict_twilight(a):
    need(a, "lat", "lon", "date")
    date = parse_date(a.date)
    day0 = day_start_jd(date, a.tz)
    f = make_sun(a.model, a.lat, a.lon, a.tz, a.decl, a.noon)
    noon = solar_noon(f, day0)
    lowest = min(f(noon - 0.5)["el"], f(noon + 0.5)["el"])
    out = {"model": a.model, "solar_noon": fmt_local(noon, day0),
           "max_elevation_deg": rnd(f(noon)["el"], 3), "min_elevation_deg": rnd(lowest, 3)}
    times = {}
    for name, alt, dawn, dusk in (("sun", -0.833, "sunrise", "sunset"),
                                  ("civil", -6, "civil_dawn", "civil_dusk"),
                                  ("nautical", -12, "nautical_dawn", "nautical_dusk"),
                                  ("astronomical", -18, "astronomical_dawn", "astronomical_dusk"),
                                  ("golden", 6, "golden_hour_end", "golden_hour_start")):
        rise, sett, _ = events(f, day0, alt)
        times[name] = (rise, sett)
        out[dawn] = fmt_local(rise, day0) if rise else None
        out[dusk] = fmt_local(sett, day0) if sett else None
    sr, ss = times["sun"]
    for name in ("civil", "nautical", "astronomical"):
        dawn, dusk = times[name]
        out[f"{name}_twilight_min"] = ([rnd((sr - dawn) * 1440, 2), rnd((dusk - ss) * 1440, 2)]
                                       if sr and ss and dawn and dusk else None)
    gold_end, gold_start = times["golden"]
    out["golden_hour_min"] = ([rnd((gold_end - sr) * 1440, 2), rnd((ss - gold_start) * 1440, 2)]
                              if sr and ss and gold_end and gold_start else None)
    if lowest > -0.833:
        darkest = "sun stays up (polar day)"
    elif lowest > -6:
        darkest = "civil twilight all night (white night)"
    elif lowest > -12:
        darkest = "nautical twilight all night"
    elif lowest > -18:
        darkest = "astronomical twilight all night"
    else:
        darkest = "full night"
    out["darkest"] = darkest
    return out


def predict_moon(a):
    date = parse_date(a.date)
    day0 = day_start_jd(date, a.tz)
    jd = day0 + parse_hours(a.time) / 24
    phase, angle, frac = moon_phase(jd)
    mean_age = (jd - MEAN_NEW_MOON_JD) % SYNODIC_MONTH_D
    rel = moon_relative_to_full(angle)
    out = {"utc": fmt_utc(jd), "phase_deg": rnd(phase, 3),
           "phase_name": PHASE_NAMES[int(((phase + 22.5) % 360) // 45)],
           "waxing": phase < 180, "illuminated_fraction": rnd(frac, 4),
           "phase_angle_deg": rnd(angle, 3), "age_days": rnd(phase / 360 * SYNODIC_MONTH_D, 3),
           "mean_age_days": rnd(mean_age, 3),
           "mean_illuminated_fraction": rnd((1 - math.cos(2 * math.pi * mean_age
                                                          / SYNODIC_MONTH_D)) / 2, 4),
           "next_new": fmt_utc(next_phase(jd, 0)), "next_first_quarter": fmt_utc(next_phase(jd, 90)),
           "next_full": fmt_utc(next_phase(jd, 180)), "next_last_quarter": fmt_utc(next_phase(jd, 270)),
           "brightness_vs_full": rnd(rel, 4),
           "rise_delay_min_per_day": rnd(1440 * SYNODIC_MONTH_D / (SYNODIC_MONTH_D - 1) - 1440, 1)}
    if a.lat is not None and a.lon is not None:
        el, az = moon_topo(jd, a.lat, a.lon)
        lux = 0.0
        if el > 0:
            lux = (FULL_MOON_LUX_ZENITH * rel * math.sin(el * D2R)
                   * 10 ** (-0.4 * 0.2 * (air_mass(el) - 1)))
        out.update(elevation_deg=rnd(el, 3), azimuth_deg=rnd(az, 3),
                   toward_moon=[rnd(c, 5) for c in direction(el, az, a.frame, a.north_offset)],
                   frame=a.frame, moonlight_lux=rnd(lux, 5),
                   note="moonlight_lux is working: 0.25 lx full moon at zenith, k = 0.2 mag/air mass")
    return out


def predict_stars(a):
    need(a, "elapsed_h")
    secs = a.elapsed_h * 3600
    out = {"sidereal_day_s": SIDEREAL_DAY_S, "rotation_deg": rnd((360 * secs / SIDEREAL_DAY_S) % 360, 4),
           "turns": rnd(secs / SIDEREAL_DAY_S, 6), "deg_per_hour": rnd(360 * 3600 / SIDEREAL_DAY_S, 5),
           "gain_per_solar_day_s": rnd(86400 - SIDEREAL_DAY_S, 4)}
    if a.scale:
        out["real_s_per_turn"] = rnd(SIDEREAL_DAY_S / a.scale, 3)
    if a.lat is not None:
        pole_az = 0.0 if a.lat >= 0 else 180.0
        out.update(pole_altitude_deg=abs(a.lat), pole_azimuth_deg=pole_az, frame=a.frame,
                   pole_axis=[rnd(c, 5) for c in direction(abs(a.lat), pole_az, a.frame,
                                                            a.north_offset)])
    if a.date and a.lon is not None:
        jd = day_start_jd(parse_date(a.date), a.tz) + parse_hours(a.time) / 24
        out.update(utc=fmt_utc(jd), gmst_h=rnd(gmst_deg(jd) / 15, 6),
                   lst_h=rnd(((gast_deg(jd) + a.lon) % 360) / 15, 6))
    return out


def predict_light(a):
    need(a, "elev")
    el = a.elev
    if el <= 0:
        return {"elevation_deg": el, "direct_normal_lux": 0.0, "direct_horizontal_lux": 0.0,
                "cct_k": CCT_TABLE[0][1],
                "note": "sun below the horizon: twilight, moon and starlight values in "
                        "references/numbers.md"}
    m = air_mass(el)
    en = SUN_LUX_TOP * math.exp(-a.extinction * m)
    eh = en * math.sin(el * D2R)
    zen = SUN_LUX_TOP * math.exp(-a.extinction * air_mass(90))
    return {"elevation_deg": el, "air_mass": rnd(m, 4), "direct_normal_lux": rnd(en, 1),
            "direct_horizontal_lux": rnd(eh, 1), "cct_k": rnd(interp(CCT_TABLE, el), 0),
            "ev100_horizontal": rnd(math.log2(eh / 2.5), 2),
            "stops_below_zenith_sun": rnd(math.log2(zen / eh), 2),
            "note": "direct beam only (sky light adds ~20,000 lx at midday); cct is working"}


def predict_time(a):
    if bool(a.day_min) == bool(a.scale):
        raise ValueError("time needs exactly one of --day-min or --scale")
    if not 0 <= a.sunrise < a.sunset <= 24 or a.night_speed <= 0:
        raise ValueError("need 0 <= --sunrise < --sunset <= 24 and --night-speed > 0")
    day_h = a.sunset - a.sunrise
    night_h = 24 - day_h
    k = a.night_speed
    s = (day_h + night_h / k) * 3600 / (a.day_min * 60) if a.day_min else a.scale
    w_day = 15 * s / 3600
    out = {"scale_day": rnd(s, 4), "scale_night": rnd(s * k, 4),
           "real_min_per_game_day": rnd((day_h / s + night_h / (s * k)) * 60, 3),
           "real_min_daytime": rnd(day_h * 60 / s, 3), "real_min_night": rnd(night_h * 60 / (s * k), 3),
           "real_s_per_game_hour": rnd(3600 / s, 3), "real_s_per_game_minute": rnd(60 / s, 4),
           "sun_deg_per_real_s": rnd(w_day, 5), "sun_deg_per_real_s_night": rnd(w_day * k, 5),
           "check_tol_deg": a.tol_deg,
           "clock_resolution_game_min": rnd(a.tol_deg / 15 * 60, 3),
           "clock_resolution_real_s": rnd(a.tol_deg / (w_day * max(k, 1)), 3)}
    if a.span_h:
        out["real_s_for_span"] = rnd(a.span_h * 3600 / s, 2)
        if a.skip_s:
            out["skip_scale"] = rnd(a.span_h * 3600 / a.skip_s, 1)
    return out


def predict(a):
    fn = {"sun": predict_sun, "twilight": predict_twilight, "moon": predict_moon,
          "stars": predict_stars, "light": predict_light, "time": predict_time}[a.case]
    return {"prediction": {"case": a.case, **fn(a)}}


# ---------- recordings ----------

def load_recording(path):
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict) and isinstance(data.get("samples"), dict):
        samples = data["samples"]
        hz = float(data.get("physics_ticks_per_second") or 60)
        ticks = data.get("ticks") or []
        n = max((len(v) for v in samples.values()), default=0)
        times = [(t - ticks[0]) / hz for t in ticks] if ticks else [i / hz for i in range(n)]
        return times, samples
    rows = data if isinstance(data, list) else [json.loads(x) for x in text.splitlines()
                                                 if x.strip()]
    rows = [r for r in rows if r.get("type", "tick") in ("tick", "sample")]
    times = [float(r["t"]) if "t" in r else float(r.get("tick", i)) / 60.0
             for i, r in enumerate(rows)]
    if times:
        times = [t - times[0] for t in times]
    keys = []
    for row in rows:
        keys.extend(k for k in row if k not in keys and k not in ("type", "t", "tick"))
    return times, {k: [row.get(k) for row in rows] for k in keys}


def probe(samples, name):
    if name not in samples:
        raise NotAssessed(f"probe '{name}' not in recording; probes: " + ", ".join(sorted(samples)))
    return samples[name]


def game_hours(values, unit):
    """Game clock -> hours, unwrapped at midnight (a drop of more than 12 h adds a day)."""
    k = {"h": 1.0, "min": 1 / 60, "s": 1 / 3600}[unit]
    out, off, prev = [], 0.0, None
    for v in values:
        if v is None:
            out.append(None)
            continue
        h = float(v) * k + off
        if prev is not None and h < prev - 12:
            off += 24
            h += 24
        out.append(h)
        prev = h
    return out


def is_vec(v):
    return isinstance(v, list) and len(v) == 3 and all(isinstance(c, (int, float)) for c in v)


def angle_between(u, v):
    u, v = unit(u), unit(v)
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(p * q for p, q in zip(u, v))))))


def percentile(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


# ---------- measurements ----------

def measure_sun(a):
    _, samples = load_recording(a.dump)
    dirs = probe(samples, a.dir)
    clock = game_hours(probe(samples, a.clock), a.clock_unit)
    day0 = day_start_jd(parse_date(a.date), a.tz)
    if a.body == "sun":
        f = make_sun(a.model, a.lat, a.lon, a.tz, a.decl, a.noon)

        def body(jd):
            p = f(jd)
            return p["el"], p["az"]
    else:
        def body(jd):
            return moon_topo(jd, a.lat, a.lon)
    tol = a.tol if a.tol is not None else (0.5 if a.body == "sun" else 1.0)
    seps, del_el, del_az = [], [], []
    worst = (None, -1.0)
    for d, h in zip(dirs, clock):
        if not is_vec(d) or h is None:
            continue
        el, az = body(day0 + h / 24)
        if el < a.min_elev:
            continue
        rec = [-c for c in d] if a.travel else d
        sep = angle_between(rec, direction(el, az, a.frame, a.north_offset))
        rel, raz = el_az(rec, a.frame, a.north_offset)
        seps.append(sep)
        del_el.append(rel - el)
        if el < 85:
            del_az.append(wrap180(raz - az))
        if sep > worst[1]:
            worst = (h, sep)
    if len(seps) < 3:
        raise NotAssessed(f"fewer than 3 samples with the {a.body} above {a.min_elev} deg")
    return [metric(f"{a.body}_direction_error_deg", rnd(max(seps), 4), f"≤ {tol}",
                   max(seps) <= tol, p95_deg=rnd(percentile(seps, 0.95), 4), samples=len(seps),
                   worst_at_game_h=rnd(worst[0] % 24, 4),
                   mean_elevation_error_deg=rnd(sum(del_el) / len(del_el), 4),
                   mean_azimuth_error_deg=rnd(sum(del_az) / len(del_az), 4) if del_az else None)]


def step(u, v, mode, eps):
    """Change between two samples (scalars or [r, g, b]); the largest channel for vectors."""
    us = u if isinstance(u, list) else [u]
    vs = v if isinstance(v, list) else [v]
    out = 0.0
    for p, q in zip(us, vs):
        p, q = float(p), float(q)
        if mode == "abs":
            d = abs(q - p)
        elif mode == "rel":
            d = abs(q - p) / max(abs(p), abs(q), eps)
        else:
            d = abs(math.log2((max(q, 0.0) + eps) / (max(p, 0.0) + eps)))
        out = max(out, d)
    return out


def measure_curve(a):
    times, samples = load_recording(a.dump)
    vals = probe(samples, a.value)
    if a.per == "game-min":
        xs = [None if h is None else h * 60
              for h in game_hours(probe(samples, a.clock), a.clock_unit)]
        window = a.window if a.window is not None else 1.0
        gap = a.max_gap_min
        unit_name = "game min"
    else:
        xs = list(times)
        window = a.window if a.window is not None else 0.5
        gap = float("inf")
        unit_name = "real s"
    pts = [(x, v) for x, v in zip(xs, vals) if x is not None and v is not None]
    if len(pts) < 3:
        raise NotAssessed("fewer than 3 samples")
    worst, at, skips, checked = 0.0, None, 0, 0
    j = 0
    for i in range(len(pts)):
        j = max(j, i + 1)
        while j < len(pts) and pts[j][0] - pts[i][0] < window:
            j += 1
        if j >= len(pts):
            break
        dx = pts[j][0] - pts[i][0]
        if dx > gap:
            skips += 1
            continue
        rate = step(pts[i][1], pts[j][1], a.mode, a.eps) / dx
        checked += 1
        if rate > worst:
            worst, at = rate, pts[i][0]
    if checked == 0:
        raise NotAssessed(f"recording shorter than one {window} {unit_name} window")
    at_text = rnd((at / 60) % 24, 4) if a.per == "game-min" and at is not None else rnd(at, 3)
    return [metric(f"{a.value}_max_rate_per_{a.per}", rnd(worst, 5), f"≤ {a.max_rate} ({a.mode})",
                   worst <= a.max_rate, worst_at=at_text, windows=checked, skipped_gaps=skips)]


def measure_handover(a):
    times, samples = load_recording(a.dump)
    sun = probe(samples, a.sun)
    moon = probe(samples, a.moon)
    rows = [(t, float(s), float(m)) for t, s, m in zip(times, sun, moon)
            if s is not None and m is not None]
    if len(rows) < 3:
        raise NotAssessed("fewer than 3 samples with both lights")
    if a.floor is not None:
        floor = a.floor
    else:
        night = [m for _, s, m in rows if m > s]
        if not night:
            raise NotAssessed("the moon is never the key light in this recording; pass --floor")
        floor = a.floor_frac * median(night)
    t_min, s_min, m_min = min(rows, key=lambda r: r[1] + r[2])
    out = [metric("key_light_min", rnd(s_min + m_min, 5), f"≥ {rnd(floor, 5)}",
                  s_min + m_min >= floor, at_s=rnd(t_min, 3))]
    if a.sun_shadow and a.moon_shadow:
        ss = probe(samples, a.sun_shadow)
        ms = probe(samples, a.moon_shadow)
        overlap, switches, last = 0.0, [], None
        for i, (t, s_on, m_on) in enumerate(zip(times, ss, ms)):
            dt_s = times[i + 1] - t if i + 1 < len(times) else 0.0
            if s_on and m_on:
                overlap += dt_s
            caster = "both" if s_on and m_on else "sun" if s_on else "moon" if m_on else None
            if caster in ("sun", "moon"):
                if last is not None and caster != last:
                    switches.append(t)
                last = caster
        flicker = sum(1 for p, q in zip(switches, switches[1:]) if q - p < a.min_hold_s)
        out.append(metric("two_shadow_casters_s", rnd(overlap, 3), f"≤ {a.max_overlap_s}",
                          overlap <= a.max_overlap_s))
        out.append(metric("shadow_caster_flicker", flicker, f"0 switches within {a.min_hold_s} s",
                          flicker == 0, switches=len(switches)))
    return out


def measure_clock(a):
    times, samples = load_recording(a.dump)
    hours = game_hours(probe(samples, a.clock), a.clock_unit)
    pts = [(t, h) for t, h in zip(times, hours) if h is not None]
    if len(pts) < 3:
        raise NotAssessed("fewer than 3 clock samples")
    back, skips = 0, 0
    sums = {"day": [0.0, 0.0], "night": [0.0, 0.0]}
    for (t0, h0), (t1, h1) in zip(pts, pts[1:]):
        dt_s, dg_s = t1 - t0, (h1 - h0) * 3600
        if dg_s < -1e-6:
            back += 1
            continue
        part = "day" if a.sunrise <= h0 % 24 < a.sunset else "night"
        expected = a.scale * (a.night_speed if part == "night" else 1.0)
        if dt_s <= 0:
            continue
        if dg_s > max(10 * expected * dt_s, 60.0):
            skips += 1
            continue
        sums[part][0] += dg_s
        sums[part][1] += dt_s
    out = [metric("clock_backward_steps", back, "0", back == 0, skips=skips)]
    for part, (game_s, real_s) in sums.items():
        if real_s < 1.0:
            continue
        expected = a.scale * (a.night_speed if part == "night" else 1.0)
        rate = game_s / real_s
        err = abs(rate / expected - 1)
        out.append(metric(f"clock_scale_{part}", rnd(rate, 4), f"{rnd(expected, 4)} ± {a.tol:.1%}",
                          err <= a.tol, real_s=rnd(real_s, 2)))
    if len(out) == 1:
        raise NotAssessed("less than 1 s of real time between clock samples")
    return out


def measure_stars(a):
    _, samples = load_recording(a.dump)
    vecs = probe(samples, a.star)
    clock = game_hours(probe(samples, a.clock), a.clock_unit)
    la = a.lat * D2R
    pts = []
    for v, h in zip(vecs, clock):
        if not is_vec(v) or h is None:
            continue
        e, u, n = from_frame(unit(v), a.frame)
        if a.north_offset:
            az = math.atan2(e, n) - a.north_offset * D2R
            ch = math.hypot(e, n)
            e, n = ch * math.sin(az), ch * math.cos(az)
        sin_dec = math.sin(la) * u + math.cos(la) * n
        ha = math.degrees(math.atan2(-e, math.cos(la) * u - math.sin(la) * n))
        pts.append((h, ha, math.degrees(math.asin(max(-1.0, min(1.0, sin_dec))))))
    if len(pts) < 10:
        raise NotAssessed("fewer than 10 star samples")
    hs, has, off, prev = [], [], 0.0, None
    for h, ha, _ in pts:
        if prev is not None:
            d = ha + off - prev
            off -= 360 * round(d / 360)
        hs.append(h)
        has.append(ha + off)
        prev = ha + off
    n = len(hs)
    mh, ma = sum(hs) / n, sum(has) / n
    sxx = sum((h - mh) ** 2 for h in hs)
    if sxx <= 0:
        raise NotAssessed("the game clock did not advance")
    rate = sum((h - mh) * (x - ma) for h, x in zip(hs, has)) / sxx
    expected = 360 / a.period_h
    decs = [p[2] for p in pts]
    spread = max(decs) - min(decs)
    return [metric("star_rate_deg_per_game_h", rnd(rate, 5), f"{rnd(expected, 5)} ± {a.tol:.2%}",
                   abs(rate / expected - 1) <= a.tol, samples=n),
            metric("star_declination_spread_deg", rnd(spread, 4), f"≤ {a.tol_deg}",
                   spread <= a.tol_deg, declination_deg=rnd(sum(decs) / n, 3))]


# ---------- CLI ----------

def add_sky_args(p, required=False):
    p.add_argument("--lat", type=float, required=required)
    p.add_argument("--lon", type=float, required=required)
    p.add_argument("--date", required=required)
    p.add_argument("--tz", type=float, default=0.0)
    p.add_argument("--model", choices=["noaa", "fourier", "arc"], default="noaa")
    p.add_argument("--decl", type=float, default=0.0)
    p.add_argument("--noon", type=float, default=12.0)
    p.add_argument("--frame", choices=["godot", "unity", "unreal"], default="godot")
    p.add_argument("--north-offset", type=float, default=0.0)


def add_clock(p):
    p.add_argument("--clock", required=True)
    p.add_argument("--clock-unit", choices=["h", "min", "s"], default="h")


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("predict")
    pr.add_argument("case", choices=["sun", "twilight", "moon", "stars", "light", "time"])
    add_sky_args(pr)
    pr.add_argument("--time")
    for name in ("elapsed-h", "scale", "elev", "day-min", "span-h", "skip-s"):
        pr.add_argument(f"--{name}", type=float)
    pr.add_argument("--extinction", type=float, default=0.267)
    pr.add_argument("--sunrise", type=float, default=6.0)
    pr.add_argument("--sunset", type=float, default=18.0)
    pr.add_argument("--night-speed", type=float, default=1.0)
    pr.add_argument("--tol-deg", type=float, default=0.5)

    s = sub.add_parser("sun")
    s.add_argument("dump")
    s.add_argument("--dir", required=True)
    add_clock(s)
    add_sky_args(s, required=True)
    s.add_argument("--body", choices=["sun", "moon"], default="sun")
    s.add_argument("--travel", action="store_true")
    s.add_argument("--min-elev", type=float, default=0.0)
    s.add_argument("--tol", type=float)

    c = sub.add_parser("curve")
    c.add_argument("dump")
    c.add_argument("--value", required=True)
    c.add_argument("--clock")
    c.add_argument("--clock-unit", choices=["h", "min", "s"], default="h")
    c.add_argument("--mode", choices=["abs", "rel", "stops"], default="abs")
    c.add_argument("--max-rate", type=float, default=0.05)
    c.add_argument("--per", choices=["game-min", "real-s"], default="game-min")
    c.add_argument("--window", type=float)
    c.add_argument("--max-gap-min", type=float, default=10.0)
    c.add_argument("--eps", type=float, default=1e-4)

    h = sub.add_parser("handover")
    h.add_argument("dump")
    h.add_argument("--sun", required=True)
    h.add_argument("--moon", required=True)
    h.add_argument("--floor", type=float)
    h.add_argument("--floor-frac", type=float, default=0.5)
    h.add_argument("--sun-shadow")
    h.add_argument("--moon-shadow")
    h.add_argument("--max-overlap-s", type=float, default=0.5)
    h.add_argument("--min-hold-s", type=float, default=5.0)

    k = sub.add_parser("clock")
    k.add_argument("dump")
    add_clock(k)
    k.add_argument("--scale", type=float, required=True)
    k.add_argument("--sunrise", type=float, default=6.0)
    k.add_argument("--sunset", type=float, default=18.0)
    k.add_argument("--night-speed", type=float, default=1.0)
    k.add_argument("--tol", type=float, default=0.02)

    st = sub.add_parser("stars")
    st.add_argument("dump")
    st.add_argument("--star", required=True)
    add_clock(st)
    st.add_argument("--lat", type=float, required=True)
    st.add_argument("--frame", choices=["godot", "unity", "unreal"], default="godot")
    st.add_argument("--north-offset", type=float, default=0.0)
    st.add_argument("--period-h", type=float, default=SIDEREAL_DAY_S / 3600)
    st.add_argument("--tol", type=float, default=0.001)
    st.add_argument("--tol-deg", type=float, default=0.5)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "predict":
            print(json.dumps(predict(a), ensure_ascii=False))
            return 0
        if a.cmd == "curve" and a.per == "game-min" and not a.clock:
            raise ValueError("curve --per game-min needs --clock")
        metrics = {"sun": measure_sun, "curve": measure_curve, "handover": measure_handover,
                   "clock": measure_clock, "stars": measure_stars}[a.cmd](a)
    except NotAssessed as exc:
        print(json.dumps({"verdict": "NOT ASSESSED", "reason": str(exc), "metrics": []},
                         ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"verdict": "ERROR", "reason": f"{type(exc).__name__}: {exc}"}))
        return 2
    verdict = "FAIL" if any(m["verdict"] == "FAIL" for m in metrics) else "PASS"
    print(json.dumps({"verdict": verdict, "metrics": metrics}, ensure_ascii=False))
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
