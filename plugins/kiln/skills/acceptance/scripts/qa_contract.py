"""Scene QA contract: record a scene's named QA states and judge them all, one report.

  python qa_contract.py run --contract res://tests/qa/plaza_qa.gd [--project .] [--godot EXE]
         [--windowed] [--out production/qa/<contract>]
  python qa_contract.py report <run folder>

run      records the contract with Godot (headless unless --windowed: `frames` states need a
         window), then reports. Godot: --godot, else KILN_GODOT, else the machine config.
report   reads <run>/qa_run.json (written by qa_contract.gd) and judges each state:
         ui          text wider than its control, a control outside its container (> 1 px),
                     plus ui_check.py layout (overlaps, safe area, target sizes)
         anchor      max distance emitter-holder over the frames <= the state's `tolerance`
                     (default 0.05 m in 3D, 2 px in 2D)
         loop        analyze.py rigid    transition  analyze.py pops    attack  analyze.py hits
         frames      frames.py anim (`check: anim`, `off`) or ramp (`check: ramp`, `steady`)
         and writes <run>/report.json {verdict, states [{name, kind, verdict, ...}]}.
A state that could not be recorded is NOT ASSESSED. Exit 1 when any state fails.
Contract format and kinds: qa_contract.gd (copy it to tests/qa/ with probe_base.gd).
"""

import argparse
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UI_CHECK = os.path.join(HERE, "..", "..", "ui", "scripts", "ui_check.py")


def tool(script, *args):
    p = subprocess.run([sys.executable, "-B", script, *args], capture_output=True, text=True,
                       timeout=600)
    try:
        return json.loads(p.stdout)
    except ValueError:
        return {"verdict": "NOT ASSESSED", "note": (p.stdout + p.stderr)[-400:]}


def ui(state):
    path = os.path.join(state["dir"], "elements.json")
    elements = json.load(open(path, encoding="utf-8"))["elements"]
    problems = []
    for e in elements:
        r = e["global_rect"]
        x, y, w, h = r["position"]["x"], r["position"]["y"], r["size"]["x"], r["size"]["y"]
        if e.get("text_width") is not None and e["text_width"] > w + 1:
            problems.append(f"{e['path']}: text '{e.get('text', '')[:40]}' is "
                            f"{e['text_width']:.0f} px wide in a {w:.0f} px control")
        if e.get("parent_rect"):
            px, py, pw, ph = e["parent_rect"]
            out = max(px - x, py - y, (x + w) - (px + pw), (y + h) - (py + ph))
            if out > 1:
                problems.append(f"{e['path']}: {out:.0f} px outside its container")
    vw, vh = state.get("viewport") or [1920, 1080]
    layout = tool(UI_CHECK, "layout", path, "--viewport", f"{int(vw)}x{int(vh)}")
    if layout.get("verdict") == "FAIL":
        problems.append("ui_check layout: " + "; ".join(str(p) for p in layout.get("problems", [])[:4]))
    return {"verdict": "FAIL" if problems else "PASS", "problems": problems,
            "elements": len(elements), "ui_check": layout.get("verdict")}


def anchor(state):
    data = json.load(open(os.path.join(state["dir"], "data.json"), encoding="utf-8"))
    em, ho = data["samples"].get("emitter"), data["samples"].get("holder")
    if not em or not ho or not em[0] or not ho[0]:
        return {"verdict": "NOT ASSESSED", "note": "track needs emitter and holder"}
    dists = [math.dist(a, b) for a, b in zip(em, ho) if a and b]
    tol = state.get("tolerance", 0.05 if len(em[0]) == 3 else 2.0)
    worst = max(dists)
    return {"verdict": "PASS" if worst <= tol else "FAIL", "max_distance": round(worst, 4),
            "tolerance": tol, "frame": dists.index(worst),
            "problem": None if worst <= tol else
            f"the emitter is {worst:.3f} from its holder (> {tol}): the effect is drawn away "
            "from what carries it"}


def analyze(cmd, state):
    data = os.path.join(state["dir"], "data.json")
    names = list(state.get("track", {}))
    args = [os.path.join(HERE, "analyze.py"), cmd, data]
    if cmd in ("rigid", "pops"):
        args += ["--joints", ",".join(n for n in names if n != state.get("root"))]
        if cmd == "rigid" and state.get("root"):
            args += ["--root", state["root"]]
        if state.get("height"):
            args += ["--height", str(state["height"])]
        if state.get("dims"):
            args += ["--dims", str(state["dims"])]
    else:
        args += ["--segment", state.get("segment", "hilt,tip"), "--targets", state["targets"],
                 "--radius", str(state.get("radius", 0.3))]
    res = tool(*args)
    if cmd == "rigid" and len(names) - (1 if state.get("root") else 0) < 3:
        res = {"verdict": "NOT ASSESSED", "note": "a loop needs >= 3 joints besides the root"}
    return res


