"""Localization checks: hard-coded user-facing strings in sources and gaps in translation tables.
Python stdlib only.

  python loc_check.py --src scenes scripts --tables locale/*.csv
  python loc_check.py --src "scenes/**/*.tscn" "scripts/**/*.gd" --tables "locale/*.po" --locales fr,de,ja
  python loc_check.py --tables locale/game.csv --source-locale en --max-expansion 1.4
  python loc_check.py --src Assets/_Project/UI Assets/_Project/Scripts --tables loc/export.csv

--src      files, directories (walked recursively) or glob patterns (expanded here, ** allowed).
           Scanned: .tscn/.tres (text, placeholder_text, tooltip_text, title, */text properties;
           nodes with auto_translate_mode = 2 and their inheriting children are skipped), .gd
           (literal assigned to .text/.placeholder_text/.tooltip_text/.title or passed to
           set_text/add_item/...), .cs (.text/.tooltip/.label = "..." and SetText("...")),
           .uxml (text/label/tooltip attributes without a LocalizedString binding), .cpp/.h
           (FText::FromString with a literal). A line with `kiln:loc-ignore` is skipped.
--tables   Godot CSV (column 1 = key or source text, one column per locale, `_` comment columns,
           `?context`/`?plural` columns and a `?pluralrule` row as in Godot 4.6+; UTF-8 without
           BOM) and gettext .po (one locale per file; .pot templates only add keys).

A literal counts as a key when it is in a table (as key or msgid) or matches --key-pattern
(default: upper snake case with at least one `_` or `.`, e.g. MENU_START, HUD.AMMO). Literals
without letters (numbers, "%d", "/") are ignored. Key-shaped literals missing from the tables are
reported as unknown_keys.

Table checks per locale: missing or empty translations, missing plural forms (nplurals from the
`?pluralrule` row / PO Plural-Forms header, else a built-in gettext table), fuzzy PO entries
(gettext tools and Godot skip them), duplicate keys, printf placeholders (%s %d %.2f, compared in
order) and brace placeholders ({name} {0}, compared as a multiset; plural forms may drop a
placeholder but not add one), BOM/encoding. Expansion risk: display width of the translation /
display width of the source > --max-expansion (East Asian wide characters count 2, markup tags 0);
a warning unless --fail-on-expansion. --expansion-min-width N skips sources narrower than N
(short labels: Polish "Ok" -> "Okay" is 2x and no layout risk) and --expansion-allow KEY,... (or @file)
skips reviewed keys; UI widths are then checked by the ui skill's layout checks.

Output: JSON with "verdict" (pass|fail), "summary" counts and findings; exit code 1 on fail.
"""

import argparse
import csv
import glob
import io
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

SRC_EXT = {".tscn", ".tres", ".gd", ".cs", ".uxml", ".cpp", ".h", ".hpp"}
TABLE_EXT = {".csv", ".po", ".pot"}
SKIP_DIRS = {".git", ".godot", ".import", "addons", "Library", "Temp", "Logs", "obj", "bin",
             "Intermediate", "Saved", "DerivedDataCache", "Binaries", "node_modules", ".kiln"}
DEFAULT_KEY_PATTERN = r"[A-Z][A-Z0-9]*(?:[_.][A-Z0-9]+)+"
IGNORE_MARK = "kiln:loc-ignore"

# gettext nplurals by language (CLDR-derived gettext rules, as used by Godot's PO/CSV loaders).
NPLURALS = {"ja": 1, "zh": 1, "ko": 1, "th": 1, "vi": 1, "id": 1, "ms": 1, "tr": 2, "en": 2,
            "de": 2, "nl": 2, "sv": 2, "da": 2, "nb": 2, "no": 2, "fi": 2, "et": 2, "es": 2,
            "it": 2, "pt": 2, "fr": 2, "el": 2, "hu": 2, "bg": 2, "he": 2, "hi": 2, "fa": 2,
            "ru": 3, "uk": 3, "be": 3, "pl": 3, "cs": 3, "sk": 3, "hr": 3, "sr": 3, "bs": 3,
            "lt": 3, "lv": 3, "ro": 3, "sl": 4, "ga": 5, "ar": 6, "cy": 6}

