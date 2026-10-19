"""Switch Kiln on or off in a Codex config.toml, safely. Stdlib only (Python 3.11+).

  python codex_config.py --off                    # user config (~/.codex/config.toml): Kiln off
  python codex_config.py --file .codex/config.toml --on    # this project: Kiln on
  python codex_config.py --file .codex/config.toml --plugin mattpocock-skills@mattpocock --off
  python codex_config.py --check [--file F]       # does Codex's file parse? names the bad line
  python codex_config.py --repair [--file F]      # split values glued to a table header

Never edit a Codex config.toml by hand or with a text tool: a block appended without a final
newline gets the next block glued to it (`enabled = false[features]`) and Codex will not start
(field report 2026-10-19). This script edits only `[plugins."<id>"] enabled`, keeps every
other line, always ends the file with a newline, parses the result before writing it, and
leaves the old file as `config.toml.kiln-backup`. A file that does not parse is not touched:
--check names the line, --repair fixes the glued-header case.
"""

import argparse
import os
import re
import sys
import tomllib

GLUED = re.compile(r'^(\s*[A-Za-z0-9_."@-]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s\[#]+))\s*(\[.*)$')


def default_file():
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    return os.path.join(home, "config.toml")


def parse_error(text):
    try:
        tomllib.loads(text)
        return None
    except tomllib.TOMLDecodeError as e:
        return str(e)


def set_enabled(text, value, plugin="kiln@kiln"):
    header = f'[plugins."{plugin}"]'
    header_re = re.compile(r'^\s*\[\s*plugins\s*\.\s*"' + re.escape(plugin) + r'"\s*\]\s*(#.*)?$')
    lines = text.splitlines()
    word = "true" if value else "false"
    start = next((i for i, line in enumerate(lines) if header_re.match(line)), None)
    if start is None:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ([""] if lines else []) + [header, f"enabled = {word}"]
    else:
        end = next((i for i in range(start + 1, len(lines))
                    if re.match(r"^\s*\[", lines[i])), len(lines))
        key = next((i for i in range(start + 1, end)
                    if re.match(r"^\s*enabled\s*=", lines[i])), None)
        if key is None:
            lines.insert(start + 1, f"enabled = {word}")
        else:
            lines[key] = f"enabled = {word}"
    return "\n".join(lines) + "\n"


def repair(text):
    out = []
    for line in text.splitlines():
        m = GLUED.match(line)
        out += [m.group(1).rstrip(), "", m.group(2)] if m else [line]
    return "\n".join(out) + "\n"


def write(path, old, new):
    if parse_error(new):
        raise SystemExit(f"refusing to write {path}: the result would not parse ({parse_error(new)})")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if old is not None:
        with open(path + ".kiln-backup", "w", encoding="utf-8", newline="") as fh:
            fh.write(old)
    tmp = path + ".kiln-tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", default=default_file())
    ap.add_argument("--plugin", default="kiln@kiln", help="plugin id (default kiln@kiln)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--on", action="store_true")
    mode.add_argument("--off", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--repair", action="store_true")
    a = ap.parse_args()
    old = None
    if os.path.isfile(a.file):
        with open(a.file, encoding="utf-8") as fh:
            old = fh.read()
    error = parse_error(old) if old is not None else None
    if a.check:
        print(f"{a.file}: {error}" if error else f"{a.file}: ok")
        if error:
            print("Fix: python codex_config.py --repair --file <that file> (a value glued to a "
                  "table header), or correct that line by hand.")
        return 1 if error else 0
    if a.repair:
        if not error:
            print(f"{a.file}: ok, nothing to repair")
            return 0
        fixed = repair(old)
        if parse_error(fixed):
            print(f"{a.file}: still broken after repair ({parse_error(fixed)}); fix that line by hand")
            return 1
        write(a.file, old, fixed)
        print(f"{a.file}: repaired (old file kept as {os.path.basename(a.file)}.kiln-backup)")
        return 0
    if error:
        print(f"{a.file} does not parse: {error}. Not touched. Run --check / --repair first.")
        return 1
    write(a.file, old, set_enabled(old or "", a.on, a.plugin))
    print(f"{a.file}: {a.plugin} enabled = {'true' if a.on else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
