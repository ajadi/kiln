"""Shared helpers for Kiln hooks.

Every hook is a no-op outside Kiln projects (manifest.md without `framework=kiln`) and fails
open: an internal error is logged to .kiln/hooks.log and the tool call is allowed, because a
broken guard must never stop the user's work.
"""

import contextlib
import json
import os
import re
import sys
import tempfile
import time
import traceback

QA_ROLES = {"qa-physics", "qa-locomotion", "qa-feel", "qa-damage", "qa-ai", "qa-readability",
            "qa-audio", "qa-performance"}
EXPERT_ROLES = {"physics-expert", "anatomy-expert", "creature-expert", "tech-designer"}
READ_ONLY_ROLES = {"playtester", "autoplayer", "art-director", "verifier"} | QA_ROLES
BUILD_ROLES = {"modeler", "animator", "level-designer", "gameplay-dev", "fx-artist",
               "sound-designer", "lighting-artist", "artist-2d", "composer", "music-producer",
               "ui-designer", "release-engineer", "writer", "ai-programmer"}
KILN_ROLES = {"game-designer"} | BUILD_ROLES | READ_ONLY_ROLES | EXPERT_ROLES

DEFAULT_POLICY = {
    "engine": "godot",                                 # godot | unity | unreal | none (assets)
    "dimension": "3d",                                 # 3d | 2d
    "model_generators": "off",                         # off | local | remote | api — image-to-3D/2D generators
    "audio_generators": "off",                         # off | local | remote | api — music/sound models
    "runtimes": "claude",                              # claude | codex | gemini, comma-separated
    "mcp_only": "on",                                  # Blender/Godot only through MCP
    "godot_files_via_mcp": "scenes,resources,scripts", # what may not be hand-edited
    "orchestrator_writes": "state",                    # main session: state | any
    "state_paths": "",                                 # extra main-session state globs
    "notes_files": "memory/kiln_reports.md",           # shared notes every role appends to
    "scene_first": "on",                               # scene content as editor nodes, not code
    "editor_lock_ttl": "600",                          # seconds before an idle lock expires
    "editor_lock_other_session_ttl": "120",            # same, for a lock left by another session
    "editor_lease_s": "900",                           # holder hands over when someone waits
    "kind": "game",                                    # game | prototype | assets (user-set)
    "user_gates": "proxy",                             # proxy (decide for the user, listed) | ask
    "autopilot_max_nudges": "3",                       # Stop-hook continuations without progress
    "agent_model": "",                                 # every Agent call: sonnet | opus | ...
    "agent_effort": "",                                # every Agent call: low ... max
    "problem_reports": "on",                           # on | off: Kiln's own problems into kiln-report.md
    "llm_npc": "off",                                  # off | local | api (LLM-driven NPC talk)
    "perf_gate": "on",                                 # on | informational | off (qa-performance)
    "on_screen": "anytime",                            # anytime | slot (batch on-screen runs)
}


def read_input():
    raw = sys.stdin.read()
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


def project_dir(data):
    """Claude Code names the project root; Codex only passes the session cwd, which may be a
    subfolder, so walk up to the nearest Kiln manifest."""
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return os.environ["CLAUDE_PROJECT_DIR"]
    start = os.path.abspath(data.get("cwd") or os.getcwd())
    path = start
    while True:
        manifest = os.path.join(path, "manifest.md")
        if os.path.isfile(manifest):
            try:
                with open(manifest, encoding="utf-8", errors="ignore") as fh:
                    if re.search(r"^framework=kiln\s*$", fh.read(), re.M):
                        return path
            except OSError:
                pass
        parent = os.path.dirname(path)
        if parent == path:
            return start
        path = parent


def read_manifest(root):
    path = os.path.join(root, "manifest.md")
    values = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"\s*([A-Za-z_][\w-]*)\s*=\s*(.*?)\s*$", line)
                if m:
                    values[m.group(1)] = m.group(2)
    except OSError:
        return None
    return values


def kiln_manifest(root):
    """Return the merged policy dict for a Kiln project, or None if this is not one."""
    manifest = read_manifest(root)
    if not manifest or manifest.get("framework") != "kiln":
        return None
    policy = dict(DEFAULT_POLICY)
    policy.update(manifest)
    return policy


