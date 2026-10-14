"""Collect the evidence a retrospective needs from a Kiln project — one JSON object on stdout.

  python retro_scan.py [--root .] [--since "YYYY-MM-DD[ HH:MM]"] [--transcript session.jsonl ...]
                       [--subagents <session>/subagents ...]

Sources (each optional; missing ones are reported as absent, not errors):
  .kiln/denials.jsonl   guard denials (the hook library writes one line per denial) — grouped by
                        rule, with roles and example inputs; repeated identical inputs are flagged
  .kiln/hooks.log       hook crashes ("hook error" tracebacks)
  tasks/*.md, tasks/archive/*.md
                        review sections and verdicts per task, rounds, BLOCKED handoffs, user
                        lines in the log (requests and corrections made after the task started),
                        PROXY decisions
  production/PIPELINE.md  gates closed by PROXY
  memory/decisions.md   user and PROXY decisions
  roles                 role coverage over the task files: roles that ran, roles the tasks
                        required (route table + touches) but that never ran, skips with their
                        reasons, Kiln roles never used, what open tasks still owe
  --transcript          Claude Code stream-json (claude -p --output-format stream-json) or session
                        transcript lines: tool calls per tool, tool errors per tool, agents started
                        per type (non-Kiln agents flagged), result cost and turns
  --pitfalls            defect catalogues in the pitfall format (default: the animation skill's
                        references/reads-wrong.md): entries whose "Caught by" is "no check yet",
                        and the user's defect reports in the task logs - each defect no check
                        caught is a candidate for a new check
  --subagents           a session's subagents folder: per role run the effort it ran at, responses,
                        output and thinking tokens (measured, from usage), wall / tool-wait / model
                        minutes — the numbers an effort or model change is judged by
Only entries at or after --since count when they carry a time.
"""

import argparse
import collections
import datetime
import glob
import json
import os
import re
import sys

VERDICT = re.compile(r"^\s*verdict:\s*([A-Z_]+)", re.M)
USER_LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) user\b[^:]*:\s*(.+)$", re.M)
PROXY = re.compile(r"PROXY")


def after(stamp, since):
    return not since or (stamp or "") >= since


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def rule_key(reason):
    reason = re.sub(r"^\[kiln\]\s*", "", reason or "")
    reason = re.sub(r"\S+\.(py|gd|tscn|tres|cs|blend)\b", "<file>", reason)
    reason = re.sub(r"\(for \d+s\)", "(for Ns)", reason)
    return reason[:90]


def scan_denials(root, since):
    text = read(os.path.join(root, ".kiln", "denials.jsonl"))
    if text is None:
        return {"present": False}
    groups = collections.OrderedDict()
    seen_inputs = collections.Counter()
    total = 0
    for line in text.splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not after(d.get("ts"), since):
            continue
        total += 1
        key = rule_key(d.get("reason"))
        g = groups.setdefault(key, {"rule": key, "count": 0, "roles": collections.Counter(),
                                    "tools": collections.Counter(), "examples": []})
        g["count"] += 1
        g["roles"][d.get("role") or "main"] += 1
        g["tools"][d.get("tool") or "?"] += 1
        if len(g["examples"]) < 3:
            g["examples"].append(d.get("input", "")[:160])
        seen_inputs[(key, d.get("input", ""))] += 1
    out = []
    for g in sorted(groups.values(), key=lambda g: -g["count"]):
        g["roles"] = dict(g["roles"])
        g["tools"] = dict(g["tools"])
        g["repeated_same_input"] = sum(n - 1 for (k, _), n in seen_inputs.items()
                                       if k == g["rule"] and n > 1)
        out.append(g)
    return {"present": True, "total": total, "by_rule": out}


def scan_hook_errors(root, since):
    text = read(os.path.join(root, ".kiln", "hooks.log"))
    if text is None:
        return {"present": False}
    errors = []
    for m in re.finditer(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) hook error:\n((?:(?!\d{4}-\d{2}-\d{2} ).*\n?)*)",
                         text, re.M):
        if after(m.group(1), since):
            last = [ln for ln in m.group(2).splitlines() if ln.strip()][-1:] or [""]
            errors.append({"ts": m.group(1), "error": last[0][:200]})
    return {"present": True, "count": len(errors), "errors": errors[-10:]}


