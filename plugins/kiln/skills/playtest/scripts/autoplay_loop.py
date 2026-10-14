"""Run many autoplay runs while the user is away; stop the moment they return. Stdlib only.

  python autoplay_loop.py --runs 30 --seed 1 --out production/autoplay/<night> [--min-idle 600]
      [--timeout 900] -- <game command ...>

The game command gets `--seed N --out <out>/run_NNN` appended after its own arguments (for a
Godot autoplay script, end the command with `--` so they reach the script:
`-- godot --path . -s res://tests/autoplay/run_full.gd --`). Before every run, presence.py must
say the user is away (flag `.kiln/away` or OS idle >= --min-idle); when they are back the loop
stops (exit 2) and the report covers the runs so far. Each run's stdout/stderr go to
run_NNN/log.txt and its exit code to run_NNN/exit.json; a run over --timeout is killed by PID.
Then `autoplay_report.py <out>` writes REPORT.md.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import presence  # noqa: E402


def main():
    argv = sys.argv[1:]
    if "--" not in argv:
        sys.exit("give the game command after --")
    cut = argv.index("--")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-idle", type=float, default=600.0)
    ap.add_argument("--timeout", type=float, default=900.0)
    a = ap.parse_args(argv[:cut])
    game = argv[cut + 1:]
    done = 0
    for i in range(a.runs):
        p = presence.check(a.min_idle)
        if not p["away"]:
            print(json.dumps({"stopped": "user present", "runs_done": done, "presence": p}))
            sys.exit(2)
        seed = a.seed + i
        out = os.path.join(a.out, f"run_{i + 1:03d}")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "log.txt"), "w", encoding="utf-8", errors="replace") as log:
            proc = subprocess.Popen(game + ["--seed", str(seed), "--out", out], stdout=log,
                                    stderr=subprocess.STDOUT)
            try:
                code = proc.wait(timeout=a.timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                                   capture_output=True)
                else:
                    proc.kill()
                code, timed_out = proc.wait(), True
        with open(os.path.join(out, "exit.json"), "w", encoding="utf-8") as fh:
            json.dump({"seed": seed, "exit_code": code, "timed_out": timed_out}, fh)
        done += 1
    print(json.dumps({"runs_done": done, "out": a.out}))


if __name__ == "__main__":
    main()