def kiln_home():
    """The machine's Kiln folder (~/.kiln; KILN_HOME overrides): machine.json, projects.json."""
    return os.environ.get("KILN_HOME") or os.path.join(os.path.expanduser("~"), ".kiln")


def projects_path():
    return os.path.join(kiln_home(), "projects.json")


def throwaway(root):
    """A project under the system temp dir (test runs): not remembered, no network checks,
    unless KILN_REGISTER_TEMP is set."""
    if os.environ.get("KILN_REGISTER_TEMP"):
        return False
    temp = os.path.normcase(os.path.realpath(tempfile.gettempdir())) + os.sep
    return os.path.normcase(os.path.realpath(root)).startswith(temp)  # 8.3 names, symlinks


def register_project(root, policy):
    """Remember this project for /kiln:update all. Throwaway folders under the system temp dir
    (test runs) are not remembered unless KILN_REGISTER_TEMP is set."""
    path = os.path.abspath(root)
    if throwaway(path):
        return
    try:
        os.makedirs(kiln_home(), exist_ok=True)
        reg = projects_path()
        with locked(reg):
            data = load_json(reg, {})
            data[path.replace("\\", "/")] = {
                "name": policy.get("project_name") or os.path.basename(path),
                "version": policy.get("framework_version", "0.0.0"),
                "seen": time.strftime("%Y-%m-%d")}
            save_json(reg, data)
    except OSError:
        pass  # a read-only home never blocks a session


def manifest_version(path):
    """framework_version of a Kiln project folder, None when it is not one (any more)."""
    manifest = read_manifest(path)
    if not manifest or manifest.get("framework") != "kiln":
        return None
    return manifest.get("framework_version", "0.0.0")


def kiln_dir(root):
    path = os.path.join(root, ".kiln")
    os.makedirs(path, exist_ok=True)
    return path


