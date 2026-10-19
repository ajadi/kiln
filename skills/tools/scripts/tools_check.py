"""Find, plan, install and verify the tools a Kiln project needs. Python stdlib only.

  python tools_check.py root [--set D:/Tools]          # the machine's tools folder
  python tools_check.py plan [--project .]             # what this project needs: found / install / manual / offer
  python tools_check.py install <tool> [--version V] [--yes]
  python tools_check.py offers [--project .]           # AI generators compared for this machine
  python tools_check.py offer-install <offer> [--yes]
  python tools_check.py detect production/tools.json [--tools-root D:/Tools]
  python tools_check.py verify production/tools.json [--tools-root D:/Tools]

Machine config: `~/.kiln/machine.json` (KILN_HOME overrides the folder), shared by the kiln and
kiln-start plugins and Codex; a machine.json left in the old plugin-data folder is merged in once.
It holds `tools_root` (asked once when Kiln is first installed; `~/kiln-tools` is suggested) and
`tools: {name: {path, version, source, checksum}}`.

The catalog (`../catalog.json`) names every tool with its official source. `plan` reads the
project's manifest (engine, dimension, llm_npc, model_generators) and, for each tool the project
needs, looks everywhere first: the machine registry, PATH, the tools root and the usual install
folders. Then: found (with its version) / install (Kiln installs it after the user's yes) /
manual (Unity, Unreal: accounts and licences, with a short instruction) / project (an MCP package
or plugin written into the project by setup). `confirm` is the one question to ask the user.
`install` without --yes only prints what it would do (exit 3); with --yes it downloads from the
source, checks the published sha256 (GitHub asset digest, Blender's .sha256 file; 'unpublished'
when the source has none), unpacks into <tools_root>/<tool>/<version>/, finds the executable,
records it and prints the MCP registration commands when the tool is an MCP server. uv tools
install into <tools_root>/uv-tools with their launchers in <tools_root>/bin.
`offers` compares the AI generators the catalog offers (what each makes, GPU memory, licence,
size, quality) against this machine's GPU (nvidia-smi, KILN_GPU_GB overrides) and the project's
`model_generators` (local: fits this GPU; remote: runs through the gpu-server skill).
Output: JSON. Exit 0 ok, 1 failed, 2 manual step, 3 needs confirmation.
"""

import argparse
import datetime
import fnmatch
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(HERE, "..", "catalog.json")
PLATFORM = "windows" if os.name == "nt" else ("macos" if sys.platform == "darwin" else "linux")


# ---------------------------------------------------------------- machine config

def kiln_home():
    return os.environ.get("KILN_HOME") or os.path.join(os.path.expanduser("~"), ".kiln")


def machine_path():
    return os.path.join(kiln_home(), "machine.json")


def load_machine():
    data = {}
    try:
        with open(machine_path(), encoding="utf-8-sig") as fh:  # a BOM from PowerShell is fine
            data = json.load(fh)
    except OSError:
        pass
    except ValueError:  # keep a broken file: the next save would leave only one key
        try:
            os.replace(machine_path(), machine_path() + time.strftime(".broken-%Y%m%d-%H%M%S"))
        except OSError:
            pass
    old_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
    if old_dir and not data.get("_migrated"):
        try:
            with open(os.path.join(old_dir, "machine.json"), encoding="utf-8") as fh:
                old = json.load(fh)
            for key, value in old.items():
                data.setdefault(key, value)
            data["_migrated"] = True
            save_machine(data)
        except (OSError, ValueError):
            pass
    return data


def save_machine(data):
    os.makedirs(kiln_home(), exist_ok=True)
    tmp = machine_path() + f".{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, machine_path())


def tools_root(machine):
    root = machine.get("tools_root")
    return os.path.expanduser(root) if root else None


# ---------------------------------------------------------------- catalog, project needs

def load_catalog(path):
    with open(path or CATALOG, encoding="utf-8") as fh:
        return json.load(fh)


