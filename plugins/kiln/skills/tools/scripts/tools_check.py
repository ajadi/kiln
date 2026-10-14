"""Detect and verify the tools a project needs, from its tool manifest. Stdlib only.

  python tools_check.py verify production/tools.json [--tools-root D:/Tools]
  python tools_check.py detect production/tools.json [--tools-root ...]

Manifest (production/tools.json, committed; machine paths stay out of it):
  {"tools": [{"name": "godot", "version": "4.7.2",
              "find": ["Godot_v4.7.2-stable_win64_console.exe", "godot"],
              "verify": ["{path}", "--version"], "expect": "4.7.2",
              "source": "https://github.com/godotengine/godot-builds/releases/tag/4.7.2-stable",
              "install": "unzip into <tools_root>/Godot/4.7.2/", "licence": "MIT"}, ...]}

detect  where each tool is: PATH, then --tools-root (machine.json tools_root) searched for the
        `find` names, then the machine registry entry (`${CLAUDE_PLUGIN_DATA}/machine.json`
        "tools": {name: path}) - the first hit wins; reports every candidate found.
verify  detect, then run `verify` with {path} filled in and require `expect` in its output (the
        exact version, or for an MCP server the tool names a probe call printed). Missing or wrong
        version -> status missing / wrong_version with `install_from` (source + install note).
Output: JSON {tools: [{name, status ok|missing|wrong_version|verify_failed, path, output,
install_from}]}; exit 1 if any tool is not ok.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys


def machine_registry():
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data:
        return {}
    try:
        with open(os.path.join(data, "machine.json"), encoding="utf-8") as fh:
            return json.load(fh).get("tools", {})
    except (OSError, ValueError):
        return {}


def candidates(tool, root, registry):
    found = []
    for name in tool.get("find", []):
        hit = shutil.which(name)
        if hit:
            found.append(hit)
    if root and os.path.isdir(root):
        names = {n.lower() for n in tool.get("find", [])}
        for base, _dirs, files in os.walk(root):
            for f in files:
                if f.lower() in names:
                    found.append(os.path.join(base, f))
    if registry.get(tool["name"]):
        found.append(registry[tool["name"]])
    seen, out = set(), []
    for p in found:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen and os.path.exists(p):
            seen.add(key)
            out.append(p)
    return out


def verify_one(tool, path):
    cmd = [part.replace("{path}", path) for part in tool.get("verify", ["{path}", "--version"])]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, str(exc)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("detect", "verify"))
    ap.add_argument("manifest")
    ap.add_argument("--tools-root", default=None)
    a = ap.parse_args()
    with open(a.manifest, encoding="utf-8") as fh:
        tools = json.load(fh)["tools"]
    registry = machine_registry()
    rows, bad = [], 0
    for tool in tools:
        found = candidates(tool, a.tools_root, registry)
        row = {"name": tool["name"], "version": tool.get("version"), "candidates": found,
               "path": found[0] if found else None}
        install = f"{tool.get('source', '?')} ({tool.get('install', 'see the tools skill')})"
        if not found:
            row.update(status="missing", install_from=install)
        elif a.cmd == "verify":
            code, out = verify_one(tool, found[0])
            row["output"] = out[-300:]
            want = tool.get("expect")
            if code != 0 and not out:
                row.update(status="verify_failed", install_from=install)
            elif want and want not in out:
                row.update(status="wrong_version", install_from=install)
            else:
                row["status"] = "ok"
        else:
            row["status"] = "found"
        bad += row["status"] not in ("ok", "found")
        rows.append(row)
    print(json.dumps({"tools": rows, "verdict": "fail" if bad else "pass"}, indent=1))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
