"""Build audit, export and smoke launch for Kiln projects (Godot, Unity, Unreal). stdlib only.

  python build.py audit [--root .] [--engine godot|unity|unreal]
  python build.py build --preset "Windows Desktop" [--out export/windows/Game.exe] [--debug]
                        [--pack] [--engine-exe PATH] [--machine PATH] [--dry-run] [--timeout 3600]
  python build.py build --preset "Assets/Settings/Build Profiles/Windows.asset"
                        [--method KilnRelease.KilnBuild.Build]               (unity)
  python build.py build --preset Win64 [--debug]          (unreal: platform; Shipping, --debug =
                                                           Development)
  python build.py smoke "export/windows/*.exe" --seconds 60 [--log PATH|GLOB] [--ignore REGEX]
                        [--error REGEX] [--sample-every 900 --warmup 60 --max-growth 20]
                        [-- game args]

audit  Engine from manifest.md. Godot: export_presets.cfg exists; every preset keeps the
       non-shipping folders (ref production tools tests design research) out of the pack -
       its exclude_filter covers them or the folder holds a .gdignore - plus an estimate of
       what ships per preset (Godot's own filter rules: '*' spans '/', '?' never matches '.',
       case-insensitive, dot-folders/.gdignore/nested projects skipped). Unity: Editor build
       method (name must contain "Build" for the Kiln guard), build profiles, scenes in build,
       folders that ship unconditionally (Resources, StreamingAssets), test assemblies.
       Unreal: .uproject, packaging settings, never-cook folders, targets.
build  Runs the engine's documented build command (Godot --headless --export-release, Unity
       -batchmode -quit -executeMethod <...Build...>, Unreal RunUAT BuildCookRun), prints it,
       checks the artefact is new and non-empty and reports sizes. --dry-run prints only.
smoke  Launches one built executable (a .py runs under this Python - used by the tests),
       waits N seconds; pass if it is still running or exited 0, and no error line appears in
       stdout/stderr or in the fresh log; kills the process tree. --sample-every turns it
       into a soak run with memory samples and a growth limit.

Engine executable: --engine-exe, else $KILN_ENGINE_EXE, else machine.json (--machine, or
~/.kiln/machine.json, then $CLAUDE_PLUGIN_DATA/machine.json) key godot_exe / unity_exe / unreal_exe or
tools.<engine>.path, else the same key in
manifest.md, else PATH. Output is JSON with "verdict"; exit code 1 when the verdict is "fail".
"""

import argparse
import glob as globlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

NON_SHIPPING = ["ref", "production", "tools", "tests", "design", "research"]
EDITOR_ADDONS = ["addons/godot_ai", "addons/gut", "addons/gdUnit4"]
EXE_KEYS = {"godot": "godot_exe", "unity": "unity_exe", "unreal": "unreal_exe"}
PATH_NAMES = {"godot": ["godot", "godot4"], "unity": ["Unity", "unity"], "unreal": ["RunUAT"]}

# Files Godot's editor filesystem exports in "all resources" mode: importable assets and native
# resources. Text files (md, txt, cfg, ini, yml, toml, xml, log) are skipped; json is a JSON
# resource in Godot 4 and is counted. Conservative: over-reporting a leak is the safe side.
GODOT_RESOURCE_EXTS = {
    "png", "jpg", "jpeg", "webp", "svg", "svgz", "tga", "bmp", "dds", "ktx", "exr", "hdr",
    "glb", "gltf", "blend", "fbx", "obj", "dae", "wav", "ogg", "mp3", "ttf", "otf", "woff",
    "woff2", "pfb", "pfm", "fnt", "font", "csv", "json", "tscn", "scn", "tres", "res", "gd",
    "gdshader", "gdshaderinc", "gdextension", "cs", "material", "mesh", "anim", "theme",
    "translation", "occ", "lmbake", "ogv", "ico", "icns",
}
GODOT_EXT = {"windows": ".exe", "linux": ".x86_64", "macos": ".zip", "web": ".zip",
             "android": ".apk", "ios": ".zip"}

ERROR_PATTERNS = {
    "common": [r"(?i)\bunhandled exception\b", r"(?i)\bsegmentation fault\b",
               r"(?i)\baccess violation\b", r"(?i)\bfatal error\b"],
    "godot": [r"^\s*(USER |USER SCRIPT |SCRIPT )?ERROR:", r"Program crashed with signal",
              r"CrashHandlerException"],
    "unity": [r"\b\w+Exception\b:", r"^Crash!!!"],
    "unreal": [r"\bLog\w+: Error:", r"Assertion failed"],
}


# ---------------------------------------------------------------- helpers

def emit(result):
    print(json.dumps(result, indent=2))
    return 1 if result.get("verdict") == "fail" else 0


def norm(path):
    return path.replace("\\", "/")


def read_text(path, limit=None):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(limit) if limit else fh.read()
    except OSError:
        return ""


def read_manifest(root):
    values = {}
    for line in read_text(os.path.join(root, "manifest.md")).splitlines():
        m = re.match(r"^\s*([A-Za-z_][\w.-]*)\s*=\s*(.*?)\s*$", line)
        if m:
            values[m.group(1)] = m.group(2)
    return values


