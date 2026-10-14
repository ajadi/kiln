"""Tests for plugins/kiln/skills/weather/scripts/weather_check.py (stdlib only)."""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "weather",
                      "scripts", "weather_check.py")


def write(data, suffix=".json"):
    fd, path = tempfile.mkstemp(prefix="kiln-weather-", suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        if isinstance(data, str):
            fh.write(data)
        else:
            json.dump(data, fh)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *map(str, args)], capture_output=True,
                       text=True, timeout=60, encoding="utf-8")
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None)


def predict(*args):
    code, res = run("predict", *args)
    assert code == 0, res
    return res["prediction"]


def recording(samples, hz=60):
    n = max(len(v) for v in samples.values())
    return write({"physics_ticks_per_second": hz, "ticks": list(range(n)), "samples": samples})


def strokes_series(starts, n=180, base=0.1, peak=0.6):
    """60 Hz luminance: each stroke is 2 frames at `peak` starting at a frame in `starts`."""
    luma = [base] * n
    for s in starts:
        luma[s] = luma[s + 1] = peak
    return luma


class PredictFog(unittest.TestCase):
    def test_fog_density_from_visibility(self):
        # Koschmieder: sigma = -ln(0.02)/200 = 3.912023/200 = 0.019560 1/m
        # MOR (5 %) = ln 20 / sigma = 2.995732/0.019560 = 153.16 m; HDRP mean free path 1/sigma
        # = 51.12 m; Unity Exp2 density = sqrt(3.912023)/200 = 0.0098894;
        # fog at 100 m = 1 - exp(-1.956) = 1 - sqrt(0.02) = 0.8586
        p = predict("fog", "--visibility", 200, "--at", 100)
        self.assertAlmostEqual(p["extinction_per_m"], 0.01956, places=5)
        self.assertEqual(p["godot_fog_density"], p["extinction_per_m"])
        self.assertEqual(p["godot_volumetric_fog_density"], p["extinction_per_m"])
        self.assertEqual(p["unity_exp_density"], p["extinction_per_m"])
        self.assertAlmostEqual(p["unity_exp2_density"], 0.009889, places=6)
        self.assertAlmostEqual(p["mor_5pct_m"], 153.16, places=1)
        self.assertAlmostEqual(p["hdrp_attenuation_distance_m"], 51.12, places=2)
        self.assertAlmostEqual(p["fog_amount_at"]["100"], 0.8586, places=4)

    def test_visibility_from_density(self):
        # density 0.01 1/m -> V = 3.912023/0.01 = 391.20 m
        self.assertAlmostEqual(predict("fog", "--density", 0.01)["visibility_m"], 391.2, places=1)

    def test_fog_needs_input(self):
        self.assertEqual(run("predict", "fog")[0], 2)


class PredictThunderFlash(unittest.TestCase):
    def test_thunder_delay(self):
        # c(20 C) = 331.3*sqrt(1 + 20/273.15) = 343.215 m/s; 1 km -> 2.9136 s (~3 s per km)
        p = predict("thunder", "--distance", 1000)
        self.assertAlmostEqual(p["speed_m_s"], 343.215, places=3)
        self.assertAlmostEqual(p["delay_s"], 2.9136, places=4)
        self.assertTrue(p["audible"])
        # 0 C: c = 331.3 m/s, 5 km -> 15.0921 s
        self.assertAlmostEqual(predict("thunder", "--distance", 5000, "--temp", 0)["delay_s"],
                               15.0921, places=4)
        # a 6 s delay at 20 C -> 6 * 343.2146 = 2059.29 m
        self.assertAlmostEqual(predict("thunder", "--delay", 6)["distance_m"], 2059.29, places=2)
        # beyond ~16 km (10 miles, NWS) no thunder is heard
        self.assertFalse(predict("thunder", "--distance", 20000)["audible"])

    def test_lightning_flicker_against_photosensitivity(self):
        # a real flash: 4 strokes 45 ms apart -> 4 pulses inside 1 s > 3 -> not photosafe
        p = predict("flash", "--strokes", 4, "--interval", 0.045)
        self.assertEqual(p["max_flashes_per_s"], 4)
        self.assertFalse(p["photosafe"])
        self.assertIsNone(p["safe_period_s"])
        # 3 strokes 50 ms apart every 0.8 s: [0, 1) holds 0, .05, .1, .8, .85, .9 -> 6
        self.assertEqual(predict("flash", "--strokes", 3, "--interval", 0.05, "--period",
                                 0.8)["max_flashes_per_s"], 6)
        # every 1.2 s: never more than 3; always safe from 1 + 0.1 = 1.1 s
        p = predict("flash", "--strokes", 3, "--interval", 0.05, "--period", 1.2)
        self.assertEqual(p["max_flashes_per_s"], 3)
        self.assertTrue(p["photosafe"])
        self.assertAlmostEqual(p["safe_period_s"], 1.1)