def frames(state, by_name):
    other = by_name.get(state.get("off") or state.get("steady") or "")
    if not other or not other.get("recorded"):
        return {"verdict": "NOT ASSESSED", "note": "the paired state was not recorded"}
    pat = lambda s: os.path.join(s["dir"], "*.png")  # noqa: E731
    box = ["--box", state["box"]] if state.get("box") else []
    if state.get("check") == "ramp":
        return tool(os.path.join(HERE, "frames.py"), "ramp", "--change", pat(state),
                    "--steady", pat(other), *box)
    return tool(os.path.join(HERE, "frames.py"), "anim", "--on", pat(state), "--off", pat(other),
                *box)


def report(run_dir):
    manifest = json.load(open(os.path.join(run_dir, "qa_run.json"), encoding="utf-8"))
    by_name = {s["name"]: s for s in manifest["states"]}
    rows = []
    for state in manifest["states"]:
        kind = state["kind"]
        if not state.get("recorded"):
            res = {"verdict": "NOT ASSESSED", "note": "not recorded (see the probe notes)"}
        elif kind == "ui":
            res = ui(state)
        elif kind == "anchor":
            res = anchor(state)
        elif kind in ("loop", "transition", "attack"):
            res = analyze({"loop": "rigid", "transition": "pops", "attack": "hits"}[kind], state)
        elif kind == "frames":
            if not (state.get("off") or state.get("steady")):
                continue                          # an OFF / held state, judged with its pair
            res = frames(state, by_name)
        else:
            res = {"verdict": "NOT ASSESSED", "note": f"unknown kind {kind}"}
        rows.append({"name": state["name"], "kind": kind, **res})
    verdicts = {r["verdict"] for r in rows}
    verdict = "FAIL" if "FAIL" in verdicts else ("PASS" if verdicts == {"PASS"} else "NOT ASSESSED")
    out = {"contract": manifest.get("contract"), "scene": manifest.get("scene"),
           "verdict": verdict, "states": rows,
           "failed": [r["name"] for r in rows if r["verdict"] == "FAIL"]}
    with open(os.path.join(run_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    return out


def find_godot(given):
    if given:
        return given
    if os.environ.get("KILN_GODOT"):
        return os.environ["KILN_GODOT"]
    home = os.environ.get("KILN_HOME") or os.path.join(os.path.expanduser("~"), ".kiln")
    try:
        machine = json.load(open(os.path.join(home, "machine.json"), encoding="utf-8"))
        return machine.get("godot_exe") or (machine.get("tools", {}).get("godot", {}) or {}).get("path")
    except (OSError, ValueError):
        return None


def run(a):
    godot = find_godot(a.godot)
    if not godot:
        return {"verdict": "NOT ASSESSED", "note": "no Godot: --godot, KILN_GODOT or machine.json"}, 0
    name = os.path.splitext(os.path.basename(a.contract))[0]
    out = os.path.abspath(a.out or os.path.join(a.project, "production", "qa", name))
    cmd = [godot] + ([] if a.windowed else ["--headless"]) + [
        "--fixed-fps", "60", "--path", a.project, "-s", a.contract, "--", "--out", out]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=a.timeout)
    if not os.path.isfile(os.path.join(out, "qa_run.json")):
        return {"verdict": "NOT ASSESSED", "note": "the contract wrote no qa_run.json",
                "godot_exit": p.returncode, "log": (p.stdout + p.stderr)[-800:]}, 0
    res = report(out)
    res["run"] = out
    return res, 1 if res["verdict"] == "FAIL" else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--contract", required=True, help="res://tests/qa/<scene>_qa.gd")
    r.add_argument("--project", default=".")
    r.add_argument("--godot")
    r.add_argument("--windowed", action="store_true", help="needed for frames states")
    r.add_argument("--out")
    r.add_argument("--timeout", type=int, default=600)
    rp = sub.add_parser("report")
    rp.add_argument("run_dir")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.cmd == "run":
        res, code = run(a)
    else:
        res = report(a.run_dir)
        code = 1 if res["verdict"] == "FAIL" else 0
    print(json.dumps(res, indent=1))
    sys.exit(code)


if __name__ == "__main__":
    main()