def detect_engine(root, manifest):
    if manifest.get("engine") in EXE_KEYS:
        return manifest["engine"]
    if os.path.isfile(os.path.join(root, "project.godot")):
        return "godot"
    if os.path.isdir(os.path.join(root, "Assets")) and \
            os.path.isdir(os.path.join(root, "ProjectSettings")):
        return "unity"
    if globlib.glob(os.path.join(root, "*.uproject")):
        return "unreal"
    return None


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "build"


def has_glob(text):
    return re.search(r"[*?[]", text) is not None


def launcher(path):
    """Command prefix for an executable; .py files run under this interpreter (tests)."""
    return [sys.executable, path] if path.lower().endswith(".py") else [path]


def dir_stats(path, top=10):
    files = []
    for dirpath, _, names in os.walk(path):
        for name in names:
            full = os.path.join(dirpath, name)
            try:
                files.append((os.path.getsize(full), norm(os.path.relpath(full, path))))
            except OSError:
                pass
    files.sort(reverse=True)
    return {"files": len(files), "bytes": sum(s for s, _ in files),
            "largest": [{"path": p, "bytes": s} for s, p in files[:top]]}


def tail(text, lines=30):
    return text.splitlines()[-lines:]


def error_lines(text, engine, extra=(), ignore=(), limit=20):
    patterns = [re.compile(p, re.M) for p in
                ERROR_PATTERNS["common"] + ERROR_PATTERNS.get(engine or "", []) + list(extra)]
    skips = [re.compile(p) for p in ignore]
    hits = []
    for line in text.splitlines():
        if any(p.search(line) for p in patterns) and not any(s.search(line) for s in skips):
            hits.append(line.strip()[:300])
            if len(hits) >= limit:
                break
    return hits


# ---------------------------------------------------------------- Godot config files

def _unescaped_quotes(text):
    count, escaped = 0, False
    for ch in text:
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            count += 1
    return count


def _value(raw):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        body = raw[1:-1]
        return re.sub(r'\\(.)', lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)),
                      body)
    if raw in ("true", "false"):
        return raw == "true"
    if raw.startswith("PackedStringArray(") or raw.startswith("Array["):
        return [_value('"' + s + '"') for s in re.findall(r'"((?:[^"\\]|\\.)*)"', raw)]
    try:
        return float(raw) if "." in raw else int(raw)
    except ValueError:
        return raw


def parse_cfg(text):
    """Godot ConfigFile text (project.godot, export_presets.cfg) -> {section: {key: value}}.
    Quoted values may span lines (the SSH deploy scripts in export presets do)."""
    sections, pending = {}, None
    current = sections.setdefault("", {})
    for line in text.splitlines():
        if pending is not None:
            pending[1] += "\n" + line
            if _unescaped_quotes(pending[1]) % 2 == 0:
                current[pending[0]] = _value(pending[1])
                pending = None
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        m = re.match(r"^\[(.+)\]$", stripped)
        if m:
            current = sections.setdefault(m.group(1), {})
            continue
        m = re.match(r"^([^=]+?)\s*=\s*(.*)$", line)
        if not m:
            continue
        key, raw = m.group(1).strip(), m.group(2)
        if _unescaped_quotes(raw) % 2:
            pending = [key, raw]
        else:
            current[key] = _value(raw)
    return sections


def godot_match(pattern, text):
    """Godot String.matchn: '*' any run including '/', '?' one char except '.', no case."""
    if not pattern or not text:
        return False
    rx = "".join(".*" if c == "*" else "[^.]" if c == "?" else re.escape(c) for c in pattern)
    return re.fullmatch(rx, text, re.I | re.S) is not None


def filters(text):
    return [f.strip() for f in str(text or "").split(",") if f.strip()]


def filter_hit(rel, pats):
    return any(godot_match(p, "res://" + rel) or godot_match(p, rel) for p in pats)


def godot_files(root):
    """{rel: size} for files Godot's editor filesystem walks: dot-folders, folders holding
    .gdignore and nested projects are skipped, as in EditorFileSystem::_should_skip_directory."""
    found = {}
    for dirpath, dirnames, names in os.walk(root):
        keep = []
        for d in sorted(dirnames):
            full = os.path.join(dirpath, d)
            if d.startswith(".") or os.path.exists(os.path.join(full, ".gdignore")) or \
                    os.path.exists(os.path.join(full, "project.godot")):
                continue
            keep.append(d)
        dirnames[:] = keep
        for name in names:
            if name.startswith("."):
                continue
            full = os.path.join(dirpath, name)
            try:
                found[norm(os.path.relpath(full, root))] = os.path.getsize(full)
            except OSError:
                pass
    return found


def godot_presets(root):
    cfg = parse_cfg(read_text(os.path.join(root, "export_presets.cfg")))
    presets = []
    for section, values in cfg.items():
        m = re.fullmatch(r"preset\.(\d+)", section)
        if m:
            presets.append(dict(values, _index=int(m.group(1)),
                                _options=cfg.get(section + ".options", {})))
    return sorted(presets, key=lambda p: p["_index"])


