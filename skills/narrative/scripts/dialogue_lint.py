"""Lint dialogue sources: Yarn Spinner `.yarn` scripts (Yarn 2/3 syntax, primary format) and Kiln
line tables (`kiln-dialogue/1` JSON graphs, CSV line tables). Python 3.12+, stdlib only.

  python dialogue_lint.py "dialogue/**/*.yarn" --entry Start --max-chars 80
  python dialogue_lint.py dialogue/ data/text/barks.csv --strict
  python dialogue_lint.py loc/strings.csv --id-col ID --text-col Text --ids warn

Checks (severity):
  broken_link              jump/detour/next/choice/entry target that does not exist   (error)
  unreachable              node not reachable from any entry node                      (error)
  dead_end                 Kiln JSON node or choice with no next and no "end": true    (error)
  duplicate_id             line ID used twice across all inputs                        (error)
  duplicate_node           node defined twice (Yarn node groups with `when:` are fine) (error)
  missing_id               line/option without an ID (#line:ID, "id", id column)       (error)
  too_long                 visible text over --max-chars (options: --max-option-chars) or
                           the line's / row's max_chars (CSV: max_chars, or the Godot
                           comment column _max_<lang> / _max)                          (error)
  implicit_end             Yarn flow can run off a node's end without <<stop>>/<<jump>>
                           (detour targets and nodes tagged `end` are exempt)          (warning)
  choices_all_conditional  every option of one choice point has a condition            (warning)
  dynamic_jump             <<jump {$expr}>>: reachability is incomplete                (warning)
  no_entry                 no entry node known, reachability skipped                   (warning)
  empty_text               line with no visible text                                   (warning)
  unreadable               JSON input that does not parse                              (error)

Entry nodes: --entry NAME (repeatable), Yarn nodes with `tags: entry`, a Yarn node titled Start,
the "entries" list of a Kiln JSON file. Visible text excludes the speaker prefix, tags, inline
conditions and markup; each {$expression} counts as --placeholder-chars characters.
Inputs are files, directories (searched for .yarn, .csv and kiln-dialogue JSON) or globs, which
the script expands itself. Lint sources, not exports of the same lines, in one run (an export
repeats every ID). Output: JSON with "verdict" PASS | WARN | FAIL, stats (nodes, lines, choices,
words, estimated VO minutes at --wpm) and findings. Exit 1 on FAIL (and on WARN with --strict),
2 when no input file is found.
"""

import argparse
import csv
import glob
import json
import os
import re
import sys
from collections import deque

JSON_FORMAT = "kiln-dialogue/1"
TERMINAL = {"jump", "stop", "return"}
BLOCK_END = {"endif", "endonce"}
TAG_SPLIT = re.compile(r"(?<!\\)#")
TAG_RE = re.compile(r"(?<!\\)#([^\s#]+)")
COMMAND_RE = re.compile(r"^<<\s*(\w+)\s*(.*?)\s*>>\s*$")
INLINE_CMD_RE = re.compile(r"<<.*?>>")
TRAILING_IF_RE = re.compile(r"<<\s*if\b.*?>>\s*$")
MARKUP_RE = re.compile(r"(?<!\\)\[/?[A-Za-z_][^\]]*\]|(?<!\\)\[/\]")
EXPR_RE = re.compile(r"(?<!\\)\{[^}]*\}")
SPEAKER_RE = re.compile(r"^([^:<>{}\[\]#\\]{1,40}?):\s")
COMMENT_RE = re.compile(r"(?<![:\\])//.*$")
HEADER_RE = re.compile(r"^\s*([A-Za-z_][\w.-]*)\s*:\s*(.*)$")