def log(root, message):
    try:
        with open(os.path.join(kiln_dir(root), "hooks.log"), "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message.rstrip() + "\n")
    except OSError:
        pass


# Gemini CLI (v0.64.0 packages/core/src/tools/tool-names.ts, tools/mcp-tool.ts): built-in tool
# names, and MCP tools as mcp_<server>_<tool>. The hooks speak Claude Code's names inside.
GEMINI_TOOLS = {"run_shell_command": "Bash", "write_file": "Write", "replace": "Edit"}
MCP_SERVER_NAMES = ("unreal-mcp-proxy", "unreal-mcp", "godot-ai", "blender", "unity", "unreal")


def gemini_agent_marker(root):
    return os.path.join(kiln_dir(root), "gemini-agent.json")


def clear_gemini_agent(root):
    try:
        os.remove(gemini_agent_marker(root))
    except OSError:
        pass


def from_gemini(data, root):
    """A Gemini CLI hook payload in the shape the Kiln hooks read. Gemini payloads name no
    subagent: the role is the one an invoke_agent call is running (marker written at its
    BeforeTool, removed at its AfterTool; subagents cannot start subagents)."""
    out = dict(data)
    name = out.get("tool_name") or ""
    if name in GEMINI_TOOLS:
        out["tool_name"] = GEMINI_TOOLS[name]
    elif name.startswith("mcp_"):
        for server in MCP_SERVER_NAMES:
            if name.startswith(f"mcp_{server}_"):
                out["tool_name"] = f"mcp__{server}__{name[len(server) + 5:]}"
                break
    if out.get("hook_event_name") in ("AfterAgent", "SessionStart", "SessionEnd"):
        # only the main agent's turn fires these: no subagent runs now (an invoke_agent that
        # failed before running never reached its AfterTool)
        clear_gemini_agent(root)
    elif name == "invoke_agent":
        agent = str((out.get("tool_input") or {}).get("agent_name") or "")
        out["agent_type"], out["agent_id"] = agent, "gemini:" + agent
    else:
        marker = load_json(gemini_agent_marker(root), {})
        if marker.get("session") == out.get("session_id") and \
                time.time() - marker.get("ts", 0) < 900:  # subagents time out after 10 min
            out["agent_type"], out["agent_id"] = marker["agent_type"], marker["agent_id"]
    return out


def runtime():
    """'codex' when the hook command passes --runtime codex (hooks/codex-hooks.json), 'gemini'
    with --runtime gemini (the Gemini extension's hooks/hooks.json), else 'claude'. Codex hook input differs: file edits arrive as apply_patch, and its documented
    PreToolUse input does not identify the calling agent."""
    args = sys.argv[1:]
    if "--runtime" in args and args.index("--runtime") + 1 < len(args):
        return args[args.index("--runtime") + 1]
    return "claude"


def role_of(data):
    """Kiln role of the calling subagent, '' when unknown (main session, or Codex without
    agent_type). Claude Code plugin agents are 'kiln:<role>'; Kiln's Codex agents 'kiln-<role>'."""
    agent_type = data.get("agent_type") or ""
    if agent_type.startswith("kiln-") and agent_type[5:] in KILN_ROLES:
        return agent_type[5:]
    return agent_type.split(":")[-1] if agent_type else ""


def actor_id(data):
    return data.get("agent_id") or "main"


AUTOPILOT_COMMAND = re.compile(r"<command-name>/(?:kiln:)?autopilot</command-name>")


def autopilot_invoked_at(transcript_path):
    """Timestamp of the last /kiln:autopilot the user typed in this session ('' if none, None if
    the transcript cannot be read). Only typed prompts count — their message.content is a string;
    tool results that merely quote the command are lists."""
    if not transcript_path:
        return None
    last = ""
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "autopilot</command-name>" not in line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                content = (entry.get("message") or {}).get("content")
                if entry.get("type") == "user" and isinstance(content, str) \
                        and AUTOPILOT_COMMAND.search(content):
                    last = entry.get("timestamp") or "0"
    except OSError:
        return None
    return last


def autopilot_session(data, root):
    """Who runs the autopilot: 'self' (this session typed the latest /kiln:autopilot), 'other'
    (another session did) or None (unknown — no owner recorded and none found in this transcript).
    The owner is kept in .kiln/autopilot-state.json; a newer invocation elsewhere takes over."""
    path = os.path.join(kiln_dir(root), "autopilot-state.json")
    state = load_json(path, {})
    session = data.get("session_id") or ""
    if session and state.get("owner") == session:
        return "self"
    invoked = autopilot_invoked_at(data.get("transcript_path"))
    if invoked and invoked >= state.get("owner_since", ""):
        state.update({"owner": session, "owner_since": invoked, "nudges": 0})
        save_json(path, state)
        return "self"
    return "other" if state.get("owner") else None


def rel_path(root, path):
    """Project-relative path with forward slashes, or None if outside the project."""
    if not path:
        return None
    full = os.path.abspath(path if os.path.isabs(path) else os.path.join(root, path))
    base = os.path.abspath(root)
    try:
        rel = os.path.relpath(full, base)
    except ValueError:  # different drive on Windows
        return None
    rel = rel.replace("\\", "/")
    if rel.startswith("../") or rel == "..":
        return None
    return rel


def path_matches(rel, patterns):
    low = rel.lower()
    for pattern in patterns:
        p = pattern.lower()
        if p.endswith("/**"):
            prefix = p[:-3]
            if low == prefix or low.startswith(prefix + "/"):
                return True
        elif p.startswith("*."):
            if low.endswith(p[1:]):
                return True
        elif low == p:
            return True
    return False


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path, value):
    tmp = f"{path}.{os.getpid()}.tmp"   # one temp file per writer: no two writers share it
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(value, fh, indent=2)
    for _ in range(50):                 # Windows refuses a replace while a reader has it open
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.02)
    os.replace(tmp, path)


@contextlib.contextmanager
def locked(path, timeout=5.0):
    """Hold `<path>.lock` around a read-modify-write of a shared state file (hooks of parallel
    agents run at the same time; unlocked, the last writer won - 16 of 20 agent starts survived).
    A lock older than 10 s is left by a killed hook and taken over; past the timeout the caller
    goes ahead unlocked (hooks fail open)."""
    lock = path + ".lock"
    deadline = time.time() + timeout
    fd = None
    while fd is None:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > 10:
                    os.remove(lock)
                    continue
            except OSError:
                continue
            if time.time() > deadline:
                break
            time.sleep(0.01)
        except OSError:
            break
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
            try:
                os.remove(lock)
            except OSError:
                pass


def emit(obj):
    if runtime() == "gemini":
        obj = to_gemini(obj)
        if obj is None:
            return
    sys.stdout.write(json.dumps(obj))
    sys.stdout.flush()


