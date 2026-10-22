"""Tests for the gpu-server skill's gpu_job.py and the tools skill's tools_check.py (stdlib only),
plus the guard's model_generators=remote policy.

g2 rows 34, 35, 41: open-weight 3D generators on a rented per-minute GPU fit neither `local` nor
`api`; every tool was found or installed by hand.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
SKILLS = os.path.join(HERE, "..", "plugins", "kiln", "skills")
GPU = os.path.join(SKILLS, "gpu-server", "scripts", "gpu_job.py")
TOOLS = os.path.join(SKILLS, "tools", "scripts", "tools_check.py")
sys.path.insert(0, HERE)
from test_guard import make_project, run_guard, shell  # noqa: E402

FAKE_PROVIDER = r'''
import json, os, shutil, subprocess, sys, time
state = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.json")
remote = os.path.join(os.path.dirname(os.path.abspath(__file__)), "remote")
cmd = sys.argv[1]
s = json.load(open(state)) if os.path.exists(state) else {"running": False, "starts": 0}
if cmd == "start":
    s["running"] = True; s["starts"] += 1
elif cmd == "stop":
    s["running"] = False
elif cmd == "status":
    print("running" if s["running"] else "stopped")
elif cmd == "exec":
    os.makedirs(remote, exist_ok=True)
    line = sys.argv[2]
    if line.startswith("mkdir -p "):                     # the remote shell is POSIX
        os.makedirs(os.path.join(remote, line[9:]), exist_ok=True)
        sys.exit(0)
    sys.exit(subprocess.run(line, shell=True, cwd=remote).returncode)
elif cmd == "push":
    os.makedirs(os.path.join(remote, os.path.dirname(sys.argv[3])), exist_ok=True)
    shutil.copy(sys.argv[2], os.path.join(remote, sys.argv[3]))
elif cmd == "pull":
    os.makedirs(sys.argv[3], exist_ok=True)
    src = os.path.join(remote, sys.argv[2])
    for n in os.listdir(src):
        shutil.copy(os.path.join(src, n), sys.argv[3])
json.dump(s, open(state, "w"))
'''


def provider(root):
    path = os.path.join(root, "fake_provider.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(FAKE_PROVIDER)
    p = [sys.executable, path]
    profile = {"rented": {
        "start": p + ["start"], "stop": p + ["stop"], "status": p + ["status"],
        "ready_when": "running",
        "exec": p + ["exec", "{cmd}"], "push": p + ["push", "{src}", "{dst}"],
        "pull": p + ["pull", "{src}", "{dst}"],
        "workdir": "jobs", "usd_per_hour": 0.60, "gpu": "RTX 4090 24 GB"}}
    cfg = os.path.join(root, "gpu.json")
    with open(cfg, "w", encoding="utf-8") as fh:
        json.dump(profile, fh)
    return cfg


def gpu(root, *args):
    p = subprocess.run([sys.executable, "-B", GPU, *args], cwd=root, capture_output=True,
                       text=True, timeout=120)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip().startswith("{") else p.stdout), p.stderr


class GpuJob(unittest.TestCase):
    def test_run_pushes_runs_pulls_and_stops_with_provenance(self):
        root = tempfile.mkdtemp(prefix="kiln-gpu-")
        cfg = provider(root)
        with open(os.path.join(root, "photo.png"), "wb") as fh:
            fh.write(b"img")
        cmd = sys.executable.replace("\\", "/") + ' -c "import shutil,os;os.makedirs(\'out\',exist_ok=True);shutil.copy(\'photo.png\',\'out/model.glb\')"'
        code, res, err = gpu(root, "run", "--config", cfg, "--profile", "rented", "--tool",
                             "trellis2", "--push", "photo.png", "--cmd", cmd, "--pull", "out",
                             "--into", "art/gen/head", "--max-usd", "1.0")
        self.assertEqual(code, 0, f"{res} {err}")
        self.assertTrue(os.path.isfile(os.path.join(root, "art", "gen", "head", "model.glb")))
        prov = json.load(open(os.path.join(root, "art", "gen", "head", "provenance.json")))
        self.assertEqual(prov["tool"], "trellis2")
        self.assertEqual(prov["gpu"], "RTX 4090 24 GB")
        self.assertIn("photo.png", prov["inputs"])
        self.assertLessEqual(prov["cost_usd_est"], 1.0)
        state = json.load(open(os.path.join(root, "server.json")))
        self.assertFalse(state["running"])                 # stopped after the job

    def test_spend_cap_turns_into_a_time_limit_and_stops_the_server(self):
        root = tempfile.mkdtemp(prefix="kiln-gpu-")
        cfg = provider(root)
        slow = sys.executable.replace("\\", "/") + ' -c "import time; time.sleep(30)"'
        code, res, err = gpu(root, "run", "--config", cfg, "--profile", "rented", "--tool", "x",
                             "--cmd", slow, "--max-usd", "0.0005")   # 0.0005 $ at 0.60 $/h = 3 s
        self.assertEqual(code, 1, f"{res} {err}")
        self.assertIn("spend cap", res["problems"][0])
        self.assertFalse(json.load(open(os.path.join(root, "server.json")))["running"])

    def test_estimate_and_one_job_lock(self):
        root = tempfile.mkdtemp(prefix="kiln-gpu-")
        cfg = provider(root)
        code, res, _ = gpu(root, "estimate", "--config", cfg, "--profile", "rented",
                           "--minutes", "30")
        self.assertAlmostEqual(res["cost_usd_est"], 0.30, places=2)
        with open(cfg + ".lock", "w") as fh:
            fh.write(json.dumps({"pid": 999999, "since": 0}))
        code, res, _ = gpu(root, "run", "--config", cfg, "--profile", "rented", "--tool", "x",
                           "--cmd", "echo hi", "--max-usd", "1")
        self.assertEqual(code, 0, res)                     # a stale lock (dead pid) is taken over


class GpuConfigDiscovery(unittest.TestCase):
    def test_a_project_gpu_json_is_never_picked_up_by_default(self):
        # KILN-REV-02 (review 2026-10-21): with CLAUDE_PLUGIN_DATA unset the old-location
        # candidate became the relative "gpu.json", so a project's file was run as the machine
        # profile. The sentinel command only writes a marker file in the throwaway project.
        root = tempfile.mkdtemp(prefix="kiln-gpucwd-")
        home = tempfile.mkdtemp(prefix="kiln-gpuhome-")
        marker = os.path.join(root, "RAN")
        touch = [sys.executable, "-c", f"open({marker!r}, 'w').close()"]
        with open(os.path.join(root, "gpu.json"), "w", encoding="utf-8") as fh:
            json.dump({"rented": {"start": touch, "stop": touch, "status": touch,
                                  "ready_when": "x", "exec": touch, "push": touch,
                                  "pull": touch, "workdir": "w", "usd_per_hour": 1.0}}, fh)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_DATA"}
        env.update(KILN_HOME=home, HOME=home, USERPROFILE=home)
        p = subprocess.run([sys.executable, "-B", GPU, "status", "--profile", "rented"],
                           cwd=root, env=env, capture_output=True, text=True, timeout=60)
        self.assertFalse(os.path.exists(marker), p.stdout + p.stderr)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("no GPU profile file", p.stdout + p.stderr)
        # an explicit --config is the user's choice and still works
        p = subprocess.run([sys.executable, "-B", GPU, "status", "--profile", "rented",
                            "--config", os.path.join(root, "gpu.json")],
                           cwd=root, env=env, capture_output=True, text=True, timeout=60)
        self.assertTrue(os.path.exists(marker), p.stdout + p.stderr)


class Tools(unittest.TestCase):
    def test_detect_and_verify(self):
        root = tempfile.mkdtemp(prefix="kiln-tools-")
        bin_dir = os.path.join(root, "_tools", "fake", "1.2.3")
        os.makedirs(bin_dir)
        script = os.path.join(bin_dir, "faketool.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write("print('faketool 1.2.3')\n")
        manifest = {"tools": [
            {"name": "faketool", "version": "1.2.3", "find": ["faketool.py"],
             "verify": [sys.executable, "{path}"], "expect": "1.2.3",
             "source": "https://example.invalid/faketool", "licence": "MIT"},
            {"name": "missing", "version": "9", "find": ["nope.exe"], "verify": ["{path}"],
             "expect": "9", "source": "https://example.invalid/missing", "licence": "MIT"}]}
        mpath = os.path.join(root, "tools.json")
        with open(mpath, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)
        p = subprocess.run([sys.executable, "-B", TOOLS, "verify", mpath, "--tools-root",
                            os.path.join(root, "_tools")], capture_output=True, text=True,
                           timeout=60)
        res = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1, res)
        rows = {r["name"]: r for r in res["tools"]}
        self.assertEqual(rows["faketool"]["status"], "ok", rows)
        self.assertEqual(rows["missing"]["status"], "missing")
        self.assertIn("example.invalid/missing", rows["missing"]["install_from"])


class RemoteGenerators(unittest.TestCase):
    def test_remote_policy_allows_only_the_job_runner(self):
        root = make_project("godot", "model_generators=remote\n")
        ok, _ = run_guard(root, shell('python gpu_job.py run --profile rented --tool trellis2 '
                                      '--cmd "python run.py --model trellis2 in.png"'))
        self.assertEqual(ok, "ALLOW")
        local, reason = run_guard(root, shell("python run.py --model trellis2 photo.png"))
        self.assertEqual(local, "DENY")
        self.assertIn("gpu_job.py", reason)
        api, _ = run_guard(root, shell("curl https://api.meshy.ai/v2/image-to-3d"))
        self.assertEqual(api, "DENY")


if __name__ == "__main__":
    unittest.main()