class PredictRainWet(unittest.TestCase):
    def test_rain_particle_budget(self):
        # 30 x 30 x 20 m = 18000 m3; 0.5 /m3 -> 9000 streaks; 20 m / 8 m/s = 2.5 s;
        # 9000 / 2.5 = 3600 per s; ground hits 0.5 * 8 = 4 per m2 per s
        p = predict("rain", "--box", 30, 30, 20, "--density", 0.5, "--speed", 8, "--budget", 5000,
                    "--rate", 10)
        self.assertEqual(p["volume_m3"], 18000)
        self.assertEqual(p["particles"], 9000)
        self.assertEqual(p["lifetime_s"], 2.5)
        self.assertEqual(p["emission_per_s"], 3600)
        self.assertEqual(p["ground_hits_per_m2_s"], 4)
        self.assertFalse(p["fits_budget"])
        # Marshall-Palmer at 10 mm/h: L = 4.1 * 10^-0.21 = 2.52804 /mm; all drops 8000/L = 3164.5
        # per m3; drops > 1 mm: 3164.5 * exp(-2.52804) = 252.58 per m3
        self.assertAlmostEqual(p["real_drops_per_m3"], 3164.5, places=1)
        self.assertAlmostEqual(p["real_drops_over_dmin_per_m3"], 252.58, places=2)
        # 1 mm/h: L = 4.1, 8000/4.1 * exp(-4.1) = 32.34 drops > 1 mm per m3
        p = predict("rain", "--box", 10, 10, 10, "--density", 1, "--speed", 5, "--rate", 1)
        self.assertAlmostEqual(p["real_drops_over_dmin_per_m3"], 32.34, places=2)

    def test_wetting_and_drying_times(self):
        # exponential drying 1 -> 0.1 with tau 60 s: 60 * ln 10 = 138.155 s
        p = predict("wetness", "--from", 1, "--to", 0.1, "--tau", 60)
        self.assertEqual(p["direction"], "drying")
        self.assertAlmostEqual(p["time_s"], 138.155, places=3)
        # exponential wetting 0 -> 0.9 with tau 20 s: 20 * ln((1-0)/(1-0.9)) = 46.052 s
        self.assertAlmostEqual(predict("wetness", "--from", 0, "--to", 0.9, "--tau", 20)["time_s"],
                               46.052, places=3)
        # linear drying at 0.01 per s: 0.9 / 0.01 = 90 s
        self.assertAlmostEqual(predict("wetness", "--from", 1, "--to", 0.1, "--rate", 0.01)
                               ["time_s"], 90.0, places=6)
        # an exponential approach never reaches 1
        self.assertEqual(run("predict", "wetness", "--from", 0, "--to", 1, "--tau", 20)[0], 2)


