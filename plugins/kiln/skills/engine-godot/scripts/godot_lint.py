"""Lint Godot 4 text files: Godot 3 API in GDScript, broken references in scenes. Stdlib only.

  python godot_lint.py [paths ...] [--root .]      # default: every .gd/.tscn/.tres under --root

Agents mix Godot 3 and 4 (public training data leans to Godot 3) and break text scene files in
ways that load without a compile error or fail only when the scene opens. Reported:

GDScript (.gd, and scripts embedded in scenes)
  error   an API Godot 4 does not have (yield, KinematicBody, export var, setget, .instance(),
          string connect(), File/Directory, deg2rad, Pool*Array, ...): the Godot 4 form is given
  style   valid in Godot 4 but a Godot 3 habit (emit_signal("x"), SkeletonIK3D)
Scenes and resources (.tscn, .tres)
  error   not format=3 (a Godot 3 file); an ExtResource / SubResource id that is not defined; an
          id defined twice; a node whose parent path does not exist; two siblings with one name;
          a connection from or to a missing node; a sub_resource after the nodes; two files with
          one uid
  warn    an ext_resource whose res:// path is missing; a resource defined but never used;
          load_steps that does not match
Output JSON; exit 1 when there is an error. engine-godot's guard rule uses the same GDScript
table for script_create / script_patch.
"""

import argparse
import glob
import json
import os
import re
import sys

# (pattern, Godot 4 form, severity); applied to code with comments and string contents removed,
# except the ones marked raw (they look at string arguments)
GODOT3 = [
    (r"\byield\s*\(", "await obj.signal / await get_tree().process_frame", "error"),
    (r"\bmove_and_slide_with_snap\b", "floor_snap_length / apply_floor_snap()", "error"),
    (r"\bmove_and_slide\s*\(\s*[^)\s]", "set velocity and up_direction; move_and_slide() takes no arguments", "error"),
    (r"^\s*export\s*(\(|var\b)", "@export var x: T", "error"),
    (r"^\s*onready\s+var\b", "@onready var", "error"),
    (r"^\s*tool\s*$", "@tool", "error"),
    (r"\bsetget\b", "var x: T: set = s, get = g", "error"),
    (r"\.instance\s*\(\s*\)", "instantiate()", "error"),
    (r"\binterpolate_property\b|\bTween\.new\s*\(", "create_tween().tween_property(...)", "error"),
    (r"\brand_range\s*\(", "randf_range / randi_range", "error"),
    (r"\b(deg2rad|rad2deg|stepify|range_lerp|str2var|var2str|polar2cartesian|cartesian2polar|linear2db|db2linear)\s*\(",
     "deg_to_rad, rad_to_deg, snapped, remap, str_to_var, var_to_str, ..._to_..., linear_to_db, db_to_linear", "error"),
    (r"\b(to_json|parse_json)\s*\(", "JSON.stringify / JSON.parse_string", "error"),
    (r"\b(File|Directory)\.new\s*\(", "FileAccess.open() / DirAccess.open()", "error"),
    (r"\bOS\.get_ticks_(msec|usec)\s*\(", "Time.get_ticks_msec() / Time.get_ticks_usec()", "error"),
    (r"\bchange_scene\s*\(", "change_scene_to_file() / change_scene_to_packed()", "error"),
    (r"\bget_world\s*\(\s*\)", "get_world_3d()", "error"),
    (r"\bcast_to\b", "target_position", "error"),
    (r"\bPool(Byte|Int|Real|String|Vector2|Vector3|Color)Array\b", "Packed...Array", "error"),
    (r"\bNavigationMeshInstance\b|\bset_target_location\s*\(", "NavigationRegion3D / target_position", "error"),
    (r"\b(GIProbe|BakedLightmap)\b", "VoxelGI / LightmapGI", "error"),
    (r"\.empty\s*\(\s*\)", "is_empty()", "error"),
    (r"\bload_interactive\s*\(", "ResourceLoader.load_threaded_request()", "error"),
    (r"\bEngine\.editor_hint\b", "Engine.is_editor_hint()", "error"),
    (r"^\s*\.\w+\s*\(", "super.method()", "error"),
    (r"\.translation\b", ".position", "error"),
    (r"\bTransform\s*\(", "Transform3D(", "error"),
    (r"\bQuat\b", "Quaternion", "error"),
    (r"(\bextends\s+|:\s*|\bas\s+|\bis\s+)(KinematicBody|KinematicBody2D|RigidBody|StaticBody|Area|"
     r"MeshInstance|CollisionShape|CollisionPolygon|Camera|RayCast|Particles|Spatial|Position3D|"
     r"Position2D|Listener|ImmediateGeometry|VisibilityNotifier|PathFollow|Navigation)\b",
     "the Godot 4 class (CharacterBody3D, RigidBody3D, StaticBody3D, Area3D, MeshInstance3D, "
     "CollisionShape3D, Camera3D, RayCast3D, GPUParticles3D, Node3D, Marker3D/Marker2D, ...)", "error"),
    (r"\b(KinematicBody|KinematicBody2D|RigidBody|StaticBody|Area|MeshInstance|CollisionShape|"
     r"Camera|RayCast|Spatial|Position3D|Position2D)\.new\s*\(", "the Godot 4 class with its 3D/2D name", "error"),
]
RAW = [
    (r"\bconnect\s*\(\s*\"[^\"]+\"\s*,\s*[\w.]+\s*,\s*\"", "signal.connect(callable) / sig.connect(_m.bind(a))", "error"),
    (r"\bemit_signal\s*\(\s*\"", "signal.emit(args)", "style"),
    (r"\bSkeletonIK3D\b", "TwoBoneIK3D / FABRIK3D / CCDIK3D (4.6+)", "style"),
]
_COMPILED = [(re.compile(p, re.M), fix, sev) for p, fix, sev in GODOT3]
_RAW = [(re.compile(p), fix, sev) for p, fix, sev in RAW]