def scan_tasks(root, since):
    tasks = []
    for path in sorted(glob.glob(os.path.join(root, "tasks", "TASK-*.md")) +
                       glob.glob(os.path.join(root, "tasks", "archive", "TASK-*.md"))):
        text = read(path) or ""
        user_lines = [(d, t.strip()[:200]) for d, t in USER_LINE.findall(text) if after(d, since[:10] if since else "")]
        reviews = re.findall(r"^## review: ([^\n]+)", text, re.M)
        verdicts = VERDICT.findall(text)
        if since and not user_lines and not reviews:
            continue
        tasks.append({
            "task": os.path.basename(path)[:-3],
            "archived": os.sep + "archive" + os.sep in path,
            "reviews": len(reviews),
            "verdicts": dict(collections.Counter(verdicts)),
            "changes_required": sum(1 for v in verdicts if v in ("CHANGES_REQUIRED", "NEEDS_WORK", "FAIL")),
            "blocked": len(re.findall(r"^status:\s*BLOCKED", text, re.M)),
            "user_lines": [{"date": d, "text": t} for d, t in user_lines],
            "proxy": len(PROXY.findall(text)),
        })
    return {"count": len(tasks), "tasks": tasks,
            "most_rounds": sorted(({"task": t["task"], "changes_required": t["changes_required"]}
                                   for t in tasks if t["changes_required"]),
                                  key=lambda x: -x["changes_required"])[:5]}


PITFALLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "animation",
                        "references", "reads-wrong.md")


def scan_pitfalls(root, since, catalogues):
    """Entries no check catches, and the user's defect reports in the task logs (K05)."""
    no_check = []
    for path in catalogues or [PITFALLS]:
        text = read(path) or ""
        for block in re.split(r"^### ", text, flags=re.M)[1:]:
            title = block.splitlines()[0].strip()
            caught = re.search(r"\*\*Caught by:\*\*\s*(.+)", block)
            looks = re.search(r"\*\*Looks like:\*\*\s*(.+)", block)
            if caught and caught.group(1).strip().lower().startswith("no check yet"):
                no_check.append({"catalogue": os.path.basename(path), "title": title,
                                 "looks_like": looks.group(1).strip() if looks else ""})
    reported = []
    for t in scan_tasks(root, since)["tasks"]:
        for line in t["user_lines"]:
            reported.append({"task": t["task"], "date": line["date"], "text": line["text"]})
    return {"no_check_yet": no_check, "user_reported": reported}


def scan_proxy(root):
    out = {}
    pipe = read(os.path.join(root, "production", "PIPELINE.md"))
    if pipe is not None:
        out["pipeline_proxy_gates"] = [ln.strip()[:200] for ln in pipe.splitlines() if "PROXY" in ln]
    dec = read(os.path.join(root, "memory", "decisions.md"))
    if dec is not None:
        out["decisions_proxy"] = [ln.strip()[:200] for ln in dec.splitlines() if "PROXY" in ln]
        out["decisions_user"] = [ln.strip()[:200] for ln in dec.splitlines() if re.search(r"\buser\b", ln)][-15:]
    return out


def scan_transcripts(paths):
    tools, errors, agents = collections.Counter(), collections.Counter(), collections.Counter()
    uses, result = {}, {}
    for path in paths:
        for line in (read(path) or "").splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(e, dict):
                continue
            if e.get("type") == "result":
                result = {"turns": e.get("num_turns"), "cost_usd": e.get("total_cost_usd"),
                          "subtype": e.get("subtype")}
            msg = e.get("message")
            content = msg.get("content") if isinstance(msg, dict) else None
            for c in content if isinstance(content, list) else []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "tool_use":
                    name = c.get("name", "?")
                    tools[name] += 1
                    uses[c.get("id")] = name
                    if name in ("Agent", "Task"):
                        agents[(c.get("input") or {}).get("subagent_type") or "?"] += 1
                elif c.get("type") == "tool_result" and c.get("is_error"):
                    errors[uses.get(c.get("tool_use_id"), "?")] += 1
    return {"tool_calls": dict(tools.most_common(20)), "tool_errors": dict(errors.most_common(10)),
            "agents": dict(agents), "non_kiln_agents": sorted(a for a in agents if not a.startswith("kiln:")),
            "result": result}


