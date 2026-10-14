"""Tests for plugins/kiln/skills/sky/scripts/sky_check.py (stdlib only).

Reference values (fetched 2026-10-11):
- JPL Horizons (ssd.jpl.nasa.gov/api/horizons.api): airless and refracted apparent azimuth and
  elevation of the Sun (10) and Moon (301) from a geodetic site at sea level, illuminated fraction,
  local apparent sidereal time, 1-minute tables for twilight crossings and 1-second tables for
  transit (solar noon).
- NOAA GML solar calculator tables (gml.noaa.gov/grad/solcalc/table.php?lat=..&lon=..&year=2026):
  sunrise and sunset, local time rounded to the minute.
- F. Espenak, Phases of the Moon 2001-2100 (astropixels.com/ephemeris/moon/phases2001gmt.html).
- Wikipedia: Equation of time, Sunlight, Exposure value; game wikis for time scales.
"""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "sky",
                      "scripts", "sky_check.py")
D2R = math.pi / 180


def write(data):
    fd, path = tempfile.mkstemp(prefix="kiln-sky-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *map(str, args)], capture_output=True,
                       text=True, timeout=60, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


def pred(*args):
    code, res = run("predict", *args)
    assert code == 0, res
    return res["prediction"]


def recording(samples, hz=60):
    n = max(len(v) for v in samples.values())
    return write({"physics_ticks_per_second": hz, "ticks": list(range(n)), "samples": samples})


def minutes(text):
    """'HH:MM' or 'HH:MM:SS' (optionally ' +1d') -> minutes."""
    clock, _, day = text.partition(" ")
    parts = [float(p) for p in clock.split(":")]
    m = parts[0] * 60 + parts[1] + (parts[2] / 60 if len(parts) > 2 else 0)
    return m + (1440 * int(day[:-1]) if day else 0)


def godot_vec(el, az):
    """Unit vector toward (elevation, azimuth from north clockwise): x east, y up, -z north."""
    ce = math.cos(el * D2R)
    return [ce * math.sin(az * D2R), math.sin(el * D2R), -ce * math.cos(az * D2R)]


def altaz(lat, dec, ha):
    la, de, h = lat * D2R, dec * D2R, ha * D2R
    el = math.asin(math.sin(la) * math.sin(de) + math.cos(la) * math.cos(de) * math.cos(h))
    az = math.atan2(math.sin(h), math.cos(h) * math.sin(la) - math.tan(de) * math.cos(la))
    return math.degrees(el), (math.degrees(az) + 180) % 360


# JPL Horizons, airless apparent topocentric (UT): lat, lon, date, local time, tz, elev, azimuth
SUN_POINTS = [
    (45, 0, "2026-06-21", "12:00", 0, 68.4338, 178.8661),
    (45, 0, "2026-06-21", "06:00", 0, 16.0352, 72.6724),
    (45, 0, "2026-03-20", "15:30", 0, 26.6438, 239.9053),
    (60, 0, "2026-12-21", "12:00", 0, 6.5597, 180.4466),
    (0, 0, "2026-03-20", "09:00", 0, 43.1300, 90.1301),
    (60, 25, "2026-09-23", "17:00", 0, -6.1715, 280.2292),
    (-33.87, 151.21, "2026-01-15", "14:00", 11, 72.3155, 312.4910),   # 03:00 UT, Sydney AEDT
    (40.015, -105.27, "2026-07-04", "14:00", -6, 69.3054, 217.8443),  # 20:00 UT, Boulder MDT
]

# NOAA table.php 2026, local time (DST where the table marks it): sunrise, sunset
NOAA_RISE_SET = [
    (45, 0, "2026-06-21", 2, "06:13", "21:50"),
    (45, 0, "2026-12-21", 1, "08:35", "17:21"),
    (60, 25, "2026-06-21", 3, "03:56", "22:48"),
    (60, 25, "2026-12-21", 2, "09:22", "15:14"),
    (-33.87, 151.21, "2026-01-15", 11, "05:59", "20:09"),
    (-33.87, 151.21, "2026-06-21", 10, "07:00", "16:54"),
    (40.015, -105.27, "2026-07-04", -6, "05:38", "20:33"),
    (0, 0, "2026-03-20", 0, "06:04", "18:11"),
    (70, 25, "2026-02-11", 1, "08:14", "14:56"),
]


class PredictSun(unittest.TestCase):
    def test_position_matches_horizons(self):
        for lat, lon, date, time, tz, el, az in SUN_POINTS:
            p = pred("sun", "--lat", lat, "--lon", lon, "--date", date, "--time", time, "--tz", tz)
            self.assertAlmostEqual(p["elevation_deg"], el, delta=0.02, msg=(lat, date, time))
            self.assertAlmostEqual(p["azimuth_deg"], az, delta=0.02, msg=(lat, date, time))

    def test_refraction_matches_horizons(self):
        # Horizons refracted apparent elevation: 6.6899 (60N Dec 21 12 UT), 16.0926 (45N Jun 21 6 UT)
        p = pred("sun", "--lat", 60, "--lon", 0, "--date", "2026-12-21", "--time", "12:00")
        self.assertAlmostEqual(p["elevation_refracted_deg"], 6.6899, delta=0.01)
        p = pred("sun", "--lat", 45, "--lon", 0, "--date", "2026-06-21", "--time", "06:00")
        self.assertAlmostEqual(p["elevation_refracted_deg"], 16.0926, delta=0.01)

    def test_short_fourier_series_within_half_degree(self):
        # the NOAA short series drifts ~1 day of declination near the 2026 equinoxes: the sun's
        # direction stays within 0.5 deg of Horizons (0.453 worst), azimuth alone may not near zenith
        for lat, lon, date, time, tz, el, az in SUN_POINTS:
            p = pred("sun", "--model", "fourier", "--lat", lat, "--lon", lon, "--date", date,
                     "--time", time, "--tz", tz)
            a, b = godot_vec(p["elevation_deg"], p["azimuth_deg"]), godot_vec(el, az)
            sep = math.degrees(math.acos(min(1.0, sum(x * y for x, y in zip(a, b)))))
            self.assertLessEqual(sep, 0.5, msg=(lat, date, time))

    def test_sunrise_sunset_match_noaa_tables(self):
        for lat, lon, date, tz, rise, sett in NOAA_RISE_SET:
            p = pred("sun", "--lat", lat, "--lon", lon, "--date", date, "--tz", tz)
            self.assertAlmostEqual(minutes(p["sunrise"]), minutes(rise), delta=1.0, msg=(lat, date))
            self.assertAlmostEqual(minutes(p["sunset"]), minutes(sett), delta=1.0, msg=(lat, date))

    def test_solar_noon_matches_horizons_transit(self):
        # Horizons 1 s tables, azimuth crossing 180: 11:58:03.9 UT, 12:01:49.0 UT, 02:04:24.5 UT
        for lat, lon, date, tz, noon in ((60, 0, "2026-12-21", 0, "11:58:03.9"),
                                         (45, 0, "2026-06-21", 0, "12:01:49.0"),
                                         (-33.87, 151.21, "2026-01-15", 11, "13:04:24.5")):
            p = pred("sun", "--lat", lat, "--lon", lon, "--date", date, "--tz", tz)
            self.assertAlmostEqual(minutes(p["solar_noon"]) * 60, minutes(noon) * 60, delta=2.0)

    def test_equation_of_time_extremes(self):
        # Wikipedia, Equation of time: -14 min 6 s around 11 Feb, +16 min 33 s around 3 Nov
        feb = pred("sun", "--lat", 0, "--lon", 0, "--date", "2026-02-11", "--time", "12:00")
        nov = pred("sun", "--lat", 0, "--lon", 0, "--date", "2026-11-03", "--time", "12:00")
        self.assertAlmostEqual(feb["eqtime_min"], -14.1, delta=0.3)
        self.assertAlmostEqual(nov["eqtime_min"], 16.55, delta=0.3)

    def test_polar_day_and_night(self):
        # NOAA table at 70N 25E shows no sunrise or sunset on 21 June and 21 December
        june = pred("sun", "--lat", 70, "--lon", 25, "--date", "2026-06-21", "--tz", 2)
        dec = pred("sun", "--lat", 70, "--lon", 25, "--date", "2026-12-21", "--tz", 1)
        self.assertEqual((june["polar"], june["day_length_h"], june["sunrise"]), ("day", 24.0, None))
        self.assertEqual((dec["polar"], dec["day_length_h"]), ("night", 0.0))
        self.assertAlmostEqual(dec["noon_elevation_deg"], 90 - 70 - 23.44, delta=0.05)

    def test_day_length_60n_june(self):
        # NOAA: 03:56 - 22:48 local = 18 h 52 min
        p = pred("sun", "--lat", 60, "--lon", 25, "--date", "2026-06-21", "--tz", 3)
        self.assertAlmostEqual(p["day_length_h"], 18 + 52 / 60, delta=2 / 60)

    def test_stylised_arc_geometry(self):
        # equator, declination 0: sun rises due east at 06:00, 45 deg at 09:00, zenith at noon;
        # day length from -0.833 deg is 2 * 90.833 / 15 h exactly
        p6 = pred("sun", "--model", "arc", "--lat", 0, "--lon", 0, "--date", "2026-01-01",
                  "--time", "06:00")
        p9 = pred("sun", "--model", "arc", "--lat", 0, "--lon", 0, "--date", "2026-01-01",
                  "--time", "09:00")
        self.assertAlmostEqual(p6["elevation_deg"], 0.0, places=3)
        self.assertAlmostEqual(p6["azimuth_deg"], 90.0, places=3)
        self.assertAlmostEqual(p9["elevation_deg"], 45.0, places=3)
        self.assertAlmostEqual(p6["day_length_h"], 2 * 90.833 / 15, places=3)
        self.assertEqual(p6["solar_noon"], "12:00:00")
        tilt = pred("sun", "--model", "arc", "--lat", 30, "--decl", 10, "--lon", 0, "--date",
                    "2026-01-01", "--time", "12:00")
        self.assertAlmostEqual(tilt["elevation_deg"], 90 - 30 + 10, places=3)

    def test_engine_frames(self):
        args = ["--model", "arc", "--lat", 0, "--lon", 0, "--date", "2026-01-01", "--time", "06:00"]
        east = {f: pred("sun", *args, "--frame", f)["toward_sun"] for f in ("godot", "unity", "unreal")}
        for f, want in (("godot", [1, 0, 0]), ("unity", [1, 0, 0]), ("unreal", [0, 1, 0])):
            for got, w in zip(east[f], want):
                self.assertAlmostEqual(got, w, places=4)
        south = pred("sun", "--model", "arc", "--lat", 30, "--lon", 0, "--date", "2026-01-01",
                     "--time", "12:00")["toward_sun"]  # el 60 due south: Godot +z is south
        for got, w in zip(south, [0, math.sin(60 * D2R), 0.5]):
            self.assertAlmostEqual(got, w, places=4)
        rotated = pred("sun", *args, "--north-offset", 90)["toward_sun"]  # east shows as south
        for got, w in zip(rotated, [0, 0, 1]):
            self.assertAlmostEqual(got, w, places=4)


class PredictTwilight(unittest.TestCase):
    def check(self, p, want):
        for key, value in want.items():
            self.assertAlmostEqual(minutes(p[key]), minutes(value), delta=0.25, msg=key)

    def test_45n_june_solstice_matches_horizons(self):
        # Horizons airless crossings (UT) of -0.833, -6, -12, -18 deg, 45N 0E, 2026-06-21
        p = pred("twilight", "--lat", 45, "--lon", 0, "--date", "2026-06-21")
        self.check(p, {"sunrise": "04:13:16", "sunset": "19:50:22", "civil_dawn": "03:35:49",
                       "civil_dusk": "20:27:49", "nautical_dawn": "02:46:00",
                       "nautical_dusk": "21:17:37", "astronomical_dawn": "01:39:49",
                       "astronomical_dusk": "22:23:48"})
        self.assertEqual(p["darkest"], "full night")

    def test_60n_equinox_matches_horizons(self):
        p = pred("twilight", "--lat", 60, "--lon", 25, "--date", "2026-03-20")
        self.check(p, {"sunrise": "04:22:04", "sunset": "16:34:14", "civil_dawn": "03:40:35",
                       "civil_dusk": "17:15:55", "nautical_dawn": "02:50:47",
                       "nautical_dusk": "18:06:02", "astronomical_dawn": "01:56:44",
                       "astronomical_dusk": "19:00:38"})

    def test_white_night_at_60n(self):
        # Horizons: lowest sun -6.5648 deg at 00:02 UT on 2026-06-21, 60N 0E: nautical all night
        p = pred("twilight", "--lat", 60, "--lon", 0, "--date", "2026-06-21")
        self.assertAlmostEqual(p["min_elevation_deg"], -6.5648, delta=0.01)
        self.assertIsNone(p["nautical_dawn"])
        self.assertEqual(p["darkest"], "nautical twilight all night")
        self.check(p, {"civil_dawn": "00:49:10", "civil_dusk": "23:14:26"})

    def test_equator_civil_twilight_minutes(self):
        # Horizons 0N 0E 2026-03-20: -6 deg at 05:43.52, -0.833 deg at 06:04.19 -> 20.67 min
        p = pred("twilight", "--lat", 0, "--lon", 0, "--date", "2026-03-20")
        self.assertAlmostEqual(p["civil_twilight_min"][0], 20.67, delta=0.2)


class PredictMoon(unittest.TestCase):
    def test_position_and_fraction_match_horizons(self):
        # Horizons, Moon from 45N 0E, airless topocentric az/el and illuminated fraction
        for date, time, el, az, illum in (("2026-01-03", "10:03", -13.6287, 332.1128, 0.99915),
                                          ("2026-01-18", "19:52", -34.4092, 269.0037, 0.00109),
                                          ("2026-03-26", "12:00", 9.3731, 62.2352, 0.58637),
                                          ("2026-05-01", "21:00", 12.4043, 137.5292, 0.99754),
                                          ("2026-07-29", "00:00", 21.0529, 184.7774, 0.99532),
                                          ("2026-10-11", "12:00", 29.1043, 174.9948, 0.01019)):
            p = pred("moon", "--date", date, "--time", time, "--lat", 45, "--lon", 0)
            self.assertAlmostEqual(p["elevation_deg"], el, delta=0.3, msg=date)
            self.assertAlmostEqual(p["azimuth_deg"], az, delta=0.3, msg=date)
            self.assertAlmostEqual(p["illuminated_fraction"], illum, delta=0.01, msg=date)

    def test_next_phases_match_espenak(self):
        # Espenak 2026 (UT): LQ Jan 10 15:48, new Jan 18 19:52, FQ Jan 26 04:47, full Feb 1 22:09;
        # LQ Oct 3 13:25, new Oct 10 15:50, FQ Oct 18 16:13, full Oct 26 04:12
        for date, want in (("2026-01-04", {"next_last_quarter": "2026-01-10T15:48",
                                           "next_new": "2026-01-18T19:52",
                                           "next_first_quarter": "2026-01-26T04:47",
                                           "next_full": "2026-02-01T22:09"}),
                           ("2026-10-01", {"next_last_quarter": "2026-10-03T13:25",
                                           "next_new": "2026-10-10T15:50",
                                           "next_first_quarter": "2026-10-18T16:13",
                                           "next_full": "2026-10-26T04:12"})):
            p = pred("moon", "--date", date, "--time", "00:00")
            for key, value in want.items():
                got = p[key]
                self.assertEqual(got[:8], value[:8], msg=key)
                d_got = int(got[8:10]) * 1440 + minutes(got[11:16])
                d_want = int(value[8:10]) * 1440 + minutes(value[11:16])
                self.assertLessEqual(abs(d_got - d_want), 45, msg=(key, got, value))

    def test_mean_month_age_within_a_day(self):
        # the game method (age mod 29.530589 d) at Espenak full moons: within 1 day of 14.77 d
        for date, time in (("2026-01-03", "10:03"), ("2026-10-26", "04:12"), ("2026-07-29", "14:36")):
            p = pred("moon", "--date", date, "--time", time)
            self.assertAlmostEqual(p["mean_age_days"], 29.530589 / 2, delta=1.0, msg=date)
            self.assertEqual(p["phase_name"], "full")

    def test_brightness_vs_phase_krisciunas_schaefer(self):
        # K&S 1991: I* ~ 10^(-0.4 (3.84 + 0.026|a| + 4e-9 a^4)); Horizons 58.637 % lit -> a = 80.05
        a = math.degrees(math.acos(2 * 0.58637 - 1))
        want = 10 ** (-0.4 * (0.026 * a + 4e-9 * a ** 4))
        p = pred("moon", "--date", "2026-03-26", "--time", "12:00", "--lat", 45, "--lon", 0)
        self.assertAlmostEqual(p["brightness_vs_full"], want, delta=0.01)
        self.assertLess(p["brightness_vs_full"], 0.15)  # half-lit moon gives ~1/8 of full light
        self.assertEqual(p["rise_delay_min_per_day"], 50.5)  # 1440*P/(P-1) - 1440


class PredictStars(unittest.TestCase):
    def test_sidereal_rotation(self):
        # sidereal day 86164.0905 s: 24 solar hours turn the sky 360.9856 deg
        p = pred("stars", "--elapsed-h", 24, "--lat", 45)
        self.assertAlmostEqual(p["rotation_deg"], 0.9856, places=3)
        self.assertAlmostEqual(p["deg_per_hour"], 15.04107, places=4)
        self.assertAlmostEqual(p["gain_per_solar_day_s"], 235.9095, places=3)
        for got, want in zip(p["pole_axis"], [0, math.sqrt(0.5), -math.sqrt(0.5)]):
            self.assertAlmostEqual(got, want, places=4)
        south = pred("stars", "--elapsed-h", 1, "--lat", -33.87)
        self.assertEqual(south["pole_azimuth_deg"], 180.0)

    def test_local_sidereal_time_matches_horizons(self):
        # Horizons local apparent sidereal time: 17.9472453 h (0E, 2026-06-21 00 UT),
        # 21.5240584 h (25E, 2026-10-11 18:30 UT)
        p = pred("stars", "--elapsed-h", 0, "--date", "2026-06-21", "--time", "00:00", "--lon", 0)
        self.assertAlmostEqual(p["lst_h"], 17.9472453, delta=0.0002)
        p = pred("stars", "--elapsed-h", 0, "--date", "2026-10-11", "--time", "18:30", "--lon", 25)
        self.assertAlmostEqual(p["lst_h"], 21.5240584, delta=0.0002)


class PredictLight(unittest.TestCase):
    def test_zenith_sun_and_air_mass(self):
        # Wikipedia Sunlight: 128,000 lx outside, ~98,000 lx at sea level on a perpendicular surface
        p = pred("light", "--elev", 90)
        self.assertAlmostEqual(p["direct_normal_lux"], 98000, delta=150)
        self.assertAlmostEqual(p["ev100_horizontal"], math.log2(p["direct_horizontal_lux"] / 2.5),
                               places=2)  # E = 2.5 * 2^EV (Wikipedia Exposure value)
        low = pred("light", "--elev", 5)
        z = 85.0
        m = 1 / (math.cos(z * D2R) + 0.50572 * (96.07995 - z) ** -1.6364)  # Kasten & Young 1989
        self.assertAlmostEqual(low["air_mass"], m, places=3)
        self.assertAlmostEqual(low["direct_horizontal_lux"],
                               128000 * math.exp(-0.267 * m) * math.sin(5 * D2R), delta=1)

    def test_colour_warms_toward_horizon(self):
        ccts = [pred("light", "--elev", e)["cct_k"] for e in (-1, 2, 5, 10, 30, 60, 90)]
        self.assertEqual(ccts, sorted(ccts))
        self.assertEqual(ccts[0], 1850)  # Godot Light3D docs: ~1850 K at sunrise/sunset


class PredictTime(unittest.TestCase):
    def test_shipped_games(self):
        # Minecraft wiki: 24000 ticks at 20 tps = 20 min, 1000 ticks per game hour = 50 s
        mc = pred("time", "--day-min", 20)
        self.assertEqual((mc["scale_day"], mc["real_s_per_game_hour"]), (72.0, 50.0))
        self.assertAlmostEqual(mc["sun_deg_per_real_s"], 0.3, places=5)
        # UESP Skyrim: timescale 20 -> 72 real minutes per game day
        self.assertEqual(pred("time", "--scale", 20)["real_min_per_game_day"], 72.0)
        # Zelda wiki BotW: one game hour per real minute -> 24 min day
        self.assertEqual(pred("time", "--day-min", 24)["real_s_per_game_hour"], 60.0)
        # Stardew wiki: 10 game minutes per 7 real seconds; 6am-2am (20 h) takes ~14 real minutes
        sv = pred("time", "--scale", 600 / 7, "--span-h", 20)
        self.assertAlmostEqual(sv["real_s_for_span"], 840.0, places=1)

    def test_fast_nights(self):
        # 48 min day, daylight 06-20, nights twice as fast: s = (14 + 10/2) * 3600 / 2880
        p = pred("time", "--day-min", 48, "--sunrise", 6, "--sunset", 20, "--night-speed", 2)
        self.assertAlmostEqual(p["scale_day"], 23.75, places=4)
        self.assertAlmostEqual(p["real_min_daytime"] + p["real_min_night"], 48.0, places=2)
        self.assertAlmostEqual(p["real_min_night"], 10 * 60 / 47.5, places=2)

    def test_clock_resolution_and_bad_input(self):
        p = pred("time", "--day-min", 20, "--tol-deg", 0.5)
        self.assertEqual(p["clock_resolution_game_min"], 2.0)  # 0.5 deg / 15 deg per game hour
        self.assertAlmostEqual(p["clock_resolution_real_s"], 0.5 / 0.3, places=2)
        self.assertEqual(run("predict", "time", "--day-min", 20, "--scale", 72)[0], 2)
        self.assertEqual(run("predict", "sun", "--lat", 95, "--lon", 0, "--date", "2026-01-01")[0], 2)


# Horizons hourly Sun, 45N 0E, 2026-06-21 (UT = game clock): hour, azimuth, elevation
SUN_DAY = [(5, 62.8286, 6.2296), (6, 72.6724, 16.0352), (7, 82.4189, 26.3777),
           (8, 92.7798, 36.9585), (9, 104.8942, 47.4245), (10, 120.8774, 57.1958),
           (11, 144.6070, 65.0345), (12, 178.8661, 68.4338), (13, 213.6039, 65.3983),
           (14, 237.9544, 57.7436), (15, 254.2766, 48.0439), (16, 266.5510, 37.5997),
           (17, 276.9793, 27.0146), (18, 286.7401, 16.6490), (19, 296.5619, 6.8021)]
# Horizons hourly Moon, 45N 0E, from 2026-07-28 21:00 UT (near full)
MOON_NIGHT = [(21, 143.8820, 12.1563), (22, 156.6168, 17.4041), (23, 170.4223, 20.4748),
              (0, 184.7774, 21.0529), (1, 198.9387, 19.0736), (2, 212.2556, 14.7532),
              (3, 224.4106, 8.4954), (4, 235.4336, 0.7549)]
SITE = ["--lat", 45, "--lon", 0, "--tz", 0]


class MeasureSun(unittest.TestCase):
    def test_sun_direction_against_horizons(self):
        clock = [h for h, _, _ in SUN_DAY]
        good = recording({"sun": [godot_vec(el, az) for _, az, el in SUN_DAY], "clock": clock})
        code, res = run("sun", good, "--dir", "sun", "--clock", "clock", "--date", "2026-06-21", *SITE)
        self.assertEqual(code, 0, res)
        self.assertLess(res["metrics"][0]["value"], 0.05)
        turned = recording({"sun": [godot_vec(el, az + 3) for _, az, el in SUN_DAY], "clock": clock})
        code, res = run("sun", turned, "--dir", "sun", "--clock", "clock", "--date", "2026-06-21",
                        *SITE)
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["mean_azimuth_error_deg"], 3.0, delta=0.05)
        self.assertEqual(run("sun", turned, "--dir", "sun", "--clock", "clock", "--date",
                             "2026-06-21", *SITE, "--north-offset", 3)[0], 0)

    def test_light_travel_direction_and_clock_units(self):
        travel = [[-c for c in godot_vec(el, az)] for _, az, el in SUN_DAY]
        seconds = [h * 3600 for h, _, _ in SUN_DAY]
        path = recording({"light_fwd": travel, "clock_s": seconds})
        args = ["--dir", "light_fwd", "--clock", "clock_s", "--clock-unit", "s", "--date",
                "2026-06-21", *SITE]
        self.assertEqual(run("sun", path, *args, "--travel")[0], 0)
        self.assertEqual(run("sun", path, *args)[0], 1)

    def test_moon_across_midnight(self):
        path = recording({"moon": [godot_vec(el, az) for _, az, el in MOON_NIGHT],
                          "clock": [h for h, _, _ in MOON_NIGHT]})
        args = ["--dir", "moon", "--clock", "clock", "--date", "2026-07-28", *SITE]
        code, res = run("sun", path, *args, "--body", "moon")
        self.assertEqual(code, 0, res)
        self.assertLess(res["metrics"][0]["value"], 0.3)
        # judged as the sun, every sample is below the horizon: nothing to assess
        self.assertEqual(run("sun", path, *args)[1]["verdict"], "NOT ASSESSED")
        code, res = run("sun", path, *args, "--body", "moon", "--tz", 2)  # clock read as UTC+2
        self.assertEqual(code, 1)

    def test_missing_probe_is_not_assessed(self):
        path = recording({"clock": [1, 2, 3]})
        code, res = run("sun", path, "--dir", "sun", "--clock", "clock", "--date", "2026-06-21",
                        *SITE)
        self.assertEqual((code, res["verdict"]), (0, "NOT ASSESSED"))