def strip_line(line):
    """Code without the comment and with string contents blanked (quotes kept)."""
    out, quote, i = [], None, 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
                out.append(ch)
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out)


SUPER_CALL = r"^\s*\.\w+\s*\("


def lint_gdscript(text):
    hits = []
    depth, continued = 0, False
    for number, line in enumerate(text.splitlines(), 1):
        code = strip_line(line)
        # a line that starts with `.` inside open brackets or after a `\` continues a method
        # chain (Godot 4 tweens, builders); only at the start of a statement is it Godot 3's
        # `.method()` super call (bug hunt 2026-10-20: the chain was refused)
        chain = depth > 0 or continued
        depth = max(0, depth + sum(code.count(c) for c in "([{") - sum(code.count(c) for c in ")]}"))
        continued = code.rstrip().endswith("\\")
        if "kiln:godot3-ok" in line:
            continue
        raw = line.split("#", 1)[0] if '"' not in line else line
        for rx, fix, sev in _COMPILED:
            if chain and rx.pattern == SUPER_CALL:
                continue
            if rx.search(code):
                hits.append({"line": number, "severity": sev, "found": rx.search(code).group(0).strip(),
                             "godot4": fix})
        for rx, fix, sev in _RAW:
            if rx.search(raw):
                hits.append({"line": number, "severity": sev, "found": rx.search(raw).group(0).strip(),
                             "godot4": fix})
    return hits


REF = re.compile(r"\b(ExtResource|SubResource)\(\s*\"([^\"]+)\"\s*\)")


def header(line):
    """(kind, attrs) of a section header line like [node name="A" parent="." x=T("a", "b")], or
    None. Values are "strings" (unquoted here), Type(...) calls with nested brackets and
    quotes (kept as written), or bare tokens."""
    s = line.strip()
    if not (s.startswith("[") and s.endswith("]")):
        return None
    s = s[1:-1]
    m = re.match(r"(\w+)", s)
    if not m:
        return None
    kind, i, attrs = m.group(1), m.end(), {}
    while i < len(s):
        while i < len(s) and s[i] == " ":
            i += 1
        k = re.match(r"([\w/]+)=", s[i:])
        if not k:
            return None if s[i:].strip() else (kind, attrs)
        key, i = k.group(1), i + k.end()
        if i < len(s) and s[i] == '"':
            j = i + 1
            while j < len(s) and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            attrs[key], i = s[i + 1:j], j + 1
            continue
        depth, j, quote = 0, i, False
        while j < len(s):
            ch = s[j]
            if quote:
                if ch == "\\":
                    j += 1
                elif ch == '"':
                    quote = False
            elif ch == '"':
                quote = True
            elif ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == " " and depth <= 0:
                break
            j += 1
        attrs[key], i = s[i:j], j
    return kind, attrs


def sections(text):
    """[(kind, attrs, body lines, line number)] of a Godot text resource."""
    out, current = [], None
    for number, line in enumerate(text.splitlines(), 1):
        h = header(line) if line.startswith("[") else None
        if h:
            current = [h[0], h[1], [], number]
            out.append(current)
        elif current is not None:
            current[2].append(line)
    return out