def to_gemini(obj):
    """Claude Code hook output -> Gemini CLI's contract (hooks/types.ts at v0.64.0)."""
    spec = obj.get("hookSpecificOutput") or {}
    decision = spec.get("permissionDecision")
    if decision == "deny":
        return {"decision": "deny", "reason": spec.get("permissionDecisionReason", "")}
    if decision == "allow":
        return {"hookSpecificOutput": {"tool_input": spec["updatedInput"]}} \
            if spec.get("updatedInput") else None
    return obj  # decision/reason (AfterAgent) and additionalContext have the same shape


_CURRENT = {}  # the hook payload being handled, for the denial record


def record_denial(reason):
    """Append one JSON line per guard denial to .kiln/denials.jsonl — the retro skill reads it
    to tell real catches from false positives (a denial followed by the same work done another
    way, or retried unchanged)."""
    try:
        data = _CURRENT
        tool_input = data.get("tool_input") or {}
        excerpt = (tool_input.get("command") or tool_input.get("file_path")
                   or tool_input.get("path") or tool_input.get("code") or "")
        entry = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "runtime": runtime(),
                 "tool": data.get("tool_name", ""), "role": role_of(data) or "main",
                 "agent": data.get("agent_id", ""), "session": data.get("session_id", ""),
                 "reason": reason[:300], "input": str(excerpt)[:300]}
        root = project_dir(data)
        with open(os.path.join(kiln_dir(root), "denials.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # recording never blocks the decision
        pass


def deny(reason):
    record_denial(reason)
    emit({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "[kiln] " + reason,
        }
    })
    sys.exit(0)


def add_context(event, text):
    if runtime() == "gemini" and event == "SubagentStart":
        # Gemini has no subagent-start context: the role's start text leads its invoke_agent
        # prompt instead (BeforeTool may rewrite the tool input)
        # (every parameter: gemini-cli validates the rewritten input on its own)
        tool_input = dict(_CURRENT.get("tool_input") or {})
        tool_input["prompt"] = text + "\n\n" + str(tool_input.get("prompt") or "")
        sys.stdout.write(json.dumps({"hookSpecificOutput": {"tool_input": tool_input}}))
        return
    emit({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})


def run_safely(main):
    data = {}
    try:
        data = read_input()
        if runtime() == "gemini":
            data = from_gemini(data, project_dir(data))
        _CURRENT.clear()
        _CURRENT.update(data)
        if os.environ.get("KILN_HOOK_TRACE"):  # diagnostics: /kiln:doctor checks hooks really run
            log(project_dir(data), f"trace {runtime()} {data.get('hook_event_name', '?')} "
                                   f"{data.get('tool_name', '')} {data.get('agent_type', '')}")
        main(data)
    except SystemExit:
        raise
    except Exception as exc:  # fail open
        try:
            root = project_dir(data)
            log(root, "hook error:\n" + traceback.format_exc())
            script = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else "hook"
            report_problem(root, "hook", "hooks", f"{script} crashed: {type(exc).__name__}: "
                           f"{str(exc)[:160]} (traceback in .kiln/hooks.log; the action went on)")
        except Exception:
            pass
    sys.exit(0)


REPORT_HEADER = ("# Kiln problem reports\n\n"
                 "Problems with Kiln itself, written while working (rules) or by the user "
                 "(/kiln:report).\n\n"
                 "| # | date | who | area | what happened | suggestion | status |\n"
                 "|---|---|---|---|---|---|---|\n")


def report_problem(root, who, area, what, suggestion="-"):
    """Append a row to the project's kiln-report.md unless manifest problem_reports=off or the
    same problem is already listed as open."""
    policy = kiln_manifest(root)
    if not policy or str(policy.get("problem_reports", "on")).lower() == "off":
        return
    what = what.replace("|", "/").replace("\n", " ")
    path = os.path.join(root, "kiln-report.md")
    with locked(path):
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = REPORT_HEADER
        if any(what in line and line.rstrip().endswith("| open |") for line in text.splitlines()):
            return
        numbers = [int(n) for n in re.findall(r"^\|\s*(\d+)\s*\|", text, re.M)]
        row = (f"| {max(numbers, default=0) + 1} | {time.strftime('%Y-%m-%d')} | {who} | {area} | "
               f"{what} | {suggestion} | open |")
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.rstrip("\n") + "\n" + row + "\n")


# ---- task files ---------------------------------------------------------------------------

