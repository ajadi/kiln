"""Licence registry: everything the project uses that someone else made or a model generated,
with its licence, attribution and whether it ships. Writes production/LICENSES.md.

  python licenses.py build        # scan the project, write production/LICENSES.md, exit 1 on risk
  python licenses.py check        # same scan, no write

Sources it reads (paths relative to the project root):
  ref/manifest.csv, tools/audio/refs_manifest.csv      references — analysis only, never ship
  **/sources.json (refs_fetch.py, board folders)        fetched references — never ship
  art/generated/**/provenance.json                       generated assets — ship
  tools/music/LICENSES.md (| item | licence | source | attribution |)   music sources — ship
  fonts (*.ttf, *.otf, *.woff2) next to a licence file   ship
  Godot addons/*/, Unreal Plugins/*/, Unity Packages/manifest.json      third-party code — ship
  production/licenses-extra.csv (asset,origin,licence,attribution,ships) anything else (store
                                                         purchases, sound packs, contractors)
Risk = a shipping item whose licence is unknown or non-commercial. The Phase 9 gate reads the
table, so keep its columns: | asset | origin | licence | attribution | ships |.
"""

import csv
import datetime
import glob
import json
import os
import re
import sys

SKIP = {".git", ".godot", ".kiln", "Library", "Temp", "Obj", "Logs", "Intermediate", "Saved",
        "DerivedDataCache", "Binaries", "node_modules", ".venv", "__pycache__"}
NC = re.compile(r"(\bnc\b|non-?commercial|research only|evaluation only|by-nc)", re.I)
KNOWN = [(r"\bmit\b", "MIT"), (r"apache", "Apache-2.0"), (r"\bcc0\b|public domain", "CC0"),
         (r"sil open font|\bofl\b", "OFL-1.1"), (r"\bcc[- ]by[- ]sa\b", "CC BY-SA"),
         (r"\bcc[- ]by\b", "CC BY"), (r"\bbsd\b", "BSD"), (r"\bgpl", "GPL"), (r"\blgpl", "LGPL"),
         (r"zlib", "zlib"), (r"unlicense", "Unlicense")]


def walk(pattern_ext):
    for dirpath, dirnames, files in os.walk("."):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for name in files:
            if name.lower().endswith(pattern_ext):
                yield os.path.relpath(os.path.join(dirpath, name)).replace("\\", "/")


def normalise(text):
    text = (text or "").strip()
    if not text:
        return "unknown"
    if NC.search(text):
        return "non-commercial (" + text + ")"
    for pattern, name in KNOWN:
        if re.search(pattern, text, re.I):
            return name if len(text) < 40 else f"{name} ({text[:40]})"
    return text


def licence_file_text(folder):
    for name in os.listdir(folder):
        if re.match(r"(licen[cs]e|copying|ofl)(\.\w+)?$", name, re.I):
            try:
                return open(os.path.join(folder, name), encoding="utf-8", errors="ignore").read(4000)
            except OSError:
                return ""
    return ""


def from_licence_text(text):
    if not text:
        return "unknown"
    for pattern, name in KNOWN:
        if re.search(pattern, text, re.I):
            return name
    return "see licence file"


def scan():
    rows = []
    for path in ("ref/manifest.csv", "tools/audio/refs_manifest.csv"):
        if os.path.isfile(path):
            for r in csv.DictReader(open(path, encoding="utf-8")):
                rows.append([r.get("local_path") or r.get("ref_id", "?"), r.get("source_url", ""),
                             normalise(r.get("licence", "")), r.get("author", ""), "no"])
    for path in walk(("sources.json",)):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for item in data.get("items", []):
            rows.append([os.path.dirname(path) + "/" + item.get("file", "?"), item.get("url", ""),
                         normalise(item.get("licence", "")), item.get("credit", ""), "no"])
    for path in walk(("provenance.json",)):
        try:
            p = json.load(open(path, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append([os.path.dirname(path), f"generated: {p.get('tool', '?')} {p.get('version', '')}",
                     normalise(p.get("licence") or p.get("weights_licence", "")),
                     p.get("attribution", ""), "yes"])
    music = "tools/music/LICENSES.md"
    if os.path.isfile(music):
        for line in open(music, encoding="utf-8"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and line.startswith("|") and not re.match(r"^-+$", cells[0]) \
                    and cells[0].lower() not in ("item", "asset"):
                rows.append([cells[0], cells[2] if len(cells) > 2 else "music",
                             normalise(cells[1]), cells[3] if len(cells) > 3 else "", "yes"])
    for path in walk((".ttf", ".otf", ".woff2")):
        text = licence_file_text(os.path.dirname(path) or ".")
        rows.append([path, "font", from_licence_text(text), "", "yes"])
    for folder in sorted(glob.glob("addons/*/")) + sorted(glob.glob("Plugins/*/")):
        rows.append([folder.replace("\\", "/").rstrip("/"), "third-party engine add-on",
                     from_licence_text(licence_file_text(folder)), "", "yes"])
    if os.path.isfile("Packages/manifest.json"):
        deps = json.load(open("Packages/manifest.json", encoding="utf-8")).get("dependencies", {})
        for name in sorted(deps):
            if not name.startswith("com.unity."):
                rows.append([name, "Unity package", "unknown", "", "yes"])
    extra = "production/licenses-extra.csv"
    if os.path.isfile(extra):
        for r in csv.DictReader(open(extra, encoding="utf-8")):
            rows.append([r.get("asset", "?"), r.get("origin", ""), normalise(r.get("licence", "")),
                         r.get("attribution", ""), (r.get("ships") or "yes").strip().lower()])
    return rows


def risky(rows):
    return [r for r in rows if r[4] == "yes" and (r[2].startswith("unknown")
                                                  or r[2].startswith("non-commercial"))]


def render(rows):
    out = ["# Licences and credits", "",
           f"Generated by licenses.py on {datetime.date.today().isoformat()}. Add what it cannot "
           "see to production/licenses-extra.csv (asset,origin,licence,attribution,ships), then "
           "rebuild.", "", "| asset | origin | licence | attribution | ships |",
           "|---|---|---|---|---|"]
    clean = lambda s: str(s).replace("|", "/").replace("\n", " ")  # noqa: E731
    out += [f"| {' | '.join(clean(c) for c in r)} |" for r in rows]
    credits = sorted({r[3] for r in rows if r[4] == "yes" and r[3]})
    out += ["", "## Credits (attribution required)", ""] + [f"- {c}" for c in credits or ["none"]]
    return "\n".join(out) + "\n"


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "check"
    if cmd not in ("build", "check"):
        print(__doc__)
        return 2
    rows = scan()
    if cmd == "build":
        os.makedirs("production", exist_ok=True)
        with open(os.path.join("production", "LICENSES.md"), "w", encoding="utf-8") as fh:
            fh.write(render(rows))
    bad = risky(rows)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"items": len(rows), "shipping": sum(r[4] == "yes" for r in rows),
                      "risky": [r[:3] for r in bad], "verdict": "fail" if bad else "pass"},
                     indent=1, ensure_ascii=False))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