def lint_scene(text, path, root):
    problems = []

    def add(sev, line, what):
        problems.append({"severity": sev, "line": line, "problem": what})

    secs = sections(text)
    if not secs:
        add("error", 1, "not a Godot text resource (no [gd_scene] / [gd_resource] header)")
        return problems, None
    head = secs[0]
    if head[0] not in ("gd_scene", "gd_resource"):
        add("error", head[3], f"first section is [{head[0]}], expected [gd_scene] or [gd_resource]")
    if head[1].get("format") != "3":
        add("error", head[3], f"format={head[1].get('format')}: not a Godot 4 file (format=3)")
    ext, sub, used = {}, {}, set()
    nodes, seen_node = {}, False
    children = {}
    instanced = set()  # nodes from another scene: their children are not listed in this file

    def inside_instance(path):
        # an [editable] child of an instanced scene, or a node of an inherited scene (bug hunt
        # 2026-10-20: `parent="Player/Arm"` under an editable instance was reported missing)
        return any(path == i or path.startswith(i + "/") or i == "." for i in instanced)
    for kind, attrs, body, line in secs[1:]:
        text_body = "\n".join(body) + " " + " ".join(f'{k}="{v}"' for k, v in attrs.items())
        for ref_kind, ref_id in REF.findall(text_body):
            used.add((ref_kind, ref_id))
            table = ext if ref_kind == "ExtResource" else sub
            if ref_id not in table:
                add("error", line, f'{ref_kind}("{ref_id}") is not defined above this section')
        if kind == "ext_resource":
            rid = attrs.get("id", "")
            if rid in ext:
                add("error", line, f'ext_resource id "{rid}" is defined twice')
            ext[rid] = line
            res = attrs.get("path", "")
            if res.startswith("res://") and root and not os.path.exists(os.path.join(root, res[6:])):
                add("warn", line, f"ext_resource path {res} does not exist")
        elif kind == "sub_resource":
            rid = attrs.get("id", "")
            if rid in sub:
                add("error", line, f'sub_resource id "{rid}" is defined twice')
            if seen_node:
                add("error", line, f'sub_resource "{rid}" comes after the nodes')
            sub[rid] = line
        elif kind == "node":
            seen_node = True
            name, parent = attrs.get("name", ""), attrs.get("parent")
            if not name or re.search(r"[./:@%\"]", name):
                add("error", line, f'node name "{name}" is empty or has . / : @ % or a quote')
            if parent is None:
                if nodes:
                    add("error", line, f'node "{name}" has no parent but the root is already "{next(iter(nodes))}"')
                nodes["."] = name
                children.setdefault(".", set())
                if "instance" in attrs:
                    instanced.add(".")
                continue
            if parent not in nodes and parent not in children and not inside_instance(parent):
                add("error", line, f'node "{name}": parent "{parent}" does not exist above it')
            sibs = children.setdefault(parent, set())
            if name in sibs:
                add("error", line, f'two children of "{parent}" are named "{name}"')
            sibs.add(name)
            full = name if parent == "." else f"{parent}/{name}"
            nodes[full] = name
            children.setdefault(full, set())
            if "instance" in attrs or "instance_placeholder" in attrs:
                instanced.add(full)
        elif kind == "connection":
            for end in ("from", "to"):
                p = attrs.get(end, "")
                if p not in nodes and p not in children and not inside_instance(p):
                    add("error", line, f'connection {end}="{p}" names no node in this scene')
            if not attrs.get("method"):
                add("error", line, "connection without a method")
    for rid, line in ext.items():
        if ("ExtResource", rid) not in used:
            add("warn", line, f'ext_resource "{rid}" is never used')
    for rid, line in sub.items():
        if ("SubResource", rid) not in used:
            add("warn", line, f'sub_resource "{rid}" is never used')
    steps = head[1].get("load_steps")
    if steps and steps.isdigit() and int(steps) != len(ext) + len(sub) + 1:
        add("warn", head[3], f"load_steps={steps}, the file has {len(ext) + len(sub)} resources (+1)")
    for kind, attrs, body, line in secs:
        if kind == "sub_resource" and attrs.get("type") == "GDScript":
            src = "\n".join(body)
            m = re.search(r'script/source\s*=\s*"((?:[^"\\]|\\.)*)"', src, re.S)
            if m:
                code = m.group(1).encode().decode("unicode_escape", errors="replace")
                for h in lint_gdscript(code):
                    add(h["severity"] if h["severity"] != "style" else "warn", line,
                        f"embedded script line {h['line']}: {h['found']} -> {h['godot4']}")
    return problems, head[1].get("uid")


def files_under(root):
    out = []
    for ext in ("gd", "tscn", "tres"):
        out += glob.glob(os.path.join(root, "**", f"*.{ext}"), recursive=True)
    skip = (os.sep + ".godot" + os.sep, os.sep + "addons" + os.sep, os.sep + ".kiln" + os.sep)
    return sorted(p for p in out if not any(s in p for s in skip))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    paths = []
    for p in a.paths or [root]:
        paths += files_under(p) if os.path.isdir(p) else glob.glob(p)
    report, uids = [], {}
    for path in paths:
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as fh:
                text = fh.read()
        except OSError as e:
            report.append({"file": path, "problems": [{"severity": "error", "problem": str(e)}]})
            continue
        rel = os.path.relpath(path, root).replace("\\", "/")
        if path.endswith(".gd"):
            probs = [{"severity": h["severity"], "line": h["line"],
                      "problem": f"{h['found']} -> {h['godot4']}"} for h in lint_gdscript(text)]
        else:
            probs, uid = lint_scene(text, path, root)
            if uid:
                uids.setdefault(uid, []).append(rel)
        if probs:
            report.append({"file": rel, "problems": probs})
    for uid, owners in uids.items():
        if len(owners) > 1:
            report.append({"file": owners[0], "problems": [
                {"severity": "error", "problem": f"uid {uid} is also used by {', '.join(owners[1:])}"}]})
    errors = sum(p["severity"] == "error" for r in report for p in r["problems"])
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"files": len(paths), "errors": errors,
                      "warnings": sum(p["severity"] != "error" for r in report for p in r["problems"]),
                      "report": report, "verdict": "fail" if errors else "pass"}, indent=1))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
