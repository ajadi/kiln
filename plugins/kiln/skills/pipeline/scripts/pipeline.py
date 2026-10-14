"""Kiln production pipeline state: phases, gates, decisions, game-first warnings.

Run from the project root (normal Python, stdlib only):

  python pipeline.py init                          # create production/PIPELINE.md from the template
  python pipeline.py status [--full]               # current phase, open gates, warnings, last decisions
  python pipeline.py tick "<gate text>" [--by user|agent|proxy] [--note "..."]
  python pipeline.py skip "<gate text>" --reason "..."
  python pipeline.py block "<gate text>" --reason "..."
  python pipeline.py reopen <phase number>         # uncheck a phase's gates (going back is normal)
  python pipeline.py decide "<decision>" --options "a / b / c" --by user|agent|proxy --why "..."

PIPELINE.md format (never delete gates; reopening is how you go back):

  ## Phase 3 — Look-dev
  files: design/ART_BIBLE.md, scenes/lookdev/lookdev.tscn
  - [ ] Art bible filled — check: filled:design/ART_BIBLE.md
  - [ ] User approved the look-dev frame — user
  - [x] Grayscale value check done — manual ✓ 2026-10-06 (agent)

Check kinds (cross-platform, no shell):
  exists:<path>              file or folder exists
  filled:<path>              file exists, has content, no <placeholder> left
  glob:<pattern>>=N          at least N files match (e.g. glob:scenes/gyms/*_gym.tscn>=3)
  grep:<regex>@<path>        regex found in file
  nogrep:<regex>@<path>      file exists and regex not found (e.g. no mvp row still open)
  lines:<path>>=N            file has at least N non-empty lines
  noplaceholder:<glob>       no <...> placeholders in matching files
"""

import argparse
import datetime
import glob as globlib
import html
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                                "hooks"))
import kiln_hooklib as k  # noqa: E402

PIPELINE = os.path.join("production", "PIPELINE.md")
DECISIONS = os.path.join("memory", "decisions.md")
PLAYTESTS = os.path.join("production", "PLAYTESTS.md")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates",
                        "PIPELINE.md")
PLACEHOLDER = re.compile(r"<[a-z][^<>\n]{0,60}>")  # <placeholder>, not HTML/xml tags with attrs
GATE = re.compile(r"^(\s*- \[)([ x])(\]\s*)(.*?)(\s+—\s+(check:\s*(.+?)|user|manual))?"
                  r"((?:\s+(?:✓|SKIP:|BLOCKED:|PROXY|REGRESSED|REOPENED).*)?)$")