def godot_ships(preset, files):
    """Estimate of the files a preset exports (export_project_files in Godot's source)."""
    mode = preset.get("export_filter", "all_resources")
    listed = {norm(str(f)).replace("res://", "", 1) for f in preset.get("export_files", [])}
    note = None
    if mode in ("scenes", "resources"):
        ships = {f for f in listed if f in files}
        note = "selected-resources mode: dependencies of the listed files are not resolved"
    else:
        ships = {f for f in files if f.rsplit(".", 1)[-1].lower() in GODOT_RESOURCE_EXTS}
        if mode == "exclude":
            ships -= listed
        if mode == "customized":
            note = "customized mode: per-folder overrides are not evaluated"
    include, exclude = filters(preset.get("include_filter")), filters(preset.get("exclude_filter"))
    ships |= {f for f in files if f.lower().endswith((".ico", ".icns")) or filter_hit(f, include)}
    ships = {f for f in ships if not filter_hit(f, exclude) and not f.endswith((".import", ".uid"))}
    return ships, note


def godot_templates(version):
    if os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA", ""), "Godot", "export_templates")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Godot/export_templates")
    else:
        data = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        base = os.path.join(data, "godot", "export_templates")
    found = sorted(os.path.basename(p) for p in globlib.glob(os.path.join(base, f"{version}*")))
    return norm(base), found


def audit_godot(root):
    issues, warnings = [], []
    project = parse_cfg(read_text(os.path.join(root, "project.godot")))
    app = project.get("application", {})
    features = app.get("config/features") or []
    version = next((f for f in features if re.fullmatch(r"\d+\.\d+", str(f))), None)
    result = {"engine": "godot", "project_version": app.get("config/version"),
              "godot_version": version, "presets": []}
    if not project:
        issues.append("project.godot missing - not a Godot project root")
    if not app.get("config/version"):
        warnings.append("application/config/version is empty - set the game version in "
                        "Project Settings through the MCP (project_manage)")
    if version:
        base, found = godot_templates(version)
        result["export_templates"] = {"dir": base, "installed": found}
        if not found:
            warnings.append(f"no export templates for Godot {version} in {base} on this machine "
                            "(Editor > Manage Export Templates)")

    files = godot_files(root)
    folders = {}
    for name in NON_SHIPPING:
        path = os.path.join(root, name)
        info = {"exists": os.path.isdir(path),
                "gdignore": os.path.isfile(os.path.join(path, ".gdignore"))}
        folders[name] = info
        if name == "tests" and info["gdignore"]:
            warnings.append("tests/ holds a .gdignore: Godot cannot load() the test suites; "
                            "exclude it with the preset's exclude_filter (tests/*) instead")
    result["non_shipping"] = folders
    export_dir = os.path.join(root, "export")
    if os.path.isdir(export_dir) and not os.path.isfile(os.path.join(export_dir, ".gdignore")):
        warnings.append("export/ has no .gdignore: Godot imports previous builds' images and the "
                        "next export ships them")

    if not os.path.isfile(os.path.join(root, "export_presets.cfg")):
        issues.append("export_presets.cfg missing - create a preset (Project > Export) first")
    presets = godot_presets(root)
    if os.path.isfile(os.path.join(root, "export_presets.cfg")) and not presets:
        issues.append("export_presets.cfg has no [preset.N] sections")
    for preset in presets:
        name = preset.get("name", f"preset.{preset['_index']}")
        exclude = filters(preset.get("exclude_filter"))
        ships, note = godot_ships(preset, files)
        coverage, leaks = {}, {}
        for folder, info in folders.items():
            probes = [f"{folder}/__kiln_probe__.kilnprobe",
                      f"{folder}/__kiln_probe__/__kiln_probe__.kilnprobe"]
            excluded = all(filter_hit(p, exclude) for p in probes)
            leaked = sorted(f for f in ships if f.split("/", 1)[0].lower() == folder)
            if not info["exists"]:
                state = "absent"
            elif info["gdignore"]:
                state = "gdignore"
            elif excluded:
                state = "excluded"
            else:
                state = "NOT COVERED"
                issues.append(f"preset '{name}': {folder}/ is neither in exclude_filter "
                              f"({folder}/*) nor marked with {folder}/.gdignore")
            coverage[folder] = state
            if leaked:
                leaks[folder] = {"files": len(leaked), "examples": leaked[:8]}
                issues.append(f"preset '{name}' would ship {len(leaked)} file(s) from {folder}/")
        for addon in EDITOR_ADDONS:
            shipped = [f for f in ships if f.lower().startswith(addon.lower() + "/")]
            if shipped:
                warnings.append(f"preset '{name}' ships editor-only {addon}/ ({len(shipped)} "
                                f"files) - add {addon}/* to exclude_filter")
        by_top = {}
        for f in ships:
            top = f.split("/", 1)[0] if "/" in f else "(root)"
            count, size = by_top.get(top, (0, 0))
            by_top[top] = (count + 1, size + files.get(f, 0))
        if not preset.get("export_path"):
            warnings.append(f"preset '{name}' has no export_path - pass --out to build")
        options = preset["_options"]
        result["presets"].append({
            "name": name, "platform": preset.get("platform"),
            "export_path": preset.get("export_path"),
            "export_filter": preset.get("export_filter"),
            "include_filter": preset.get("include_filter", ""),
            "exclude_filter": preset.get("exclude_filter", ""),
            "non_shipping": coverage, "leaks": leaks,
            "ships": {"files": len(ships), "source_bytes": sum(files.get(f, 0) for f in ships),
                      "by_folder": {k: {"files": c, "bytes": b} for k, (c, b) in
                                    sorted(by_top.items(), key=lambda kv: -kv[1][1])[:12]}},
            "options": {k: options[k] for k in ("binary_format/embed_pck",
                                                "debug/export_console_wrapper",
                                                "shader_baker/enabled", "codesign/enable",
                                                "application/product_version")
                        if k in options},
            "note": note,
        })
    return result, issues, warnings


