"""Morning report over a night of autoplay runs (autoplay_loop.py output). Stdlib only.

  python autoplay_report.py production/autoplay/<night>

Per run (run_NNN/summary.json, log.txt, exit.json): seed, verdict, objectives reached, stuck
events, hitches (frames after a screenshot excluded and counted apart), and the crash class:
  exit     the game printed "AUTOPLAY done" and then exited abnormally (a shutdown crash: engine
           teardown, audio driver, physics server) - report it, but it is not a gameplay crash
  mid-run  abnormal exit before "AUTOPLAY done", a timeout, or a run that never got going (no
           "AUTOPLAY done" and no summary.json, whatever the exit code: a script parse error)
Writes <night>/REPORT.md (runs, % of objectives reached, failures with their seeds) and prints the
same as JSON. Exit 0.
"""

import json
import os
import sys


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def main():
    night = sys.argv[1] if len(sys.argv) > 1 else "."
    runs = sorted(d for d in os.listdir(night) if d.startswith("run_"))
    results, objectives = [], {}
    for name in runs:
        folder = os.path.join(night, name)
        summary = load(os.path.join(folder, "summary.json"), {})
        exit_info = load(os.path.join(folder, "exit.json"), {})
        try:
            with open(os.path.join(folder, "log.txt"), encoding="utf-8", errors="replace") as fh:
                log = fh.read()
        except OSError:
            log = ""
        code = exit_info.get("exit_code", 0)
        finished = "AUTOPLAY done" in log
        crash = None
        if exit_info.get("timed_out"):
            crash = "mid-run"
        elif not finished and not summary:  # never ran to the end: a parse error, a crash on
            crash = "mid-run"               # load (bug hunt 2026-10-20: exit 1 read as a FAIL)
        elif code not in (0, 1):            # 1 = a FAIL verdict, not a crash
            crash = "exit" if finished else "mid-run"
        seed = summary.get("seed", exit_info.get("seed"))
        for obj, t in (summary.get("objectives") or {}).items():
            o = objectives.setdefault(obj, {"reached": 0, "runs": 0, "missed_seeds": []})
            o["runs"] += 1
            if t is not None:
                o["reached"] += 1
            else:
                o["missed_seeds"].append(seed)
        results.append({"run": name, "seed": seed, "verdict": summary.get("verdict", "NONE"),
                        "exit_code": code, "crash": crash,
                        "stuck": summary.get("stuck", []),
                        "hitches": summary.get("hitches"),
                        "hitches_after_shot": summary.get("hitches_after_shot")})
    rep = {"night": night, "runs": len(results),
           "crashes_mid_run": sum(r["crash"] == "mid-run" for r in results),
           "crashes_at_exit": sum(r["crash"] == "exit" for r in results),
           "stuck_runs": [r["seed"] for r in results if r["stuck"]],
           "objectives": objectives, "results": results}
    lines = [f"# Autoplay report — {night}", "",
             f"Runs: {rep['runs']} · crashes mid-run: {rep['crashes_mid_run']} · "
             f"crashes at exit (after AUTOPLAY done): {rep['crashes_at_exit']} · "
             f"runs with a stuck event: {len(rep['stuck_runs'])}", "",
             "| objective | reached | missed seeds |", "|---|---|---|"]
    for obj, o in objectives.items():
        lines.append(f"| {obj} | {o['reached']}/{o['runs']} | "
                     f"{', '.join(str(s) for s in o['missed_seeds'][:10]) or '-'} |")
    lines += ["", "| run | seed | verdict | crash | stuck | hitches (+ after shots) |",
              "|---|---|---|---|---|---|"]
    for r in results:
        stuck = "; ".join(f"t={s.get('t')} at {s.get('where')}" for s in r["stuck"][:2]) or "-"
        lines.append(f"| {r['run']} | {r['seed']} | {r['verdict']} | {r['crash'] or '-'} | "
                     f"{stuck} | " + ("n/a (headless)" if r["hitches"] is None else
                                      f"{r['hitches']} (+{r['hitches_after_shot']})") + " |")
    with open(os.path.join(night, "REPORT.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