class MeasureCurve(unittest.TestCase):
    def day(self, n=7200):
        clock = [6 + 12 * i / n for i in range(n + 1)]
        return clock, [math.sin(math.pi * (h - 6) / 12) for h in clock]

    def test_smooth_curve_passes_and_a_pop_fails(self):
        clock, energy = self.day()
        code, res = run("curve", recording({"e": energy, "clock": clock}), "--value", "e",
                        "--clock", "clock", "--max-rate", 0.01)
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["metrics"][0]["value"], math.pi / 12 / 60, delta=2e-4)
        energy[3000:] = [e + 0.3 for e in energy[3000:]]
        code, res = run("curve", recording({"e": energy, "clock": clock}), "--value", "e",
                        "--clock", "clock", "--max-rate", 0.01)
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["worst_at"], clock[3000], delta=0.05)

    def test_colour_stops_and_sleep_skip(self):
        clock = [18 + i / 600 for i in range(601)] + [6 + 24 + i / 600 for i in range(601)]
        lux = [1000 * 2 ** (-6 * i / 600) for i in range(601)] + [10] * 601  # 6 stops per hour
        colour = [[1.0, 0.8 - 0.3 * i / 600, 0.6] for i in range(601)] + [[1, 0.5, 0.6]] * 601
        path = recording({"lux": lux, "col": colour, "clock": clock})
        code, res = run("curve", path, "--value", "lux", "--clock", "clock", "--mode", "stops",
                        "--max-rate", 0.2)
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["metrics"][0]["value"], 0.1, delta=0.005)  # 6 stops / 60 min
        self.assertEqual(res["metrics"][0]["skipped_gaps"] > 0, True)  # the sleep jump
        self.assertEqual(run("curve", path, "--value", "col", "--clock", "clock",
                             "--max-rate", 0.006)[0], 0)  # 0.3 over 60 game minutes

    def test_exposure_per_real_second(self):
        luma = [0.18] * 300 + [0.5] + [0.18] * 300  # one-frame flash in mean screen luminance
        path = recording({"luma": luma})
        self.assertEqual(run("curve", path, "--value", "luma", "--per", "real-s", "--mode", "stops",
                             "--window", 0.02, "--max-rate", 4)[0], 1)
        self.assertEqual(run("curve", recording({"luma": [0.18] * 601}), "--value", "luma",
                             "--per", "real-s", "--mode", "stops", "--max-rate", 4)[0], 0)


