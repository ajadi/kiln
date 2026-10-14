"""SessionStart / SessionEnd hook for Kiln projects.

start: inject a short state summary (active tasks with open checklist items, open questions,
       backlog progress, autopilot flag, last session handoff). After a compaction it also
       reminds the model to re-read the active task file — the summary may have dropped details.
end:   write memory/session-handoff.md and release this session's editor locks.
"""

import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kiln_hooklib as k  # noqa: E402
import update_check  # noqa: E402

AUTO_MARK = "<!-- kiln-auto-handoff: SessionEnd rewrites this file; delete this line to keep it -->"
NO_ENGINE_PROFILE = {"game-designer", "composer", "anatomy-expert"}


def git(root, *args):
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def state_lines(root):
    lines = []
    progress = k.backlog_progress(root)
    if progress:
        lines.append(f"Backlog: {progress[0]}/{progress[1]} done.")
    tasks = k.active_tasks(root)
    for task in tasks[:4]:
        flag = " [BLOCKED]" if task["blocked"] else ""
        lines.append(f"Active: {task['file']} — {task['title']}{flag} "
                     f"({task['done']} done, {len(task['open'])} open)")
        for item in task["open"][:3]:
            lines.append(f"    - [ ] {item}")
    if len(tasks) > 4:
        lines.append(f"(+{len(tasks) - 4} more active task files)")
    questions = k.open_questions(root)
    if questions:
        lines.append(f"Open questions in GAME.md: {len(questions)}")
        lines.extend("    " + q[:160] for q in questions[:3])
    return lines


def start(data, root, policy):
    source = data.get("source") or "startup"
    lines = [f"Kiln project '{policy.get('project_name', os.path.basename(root))}': "
             f"engine={policy.get('engine', 'godot')}, dimension={policy.get('dimension', '3d')}. "
             f"Policy: mcp_only={policy.get('mcp_only')}, scene_first={policy.get('scene_first')}, "
             f"orchestrator_writes={policy.get('orchestrator_writes')}, "
             f"user_gates={policy.get('user_gates', 'proxy')} (proxy: decide for the user with the "
             f"recommended option, record PROXY, list it in the report; ask: ask and wait). "
             + (f"Engine rules: skill kiln:engine-{policy.get('engine', 'godot')}. "
                if policy.get("engine", "godot") != "none" else "No game engine. ")
             + ("Workflow skills of the kiln plugin: pipeline, status, run, doctor (mention with $ "
                "or pick in /skills); Kiln roles are the custom agents kiln-<role>."
                if k.runtime() == "codex" else
                "Workflow: /kiln:pipeline, /kiln:status, /kiln:run, /kiln:doctor.")]
    version = plugin_version()
    older = policy.get("framework_version")
    if version and older and k_version(older) < k_version(version):
        lines.append(f"Kiln {version} is installed, the project was set up with "
                     f"{policy['framework_version']}: run /kiln:update (migrates task files and "
                     "the manifest, shows what changed).")
    if not k.throwaway(root):  # test projects never read or write this machine's state
        lines += machine_lines(root, policy, version)
    if str(policy.get("problem_reports", "on")).lower() == "off":
        lines.append("problem_reports=off in manifest.md: do not write kiln-report.md (the "
                     "project rules' problem reports are switched off here).")
    if policy.get("kind") == "prototype":
        lines.append("Project kind: PROTOTYPE (manifest kind=prototype, set by the user) — light "
                     "review per the run skill: one acceptance role + verifier, no risk review, no "
                     "separate playtester, at most 2 rounds per gate. Start every report to the user "
                     "with the mode. Never change kind yourself.")
    if policy.get("kind") == "assets":
        lines.append("Project kind: ASSETS (manifest kind=assets, set by the user) - assets made on "
                     "their own, no game: /kiln:model (a 3D model from 1-3 images), /kiln:sprites "
                     "(a sprite sheet or 2D map from an image), /kiln:track (a track from a "
                     "description), /kiln:cinematic (a video clip). No game pipeline, no engine; Blender through its MCP; deliver "
                     "into out/<asset>/ with the numbers and licences. Never change kind yourself.")
    lines += state_lines(root)
    if os.path.exists(os.path.join(root, ".kiln", "autopilot")):
        if k.runtime() == "codex" or k.autopilot_session(data, root) == "self":
            lines.append("Autopilot is ON (.kiln/autopilot): keep working through the backlog per "
                         "the kiln run/autopilot skills; stop only on the listed hard stops.")
        else:
            lines.append("Autopilot is ON in another session (.kiln/autopilot): do not work its "
                         "tasks or start a second producer here; answer the user. If the user runs "
                         "/kiln:autopilot in this session, this session takes it over.")
    if source == "compact":
        lines.append("Context was just compacted: re-read the active task file(s) above before "
                     "continuing — the summary may have lost details of the plan and checklist.")
    elif source in ("startup", "resume"):
        handoff = os.path.join(root, "memory", "session-handoff.md")
        if os.path.exists(handoff):
            lines.append("Last session handoff: memory/session-handoff.md (read it if resuming).")
        if os.path.exists(os.path.join(root, "memory", "session-handoff.auto.md")):
            lines.append("State at the end of the last session: memory/session-handoff.auto.md "
                         "(auto summary; the written handoff above stays the plan).")
    k.add_context("SessionStart", "\n".join(lines))