def manifest(project):
    out = {}
    try:
        with open(os.path.join(project, "manifest.md"), encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"\s*([A-Za-z_][\w-]*)\s*=\s*(.*?)\s*$", line)
                if m:
                    out[m.group(1)] = m.group(2)
    except OSError:
        pass
    return out


def needed(cond, policy):
    if cond in (None, "always"):
        return True
    if cond == "on-request":                 # installed only when a task asks for it
        return False
    key, _, value = cond.partition("=")
    have = policy.get(key, {"engine": "godot"}.get(key, "off"))
    return have == value


def fill(text, **values):
    if text is None:
        return None
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    return text


# ---------------------------------------------------------------- finding

def expand(pattern):
    return glob.glob(os.path.expanduser(pattern))


def run_verify(tool, path, version, series):
    cmd = tool.get("verify")
    if not cmd:
        return None, ""
    argv = [fill(part, path=path) for part in cmd]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        out = (p.stdout + p.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    want = fill(tool.get("expect", ""), version=version or "", series=series or "")
    return (want in out) if want else (p.returncode == 0), out[:200]


def find_tool(name, tool, machine):
    """Every place the tool may already be: registry, PATH, the tools root, usual folders."""
    hits = []
    reg = (machine.get("tools") or {}).get(name) or {}
    if reg.get("path") and os.path.exists(reg["path"]):
        hits.append(reg["path"])
    legacy = machine.get(f"{name.replace('-', '_')}_exe")
    if legacy and os.path.exists(legacy):
        hits.append(legacy)
    for exe in tool.get("find", []):
        if not any(c in exe for c in "*?["):
            hit = shutil.which(exe)
            if hit:
                hits.append(hit)
    root = tools_root(machine)
    if root and os.path.isdir(root):
        for base, _dirs, files in os.walk(root):
            for f in files:
                if any(fnmatch.fnmatch(f, pat) for pat in tool.get("find", [])):
                    hits.append(os.path.join(base, f))
    for pat in tool.get("known", []):
        hits += expand(pat)
    seen, out = set(), []
    for h in hits:
        key = os.path.normcase(os.path.abspath(h))
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out


# ---------------------------------------------------------------- sources

def fetch(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "kiln-tools"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def github_release(repo, tag=None):
    base = os.environ.get("KILN_GITHUB_API", "https://api.github.com")
    if base.startswith("file:"):
        url = f"{base}/repos/{repo}/releases/" + (f"tags-{tag}.json" if tag else "latest.json")
    else:
        url = f"{base}/repos/{repo}/releases/" + (f"tags/{tag}" if tag else "latest")
    return json.loads(fetch(url))


def resolve(name, tool, version=None):
    """(version, download url, expected sha256 or None, asset name) for this platform."""
    src = tool["source"]
    asset_t = (tool.get("assets") or {}).get(PLATFORM)
    if asset_t is None and src["kind"] in ("github", "blender"):
        raise LookupError(fill(tool.get(f"{PLATFORM}_instruction")
                               or f"no {PLATFORM} build of {name} in the catalog", version="?"))
    if src["kind"] == "github":
        version = version or src.get("default_version")
        rel = github_release(src["repo"], fill(src["tag"], version=version) if version else None)
        tag = rel["tag_name"]
        version = version or re.sub(r"^v|-stable$", "", tag)
        asset = fill(asset_t, version=version)
        for a in rel.get("assets", []):
            if a["name"] == asset:
                digest = (a.get("digest") or "").removeprefix("sha256:") or None
                return version, a["browser_download_url"], digest, asset
        raise LookupError(f"release {tag} of {src['repo']} has no asset {asset}")
    if src["kind"] == "blender":
        series = src["series"]
        index_url = fill(src["index"], series=series)
        page = fetch(index_url)
        pattern = re.escape(fill(asset_t, version="VERSION")).replace("VERSION", r"(\d+\.\d+\.\d+)")
        found = sorted({m for m in re.findall(pattern, page) if m.startswith(series + ".")},
                       key=lambda v: tuple(int(x) for x in v.split(".")))
        if not found:
            raise LookupError(f"no {asset_t} for Blender {series} at {index_url}")
        version = version or found[-1]
        folder = index_url.rsplit("/", 1)[0] + "/"
        asset = fill(asset_t, version=version)
        sums = fetch(folder + fill(src["checksums"], version=version))
        digest = next((line.split()[0] for line in sums.splitlines() if line.strip().endswith(asset)),
                      None)
        return version, folder + asset, digest, asset
    raise LookupError(f"{name}: source kind {src['kind']} is not downloadable")


# ---------------------------------------------------------------- install

def unpack(archive, dest):
    os.makedirs(dest, exist_ok=True)
    low = archive.lower()
    if low.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    elif low.endswith((".tar.gz", ".tgz", ".tar.xz")):
        with tarfile.open(archive) as t:
            t.extractall(dest, filter="data")
    else:
        raise LookupError(f"cannot unpack {os.path.basename(archive)}: install it by hand")


def mcp_commands(tool, path):
    mcp = tool.get("mcp")
    if not mcp:
        return None
    return {k: [fill(part, path=path) for part in v] for k, v in mcp.items() if k != "name"}


def cmd_install(a, catalog, machine):
    tool = catalog["tools"].get(a.tool)
    if not tool:
        return {"problems": [f"no tool {a.tool} in the catalog"]}, 1
    if tool["action"] == "manual":
        return {"tool": a.tool, "action": "manual", "instruction": tool["instruction"]}, 2
    if tool["source"]["kind"] == "project":
        return {"tool": a.tool, "action": "project",
                "instruction": fill(tool["project_edit"], version=tool["source"]["default_version"]),
                "register": mcp_commands(tool, ""), "after": tool.get("after")}, 2
    root = tools_root(machine)
    if not root:
        return {"problems": ["no tools_root yet: ask the user once and run `tools_check.py root "
                             "--set <folder>` (suggest ~/kiln-tools)"]}, 1
    if tool["source"]["kind"] == "venv":           # a Python library for Kiln's own scripts
        packages = tool["source"]["packages"]
        dest = os.path.join(root, "venvs", a.tool)
        plan = {"tool": a.tool, "packages": packages, "into": dest,
                "size_mb": tool.get("size_mb"), "licence": tool.get("licence")}
        if not a.yes:
            return {"would_install": plan, "confirm": "ask the user, then rerun with --yes"}, 3
        uv = (machine.get("tools") or {}).get("uv", {}).get("path") or shutil.which("uv")
        if not uv:
            return {"problems": ["uv is needed first: tools_check.py install uv --yes"]}, 1
        py = os.path.join(dest, "Scripts" if os.name == "nt" else "bin",
                          "python.exe" if os.name == "nt" else "python")
        for argv in ([uv, "venv", "--python", tool["source"].get("python", "3.12"), dest],
                     [uv, "pip", "install", "--python", py, *packages]):
            p = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
            if p.returncode:
                return {"problems": [f"{' '.join(argv[:3])} failed: {(p.stdout + p.stderr)[-600:]}"]}, 1
        record(machine, a.tool, py, " ".join(packages), "pip via uv", "via uv")
        return {"tool": a.tool, "python": norm(py), "packages": packages,
                "after": tool.get("after")}, 0
    if tool["source"]["kind"] == "uv-tool":
        version = a.version or tool["source"].get("default_version")
        spec = fill(tool["source"]["spec"], version=version)
        plan = {"tool": a.tool, "version": version, "via": f"uv tool install {spec}",
                "into": os.path.join(root, "uv-tools"), "size_mb": tool.get("size_mb")}
        if not a.yes:
            return {"would_install": plan, "confirm": "ask the user, then rerun with --yes"}, 3
        uv = (machine.get("tools") or {}).get("uv", {}).get("path") or shutil.which("uv")
        if not uv:
            return {"problems": ["uv is needed first: tools_check.py install uv --yes"]}, 1
        env = dict(os.environ, UV_TOOL_DIR=os.path.join(root, "uv-tools"),
                   UV_TOOL_BIN_DIR=os.path.join(root, "bin"))
        p = subprocess.run([uv, "tool", "install", "--force", spec], env=env, capture_output=True,
                           text=True, timeout=1800)
        if p.returncode:
            return {"problems": [f"uv tool install failed: {(p.stdout + p.stderr)[-600:]}"]}, 1
        exe = next((os.path.join(root, "bin", n) for n in tool.get("find", [])
                    if os.path.exists(os.path.join(root, "bin", n))), None)
        record(machine, a.tool, exe, version, spec, "uv resolves the package (PyPI / git)")
        res = {"tool": a.tool, "version": version, "path": norm(exe), "checksum": "via uv",
               "register": mcp_commands(tool, norm(exe)),
               "after": fill(tool.get("after"), version=version)}
        if tool.get("addon"):
            url = fill(tool["addon"], version=version)
            addon = os.path.join(root, a.tool, version, url.rsplit("/", 1)[-1])
            os.makedirs(os.path.dirname(addon), exist_ok=True)
            try:
                with open(addon, "wb") as fh:
                    fh.write(fetch(url, binary=True))
                res["addon"] = norm(addon)
            except OSError as exc:
                res["problems"] = [f"add-on download failed: {exc}"]
                return res, 1
        return res, 0
    try:
        version, url, digest, asset = resolve(a.tool, tool, a.version)
    except (LookupError, OSError, ValueError, KeyError) as exc:
        return {"tool": a.tool, "problems": [str(exc)]}, 1
    dest = os.path.join(root, a.tool, version)
    plan = {"tool": a.tool, "version": version, "from": url, "into": dest,
            "size_mb": tool.get("size_mb"), "licence": tool.get("licence"),
            "checksum": f"sha256 {digest}" if digest else "unpublished by the source"}
    if not a.yes:
        return {"would_install": plan, "confirm": "ask the user, then rerun with --yes"}, 3
    tmpdir = tempfile.mkdtemp(prefix="kiln-dl-", dir=root)
    try:
        archive = os.path.join(tmpdir, asset)
        data = fetch(url, binary=True)
        got = hashlib.sha256(data).hexdigest()
        if digest and got != digest.lower():
            return {"tool": a.tool, "problems": [f"checksum mismatch for {asset}: got {got}, the "
                                                 f"source says {digest}; nothing installed"]}, 1
        with open(archive, "wb") as fh:
            fh.write(data)
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        unpack(archive, dest)
    except (OSError, LookupError, zipfile.BadZipFile, tarfile.TarError) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        return {"tool": a.tool, "problems": [str(exc)]}, 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    exe = next((os.path.join(b, f) for b, _d, fs in os.walk(dest) for f in fs
                if any(fnmatch.fnmatch(f, p) for p in tool.get("find", []))), None)
    path = exe or dest
    ok, out = run_verify(tool, path, version, tool["source"].get("series")) if exe else (None, "")
    record(machine, a.tool, path, version, url, "sha256 verified" if digest else "unpublished")
    return {"tool": a.tool, "version": version, "path": norm(path),
            "checksum": "sha256 verified" if digest else "unpublished by the source",
            "verify": out, "verified": ok, "register": mcp_commands(tool, norm(path)),
            "after": fill(tool.get("after"), version=version)}, 0 if ok is not False else 1


def norm(path):
    return path.replace("\\", "/") if path else path


def record(machine, name, path, version, source, checksum):
    old = machine.setdefault("tools", {}).get(name) or {}
    machine["tools"][name] = {"path": path.replace("\\", "/") if path else None,
                              "version": version, "source": source, "checksum": checksum,
                              "installed_by": "kiln",
                              "installed_on": datetime.date.today().isoformat(),
                              "mcp": old.get("mcp", []), "addons": old.get("addons", [])}
    save_machine(machine)


def size_bytes(path):
    if not path or not os.path.exists(path):
        return 0
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(os.path.getsize(os.path.join(b, f)) for b, _d, fs in os.walk(path) for f in fs)


def sized(row, path):
    row["size_bytes"] = size_bytes(path)
    row["size_mb"] = round(row["size_bytes"] / 2 ** 20, 1)
    return row


def cmd_installed(machine):
    """Everything Kiln put on this machine: tools (with their MCP registrations and add-ons) and
    generators, with version, place, size and how it was checked."""
    root = tools_root(machine)
    rows = []
    for name, t in sorted((machine.get("tools") or {}).items()):
        if t.get("installed_by") != "kiln":
            continue
        folder = os.path.join(root, name, t["version"]) if root and t.get("version") else None
        place = folder if folder and os.path.isdir(folder) else t.get("path")
        rows.append(sized({"tool": name, "version": t.get("version"), "path": t.get("path"),
                     "checksum": t.get("checksum"),
                     "source": t.get("source"), "installed_on": t.get("installed_on"),
                     "mcp": t.get("mcp", []), "addons": t.get("addons", [])}, place))
    for name, g in sorted((machine.get("generators") or {}).items()):
        rows.append(sized({"tool": name, "kind": "generator", "version": g.get("commit"),
                           "path": g.get("path"), "source": g.get("repo"),
                           "installed_on": g.get("installed_on")}, g.get("path")))
    return {"tools_root": root, "installed": rows,
            "total_mb": round(sum(r["size_bytes"] for r in rows) / 2 ** 20, 1)}, 0


def cmd_mark(a, machine):
    """Record what was done after an install: an MCP registration (claude / codex) or an add-on."""
    entry = (machine.get("tools") or {}).get(a.tool) or (machine.get("generators") or {}).get(a.tool)
    if not entry:
        return {"problems": [f"{a.tool} is not installed by Kiln on this machine"]}, 1
    for key, value in (("mcp", a.mcp), ("addons", a.addon)):
        if value and value not in entry.setdefault(key, []):
            entry[key].append(value)
    save_machine(machine)
    return {"tool": a.tool, "mcp": entry.get("mcp", []), "addons": entry.get("addons", [])}, 0


# ---------------------------------------------------------------- plan and offers

def gpu_gb():
    if os.environ.get("KILN_GPU_GB"):
        return float(os.environ["KILN_GPU_GB"])
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,"
                              "nounits"], capture_output=True, text=True, timeout=10).stdout
        return max(float(x) for x in out.split()) / 1024
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def offers_for(catalog, policy):
    """Generators that the policy allows: 3D/image ones by model_generators, music and sound ones
    (kind audio) by audio_generators; `fits` = runs here (local) or on a rented GPU (remote)."""
    modes = {"model": policy.get("model_generators", "off"),
             "audio": policy.get("audio_generators", "off"),
             "video": policy.get("video_generators", "off")}
    if not any(m in ("local", "remote") for m in modes.values()):
        return []
    gpu = gpu_gb()
    out = []
    for key, o in catalog.get("offers", {}).items():
        mode = modes[o.get("kind", "model")]
        if mode not in ("local", "remote"):
            continue
        if mode == "local":
            fits = bool(o.get("cpu")) or (gpu >= o.get("gpu_gb", 0) and not
                                         (o.get("linux_only") and PLATFORM != "linux"))
        else:
            fits = True
        out.append({"offer": key, "kind": o.get("kind", "model"), "title": o["title"],
                    "makes": o["makes"],
                    "gpu_gb": o.get("gpu_gb"), "licence": o["licence"],
                    "commercial": o["commercial"], "size_gb": o.get("size_gb"),
                    "quality": o["quality"], "speed": o.get("speed"), "fits": fits,
                    "route": "this machine" if mode == "local" else "rented GPU (gpu_job.py)"})
    out.sort(key=lambda r: (not r["fits"], r["gpu_gb"] or 0))
    return out