class MeasureHandover(unittest.TestCase):
    def dusk(self, moon_start, overlap_shadows=False, flicker=False):
        n = 600  # 10 s at 60 Hz
        sun = [max(0.0, 1 - i / 300) for i in range(n)]
        moon = [0.0 if i < moon_start else min(0.1, (i - moon_start) / 1000) for i in range(n)]
        sun_sh = [s > m or (overlap_shadows and m > 0) for s, m in zip(sun, moon)]
        moon_sh = [not s for s in sun_sh] if not overlap_shadows else [m > 0 for m in moon]
        if flicker:
            for i in range(320, 330):
                sun_sh[i], moon_sh[i] = True, False
        return recording({"sun": sun, "moon": moon, "sun_sh": sun_sh, "moon_sh": moon_sh})

    def test_crossfade_passes_and_dark_gap_fails(self):
        code, res = run("handover", self.dusk(200), "--sun", "sun", "--moon", "moon",
                        "--sun-shadow", "sun_sh", "--moon-shadow", "moon_sh")
        self.assertEqual(code, 0, res)
        code, res = run("handover", self.dusk(400), "--sun", "sun", "--moon", "moon")
        self.assertEqual(code, 1)  # sun gone at 300, moon starts at 400: key light 0
        self.assertEqual(res["metrics"][0]["value"], 0.0)

    def test_shadow_overlap_and_flicker(self):
        _, res = run("handover", self.dusk(200, overlap_shadows=True), "--sun", "sun", "--moon",
                     "moon", "--sun-shadow", "sun_sh", "--moon-shadow", "moon_sh")
        self.assertEqual({m["metric"]: m["verdict"] for m in res["metrics"]}["two_shadow_casters_s"],
                         "FAIL")
        _, res = run("handover", self.dusk(200, flicker=True), "--sun", "sun", "--moon", "moon",
                     "--sun-shadow", "sun_sh", "--moon-shadow", "moon_sh")
        self.assertEqual({m["metric"]: m["verdict"] for m in res["metrics"]}["shadow_caster_flicker"],
                         "FAIL")


