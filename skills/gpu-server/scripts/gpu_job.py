"""Run one job on a rented GPU server: start it, push inputs, run, pull outputs, write provenance,
stop it - under a spend cap and a one-job lock. Stdlib only; provider-neutral (every provider
command is a template in the machine's GPU profile, never in the project).

  python gpu_job.py estimate --profile rented --minutes 30
  python gpu_job.py run --profile rented --tool trellis2 --push ref/head_front.png \
      --cmd "python run.py --image head_front.png --out out" --pull out \
      --into art/gen/head --max-usd 2.00 [--max-minutes 40] [--keep] [--config <gpu.json>]
  python gpu_job.py status --profile rented
  python gpu_job.py stop --profile rented

Profile file (default `~/.kiln/gpu.json`, KILN_HOME overrides the folder; outside
every project, so no host, key path or provider id lands in git):

  {"rented": {
     "start":  ["runpodctl", "pod", "start", "<pod-id>"],
     "stop":   ["runpodctl", "pod", "stop", "<pod-id>"],
     "status": ["runpodctl", "pod", "get", "<pod-id>"], "ready_when": "RUNNING",
     "exec":   ["ssh", "-i", "C:/Users/me/.ssh/gpu", "root@1.2.3.4", "-p", "22022", "{cmd}"],
     "push":   ["scp", "-i", "...", "-P", "22022", "{src}", "root@1.2.3.4:{dst}"],
     "pull":   ["scp", "-r", "-i", "...", "-P", "22022", "root@1.2.3.4:{src}/.", "{dst}"],
     "workdir": "/workspace/kiln", "usd_per_hour": 0.69, "gpu": "RTX 4090 24 GB",
     "setup": "cd /workspace/kiln && ./setup_env.sh"}}

{cmd} {src} {dst} are filled in per call. The job runs in <workdir>/<job id>; inputs land there
by base name. The run's wall-clock limit is min(--max-minutes, --max-usd / usd_per_hour); when it
is hit the local transport process tree is killed by PID, the server is stopped and the run
fails with "spend cap". The server is stopped after every run unless --keep (then the profile's
own idle auto-stop must exist). provenance.json goes next to the pulled outputs: tool, profile,
gpu, command, input sha256, start/end, wall seconds, estimated cost, exit code.
Output: JSON; exit 0 ok, 1 failed.
"""

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid


def default_config():
    """The machine's Kiln folder (~/.kiln, shared by both plugins and Codex); the old locations
    are read when the file is still there."""
    home = os.environ.get("KILN_HOME") or os.path.join(os.path.expanduser("~"), ".kiln")
    old = [os.path.join(os.path.expanduser("~"), ".config", "kiln", "gpu.json")]
    # only a set, absolute plugin-data folder: an unset variable once made this the relative
    # "gpu.json", and a project's file was run as the machine profile (review 2026-10-21,
    # KILN-REV-02). The profile never comes from the project unless --config names it.
    data = os.environ.get("CLAUDE_PLUGIN_DATA") or ""
    if data and os.path.isabs(data):
        old.insert(0, os.path.join(data, "gpu.json"))
    for path in old:
        if os.path.isabs(path) and os.path.isfile(path) and \
                not os.path.isfile(os.path.join(home, "gpu.json")):
            return path
    return os.path.join(os.path.abspath(home), "gpu.json")


def load_profile(path, name):
    try:
        with open(path, encoding="utf-8") as fh:
            profiles = json.load(fh)
    except OSError:
        sys.exit(json.dumps({"problems": [f"no GPU profile file {path} (gpu-server skill: "
                                          "create it outside the project)"], "verdict": "fail"}))
    if name not in profiles:
        sys.exit(json.dumps({"problems": [f"no profile '{name}' in {path}"], "verdict": "fail"}))
    return profiles[name]


def fill(template, **values):
    out = []
    for part in template:
        for key, val in values.items():
            part = part.replace("{" + key + "}", str(val))
        out.append(part)
    return out


def call(template, timeout=None, **values):
    """Run a provider command; output to a temp file (no pipes a grandchild could hold open);
    on timeout kill the whole process tree by PID."""
    cmd = fill(template, **values)
    with tempfile.TemporaryFile() as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        try:
            code = proc.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True)
            else:
                proc.kill()
            code, timed_out = proc.wait(), True
        log.seek(0)
        text = log.read().decode("utf-8", "replace")
    return code, text, timed_out


def pid_alive(pid):
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True,
                             text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def take_lock(path):
    lock = path + ".lock"
    if os.path.exists(lock):
        try:
            with open(lock, encoding="utf-8") as fh:
                held = json.load(fh)
        except (OSError, ValueError):
            held = {}
        if held.get("pid") and pid_alive(int(held["pid"])):
            return None, f"another GPU job is running (pid {held['pid']}, lock {lock})"
    with open(lock, "w", encoding="utf-8") as fh:
        json.dump({"pid": os.getpid(), "since": time.time()}, fh)
    return lock, None