PRINTF = re.compile(r"%(?:%|[-+0#]*\d*(?:\.\d+)?([sdifFeEgGxXcvo]))")
BRACE = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*|\d+)(?=[}:|,])")
MARKUP = re.compile(r"\[/?[A-Za-z_][^\]]*\]|</?[A-Za-z][^>]*>")

TSCN_PROP = re.compile(r"^(text|placeholder_text|tooltip_text|title|[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*/"
                       r"(?:text|tooltip))\s*=\s*(.*)$")
TSCN_HEADER = re.compile(r"^\[(\w+)(.*)\]\s*$")
GD_ASSIGN = re.compile(r"(?:^|[^\w])(?:[\w$%]+\.)*(text|placeholder_text|tooltip_text|title)\s*\+?=\s*"
                       r"(\"(?:[^\"\\]|\\.)*\")")
GD_CALL = re.compile(r"\b(set_text|add_item|set_item_text|add_check_item|add_radio_check_item|"
                     r"set_tooltip_text|set_placeholder|set_title|set_tab_title|add_tab|"
                     r"add_icon_item|set_item_tooltip)\s*\(([^)]*)\)")
CS_ASSIGN = re.compile(r"\.(text|Text|tooltip|label)\s*\+?=\s*(\$?@?\"(?:[^\"\\]|\\.)*\")")
CS_CALL = re.compile(r"\bSetText\s*\(\s*(\$?@?\"(?:[^\"\\]|\\.)*\")")
CPP_FROMSTRING = re.compile(r"FText::FromString\s*\(\s*(?:TEXT\s*\(\s*)?(\"(?:[^\"\\]|\\.)*\")")
STRING_LIT = re.compile(r"\"((?:[^\"\\]|\\.)*)\"")


# ---------------------------------------------------------------- helpers

def expand(patterns, exts):
    out, seen = [], set()
    for pat in patterns:
        if os.path.isdir(pat):
            hits = []
            for root, dirs, files in os.walk(pat):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                hits += [os.path.join(root, f) for f in sorted(files)]
        elif any(c in pat for c in "*?["):
            hits = sorted(glob.glob(pat, recursive=True))
        else:
            hits = [pat]
        for h in hits:
            if os.path.isfile(h) and os.path.splitext(h)[1].lower() in exts:
                n = os.path.normpath(h).replace("\\", "/")
                if n not in seen:
                    seen.add(n)
                    out.append(n)
            elif not os.path.exists(h):
                out.append(("missing", h))
    return out


def unescape(s):
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", "r": "\r"}.get(m.group(1), m.group(1)), s)


def width(s):
    s = MARKUP.sub("", s)
    w = 0
    for ch in s:
        if unicodedata.combining(ch) or ch in "​‌‍﻿":
            continue
        w += 2 if unicodedata.east_asian_width(ch) in "WF" else 1
    return w


def needs_translation(s):
    s = PRINTF.sub("", MARKUP.sub("", s))
    s = re.sub(r"\{[^{}]*\}", "", s)
    return any(ch.isalpha() for ch in s)


def placeholders(s):
    printf = [m.group(1) for m in PRINTF.finditer(s) if m.group(0) != "%%"]
    brace = sorted(m.group(1) for m in BRACE.finditer(s))
    return printf, brace