# ---------------------------------------------------------------- Unity

def unity_build_methods(root):
    methods = []
    for path in globlib.glob(os.path.join(root, "Assets", "**", "*.cs"), recursive=True):
        code = read_text(path)
        if "BuildPipeline.BuildPlayer" not in code:
            continue
        rel = norm(os.path.relpath(path, root))
        ns = re.search(r"^\s*namespace\s+([\w.]+)", code, re.M)
        in_editor = "/Editor/" in "/" + rel
        for cls in re.finditer(r"\bclass\s+(\w+)", code):
            body = code[cls.end():]
            nxt = re.search(r"\bclass\s+\w+", body)
            body = body[:nxt.start()] if nxt else body
            for m in re.finditer(r"\bpublic\s+static\s+void\s+(\w+)\s*\(\s*\)", body):
                full = ".".join(x for x in (ns.group(1) if ns else "", cls.group(1),
                                            m.group(1)) if x)
                methods.append({"method": full, "file": rel, "editor_folder": in_editor,
                                "guard_allowed": "build" in full.lower()})
    return methods


def audit_unity(root):
    issues, warnings = [], []
    result = {"engine": "unity"}
    if not (os.path.isdir(os.path.join(root, "Assets")) and
            os.path.isdir(os.path.join(root, "ProjectSettings"))):
        issues.append("Assets/ and ProjectSettings/ missing - not a Unity project root")
        return result, issues, warnings
    ver = re.search(r"m_EditorVersion:\s*(\S+)",
                    read_text(os.path.join(root, "ProjectSettings", "ProjectVersion.txt")))
    settings = read_text(os.path.join(root, "ProjectSettings", "ProjectSettings.asset"))
    bundle = re.search(r"^\s*bundleVersion:\s*(.+)$", settings, re.M)
    product = re.search(r"^\s*productName:\s*(.+)$", settings, re.M)
    result.update(unity_version=ver.group(1) if ver else None,
                  project_version=bundle.group(1).strip() if bundle else None,
                  product_name=product.group(1).strip() if product else None)

    methods = unity_build_methods(root)
    result["build_methods"] = methods
    if not any(m["guard_allowed"] for m in methods):
        issues.append("no Editor build method calling BuildPipeline.BuildPlayer with 'Build' in "
                      "its name (the Kiln guard allows -executeMethod only for build methods); "
                      "add KilnBuild.cs (release skill, references/engine-builds.md) under an "
                      "Editor folder")
    for m in methods:
        if not m["editor_folder"]:
            warnings.append(f"{m['file']} uses BuildPipeline outside an Editor folder - player "
                            "builds fail to compile unless it is wrapped in #if UNITY_EDITOR")
    profiles = []
    for path in globlib.glob(os.path.join(root, "Assets", "**", "*.asset"), recursive=True):
        rel = norm(os.path.relpath(path, root))
        if "/Build Profiles/" in rel or "BuildProfile" in read_text(path, 4096):
            profiles.append(rel)
    result["build_profiles"] = sorted(profiles)
    scenes = re.findall(r"enabled:\s*1\s*\n\s*path:\s*(\S+)",
                        read_text(os.path.join(root, "ProjectSettings",
                                               "EditorBuildSettings.asset")))
    result["scenes_in_build"] = scenes
    if not scenes and not profiles:
        issues.append("no enabled scenes in Build Settings and no build profile")

    always = {}
    for kind in ("Resources", "StreamingAssets"):
        for path in globlib.glob(os.path.join(root, "Assets", "**", kind), recursive=True):
            if os.path.isdir(path):
                rel = norm(os.path.relpath(path, root))
                stats = dir_stats(path, top=0)
                always[rel] = {"files": stats["files"], "bytes": stats["bytes"]}
                for dirpath, dirnames, _ in os.walk(path):
                    for d in dirnames:
                        if d.lower() in NON_SHIPPING:
                            issues.append(f"{norm(os.path.relpath(os.path.join(dirpath, d), root))}"
                                          f" sits inside {kind}/ and ships unconditionally")
    result["ships_unconditionally"] = always
    for name in NON_SHIPPING:
        for entry in os.listdir(os.path.join(root, "Assets")):
            if entry.lower() == name:
                warnings.append(f"Assets/{entry}/ is imported by Unity; keep {name}/ at the "
                                "project root, outside Assets/")
    for path in globlib.glob(os.path.join(root, "Assets", "**", "*.asmdef"), recursive=True):
        text = read_text(path)
        if "test" in os.path.basename(path).lower() and "UNITY_INCLUDE_TESTS" not in text and \
                not re.search(r'"includePlatforms"\s*:\s*\[\s*"Editor"', text):
            warnings.append(f"{norm(os.path.relpath(path, root))}: test assembly without the "
                            "UNITY_INCLUDE_TESTS constraint ends up in player builds")
    return result, issues, warnings