def cmd_plan(a, catalog, machine):
    policy = manifest(a.project)
    rows = []
    for name, tool in catalog["tools"].items():
        if not needed(tool.get("when"), policy):
            continue
        hits = find_tool(name, tool, machine)
        row = {"tool": name, "title": tool["title"], "found": hits}
        if hits:
            row.update(status="found", path=hits[0], action="none")
        elif tool["action"] == "manual":
            row.update(status="missing", action="manual", instruction=tool["instruction"])
        elif tool["source"]["kind"] == "project":
            row.update(status="not in the project", action="project",
                       instruction=fill(tool["project_edit"],
                                        version=tool["source"]["default_version"]))
        else:
            row.update(status="missing", action="install", size_mb=tool.get("size_mb"),
                       licence=tool.get("licence"))
        rows.append(row)
    offers = offers_for(catalog, policy)
    installs = [r for r in rows if r["action"] == "install"]
    manual = [r for r in rows if r["action"] == "manual"]
    confirm = []
    if installs:
        confirm.append("Kiln needs to install: " + ", ".join(
            f"{r['title']} (~{r['size_mb']} MB)" for r in installs) + " into " +
            str(tools_root(machine) or "<tools_root not set>") + ". Install them?")
    if manual:
        confirm.append("Needs you: " + "; ".join(r["title"] for r in manual))
    if offers:
        confirm.append("AI generators that fit: " + ", ".join(o["title"] for o in offers if o["fits"])
                       + " (comparison in offers); install which?")
    return {"tools_root": tools_root(machine), "platform": PLATFORM, "tools": rows,
            "offers": offers, "confirm": " ".join(confirm) or "nothing to do"}, 0


