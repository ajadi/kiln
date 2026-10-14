"""Bring a connected project up to the installed Kiln. Stdlib only; run from the project root.

  python kiln_update.py status      # project vs plugin version, what changed since, next steps
  python kiln_update.py apply       # pipeline.py migrate + framework_version, then status

status  reads `framework_version` from manifest.md and the plugin's version, and lists the
        CHANGELOG entries (plugin CHANGELOG.md) newer than the project's version.
apply   runs `pipeline.py migrate` (touches lines, gates tables, new manifest keys, the version),
        prints the changes; the guessed touches lines still need the producer's confirmation.
Refreshing the plugin itself (the installed copy) is a step of the update skill, not of this
script: the session runs the plugin commands. Output: JSON; exit 1 outside a Kiln project.
"""

import json
import os
import re
import subprocess
import sys

PLUGIN = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                      ".."))


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:3]) or (0,)


def plugin_version():
    with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        return json.load(fh)["version"]


def project_version():
    try:
        with open("manifest.md", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None, False
    if not re.search(r"^framework=kiln\s*$", text, re.M):
        return None, False
    m = re.search(r"^framework_version=(\S+)", text, re.M)
    return (m.group(1) if m else "0.0.0"), True


def changes_since(version):
    try:
        with open(os.path.join(PLUGIN, "CHANGELOG.md"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    out = []
    parts = re.split(r"^## (\d+\.\d+\.\d+)[^\n]*\n", text, flags=re.M)
    for i in range(1, len(parts) - 1, 2):
        ver, body = parts[i], parts[i + 1]
        if vtuple(ver) > vtuple(version):
            bullets = [re.sub(r"\s+", " ", b).strip()[:160]
                       for b in re.findall(r"^- (.+?)(?=^- |\Z)", body, re.M | re.S)]
            out.append({"version": ver, "highlights": bullets[:12]})
    return out


def status():
    pv = plugin_version()
    proj, ok = project_version()
    if not ok:
        return {"problems": ["no manifest.md with framework=kiln here: run from a connected "
                             "project's root"]}, 1
    behind = vtuple(proj) < vtuple(pv)
    nxt = []
    if behind:
        nxt = ["python kiln_update.py apply  (pipeline.py migrate + framework_version)",
               "confirm every guessed touches: line the migration reports",
               "Codex in runtimes: re-run scripts/codex_agents.py"]
    return {"project_version": proj, "plugin_version": pv, "behind": behind,
            "changes": changes_since(proj) if behind else [], "next": nxt}, 0


def apply():
    res, code = status()
    if code:
        return res, code
    pipeline = os.path.join(PLUGIN, "skills", "pipeline", "scripts", "pipeline.py")
    p = subprocess.run([sys.executable, "-B", pipeline, "migrate"], capture_output=True,
                       text=True, timeout=120)
    after, _ = status()
    return {"migrate": p.stdout.strip().splitlines(), "migrate_exit": p.returncode,
            "was": res["project_version"], **after}, p.returncode


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    res, code = apply() if cmd == "apply" else status()
    print(json.dumps(res, indent=1, ensure_ascii=False))
    sys.exit(code)


if __name__ == "__main__":
    main()