TODAY = datetime.date.today().isoformat()


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def editor_lines(now=None):
    """Who holds each editor and who waits for it (.kiln/locks.json, .kiln/queue.json)."""
    now = now or time.time()

    def load(name):
        try:
            with open(os.path.join(".kiln", name), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    locks, queues = load("locks.json"), load("queue.json")
    out = []
    for res in sorted(set(locks) | set(queues)):
        held = locks.get(res)
        line = f"{res}: " + (f"{held.get('role')} for {int((now - held.get('since', now)) // 60)}"
                             " min" if held else "free")
        waiting = [w for w in queues.get(res, []) if now - w.get("ts", 0) < 300]
        if waiting:
            line += "; waiting: " + ", ".join(
                f"{w.get('role')} {int((now - w.get('since', now)) // 60)} min" for w in waiting)
        out.append(line)
    return out


def running_agents(now=None):
    """Lines for .kiln/agents.json (written by the Kiln hooks): role, id, run time, last tool
    call. A long silence means the agent may have died (usage limit, killed session)."""
    try:
        with open(os.path.join(".kiln", "agents.json"), encoding="utf-8") as fh:
            agents = json.load(fh)
    except (OSError, ValueError):
        return []
    now = now or time.time()
    out = []
    for aid, a in sorted(agents.items(), key=lambda kv: kv[1].get("since", 0)):
        mins = int((now - a.get("since", now)) // 60)
        line = f"{a.get('role', '?')} ({aid}) running {mins} min"
        if a.get("last"):
            idle = int((now - a["last"]) // 60)
            line += f", last call {idle} min ago: {a.get('last_tool', '?')}"
            if idle >= 20:
                line += " - silent; check it is alive before waiting on it"
        out.append(line)
    return out


def has_placeholder(path):
    text = read(path)
    if text is None:
        return False
    text = re.sub(r"```.*?```", "", text, flags=re.S)       # ignore code blocks
    text = re.sub(r"`[^`\n]*`", "", text)                   # inline code: notation like `kiln:<role>`
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)      # and comments
    return bool(PLACEHOLDER.search(text))


# engine caches and third-party code: never walked (Unity Library alone can hold 100k+ files)
SKIP_DIRS = {".git", ".godot", ".import", "addons", "Library", "Temp", "Obj", "Logs",
             "UserSettings", "Packages", "Intermediate", "Saved", "DerivedDataCache", "Binaries",
             "Plugins", "node_modules", ".venv", "venv", "__pycache__", ".kiln", "build", "dist"}
CODE_EXT = {"godot": (".gd",), "unity": (".cs",), "unreal": (".cpp", ".h")}
ENGINE_GATES = {
    "godot": {"{{LOOKDEV_CHECK}}": "glob:scenes/lookdev/*.tscn>=1", "{{EDITOR}}": "Godot editor"},
    "unity": {"{{LOOKDEV_CHECK}}": "glob:Assets/_Project/Scenes/LookDev*.unity>=1",
              "{{EDITOR}}": "Unity editor"},
    "unreal": {"{{LOOKDEV_CHECK}}": "glob:Content/*/Maps/LookDev*.umap>=1",
               "{{EDITOR}}": "Unreal editor"},
}


def engine():
    value = manifest_value("engine", "godot")
    return value if value in CODE_EXT else "godot"


def project_files(exts):
    for dirpath, dirnames, filenames in os.walk("."):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(exts):
                yield os.path.relpath(os.path.join(dirpath, name))


def run_check(spec):
    kind, _, arg = spec.partition(":")
    if kind == "exists":
        return os.path.exists(arg)
    if kind == "filled":
        text = read(arg)
        return bool(text and text.strip()) and not has_placeholder(arg)
    if kind == "glob":
        pattern, _, n = arg.rpartition(">=")
        return len(globlib.glob(pattern, recursive=True)) >= int(n or 1)
    if kind == "grep":
        regex, _, path = arg.rpartition("@")
        text = read(path)
        return bool(text and re.search(regex, text, re.M))
    if kind == "nogrep":
        regex, _, path = arg.rpartition("@")
        text = read(path)
        return text is not None and not re.search(regex, text, re.M)
    if kind == "lines":
        path, _, n = arg.rpartition(">=")
        text = read(path) or ""
        return sum(1 for line in text.splitlines() if line.strip()) >= int(n)
    if kind == "noplaceholder":
        files = globlib.glob(arg, recursive=True)
        return bool(files) and not any(has_placeholder(p) for p in files)
    return False


def parse(text):
    phases, current = [], None
    for i, line in enumerate(text.splitlines()):
        m = re.match(r"^##\s+Phase\s+(\d+)\s+—\s+(.+)$", line)
        if m:
            current = {"num": int(m.group(1)), "name": m.group(2).strip(), "files": [],
                       "gates": []}
            phases.append(current)
            continue
        if current is None:
            continue
        if line.startswith("files:"):
            current["files"] = [f.strip() for f in line[6:].split(",") if f.strip()]
            continue
        g = GATE.match(line)
        if g:
            tail = g.group(8) or ""
            current["gates"].append({
                "line": i, "done": g.group(2) == "x", "text": g.group(4).strip(),
                "kind": "check" if g.group(7) else (g.group(5) or "").strip(" —") or "manual",
                "check": g.group(7), "skip": "SKIP:" in tail, "blocked": "BLOCKED:" in tail,
            })
    return phases


def set_gate(text, gate, mark, suffix):
    lines = text.splitlines()
    line = re.sub(r"\s+(✓|SKIP:|BLOCKED:|PROXY|REGRESSED|REOPENED).*$", "", lines[gate["line"]])
    line = re.sub(r"^(\s*- \[)[ x](\])", r"\1" + mark + r"\2", line)
    lines[gate["line"]] = line + (" " + suffix if suffix else "")
    return "\n".join(lines) + "\n"


def find_gate(phases, needle):
    hits = [g for p in phases for g in p["gates"] if needle.lower() in g["text"].lower()]
    if len(hits) != 1:
        sys.exit(f"gate '{needle}': {len(hits)} matches — be more specific")
    return hits[0]


def git(*args):
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def balance_warnings():
    """Game-first: warn when work drifts to docs/tests/tools instead of the game."""
    warnings = []
    log = git("log", "-8", "--name-only", "--pretty=format:@@")
    streak = 0
    for commit in [c for c in log.split("@@") if c.strip()]:
        files = [f for f in commit.strip().splitlines() if f.strip()]
        game = [f for f in files if not re.search(
            r"(^|/)(tests?|docs?|tools|memory|tasks|production|design)/|\.md$", f)]
        if game:
            break
        streak += 1
    if streak >= 3:
        warnings.append(f"FOCUS ON THE GAME: last {streak} commits touched no game files")
    code = test = 0
    for path in project_files(CODE_EXT.get(engine(), (".gd",))):
        n = sum(1 for _ in open(path, encoding="utf-8", errors="ignore"))
        if re.search(r"(^|[\\/])tests?[\\/]", path):
            test += n
        else:
            code += n
    if code + test > 400 and test / (code + test) > 0.35:
        warnings.append(f"TOO MANY TESTS: {test} test lines vs {code} game code lines")
    docs = sum(sum(1 for _ in open(p, encoding="utf-8", errors="ignore"))
               for p in project_files((".md",))
               if not re.match(r"(production|memory|tasks|design|\.claude)[\\/]", p))
    if docs > max(800, code // 2):
        warnings.append(f"TOO MUCH DOCUMENTATION: {docs} doc lines vs {code} code lines")
    return warnings


def last_rows(path, n, prefix="|"):
    text = read(path) or ""
    rows = [l for l in text.splitlines() if l.startswith(prefix) and not re.match(r"^\|\s*[-#]", l)]
    return rows[-n:]


def asset_status():
    """kind=assets: no phases; the backlog's asset tasks and where they stand."""
    lines = [l.strip() for l in (read("backlog.md") or "").splitlines()
             if re.match(r"^\s*- \[[ x~]\]", l)]
    print("asset mode (kind=assets): no game pipeline - assets are tasks in backlog.md")
    for line in lines or ["(no asset tasks yet: /kiln:model, /kiln:sprites, /kiln:track)"]:
        print(" ", line)


def status(full):
    if kind() == "assets":
        return asset_status()
    text = read(PIPELINE)
    if text is None:
        sys.exit("no production/PIPELINE.md — run: python pipeline.py init")
    phases = parse(text)
    changed = False
    for phase in phases:
        for gate in phase["gates"]:
            if gate["kind"] == "check" and (not gate["done"] or full) and not gate["skip"]:
                ok = run_check(gate["check"])
                if ok and not gate["done"]:
                    text = set_gate(text, gate, "x", f"✓ {TODAY} (auto)")
                    gate["done"] = changed = True
                elif not ok and gate["done"] and full:
                    text = set_gate(text, gate, " ", f"REGRESSED {TODAY}")
                    gate["done"], changed = False, True
    if changed:
        write(PIPELINE, text)
    current = None
    for phase in phases:
        open_gates = [g for g in phase["gates"] if not g["done"] and not g["skip"]]
        unfilled = [f for f in phase["files"] if has_placeholder(f)]
        phase["open"], phase["unfilled"] = open_gates, unfilled
        if current is None and (open_gates or unfilled):
            current = phase
    print("PIPELINE")
    for phase in phases:
        total = len(phase["gates"])
        done = total - len(phase["open"])
        marker = ">>" if phase is current else "  "
        print(f"{marker} Phase {phase['num']} — {phase['name']}: {done}/{total} gates")
    if current:
        print(f"\nNOW: Phase {current['num']} — {current['name']}")
        for g in current["open"]:
            tag = "BLOCKED " if g["blocked"] else ""
            how = g["check"] or g["kind"]
            print(f"  [ ] {tag}{g['text']}  ({how})")
        for f in current["unfilled"]:
            print(f"  placeholder left in {f}")
    else:
        print("\nAll phases closed.")
    for w in balance_warnings():
        print("WARNING:", w)
    editors = editor_lines()
    if editors:
        print("\nEditors:")
        for line in editors:
            print(" ", line)
    agents = running_agents()
    if agents:
        print("\nRunning agents (no SubagentStop yet):")
        for line in agents:
            print(" ", line)
    decisions = last_rows(DECISIONS, 3)
    if decisions:
        print("\nLast decisions:")
        for row in decisions:
            print(" ", row[:160])
    playtests = [l for l in (read(PLAYTESTS) or "").splitlines() if l.startswith("## PT-")]
    if playtests:
        print("\nLast playtest:", playtests[-1][3:])
    if os.path.exists(os.path.join(".kiln", "autopilot")):
        print("\nAutopilot: ON")
    dirty = git("status", "--porcelain").splitlines()
    if dirty:
        print(f"\nUncommitted files: {len(dirty)}")


def manifest_value(key, default):
    """A manifest key as the hooks read it (k.read_manifest: `key = value` works, last wins)."""
    return (k.read_manifest(".") or {}).get(key) or default


def kind():
    return manifest_value("kind", "game")


def gates(task_id, suggest):
    """`## gates` table for a task (--suggest), or exit 1 listing the roles still owed."""
    text = k.task_text(".", task_id)
    if not text:
        print(f"{task_id}: no task file in tasks/ or tasks/archive/")
        return 1
    if suggest:
        declared = k.declared_touches(text)
        if declared is not None:
            print(f"touches: {', '.join(declared) or 'none'} (declared)")
        else:
            guess = k.guess_touches(text)
            print(f"touches: {', '.join(guess)} (guessed - confirm and write this line into "
                  "the spec)" if guess else "touches: (none guessed) - write the line anyway, "
                  "`touches: none` if nothing applies")
        print("## gates\n| role | why | verdict |\n|---|---|---|")
        for role, why in k.suggested_gates(text, kind(), manifest_value("perf_gate", "on")):
            print(f"| {role} | {why} | |")
        return 0
    if k.gate_rows(text) is None:
        print(f"{task_id}: no `## gates` table; add one with `pipeline.py gates {task_id} "
              "--suggest` (plan skill)")
        return 1
    missing = k.missing_gates(text, kind(), manifest_value("perf_gate", "on"))
    if k.declared_touches(text) is None:
        print(f"{task_id}: no touches: line - only the route table is enforced; run --suggest "
              "and write the line")
    if missing:
        for role in missing:
            print(f"missing: {role}")
        print(f"{task_id}: {len(missing)} gate(s) open. Run the role, or record "
              "`SKIP: <reason, decision #>` in its row.")
        return 1
    print(f"{task_id}: every gate has a verdict or a recorded skip")
    return 0


PAGE_CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--mute:#6b6a65;--line:#e4e1d8;--card:#fff;--ok:#2f7d4f;--bad:#b4472f;--warn:#a2700f}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#ecebe6;--mute:#9b9a93;--line:#34332f;--card:#1f1e1b;--ok:#6cc08b;--bad:#ef8a6f;--warn:#e0b25a}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1000px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:24px;margin:0 0 4px} h2{font-size:17px;margin:28px 0 8px}
.mute{color:var(--mute)} section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:12px 0}
table{border-collapse:collapse;width:100%} td,th{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.ok{color:var(--ok)} .bad{color:var(--bad)} .warn{color:var(--warn)} code{font-size:13px}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden;min-width:80px}.bar i{display:block;height:100%;background:var(--ok)}
pre{white-space:pre-wrap;margin:0;font-size:13px}
"""


def page(out_path):
    """A self-contained status page for a busy user: phases, tasks and their open gates, who is
    working, editors, decisions taken for the user (PROXY), the last autoplay night."""
    esc = html.escape
    manifest = read("manifest.md") or ""
    name = (re.search(r"^project_name=(.*)$", manifest, re.M) or [None, "project"])[1]
    parts = [f"<h1>{esc(name)}</h1><p class='mute'>Kiln status · {esc(manifest_value('kind', 'game'))}"
             f" · generated {datetime.datetime.now():%Y-%m-%d %H:%M}</p>"]
    phases = parse(read(PIPELINE) or "")
    rows = []
    for p in phases:
        total = len(p["gates"])
        done = sum(1 for g in p["gates"] if g["done"] or g["skip"])
        pct = int(100 * done / total) if total else 100
        rows.append(f"<tr><td>Phase {p['num']} — {esc(p['name'])}</td><td>{done} / {total}</td>"
                    f"<td><div class='bar'><i style='width:{pct}%'></i></div></td></tr>")
    current = next((p for p in phases if any(not g["done"] and not g["skip"] for g in p["gates"])),
                   None)
    open_gates = "".join(f"<li>{esc(g['text'])}</li>" for g in current["gates"]
                         if not g["done"] and not g["skip"]) if current else ""
    parts.append("<h2>Pipeline</h2><section><table>" + "".join(rows) + "</table>"
                 + (f"<p><b>Now: Phase {current['num']}</b></p><ul>{open_gates}</ul>"
                    if current else "<p class='ok'>All phases closed.</p>") + "</section>")
    backlog = read("backlog.md") or ""
    items = re.findall(r"^\s*- \[([ x~X])\]\s*(TASK-\d+)\s*(.*)$", backlog, re.M)
    done_n = sum(1 for m, _, _ in items if m in "xX")
    trs = []
    for mark, tid, rest in items:
        state = {"x": "done", "X": "done", "~": "in progress", " ": "to do"}[mark]
        text = k.task_text(".", tid)
        gates = ""
        if text and mark not in "xX":
            missing = k.missing_gates(text, manifest_value("kind", "game"),
                                      manifest_value("perf_gate", "on"))
            gates = (f"<span class='warn'>owed: {esc(', '.join(missing))}</span>" if missing
                     else "<span class='ok'>gates complete</span>")
        trs.append(f"<tr><td>{tid}</td><td>{esc(rest.split('·')[0].strip())}</td>"
                   f"<td class='{'ok' if state == 'done' else ''}'>{state}</td><td>{gates}</td></tr>")
    parts.append(f"<h2>Tasks <span class='mute'>{done_n} / {len(items)} done</span></h2>"
                 "<section><table>" + "".join(trs) + "</table></section>")
    agents = running_agents()
    editors = editor_lines()
    parts.append("<h2>Working now</h2><section>"
                 + ("<ul>" + "".join(f"<li>{esc(a)}</li>" for a in agents) + "</ul>"
                    if agents else "<p class='mute'>No agents running.</p>")
                 + ("<p><b>Editors</b></p><ul>" + "".join(f"<li>{esc(e)}</li>" for e in editors)
                    + "</ul>" if editors else "") + "</section>")
    proxy = [l for l in (read(DECISIONS) or "").splitlines()
             if re.match(r"^\|\s*\d+\s*\|", l) and re.search(r"\|\s*proxy\s*\|", l, re.I)]
    cells = [[c.strip() for c in l.strip().strip("|").split("|")] for l in proxy]
    parts.append("<h2>Decided for you</h2><section>"
                 + ("<table><tr><th>#</th><th>date</th><th>decision</th><th>options</th>"
                    "<th>why</th></tr>" + "".join(
                        f"<tr><td>{esc(c[0])}</td><td>{esc(c[1])}</td><td>{esc(c[3])}</td>"
                        f"<td>{esc(c[4])}</td><td>{esc(c[6] if len(c) > 6 else '')}</td></tr>"
                        for c in cells[-30:]) + "</table><p class='mute'>Say \"redo #N\" to "
                    "change one.</p>" if cells else "<p class='mute'>None.</p>") + "</section>")
    reports = sorted(globlib.glob(os.path.join("production", "autoplay", "*", "REPORT.md")),
                     key=os.path.getmtime)
    if reports:
        head = "\n".join((read(reports[-1]) or "").splitlines()[:14])
        parts.append(f"<h2>Last autoplay night</h2><section><p class='mute'>{esc(reports[-1])}</p>"
                     f"<pre>{esc(head)}</pre></section>")
    slot = read(os.path.join("production", "MEASUREMENT_SLOT.md"))
    if slot and slot.strip():
        n = len([l for l in slot.splitlines() if l.strip().startswith(("-", "|"))])
        parts.append(f"<h2>Waiting for your screen</h2><section><p>{n} on-screen check line(s) in "
                     "production/MEASUREMENT_SLOT.md.</p></section>")
    doc = ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
           f"content='width=device-width,initial-scale=1'><title>{esc(name)} status</title>"
           f"<style>{PAGE_CSS}</style></head><body><main>{''.join(parts)}</main></body></html>\n")
    write(out_path, doc)
    print(f"wrote {out_path}")
    return 0


def report_rule_section():
    """The "## Problem reports" section of the project rules template, up to the next heading."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "templates",
                        "project", "CLAUDE.md")
    m = re.search(r"^## Problem reports.*?(?=^## )", read(path) or "", re.M | re.S)
    return m.group(0) if m else None


def migrate():
    """Bring a project planned by an older Kiln to the current task format: open task files
    (tasks/*.md, not the archive) get a `touches:` line (guessed, marked for confirmation) and a
    `## gates` table when they have none; manifest.md gets the policy keys it lacks, with their
    defaults. Never rewrites an existing line or table."""
    changed = []
    for path in sorted(globlib.glob(os.path.join("tasks", "*.md"))):
        text = read(path) or ""
        if not re.search(r"^## spec", text, re.M):
            continue
        new = text
        notes = []
        if k.declared_touches(new) is None:
            guess = k.guess_touches(new)
            line = (f"touches: {', '.join(guess) or 'none'}\n"
                    "touches_source: guessed by migrate - confirm")
            anchor = re.search(r"^(paths|role|type):.*$", new, re.M)
            spec_end = max((m.end() for m in re.finditer(r"^(type|role|batch|paths|depends_on|"
                                                          r"refs|complexity|effort):.*$", new,
                                                          re.M)), default=None)
            at = spec_end if spec_end is not None else (anchor.end() if anchor else len(new))
            new = new[:at] + "\n" + line + new[at:]
            notes.append(f"touches: {', '.join(guess) or 'none'} (guessed)")
        if k.gate_rows(new) is None:
            rows = "\n".join(f"| {r} | {why} | |" for r, why in
                             k.suggested_gates(new, kind(), manifest_value("perf_gate", "on")))
            table = "## gates\n| role | why | verdict |\n|---|---|---|\n" + rows + "\n"
            nxt = re.search(r"^## (?!spec)", new, re.M)
            new = new[:nxt.start()] + table + new[nxt.start():] if nxt else \
                new.rstrip("\n") + "\n" + table
            notes.append("gates table added")
        if new != text:
            write(path, new)
            changed.append(f"{path}: " + "; ".join(notes))
    manifest = read("manifest.md") or ""
    plugin_json = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                               ".claude-plugin", "plugin.json")
    try:
        with open(plugin_json, encoding="utf-8") as fh:
            version = json.load(fh)["version"]
    except (OSError, ValueError, KeyError):
        version = None
    if manifest and version and f"framework_version={version}" not in manifest:
        if re.search(r"^\s*framework_version\s*=", manifest, re.M):
            manifest = re.sub(r"^\s*framework_version\s*=.*$", f"framework_version={version}",
                              manifest, flags=re.M)
        else:
            manifest = re.sub(r"^(\s*framework\s*=\s*kiln\s*)$",
                              lambda m: f"{m.group(1)}\nframework_version={version}", manifest,
                              count=1, flags=re.M)
        write("manifest.md", manifest)
        changed.append(f"manifest.md: framework_version={version}")
    have = k.read_manifest(".") or {}
    missing = [f"{key}={value}" for key, value in k.DEFAULT_POLICY.items() if key not in have]
    if missing and manifest:
        write("manifest.md", manifest.rstrip("\n") + "\n" + "\n".join(missing) + "\n")
        changed.append("manifest.md: added " + ", ".join(m.split("=")[0] for m in missing))
    rules = next((f for f in ("AGENTS.md", "CLAUDE.md")
                  if "## Rules that matter most" in (read(f) or "")), None)
    section = report_rule_section()
    if rules and section and "## Problem reports" not in read(rules):
        text = read(rules)
        at = text.find("## Kiln settings")
        text = text[:at] + section + text[at:] if at >= 0 else text.rstrip("\n") + "\n\n" + section
        write(rules, text)
        changed.append(f"{rules}: problem report rule added")
    if not changed:
        print("nothing to migrate")
        return 0
    print("migrated:")
    for line in changed:
        print(" ", line)
    print("Confirm every guessed touches: line (then delete its touches_source line), and fill "
          "or SKIP the new gates rows.")
    return 0


