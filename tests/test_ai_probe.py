"""Tests for plugins/kiln/skills/game-ai/scripts/ai_probe.py (stdlib only)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "game-ai",
                      "scripts", "ai_probe.py")
HZ = 60
N = 600
TMP = tempfile.TemporaryDirectory(prefix="kiln-ai-")


def tearDownModule():
    TMP.cleanup()


def run(samples, *args, lines=False):
    fd, path = tempfile.mkstemp(suffix=".jsonl" if lines else ".json", dir=TMP.name)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        if lines:
            n = len(next(iter(samples.values())))
            fh.write("\n".join(json.dumps({"dt": 1 / HZ, **{k: v[i] for k, v in samples.items()}})
                               for i in range(n)))
        else:
            json.dump({"physics_ticks_per_second": HZ, "ticks": list(range(N)),
                       "frame_ms": [16.6] * N, "samples": samples}, fh)
    p = subprocess.run([sys.executable, "-B", SCRIPT, path, *args], capture_output=True,
                       text=True, timeout=60)
    return p.returncode, json.loads(p.stdout)


def by_name(res):
    return {m["metric"]: m for m in res["metrics"]}


def fair_agent(name, sight=60, first_shot=90, attack=(90, 150), walk=True):
    """Sees the player at `sight`, shoots from `first_shot` every 30 ticks while visible."""
    los = [i >= sight for i in range(N)]
    fired = [i >= first_shot and (i - first_shot) % 30 == 0 for i in range(N)]
    attacking = [attack[0] <= i < attack[1] for i in range(N)]
    pos = [[0.02 * i if walk else 0.0, 0.0, 0.0] for i in range(N)]   # 1.2 m/s
    state = ["patrol" if i < sight else "combat" for i in range(N)]
    return {f"{name}.los": los, f"{name}.fired": fired, f"{name}.attacking": attacking,
            f"{name}.pos": pos, f"{name}.moving": [True] * N, f"{name}.state": state}


class AiProbe(unittest.TestCase):
    def test_fair_squad_passes(self):
        s = {**fair_agent("g1"), **fair_agent("g2", sight=70, first_shot=110, attack=(160, 220))}
        code, res = run(s, "--tokens", "1")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["verdict"], "PASS")
        self.assertEqual(res["agents"], ["g1", "g2"])
        m = by_name(res)
        self.assertEqual(m["reaction_min_ms"]["value"], 500.0)
        self.assertEqual(m["max_concurrent_attackers"]["value"], {"*": 1})

    def test_shot_without_los_fails(self):
        s = fair_agent("g1")
        s["g1.fired"][30] = True                       # before the player is visible
        code, res = run(s)
        self.assertEqual(code, 1)
        m = by_name(res)["shots_without_los"]
        self.assertEqual(m["verdict"], "FAIL")
        self.assertEqual(m["first"][0]["tick"], 30)

    def test_instant_reaction_fails(self):
        code, res = run(fair_agent("g1", sight=60, first_shot=63))   # 50 ms
        self.assertEqual(by_name(res)["reaction_min_ms"]["verdict"], "FAIL")

    def test_brief_los_drop_is_not_a_new_sighting(self):
        s = fair_agent("g1")
        for i in range(200, 210):                      # 1/6 s occlusion, shot right after
            s["g1.los"][i] = False
        s["g1.fired"][211] = True
        code, res = run(s)
        self.assertEqual(by_name(res)["reaction_min_ms"]["value"], 500.0)

    def test_token_limit_exceeded(self):
        s = {**fair_agent("g1"), **fair_agent("g2"), **fair_agent("g3")}
        code, res = run(s, "--tokens", "2")
        m = by_name(res)["max_concurrent_attackers"]
        self.assertEqual(m["verdict"], "FAIL")
        self.assertEqual(m["value"], {"*": 3})

    def test_typed_tokens(self):
        s = {**fair_agent("g1"), **fair_agent("g2")}
        s["g1.attacking"] = ["melee" if 90 <= i < 150 else "" for i in range(N)]
        s["g2.attacking"] = ["ranged" if 100 <= i < 160 else None for i in range(N)]
        code, res = run(s, "--tokens", "melee=1,ranged=1")
        self.assertEqual(by_name(res)["max_concurrent_attackers"]["verdict"], "PASS", res)
        s["g2.attacking"] = ["melee" if 100 <= i < 160 else None for i in range(N)]
        code, res = run(s, "--tokens", "melee=1,ranged=1")
        self.assertEqual(by_name(res)["max_concurrent_attackers"]["verdict"], "FAIL")

    def test_stuck_agent(self):
        code, res = run(fair_agent("g1", walk=False))
        m = by_name(res)["stuck_episodes"]
        self.assertEqual(m["verdict"], "FAIL")
        self.assertEqual(m["value"], 1)

    def test_state_dithering(self):
        s = fair_agent("g1")
        for i in range(300, 305):                      # 83 ms in cover, then back
            s["g1.state"][i] = "cover"
        code, res = run(s)
        m = by_name(res)["state_flips"]
        self.assertEqual(m["verdict"], "FAIL")
        self.assertEqual(m["first"][0]["flip"], "combat>cover>combat")

    def test_json_lines_and_unit_scale(self):
        s = fair_agent("g1")
        s["g1.pos"] = [{"x": 2.0 * i, "y": 0.0, "z": 0.0} for i in range(N)]   # cm, 1.2 m/s
        code, res = run(s, lines=True)
        self.assertEqual(by_name(res)["stuck_episodes"]["verdict"], "PASS")
        code, res = run(s, "--unit-scale", "0.001", lines=True)               # 0.12 m/s: stuck
        self.assertEqual(by_name(res)["stuck_episodes"]["verdict"], "FAIL")

    def test_no_agents_not_assessed(self):
        code, res = run({"player_pos": [[0, 0, 0]] * N})
        self.assertEqual(code, 2)
        self.assertEqual(res["verdict"], "NOT ASSESSED")


if __name__ == "__main__":
    unittest.main()