def machine_lines(root, policy, version):
    """This machine's view: record the project, a newer Kiln release, other projects behind."""
    lines = []
    k.register_project(root, policy)
    newer = update_check.notice(version, k_version, k.runtime())
    if newer:
        lines.append(newer)
    if update_check.due():
        update_check.mark_started()
        spawn_update_check()
    if not version:
        return lines
    here = os.path.normcase(os.path.abspath(root).replace("\\", "/"))
    behind = []
    for path, entry in sorted(k.load_json(k.projects_path(), {}).items()):
        other = k.manifest_version(path)
        if os.path.normcase(path) != here and other and k_version(other) < k_version(version):
            behind.append(entry.get("name") or os.path.basename(path))
    if behind:
        lines.append(f"{len(behind)} other Kiln project{'s' if len(behind) > 1 else ''} on "
                     f"this machine {'are' if len(behind) > 1 else 'is'} older than Kiln "
                     f"{version} ({', '.join(behind[:5])}): /kiln:update all updates them "
                     "from here (the user confirms once).")
    return lines


def spawn_update_check():
    """Look up the latest release in a detached process: the session never waits for it; its
    answer is shown at the next session start."""
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
              "stderr": subprocess.DEVNULL, "close_fds": True}
    argv = [sys.executable, "-B", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "update_check.py")]
    if os.name != "nt":
        kwargs["start_new_session"] = True
        flag_sets = [0]
    else:
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, plus CREATE_BREAKAWAY_FROM_JOB so a short
        # headless session closing its job object does not kill the check (refused when the job
        # forbids breakaway: then without it)
        flag_sets = [0x00000008 | 0x00000200 | 0x01000000, 0x00000008 | 0x00000200]
    for flags in flag_sets:
        try:
            if flags:
                kwargs["creationflags"] = flags
            subprocess.Popen(argv, **kwargs)
            return
        except OSError:
            continue


def plugin_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version")
    except (OSError, ValueError):
        return None