REPORT_HEADER = ("# Kiln problem reports\n\n"
                 "Problems with Kiln itself, written while working (rules) or by the user "
                 "(/kiln:report).\n\n"
                 "| # | date | who | area | what happened | suggestion | status |\n"
                 "|---|---|---|---|---|---|---|\n")


DECISIONS_HEADER = ("# Decisions\n\n| # | date | phase | decision | options | by | why |\n"
                    "|---|---|---|---|---|---|---|\n")


def append_row(path, cells, header=None, label=None):
    """Append `| <next number> | <cells> |` to a numbered markdown table, under a lock file so two
    agents never take the same number (g2: two agents wrote the same report row number)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lock = path + ".lock"
    for _ in range(100):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() - os.path.getmtime(lock) > 30:
                os.remove(lock)  # left by a killed writer
            time.sleep(0.1)
    else:
        print(f"{path}: locked by another writer")
        return 1
    try:
        text = read(path) or ""
        if not text and os.path.basename(path) == "kiln-report.md":
            text = REPORT_HEADER
        if header and "| # |" not in text:
            table = header[header.index("| # |"):]
            text = text.rstrip("\n") + "\n\n" + table if text.strip() else header
        numbers = [int(n) for n in re.findall(r"^\|\s*(\d+)\s*\|", text, re.M)]
        n = max(numbers, default=0) + 1
        text = text.rstrip("\n") + f"\n| {n} | {cells.strip().strip('|').strip()} |\n"
        write(path, text)
    finally:
        os.close(fd)
        os.remove(lock)
    print(label.format(n=n) if label else f"row {n} appended to {path}")
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    s = sub.add_parser("status"); s.add_argument("--full", action="store_true")
    for name in ("tick", "skip", "block"):
        p = sub.add_parser(name); p.add_argument("gate")
        p.add_argument("--by", default="agent", choices=["user", "agent", "proxy"])
        p.add_argument("--note", default=""); p.add_argument("--reason", default="")
    r = sub.add_parser("reopen"); r.add_argument("phase", type=int)
    d = sub.add_parser("decide"); d.add_argument("decision")
    d.add_argument("--options", default=""); d.add_argument("--why", default="")
    d.add_argument("--by", default="agent", choices=["user", "agent", "proxy"])
    g = sub.add_parser("gates"); g.add_argument("task")
    g.add_argument("--suggest", action="store_true")
    w = sub.add_parser("row"); w.add_argument("file"); w.add_argument("cells")
    sub.add_parser("migrate")
    pg = sub.add_parser("page"); pg.add_argument("--out", default=os.path.join("production", "STATUS.html"))
    a = ap.parse_args()

    if a.cmd == "gates":
        sys.exit(gates(a.task, a.suggest))
    if a.cmd == "page":
        sys.exit(page(a.out))
    if a.cmd == "migrate":
        sys.exit(migrate())
    if a.cmd == "row":
        sys.exit(append_row(a.file, a.cells))

    if a.cmd == "init":
        if kind() == "assets":
            sys.exit("kind=assets: asset mode has no game pipeline (no phases or gates to init)")
        if os.path.exists(PIPELINE):
            sys.exit("production/PIPELINE.md exists — not overwriting")
        text = read(TEMPLATE)
        for key, value in ENGINE_GATES[engine()].items():
            text = text.replace(key, value)
        write(PIPELINE, text)
        print("created", PIPELINE, "for", engine())
    elif a.cmd == "status":
        status(a.full)
    elif a.cmd in ("tick", "skip", "block"):
        text = read(PIPELINE)
        gate = find_gate(parse(text), a.gate)
        if a.cmd == "tick":
            by = a.by  # kept as given: a real user answer during autopilot is the user's
            mark, suffix = "x", f"✓ {TODAY} ({by})" + (f" {a.note}" if a.note else "")
            if by == "proxy":
                suffix = f"PROXY {TODAY}" + (f" {a.note}" if a.note else "")
        elif a.cmd == "skip":
            mark, suffix = "x", f"SKIP: {a.reason or 'no reason given'} ({TODAY})"
        else:
            mark, suffix = " ", f"BLOCKED: {a.reason or 'no reason given'} ({TODAY})"
        write(PIPELINE, set_gate(text, gate, mark, suffix))
        print(a.cmd, "->", gate["text"])
    elif a.cmd == "reopen":
        text = read(PIPELINE)
        for phase in parse(text):
            if phase["num"] == a.phase:
                for gate in phase["gates"]:
                    text = set_gate(text, gate, " ", f"REOPENED {TODAY}")
        write(PIPELINE, text)
        print("reopened phase", a.phase)
    elif a.cmd == "decide":
        by = a.by  # kept as given (g2: real user decisions on autopilot were marked proxy)
        phases = parse(read(PIPELINE) or "")
        phase = next((f"P{p['num']}" for p in phases
                      if any(not g["done"] and not g["skip"] for g in p["gates"])), "-")
        # numbered under the row lock: parallel deciders never share a number
        sys.exit(append_row(DECISIONS, f"{TODAY} | {phase} | {a.decision} | {a.options} | {by} | "
                            f"{a.why}", header=DECISIONS_HEADER, label="decision #{n} recorded (" + by + ")"))


if __name__ == "__main__":
    main()
