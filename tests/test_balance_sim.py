"""Tests for plugins/kiln/skills/balance/scripts/balance_sim.py (stdlib + numpy)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "balance",
                      "scripts", "balance_sim.py")


def write(data):
    fd, path = tempfile.mkstemp(prefix="kiln-balance-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


def run(*args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       timeout=120, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


class Ttk(unittest.TestCase):
    def test_deterministic_weapon_matches_hand_math(self):
        # 25 dmg, 600 rpm (10/s), always hits: 100 hp -> 4 shots -> 3 intervals = 0.3 s
        w = write({"weapons": [{"name": "rifle", "damage": 25, "rpm": 600, "accuracy": 1.0}]})
        e = write({"enemies": [{"name": "grunt", "hp": 100, "ttk_target": [0.25, 0.35]}]})
        code, res = run("ttk", "--weapons", w, "--enemies", e, "--trials", "500")
        self.assertEqual(code, 0, res["problems"])
        row = res["table"][0]
        self.assertEqual(row["stk_body"], 4)
        self.assertAlmostEqual(row["ttk_ideal_s"], 0.3)
        self.assertAlmostEqual(row["ttk_p50_s"], 0.3)
        self.assertAlmostEqual(row["ttk_p90_s"], 0.3)
        self.assertEqual(row["kill_rate"], 1.0)
        self.assertAlmostEqual(row["dps_expected"], 250.0)

    def test_armour_reload_falloff_and_target_failure(self):
        w = write({"weapons": [{"name": "smg", "damage": 22, "rate": 10, "magazine": 5,
                                "reload_s": 2.0, "accuracy": 1.0,
                                "falloff": [[0, 1.0], [10, 1.0], [30, 0.5]]}]})
        e = write({"enemies": [{"name": "mech", "hp": 100, "armor_flat": 2,
                                "ttk_target": {"*": [0.1, 0.5]}}]})
        code, res = run("ttk", "--weapons", w, "--enemies", e, "--ranges", "5", "30",
                        "--trials", "200")
        near, far = res["table"]
        # 20 dmg after armour -> 5 shots, all in one magazine: 0.4 s
        self.assertEqual(near["stk_body"], 5)
        self.assertAlmostEqual(near["ttk_ideal_s"], 0.4)
        # 30 m: 11 raw - 2 = 9 -> 12 shots: 11 intervals + 2 reloads = 1.1 + 4.0 s
        self.assertEqual(far["stk_body"], 12)
        self.assertAlmostEqual(far["ttk_ideal_s"], 5.1)
        self.assertEqual(code, 1)
        self.assertIn("at 30.0 m", " ".join(res["problems"]))
        self.assertEqual(near["problems"], [])

    def test_accuracy_spreads_ttk_and_headshots_help(self):
        w = write({"weapons": [{"name": "ar", "damage": 20, "rate": 10,
                                "multipliers": {"head": 2.0},
                                "accuracy": {"body": 0.5, "head": 0.2}}]})
        e = write({"enemies": [{"name": "grunt", "hp": 200}]})
        code, res = run("ttk", "--weapons", w, "--enemies", e, "--trials", "4000", "--seed", "7")
        row = res["table"][0]
        self.assertEqual(code, 0)
        self.assertLess(row["ttk_p10_s"], row["ttk_p50_s"])
        self.assertLess(row["ttk_p50_s"], row["ttk_p90_s"])
        self.assertGreater(row["ttk_p50_s"], row["ttk_ideal_s"] * 0.8)
        # expected damage per shot = 0.5*20 + 0.2*40 = 18 -> 180 dps
        self.assertAlmostEqual(row["dps_expected"], 180.0)
        _, again = run("ttk", "--weapons", w, "--enemies", e, "--trials", "4000", "--seed", "7")
        self.assertEqual(again["table"][0]["ttk_p50_s"], row["ttk_p50_s"])

    def test_immune_target_never_dies(self):
        w = write({"weapons": [{"name": "pea", "damage": 3, "rate": 5}]})
        e = write({"enemies": [{"name": "tank", "hp": 50, "armor_flat": 5,
                                "ttk_target": [1, 5]}]})
        code, res = run("ttk", "--weapons", w, "--enemies", e, "--trials", "50")
        self.assertEqual(code, 1)
        self.assertEqual(res["table"][0]["kill_rate"], 0.0)
        self.assertIsNone(res["table"][0]["ttk_p50_s"])


class Economy(unittest.TestCase):
    BASE = {"sessions": 20, "sources": [{"name": "loot", "amount": 10, "per_session": 20}]}

    def test_no_sinks_is_inflation(self):
        code, res = run("economy", write(self.BASE), "--players", "300")
        self.assertEqual(code, 1)
        self.assertIn("inflation", " ".join(res["problems"]))
        self.assertGreater(res["hoard_sessions_of_income"], 5)

    def test_matched_sinks_pass(self):
        cfg = dict(self.BASE, sinks=[
            {"name": "ammo", "kind": "repeatable", "cost": 5, "per_session": 20},
            {"name": "upgrades", "kind": "upgrade", "cost": 50, "growth": 1.15, "max": 40}])
        code, res = run("economy", write(cfg), "--players", "300")
        self.assertEqual(code, 0, res["problems"])
        self.assertGreater(res["sink_source_ratio"], 0.8)

    def test_expensive_needs_are_scarcity(self):
        cfg = dict(self.BASE, sinks=[{"name": "repairs", "kind": "upkeep", "cost": 400}])
        code, res = run("economy", write(cfg), "--players", "300")
        self.assertEqual(code, 1)
        self.assertIn("scarcity", " ".join(res["problems"]))

    def test_item_pacing_against_plan(self):
        # ~200 per session: a 1000 item lands around session 5
        cfg = dict(self.BASE, sinks=[{"name": "shop", "kind": "items", "items": [
            {"name": "shotgun", "cost": 1000, "planned": 5},
            {"name": "railgun", "cost": 1500, "planned": 3}]}])
        code, res = run("economy", write(cfg), "--players", "300")
        items = {i["item"]: i for i in res["items"]}
        self.assertAlmostEqual(items["shotgun"]["median_session"], 5, delta=1)
        text = " ".join(res["problems"])
        self.assertIn("railgun", text)
        self.assertNotIn("shotgun", text)
        self.assertEqual(code, 1)

    def test_csv_written(self):
        out = os.path.join(tempfile.mkdtemp(prefix="kiln-balance-"), "e.csv")
        run("economy", write(self.BASE), "--players", "50", "--csv", out)
        with open(out, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertEqual(len(lines), 21)
        self.assertTrue(lines[0].startswith("session,income_mean"))


class Drops(unittest.TestCase):
    def test_plain_chance(self):
        code, res = run("drops", "--p", "0.01", "--attempts", "100", "299")
        self.assertEqual(code, 0)
        self.assertAlmostEqual(res["p_by_attempts"]["100"], 1 - 0.99 ** 100, places=3)
        self.assertAlmostEqual(res["p_by_attempts"]["299"], 0.95, places=2)
        self.assertAlmostEqual(res["expected_attempts"], 100, delta=0.5)

    def test_hard_pity_caps_attempts(self):
        code, res = run("drops", "--p", "0.01", "--hard-pity", "50", "--max-p90", "40")
        self.assertEqual(res["attempts_p99"], 50)
        self.assertLessEqual(res["expected_attempts"], 50)
        self.assertEqual(code, 1)  # p90 = 50 > 40

    def test_prd_constant(self):
        code, res = run("drops", "--p", "0.25", "--prd")
        self.assertEqual(code, 0)
        self.assertAlmostEqual(res["prd_constant"], 0.084744, places=5)
        self.assertAlmostEqual(res["effective_rate"], 0.25, places=3)
        self.assertLessEqual(res["attempts_p99"], 12)


class Curve(unittest.TestCase):
    def test_wall_and_targets(self):
        cfg = {"levels": 10, "xp": {"kind": "poly", "a": 100, "k": 2},
               "rate": {"kind": "linear", "a": 1000, "b": 0}, "rate_unit": "hour",
               "targets": [[1, 0.05, 0.2], [10, 5, 12]], "max_step": 1.5}
        code, res = run("curve", write(cfg))
        self.assertEqual(code, 1)
        text = " ".join(res["problems"])
        self.assertIn("level 2: time per level jumps x4.00", text)
        self.assertEqual(res["table"][9]["xp_to_next"], 10000.0)
        self.assertAlmostEqual(res["table"][9]["hours"], 10.0)

    def test_smooth_curve_passes(self):
        cfg = {"levels": 20, "xp": {"kind": "exp", "a": 100, "r": 1.2},
               "rate": {"kind": "exp", "a": 600, "r": 1.1}, "max_step": 1.2}
        code, res = run("curve", write(cfg))
        self.assertEqual(code, 0, res["problems"])


if __name__ == "__main__":
    unittest.main()