class PredictTransitionSchedule(unittest.TestCase):
    def test_transition_shapes_and_hysteresis(self):
        # linear 0 -> 1 in 120 s: 1/120 = 0.008333 per s; crosses on=0.6 at 72 s
        p = predict("transition", "--from", 0, "--to", 1, "--duration", 120, "--on", 0.6,
                    "--off", 0.4, "--noise", 0.1, "--max-rate", 0.01)
        self.assertAlmostEqual(p["max_rate_per_s"], 0.008333, places=6)
        self.assertAlmostEqual(p["crosses_threshold_at_s"], 72.0, places=3)
        self.assertAlmostEqual(p["hysteresis_band"], 0.2, places=6)
        self.assertTrue(p["chatter_safe"])      # band 0.2 > noise 0.1
        self.assertTrue(p["smooth_ok"])
        # smoothstep: peak rate 1.5/120 = 0.0125 per s; 3u^2 - 2u^3 = 0.6 at
        # u = 0.5 - sin(asin(-0.2)/3) = 0.567069 -> 68.048 s; 95 % at u = 0.864638 -> 103.758 s
        p = predict("transition", "--from", 0, "--to", 1, "--duration", 120, "--shape",
                    "smoothstep", "--on", 0.6, "--max-rate", 0.01)
        self.assertAlmostEqual(p["max_rate_per_s"], 0.0125, places=6)
        self.assertAlmostEqual(p["crosses_threshold_at_s"], 68.048, places=3)
        self.assertAlmostEqual(p["time_to_95pct_s"], 103.758, places=3)
        self.assertFalse(p["smooth_ok"])
        # exponential, tau 40 s: start rate 1/40 = 0.025; on 0.6 at -40 ln 0.4 = 36.652 s;
        # 95 % at 40 ln 20 = 119.829 s
        p = predict("transition", "--from", 0, "--to", 1, "--shape", "exp", "--tau", 40, "--on",
                    0.6)
        self.assertAlmostEqual(p["max_rate_per_s"], 0.025, places=6)
        self.assertAlmostEqual(p["crosses_threshold_at_s"], 36.652, places=3)
        self.assertAlmostEqual(p["time_to_95pct_s"], 119.829, places=3)
        # falling 1 -> 0 in 100 s crosses off=0.4 at 60 s; noise 0.25 > band 0.2 chatters
        p = predict("transition", "--from", 1, "--to", 0, "--duration", 100, "--on", 0.6,
                    "--off", 0.4, "--noise", 0.25)
        self.assertAlmostEqual(p["crosses_threshold_at_s"], 60.0, places=3)
        self.assertFalse(p["chatter_safe"])
        self.assertEqual(run("predict", "transition", "--from", 0, "--to", 1)[0], 2)

    def test_schedule_minecraft_and_game_hours(self):
        # Minecraft Java: rain 12000-24000 ticks, clear 12000-180000, uniform:
        # mean 18000 and 96000 ticks -> rain 18000/114000 = 15.79 % of the time;
        # 1 tick = 0.05 s -> mean rain 900 s (15 min), mean clear 4800 s (80 min)
        p = predict("schedule", "--on-min", 12000, "--on-max", 24000, "--off-min", 12000,
                    "--off-max", 180000, "--unit-s", 0.05)
        self.assertEqual(p["mean_on"], 18000)
        self.assertEqual(p["mean_off"], 96000)
        self.assertAlmostEqual(p["share_on"], 0.157895, places=6)
        self.assertEqual(p["mean_on_s"], 900)
        self.assertEqual(p["mean_off_min"], 80)
        # dwell 2-12 game hours with a 48-minute day: 1 game hour = 120 s -> 240-1440 s, mean 840
        p = predict("schedule", "--on-min", 2, "--on-max", 12, "--day-minutes", 48)
        self.assertEqual(p["on_s"], [240, 1440])
        self.assertEqual(p["mean_on_s"], 840)