class MeasureClock(unittest.TestCase):
    def test_scale_with_midnight_wrap(self):
        clock = [(23.5 + 72 * i / 60 / 3600) % 24 for i in range(6000)]  # 100 s at 60 Hz, 72x
        path = recording({"clock": clock})
        code, res = run("clock", path, "--clock", "clock", "--scale", 72)
        self.assertEqual(code, 0, res)
        self.assertEqual(run("clock", path, "--clock", "clock", "--scale", 60)[0], 1)

    def test_backward_step_and_sleep_skip(self):
        clock = [10 + 72 * i / 60 / 3600 for i in range(3000)]
        skip = clock[:1500] + [c + 8 for c in clock[1500:]]  # sleep: 8 game hours in one tick
        code, res = run("clock", recording({"clock": skip}), "--clock", "clock", "--scale", 72)
        self.assertEqual(code, 0, res)
        self.assertEqual(res["metrics"][0]["skips"], 1)
        back = clock[:1500] + [c - 0.5 for c in clock[1500:]]
        self.assertEqual(run("clock", recording({"clock": back}), "--clock", "clock", "--scale",
                             72)[0], 1)

    def test_fast_nights(self):
        clock, h = [], 17.9
        for _ in range(3000):
            clock.append(h)
            h += (72 if 6 <= h % 24 < 18 else 144) / 60 / 3600
        path = recording({"clock": clock})
        self.assertEqual(run("clock", path, "--clock", "clock", "--scale", 72, "--night-speed", 2)[0], 0)
        self.assertEqual(run("clock", path, "--clock", "clock", "--scale", 72)[0], 1)