def ensure_running(p, wait_s):
    code, out, _ = call(p["status"], timeout=60)
    if p.get("ready_when", "running") in out:
        return True
    call(p["start"], timeout=300)
    deadline = time.time() + wait_s
    while time.time() < deadline:
        code, out, _ = call(p["status"], timeout=60)
        if p.get("ready_when", "running") in out:
            return True
        time.sleep(5)
    return False


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def cmd_run(a, p):
    lock, why = take_lock(a.config)
    if lock is None:
        return {"problems": [why], "verdict": "fail"}, 1
    started = time.time()
    problems, code = [], None
    rate = float(p.get("usd_per_hour", 0))
    limit_s = a.max_minutes * 60
    if rate > 0:
        limit_s = min(limit_s, a.max_usd / rate * 3600)
    job = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    jobdir = f"{p.get('workdir', '.').rstrip('/')}/{job}"
    try:
        if not ensure_running(p, a.ready_timeout):
            problems.append("server did not become ready")
            return {"problems": problems, "verdict": "fail"}, 1
        call(p["exec"], timeout=120, cmd=f"mkdir -p {jobdir}")      # servers run a POSIX shell
        for src in a.push or []:
            c, out, _ = call(p["push"], timeout=1800, src=src,
                             dst=f"{jobdir}/{os.path.basename(src)}")
            if c:
                problems.append(f"push {src} failed: {out[-300:]}")
        if not problems:
            if p.get("setup"):
                call(p["exec"], timeout=1800, cmd=p["setup"])
            left = max(1.0, limit_s - (time.time() - started))
            code, out, timed_out = call(p["exec"], timeout=left, cmd=f"cd {jobdir} && {a.cmd}")
            if timed_out:
                problems.append(f"spend cap: stopped after {left:.0f} s (max ${a.max_usd} at "
                                f"${rate}/h, or --max-minutes {a.max_minutes})")
            elif code:
                problems.append(f"job exited {code}: {out[-500:]}")
        if not problems and a.pull:
            into = a.into or os.path.join(".kiln", "tmp", "gpu", job)
            c, out, _ = call(p["pull"], timeout=1800, src=f"{jobdir}/{a.pull}", dst=into)
            if c:
                problems.append(f"pull failed: {out[-300:]}")
    finally:
        if not a.keep:
            call(p["stop"], timeout=300)
        os.remove(lock)
    wall = time.time() - started
    result = {"job": job, "profile": a.profile, "tool": a.tool, "gpu": p.get("gpu"),
              "command": a.cmd, "inputs": {os.path.basename(s): sha256(s) for s in a.push or []
                                           if os.path.isfile(s)},
              "start": datetime.datetime.fromtimestamp(started).isoformat(timespec="seconds"),
              "end": datetime.datetime.now().isoformat(timespec="seconds"),
              "wall_s": round(wall, 1), "cost_usd_est": round(wall / 3600 * rate, 4),
              "exit_code": code, "server_stopped": not a.keep}
    if not problems and a.pull:
        into = a.into or os.path.join(".kiln", "tmp", "gpu", job)
        with open(os.path.join(into, "provenance.json"), "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=1)
        result["outputs"] = into
    result.update({"problems": problems, "verdict": "fail" if problems else "pass"})
    return result, 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd_name", required=True)
    for name in ("estimate", "run", "status", "stop"):
        s = sub.add_parser(name)
        s.add_argument("--profile", required=True)
        s.add_argument("--config", default=default_config())
        if name == "estimate":
            s.add_argument("--minutes", type=float, required=True)
        if name == "run":
            s.add_argument("--tool", required=True)
            s.add_argument("--cmd", required=True)
            s.add_argument("--push", nargs="*")
            s.add_argument("--pull")
            s.add_argument("--into")
            s.add_argument("--max-usd", type=float, required=True)
            s.add_argument("--max-minutes", type=float, default=60.0)
            s.add_argument("--ready-timeout", type=float, default=600.0)
            s.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    p = load_profile(a.config, a.profile)
    if a.cmd_name == "estimate":
        rate = float(p.get("usd_per_hour", 0))
        res, code = {"profile": a.profile, "gpu": p.get("gpu"), "usd_per_hour": rate,
                     "minutes": a.minutes, "cost_usd_est": round(a.minutes / 60 * rate, 4)}, 0
    elif a.cmd_name == "status":
        c, out, _ = call(p["status"], timeout=60)
        res, code = {"profile": a.profile, "ready": p.get("ready_when", "running") in out,
                     "output": out[-500:]}, 0
    elif a.cmd_name == "stop":
        c, out, _ = call(p["stop"], timeout=300)
        res, code = {"profile": a.profile, "stopped": c == 0, "output": out[-300:]}, c
    else:
        res, code = cmd_run(a, p)
    print(json.dumps(res, indent=1))
    sys.exit(code)


if __name__ == "__main__":
    main()