def strip_code_comment(line, marker):
    """Cut a line comment (# or //) that is outside string literals."""
    quote, i = None, 0
    while i < len(line):
        c = line[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif line.startswith(marker, i):
            return line[:i]
        i += 1
    return line


# ---------------------------------------------------------------- source scanning

def read_godot_string(lines, i, rest):
    """rest starts with a quote; the string may span lines. Returns (value, last line index)."""
    buf, j, text = [], i, rest[1:]
    while True:
        k, out = 0, []
        while k < len(text):
            c = text[k]
            if c == "\\" and k + 1 < len(text):
                out.append(text[k:k + 2])
                k += 2
                continue
            if c == '"':
                buf.append("".join(out))
                return unescape("\n".join(buf)), j
            out.append(c)
            k += 1
        buf.append("".join(out))
        j += 1
        if j >= len(lines):
            return unescape("\n".join(buf)), j - 1
        text = lines[j]


def scan_tscn(path, text):
    lines = text.splitlines()
    nodes, cur, i = [], None, 0
    while i < len(lines):
        line = lines[i]
        h = TSCN_HEADER.match(line)
        if h:
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', h.group(2)))
            cur = {"kind": h.group(1), "name": attrs.get("name", ""), "type": attrs.get("type", ""),
                   "parent": attrs.get("parent"), "mode": 0, "texts": []}
            nodes.append(cur)
            i += 1
            continue
        if cur is not None:
            m = TSCN_PROP.match(line)
            if m and m.group(2).startswith('"'):
                value, end = read_godot_string(lines, i, m.group(2))
                if IGNORE_MARK not in line:
                    cur["texts"].append((m.group(1), value, i + 1))
                i = end + 1
                continue
            am = re.match(r"^auto_translate_mode\s*=\s*(\d+)", line)
            if am:
                cur["mode"] = int(am.group(1))
        i += 1
    paths = {}
    for n in nodes:
        if n["kind"] != "node":
            continue
        if n["parent"] is None:
            n["path"] = "."
        elif n["parent"] == ".":
            n["path"] = n["name"]
        else:
            n["path"] = n["parent"] + "/" + n["name"]
        paths[n["path"]] = n

    def disabled(n):
        while n is not None:
            if n["mode"] == 2:
                return True
            if n["mode"] == 1:
                return False
            p = n.get("parent")
            n = paths.get("." if p == "." else p) if p is not None else None
        return False

    hits = []
    for n in nodes:
        if n["kind"] == "node" and disabled(n):
            continue
        for prop, value, line_no in n["texts"]:
            hits.append({"file": path, "line": line_no, "node": n.get("path", n["kind"]),
                         "type": n["type"], "property": prop, "text": value})
    return hits


def scan_code(path, text, kind):
    hits = []
    marker = "#" if kind == "gd" else "//"
    for no, raw in enumerate(text.splitlines(), 1):
        if IGNORE_MARK in raw:
            continue
        line = strip_code_comment(raw, marker)
        found = []
        if kind == "gd":
            found += [(m.group(1), m.group(2)) for m in GD_ASSIGN.finditer(line)]
            for m in GD_CALL.finditer(line):
                if "tr(" in m.group(2) or "tr_n(" in m.group(2):
                    continue
                for s in STRING_LIT.finditer(m.group(2)):
                    found.append((m.group(1), s.group(0)))
        elif kind == "cs":
            found += [(m.group(1), m.group(2)) for m in CS_ASSIGN.finditer(line)]
            found += [("SetText", m.group(1)) for m in CS_CALL.finditer(line)]
        else:
            found += [("FText::FromString", m.group(1)) for m in CPP_FROMSTRING.finditer(line)]
        for prop, lit in found:
            value = unescape(lit[lit.index('"') + 1:-1])
            hits.append({"file": path, "line": no, "property": prop, "text": value})
    return hits


def scan_uxml(path, text):
    hits = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return [], [f"{path}: UXML parse error {exc}"]
    lines = text.splitlines()
    for el in root.iter():
        bound = set()
        for child in el:
            if child.tag.split("}")[-1] == "Bindings":
                for b in child:
                    if b.tag.split("}")[-1].endswith("LocalizedString"):
                        bound.add(b.attrib.get("property", "text"))
        for attr in ("text", "label", "tooltip"):
            value = el.attrib.get(attr)
            if not value or attr in bound:
                continue
            needle = f'{attr}="{value}"'
            line_no = next((k for k, ln in enumerate(lines, 1) if needle in ln), 0)
            hits.append({"file": path, "line": line_no, "type": el.tag.split("}")[-1],
                         "property": attr, "text": value})
    return hits, []


def scan_sources(files):
    hits, warnings = [], []
    for f in files:
        if isinstance(f, tuple):
            warnings.append(f"no such source: {f[1]}")
            continue
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as exc:
            warnings.append(f"{f}: {exc}")
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext in (".tscn", ".tres"):
            hits += scan_tscn(f, text)
        elif ext == ".gd":
            hits += scan_code(f, text, "gd")
        elif ext == ".cs":
            hits += scan_code(f, text, "cs")
        elif ext == ".uxml":
            h, w = scan_uxml(f, text)
            hits += h
            warnings += w
        else:
            hits += scan_code(f, text, "cpp")
    return hits, warnings


# ---------------------------------------------------------------- tables

def lang_of(locale):
    return re.split(r"[_\-]", locale)[0].lower()


def expected_forms(locale, rules):
    m = re.search(r"nplurals\s*=\s*(\d+)", rules.get(locale, "") or "")
    if m:
        return int(m.group(1))
    return NPLURALS.get(lang_of(locale), 2)


def read_csv_table(path, delimiter, source_locale):
    problems, raw = [], open(path, "rb").read()
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append("UTF-8 BOM present (Godot needs UTF-8 without BOM)")
        raw = raw[3:]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, problems + [f"not UTF-8: {exc}"]
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if not rows:
        return None, problems + ["empty table"]
    header = [h.strip() for h in rows[0]]
    cols = {"locales": {}, "context": None, "plural": None}
    for idx, name in enumerate(header[1:], 1):
        if not name or name.startswith("_"):
            continue
        if name == "?context":
            cols["context"] = idx
        elif name == "?plural":
            cols["plural"] = idx
        else:
            cols["locales"][name] = idx

    def cell(row, idx):
        return row[idx] if idx is not None and idx < len(row) else ""

    first = header[0].lower()
    key_is_source = first not in ("keys", "key", "id", "") or (
        first == source_locale.lower())
    src_col = cols["locales"].get(source_locale)
    entries, rules, cur = [], {}, None
    for line_no, row in enumerate(rows[1:], 2):
        if not any(c.strip() for c in row):
            continue
        key = row[0] if row else ""
        if key == "?pluralrule":
            rules = {loc: cell(row, i) for loc, i in cols["locales"].items()}
            continue
        if not key:
            if cur is not None and cols["plural"] is not None:
                for loc, i in cols["locales"].items():
                    cur["forms"][loc].append(cell(row, i))
            continue
        source = cell(row, src_col) if src_col is not None else (key if key_is_source else None)
        cur = {"key": key, "context": cell(row, cols["context"]), "line": line_no,
               "source": source, "source_plural": cell(row, cols["plural"]) or None,
               "plural": bool(cell(row, cols["plural"])),
               "forms": {loc: [cell(row, i)] for loc, i in cols["locales"].items()}}
        entries.append(cur)
    locales = [l for l in cols["locales"] if l != source_locale]
    return {"format": "csv", "locales": locales, "entries": entries, "rules": rules,
            "has_source": src_col is not None or key_is_source}, problems


def po_unquote(s):
    s = s.strip()
    return unescape(s[1:-1]) if len(s) >= 2 and s[0] == '"' and s[-1] == '"' else ""


def read_po(path, source_locale):
    problems = []
    raw = open(path, "rb").read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return None, [f"not UTF-8: {exc}"]
    entries, cur, field = [], {}, None

    def flush():
        nonlocal cur, field
        if "msgid" in cur and not cur.get("obsolete"):
            entries.append(cur)
        cur, field = {}, None

    for no, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            flush()
            continue
        if s.startswith("#~"):
            cur["obsolete"] = True
            continue
        if s.startswith("#,"):
            if "msgid" in cur:
                flush()
            cur.setdefault("flags", set()).update(f.strip() for f in s[2:].split(","))
            continue
        if s.startswith("#"):
            continue
        m = re.match(r"^(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?)\s+(\".*\")$", s)
        if m:
            name = m.group(1)
            if name in ("msgctxt", "msgid") and "msgid" in cur and (
                    name == "msgctxt" or "msgstr" in cur or "msgstr_forms" in cur):
                flush()
            if m.group(2) is not None:
                cur.setdefault("msgstr_forms", {})[int(m.group(2))] = po_unquote(m.group(3))
                field = ("msgstr_forms", int(m.group(2)))
            else:
                cur[name] = po_unquote(m.group(3))
                cur.setdefault("line", no)
                field = (name, None)
            continue
        if s.startswith('"') and field:
            if field[1] is None:
                cur[field[0]] += po_unquote(s)
            else:
                cur["msgstr_forms"][field[1]] += po_unquote(s)
    flush()
    template = path.lower().endswith(".pot")
    header = next((e for e in entries if e.get("msgid") == "" and "msgctxt" not in e), None)
    locale, rules = os.path.splitext(os.path.basename(path))[0], {}
    if header:
        hs = header.get("msgstr", "")
        lm = re.search(r"^Language:\s*(\S+)", hs, re.M)
        if lm:
            locale = lm.group(1)
        pm = re.search(r"^Plural-Forms:\s*(.+)$", hs, re.M)
        if pm:
            rules[locale] = pm.group(1)
    out = []
    for e in entries:
        if e is header:
            continue
        plural = "msgid_plural" in e
        forms = [e.get("msgstr_forms", {}).get(i, "") for i in
                 range(max(e.get("msgstr_forms", {0: ""}).keys()) + 1)] if plural \
            else [e.get("msgstr", "")]
        if "fuzzy" in e.get("flags", set()):
            forms = ["" for _ in forms]
            e["fuzzy"] = True
        out.append({"key": e["msgid"], "context": e.get("msgctxt", ""), "line": e.get("line"),
                    "source": e["msgid"], "source_plural": e.get("msgid_plural"),
                    "plural": plural, "fuzzy": e.get("fuzzy", False),
                    "forms": {} if template else {locale: forms}})
    return {"format": "pot" if template else "po", "locales": [] if template else [locale],
            "entries": out, "rules": rules, "has_source": True}, problems


def check_table(path, table, want_locales, max_exp, max_items, min_width=0, allow=()):
    res = {"file": path, "format": table["format"], "locales": table["locales"],
           "keys": len(table["entries"]), "missing": {}, "missing_plural_forms": [],
           "fuzzy": [], "duplicates": [], "placeholder_mismatch": [], "expansion_risk": []}
    seen = set()
    locales = [l for l in table["locales"] if not want_locales or l in want_locales]
    for e in table["entries"]:
        ident = (e["key"], e["context"])
        if ident in seen:
            res["duplicates"].append({"key": e["key"], "context": e["context"], "line": e["line"]})
        seen.add(ident)
        if e.get("fuzzy"):
            res["fuzzy"].append(e["key"])
        src = e["source"]
        for loc in locales:
            forms = e["forms"].get(loc, [""])
            if not forms or not forms[0].strip():
                res["missing"].setdefault(loc, []).append(e["key"])
                continue
            if e["plural"]:
                want = expected_forms(loc, table["rules"])
                have = sum(1 for f in forms[:want] if f.strip())
                if have < want:
                    res["missing_plural_forms"].append(
                        {"key": e["key"], "locale": loc, "have": have, "want": want})
            if src is None:
                continue
            sp, sb = placeholders(src)
            if e["plural"] and e["source_plural"]:
                pp, pb = placeholders(e["source_plural"])
                allowed_p, allowed_b = set(sp) | set(pp), set(sb) | set(pb)
                for n, f in enumerate(forms):
                    if not f.strip():
                        continue
                    fp, fb = placeholders(f)
                    extra = sorted((set(fp) - allowed_p) | (set(fb) - allowed_b))
                    if extra:
                        res["placeholder_mismatch"].append(
                            {"key": e["key"], "locale": loc, "form": n, "extra": extra,
                             "source": src, "translation": f})
            else:
                fp, fb = placeholders(forms[0])
                if fp != sp or fb != sb:
                    res["placeholder_mismatch"].append(
                        {"key": e["key"], "locale": loc, "source_placeholders": sp + sb,
                         "translation_placeholders": fp + fb, "source": src,
                         "translation": forms[0]})
            sw = width(src)
            if sw < min_width or e["key"] in allow:
                continue  # short labels and reviewed keys: expansion is no layout risk
            for f in forms:
                if f.strip() and sw:
                    ratio = width(f) / sw
                    if ratio > max_exp:
                        res["expansion_risk"].append(
                            {"key": e["key"], "locale": loc, "ratio": round(ratio, 2),
                             "source_width": sw, "translated_width": width(f), "text": f})
                        break
    res["expansion_risk"].sort(key=lambda r: -r["ratio"])
    if not table["has_source"]:
        res["note"] = "no source-locale column: placeholder and expansion checks skipped"
    for k in ("missing_plural_forms", "fuzzy", "duplicates", "placeholder_mismatch",
              "expansion_risk"):
        res[k + "_count"] = len(res[k])
        res[k] = res[k][:max_items]
    res["missing_count"] = {loc: len(v) for loc, v in res["missing"].items()}
    res["missing"] = {loc: v[:max_items] for loc, v in res["missing"].items()}
    return res


# ---------------------------------------------------------------- main

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--src", nargs="*", default=[], help="source files, dirs or globs")
    p.add_argument("--tables", nargs="*", default=[], help="CSV / PO / POT files or globs")
    p.add_argument("--source-locale", default="en")
    p.add_argument("--locales", default="", help="comma list of locales that must be complete")
    p.add_argument("--max-expansion", type=float, default=1.4)
    p.add_argument("--fail-on-expansion", action="store_true")
    p.add_argument("--expansion-min-width", type=int, default=0,
                   help="skip the expansion check for sources narrower than N (short labels)")
    p.add_argument("--expansion-allow", default="",
                   help="keys whose expansion was reviewed: comma list or @file (one per line)")
    p.add_argument("--key-pattern", default=DEFAULT_KEY_PATTERN)
    p.add_argument("--delimiter", default=",")
    p.add_argument("--max-items", type=int, default=100)
    args = p.parse_args(argv)
    if not args.src and not args.tables:
        p.error("give --src and/or --tables")
    want = [l.strip() for l in args.locales.split(",") if l.strip()]
    if args.expansion_allow.startswith("@"):
        with open(args.expansion_allow[1:], encoding="utf-8") as fh:
            allow_keys = {line.strip() for line in fh if line.strip()}
    else:
        allow_keys = {k.strip() for k in args.expansion_allow.split(",") if k.strip()}
    key_re = re.compile(args.key_pattern)
    report = {"verdict": "pass", "summary": {}, "hardcoded": [], "unknown_keys": [],
              "tables": [], "warnings": []}

    keys, table_problems, all_locales = set(), [], {args.source_locale}
    for f in expand(args.tables, TABLE_EXT):
        if isinstance(f, tuple):
            report["warnings"].append(f"no such table: {f[1]}")
            table_problems.append(f[1])
            continue
        if f.lower().endswith(".csv"):
            table, problems = read_csv_table(f, args.delimiter.encode().decode("unicode_escape"),
                                             args.source_locale)
        else:
            table, problems = read_po(f, args.source_locale)
        if table is None:
            report["tables"].append({"file": f, "problems": problems})
            table_problems.append(f)
            continue
        all_locales.update(table["locales"])
        for e in table["entries"]:
            keys.add(e["key"])
            if e.get("source"):
                keys.add(e["source"])
        if table["format"] == "pot":
            report["tables"].append({"file": f, "format": "pot", "keys": len(table["entries"])})
            continue
        res = check_table(f, table, want, args.max_expansion, args.max_items,
                          args.expansion_min_width, allow_keys)
        if problems:
            res["problems"] = problems
            table_problems.append(f)
        report["tables"].append(res)

    if args.src:
        hits, warnings = scan_sources(expand(args.src, SRC_EXT))
        report["warnings"] += warnings
        for h in hits:
            value = h["text"]
            if not value.strip() or not needs_translation(value) and not key_re.fullmatch(value):
                continue
            if value in keys:
                continue
            if key_re.fullmatch(value):
                if args.tables:
                    report["unknown_keys"].append(h)
                continue
            report["hardcoded"].append(h)

    s = report["summary"]
    s["hardcoded"] = len(report["hardcoded"])
    s["unknown_keys"] = len(report["unknown_keys"])
    tabs = [t for t in report["tables"] if "missing_count" in t]
    s["missing"] = sum(sum(t["missing_count"].values()) for t in tabs)
    for k in ("missing_plural_forms", "fuzzy", "duplicates", "placeholder_mismatch",
              "expansion_risk"):
        s[k] = sum(t[k + "_count"] for t in tabs)
    s["missing_locales"] = [l for l in want if l not in all_locales] if args.tables else []
    s["table_problems"] = len(table_problems)
    failed = (s["hardcoded"] or s["unknown_keys"] or s["missing"] or s["missing_plural_forms"]
              or s["fuzzy"] or s["duplicates"] or s["placeholder_mismatch"]
              or s["missing_locales"] or s["table_problems"]
              or (args.fail_on_expansion and s["expansion_risk"]))
    report["verdict"] = "fail" if failed else "pass"
    report["hardcoded"] = report["hardcoded"][:args.max_items]
    report["unknown_keys"] = report["unknown_keys"][:args.max_items]
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(report, indent=1, ensure_ascii=False))
    sys.exit(0 if report["verdict"] == "pass" else 1)


if __name__ == "__main__":
    main()