# ---------------------------------------------------------------- Unreal

def ini_values(text, section):
    values, current = {}, None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            current = s[1:-1]
            continue
        if current == section and "=" in s and not s.startswith(";"):
            key, val = s.split("=", 1)
            values.setdefault(key.strip(), []).append(val.strip())
    return values


def audit_unreal(root):
    issues, warnings = [], []
    result = {"engine": "unreal"}
    uprojects = globlib.glob(os.path.join(root, "*.uproject"))
    if not uprojects:
        issues.append("no *.uproject in the project root")
        return result, issues, warnings
    try:
        with open(uprojects[0], encoding="utf-8-sig") as fh:
            association = json.load(fh).get("EngineAssociation")
    except (OSError, ValueError):
        association = None
    game_ini = read_text(os.path.join(root, "Config", "DefaultGame.ini"))
    pack = ini_values(game_ini, "/Script/UnrealEd.ProjectPackagingSettings")
    general = ini_values(game_ini, "/Script/EngineSettings.GeneralProjectSettings")
    result.update(uproject=norm(os.path.relpath(uprojects[0], root)),
                  engine_association=association,
                  project_version=(general.get("ProjectVersion") or [None])[0],
                  packaging={k: v if len(v) > 1 else v[0] for k, v in pack.items()})
    if not pack:
        warnings.append("no [/Script/UnrealEd.ProjectPackagingSettings] in DefaultGame.ini - "
                        "engine defaults apply (set Project Settings > Packaging through the MCP)")
    if not pack.get("+MapsToCook"):
        warnings.append("no Maps To Cook listed: every map in Content is cooked, test maps "
                        "included")
    never = " ".join(pack.get("+DirectoriesToNeverCook", []))
    for sub in ("Developers",):
        if os.path.isdir(os.path.join(root, "Content", sub)) and f"/Game/{sub}" not in never:
            warnings.append(f"Content/{sub}/ is not in Directories To Never Cook")
    for name in NON_SHIPPING:
        if os.path.isdir(os.path.join(root, "Content", name)):
            warnings.append(f"Content/{name}/ is inside Content and cooks when referenced; "
                            "keep it at the project root")
    targets = []
    for path in globlib.glob(os.path.join(root, "Source", "*.Target.cs")):
        text = read_text(path)
        kind = re.search(r"Type\s*=\s*TargetType\.(\w+)", text)
        targets.append({"file": norm(os.path.relpath(path, root)),
                        "type": kind.group(1) if kind else None,
                        "logging_in_shipping": bool(re.search(r"bUseLoggingInShipping\s*=\s*true",
                                                              text))})
    result["targets"] = targets
    if os.path.isdir(os.path.join(root, "Source")) and \
            not any(t["type"] == "Game" for t in targets):
        warnings.append("Source/ exists but no Game target (*.Target.cs with TargetType.Game)")
    return result, issues, warnings


AUDITS = {"godot": audit_godot, "unity": audit_unity, "unreal": audit_unreal}


def cmd_audit(args):
    root = os.path.abspath(args.root)
    engine = args.engine or detect_engine(root, read_manifest(root))
    if engine not in AUDITS:
        return emit({"verdict": "fail", "issues": ["engine unknown: set engine= in manifest.md "
                                                   "or pass --engine"]})
    result, issues, warnings = AUDITS[engine](root)
    result = {"verdict": "fail" if issues else "pass", "root": norm(root), **result,
              "issues": issues, "warnings": warnings}
    return emit(result)


# ---------------------------------------------------------------- build

def engine_exe(engine, root, manifest, args):
    if args.engine_exe:
        return args.engine_exe, "--engine-exe"
    if os.environ.get("KILN_ENGINE_EXE"):
        return os.environ["KILN_ENGINE_EXE"], "$KILN_ENGINE_EXE"
    key = EXE_KEYS[engine]
    machine = args.machine
    if not machine:  # the shared machine config, then the old per-plugin copy
        home = os.environ.get("KILN_HOME") or os.path.join(os.path.expanduser("~"), ".kiln")
        candidates = [os.path.join(home, "machine.json")]
        if os.environ.get("CLAUDE_PLUGIN_DATA"):
            candidates.append(os.path.join(os.environ["CLAUDE_PLUGIN_DATA"], "machine.json"))
        machine = next((c for c in candidates if os.path.isfile(c)), None)
    if machine and os.path.isfile(machine):
        try:
            with open(machine, encoding="utf-8") as fh:
                data = json.load(fh)
            value = data.get(key) or ((data.get("tools") or {}).get(engine) or {}).get("path")
            if value:
                return value, f"{norm(machine)}:{key}"
        except (OSError, ValueError):
            pass
    if manifest.get(key):
        return manifest[key], f"manifest.md:{key}"
    for name in PATH_NAMES[engine]:
        found = shutil.which(name)
        if found:
            return found, "PATH"
    return None, None


