"""Merge Kiln's settings into another program's JSON file, safely. Stdlib only.

  python json_config.py merge --file .claude/settings.json --json '{"enabledPlugins": {"kiln@kiln": true}}'
  python json_config.py merge --file .github/copilot/settings.json --json '{"enabledPlugins": {"kiln@kiln": true}}'
  python json_config.py merge --file opencode.json --json '{"mcp": {"godot-ai": {...}}}'
  python json_config.py merge --file Packages/manifest.json --json '{"dependencies": {...}}'
  python json_config.py check --file <file>

merge   deep-merges the object into the file: objects merge key by key, lists are joined
        without duplicates, other values are replaced; everything else in the file stays.
        Reads a BOM and JSONC (comments, trailing commas - OpenCode, VS Code); the result is
        plain JSON, so comments are not kept (the original is left as <file>.kiln-backup and the
        script says so). The result is parsed before it is written; the write is atomic.
check   says whether the file parses, and where it does not.
A file that does not parse is not touched. Never edit these files by hand or with a text tool:
a broken settings file makes the program ignore it (Claude Code: Kiln and the user's
permissions off) or refuse to start (Unity Packages/manifest.json, an Unreal .uproject).
"""

import argparse
import json
import os
import re
import sys

COMMENT = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/', re.S)
TRAILING = re.compile(r'"(?:\\.|[^"\\])*"|,(\s*[}\]])', re.S)


def strip_jsonc(text):
    """(plain JSON text, whether there were comments)."""
    found = []

    def drop(m):
        if m.group(0).startswith('"'):
            return m.group(0)
        found.append(1)
        return ""
    text = COMMENT.sub(drop, text)
    text = TRAILING.sub(lambda m: m.group(0) if m.group(0).startswith('"') else m.group(1), text)
    return text, bool(found)


def load(path):
    """(data or None, original text, comments?, error)."""
    if not os.path.exists(path):
        return {}, None, False, None
    with open(path, encoding="utf-8-sig") as fh:
        original = fh.read()
    if not original.strip():
        return {}, original, False, None
    plain, comments = strip_jsonc(original)
    try:
        return json.loads(plain), original, comments, None
    except json.JSONDecodeError as e:
        return None, original, comments, f"line {e.lineno}, column {e.colno}: {e.msg}"


def merge(base, extra):
    if isinstance(base, dict) and isinstance(extra, dict):
        out = dict(base)
        for key, value in extra.items():
            out[key] = merge(base[key], value) if key in base else value
        return out
    if isinstance(base, list) and isinstance(extra, list):
        return base + [v for v in extra if v not in base]
    return extra


def write(path, original, data):
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    json.loads(text)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if original is not None:
        with open(path + ".kiln-backup", "w", encoding="utf-8", newline="") as fh:
            fh.write(original)
    tmp = path + ".kiln-tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--file", required=True)
    m.add_argument("--json", required=True, help="a JSON object to merge in")
    c = sub.add_parser("check")
    c.add_argument("--file", required=True)
    a = ap.parse_args()
    data, original, comments, error = load(a.file)
    if error:
        print(f"{a.file} does not parse ({error}). Not touched - fix that line, or ask the user.")
        return 1
    if a.cmd == "check":
        print(f"{a.file}: ok" + (" (JSONC: has comments)" if comments else ""))
        return 0
    extra = json.loads(a.json)
    if not isinstance(extra, dict) or not isinstance(data, dict):
        print("Both the file and --json must be JSON objects.")
        return 1
    write(a.file, original, merge(data, extra))
    note = (" Its comments were not kept; the original is in "
            f"{os.path.basename(a.file)}.kiln-backup.") if comments else ""
    print(f"{a.file}: merged.{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
