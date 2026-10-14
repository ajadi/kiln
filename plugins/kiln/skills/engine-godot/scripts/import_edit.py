"""Read and change Godot import options in a `.import` file. Python stdlib only.

  python import_edit.py get assets/music/calm.ogg.import
  python import_edit.py set assets/music/calm.ogg.import --param loop=true --param bpm=96 \
      --param beat_count=64 --param bar_beats=4
  python import_edit.py set assets/npc/npc.glb.import --param materials/extract=2 \
      --sub "animations::walk::settings/loop_mode=1" \
      --sub "nodes::PATH:Water/Surface::mesh_instance/cast_shadow=0" \
      --sub 'materials::Hair::use_external/enabled=true' \
      --sub 'materials::Hair::use_external/path="res://materials/hair.tres"'
  python import_edit.py set assets/npc/clips.glb.import --importer animation_library

get      prints {"importer", "params", "subresources"} as JSON (params as their raw Godot text).
--param  key=value under [params]; value in Godot text form, written as given (true, 96, "x").
--sub    path::to::key=value inside the [params] _subresources dictionary; value is JSON.
         Top level: animations (clip name), materials (material name), meshes (mesh name),
         nodes ("PATH:<node path from the scene root>"). Keys (Godot 4.7.2,
         resource_importer_scene.cpp): animations settings/loop_mode (0 none, 1 linear,
         2 pingpong), save_to_file/enabled, save_to_file/path; materials use_external/enabled,
         use_external/path; nodes mesh_instance/cast_shadow (0 off, 1 on, 2 double-sided,
         3 shadows only), node/node_type, physics/*.
--importer  scene | animation_library (Import As) ; sets [remap] importer and type.
--no-touch  do not bump the source file's mtime.

The editor skips a reimport while the source file's mtime is unchanged (g2 row 93), so `set`
touches the source; then run `filesystem_manage` op `reimport` with the source path through the
Godot AI MCP (a .csv translation needs op `scan`). Other lines of the file are kept verbatim;
a _subresources value that is not plain JSON (Vector3(...), Resource(...)) is refused rather
than rewritten. Exit 1 with a message on any error; the file is then unchanged.
"""

import argparse
import json
import os
import re
import sys

IMPORTER_TYPES = {"scene": "PackedScene", "animation_library": "AnimationLibrary"}


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def sections(lines):
    """{section name: (first line index after the header, end index)}."""
    out, name, start = {}, None, 0
    for i, line in enumerate(lines):
        m = re.match(r"^\[(\w+)\]\s*$", line)
        if m:
            if name:
                out[name] = (start, i)
            name, start = m.group(1), i + 1
    if name:
        out[name] = (start, len(lines))
    return out


def subresources_span(lines, start, end):
    """(first, last) line indexes of the `_subresources=` value, or None."""
    for i in range(start, end):
        if lines[i].startswith("_subresources="):
            depth, j = 0, i
            while j < end:
                text = lines[j] if j > i else lines[j][len("_subresources="):]
                depth += text.count("{") - text.count("}")
                if depth <= 0:
                    return i, j
                j += 1
            fail("_subresources: unbalanced braces")
    return None


def parse_subresources(lines, span):
    if span is None:
        return {}
    first, last = span
    text = "\n".join([lines[first][len("_subresources="):]] + lines[first + 1:last + 1])
    try:
        return json.loads(text)
    except ValueError:
        odd = re.search(r"\b[A-Z]\w*\(", text)
        fail("_subresources holds values this tool does not rewrite"
             + (f" ({odd.group(0)}...)" if odd else "") + "; change it in the editor's "
             "Advanced Import Settings or with a run-once @tool script (engine-godot "
             "references/import-settings.md).")


def load(path):
    if not path.endswith(".import"):
        fail(f"{path}: expected a .import file (the file next to the asset, e.g. a.glb.import)")
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
    except OSError as exc:
        fail(f"{path}: {exc}")
    found = sections(lines)
    if "params" not in found:
        fail(f"{path}: no [params] section")
    return lines, found