class Lint:
    def __init__(self, args):
        self.args = args
        self.errors, self.warnings = [], []
        self.ids = {}            # line id -> first location
        self.stats = {"files": 0, "nodes": 0, "lines": 0, "choices": 0, "words": 0}

    def add(self, severity, check, file, message, line=None, node=None, line_id=None):
        item = {"check": check, "file": file, "message": message}
        if line is not None:
            item["line"] = line
        if node is not None:
            item["node"] = node
        if line_id is not None:
            item["id"] = line_id
        (self.errors if severity == "error" else self.warnings).append(item)

    def missing_id(self, file, line, node, text):
        mode = self.args.ids
        if mode == "off":
            return
        self.add("error" if mode == "required" else "warning", "missing_id", file,
                 f"line has no ID: {text[:60]!r}", line, node)

    def register_id(self, line_id, file, line, node):
        where = f"{file}:{line}" if line is not None else f"{file} node {node}"
        if line_id in self.ids:
            self.add("error", "duplicate_id", file,
                     f"ID {line_id} already used at {self.ids[line_id]}", line, node, line_id)
        else:
            self.ids[line_id] = where

    def check_text(self, visible, file, line, node, line_id, limit=None):
        limit = limit or self.args.max_chars
        self.stats["lines"] += 1
        self.stats["words"] += len(visible.split())
        if not visible.strip():
            self.add("warning", "empty_text", file, "line has no visible text", line, node,
                     line_id)
        elif len(visible) > limit:
            self.add("error", "too_long", file,
                     f"{len(visible)} chars > {limit}: {visible[:60]!r}", line, node, line_id)


# ---------------------------------------------------------------- text helpers

def visible_text(text, placeholder, strip_speaker=True):
    """Text the player reads: no speaker prefix, tags, commands, markup; expressions as Xs."""
    body = TAG_SPLIT.split(text, 1)[0]
    body = INLINE_CMD_RE.sub("", body).strip()
    speaker = None
    m = SPEAKER_RE.match(body) if strip_speaker else None
    if m:
        speaker, body = m.group(1).strip(), body[m.end():]
    body = EXPR_RE.sub("X" * placeholder, body)
    body = MARKUP_RE.sub("", body)
    body = re.sub(r"\\(.)", r"\1", body)
    return speaker, re.sub(r"\s+", " ", body).strip()


def line_tags(text):
    parts = TAG_SPLIT.split(text, 1)
    return TAG_RE.findall("#" + parts[1]) if len(parts) == 2 else []


# ---------------------------------------------------------------- Yarn

class Stmt:
    __slots__ = ("lineno", "indent", "kind", "text", "cmd", "arg", "conditional")

    def __init__(self, lineno, indent, kind, text, cmd=None, arg="", conditional=False):
        self.lineno, self.indent, self.kind, self.text = lineno, indent, kind, text
        self.cmd, self.arg, self.conditional = cmd, arg, conditional


def parse_yarn(path):
    """Return [{title, tags, headers, has_when, lineno, stmts}] for one .yarn file."""
    with open(path, encoding="utf-8-sig") as fh:
        raw = fh.read().splitlines()
    nodes, i = [], 0
    while i < len(raw):
        headers, start = {}, None
        while i < len(raw) and raw[i].strip() != "---":
            m = HEADER_RE.match(raw[i])
            if m:
                headers.setdefault(m.group(1).lower(), []).append(m.group(2).strip())
                start = i if start is None else start
            i += 1
        if i >= len(raw):
            break
        i += 1  # skip ---
        stmts = []
        while i < len(raw) and raw[i].strip() != "===":
            src = COMMENT_RE.sub("", raw[i]).rstrip()
            expanded = src.expandtabs(4)
            indent = len(expanded) - len(expanded.lstrip())
            s = src.strip()
            if not s:
                pass
            elif s.startswith("->"):
                rest = s[2:].strip()
                stmts.append(Stmt(i + 1, indent, "option", rest,
                                  conditional=bool(TRAILING_IF_RE.search(TAG_SPLIT.split(rest, 1)[0]))))
            elif s.startswith("=>"):
                stmts.append(Stmt(i + 1, indent, "group", s[2:].strip()))
            elif s.startswith("<<"):
                m = COMMAND_RE.match(s)
                cmd, arg = (m.group(1).lower(), m.group(2)) if m else ("?", s)
                stmts.append(Stmt(i + 1, indent, "cmd", s, cmd, arg))
            else:
                stmts.append(Stmt(i + 1, indent, "line", s))
            i += 1
        i += 1  # skip ===
        title = (headers.get("title") or [""])[0]
        tags = []
        for value in headers.get("tags", []):
            tags += [t.lstrip("#") for t in value.split()]
        nodes.append({"title": title, "tags": tags, "has_when": "when" in headers,
                      "lineno": (start if start is not None else i) + 1, "stmts": stmts})
    return nodes


