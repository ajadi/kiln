"""Tests for plugins/kiln/skills/fluids-granular/scripts/fluid_check.py (stdlib only).

Expected numbers come from the closed-form answers in the script's docstring; every check is also
shown failing on a broken input.
"""

import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "fluids-granular", "scripts", "fluid_check.py")
G = 9.81


def write(data):
    fd, path = tempfile.mkstemp(prefix="kiln-fluid-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *map(str, args)], capture_output=True,
                       text=True, timeout=120, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


def recording(samples, hz=60):
    n = max(len(v) for v in samples.values())
    return write({"physics_ticks_per_second": hz, "ticks": list(range(n)), "samples": samples})


class Predict(unittest.TestCase):
    def test_floating_boxes(self):
        _, pine = run("predict", "float", "--rho-body", 500, "--height", 0.4)
        self.assertEqual(pine["prediction"]["submerged_fraction"], 0.5)
        self.assertAlmostEqual(pine["prediction"]["draft_m"], 0.2)
        _, ice = run("predict", "float", "--rho-body", 917)
        self.assertAlmostEqual(ice["prediction"]["submerged_fraction"], 0.917)
        _, steel = run("predict", "float", "--rho-body", 7850)
        self.assertFalse(steel["prediction"]["floats"])

    def test_heave_period(self):
        # 500 kg box with 1 m2 waterplane: omega = sqrt(1000*9.81*1/500) = 4.429, T = 1.419 s
        _, res = run("predict", "heave", "--mass", 500, "--area", 1)
        self.assertAlmostEqual(res["prediction"]["period_s"],
                               2 * math.pi / math.sqrt(1000 * G / 500), places=3)

    def test_torricelli_and_drain(self):
        # h 2 m: v = sqrt(2*9.81*2) = 6.264; drain 1 m2 tank through 0.01 m2: 100*sqrt(4/9.81)
        _, res = run("predict", "efflux", "--h", 2, "--tank-area", 1, "--hole-area", 0.01)
        self.assertAlmostEqual(res["prediction"]["speed_m_s"], math.sqrt(2 * G * 2), places=3)
        self.assertAlmostEqual(res["prediction"]["drain_s"], 100 * math.sqrt(4 / G), places=2)

    def test_dam_break_front(self):
        _, res = run("predict", "dambreak", "--h0", 1)
        self.assertAlmostEqual(res["prediction"]["front_speed_m_s"], 2 * math.sqrt(G), places=3)

    def test_wave_dispersion_deep_and_shallow(self):
        # deep water, lambda 10 m: T = sqrt(2*pi*10/g) = 2.531 s, c = 3.951 m/s
        _, deep = run("predict", "wave", "--wavelength", 10)
        self.assertAlmostEqual(deep["prediction"]["period_s"], math.sqrt(2 * math.pi * 10 / G),
                               places=3)
        self.assertTrue(deep["prediction"]["deep_water"])
        # shallow: lambda 100 m in 1 m depth -> c ~ sqrt(g*d) = 3.13 m/s (within 1 %)
        _, sh = run("predict", "wave", "--wavelength", 100, "--depth", 1)
        self.assertAlmostEqual(sh["prediction"]["phase_speed_m_s"], math.sqrt(G * 1), delta=0.04)
        self.assertTrue(sh["prediction"]["shallow_water"])

    def test_cfl(self):
        _, ok = run("predict", "cfl", "--dx", 0.25, "--dt", 0.0167, "--umax", 3, "--depth", 2)
        self.assertTrue(ok["prediction"]["stable"])  # wave 4.43 m/s -> courant 0.296
        _, bad = run("predict", "cfl", "--dx", 0.05, "--dt", 0.0167, "--depth", 2)
        self.assertFalse(bad["prediction"]["stable"])


class Float(unittest.TestCase):
    def bob(self, rest_y, damping=0.8, amp=0.2):
        return [[0.0, rest_y + amp * math.exp(-damping * i / 60) * math.cos(4.4 * i / 60), 0.0]
                for i in range(60 * 12)]

    def test_half_density_box_floats_half_submerged(self):
        # 1 m box, fraction 0.5: centre at water_y + 0 (bottom 0.5 below the surface)
        path = recording({"box": self.bob(0.0)})
        code, res = run("float", path, "--pos", "box", "--water-y", 0, "--height", 1,
                        "--fraction", 0.5)
        self.assertEqual(code, 0, res)

    def test_floating_too_high_and_endless_bobbing_fail(self):
        path = recording({"box": self.bob(0.3, damping=0.0)})
        code, res = run("float", path, "--pos", "box", "--water-y", 0, "--height", 1,
                        "--fraction", 0.5)
        self.assertEqual(code, 1)
        self.assertEqual({m["verdict"] for m in res["metrics"]}, {"FAIL"})


class Levels(unittest.TestCase):
    def test_vessels_equalise(self):
        a = [1.0 - 0.5 * (1 - math.exp(-i / 60)) for i in range(600)]
        b = [0.0 + 0.5 * (1 - math.exp(-i / 60)) for i in range(600)]
        self.assertEqual(run("levels", recording({"a": a, "b": b}), "--probes", "a,b")[0], 0)
        stuck = [0.2] * 600
        self.assertEqual(run("levels", recording({"a": a, "b": stuck}), "--probes", "a,b")[0], 1)


class Conserve(unittest.TestCase):
    def test_volume_drift(self):
        self.assertEqual(run("conserve", recording({"v": [10.0 + 0.01 * math.sin(i)
                                                          for i in range(200)]}),
                             "--total", "v")[0], 0)
        self.assertEqual(run("conserve", recording({"v": [10.0 * 0.999 ** i for i in range(200)]}),
                             "--total", "v")[0], 1)


class Repose(unittest.TestCase):
    def cone(self, angle_deg, n=41, dx=0.1):
        c = (n - 1) / 2
        t = math.tan(math.radians(angle_deg))
        return {"dx": dx, "heights": [[max(0.0, 1.5 - t * dx * max(abs(i - c), abs(j - c)))
                                       for i in range(n)] for j in range(n)]}

    def test_sand_cone_at_34_degrees(self):
        code, res = run("repose", write(self.cone(34)), "--angle", 34)
        self.assertEqual(code, 0, res)

    def test_too_steep_and_too_flat_fail(self):
        self.assertEqual(run("repose", write(self.cone(60)), "--angle", 34)[0], 1)
        self.assertEqual(run("repose", write(self.cone(10)), "--angle", 34)[0], 1)


class Wave(unittest.TestCase):
    def buoy(self, period):
        return recording({"h": [0.3 * math.sin(2 * math.pi * (i / 60) / period)
                                for i in range(60 * 20)]})

    def test_deep_water_period(self):
        t = math.sqrt(2 * math.pi * 10 / G)
        self.assertEqual(run("wave", self.buoy(t), "--height", "h", "--wavelength", 10)[0], 0)
        self.assertEqual(run("wave", self.buoy(1.5), "--height", "h", "--wavelength", 10)[0], 1)


def pred(*args):
    code, res = run("predict", *args)
    assert code == 0, res
    return res["prediction"]


class SandPredict(unittest.TestCase):
    def test_saltation_thresholds(self):
        # d 0.25 mm: sqrt((2650 - 1.225)/1.225 * 9.81 * 0.00025) = 2.30282
        # u*ft = 0.10 * 2.30282 = 0.2303, u*it = 0.082 * 2.30282 = 0.1888 m/s
        # 10 m wind (z0 1e-3): 0.2303/0.4 * ln(1e4) = 5.302; impact 4.348 m/s
        p = pred("saltation", "--d", 0.25)
        self.assertAlmostEqual(p["ustar_fluid"], 0.2303, places=4)
        self.assertAlmostEqual(p["ustar_impact"], 0.1888, places=4)
        self.assertAlmostEqual(p["wind_to_start_m_s"], 5.302, places=3)
        self.assertAlmostEqual(p["wind_to_keep_m_s"], 4.348, places=3)
        # z0 1e-4: start at 0.2303/0.4 * ln(1e5) = 6.628 m/s; a 6 m/s wind (u* 0.2085) keeps
        # sand moving but cannot start it
        p = pred("saltation", "--d", 0.25, "--z0", 1e-4, "--wind", 6)
        self.assertAlmostEqual(p["wind_to_start_m_s"], 6.628, places=3)
        self.assertAlmostEqual(p["ustar"], 0.2085, places=4)
        self.assertFalse(p["starts"])
        self.assertTrue(p["keeps_moving"])

    def test_sand_flux_models(self):
        # u* 0.4, d 0.25 mm, rho_a/g = 0.124873: Bagnold 1.8*0.124873*0.064 = 0.014386;
        # Kawamura r = 0.18883/0.4 = 0.47208, 2.78*0.124873*0.064*(1-r)(1+r)^2 = 0.025417;
        # Lettau 6.7*0.124873*0.16*(0.4-0.18883) = 0.028268 kg/m/s
        p = pred("sandflux", "--ustar", 0.4)
        f = p["flux_kg_m_s"]
        self.assertAlmostEqual(f["bagnold"], 0.014386, places=5)
        self.assertAlmostEqual(f["kawamura"], 0.025417, places=5)
        self.assertAlmostEqual(f["lettau"], 0.028268, places=5)
        # bulk 2650*0.6 = 1590: q = 9.0474e-6 m2/s, 51.79 kg/m/h, 285.5 m2/yr if it always blew
        self.assertAlmostEqual(p["volume_flux_m2_s"], 9.0474e-6, places=9)
        self.assertAlmostEqual(p["per_hour_kg_m"], 51.79, places=2)
        self.assertAlmostEqual(p["per_year_m2"], 285.51, places=1)
        # doubling u* multiplies Bagnold's flux by 8
        double = pred("sandflux", "--ustar", 0.8)["flux_kg_m_s"]["bagnold"]
        self.assertAlmostEqual(double / f["bagnold"], 8.0, places=3)
        # below the impact threshold nothing moves (Bagnold alone has no threshold)
        calm = pred("sandflux", "--ustar", 0.15)
        self.assertFalse(calm["moving"])
        self.assertEqual(calm["flux_kg_m_s"]["bagnold"], 0.0)

    def test_dune_migration_and_compression(self):
        # c = q/H: 100 m2/yr over a 3 m crest = 33.333 m/yr, over 10 m = 10 m/yr
        p = pred("dune", "--dune-height", 3, "--q-year", 100, "--width", 300,
                 "--game-move", 1, "--game-s", 60)
        self.assertAlmostEqual(p["speed_m_year"], 33.333, places=3)
        self.assertAlmostEqual(pred("dune", "--dune-height", 10, "--q-year", 100)["speed_m_year"],
                               10.0)
        # barchan scaling: 50*100/300 = 16.667 m/yr, turnover 0.02*300^2/100 = 18 yr
        self.assertAlmostEqual(p["barchan_speed_m_year"], 16.667, places=3)
        self.assertAlmostEqual(p["turnover_years"], 18.0)
        # l_drag = 0.25e-3*2650/1.225 = 0.5408 m, minimum width 24*l_drag = 12.98 m
        self.assertAlmostEqual(p["min_dune_width_m"], 12.98, places=2)
        # 1 m takes 1/33.333 yr = 946728 s; shown in 60 game s -> K = 15778.8
        self.assertAlmostEqual(p["real_time_s"], 946728.0, places=0)
        self.assertAlmostEqual(p["compression"], 15778.8, places=1)

    def test_ripple_height(self):
        # 10 cm ripples, index 15 -> 0.667 cm high
        p = pred("ripple")
        self.assertAlmostEqual(p["height_m"], 0.00667, places=5)
        self.assertFalse(pred("ripple", "--wavelength", 0.3)["normal_ripple"])

    def test_werner_units(self):
        # 1 m cells, slab 1/3 m, tan 30 / (1/3) = 1.7321 slabs -> 1 whole slab (18.43 deg);
        # flux per time unit 0.3333*5*1/0.6 = 2.7778 m2; real 29 m2/yr -> 2.7778/29 yr = 34.986 d
        p = pred("werner", "--q-year", 29)
        self.assertAlmostEqual(p["slab_m"], 0.3333, places=4)
        self.assertAlmostEqual(p["max_step_slabs"], 1.7321, places=4)
        self.assertEqual(p["max_step_whole"], 1)
        self.assertAlmostEqual(p["effective_repose_deg"], 18.43, places=2)
        self.assertAlmostEqual(p["flux_per_unit_m2"], 2.7778, places=4)
        self.assertAlmostEqual(p["real_days_per_unit"], 34.986, places=3)

    def test_footprint_fill_time(self):
        # 28 cm long, 3 cm deep print, u* 0.4 sand: t = 0.28*0.03/9.0474e-6 = 928.4 s;
        # shown in 60 game s -> K = 15.47
        p = pred("fill", "--length", 0.28, "--depth", 0.03, "--ustar", 0.4, "--game-s", 60)
        self.assertAlmostEqual(p["fill_s"], 928.4, places=1)
        self.assertAlmostEqual(p["compression"], 15.474, places=3)
        # half the grains trapped -> twice as long (2 * 928.43 = 1856.86)
        half = pred("fill", "--length", 0.28, "--depth", 0.03, "--ustar", 0.4, "--trap", 0.5)
        self.assertAlmostEqual(half["fill_s"], 1856.9, places=1)
        # snow, u* 0.4, u*t 0.2: Q = 0.68*1.225*(0.2/(0.4*9.81))*(0.16 - 0.04) = 0.0050947 kg/m/s,
        # over 350 kg/m3 = 1.45566e-5 m2/s; 30 cm x 10 cm boot print fills in 0.03/q = 2060.9 s
        s = pred("fill", "--length", 0.3, "--depth", 0.1, "--ustar", 0.4, "--material", "snow",
                 "--ustar-t", 0.2)
        self.assertAlmostEqual(s["volume_flux_m2_s"], 1.45566e-5, places=9)
        self.assertAlmostEqual(s["fill_s"], 2060.9, places=1)
        calm = pred("fill", "--length", 0.28, "--depth", 0.03, "--ustar", 0.1)
        self.assertIsNone(calm["fill_s"])


class SnowPredict(unittest.TestCase):
    def test_blowing_snow(self):
        # dry snow, threshold 7.7 m/s at 10 m: u*t = 0.4*7.7/ln(1e4) = 0.3344; 12 m/s: u* 0.5212;
        # Q = 0.68*1.225*0.3344/(0.5212*9.81)*(0.5212^2 - 0.3344^2) = 0.008705 kg/m/s
        p = pred("blowsnow", "--wind", 12)
        self.assertAlmostEqual(p["ustar_threshold"], 0.3344, places=4)
        self.assertAlmostEqual(p["ustar"], 0.5212, places=4)
        self.assertAlmostEqual(p["flux_kg_m_s"], 0.008705, places=6)
        self.assertTrue(p["blowing"])
        # wet snow holds at 9 m/s (threshold 9.9); fresh snow blows at 5 m/s (threshold 4.5)
        self.assertFalse(pred("blowsnow", "--wind", 9, "--snow", "wet")["blowing"])
        self.assertTrue(pred("blowsnow", "--wind", 5, "--snow", "fresh")["blowing"])

    def test_fence_drift(self):
        # Tabler: H 2 m -> lee 60 m long, 2.4 m deep, 77.2 m2; density 376 + 158*log10(2.4)
        # = 436.07 kg/m3; mass 33664.9 kg per metre; at 0.01 kg/m/s it fills in 38.96 days
        p = pred("drift", "--barrier", 2, "--q-mass", 0.01, "--game-s", 300)
        self.assertEqual(p["lee_length_m"], 60.0)
        self.assertAlmostEqual(p["lee_depth_m"], 2.4)
        self.assertAlmostEqual(p["lee_area_m2"], 77.2)
        self.assertAlmostEqual(p["density"], 436.1, places=1)
        self.assertAlmostEqual(p["mass_kg_per_m"], 33664.9, places=1)
        self.assertAlmostEqual(p["fill_days"], 38.96, places=2)
        self.assertAlmostEqual(p["compression"], 3366486 / 300, places=0)

    def test_snowfall_depth_and_water(self):
        # 2.54 cm/h for 6 h at 100 kg/m3: 15.24 cm, 15.24 mm water, 6.096 cm settled at 250;
        # 6 h shown in 600 game s -> K = 36; meets the NWS heavy-snow line (10.16 cm in 12 h)
        p = pred("snowfall", "--hours", 6, "--rate", 2.54, "--rho-settled", 250, "--game-s", 600)
        self.assertAlmostEqual(p["depth_fresh_m"], 0.1524)
        self.assertAlmostEqual(p["swe_mm"], 15.24)
        self.assertAlmostEqual(p["depth_settled_m"], 0.061, places=3)
        self.assertEqual(p["compression"], 36.0)
        self.assertTrue(p["nws_heavy_snow"])
        self.assertFalse(pred("snowfall", "--hours", 6, "--rate", 0.5)["nws_heavy_snow"])
        # 2.5 mm water/h for 4 h at 100 kg/m3 -> 10 cm of snow
        self.assertAlmostEqual(pred("snowfall", "--hours", 4, "--swe-rate", 2.5)["depth_fresh_m"],
                               0.1)

    def test_settling(self):
        # FSM: rho = 300 + (100 - 300)*exp(-200/200) = 226.42; 30 cm settles to
        # 0.3*100/226.42 = 13.25 cm; 250 kg/m3 after -200*ln(50/200) = 277.26 h
        p = pred("settle", "--hours", 200, "--depth", 0.3, "--target-rho", 250)
        self.assertAlmostEqual(p["rho_now"], 226.42, places=2)
        self.assertAlmostEqual(p["depth_now_m"], 0.1325, places=4)
        self.assertAlmostEqual(p["hours_to_target"], 277.259, places=3)
        # cover fraction tanh(h/0.1): 30 cm 0.9951, 13.25 cm 0.868
        self.assertAlmostEqual(p["cover_now"], 0.868, places=3)
        # melting snow heads to 500: 500 - 400/e = 352.85
        self.assertAlmostEqual(pred("settle", "--hours", 200, "--melting")["rho_now"], 352.85,
                               places=2)

    def test_footprint_sinkage(self):
        # 80 kg on 0.03 m2: 26.16 kPa; 30 cm of 100 kg/m3 compacts to 500: z = 0.3*(1 - 0.2)
        # = 0.24 m; capped at 0.12 m in deep snow
        p = pred("footprint", "--mass", 80, "--area", 0.03, "--depth", 0.3, "--rho0", 100,
                 "--cap", 0.12)
        self.assertAlmostEqual(p["pressure_kpa"], 26.16, places=2)
        self.assertAlmostEqual(p["full_compaction_m"], 0.24)
        self.assertAlmostEqual(p["sinkage_m"], 0.12)
        self.assertTrue(p["capped"])
        # wheel fit: rho_f = 519 + 2.3*26.16 = 579.17 -> z = 0.3*(1 - 100/579.17) = 0.2482
        fit = pred("footprint", "--mass", 80, "--area", 0.03, "--depth", 0.3, "--rho0", 100,
                   "--fit")
        self.assertAlmostEqual(fit["sinkage_m"], 0.2482, places=4)
        # CRREL truck tyre at 233 kPa (> 210 -> rho_f 550) in 20 cm of 250 kg/m3:
        # z = 0.2*(1 - 250/550) = 0.1091 m (measured HEMTT ruts 12-16 cm)
        truck = pred("footprint", "--mass", 1000, "--area", 1000 * G / 233000, "--depth", 0.2,
                     "--rho0", 250)
        self.assertEqual(truck["rho_final"], 550.0)
        self.assertAlmostEqual(truck["sinkage_m"], 0.1091, places=4)
        # wind-packed snow already denser than the target leaves no print
        self.assertEqual(pred("footprint", "--mass", 80, "--area", 0.03, "--depth", 0.3,
                              "--rho0", 520)["sinkage_m"], 0.0)

    def test_avalanche_release_and_runout(self):
        for slope, prone in ((25, False), (28, False), (32, True), (38, True), (44, True),
                             (50, False)):
            self.assertEqual(pred("avalanche", "--slope", slope)["in_release_band"], prone, slope)
        # 0.5 m slab of 200 kg/m3 on 38 deg: 200*9.81*0.5*sin38*cos38 = 0.4759 kPa;
        # weak layer 1.0 kPa -> S 2.101; skier adds 0.14/0.5 = 0.28 kPa -> S' 1.323 (transitional)
        p = pred("avalanche", "--slope", 38, "--slab", 0.5, "--strength", 1.0, "--skier",
                 "--beta", 28, "--drop", 500)
        self.assertAlmostEqual(p["slab_stress_kpa"], 0.4759, places=4)
        self.assertAlmostEqual(p["stability_natural"], 2.101, places=3)
        self.assertAlmostEqual(p["skier_stress_kpa"], 0.28, places=4)
        self.assertAlmostEqual(p["stability_skier"], 1.323, places=3)
        self.assertEqual(p["stability_class"], "transitional")
        self.assertFalse(p["releases"])
        # Lied & Bakkehoi: alpha = 0.97*28 - 1.4 = 25.76 deg; 500 m drop reaches 500/tan(25.76)
        # = 1036.1 m, 1221.6 m at alpha - 1 SD
        self.assertAlmostEqual(p["alpha_deg"], 25.76, places=2)
        self.assertAlmostEqual(p["reach_m"], 1036.1, places=1)
        self.assertAlmostEqual(p["reach_1sd_m"], 1221.6, places=1)
        # weak layer 0.4 kPa: S = 0.4/0.4759 = 0.841 -> releases on its own
        weak = pred("avalanche", "--slope", 38, "--slab", 0.5, "--strength", 0.4)
        self.assertTrue(weak["releases"])
        self.assertEqual(weak["stability_class"], "unstable")
        # the same weak slab on 25 deg is outside the band: no release
        self.assertFalse(pred("avalanche", "--slope", 25, "--slab", 0.5, "--strength", 0.2)
                         ["releases"])

    def test_melt_time(self):
        # 10 kg/m2 (10 cm at 100 kg/m3) at 300 W/m2: 10*333550/300 = 11118.3 s = 3.088 h;
        # from -10 C add 10*2090*10 J: 3544500/300 = 11815 s
        self.assertAlmostEqual(pred("melt", "--swe", 10, "--power", 300)["melt_h"], 3.0884,
                               places=4)
        cold = pred("melt", "--depth", 0.1, "--rho0", 100, "--power", 300, "--temp", -10)
        self.assertAlmostEqual(cold["melt_s"], 11815.0, places=1)


class StormPredict(unittest.TestCase):
    def test_visibility_and_overdraw(self):
        # Koschmieder: sigma = 3.912/200 = 0.01956 per m (Godot exponential fog_density)
        # 2000 sprites of 1 m in a 30 m sphere: n = 2000/113097 = 0.017684 per m3;
        # overdraw = n*1*(30 - 1) = 0.5128 layers; at opacity 0.1 their own sigma 0.0017684
        # -> visibility 2212.2 m
        p = pred("storm", "--visibility", 200, "--count", 2000, "--size", 1, "--radius", 30,
                 "--near", 1, "--opacity", 0.1)
        self.assertAlmostEqual(p["godot_fog_density"], 0.01956, places=5)
        self.assertEqual(p["category"], "sandstorm")
        self.assertAlmostEqual(p["overdraw_layers"], 0.5128, places=4)
        self.assertAlmostEqual(p["particle_visibility_m"], 2212.2, places=1)
        # 4 m sheets: 16x the overdraw
        big = pred("storm", "--count", 2000, "--size", 4, "--radius", 30, "--near", 1)
        self.assertAlmostEqual(big["overdraw_layers"], 0.5128 * 16, places=2)
        self.assertEqual(pred("storm", "--visibility", 150)["category"], "severe")


class Fill(unittest.TestCase):
    def print_depth(self, full_s, seconds, deepen_at=None):
        out = []
        for i in range(int(seconds * 10)):
            t = i / 10
            d = max(0.0, 0.03 * (1 - t / full_s))
            if deepen_at is not None and t >= deepen_at:
                d += 0.01
            out.append(d)
        return recording({"print": out}, hz=10)

    def test_print_fills_at_the_predicted_time(self):
        # linear fill over 928.4 s: 90 % at 835.6 s -> full fill 928.4 s
        code, res = run("fill", self.print_depth(928.4, 1200), "--depth", "print",
                        "--expect-s", 928.4)
        self.assertEqual(code, 0, res)
        self.assertAlmostEqual(res["metrics"][0]["value"], 928.4, delta=0.5)

    def test_too_fast_and_redeepening_fail(self):
        self.assertEqual(run("fill", self.print_depth(928.4, 1200), "--depth", "print",
                             "--expect-s", 300)[0], 1)
        code, res = run("fill", self.print_depth(928.4, 1200, deepen_at=400), "--depth", "print",
                        "--expect-s", 928.4)
        self.assertEqual(code, 1)
        self.assertEqual(res["metrics"][1]["verdict"], "FAIL")

    def test_short_recording_is_not_assessed(self):
        code, res = run("fill", self.print_depth(928.4, 300), "--depth", "print",
                        "--expect-s", 928.4)
        self.assertEqual((code, res["verdict"]), (0, "NOT ASSESSED"))


class Accum(unittest.TestCase):
    def test_snow_depth_rate(self):
        # 2.54 cm/h at K 36: 2.54/100/3600*36 = 2.54e-4 m per game second
        path = recording({"snow": [2.54e-4 * i / 10 for i in range(6000)]}, hz=10)
        self.assertEqual(run("accum", path, "--depth", "snow", "--rate", 2.54, "--k", 36)[0], 0)
        self.assertEqual(run("accum", path, "--depth", "snow", "--rate", 2.54)[0], 1)


class Lee(unittest.TestCase):
    def profile(self, lee_deg=32.0, n=80, dx=0.5):
        # stoss 12 deg from cell 10 to the crest at cell 40 (3.188 m), then the lee face
        crest = 30 * dx * math.tan(math.radians(12))
        row = []
        for i in range(n):
            if 10 <= i <= 40:
                row.append((i - 10) * dx * math.tan(math.radians(12)))
            elif i > 40:
                row.append(max(0.0, crest - (i - 40) * dx * math.tan(math.radians(lee_deg))))
            else:
                row.append(0.0)
        return row

    def grids(self, shift, lee_deg=32.0, rows=5):
        b = self.profile(lee_deg)
        f = [b[i - shift] if 0 <= i - shift < len(b) else 0.0 for i in range(len(b))]
        return ({"dx": 0.5, "heights": [b[:] for _ in range(rows)]},
                {"dx": 0.5, "heights": [f[:] for _ in range(rows)]})

    def test_dune_moves_downwind_with_lee_deposition(self):
        # shifted 2 cells (1.0 m) downwind in 100 s at 0.01 m/s: all deposition on the lee
        b, f = self.grids(2)
        code, res = run("lee", write(b), write(f), "--wind", "+x", "--speed", 0.01,
                        "--dt-s", 100)
        self.assertEqual(code, 0, res)
        m = {x["metric"]: x for x in res["metrics"]}
        self.assertEqual(m["lee_deposition_fraction"]["value"], 1.0)
        self.assertAlmostEqual(m["migration_m"]["value"], 1.0, places=3)
        self.assertAlmostEqual(m["slip_face_deg"]["value"], 32.0, places=2)
        # the same dune with the wind toward -x (written x-) is the mirror image
        mirror = [{"dx": 0.5, "heights": [r[::-1] for r in g["heights"]]} for g in (b, f)]
        self.assertEqual(run("lee", write(mirror[0]), write(mirror[1]), "--wind", "x-")[0], 0)
        self.assertEqual(run("lee", write(mirror[0]), write(mirror[1]), "--wind=-x")[0], 0)
        # and along +z the transpose
        trans = [{"dx": 0.5, "heights": [list(c) for c in zip(*g["heights"])]} for g in (b, f)]
        self.assertEqual(run("lee", write(trans[0]), write(trans[1]), "--wind", "+z")[0], 0)

    def test_upwind_motion_and_overhanging_lee_fail(self):
        b, f = self.grids(-2)
        code, res = run("lee", write(b), write(f), "--wind", "+x")
        self.assertEqual(code, 1)
        m = {x["metric"]: x for x in res["metrics"]}
        self.assertEqual(m["lee_deposition_fraction"]["verdict"], "FAIL")
        self.assertEqual(m["migration_m"]["verdict"], "FAIL")
        b, f = self.grids(2, lee_deg=60)
        code, res = run("lee", write(b), write(f), "--wind", "+x")
        self.assertEqual(code, 1)
        self.assertEqual({x["metric"]: x for x in res["metrics"]}["slip_face_deg"]["verdict"],
                         "FAIL")


class Runout(unittest.TestCase):
    def path(self, reach, drop=500.0):
        return recording({"front": [[reach * i / 299, drop * (1 - i / 299), 0.0]
                                    for i in range(300)]})

    def test_alpha_beta_runout(self):
        # beta 28 -> alpha 25.76; reaching 1036.1 m for a 500 m drop is alpha 25.76
        self.assertEqual(run("runout", self.path(1036.1), "--pos", "front", "--beta", 28)[0], 0)
        # stopping at 600 m is alpha 39.8: 14 deg off, more than 2 SD (7 deg)
        self.assertEqual(run("runout", self.path(600), "--pos", "front", "--beta", 28)[0], 1)
        self.assertEqual(run("runout", self.path(600), "--pos", "front", "--alpha", 39.8)[0], 0)


class Release(unittest.TestCase):
    def test_release_band_and_stability(self):
        good = [{"slope": s, "released": 30 <= s <= 45} for s in (25, 32, 38, 44, 50)]
        self.assertEqual(run("release", write(good))[0], 0)
        bad = good + [{"slope": 25, "released": True}]
        self.assertEqual(run("release", write({"trials": bad}))[0], 1)
        with_s = [{"slope": 38, "released": True, "S": 0.8},
                  {"slope": 38, "released": False, "S": 2.0},
                  {"slope": 40, "released": False, "S": 1.2}]
        self.assertEqual(run("release", write(with_s))[0], 0)
        self.assertEqual(run("release", write([{"slope": 38, "released": False, "S": 0.8}]))[0],
                         1)
        self.assertEqual(run("release", write([{"slope": 38, "released": True, "S": 2.0}]))[0], 1)


if __name__ == "__main__":
    unittest.main()
