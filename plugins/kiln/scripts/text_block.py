"""Kiln's additions to a project's own text files (.gitignore, .gitattributes, CLAUDE.md,
GEMINI.md, AGENTS.md), without breaking what the user has there. Stdlib only.

  python text_block.py block --file .gitignore --source <kiln>/templates/project/gitignore.tmpl --marker kiln
  python text_block.py include --file CLAUDE.md --line "@AGENTS.md"
  python text_block.py include --file .gitattributes --line "* text=auto eol=lf"

block    puts the source text between `# --- <marker> ---` and `# --- <marker> end ---` lines
         (replaces that block on re-runs; an old block with only the start line is left alone);
         the rest of the file is kept, a missing final newline is added before the block.
include  makes the line the file's first line if it is not there yet; the user's text stays.
Both keep the file's line endings (LF or CRLF), drop a BOM, and end the file with a newline.
Use this instead of appending with a text tool: `.env` + an appended block without a newline
became `.env# --- kiln ---` and the user's last pattern stopped working (install audit).
"""

import argparse
import os
import sys


def load(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except FileNotFoundError:
        return "", "\n"
    text = raw.decode("utf-8-sig")
    eol = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), eol


def save(path, text, eol):
    text = text.rstrip("\n") + "\n"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text.replace("\n", eol))


def block(path, source, marker):
    begin, end = f"# --- {marker} ---", f"# --- {marker} end ---"
    with open(source, encoding="utf-8-sig") as fh:
        body = [line for line in fh.read().replace("\r\n", "\n").splitlines()
                if line.strip() not in (begin, end)]
    text, eol = load(path)
    lines = text.splitlines()
    new = [begin] + body + [end]
    if any(x.strip().startswith(f"# --- {marker}") and x.strip() not in (begin, end)
           for x in lines):
        return "kept: an older Kiln block is there"
    if begin in [line.strip() for line in lines]:
        start = [line.strip() for line in lines].index(begin)
        stop = next((i for i in range(start + 1, len(lines)) if lines[i].strip() == end), None)
        if stop is None:
            return "kept: an older Kiln block without its end line is there"
        lines[start:stop + 1] = new
    else:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ([""] if lines else []) + new
    save(path, "\n".join(lines), eol)
    return "written"


def include(path, line):
    text, eol = load(path)
    lines = text.splitlines()
    if line in (x.strip() for x in lines):
        if text and not text.endswith("\n"):
            save(path, text, eol)
        return "already there"
    save(path, "\n".join([line] + lines), eol)
    return "added"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("block")
    b.add_argument("--file", required=True)
    b.add_argument("--source", required=True)
    b.add_argument("--marker", required=True)
    i = sub.add_parser("include")
    i.add_argument("--file", required=True)
    i.add_argument("--line", required=True)
    a = ap.parse_args()
    result = block(a.file, a.source, a.marker) if a.cmd == "block" else include(a.file, a.line)
    print(f"{a.file}: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