def active_tasks(root):
    """Open task files (not archived) with their unchecked checklist items."""
    tasks_dir = os.path.join(root, "tasks")
    result = []
    try:
        names = sorted(n for n in os.listdir(tasks_dir) if re.match(r"TASK-\d+.*\.md$", n))
    except OSError:
        return result
    for name in names:
        path = os.path.join(tasks_dir, name)
        try:
            text = open(path, encoding="utf-8").read()
        except OSError:
            continue
        title = text.splitlines()[0].lstrip("# ").strip() if text else name
        open_items = re.findall(r"^\s*- \[ \]\s*(.+)$", text, re.M)
        done_items = re.findall(r"^\s*- \[x\]\s*(.+)$", text, re.M | re.I)
        blocked = bool(re.search(r"^status:\s*BLOCKED", text, re.M))
        closed = bool(re.search(r"^verdict:\s*PASSED", text, re.M)) and not open_items
        if closed:
            continue
        result.append({
            "file": "tasks/" + name, "title": title, "open": open_items,
            "done": len(done_items), "blocked": blocked,
        })
    return result


def open_questions(root):
    try:
        text = open(os.path.join(root, "GAME.md"), encoding="utf-8").read()
    except OSError:
        return []
    return [row.strip() for row in re.findall(r"^\|\s*OQ-\d+.*⏳.*$", text, re.M)]


def backlog_progress(root):
    try:
        text = open(os.path.join(root, "backlog.md"), encoding="utf-8").read()
    except OSError:
        return None
    done = len(re.findall(r"^\s*- \[x\]", text, re.M | re.I))
    todo = len(re.findall(r"^\s*- \[[ ~]\]", text, re.M))  # [~] = in progress
    return done, done + todo


TASK_ROLE = re.compile(r"^role:\s*(.+)$", re.M)
TASK_PATHS = re.compile(r"^paths:\s*(.+)$", re.M)


def task_globs(text):
    """Globs from a task file's `paths:` line ("art/x/" -> "art/x/**", backticks stripped)."""
    m = TASK_PATHS.search(text)
    if not m:
        return []
    out = []
    for token in re.split(r"[,\s]+", m.group(1)):
        token = token.strip("`'\" ").rstrip(".;")
        if "/" in token or "." in token:
            out.append(token + "**" if token.endswith("/") else token)
    return out


def task_roles(text):
    m = TASK_ROLE.search(text)
    if not m:
        return set()
    return {r.strip().removeprefix("kiln:") for r in re.split(r"[,/+ ]+", m.group(1)) if r.strip()}


def task_text(root, task_id):
    """Text of tasks/TASK-NNN*.md (or its archived copy), '' if missing."""
    for folder in (os.path.join(root, "tasks"), os.path.join(root, "tasks", "archive")):
        try:
            names = [n for n in os.listdir(folder) if re.match(rf"{task_id}\b.*\.md$", n)]
        except OSError:
            continue
        for name in names:
            try:
                with open(os.path.join(folder, name), encoding="utf-8", errors="ignore") as fh:
                    return fh.read(20000)
            except OSError:
                pass
    return ""


AGENT_MAX_AGE = 6 * 3600  # an agent silent this long is assumed dead (its Stop never ran)


def agent_started(root, data):
    """Record a subagent as running until its SubagentStop (g2 rows 10, 125)."""
    path = os.path.join(kiln_dir(root), "agents.json")
    with locked(path):
        agents = load_json(path, {})
        now = time.time()
        agents = {aid: a for aid, a in agents.items() if now - a.get("since", 0) < AGENT_MAX_AGE}
        agent_id = data.get("agent_id")
        if agent_id:
            agents[agent_id] = {"role": role_of(data) or data.get("agent_type") or "agent",
                                "session": data.get("session_id") or "", "since": now}
        save_json(path, agents)


def agent_seen(root, data):
    """Heartbeat: the time and tool of an agent's latest guarded call (pipeline.py status)."""
    agent_id = data.get("agent_id")
    if not agent_id:
        return
    path = os.path.join(kiln_dir(root), "agents.json")
    with locked(path):
        agents = load_json(path, {})
        entry = agents.get(agent_id)
        if entry is None:
            return  # started outside the hooks' view (or already stopped)
        entry.update({"last": time.time(), "last_tool": data.get("tool_name") or "?"})
        save_json(path, agents)