def runuat_from(exe):
    if os.path.basename(exe).lower().startswith("runuat"):
        return exe
    engine_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(exe))))
    return os.path.join(engine_dir, "Build", "BatchFiles",
                        "RunUAT.bat" if os.name == "nt" else "RunUAT.sh")


def godot_out(root, preset, args):
    if args.out:
        return args.out
    if args.pack:
        return os.path.join("export", slug(preset.get("name", "pack")), "game.pck")
    if preset.get("export_path"):
        return preset["export_path"]
    project = parse_cfg(read_text(os.path.join(root, "project.godot")))
    name = slug(str(project.get("application", {}).get("config/name") or "game"))
    platform = str(preset.get("platform", "")).lower()
    ext = next((e for key, e in GODOT_EXT.items() if key in platform), "")
    return os.path.join("export", slug(preset.get("name", "build")), name + ext)


def unity_ext(preset):
    low = preset.lower()
    for keys, ext in ((("android",), ".apk"), (("webgl", "web"), ""), (("mac", "osx"), ".app"),
                      (("linux",), ".x86_64"), (("win",), ".exe")):
        if any(k in low for k in keys):
            return ext
    return ".exe"


def plan_build(root, engine, manifest, args, issues):
    """(command list, output path, extra report fields)."""
    exe, source = engine_exe(engine, root, manifest, args)
    if not exe:
        issues.append(f"{EXE_KEYS[engine]} not found (--engine-exe, $KILN_ENGINE_EXE, "
                      "machine.json, manifest.md, PATH)")
        exe = f"<{EXE_KEYS[engine]}>"
    elif not os.path.exists(exe):
        issues.append(f"engine executable does not exist: {exe}")
    info = {"engine_exe": norm(exe), "engine_exe_from": source}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if engine == "godot":
        preset = next((p for p in godot_presets(root) if p.get("name") == args.preset), None)
        if preset is None:
            names = [p.get("name") for p in godot_presets(root)]
            issues.append(f"preset '{args.preset}' not in export_presets.cfg (have: {names})")
            preset = {"name": args.preset}
        out = godot_out(root, preset, args)
        flag = "--export-pack" if args.pack else "--export-debug" if args.debug else \
            "--export-release"
        out = os.path.abspath(os.path.join(root, out))
        return [*launcher(exe), "--headless", "--path", root, flag, args.preset, out] + \
            args.extra, out, info
    if engine == "unity":
        method = args.method
        if not method:
            allowed = [m["method"] for m in unity_build_methods(root) if m["guard_allowed"]]
            method = allowed[0] if allowed else None
            if not method:
                issues.append("no build method: pass --method Ns.Class.Build or add KilnBuild.cs")
                method = "<Namespace.Class.Build>"
        if "build" not in method.lower():
            issues.append(f"method {method} has no 'Build' in its name; the Kiln guard denies "
                          "other -executeMethod calls")
        settings = read_text(os.path.join(root, "ProjectSettings", "ProjectSettings.asset"))
        product = re.search(r"^\s*productName:\s*(.+)$", settings, re.M)
        name = slug(product.group(1)) if product else "game"
        out = os.path.abspath(os.path.join(root, args.out or os.path.join(
            "export", slug(os.path.splitext(os.path.basename(args.preset))[0]),
            name + unity_ext(args.preset))))
        log = os.path.join(root, "export", "logs", f"unity-{slug(args.preset)}-{stamp}.log")
        info["engine_log"] = norm(log)
        cmd = [*launcher(exe), "-batchmode", "-quit", "-projectPath", root, "-logFile", log,
               "-executeMethod", method, "-kilnPreset", args.preset, "-kilnOut", out]
        return cmd + (["-kilnDevelopment"] if args.debug else []) + args.extra, out, info
    uprojects = globlib.glob(os.path.join(root, "*.uproject"))
    if not uprojects:
        issues.append("no *.uproject in the project root")
    uproject = os.path.abspath(uprojects[0]) if uprojects else "<project>.uproject"
    config = "Development" if args.debug else "Shipping"
    out = os.path.abspath(os.path.join(root, args.out or os.path.join(
        "export", f"{slug(args.preset)}-{config.lower()}")))
    uat = runuat_from(exe) if not exe.startswith("<") else "<RunUAT>"
    info["runuat"] = norm(uat)
    cmd = [*launcher(uat), "BuildCookRun", f"-project={uproject}", "-noP4", "-utf8output",
           "-unattended", f"-platform={args.preset}", f"-clientconfig={config}", "-build",
           "-cook", "-stage", "-pak", "-iostore", "-package", "-archive",
           f"-archivedirectory={out}", "-prereqs"]
    return cmd + args.extra, out, info