class PredictWindPerception(unittest.TestCase):
    def test_snow_lives_in_fluid_check(self):
        # snowfall, settling and melt are fluids-granular's (fluid_check.py) — no duplicate here
        self.assertEqual(run("predict", "snow", "--rate", 2.54, "--hours", 6)[0], 2)

    def test_wind_beaufort_gust_and_chill(self):
        # 30 km/h at -20 C: 13.12 - 12.43 - 11.37*30^0.16 - 7.93*30^0.16 = -32.568 C (Wikipedia
        # table: -33); 8.333 m/s is force 5; B = (8.333/0.836)^(2/3) = 4.632
        p = predict("wind", "--speed", 30 / 3.6, "--temp", -20)
        self.assertAlmostEqual(p["wind_chill_c"], -32.568, places=3)
        self.assertEqual(p["beaufort_force"], 5)
        self.assertAlmostEqual(p["beaufort_number"], 4.632, places=3)
        # 5 km/h at -20 C: -24.279 C (Wikipedia: -24)
        self.assertAlmostEqual(predict("wind", "--speed", 5 / 3.6, "--temp", -20)["wind_chill_c"],
                               -24.279, places=3)
        # 10 m/s: force 5 (8-10.7), B = (10/0.836)^(2/3) = 5.230, gust x1.5 = 15 m/s
        p = predict("wind", "--speed", 10)
        self.assertEqual(p["beaufort_force"], 5)
        self.assertAlmostEqual(p["beaufort_number"], 5.230, places=3)
        self.assertEqual(p["gust_m_s"], 15)
        self.assertEqual(predict("wind", "--speed", 0.2)["beaufort_force"], 0)
        self.assertEqual(predict("wind", "--speed", 3.4)["beaufort_force"], 3)
        self.assertEqual(predict("wind", "--speed", 32.7)["beaufort_force"], 12)
        self.assertIsNone(predict("wind", "--speed", 10, "--temp", 20)["wind_chill_c"])

    def test_perception_in_fog_and_rain_noise(self):
        # V = 400 m: sigma = 3.912/400; a target of contrast 0.3 fades to 0.02 at
        # ln(0.3/0.02)/sigma = 2.70805/0.0097801 = 276.90 m; hearing 30 m with +6 dB of rain
        # noise: 30 * 10^(-6/20) = 15.036 m
        p = predict("perception", "--visibility", 400, "--contrast", 0.3, "--hearing", 30,
                    "--noise-db", 6)
        self.assertAlmostEqual(p["sight_m"], 276.90, places=2)
        self.assertAlmostEqual(p["hearing_m"], 15.036, places=3)
        self.assertAlmostEqual(predict("perception", "--visibility", 400)["sight_m"], 400.0,
                               places=6)


class MeasureSmooth(unittest.TestCase):
    def test_ramp_passes_and_pop_fails(self):
        # 0 -> 1 over 50 s at 60 Hz: 0.02 per s everywhere
        ramp = [i / 3000 for i in range(3000)]
        code, res = run("smooth", recording({"intensity": ramp}), "--probe", "intensity=0.05")
        self.assertEqual(code, 0)
        self.assertAlmostEqual(res["metrics"][0]["value"], 0.02, places=6)
        # a 0.3 jump at 25 s: (0.3 + 0.01) / 0.5 s = 0.62 per s
        pop = [v + (0.3 if i >= 1500 else 0) for i, v in enumerate(ramp)]
        code, res = run("smooth", recording({"intensity": pop}), "--probe", "intensity=0.05")
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["value"], 0.62, places=6)

    def test_vector_wind_and_jsonl(self):
        # wind vector turning at 0.2 rad/s with |v| = 5 m/s: chord over 0.5 s / 0.5 s
        # = 2 * 5 * sin(0.05) / 0.5 = 0.99958 m/s per s
        rows = [{"type": "tick", "t": i / 60, "wind": [5 * math.cos(0.2 * i / 60), 0,
                                                       5 * math.sin(0.2 * i / 60)]}
                for i in range(600)]
        path = write("\n".join(json.dumps(r) for r in rows), suffix=".jsonl")
        code, res = run("smooth", path, "--probe", "wind=1.0")
        self.assertEqual(code, 0)
        self.assertAlmostEqual(res["metrics"][0]["value"], 2 * 5 * math.sin(0.05) / 0.5, places=4)
        self.assertEqual(run("smooth", path, "--probe", "wind=0.5")[0], 1)

    def test_state_dwell(self):
        # runs of 10 s: inner runs 10 s >= 5 -> PASS; a 1 s blip -> FAIL
        steady = [(i // 600) % 2 == 1 for i in range(2400)]
        code, res = run("smooth", recording({"rain_on": steady}), "--state", "rain_on")
        self.assertEqual(code, 0)
        self.assertAlmostEqual(res["metrics"][0]["value"], 10.0, places=3)
        self.assertEqual(res["metrics"][0]["toggles"], 3)
        blip = [600 <= i < 660 for i in range(1800)]
        code, res = run("smooth", recording({"rain_on": blip}), "--state", "rain_on")
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][0]["value"], 1.0, places=3)