def agent_stopped(root, data):
    path = os.path.join(kiln_dir(root), "agents.json")
    with locked(path):
        agents = load_json(path, {})
        if agents.pop(data.get("agent_id") or "", None) is not None:
            save_json(path, agents)


def running_agents(root, session):
    """[(agent_id, role, seconds running)] of this session's subagents that have not stopped."""
    agents = load_json(os.path.join(kiln_dir(root), "agents.json"), {})
    now = time.time()
    return [(aid, a.get("role"), int(now - a.get("since", now))) for aid, a in agents.items()
            if a.get("session") == session and now - a.get("since", 0) < AGENT_MAX_AGE]


# Required roles per task type: the run skill's route table (acceptance + close). Triggers add
# roles by what the task touches (g2 rows 43-46: consultants and acceptors named in parentheses
# were never called).
ROUTE = {
    "design": [], "tech": [],
    "art": ["art-director", "qa-readability", "verifier"],
    "animation": ["qa-locomotion", "verifier"],
    "level": ["playtester", "qa-ai", "qa-readability", "art-director", "verifier"],
    "lighting": ["qa-readability", "qa-performance", "verifier"],
    "gameplay": ["playtester", "verifier"],
    "ai": ["qa-ai", "playtester", "verifier"],
    "ui": ["qa-readability", "playtester", "verifier"],
    "narrative": ["playtester", "verifier"],
    "release": ["qa-performance", "verifier"],
    "fx": ["qa-performance", "qa-readability", "verifier"],
    "audio": ["qa-audio", "verifier"],
    "music": ["qa-audio", "verifier"],
    "integration": ["playtester", "autoplayer", "verifier"],
    "cinematic": ["art-director", "qa-readability", "qa-performance", "verifier"],
}
# kind=assets: a model, sprite sheet or track made on its own, without a game to play it in.
ASSET_ROUTE = {
    "art": ["art-director", "verifier"],
    "animation": ["art-director", "verifier"],
    "fx": ["art-director", "verifier"],
    "cinematic": ["art-director", "verifier"],
    "audio": ["qa-audio", "verifier"],
    "music": ["qa-audio", "verifier"],
}
# What a task touches decides the consultants and acceptors it needs. The plan writes it as
# `touches: humanoid, physics, ...` in the spec; that line is the contract the gates enforce.
# Without it the roles are only guessed from the spec's own lines (title, type, batch, paths) -
# never from acceptance prose or references, which mention characters and sounds everywhere
# (0.7.0 review: whole-text keywords put anatomy-expert on g2's facades, a rug and a dagger).
TOUCHES = {
    # touch: [(role, task types it applies to or None for all, why)]
    "humanoid": [("anatomy-expert", None, "humanoid body built or animated")],
    "creature": [("creature-expert", None, "animal / creature built or animated")],
    "mech": [("creature-expert", None, "walking machine")],
    "physics": [("physics-expert", None, "bodies, joints, layers or physics settings change"),
                ("qa-physics", {"gameplay", "integration", "tech", "ai"}, "physics behaviour")],
    "movement": [("qa-feel", None, "player movement or camera")],
    "npc": [("qa-ai", None, "NPC behaviour")],
    "damage": [("qa-damage", None, "damage rules")],
    "audio": [("qa-audio", None, "audio imported or mixed")],
    "scene-growth": [("qa-performance", None, "the scene grows (crowd, shadows, particles)")],
}
GUESS = {
    "humanoid": r"\b(human|humanoid|npc|person|people|dwarf|elf|merchant|soldier|villager|"
                r"crowd|character model|body|bodies)\b",
    "creature": r"\b(animal|creature|quadruped|horse|dog|wolf|bird|pigeon|monster|insect)s?\b",
    "mech": r"\b(mech|robot|walker)s?\b",
    "physics": r"\b(physics|rigid ?bod(y|ies)|joints?|jolt|ragdoll|collision layers?|"
               r"characterbody\w*|character controller|step-up|vehicles?)\b",
    "movement": r"\b(player controller|controller|camera|jump|movement|dash|aim)\b",
    "npc": r"\b(npc|enemy|enemies|navmesh|navigation|panic|routines?|perception)\b",
    "damage": r"\b(damage|hit ?box(es)?|hurtbox(es)?|health|kills?|stab)\b",
    "audio": r"(\.ogg\b|\.wav\b|\baudio\b|\bsfx\b|\bsound|\bmusic\b|\bambience\b)",
    "scene-growth": r"\b(crowd|lod|particles|scene grows|\d{2,} (props|npcs|looks))\b",
}
GUESS_TYPES = {"audio": {"audio", "music", "ui", "gameplay", "integration", "level"},
               "humanoid": {"art", "animation", "ai", "tech"},
               "creature": {"art", "animation", "ai", "tech"},
               "mech": {"art", "animation", "ai", "tech"},
               "movement": {"gameplay", "integration", "tech"},
               "npc": {"gameplay", "ai", "integration"},
               "damage": {"gameplay", "ai", "integration"}}