class MeasureStars(unittest.TestCase):
    def dome(self, rate, lat=45, dec=30):
        hours = [20 + i * 0.05 for i in range(160)]  # 8 game hours
        return recording({"star": [godot_vec(*altaz(lat, dec, -40 + rate * (h - 20))) for h in hours],
                          "clock": hours})

    def test_sidereal_rate_and_axis(self):
        sidereal = 360 / 23.9344696
        path = self.dome(sidereal)
        code, res = run("stars", path, "--star", "star", "--clock", "clock", "--lat", 45)
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["metrics"][1]["declination_deg"], 30.0, places=2)
        # solar-day rate is 0.27 % slow: fails the default 0.1 %, passes with --period-h 24
        solar = self.dome(15.0)
        self.assertEqual(run("stars", solar, "--star", "star", "--clock", "clock", "--lat", 45)[0], 1)
        self.assertEqual(run("stars", solar, "--star", "star", "--clock", "clock", "--lat", 45,
                             "--period-h", 24)[0], 0)
        # a dome turning about the wrong axis (built for 30N, checked at 45N)
        tilted = self.dome(sidereal, lat=30)
        _, res = run("stars", tilted, "--star", "star", "--clock", "clock", "--lat", 45)
        self.assertEqual(res["metrics"][1]["verdict"], "FAIL")

    def test_backwards_sky_fails(self):
        path = self.dome(-360 / 23.9344696)
        self.assertEqual(run("stars", path, "--star", "star", "--clock", "clock", "--lat", 45)[0], 1)


if __name__ == "__main__":
    unittest.main()