def k_version(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def end(data, root, policy):
    tasks = k.active_tasks(root)
    status = git(root, "status", "--porcelain").splitlines()
    out = [
        "# Session handoff",
        "",
        f"timestamp: {time.strftime('%Y-%m-%d %H:%M')}",
        f"branch: {git(root, 'rev-parse', '--abbrev-ref', 'HEAD') or 'n/a'}",
        f"last commit: {git(root, 'log', '-1', '--oneline') or 'n/a'}",
        "",
        "## Active tasks",
    ]
    if tasks:
        for task in tasks:
            out.append(f"- {task['file']} — {task['title']}"
                       f"{' [BLOCKED]' if task['blocked'] else ''}")
            out.extend(f"  - [ ] {item}" for item in task["open"][:8])
    else:
        out.append("none")
    out += ["", "## Open questions"]
    out += k.open_questions(root) or ["none"]
    out += ["", "## Uncommitted files"]
    out += [f"    {line}" for line in status[:30]] or ["none"]
    if len(status) > 30:
        out.append(f"    ... {len(status) - 30} more")
    os.makedirs(os.path.join(root, "memory"), exist_ok=True)
    # A handoff someone wrote by hand is the plan for the next session: never overwrite it; the
    # auto summary then goes next to it (g2 row 23).
    handoff = os.path.join(root, "memory", "session-handoff.md")
    auto = os.path.join(root, "memory", "session-handoff.auto.md")
    try:
        with open(handoff, encoding="utf-8") as fh:
            written = fh.readline().strip() != AUTO_MARK
    except OSError:
        written = False
    with open(auto if written else handoff, "w", encoding="utf-8") as fh:
        fh.write("\n".join([AUTO_MARK] + out) + "\n")
    if not written and os.path.exists(auto):
        os.remove(auto)
    path = os.path.join(k.kiln_dir(root), "locks.json")
    session = data.get("session_id") or ""
    with k.locked(path):
        locks = k.load_json(path, {})
        kept = {res: entry for res, entry in locks.items()
                if entry.get("session", session) != session}
        if kept != locks:  # another session's locks (a running autopilot) stay
            k.save_json(path, kept)


def engine_profile(policy):
    """Text of the engine skill for this project (frontmatter stripped)."""
    engine = policy.get("engine", "godot")
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "skills", f"engine-{engine}", "SKILL.md")
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return None
    if text.startswith("---"):
        text = text.split("---", 2)[-1]
    return text.strip()


def subagent(data, root, policy):
    """Give every Kiln role the project's engine profile and policies at spawn."""
    k.agent_started(root, data)
    role = k.role_of(data)
    if k.runtime() == "gemini" and role in k.KILN_ROLES:
        k.save_json(k.gemini_agent_marker(root), {"agent_type": data.get("agent_type"),
                                                  "agent_id": data.get("agent_id"),
                                                  "session": data.get("session_id"),
                                                  "ts": time.time()})
    if role not in k.KILN_ROLES:
        return
    engine = policy.get("engine", "godot")
    dimension = policy.get("dimension", "3d")
    head = (f"Kiln project: engine={engine}, dimension={dimension}, "
            f"mcp_only={policy.get('mcp_only')}, scene_first={policy.get('scene_first')}, "
            f"model_generators={policy.get('model_generators', 'off')}, "
            f"audio_generators={policy.get('audio_generators', 'off')}.")
    if engine == "none":
        k.add_context("SubagentStart", head + " No game engine (asset mode): deliver files and "
                                              "Blender scenes into out/<asset>/; no engine work.")
        return
    if role in NO_ENGINE_PROFILE:  # ~11-14k chars these roles never use
        k.add_context("SubagentStart", head + f" Load skill kiln:engine-{engine} only if your "
                                              "task turns out to need engine details.")
        return
    head += f" The engine profile below (skill kiln:engine-{engine}) applies to all engine work."
    profile = engine_profile(policy)
    if profile is None:
        k.add_context("SubagentStart", head + f" (engine skill engine-{engine} not found — "
                                              "report this in your handoff)")
        return
    k.add_context("SubagentStart", head + "\n\n" + profile)


def main(data):
    root = k.project_dir(data)
    policy = k.kiln_manifest(root)
    if policy is None:
        return
    mode = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "start"
    if mode == "start":
        start(data, root, policy)
    elif mode == "subagent":
        subagent(data, root, policy)
    else:
        end(data, root, policy)


if __name__ == "__main__":
    k.run_safely(main)