def ends_explicitly(stmts):
    """True if every path through this block ends in jump/stop/return."""
    if not stmts:
        return False
    base = min(s.indent for s in stmts)
    top = [i for i, s in enumerate(stmts) if s.indent == base]
    last = stmts[top[-1]]
    if last.kind == "cmd":
        return last.cmd in TERMINAL or last.cmd in BLOCK_END  # if/once blocks: not analysed
    if last.kind != "option":
        return False
    k = len(top) - 1
    while k >= 0 and stmts[top[k]].kind == "option":
        end = top[k + 1] if k + 1 < len(top) else len(stmts)
        body = stmts[top[k] + 1:end]
        if not ends_explicitly(body):
            return False
        k -= 1
    return True


def option_groups(stmts):
    """Yield lists of option statements that are offered together."""
    open_groups = {}
    for s in stmts:
        for indent in sorted(open_groups):
            if indent > s.indent or (indent == s.indent and s.kind != "option"):
                yield open_groups.pop(indent)
        if s.kind == "option":
            open_groups.setdefault(s.indent, []).append(s)
    for indent in sorted(open_groups):
        yield open_groups[indent]


def lint_yarn(lint, files):
    by_title, records = {}, []
    for path in files:
        for node in parse_yarn(path):
            node["file"] = path
            records.append(node)
            by_title.setdefault(node["title"], []).append(node)
    lint.stats["nodes"] += len(records)
    for title, group in by_title.items():
        if not title:
            for n in group:
                lint.add("error", "duplicate_node", n["file"], "node without title", n["lineno"])
        elif len(group) > 1 and not all(n["has_when"] for n in group):
            for n in group[1:]:
                lint.add("error", "duplicate_node", n["file"],
                         f"node {title} defined {len(group)} times without when: headers",
                         n["lineno"], title)
    jump_targets, detour_targets, dynamic = set(), set(), False
    edges = {}
    for n in records:
        out = edges.setdefault(n["title"], set())
        for s in n["stmts"]:
            if s.kind == "cmd" and s.cmd in ("jump", "detour"):
                target = s.arg.strip()
                if target.startswith("{"):
                    dynamic = True
                    lint.add("warning", "dynamic_jump", n["file"],
                             f"<<{s.cmd} {target}>> cannot be followed; reachability incomplete",
                             s.lineno, n["title"])
                    continue
                (jump_targets if s.cmd == "jump" else detour_targets).add(target)
                out.add(target)
                if target not in by_title:
                    lint.add("error", "broken_link", n["file"],
                             f"<<{s.cmd} {target}>>: no node titled {target}", s.lineno, n["title"])
            if s.kind in ("line", "option", "group"):
                speaker, text = visible_text(s.text, lint.args.placeholder_chars)
                if s.kind == "option":
                    lint.stats["choices"] += 1
                tags = line_tags(s.text)
                ids = [t[5:] for t in tags if t.startswith("line:") and len(t) > 5]
                if ids:
                    lint.register_id(ids[0], n["file"], s.lineno, n["title"])
                else:
                    lint.missing_id(n["file"], s.lineno, n["title"], text)
                limit = lint.args.max_option_chars if s.kind == "option" else None
                lint.check_text(text, n["file"], s.lineno, n["title"], ids[0] if ids else None,
                                limit)
        for group in option_groups(n["stmts"]):
            if all(s.conditional for s in group):
                lint.add("warning", "choices_all_conditional", n["file"],
                         f"all {len(group)} options have conditions; the player can be left with "
                         "no option — add an unconditional fallback", group[0].lineno, n["title"])
    entries = set(lint.args.entry or [])
    entries |= {n["title"] for n in records if "entry" in n["tags"]}
    if "Start" in by_title:
        entries.add("Start")
    for name in sorted(entries - set(by_title)):  # only --entry names can be missing
        lint.add("error", "broken_link", files[0], f"entry node {name} not found")
    reach_roots = entries & set(by_title)
    for n in records:
        title = n["title"]
        exempt = ("end" in n["tags"] or
                  (title in detour_targets and title not in jump_targets and title not in entries))
        if not exempt and not ends_explicitly(n["stmts"]):
            lint.add("warning", "implicit_end", n["file"],
                     "flow can run off the end of the node; end with <<stop>> or <<jump>>, or tag "
                     "the node `end`", n["lineno"], title)
    if not records:
        return
    if not reach_roots:
        lint.add("warning", "no_entry", files[0],
                 "no entry node (Start, tags: entry or --entry); reachability skipped")
        return
    seen = bfs(reach_roots, edges)
    if dynamic:
        return
    for n in records:
        if n["title"] and n["title"] not in seen:
            lint.add("error", "unreachable", n["file"],
                     f"node {n['title']} is not reachable from {sorted(reach_roots)}",
                     n["lineno"], n["title"])