def _stamp(ts):
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def scan_subagents(dirs):
    """Per role run: effort, responses, output and thinking tokens, wall time split into tool wait
    and model time. Claude Code keeps each subagent's transcript in <session>/subagents/agent-*.jsonl
    with an agent-*.meta.json beside it (agentType, description)."""
    runs = []
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "agent-*.jsonl"))):
            meta = {}
            try:
                meta = json.loads(read(path[:-len(".jsonl")] + ".meta.json") or "{}")
            except json.JSONDecodeError:
                pass
            usage, effort, times = {}, collections.Counter(), []
            tool_at, tool_wait = None, 0.0
            for line in (read(path) or "").splitlines():
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(e, dict):
                    continue
                t = _stamp(e.get("timestamp"))
                if t:
                    times.append(t)
                if e.get("effort"):
                    effort[e["effort"]] += 1
                msg = e.get("message") if isinstance(e.get("message"), dict) else {}
                content = msg.get("content") if isinstance(msg.get("content"), list) else []
                if e.get("type") == "assistant":
                    u = msg.get("usage") or {}
                    out = u.get("output_tokens") or 0
                    think = (u.get("output_tokens_details") or {}).get("thinking_tokens")
                    prev = usage.get(msg.get("id"))
                    if prev is None or out >= prev[0]:     # streamed blocks repeat the id; keep the final usage
                        usage[msg.get("id")] = (out, think)
                    if t and any(isinstance(c, dict) and c.get("type") == "tool_use" for c in content):
                        tool_at = t
                elif e.get("type") == "user" and tool_at and t and any(
                        isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
                    tool_wait += (t - tool_at).total_seconds()
                    tool_at = None
            out = sum(v[0] for v in usage.values())
            known = [v for v in usage.values() if v[1] is not None]
            think = sum(v[1] for v in known)
            wall = (max(times) - min(times)).total_seconds() / 60 if times else 0.0
            runs.append({
                "agent": meta.get("agentType", "?"), "description": meta.get("description", ""),
                "effort": effort.most_common(1)[0][0] if effort else None,
                "responses": len(usage), "output_tokens": out,
                "thinking_tokens": think if known else None,
                "thinking_share": round(think / out, 2) if known and out else None,
                "wall_min": round(wall, 1), "tool_wait_min": round(tool_wait / 60, 1),
                "model_min": round(wall - tool_wait / 60, 1),
            })
    return {"present": bool(runs), "runs": runs}


def scan_roles(root):
    """Role coverage over every task file (open and archived): which roles ran (a handoff,
    acceptance, review or verification section, or a filled gates verdict), which roles the
    tasks required (route table + declared touches) but never ran, which were skipped and why,
    which Kiln roles were never used at all, and what each open task still owes."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                                    "..", "hooks"))
    import kiln_hooklib as k
    ran, required, skipped, owed = set(), set(), [], {}
    files = sorted(glob.glob(os.path.join(root, "tasks", "*.md")) +
                   glob.glob(os.path.join(root, "tasks", "archive", "*.md")))
    for path in files:
        text = read(path) or ""
        tid = (re.search(r"TASK-\d+", os.path.basename(path)) or [os.path.basename(path)])[0]
        ran |= set(re.findall(r"^## (?:handoff|acceptance|review|verification)[:\s]+([\w-]+)",
                              text, re.M))
        rows = k.gate_rows(text) or {}
        for role, verdict in rows.items():
            if re.match(r"SKIP\b", verdict, re.I):
                skipped.append({"task": tid, "role": role,
                                "reason": re.sub(r"^SKIP:?\s*", "", verdict, flags=re.I)})
            elif verdict:
                ran.add(role)
        required |= {r for r, _ in k.suggested_gates(text, guess=False)}
        if os.sep + "archive" + os.sep not in path:
            missing = k.missing_gates(text)
            if missing:
                owed[tid] = missing
    skipped_roles = {s["role"] for s in skipped}
    return {"tasks": len(files), "ran": sorted(ran),
            "required_never_ran": sorted(required - ran - skipped_roles),
            "never_used": sorted(k.KILN_ROLES - ran),
            "skipped": skipped, "owed": owed}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--since", default="")
    ap.add_argument("--transcript", action="append", default=[])
    ap.add_argument("--pitfalls", action="append", default=[],
                    help="pitfall catalogue (default: animation references/reads-wrong.md)")
    ap.add_argument("--subagents", action="append", default=[],
                    help="a session's subagents folder (~/.claude/projects/<project>/<session>/subagents)")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    report = {
        "root": root, "since": args.since,
        "denials": scan_denials(root, args.since),
        "hook_errors": scan_hook_errors(root, args.since),
        "tasks": scan_tasks(root, args.since),
        "decisions": scan_proxy(root),
        "roles": scan_roles(root),
        "pitfalls": scan_pitfalls(root, args.since, args.pitfalls),
        "transcripts": scan_transcripts(args.transcript) if args.transcript else {"present": False},
        "subagents": scan_subagents(args.subagents) if args.subagents else {"present": False},
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