TOUCHES_LINE = re.compile(r"^touches:\s*(.*)$", re.M)
GATES_TABLE = re.compile(r"^## gates\s*\n(.*?)(?=^## |\Z)", re.M | re.S)


def task_type(text):
    m = re.search(r"^type:\s*([\w-]+)", text, re.M)
    return m.group(1).lower() if m else ""


def declared_touches(text):
    """Touches from the `touches:` line, or None when the task has no such line."""
    m = TOUCHES_LINE.search(text)
    if not m:
        return None
    return [t.strip() for t in re.split(r"[,\s]+", m.group(1)) if t.strip() and t != "none"]


def guess_touches(text):
    """Touches guessed from the spec's own lines only: the title, `batch:` and `paths:`."""
    lines = text.splitlines()
    head = [lines[0]] if lines else []
    head += [l for l in lines if re.match(r"^(batch|paths):", l)]
    spec = " ".join(head).lower()
    ttype = task_type(text)
    return [t for t, pattern in GUESS.items()
            if re.search(pattern, spec) and ttype in GUESS_TYPES.get(t, {ttype})]


def suggested_gates(text, kind="game", perf_gate="on", guess=True):
    """[(role, why)] for a task: the route table of its type plus the roles of what it touches
    (declared `touches:`, else - when guess is true - guessed). perf_gate (manifest)
    informational/off: qa-performance runs as advice, not a gate."""
    if kind == "prototype":
        return [("verifier", "close (prototype: plus one acceptance role)")]
    ttype = task_type(text)
    route = ASSET_ROUTE if kind == "assets" else ROUTE
    out = [(role, "route table") for role in route.get(ttype, ["verifier"])]
    touches = declared_touches(text)
    if touches is None:
        touches = guess_touches(text) if guess else []
    for touch in touches:
        for role, types, why in TOUCHES.get(touch, []):
            if kind == "assets" and not role.endswith("-expert"):
                continue  # no running game to accept movement, AI or damage in
            if (types is None or ttype in types) and role not in [r for r, _ in out]:
                out.insert(len(out) - 1 if out and out[-1][0] == "verifier" else len(out),
                           (role, why))
    if perf_gate != "on":
        out = [(r, f"advisory (perf_gate={perf_gate})" if r == "qa-performance" else why)
               for r, why in out if perf_gate != "off" or r != "qa-performance"]
    return out


def gate_rows(text):
    """{role: verdict cell} from the task's `## gates` table, None if there is no table."""
    m = GATES_TABLE.search(text)
    if not m:
        return None
    rows = {}
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] not in ("role", "") and not set(cells[0]) <= set("-: "):
            rows[cells[0].removeprefix("kiln:")] = cells[-1]
    return rows


def missing_gates(text, kind="game", perf_gate="on"):
    """Roles still owed a verdict: table rows with an empty verdict and no handoff by that role,
    and required roles (route table + declared touches; guesses never gate) absent from the
    table. A skip is a row with `SKIP: <reason>`."""
    rows = gate_rows(text) or {}
    handed = set(re.findall(r"^## (?:handoff|acceptance|review)[:\s]+([\w-]+)", text, re.M))
    advisory = {"qa-performance"} if perf_gate != "on" else set()
    missing = [role for role, verdict in rows.items()
               if not verdict and role not in handed and role not in advisory]
    missing += [role for role, _ in suggested_gates(text, kind, perf_gate, guess=False)
                if role not in rows and role not in handed and role not in advisory]
    bad_skips = [role for role, verdict in rows.items()
                 if re.match(r"SKIP\b:?\s*$", verdict, re.I)]
    return missing + [f"{r} (SKIP without a reason)" for r in bad_skips]