def bfs(roots, edges):
    seen, queue = set(roots), deque(roots)
    while queue:
        for nxt in edges.get(queue.popleft(), ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


# ---------------------------------------------------------------- Kiln JSON

def lint_kiln_json(lint, docs):
    nodes, entries, edges = {}, set(), {}
    for path, doc in docs:
        entries |= set(doc.get("entries") or [])
        for node in doc.get("nodes") or []:
            nid = node.get("id")
            if not nid:
                lint.add("error", "duplicate_node", path, "node without id")
                continue
            if nid in nodes:
                lint.add("error", "duplicate_node", path, f"node {nid} defined twice", node=nid)
                continue
            nodes[nid] = (path, node)
    entries |= set(lint.args.entry or [])
    lint.stats["nodes"] += len(nodes)
    for nid, (path, node) in nodes.items():
        out = edges.setdefault(nid, set())
        for item in node.get("lines") or []:
            lint_json_line(lint, path, nid, item)
        choices = [ch if isinstance(ch, dict) else {"text": str(ch)}
                   for ch in node.get("choices") or []]
        for ch in choices:
            lint.stats["choices"] += 1
            lint_json_line(lint, path, nid, ch, lint.args.max_option_chars)
            target = ch.get("next") or node.get("next")
            if target:
                out.add(target)
                if target not in nodes:
                    lint.add("error", "broken_link", path, f"choice -> {target}: no such node",
                             node=nid, line_id=ch.get("id"))
            elif not ch.get("end"):
                lint.add("error", "dead_end", path, "choice has no next and no end: true",
                         node=nid, line_id=ch.get("id"))
        if choices and all(ch.get("condition") for ch in choices):
            lint.add("warning", "choices_all_conditional", path,
                     f"all {len(choices)} choices have conditions; add an unconditional fallback",
                     node=nid)
        nxt = node.get("next")
        if nxt:
            out.add(nxt)
            if nxt not in nodes:
                lint.add("error", "broken_link", path, f"next -> {nxt}: no such node", node=nid)
        if not choices and not nxt and not node.get("end"):
            lint.add("error", "dead_end", path,
                     "node has no choices, no next and no end: true — the player is stuck",
                     node=nid)
    if not nodes:
        return
    for name in sorted(entries - set(nodes)):
        lint.add("error", "broken_link", docs[0][0], f"entry {name}: no such node")
    roots = entries & set(nodes)
    if not roots:
        lint.add("warning", "no_entry", docs[0][0], "no entries; reachability skipped")
        return
    seen = bfs(roots, edges)
    for nid, (path, _node) in nodes.items():
        if nid not in seen:
            lint.add("error", "unreachable", path, f"node {nid} is not reachable", node=nid)


def lint_json_line(lint, path, nid, item, default_limit=None):
    if not isinstance(item, dict):
        item = {"text": str(item)}
    _speaker, text = visible_text(str(item.get("text", "")), lint.args.placeholder_chars,
                                  strip_speaker=False)
    line_id = item.get("id")
    if line_id:
        lint.register_id(str(line_id), path, None, nid)
    else:
        lint.missing_id(path, None, nid, text)
    lint.check_text(text, path, None, nid, line_id,
                    to_int(item.get("max_chars")) or default_limit)


def to_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- CSV line table

def pick_column(fields, wanted):
    lower = {f.strip().lower(): f for f in fields if f}
    for name in wanted:
        if name and name.lower() in lower:
            return lower[name.lower()]
    return None


def lint_csv(lint, path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        id_col = pick_column(fields, [lint.args.id_col, "id", "line_id", "key", "keys"])
        text_col = pick_column(fields, [lint.args.text_col, "text", lint.args.lang])
        # per-row limit: max_chars, or the Godot CSV comment column `_max` / `_max_<lang>`
        # (Godot skips `_` columns on import); the locale's own column wins
        max_col = pick_column(fields, [f"_max_{lint.args.lang}" if lint.args.lang else "",
                                       "max_chars", "_max_chars", "_max"])
        if not text_col:
            lint.add("error", "missing_id", path,
                     f"no text column (looked for {lint.args.text_col or 'text'}, {lint.args.lang})")
            return
        if not id_col and lint.args.ids != "off":
            lint.add("error" if lint.args.ids == "required" else "warning", "missing_id", path,
                     "no ID column (id, line_id, key, keys or --id-col)")
        for row in reader:
            line = reader.line_num
            _speaker, text = visible_text(row.get(text_col) or "", lint.args.placeholder_chars,
                                          strip_speaker=False)
            line_id = (row.get(id_col) or "").strip() if id_col else ""
            if id_col:
                if line_id:
                    lint.register_id(line_id, path, line, None)
                else:
                    lint.missing_id(path, line, None, text)
            limit = to_int(row.get(max_col)) if max_col else None
            lint.check_text(text, path, line, None, line_id or None, limit)


# ---------------------------------------------------------------- inputs

def collect(paths):
    found, missing = [], []
    for arg in paths:
        if any(ch in arg for ch in "*?["):
            matches = sorted(glob.glob(arg, recursive=True))
        elif os.path.isdir(arg):
            matches = sorted(os.path.join(root, f) for root, _d, names in os.walk(arg)
                             for f in names if f.lower().endswith((".yarn", ".csv", ".json")))
        elif os.path.isfile(arg):
            matches = [arg]
        else:
            matches = []
        if not matches:
            missing.append(arg)
        found += [m for m in matches if os.path.isfile(m) and m not in found]
    return found, missing


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="files, directories or globs")
    ap.add_argument("--entry", action="append", help="entry node name (repeatable)")
    ap.add_argument("--max-chars", type=int, default=80,
                    help="visible characters per line (default 80 = two 40-char subtitle lines)")
    ap.add_argument("--max-option-chars", type=int, default=40,
                    help="visible characters per option / choice (default 40 = one line)")
    ap.add_argument("--ids", choices=["required", "warn", "off"], default="required",
                    help="missing line IDs are errors (default), warnings or ignored")
    ap.add_argument("--id-col", default="", help="CSV ID column name")
    ap.add_argument("--text-col", default="", help="CSV text column name")
    ap.add_argument("--lang", default="en", help="CSV text column fallback (Godot CSV locale)")
    ap.add_argument("--placeholder-chars", type=int, default=8,
                    help="characters counted for each {$expression}")
    ap.add_argument("--wpm", type=float, default=150.0,
                    help="speech rate for the VO-minutes estimate")
    ap.add_argument("--strict", action="store_true", help="warnings fail the lint")
    ap.add_argument("--out", help="also write the JSON report to this file")
    args = ap.parse_args(argv)

    files, missing = collect(args.inputs)
    lint = Lint(args)
    yarn = [f for f in files if f.lower().endswith(".yarn")]
    csvs = [f for f in files if f.lower().endswith(".csv")]
    docs, skipped = [], []
    for f in files:
        if not f.lower().endswith(".json"):
            continue
        try:
            with open(f, encoding="utf-8-sig") as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            lint.add("error", "unreadable", f, f"cannot read JSON: {exc}")
            continue
        if isinstance(doc, dict) and doc.get("format") == JSON_FORMAT:
            docs.append((f, doc))
        else:
            skipped.append(f)
    lint.stats["files"] = len(yarn) + len(csvs) + len(docs)
    if yarn:
        lint_yarn(lint, yarn)
    if docs:
        lint_kiln_json(lint, docs)
    for f in csvs:
        lint_csv(lint, f)

    if lint.stats["files"] == 0:
        verdict = "FAIL"
    elif lint.errors or (args.strict and lint.warnings):
        verdict = "FAIL"
    elif lint.warnings:
        verdict = "WARN"
    else:
        verdict = "PASS"
    stats = dict(lint.stats)
    stats["vo_minutes_est"] = round(stats["words"] / args.wpm, 1) if args.wpm > 0 else None
    report = {"verdict": verdict, "stats": stats, "errors": lint.errors,
              "warnings": lint.warnings, "skipped_json": skipped, "not_found": missing,
              "settings": {"max_chars": args.max_chars,
                           "max_option_chars": args.max_option_chars, "ids": args.ids,
                           "wpm": args.wpm,
                           "entries": args.entry or []}}
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    sys.stdout.write(text + "\n")
    if lint.stats["files"] == 0:
        return 2
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