def wet_run(dry_rate=0.01, hz=10, seconds=200, drop_at_stop=False, dip=False):
    """Rain 5-65 s; wetness +0.05/s from 5 s (capped at 1), then -dry_rate per s."""
    wet, rain = [], []
    for i in range(seconds * hz):
        t = i / hz
        raining = 5 <= t < 65
        if raining:
            w = min(1.0, max(0.0, (t - 5) * 0.05))
            if dip and 40 <= t < 41:
                w = 0.5
        else:
            w = 0.0 if t < 5 else (0.0 if drop_at_stop else max(0.0, 1 - (t - 65) * dry_rate))
        wet.append(w)
        rain.append(raining)
    return recording({"wet": wet, "raining": rain}, hz=hz)


class MeasureWetness(unittest.TestCase):
    def test_wets_and_dries_in_window(self):
        # 0.8 at t = 21 s -> ramp 16 s; dries 1 -> 0.1 at 0.01/s -> 90 s after the stop
        code, res = run("wetness", wet_run(), "--wetness", "wet", "--rain", "raining",
                        "--dry-min", 30, "--dry-within", 300)
        self.assertEqual(code, 0, res)
        m = {x["metric"]: x for x in res["metrics"]}
        self.assertAlmostEqual(m["wet_ramp_s"]["value"], 16.0, delta=0.11)
        self.assertAlmostEqual(m["dry_time_s"]["value"], 90.0, delta=0.11)

    def test_never_dries_or_dries_instantly_or_dips(self):
        code, res = run("wetness", wet_run(dry_rate=0.0), "--wetness", "wet", "--rain", "raining",
                        "--dry-within", 100)
        self.assertEqual(code, 1)        # still 1.0 after 135 s of no rain
        code, res = run("wetness", wet_run(drop_at_stop=True), "--wetness", "wet", "--rain",
                        "raining", "--dry-min", 30)
        self.assertEqual(code, 1)        # dry in 0 s < 30 s: a snap, not drying
        code, res = run("wetness", wet_run(dip=True), "--wetness", "wet", "--rain", "raining")
        self.assertEqual(code, 1)        # dropped 0.5 while it rained
        m = {x["metric"]: x for x in res["metrics"]}
        self.assertAlmostEqual(m["wet_drop_while_raining"]["value"], 0.5, places=4)

    def test_no_rain_is_not_assessed(self):
        path = recording({"wet": [0.0] * 100, "raining": [False] * 100})
        code, res = run("wetness", path, "--wetness", "wet", "--rain", "raining")
        self.assertEqual(code, 0)
        self.assertEqual(res["verdict"], "NOT ASSESSED")


class MeasureShelter(unittest.TestCase):
    def test_roof_keeps_rain_out(self):
        outside = [min(1.0, i / 300) for i in range(600)]
        dry = recording({"open": outside, "under": [0.0] * 600})
        self.assertEqual(run("shelter", dry, "--inside", "under", "--outside", "open")[0], 0)
        leak = recording({"open": outside, "under": [min(0.3, i / 1000) for i in range(600)]})
        code, res = run("shelter", leak, "--inside", "under", "--outside", "open")
        self.assertEqual(code, 1)
        self.assertAlmostEqual(res["metrics"][1]["value"], 0.3, places=4)
        no_rain = recording({"open": [0.1] * 600, "under": [0.0] * 600})
        code, res = run("shelter", no_rain, "--inside", "under", "--outside", "open")
        self.assertEqual((code, res["verdict"]), (0, "NOT ASSESSED"))

    def test_splash_positions_under_roof(self):
        roof = [0, 0, 0, 4, 3, 4]
        out = [[[10, 0, 10], [12, 0, 9]] for _ in range(60)]
        self.assertEqual(run("shelter", recording({"splash": out}), "--splashes", "splash",
                             "--roof", *roof)[0], 0)
        leak = [row[:] for row in out]
        leak[30] = leak[30] + [[2, 0, 2]]
        code, res = run("shelter", recording({"splash": leak}), "--splashes", "splash",
                        "--roof", *roof)
        self.assertEqual(code, 1)
        self.assertEqual(res["metrics"][0]["value"], 1)
        self.assertAlmostEqual(res["metrics"][0]["first_at_s"], 0.5, places=3)