def cmd_offer_install(a, catalog, machine):
    o = catalog.get("offers", {}).get(a.offer)
    if not o:
        return {"problems": [f"no offer {a.offer}"]}, 1
    root = tools_root(machine)
    if not root:
        return {"problems": ["no tools_root yet (tools_check.py root --set)"]}, 1
    dest = os.path.join(root, "generators", a.offer)
    plan = {"offer": a.offer, "repo": o["repo"], "commit": o["commit"], "into": dest,
            "size_gb": o.get("size_gb"), "licence": o["licence"],
            "steps": ["git clone", f"git checkout {o['commit']}", "uv venv .venv",
                      "uv pip install -r requirements.txt (when present)",
                      "weights download on the first run (Hugging Face cache)"]}
    if not a.yes:
        return {"would_install": plan, "confirm": "ask the user, then rerun with --yes"}, 3
    uv = (machine.get("tools") or {}).get("uv", {}).get("path") or shutil.which("uv")
    if not uv:
        return {"problems": ["uv is needed first: tools_check.py install uv --yes"]}, 1
    steps = [["git", "clone", o["repo"], dest], ["git", "-C", dest, "checkout", o["commit"]],
             [uv, "venv", os.path.join(dest, ".venv")]]
    for argv in steps:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
        if p.returncode:
            return {"problems": [f"{' '.join(argv[:3])} failed: {(p.stdout + p.stderr)[-400:]}"]}, 1
    req = os.path.join(dest, "requirements.txt")
    if os.path.isfile(req):
        py = os.path.join(dest, ".venv", "Scripts" if os.name == "nt" else "bin", "python")
        p = subprocess.run([uv, "pip", "install", "--python", py, "-r", req], capture_output=True,
                           text=True, timeout=7200)
        if p.returncode:
            return {"problems": [f"requirements failed: {(p.stdout + p.stderr)[-600:]}"],
                    "into": dest}, 1
    machine.setdefault("generators", {})[a.offer] = {
        "path": dest.replace("\\", "/"), "commit": o["commit"], "repo": o["repo"],
        "installed_on": datetime.date.today().isoformat()}
    save_machine(machine)
    return {"offer": a.offer, "path": dest, "commit": o["commit"]}, 0