def newest_mtime(path):
    if os.path.isfile(path):
        return os.path.getmtime(path)
    times = [os.path.getmtime(os.path.join(d, f)) for d, _, fs in os.walk(path) for f in fs]
    return max(times) if times else 0


def cmd_build(args):
    root = os.path.abspath(args.root)
    manifest = read_manifest(root)
    engine = args.engine or detect_engine(root, manifest)
    if engine not in EXE_KEYS:
        return emit({"verdict": "fail", "issues": ["engine unknown: set engine= in manifest.md "
                                                   "or pass --engine"]})
    issues = []
    cmd, out, info = plan_build(root, engine, manifest, args, issues)
    result = {"engine": engine, "preset": args.preset, "dry_run": args.dry_run,
              "command": cmd, "command_line": subprocess.list2cmdline(cmd), "out": norm(out),
              **info}
    if args.dry_run or issues:
        result.update(verdict="fail" if issues else "pass", issues=issues)
        return emit(result)

    artefact_dir = out if engine == "unreal" or os.path.isdir(out) else os.path.dirname(out)
    os.makedirs(artefact_dir, exist_ok=True)  # Godot requires the target folder to exist
    export_root = os.path.join(root, "export")
    if engine == "godot" and norm(out).lower().startswith(norm(export_root).lower() + "/"):
        open(os.path.join(export_root, ".gdignore"), "a").close()
    logs = os.path.join(export_root, "logs")
    os.makedirs(logs, exist_ok=True)
    log_path = os.path.join(logs, f"build-{engine}-{slug(args.preset)}-"
                                  f"{time.strftime('%Y%m%d-%H%M%S')}.log")
    start = time.time()
    try:
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            proc = subprocess.run(cmd, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                  timeout=args.timeout)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        code, issues = None, issues + [f"timed out after {args.timeout} s"]
    except OSError as exc:
        code, issues = None, issues + [f"could not start: {exc}"]
    duration = round(time.time() - start, 1)
    text = read_text(log_path)
    if info.get("engine_log"):
        text += "\n" + read_text(info["engine_log"])
    exists = os.path.exists(out)
    fresh = exists and newest_mtime(out) >= start - 2
    size = (os.path.getsize(out) if os.path.isfile(out) else dir_stats(out, 0)["bytes"]) \
        if exists else 0
    if code not in (0, None):
        issues.append(f"exit code {code}")
    if not exists:
        issues.append(f"artefact missing: {norm(out)}")
    elif not fresh:
        issues.append("artefact is older than this build - the export did not write it")
    elif size == 0:
        issues.append("artefact is empty")
    if engine == "unreal" and exists and os.name == "nt" and \
            not globlib.glob(os.path.join(out, "**", "*.exe"), recursive=True):
        issues.append("no .exe in the archive directory")
    result.update(verdict="fail" if issues else "pass", exit_code=code, duration_s=duration,
                  artefact={"path": norm(out), "exists": exists, "fresh": fresh, "bytes": size},
                  output_dir=dict(path=norm(artefact_dir), **dir_stats(artefact_dir)),
                  log=norm(log_path), log_errors=error_lines(text, engine),
                  log_tail=tail(text), issues=issues)
    return emit(result)


# ---------------------------------------------------------------- smoke