def params_of(lines, found):
    start, end = found["params"]
    out = {}
    for line in lines[start:end]:
        m = re.match(r"^([^=\s][^=]*)=(.*)$", line)
        if m and m.group(1) != "_subresources":
            out[m.group(1)] = m.group(2)
    return out


def importer_of(lines, found):
    start, end = found.get("remap", (0, 0))
    for line in lines[start:end]:
        m = re.match(r'^importer="(.*)"$', line)
        if m:
            return m.group(1)
    return None


def cmd_get(args):
    lines, found = load(args.file)
    start, end = found["params"]
    print(json.dumps({"importer": importer_of(lines, found),
                      "params": params_of(lines, found),
                      "subresources": parse_subresources(lines, subresources_span(lines, start,
                                                                                  end))},
                     indent=2))


def set_param(lines, found, key, value):
    start, end = found["params"]
    for i in range(start, end):
        if lines[i].startswith(key + "="):
            lines[i] = f"{key}={value}"
            return
    # append after the last non-empty line of [params]
    at = end
    while at > start and not lines[at - 1].strip():
        at -= 1
    lines.insert(at, f"{key}={value}")
    found["params"] = (start, end + 1)


def set_sub(tree, spec):
    path, sep, raw = spec.partition("=")
    keys = path.split("::")
    if not sep or len(keys) < 2:
        fail(f"--sub {spec}: expected group::name::key=value")
    try:
        value = json.loads(raw)
    except ValueError:
        fail(f"--sub {spec}: value must be JSON (1, true, \"res://x.tres\")")
    node = tree
    for key in keys[:-1]:
        child = node.setdefault(key, {})
        if not isinstance(child, dict):
            fail(f"--sub {spec}: {key} is not a dictionary")
        node = child
    node[keys[-1]] = value


def cmd_set(args):
    lines, found = load(args.file)
    original = list(lines)
    for spec in args.param or []:
        key, sep, value = spec.partition("=")
        if not sep or not key or key == "_subresources":
            fail(f"--param {spec}: expected key=value (use --sub for _subresources)")
        set_param(lines, found, key, value)
    if args.sub:
        start, end = found["params"]
        span = subresources_span(lines, start, end)
        tree = parse_subresources(lines, span)
        for spec in args.sub:
            set_sub(tree, spec)
        block = ("_subresources=" + json.dumps(tree, indent=0, ensure_ascii=False)).split("\n")
        if span:
            lines[span[0]:span[1] + 1] = block
        else:
            set_param(lines, found, "_subresources", "{}")
            start, end = found["params"]
            span = subresources_span(lines, start, end)
            lines[span[0]:span[1] + 1] = block
    if args.importer:
        if args.importer not in IMPORTER_TYPES:
            fail(f"--importer {args.importer}: one of {', '.join(IMPORTER_TYPES)}")
        start, end = found.get("remap", (0, 0))
        for i in range(start, end):
            if lines[i].startswith("importer="):
                lines[i] = f'importer="{args.importer}"'
            elif lines[i].startswith("type="):
                lines[i] = f'type="{IMPORTER_TYPES[args.importer]}"'
    if lines != original:
        with open(args.file, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines))
    source = args.file[:-len(".import")]
    if not args.no_touch and os.path.isfile(source):
        os.utime(source, None)
    print(json.dumps({"file": args.file, "changed": lines != original,
                      "touched": not args.no_touch and os.path.isfile(source),
                      "next": "filesystem_manage op=reimport (op=scan for .csv)"}))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("get")
    g.add_argument("file")
    s = sub.add_parser("set")
    s.add_argument("file")
    s.add_argument("--param", action="append")
    s.add_argument("--sub", action="append")
    s.add_argument("--importer")
    s.add_argument("--no-touch", action="store_true")
    args = ap.parse_args()
    (cmd_get if args.cmd == "get" else cmd_set)(args)


if __name__ == "__main__":
    main()
