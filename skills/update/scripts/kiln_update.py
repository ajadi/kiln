"""Bring a connected project up to the installed Kiln. Stdlib only; run from the project root.

  python kiln_update.py status      # project vs plugin version, what changed since, next steps
  python kiln_update.py apply       # pipeline.py migrate + framework_version, then status
  python kiln_update.py projects [--scan DIR ...]   # every Kiln project on this machine
  python kiln_update.py apply-all [--yes] [--scan DIR ...]   # migrate every project behind

status  reads `framework_version` from manifest.md and the plugin's version, and lists the
        CHANGELOG entries (plugin CHANGELOG.md) newer than the project's version.
apply   runs `pipeline.py migrate` (touches lines, gates tables, new manifest keys, the version),
        prints the changes; the guessed touches lines still need the producer's confirmation.
projects   the machine's registry (~/.kiln/projects.json; every Kiln session start records its
           project) plus Kiln projects found under --scan folders (manifest.md with
           framework=kiln, up to 4 levels deep); folders that are gone or no longer Kiln are
           forgotten. Each row: path, name, version, behind the plugin or not.
apply-all  without --yes: the projects it would update (exit 3, nothing changed); with --yes:
           `pipeline.py migrate` in each project behind, run in that project's folder.
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


def codex_configs():
    """Codex config.toml files that do not parse: the user's (~/.codex or CODEX_HOME) and this
    project's. Kiln up to 0.8.0 had agents append to them by hand, and a block glued to the next
    table header stops Codex from starting or from reading which projects are trusted (field
    reports 2026-10-19 and 2026-10-20: "Can't verify project trust"). None without Python 3.11."""
    if sys.version_info < (3, 11):
        return None
    sys.path.insert(0, os.path.join(PLUGIN, "scripts"))
    import codex_config
    out = []
    for path in (codex_config.default_file(), os.path.join(".codex", "config.toml")):
        try:
            with open(path, encoding="utf-8-sig") as fh:
                text = fh.read()
        except OSError:
            continue
        error = codex_config.parse_error(text)
        if error:
            out.append({"file": path.replace("\\", "/"), "error": error,
                        "glued_header": bool(any(codex_config.GLUED.match(line)
                                                 for line in text.splitlines()))})
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
               "Codex in runtimes: re-run scripts/codex_agents.py",
               "OpenCode in runtimes: re-run scripts/opencode_setup.py --project ."]
    broken = codex_configs() or []
    for b in broken:
        nxt.insert(0, f"{b['file']} does not parse ({b['error']}): "
                   + ("python scripts/codex_config.py --repair --file " + b["file"]
                      if b["glued_header"] else "show the user the line; never edit it by hand"))
    return {"project_version": proj, "plugin_version": pv, "behind": behind,
            "changes": changes_since(proj) if behind else [], "codex_config_broken": broken,
            "next": nxt}, 0


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


sys.path.insert(0, os.path.join(PLUGIN, "hooks"))
import kiln_hooklib as k  # noqa: E402

SKIP_DIRS = {".git", ".godot", ".import", "node_modules", "Library", "Temp", "Intermediate",
             "Saved", "Binaries", "DerivedDataCache", ".venv", "__pycache__", "export"}


def kiln_checkout(folder):
    """A Kiln source checkout: its project template and test fixtures are not projects."""
    return os.path.isfile(os.path.join(folder, "plugins", "kiln", ".claude-plugin", "plugin.json"))


def template(folder):
    try:
        with open(os.path.join(folder, "manifest.md"), encoding="utf-8") as fh:
            return "{{" in fh.read()
    except OSError:
        return False


def scan(folder, depth=4):
    found = []
    for base, dirs, files in os.walk(folder):
        if kiln_checkout(base):
            dirs[:] = []
            continue
        level = os.path.relpath(base, folder).count(os.sep)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and level < depth]
        if "manifest.md" in files and k.manifest_version(base) and not template(base):
            found.append(os.path.abspath(base))
    return found


def merged(data):
    """Registry rows under one key per folder (k.registry_key); the latest 'seen' wins."""
    out = {}
    for path, row in data.items():
        key = k.registry_key(path)
        if key not in out or str(row.get("seen", "")) > str(out[key].get("seen", "")):
            out[key] = row
    return out


def projects(scan_dirs=()):
    pv = plugin_version()
    reg = k.projects_path()
    os.makedirs(k.kiln_home(), exist_ok=True)
    with k.locked(reg):
        data = merged(k.load_json(reg, {}))
        for folder in scan_dirs:
            for path in scan(folder):
                key = k.registry_key(path)
                data.setdefault(key, {"name": os.path.basename(path), "seen": "found by scan"})
        rows = []
        for path in sorted(data):
            version = k.manifest_version(path)
            if version is None:
                del data[path]  # gone, or no longer a Kiln project
                continue
            data[path]["version"] = version
            rows.append({"path": path, "name": data[path].get("name"), "version": version,
                         "behind": vtuple(version) < vtuple(pv)})
        k.save_json(reg, data)
    return {"plugin_version": pv, "projects": rows,
            "behind": sum(r["behind"] for r in rows)}, 0


def apply_all(yes, scan_dirs=()):
    res, _ = projects(scan_dirs)
    behind = [r for r in res["projects"] if r["behind"]]
    if not yes:
        return {"plugin_version": res["plugin_version"], "would_update": behind,
                "confirm": "show the user this list; on the yes rerun with --yes"}, 3
    pipeline = os.path.join(PLUGIN, "skills", "pipeline", "scripts", "pipeline.py")
    updated, failed = [], []
    for row in behind:
        p = subprocess.run([sys.executable, "-B", pipeline, "migrate"], cwd=row["path"],
                           capture_output=True, text=True, timeout=300)
        entry = {"path": row["path"], "was": row["version"],
                 "now": k.manifest_version(row["path"]),
                 "migrate": p.stdout.strip().splitlines()[-12:]}
        (updated if p.returncode == 0 else failed).append(entry)
    after, _ = projects()
    return {"plugin_version": res["plugin_version"], "updated": updated, "failed": failed,
            "still_behind": after["behind"]}, 1 if failed else 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    args = sys.argv[2:]
    scan_dirs = [args[i + 1] for i, a in enumerate(args) if a == "--scan" and i + 1 < len(args)]
    if cmd == "projects":
        res, code = projects(scan_dirs)
    elif cmd == "apply-all":
        res, code = apply_all("--yes" in args, scan_dirs)
    else:
        res, code = apply() if cmd == "apply" else status()
    print(json.dumps(res, indent=1, ensure_ascii=False))
    sys.exit(code)


if __name__ == "__main__":
    main()