def memory_bytes(pid):
    """Private bytes (Windows) or resident set size, or None."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class Counters(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + \
                    [(n, ctypes.c_size_t) for n in (
                        "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                        "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                        "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                        "PrivateUsage")]

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                                    wintypes.DWORD]
            k32.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = k32.OpenProcess(0x1000 | 0x0010, False, pid)
            if not handle:
                return None
            counters = Counters()
            counters.cb = ctypes.sizeof(Counters)
            ok = k32.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
            k32.CloseHandle(handle)
            return int(counters.PrivateUsage) if ok else None
        status = f"/proc/{pid}/status"
        if os.path.exists(status):
            m = re.search(r"VmRSS:\s*(\d+)\s*kB", read_text(status))
            return int(m.group(1)) * 1024 if m else None
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True,
                             text=True, timeout=5).stdout.strip()
        return int(out) * 1024 if out.isdigit() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def kill_tree(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                       timeout=30)
    else:
        import signal
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError:
                pass
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()


def cmd_smoke(args):
    root = os.path.abspath(args.root)
    engine = args.engine or detect_engine(root, read_manifest(root))
    matches = sorted(globlib.glob(args.executable)) if has_glob(args.executable) \
        else [args.executable]
    result = {"executable": args.executable, "seconds": args.seconds}
    if len(matches) != 1 or not os.path.isfile(matches[0]):
        result.update(verdict="fail", matches=[norm(m) for m in matches],
                      issues=["need exactly one existing executable; pass a specific path"])
        return emit(result)
    exe = os.path.abspath(matches[0])
    cwd = os.path.abspath(args.cwd) if args.cwd else os.path.dirname(exe)
    cmd = launcher(exe) + args.extra
    tmp = tempfile.mkdtemp(prefix="kiln-smoke-")
    out_path, err_path = os.path.join(tmp, "stdout.txt"), os.path.join(tmp, "stderr.txt")
    kwargs = {"creationflags": 0x00000200} if os.name == "nt" else {"start_new_session": True}
    start = time.time()
    samples, next_sample = [], start + args.warmup if args.sample_every else None
    with open(out_path, "wb") as out_fh, open(err_path, "wb") as err_fh:
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, stdout=out_fh, stderr=err_fh,
                                    stdin=subprocess.DEVNULL, **kwargs)
        except OSError as exc:
            result.update(verdict="fail", command=cmd, issues=[f"could not start: {exc}"])
            return emit(result)
        deadline = start + args.seconds
        while time.time() < deadline and proc.poll() is None:
            if next_sample is not None and time.time() >= next_sample:
                mem = memory_bytes(proc.pid)
                if mem is not None:
                    samples.append({"t_s": round(time.time() - start, 1),
                                    "mb": round(mem / 1048576, 1)})
                next_sample += args.sample_every
            time.sleep(0.1)
        alive = proc.poll() is None
        alive_s = round(time.time() - start, 1)
        exit_code = None if alive else proc.returncode
        kill_tree(proc)
    stdout, stderr = read_text(out_path), read_text(err_path)
    shutil.rmtree(tmp, ignore_errors=True)

    issues = []
    log_info, log_text = None, ""
    if args.log:
        candidates = globlib.glob(args.log) if has_glob(args.log) else [args.log]
        candidates = [c for c in candidates if os.path.isfile(c)]
        newest = max(candidates, key=os.path.getmtime) if candidates else None
        fresh = bool(newest) and os.path.getmtime(newest) >= start - 1
        log_info = {"path": norm(newest) if newest else norm(args.log), "found": bool(newest),
                    "fresh": fresh}
        if fresh:
            log_text = read_text(newest)
            log_info["tail"] = tail(log_text, 40)
        else:
            issues.append("log missing or not written during this run: "
                          f"{log_info['path']}")
    errors = error_lines("\n".join((stdout, stderr, log_text)), engine, args.error, args.ignore)
    if not alive and exit_code != 0:
        issues.append(f"exited with code {exit_code} after {alive_s} s")
    if errors:
        issues.append(f"{len(errors)} error line(s) in output/log")
    growth = None
    if len(samples) >= 2 and samples[0]["mb"] > 0:
        growth = round((samples[-1]["mb"] - samples[0]["mb"]) / samples[0]["mb"] * 100, 1)
        if growth > args.max_growth:
            issues.append(f"memory grew {growth}% (limit {args.max_growth}%)")
    elif args.sample_every:
        issues.append("fewer than two memory samples - raise --seconds or lower --sample-every")
    result.update(verdict="fail" if issues else "pass", command=cmd, cwd=norm(cwd),
                  alive_at_end=alive, ran_s=alive_s, exit_code=exit_code, errors=errors,
                  stdout_tail=tail(stdout, 20), stderr_tail=tail(stderr, 20), log=log_info,
                  memory={"samples": samples, "growth_pct": growth} if args.sample_every
                  else None, issues=issues)
    return emit(result)


# ---------------------------------------------------------------- main

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:
        cut = argv.index("--")
        argv, extra = argv[:cut], argv[cut + 1:]
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "build", "smoke"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".", help="project root (default: current folder)")
        p.add_argument("--engine", choices=sorted(EXE_KEYS), help="override manifest engine=")
        if name == "build":
            p.add_argument("--preset", required=True,
                           help="Godot preset name | Unity build profile or target | Unreal "
                                "platform (Win64, Linux, Mac)")
            p.add_argument("--out", help="artefact path (Unreal: archive folder)")
            p.add_argument("--debug", action="store_true",
                           help="debug template / development build")
            p.add_argument("--pack", action="store_true", help="Godot: --export-pack only")
            p.add_argument("--method", help="Unity build method Namespace.Class.Build")
            p.add_argument("--engine-exe", help="editor/RunUAT executable")
            p.add_argument("--machine", help="machine.json with godot_exe/unity_exe/unreal_exe")
            p.add_argument("--timeout", type=float, default=3600)
            p.add_argument("--dry-run", action="store_true", help="print the command only")
        if name == "smoke":
            p.add_argument("executable", help="built executable (glob allowed, one match)")
            p.add_argument("--seconds", type=float, default=30,
                           help="how long it must stay up")
            p.add_argument("--log", help="game log file or glob; must be written during the run")
            p.add_argument("--error", action="append", default=[], help="extra error regex")
            p.add_argument("--ignore", action="append", default=[],
                           help="regex of known lines to ignore")
            p.add_argument("--cwd", help="working folder (default: the executable's folder)")
            p.add_argument("--sample-every", type=float, default=0,
                           help="memory sample interval in s (soak)")
            p.add_argument("--warmup", type=float, default=30,
                           help="first memory sample after this many s")
            p.add_argument("--max-growth", type=float, default=20,
                           help="allowed memory growth in %%")
    args = parser.parse_args(argv)
    args.extra = extra
    return {"audit": cmd_audit, "build": cmd_build, "smoke": cmd_smoke}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