class MeasureVisibility(unittest.TestCase):
    def test_fitted_visibility(self):
        # contrast = exp(-sigma d) with sigma = 3.912/200 -> fitted V = 200 m exactly
        sigma = -math.log(0.02) / 200
        targets = write({"targets": [{"distance": d, "contrast": math.exp(-sigma * d)}
                                     for d in (50, 100, 200, 400)]})
        code, res = run("visibility", targets, "--visibility", 200)
        self.assertEqual(code, 0)
        self.assertAlmostEqual(res["metrics"][0]["value"], 200.0, places=2)
        self.assertEqual(run("visibility", targets, "--visibility", 400)[0], 1)   # 50 % off
        # fog amounts instead of contrast: fog = 1 - transmittance
        fog = write([{"distance": d, "fog": 1 - math.exp(-sigma * d)} for d in (50, 150)])
        self.assertEqual(run("visibility", fog, "--visibility", 210)[0], 0)        # 4.8 % off
        one = write({"targets": [{"distance": 50, "contrast": 0.5}]})
        code, res = run("visibility", one, "--visibility", 200)
        self.assertEqual((code, res["verdict"]), (0, "NOT ASSESSED"))


class MeasureFlashes(unittest.TestCase):
    def test_lightning_flicker(self):
        # 4 strokes 3 frames apart: 8 transitions in 0.18 s -> 4 flashes > 3 -> FAIL
        code, res = run("flashes", recording({"luma": strokes_series([30, 33, 36, 39])}),
                        "--luma", "luma")
        self.assertEqual(code, 1)
        self.assertEqual(res["metrics"][0]["transitions_in_worst_1s"], 8)
        self.assertEqual(res["metrics"][0]["value"], 4.0)
        # 3 strokes: 6 transitions = 3 flashes -> PASS
        code, res = run("flashes", recording({"luma": strokes_series([30, 33, 36])}),
                        "--luma", "luma")
        self.assertEqual(code, 0)
        self.assertEqual(res["metrics"][0]["value"], 3.0)

    def test_bursts_spacing(self):
        # two 3-stroke bursts 0.6 s apart: 12 transitions in 1 s -> FAIL; 1.2 s apart -> PASS
        near = strokes_series([30, 33, 36, 66, 69, 72])
        self.assertEqual(run("flashes", recording({"luma": near}), "--luma", "luma")[0], 1)
        far = strokes_series([30, 33, 36, 102, 105, 108])
        self.assertEqual(run("flashes", recording({"luma": far}), "--luma", "luma")[0], 0)

    def test_small_area_or_bright_states_do_not_count(self):
        four = strokes_series([30, 33, 36, 39])
        small = recording({"luma": four, "area": [0.1] * len(four)})
        self.assertEqual(run("flashes", small, "--luma", "luma", "--area", "area")[0], 0)
        # 0.85 <-> 0.98: changes of 0.13 but the darker state is >= 0.8 -> not a general flash
        bright = strokes_series([30, 33, 36, 39], base=0.85, peak=0.98)
        code, res = run("flashes", recording({"luma": bright}), "--luma", "luma")
        self.assertEqual((code, res["metrics"][0]["transitions_total"]), (0, 0))

    def test_frame_samples(self):
        four = strokes_series([30, 33, 36, 39])
        path = write({"physics_ticks_per_second": 60, "ticks": [], "samples": {},
                      "frame_ms": [1000 / 60] * len(four), "frame_samples": {"luma": four}})
        self.assertEqual(run("flashes", path, "--luma", "luma")[0], 1)
        code, res = run("flashes", path, "--luma", "missing")
        self.assertEqual((code, res["verdict"]), (0, "NOT ASSESSED"))


if __name__ == "__main__":
    unittest.main()