# ---------------------------------------------------------------- project manifest (tools.json)

def cmd_manifest(a, machine):
    with open(a.manifest, encoding="utf-8") as fh:
        tools = json.load(fh)["tools"]
    if a.tools_root:
        machine = dict(machine, tools_root=a.tools_root)
    rows, bad = [], 0
    for tool in tools:
        found = find_tool(tool["name"], tool, machine)
        row = {"name": tool["name"], "version": tool.get("version"), "candidates": found,
               "path": found[0] if found else None}
        install = f"{tool.get('source', '?')} ({tool.get('install', 'tools_check.py install')})"
        if not found:
            row.update(status="missing", install_from=install)
        elif a.cmd == "verify":
            ok, out = run_verify(dict(tool, verify=tool.get("verify", ["{path}", "--version"])),
                                 found[0], tool.get("version"), None)
            row["output"] = out
            row["status"] = "ok" if ok else "wrong_version"
            if not ok:
                row["install_from"] = install
        else:
            row["status"] = "found"
        bad += row["status"] not in ("ok", "found")
        rows.append(row)
    return {"tools": rows, "verdict": "fail" if bad else "pass"}, 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("root"); r.add_argument("--set")
    p = sub.add_parser("plan"); p.add_argument("--project", default=".")
    p.add_argument("--catalog")
    i = sub.add_parser("install"); i.add_argument("tool"); i.add_argument("--version")
    i.add_argument("--yes", action="store_true"); i.add_argument("--catalog")
    o = sub.add_parser("offers"); o.add_argument("--project", default=".")
    o.add_argument("--catalog")
    oi = sub.add_parser("offer-install"); oi.add_argument("offer")
    oi.add_argument("--yes", action="store_true"); oi.add_argument("--catalog")
    sub.add_parser("installed")
    mk = sub.add_parser("mark"); mk.add_argument("tool")
    mk.add_argument("--mcp", choices=["claude", "codex"]); mk.add_argument("--addon")
    for name in ("detect", "verify"):
        m = sub.add_parser(name); m.add_argument("manifest"); m.add_argument("--tools-root")
    a = ap.parse_args()
    machine = load_machine()
    if a.cmd == "root":
        if a.set:
            path = os.path.abspath(os.path.expanduser(a.set))
            os.makedirs(path, exist_ok=True)
            machine["tools_root"] = path.replace("\\", "/")
            save_machine(machine)
        res, code = {"tools_root": machine.get("tools_root"),
                     "suggested": os.path.join(os.path.expanduser("~"), "kiln-tools").replace("\\", "/"),
                     "machine_config": machine_path()}, 0
    elif a.cmd == "installed":
        res, code = cmd_installed(machine)
    elif a.cmd == "mark":
        res, code = cmd_mark(a, machine)
    elif a.cmd in ("detect", "verify"):
        res, code = cmd_manifest(a, machine)
    else:
        catalog = load_catalog(getattr(a, "catalog", None))
        if a.cmd == "plan":
            res, code = cmd_plan(a, catalog, machine)
        elif a.cmd == "install":
            res, code = cmd_install(a, catalog, machine)
        elif a.cmd == "offers":
            res, code = {"gpu_gb": gpu_gb(), "offers": offers_for(catalog, manifest(a.project)),
                         "not_offered": catalog.get("not_offered", {})}, 0
        else:
            res, code = cmd_offer_install(a, catalog, machine)
    print(json.dumps(res, indent=1, ensure_ascii=False))
    sys.exit(code)


if __name__ == "__main__":
    main()
