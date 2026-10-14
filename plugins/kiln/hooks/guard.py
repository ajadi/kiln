"""PreToolUse guard for Kiln projects.

Checks, in order:
  1. Write/Edit/NotebookEdit (Codex: apply_patch, one check per patched file) — MCP-only file
     types, protected files, role write zones.
  2. Bash/PowerShell        — background Blender / bpy scripts, MCP bypass through the shell,
                              headless Godot scripting, git hygiene.
  3. mcp__blender__* / mcp__godot-ai__* / mcp__unity__* / mcp__unreal__* — forbidden tools,
     read-only roles, scene-first scripts and the one-driver-per-editor lock.

Denials are returned as JSON (permissionDecision=deny) so the reason reaches the model.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kiln_hooklib as k  # noqa: E402

PROTECTED = [".claude/settings.json", ".claude/settings.local.json", ".claude/agents/**",
             ".mcp.json", "manifest.md"]
GODOT_SCENES = ["*.tscn", "*.scn", "project.godot", "*.import", ".godot/**"]
GODOT_RESOURCES = ["*.tres", "*.res"]
GODOT_SCRIPTS = ["*.gd", "*.gdshader"]
MCP_FILE_EXEMPT = ["tests/probes/**", ".kiln/**"]

STATE_FILES = ["tasks/**", "backlog.md", "GAME.md", "design/**", "memory/**", "CLAUDE.md",
               "CLAUDE.local.md", "AGENTS.md", "manifest.md", ".claude/**", ".codex/**",
               ".agents/**", ".kiln/**", "docs/**", "README.md", "CHANGELOG.md", ".gitignore",
               ".gitattributes", "ref/**", "playtests/**", "production/**", "research/**"]
# The protocol's file table: anyone appends decisions and known issues; whoever changes the
# numbers writes registries and pipeline. Every role may write these (g2 rows 3, 79).
SHARED_MEMORY = ["memory/decisions.md", "memory/known-issues.md", "memory/registries.md",
                 "memory/pipeline.md"]
REVIEW_ZONE = ["tasks/**", "playtests/**", "tests/probes/**", "production/gauntlet/**",
               "production/captures/**", ".kiln/**"]
ADVISOR_ZONE = ["design/**", "research/**", "tasks/**", "production/**", ".kiln/**"]
ZONES = {
    "game-designer": ["GAME.md", "design/**", "research/**", "tasks/**", "memory/**",
                      "backlog.md", "production/**", ".kiln/**"],
    "playtester": REVIEW_ZONE,
    "autoplayer": REVIEW_ZONE + ["tests/autoplay/**", "production/autoplay/**"],
    "art-director": REVIEW_ZONE + ["design/ART_BIBLE.md", "research/**"],
    "verifier": REVIEW_ZONE,
    **{role: REVIEW_ZONE for role in k.QA_ROLES},
    **{role: ADVISOR_ZONE for role in k.EXPERT_ROLES},
}

RUNTIME_NODE = re.compile(
    r"\b((?:[A-Z][A-Za-z0-9]*)?(?:3D|2D|Mesh|Material|Shape|Light|Camera|Body|Area|Player|Tree|"
    r"Container|Button|Label|Panel|Rect|Control|Particles|Decal|Region|Marker|Instance|Sprite|"
    r"Node|Timer))\s*\.new\s*\(")
RUNTIME_NEW_OK = re.compile(r"^(\w*QueryParameters\w*|AStar\w*|PhysicsServer\w*)$")
RUNTIME_MARKER = "kiln:runtime-node"

REVIEW_SCRIPTS = ("# Kiln review view", "# Kiln mesh QA", "# Kiln contact check")

UNITY_ASSETS = ["*.unity", "*.prefab", "*.asset", "*.mat", "*.meta", "*.controller",
                "*.overrideController", "*.physicMaterial", "*.mixer", "*.inputactions"]
UNREAL_ASSETS = ["*.uasset", "*.umap", "config/**"]
CSHARP_NODE = re.compile(
    r"(new\s+GameObject\s*\(|GameObject\.CreatePrimitive\s*\(|"
    r"AddComponent\s*<\s*(MeshRenderer|MeshFilter|SkinnedMeshRenderer|\w*Collider|Light|Camera|"
    r"Canvas|Image|Text|TextMeshProUGUI|LineRenderer|ParticleSystem|Rigidbody|AudioSource)\s*>|"
    r"new\s+Material\s*\()")
# MCP for Unity (CoplayDev, read from its tool sources at v10.3.0): tools marked read-only, and
# read actions of the action-based manage_* tools. manage_tools is not here: its actions change
# which tools the session sees.
UNITY_READ_TOOLS = {"find_gameobjects", "read_console", "validate_script", "find_in_file", "get_sha",
                    "unity_reflect", "get_test_job", "run_tests", "unity_docs",
                    "manage_script_capabilities", "debug_request_context"}
UNITY_READ_ACTIONS = re.compile(
    r"^((\w+_)?(get|list|find|search|read|status|ping)(_\w+)?|screenshot(_multiview)?|play|pause|"
    r"stop|raycast(_all)?|linecast|overlap|shapecast|profiler_(start|stop))$")
UNITY_SCRIPT_TOOLS = {"create_script", "script_apply_edits", "apply_text_edits", "manage_script"}
# Epic's Unreal MCP (UE 5.8) exposes list_toolsets / describe_toolset / call_tool with qualified
# names (editor_toolset.toolsets.scene.SceneTools); community servers expose plain tool names.
# Epic's GenerateClientConfig registers the server as unreal-mcp (proxy: unreal-mcp-proxy).
UNREAL_PREFIX = re.compile(r"^mcp__unreal(-mcp(-proxy)?)?__")
UNREAL_READ_TOOLS = re.compile(
    r"^(get|find|list|describe|read|search|discover|is|capture|screenshot|trace_world|"
    r"dependencies|startpie|stoppie|runtests|stoptests|kiln_probe|inject_input|highres_shot)",
    re.I)
UNREAL_SAFE_CONSOLE = re.compile(r"^\s*(stat\s|csvprofile\s|trace\.|highresshot\b|profilegpu\b)",
                                 re.I)
UNREAL_GENERATORS = re.compile(r"^(create_(town|house|city|maze|building|castle)|construct_)", re.I)
CPP_NODE = re.compile(
    r"(SpawnActor\s*<\s*AStaticMeshActor\s*>|"
    r"NewObject\s*<\s*U\w*(MeshComponent|LightComponent|DecalComponent)\s*>)")


def csharp_constructions(code, pattern=CSHARP_NODE):
    """C# and C++ share // comments, so the same scan serves Unity and Unreal."""
    hits = []
    for number, line in enumerate(code.splitlines(), 1):
        if RUNTIME_MARKER in line:
            continue
        m = pattern.search(line.split("//", 1)[0])
        if m:
            hits.append(f"line {number}: {m.group(0).strip()}")
    return hits


def scene_first_reason(hits, comment):
    return ("This script builds scene content in code (" + "; ".join(hits[:3]) + "). Build it in "
            "the open editor through the MCP (or as a prefab/scene that is instantiated) and "
            "reference it from the script — the user edits scenes by hand, not code. Genuine "
            f"runtime exceptions carry '{comment} {RUNTIME_MARKER} <reason>' on that line.")

BLENDER_READ_ONLY = re.compile(r"^mcp__blender__(get_|search_)")
GODOT_READ_ONLY = {"editor_state", "logs_read", "scene_get_hierarchy", "node_get_properties",
                   "node_find", "api_manage", "session_manage", "session_activate",
                   "test_manage"}
FOR_CLI = re.compile(r"^mcp__blender__.*_for_cli$")
# Experts and the tech designer advise and measure; through editor MCPs they only read.
MCP_READ_ONLY = k.READ_ONLY_ROLES | k.EXPERT_ROLES
# Godot AI <domain>_manage tools take {op, params}. What read-only roles may do with them:
GODOT_REVIEW_TOOLS = GODOT_READ_ONLY | {"editor_screenshot", "scene_open", "project_run",
                                        "test_run", "game_manage"}
GODOT_REVIEW_OPS = {
    "editor_manage": {"state", "selection_get", "selection_set", "monitors_get", "logs_clear",
                      "game_eval"},
    "project_manage": {"stop", "settings_get"},
    "script_manage": {"read", "find_symbols"},
    "filesystem_manage": {"read_text", "search", "scan", "write_text"},
}
GODOT_REVIEW_WRITES = ["tests/probes/**", "tests/autoplay/**", "production/captures/**",
                       "production/autoplay/**", "playtests/**", ".kiln/**"]


ACCEPTOR_PROBE = re.compile(r"^tests/probes/(.*/)?probe_qa_[^/]*$", re.I)


def policy_list(policy, key, default=""):
    return [p.strip() for p in policy.get(key, default).split(",") if p.strip()]


def notes_files(policy):
    """Shared notes files every role and the main session may append to (manifest notes_files)."""
    return ["kiln-report.md"] + policy_list(policy, "notes_files", "memory/kiln_reports.md")


def task_paths(root, role):
    """Globs from the `paths:` of open task files (tasks/*.md, not the archive) whose `role:` line
    names this role: a delegation extends the role's zone to its task (g2 row 130)."""
    out = []
    folder = os.path.join(root, "tasks")
    try:
        names = [n for n in os.listdir(folder) if n.lower().endswith(".md")]
    except OSError:
        return out
    for name in names:
        try:
            with open(os.path.join(folder, name), encoding="utf-8", errors="ignore") as fh:
                text = fh.read(20000)
        except OSError:
            continue
        if role in k.task_roles(text):
            out += k.task_globs(text)
    return out


def deny_acceptor_probe(rel, role):
    if role and role in k.KILN_ROLES and role not in k.READ_ONLY_ROLES and \
            ACCEPTOR_PROBE.match(rel):
        k.deny(f"{rel} is an acceptor's probe (probe_qa_*); only QA roles, the playtester and the "
               "verifier change it, so a builder fix cannot weaken the test that judges it. Put "
               "your own checks in another tests/probes/ file, and append the row change you need "
               "to the task file for the acceptor.")


SPEC_LINES = re.compile(r"^(role|paths|touches|type):.*$", re.M)


def new_text_of(data, full):
    """The file's text after this Write / Edit (None when it cannot be worked out)."""
    tool_input = data.get("tool_input") or {}
    if data.get("tool_name") == "ShellWrite":
        if data.get("shell_mode") == "append":
            try:
                with open(full, encoding="utf-8", errors="ignore") as fh:
                    return fh.read()  # appended text is not known; spec lines stay as they are
            except OSError:
                return None
        return ""
    if data.get("tool_name") == "Edit":
        try:
            with open(full, encoding="utf-8", errors="ignore") as fh:
                old = fh.read()
        except OSError:
            return None
        a, b = tool_input.get("old_string") or "", tool_input.get("new_string") or ""
        if not a or a not in old:
            return None
        return old.replace(a, b) if tool_input.get("replace_all") else old.replace(a, b, 1)
    return tool_input.get("content")


def check_task_edit(data, root, rel, role):
    """Roles append to task files; the spec lines that set roles, zones and gates (role, paths,
    touches, type) and other roles' verdict cells belong to the producer (0.7.0 review: a role in
    a task's role line may write its paths, so editing those lines widened its own zone)."""
    if not role or role not in k.KILN_ROLES or not re.match(r"tasks/(archive/)?[^/]+\.md$", rel):
        return
    full = os.path.join(root, rel)
    try:
        with open(full, encoding="utf-8", errors="ignore") as fh:
            old = fh.read()
    except OSError:
        return  # a new task file: the producer creates tasks, a role's new file has no gates yet
    new = new_text_of(data, full)
    if new is None:
        return
    if [m.group(0) for m in SPEC_LINES.finditer(old)] != \
            [m.group(0) for m in SPEC_LINES.finditer(new)]:
        k.deny(f"{rel}: the role, paths, touches and type lines are the producer's. Ask for the "
               "change in your handoff (open: / next: orchestrator) instead of editing them.")
    before, after = k.gate_rows(old) or {}, k.gate_rows(new) or {}
    for other in set(before) | set(after):
        if other != role and before.get(other) != after.get(other):
            k.deny(f"{rel}: the gates row of {other} is that role's verdict (or the producer's "
                   "recorded skip). Write only your own row and your own handoff section.")


def godot_bootstrap(rel, root, role):
    """Setup writes project.godot (and the editor metadata) once, before the editor exists."""
    if role or rel not in ("project.godot", ".godot/editor/project_metadata.cfg"):
        return False
    if rel != "project.godot":
        return True  # editor UI state (embedded game view), merged by setup while it is closed
    full = os.path.join(root, rel)
    return not os.path.isfile(full) or os.path.getsize(full) == 0


def check_write(data, root, policy):
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    rel = k.rel_path(root, path)
    if rel is None:
        return
    role = k.role_of(data)

    engine = policy.get("engine", "godot")
    if engine == "godot" and godot_bootstrap(rel, root, role):
        return
    deny_acceptor_probe(rel, role)
    check_task_edit(data, root, rel, role)
    if policy.get("mcp_only") == "on" and not k.path_matches(rel, MCP_FILE_EXEMPT):
        via_mcp = policy.get("godot_files_via_mcp", "") if engine == "godot" else ""
        if engine == "unity" and (k.path_matches(rel, UNITY_ASSETS)
                                  or rel.lower().startswith("projectsettings/")):
            k.deny(f"{rel} is a Unity scene/prefab/asset/settings file. Change it in the editor "
                   "through MCP for Unity (manage_scene, manage_prefabs, manage_asset, ...).")
        if engine == "unreal" and k.path_matches(rel, UNREAL_ASSETS):
            k.deny(f"{rel} is an Unreal asset or config file. Change it in the editor through "
                   "the Unreal MCP.")
        if "scenes" in via_mcp and rel.lower().endswith(".import"):
            k.deny(f"{rel} holds import options. Change them with the engine-godot skill's "
                   "scripts/import_edit.py (set --param / --sub / --importer; it touches the "
                   "source), then filesystem_manage op=reimport through the Godot AI MCP.")
        if "scenes" in via_mcp and k.path_matches(rel, GODOT_SCENES):
            k.deny(f"{rel} is a Godot scene/project file. Edit it in the editor through the "
                   "Godot AI MCP (scene_*/node_*/project_manage tools), not as text.")
        if "resources" in via_mcp and k.path_matches(rel, GODOT_RESOURCES):
            k.deny(f"{rel} is a Godot resource. Create or change it through the Godot AI MCP "
                   "(resource_manage, material_manage, ...).")
        if "scripts" in via_mcp and k.path_matches(rel, GODOT_SCRIPTS):
            k.deny(f"{rel} is a Godot script. Use script_create / script_patch from the Godot "
                   "AI MCP so the editor validates and reloads it (editing on disk while the "
                   "editor is open triggers a blocking reload dialog).")
        if rel.lower().endswith((".blend", ".blend1")):
            k.deny(f"{rel} is a Blender file. Change it in the open Blender through the "
                   "Blender Lab MCP and save it there.")

    if (engine == "unity" and rel.lower().endswith(".cs")
            and policy.get("scene_first", "on") == "on"
            and not re.search(r"(^|/)(editor|tests?)/", rel.lower())):
        code = tool_input.get("content") or tool_input.get("new_string") or ""
        hits = csharp_constructions(code)
        if hits:
            k.deny(scene_first_reason(hits, "//"))
    if (engine == "unreal" and rel.lower().endswith((".cpp", ".h"))
            and policy.get("scene_first", "on") == "on"
            and not re.search(r"(^|/)(\w*editor|tests?)/|editor\.(cpp|h)$", rel.lower())):
        code = tool_input.get("content") or tool_input.get("new_string") or ""
        hits = csharp_constructions(code, CPP_NODE)
        if hits:
            k.deny(scene_first_reason(hits, "//"))

    if (engine == "godot" and rel.lower().endswith(".gd")
            and policy.get("scene_first", "on") == "on" and not rel.startswith("tests/")):
        hits = runtime_constructions(tool_input.get("content") or tool_input.get("new_string")
                                     or "")
        if hits:
            k.deny(scene_first_reason(hits, "#"))

    if not role:  # main session
        if k.runtime() == "codex":
            # Codex's documented PreToolUse input has no agent identity, so a role-less call may
            # come from the main thread or a subagent: role rules live in the agent files
            # (permission profiles, MCP tool lists) instead.
            return
        state = STATE_FILES + notes_files(policy) + policy_list(policy, "state_paths")
        # shell output of the producer's own tools (reports, logs, recipes) is not policed here;
        # the engine-file rules above still apply to it
        if policy.get("orchestrator_writes", "state") == "state" and \
                data.get("tool_name") != "ShellWrite" and not k.path_matches(rel, state):
            k.deny(f"The main session coordinates; it does not write game content ({rel}). "
                   "Delegate to the Kiln role that owns this path (see the run skill), or set "
                   "orchestrator_writes=any in manifest.md if the user wants direct edits.")
        return

    if role not in k.KILN_ROLES:  # built-in or third-party agents: not ours to police
        return
    if k.path_matches(rel, PROTECTED):
        k.deny(f"{rel} is framework configuration; Kiln agents do not change it. Report the "
               "needed change in your handoff instead.")
    zone = ZONES.get(role)
    if zone is not None:
        zone = zone + SHARED_MEMORY + notes_files(policy)
        if not k.path_matches(rel, zone) and not k.path_matches(rel, task_paths(root, role)):
            k.deny(f"{role} may not write {rel}. Allowed: {', '.join(zone)}, plus the `paths:` "
                   "of an open task whose `role:` line names you. Describe the needed change in "
                   "your handoff and name the role that owns it (or ask the producer to add you "
                   "to the task's role line).")


# Codex apply_patch grammar (codex-rs/apply-patch/src/parser.rs): file hunks start with these
# markers; added lines start with "+".
PATCH_FILE = re.compile(r"^\*\*\* (Add File|Update File|Delete File|Move to): (.+?)\s*$")


def patch_operations(patch):
    """[(path, added_text)] for every file a Codex apply_patch touches, in order."""
    ops = []
    for line in patch.splitlines():
        m = PATCH_FILE.match(line)
        if m:
            ops.append((m.group(2), []))
        elif ops and line.startswith("+"):
            ops[-1][1].append(line[1:])
    return [(path, "\n".join(lines)) for path, lines in ops]


def check_patch(data, root, policy):
    """Codex file edits: run the Write checks once per file in the patch."""
    tool_input = data.get("tool_input") or {}
    base = data.get("cwd") or root
    for path, added in patch_operations(str(tool_input.get("command") or "")):
        full = path if os.path.isabs(path) else os.path.join(base, path)
        check_write({**data, "tool_input": {"file_path": full, "content": added}}, root, policy)


# AI generators by policy (manifest model_generators / audio_generators: off | local | api).
MODEL_LOCAL = re.compile(r"\b(trellis|pixal3d|hunyuan3d|triposg|triposr|instantmesh|step1x-3d|"
                         r"direct3d-s2|hi3dgen|stable-fast-3d|sf3d|spar3d|partcrafter|omnipart|"
                         r"comfyui|diffusers|stable[-_]?diffusion|sdxl|flux\.?[12]|qwen-image)")
MODEL_API = re.compile(r"(api\.tripo3d\.ai|api\.meshy\.ai|hyper3d\.ai|api\.stability\.ai|"
                       r"api\.retrodiffusion|pixellab\.ai)")
AUDIO_LOCAL = re.compile(r"\b(audiocraft|musicgen|ace-?step|stable[-_]audio|riffusion|yue)\b")
AUDIO_API = re.compile(r"(suno\.com|udio\.com|api\.elevenlabs\.io|stableaudio\.com)")


# Programs that only read or print: a generator's name in their arguments is not a run of it
# (g2: `grep trellis skills/image-to-model/SKILL.md` and a hardware check were denied).
READERS = {"ls", "dir", "cat", "type", "head", "tail", "less", "more", "grep", "egrep", "fgrep",
           "rg", "findstr", "wc", "sort", "uniq", "cut", "diff", "echo", "printf", "file", "stat",
           "get-content", "gc", "select-string", "sls", "get-childitem", "gci", "get-item",
           "test-path", "write-output", "write-host", "get-ciminstance", "get-wmiobject",
           "vswhere", "nvidia-smi", "where", "which", "get-command", "measure-object",
           "select-object", "format-table", "format-list", "out-string"}


def executed_text(command):
    """The words of every simple command that is not a reader, joined: what may start a tool."""
    return "\n".join(" ".join(words) for words in shell_segments(command)
                     if program(words).removesuffix(".exe") not in READERS
                     and not vcs_text(words))


def vcs_text(words):
    """git / gh words are messages, titles and refs, not programs to start - except a git that
    fetches code (clone, submodule, fetch, pull), which installs what it names."""
    prog = program(words).removesuffix(".exe")
    if prog == "gh":
        return True
    if prog == "git":
        sub = next((w for w in words[1:] if not w.startswith("-")), "")
        return sub not in ("clone", "submodule", "fetch", "pull")
    return False


def runs_gpu_job(command):
    """True when the command starts the gpu-server skill's job runner."""
    return any(any(os.path.basename(w).lower() == "gpu_job.py" for w in words[:3])
               for words in shell_segments(command))


def check_generators(low, policy):
    for key, local, api, what in (("model_generators", MODEL_LOCAL, MODEL_API, "image/3D"),
                                  ("audio_generators", AUDIO_LOCAL, AUDIO_API, "music/sound")):
        if policy.get(key) == "remote" and not runs_gpu_job(low):
            text = executed_text(low)
            if local.search(text) or api.search(text):
                k.deny(f"{key}=remote: {what} generators run only on the rented GPU server "
                       "through the gpu-server skill's gpu_job.py (spend cap, provenance, stop "
                       "after the job), not on this machine and not through paid APIs.")
    low = executed_text(low)
    for key, local, api, what in (("model_generators", MODEL_LOCAL, MODEL_API, "image/3D"),
                                  ("audio_generators", AUDIO_LOCAL, AUDIO_API, "music/sound")):
        mode = policy.get(key, "off")
        if mode == "off" and (local.search(low) or api.search(low)):
            k.deny(f"{what} generators are off for this project ({key}=off in manifest.md). "
                   "Make the asset with the normal pipeline, or ask the user to change the policy.")
        if mode == "local" and api.search(low):
            k.deny(f"{key}=local allows only local open-weight models, not paid APIs.")


PYTHON_EXE = re.compile(r"^(?:.*/)?(python[\d.]*w?|py)(\.exe)?$", re.I)
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")


def split_heredocs(command):
    """(command without here-document bodies, bodies fed to a Python interpreter).

    Bodies are data (stdin), not shell commands; only a body piped into python is code."""
    out, python_bodies, end, body, to_python = [], [], None, [], False
    for line in command.split("\n"):
        if end is not None:
            if line.strip() == end:
                if to_python:
                    python_bodies.append("\n".join(body))
                end, body = None, []
            else:
                body.append(line)
            continue
        out.append(line)
        m = HEREDOC.search(line)
        if m:
            end = m.group(2)
            head = line[:m.start()].replace("\\", "/").split()
            to_python = bool(head) and bool(PYTHON_EXE.match(head[0]))
    return "\n".join(out), python_bodies


def strip_heredocs(command):
    return split_heredocs(command)[0]


def split_unquoted(text):
    """Split on ; & | && || and newlines that are outside single or double quotes."""
    parts, cur, quote = [], [], None
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            cur.append(ch)
        elif ch in ";&|\n":
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def shell_segments(command):
    """Word lists of the simple commands in a shell line, program first.

    Splits on ; && || | & and newlines, skips here-document bodies, drops VAR=value prefixes and
    unwraps `uv run` / `uvx` / `uv tool run`. Words after the program are its arguments, so a
    server name inside a quoted note or a --probe value is not a call to that server.
    """
    for seg in split_unquoted(strip_heredocs(command).replace("\\", "/")):
        try:
            words = shlex.split(seg)
        except ValueError:
            words = seg.split()
        while words and re.match(r"^\w+=", words[0]):  # VAR=value prefix
            words.pop(0)
        if words[:3] == ["uv", "tool", "run"]:
            words = words[3:]
        elif words[:2] == ["uv", "run"] or words[:1] == ["uvx"]:
            words = [w for w in words[1 if words[0] == "uvx" else 2:] if not w.startswith("-")]
        if words:
            yield words


def program(words):
    return os.path.basename(words[0]).lower()


def python_pipelines(command):
    """Pipelines (a | b | c) of the command that start a Python interpreter: text in them is its
    code or its stdin; text in other pipelines (a search, a commit message) is not."""
    out = []
    for pipe in re.split(r"&&|\|\||;|\n", command):
        for part in pipe.split("|"):
            first = part.strip().split(None, 1)
            if first and PYTHON_EXE.match(first[0].strip("'\"")):
                out.append(pipe)
                break
    return out


def python_runs(command, root):
    """(starts a Python interpreter?, script files it runs) for a shell command.

    Only executed scripts count: `head parts.py` or `grep bpy review.py` read a file and are fine.
    `cd <dir>` moves the base for relative paths.
    """
    invoked, scripts, cwd = False, [], root
    for words in shell_segments(command):
        if words[0] == "cd" and len(words) > 1:
            cwd = os.path.join(cwd, words[1])
            continue
        script = None
        if PYTHON_EXE.match(words[0]):
            invoked = True
            rest = iter(words[1:])
            for arg in rest:
                if arg in ("-c", "-m", "-"):
                    break
                if arg in ("-X", "-W", "-Q"):
                    next(rest, None)
                elif not arg.startswith("-"):
                    script = arg
                    break
        elif words[0].lower().endswith(".py"):
            script = words[0]
        if script:
            path = os.path.join(cwd, script)
            if os.path.isfile(path):
                scripts.append(path)
    return invoked, scripts


NULL_TARGETS = {"/dev/null", "nul", "$null", "nul:"}
PS_WRITE = {"set-content": ("-path", "-literalpath"), "add-content": ("-path", "-literalpath"),
            "out-file": ("-filepath", "-literalpath", "-path")}
PS_COPY = {"copy-item", "move-item", "cp", "mv", "copy", "move"}


def shell_write_targets(command):
    """[(path, mode)] a shell command writes: redirections, tee, cp/mv destinations, sed -i,
    PowerShell Set-Content / Add-Content / Out-File / Copy-Item / Move-Item. mode is 'append'
    for >> and tee -a / Add-Content, else 'write'. Here-document bodies are not commands."""
    out = []
    for seg in split_unquoted(strip_heredocs(command).replace("\\", "/")):
        try:
            lex = shlex.shlex(seg, posix=True, punctuation_chars="<>")
            lex.whitespace_split = True
            toks = list(lex)
        except ValueError:
            toks = seg.split()
        if not toks:
            continue
        for i, t in enumerate(toks):
            if t in (">", ">>", ">|") and i + 1 < len(toks):
                out.append((toks[i + 1], "append" if t == ">>" else "write"))
        words = [t for i, t in enumerate(toks)
                 if t not in (">", ">>", ">|", "<", "<<")
                 and not (i and toks[i - 1] in (">", ">>", ">|", "<", "<<"))]
        while words and re.match(r"^\w+=", words[0]):
            words.pop(0)
        if not words:
            continue
        prog = os.path.basename(words[0]).lower().removesuffix(".exe")
        args = words[1:]
        if prog == "tee":
            mode = "append" if any(a in ("-a", "--append") for a in args) else "write"
            out += [(a, mode) for a in args if not a.startswith("-")]
        elif prog == "sed" and any(a == "-i" or a.startswith("-i") or a == "--in-place"
                                   for a in args):
            files = [a for a in args if not a.startswith("-")][1:]
            out += [(f, "write") for f in files]
        elif prog in ("cp", "mv", "install") and len([a for a in args if not a.startswith("-")]) >= 2:
            dest = [a for a in args if not a.startswith("-")][-1]
            srcs = [a for a in args if not a.startswith("-")][:-1]
            if dest.endswith("/") and len(srcs) == 1:
                dest += os.path.basename(srcs[0])
            out.append((dest, "write"))
        elif prog in PS_WRITE:
            low = [a.lower() for a in args]
            named = next((args[j + 1] for j, a in enumerate(low)
                          if a in PS_WRITE[prog] and j + 1 < len(args)), None)
            target = named or next((a for a in args if not a.startswith("-")), None)
            if target:
                out.append((target, "append" if prog == "add-content" else "write"))
        elif prog in PS_COPY:
            low = [a.lower() for a in args]
            named = next((args[j + 1] for j, a in enumerate(low)
                          if a == "-destination" and j + 1 < len(args)), None)
            positional = [a for j, a in enumerate(args) if not a.startswith("-")
                          and not (j and low[j - 1].startswith("-"))]
            target = named or (positional[1] if len(positional) >= 2 else None)
            if target:
                out.append((target, "write"))
    return [(p, m) for p, m in out if p.lower() not in NULL_TARGETS]


def check_shell_writes(data, root, policy):
    """A file written by a shell command passes the same checks as a Write of that file."""
    command = (data.get("tool_input") or {}).get("command") or ""
    for target, mode in shell_write_targets(command):
        path = target if os.path.isabs(target) else os.path.join(root, target)
        if k.rel_path(root, path) is None:
            continue
        check_write({**data, "tool_name": "ShellWrite", "shell_mode": mode,
                     "tool_input": {"file_path": path, "content": ""}}, root, policy)


def screen_free(root):
    """on_screen=slot: a windowed game run needs the user's slot (`.kiln/slot`, optional
    `until=<ISO time>`) or the away flag (`.kiln/away`)."""
    if os.path.exists(os.path.join(root, ".kiln", "away")):
        return True
    path = os.path.join(root, ".kiln", "slot")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    m = re.search(r"until=(\S+)", text)
    if not m:
        return True
    try:
        return time.time() < time.mktime(time.strptime(m.group(1)[:16], "%Y-%m-%dT%H:%M"))
    except ValueError:
        return True


SLOT_REASON = ("on_screen=slot: the user works on this PC, so no windowed game run now. Work "
               "headless (probes, cinematic captures), and add this check to "
               "production/MEASUREMENT_SLOT.md for the next slot (the producer asks the user; a "
               "granted slot is .kiln/slot, the user being away is .kiln/away).")


def windowed_godot_run(words):
    """A Godot command line that opens a game window: not --headless, not the editor, not a
    version/help/export/check call."""
    if not re.fullmatch(r"godot(?!-ai)[\w.-]*", program(words)):
        return False
    quiet = {"--headless", "--editor", "-e", "--version", "--help", "-h", "--check-only",
             "--export-release", "--export-debug", "--export-pack", "--doctool", "--import"}
    return not any(a in quiet for a in words[1:])


def godot_script(words):
    """The script a Godot command line runs with -s/--script, or None."""
    if not re.fullmatch(r"godot(?!-ai)[\w.-]*", program(words)):
        return None
    for i, arg in enumerate(words[1:], 1):
        if arg in ("--script", "-s"):
            return words[i + 1] if i + 1 < len(words) else ""
    return None


def headless_probe(words, script):
    """Parse checks and test probes may run headless; scripts that build content may not."""
    rel = re.sub(r"^(res://|\./|/)+", "", script.replace("\\", "/"))
    return "--check-only" in words or rel.startswith(("tests/", ".kiln/"))


def kills_by_name(words):
    prog = program(words).removesuffix(".exe")
    args = [a.lower() for a in words[1:]]
    if prog == "taskkill":
        return "/im" in args or "-im" in args
    if prog in ("pkill", "killall"):
        return True
    if prog in ("stop-process", "spps"):
        return not any(a in ("-id", "-processid") for a in args)
    return False


def check_shell(data, root, policy):
    command = (data.get("tool_input") or {}).get("command") or ""
    if not command.strip():
        return
    low = command.lower()
    role = k.role_of(data)

    check_shell_writes(data, root, policy)
    windowed = any(windowed_godot_run(w) for w in shell_segments(command))
    if windowed and policy.get("on_screen") == "slot" and not screen_free(root):
        k.deny(SLOT_REASON)
    check_generators(low, policy)
    if role and re.search(r"pipeline\.py\b.*\b(tick|skip)\b.*--by\s+(user|proxy)\b", low):
        k.deny("User gates are closed by the main session after the user decides (or as PROXY "
               "on autopilot), never by a role. Report the evidence in your handoff instead.")

    if policy.get("mcp_only") == "on":
        calls = list(shell_segments(command))
        if any(re.fullmatch(r"blender(\.exe)?", program(w)) and any(
                re.fullmatch(r"-b|--background|-P|--python(-expr|-text|-exit-code)?", a)
                for a in w[1:]) for w in calls):
            k.deny("Background Blender runs are not allowed in this project. Do the work in the "
                   "user's open Blender through the Blender Lab MCP (execute_blender_code).")
        invoked, scripts = python_runs(command, root)
        # Text written to a file through a here-document is data; a body fed to python is code
        # when a line of it imports bpy (a string that mentions bpy is not).
        outside, python_bodies = split_heredocs(command)
        if invoked and (any(re.search(r"\b(import\s+bpy|from\s+bpy\b)", pipe)
                            for pipe in python_pipelines(outside)) or any(
                re.search(r"^\s*(import\s+bpy|from\s+bpy\b)", body, re.M)
                for body in python_bodies)):
            k.deny("bpy code must run inside the user's Blender through the Blender Lab MCP "
                   "(execute_blender_code), not from the shell.")
        for path in scripts:
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    if re.search(r"^\s*(import\s+bpy|from\s+bpy\b)", fh.read(), re.M):
                        k.deny(f"{os.path.basename(path)} imports bpy. Run Blender code through "
                               "the Blender Lab MCP in the open Blender instead.")
            except OSError:
                pass
        # Only programs started count: `claude mcp add godot-ai -- godot-ai attach`, a gate note
        # saying "godot-ai connected" or `--probe godot-ai=ok` name the server without calling it.
        if any(re.fullmatch(r"(blender-mcp|blmcp)(\.exe)?", program(w)) or (
                PYTHON_EXE.match(w[0]) and any(a.endswith("mcp_client.py") for a in w[1:3]))
               for w in calls):
            k.deny("Calling the Blender MCP server from the shell bypasses the MCP connection. "
                   "Use the mcp__blender__* tools.")
        if any(re.fullmatch(r"godot-ai(\.exe)?", program(w)) and
               not any(a in ("--version", "--help") for a in w[1:]) for w in calls):
            k.deny("Calling the Godot AI server from the shell bypasses the MCP connection. "
                   "Use the mcp__godot-ai__* tools.")
        if re.search(r"(127\.0\.0\.1|localhost):(9876|9500|8000|8080)\b", low):
            k.deny("Direct connections to the editors' MCP ports (Blender, Godot, Unity, Unreal) "
                   "are not allowed; use the MCP tools.")
        if re.search(r"-batchmode\b", low) and \
                re.search(r"-executemethod\s+(?![\w.]*build)", low):
            k.deny("Headless Unity editor scripts are not allowed for editor work; use MCP "
                   "for Unity in the open editor. (Build methods are allowed.)")
        if re.search(r"(-executepythonscript|-run=pythonscript)", low):
            k.deny("Headless Unreal Python is not allowed for editor work; use the Unreal "
                   "MCP in the open editor.")
        for w in calls:
            script = godot_script(w)
            if script is not None and not headless_probe(w, script):
                k.deny(f"Headless Godot script {script} looks like editor work; build it in the "
                       "open editor through the Godot AI MCP tools. Allowed headless: probes and "
                       "tests under tests/ or .kiln/tmp/ (any flags, any pipe), and "
                       "--check-only parse checks of any script.")

    for w in shell_segments(command):
        if kills_by_name(w):
            k.deny("Do not kill processes by image name (taskkill /IM, pkill, killall, "
                   "Stop-Process -Name): MCP servers, editors and other agents' tools share those "
                   "names. Kill the PID you started: taskkill /PID <pid> /T /F or Stop-Process "
                   "-Id <pid>.")

    # git hygiene (user's commit policy): stage specific files, no force push, no secrets
    for segment in re.split(r"&&|\|\||;|\n", command):
        seg = segment.strip()
        if re.match(r"git\s+add\s+(-A\b|--all\b|\.(\s|$))", seg):
            k.deny("Stage specific files (git add <paths>), not everything — framework state and "
                   "generated files must not slip into commits.")
        if re.match(r"git\s+push\b", seg) and re.search(r"\s(--force(?!-with-lease)|-f\b)", seg):
            k.deny("Force push is not allowed. Use --force-with-lease only if the user asked.")
        if re.match(r"git\s+commit\b", seg) and "--no-verify" in seg:
            k.deny("Do not skip git hooks (--no-verify).")
        if re.match(r"git\s+add\b", seg):
            for name in git_words(seg)[2:]:
                if is_secret_file(name):
                    k.deny(f"{name} is a secrets file: never stage it. Make sure it is "
                           "git-ignored.")
        if re.match(r"git\s+commit\b", seg):
            paths, everything = commit_paths(git_words(seg))
            names = git_names(root, "diff", "--cached", "--name-only") + paths
            if everything:  # -a commits every modified tracked file
                names += git_names(root, "diff", "--name-only")
            for name in names:
                if is_secret_file(name):
                    k.deny(f"{name} would be committed; secrets files must not be committed. "
                           "Unstage it (git restore --staged), leave it out of the commit and "
                           "make sure it is git-ignored.")


def is_secret_file(name):
    base = name.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return bool(re.fullmatch(r"\.env(\..+)?", base)) and base != ".env.example"


def git_words(segment):
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


def git_names(root, *args):
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                              timeout=5).stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return []


COMMIT_VALUE_OPTS = {"-m", "--message", "-F", "--file", "-C", "--reuse-message", "-c",
                     "--reedit-message", "--author", "--date", "--fixup", "--squash", "-t",
                     "--template", "--cleanup", "--trailer", "--pathspec-from-file"}


def commit_paths(words):
    """(paths named on a `git commit` line, whether -a/--all commits every tracked change)."""
    paths, everything, skip, literal = [], False, False, False
    for w in words[2:]:
        if skip:
            skip = False
        elif literal or not w.startswith("-"):
            paths.append(w)
        elif w == "--":
            literal = True
        elif w.startswith("--"):
            everything |= w == "--all"
            skip = w in COMMIT_VALUE_OPTS
        else:  # a short cluster such as -am: a value-taking letter ends it
            for i, ch in enumerate(w[1:]):
                everything |= ch == "a"
                if "-" + ch in COMMIT_VALUE_OPTS:
                    skip = i == len(w) - 2
                    break
    return paths, everything


def editor_lock(data, root, policy, resource):
    tool = data.get("tool_name") or ""
    short = tool.split("__", 2)[-1]
    if resource == "blender" and BLENDER_READ_ONLY.match(tool):
        return
    if resource == "godot" and short in GODOT_READ_ONLY:
        return
    if resource in ("unity", "unreal") and is_engine_read(data):
        return
    path = os.path.join(k.kiln_dir(root), "locks.json")
    with k.locked(path):  # two agents asking at once must not both get the editor
        take_editor(data, policy, resource, path)


QUEUE_STALE_S = 300  # a waiter that has not asked again for 5 min has gone elsewhere


def take_editor(data, policy, resource, path):
    locks = k.load_json(path, {})
    me = k.actor_id(data)
    role = k.role_of(data) or "main session"
    now = time.time()
    session = data.get("session_id") or ""
    held = locks.get(resource)
    # A session that was killed (usage limit, Ctrl-C, crash) never runs its Stop hooks, so its
    # lock lingers. Another session's lock therefore expires sooner than one inside this session.
    if held and held.get("session", session) != session:
        ttl = float(policy.get("editor_lock_other_session_ttl", 120))
    else:
        ttl = float(policy.get("editor_lock_ttl", 600))
    # The main session hands the editor to the role it delegates to: its own doctor probes must
    # not lock its agents out (live: the producer's probe blocked the animator for the TTL).
    handed_over = held and held.get("owner") == "main" and me != "main" and \
        held.get("session", session) == session
    # The queue (g2 row 6): a refused caller waits in line instead of retrying blind; a holder
    # past its lease hands over when someone waits; a free editor goes to the head of the line.
    qpath = os.path.join(os.path.dirname(path), "queue.json")
    queues = k.load_json(qpath, {})
    line = [w for w in queues.get(resource, []) if now - w.get("ts", 0) < QUEUE_STALE_S]
    lease = float(policy.get("editor_lease_s", 900))

    def wait(reason):
        mine = next((w for w in line if w["owner"] == me), None)
        if mine:
            mine["ts"] = now
        else:
            line.append({"owner": me, "role": role, "session": session, "since": now, "ts": now})
        queues[resource] = line
        k.save_json(qpath, queues)
        pos = [w["owner"] for w in line].index(me) + 1
        k.deny(f"{reason} You are #{pos} in the queue for {resource} "
               f"({', '.join(w['role'] for w in line)}). Do work that does not need the editor, "
               "then call again; the editor goes to the head of the queue when it is free, and a "
               f"holder past its {int(lease)} s lease hands over to waiters. If nothing else is "
               "left, hand off with the editor work under open.")

    valid = held and now - held.get("ts", 0) < ttl
    if valid and held.get("owner") != me and not handed_over:
        since = int(now - held.get("since", now))
        wait(f"{resource.capitalize()} is being driven by {held.get('role')} (for {since}s); two "
             "drivers corrupt each other's editor state.")
    others = [w for w in line if w["owner"] != me]
    if valid and held.get("owner") == me and others and now - held.get("since", now) > lease:
        del locks[resource]
        k.save_json(path, locks)
        wait(f"Your lease on {resource} is over ({int(now - held.get('since', now))} s held) and "
             f"{others[0]['role']} waits: finish the current step without the editor, write your "
             "handoff with the remaining editor work under open, or wait your turn.")
    if not (valid and held.get("owner") == me) and line and line[0]["owner"] != me \
            and not handed_over:
        wait(f"{resource.capitalize()} is free, but {line[0]['role']} asked first.")
    if any(w["owner"] == me for w in line):
        queues[resource] = [w for w in line if w["owner"] != me]
        k.save_json(qpath, queues)
    entry = {"owner": me, "role": role, "session": session, "ts": now,
             "since": held.get("since", now) if held and held.get("owner") == me else now}
    locks[resource] = entry
    k.save_json(path, locks)


def runtime_constructions(code):
    hits = []
    for number, line in enumerate(code.splitlines(), 1):
        code_part = line.split("#", 1)[0]
        if RUNTIME_MARKER in line:
            continue
        for cls in RUNTIME_NODE.findall(code_part):
            if not RUNTIME_NEW_OK.match(cls):
                hits.append(f"line {number}: {cls}.new()")
    return hits


def check_scene_first(data, policy):
    """Scripts add behaviour; scene content is built as nodes in the editor."""
    if policy.get("scene_first", "on") != "on":
        return
    tool = (data.get("tool_name") or "").split("__", 2)[-1]
    tool_input = data.get("tool_input") or {}
    if tool == "script_create":
        path, code = tool_input.get("path", ""), tool_input.get("content", "")
    elif tool == "script_patch":
        path, code = tool_input.get("path", ""), tool_input.get("new_text", "")
    elif tool == "batch_execute":
        path, code = "", str(tool_input.get("commands", "")).replace("\\n", "\n")
    else:
        return
    rel = str(path).replace("res://", "").lstrip("/")
    if rel.startswith("tests/"):
        return  # probes and test suites may build throwaway nodes
    if tool != "batch_execute" and not str(path).endswith(".gd"):
        return
    hits = runtime_constructions(code)
    if hits:
        k.deny("This script builds scene content in code (" + "; ".join(hits[:3]) + "). Build it "
               "as nodes in the scene in the open editor (scene_open, node_create, "
               "node_set_property, scene_save) or instance a prepared .tscn, and reference it from "
               "the script with @onready/@export — the user edits scenes by hand, not code. If "
               "runtime creation is genuinely required (pooled debris, a procedural mesh the "
               f"design asks for, debug drawing), add '# {RUNTIME_MARKER} <reason>' on that line.")


def check_godot_review(data, role):
    """Read-only roles drive Godot to run, observe and probe the game, never to change it."""
    tool = (data.get("tool_name") or "").split("__", 2)[-1]
    tool_input = data.get("tool_input") or {}
    op = str(tool_input.get("op") or "")
    params = tool_input.get("params") if isinstance(tool_input.get("params"), dict) else {}
    if tool in GODOT_REVIEW_TOOLS:
        return
    if tool in ("script_create", "script_patch"):
        rel = str(tool_input.get("path") or "").replace("res://", "").lstrip("/")
        if k.path_matches(rel, GODOT_REVIEW_WRITES):
            return
    allowed = GODOT_REVIEW_OPS.get(tool)
    if allowed is None or op not in allowed:
        k.deny(f"{role} is read-only: {tool} {op} can change the project. Run, observe and "
               "probe the game; describe the change in your handoff for the owning role.")
    if tool == "filesystem_manage" and op == "write_text":
        rel = str(params.get("path") or tool_input.get("path") or "").replace("res://", "")
        if not k.path_matches(rel.lstrip("/"), GODOT_REVIEW_WRITES):
            k.deny(f"{role} may write files through the Godot MCP only under "
                   f"{', '.join(GODOT_REVIEW_WRITES)} (probes, captures, reports).")


def check_godot_text_write(data, root, policy):
    """filesystem_manage write_text is a raw text write: the same file rules as Write apply, so
    scenes, resources and scripts cannot be hand-written through the MCP either."""
    if not (data.get("tool_name") or "").endswith("__filesystem_manage"):
        return
    tool_input = data.get("tool_input") or {}
    params = tool_input.get("params") if isinstance(tool_input.get("params"), dict) else {}
    if str(tool_input.get("op") or "") != "write_text":
        return
    path = str(params.get("path") or tool_input.get("path") or "").replace("res://", "")
    content = str(params.get("content") or "")
    if path:
        check_write({**data, "tool_input": {"file_path": os.path.join(root, path.lstrip("/")),
                                            "content": content}}, root, policy)


def unity_is_read(short, tool_input):
    """Read-only use of an MCP for Unity tool (names and actions from its v10.3.0 sources)."""
    action = str(tool_input.get("action") or "")
    if short == "execute_code":
        return action in ("", "execute") and "kiln:probe" in str(tool_input.get("code") or "")
    if short == "manage_scene" and action == "validate":
        return not tool_input.get("auto_repair")
    return short in UNITY_READ_TOOLS or bool(UNITY_READ_ACTIONS.match(action))


def unity_script_payloads(short, tool_input):
    """(path, code) for every C# text a Unity MCP call would write; batch_execute is unwrapped."""
    if short == "batch_execute":
        out = []
        commands = tool_input.get("commands") or []
        if isinstance(commands, str):
            try:
                commands = json.loads(commands)
            except ValueError:
                commands = []
        for cmd in commands if isinstance(commands, list) else []:
            if isinstance(cmd, dict):
                params = cmd.get("params") if isinstance(cmd.get("params"), dict) else cmd
                out += unity_script_payloads(str(cmd.get("tool") or cmd.get("name") or ""), params)
        return out
    if short not in UNITY_SCRIPT_TOOLS:
        return []
    if short == "manage_script" and str(tool_input.get("action") or "") not in ("create", "update"):
        return []
    path = str(tool_input.get("path") or tool_input.get("uri") or tool_input.get("name") or "")
    path = re.sub(r"^(unity://path/|file://)", "", path).replace("\\", "/")
    parts = [tool_input.get(key) for key in ("contents", "content", "text")]
    edits = tool_input.get("edits")
    if isinstance(edits, str):
        try:
            edits = json.loads(edits)
        except ValueError:
            parts.append(edits)
            edits = None
    for edit in edits if isinstance(edits, list) else []:
        if isinstance(edit, dict):
            parts += [edit.get(key) for key in ("newText", "replacement", "text", "new_text")]
    code = "\n".join(str(part) for part in parts if part)
    return [(path, code)] if code else []


def check_unity(data, policy, role):
    tool = (data.get("tool_name") or "").split("__", 2)[-1]
    tool_input = data.get("tool_input") or {}
    if role in MCP_READ_ONLY and not unity_is_read(tool, tool_input):
        action = str(tool_input.get("action") or "")
        if tool == "execute_code":
            k.deny(f"{role} is read-only: execute_code is allowed only for probes (action "
                   "execute, code marked '// kiln:probe') that read state, never for edits.")
        k.deny(f"{role} is read-only: {tool} {action} changes the project. Describe the "
               "change in your handoff for the owning role.")
    if policy.get("scene_first", "on") != "on":
        return
    for path, code in unity_script_payloads(tool, tool_input):
        if re.search(r"(^|/)(editor|tests?)/", path.lower()):
            continue
        hits = csharp_constructions(code)
        if hits:
            k.deny(scene_first_reason(hits, "//"))


def unreal_call(data):
    """(tool name, arguments) of an Unreal MCP call, unwrapping Epic's call_tool. UE 5.8 names
    are qualified (editor_toolset.toolsets.scene.SceneTools.get_current_level): keep the last
    segment."""
    tool = (data.get("tool_name") or "").split("__", 2)[-1]
    tool_input = data.get("tool_input") or {}
    if tool == "call_tool":
        args = tool_input.get("arguments") or {}
        name = str(tool_input.get("tool_name") or tool_input.get("name") or "")
        return name.rsplit(".", 1)[-1], args if isinstance(args, dict) else {}
    return tool, tool_input


def is_engine_read(data):
    tool = data.get("tool_name") or ""
    short = tool.split("__", 2)[-1]
    tool_input = data.get("tool_input") or {}
    if tool.startswith("mcp__unity__"):
        return unity_is_read(short, tool_input)
    if UNREAL_PREFIX.match(tool):
        if short in ("list_toolsets", "describe_toolset", "unreal_mcp_status"):
            return True
        name, args = unreal_call(data)
        if re.search(r"console", name, re.I):
            return bool(UNREAL_SAFE_CONSOLE.match(str(args.get("command") or args.get("cmd") or "")))
        return bool(UNREAL_READ_TOOLS.match(name))
    return False


def check_unreal(data, policy, role):
    name, args = unreal_call(data)
    if role in MCP_READ_ONLY and not is_engine_read(data):
        k.deny(f"{role} is read-only: Unreal tool {name or data.get('tool_name')} may change the "
               "project. Read-only roles use get/find/list/capture/log/PIE/test tools, the Kiln "
               "probe toolset and stat/csvprofile/trace console commands. Describe the change in "
               "your handoff for the owning role.")
    if policy.get("scene_first", "on") == "on" and UNREAL_GENERATORS.match(name):
        k.deny(f"{name} generates level content procedurally. Build levels by placing actors, "
               "level instances and packed level actors in the open editor so the user can edit "
               "them by hand.")


GAME_START = re.compile(r"__(project_run|startpie)$|__manage_editor$", re.I)


def starts_windowed_game(data):
    tool = data.get("tool_name") or ""
    if not GAME_START.search(tool):
        return False
    if tool.endswith("__manage_editor"):  # MCP for Unity: action play enters Play mode
        return str((data.get("tool_input") or {}).get("action") or "").lower() == "play"
    return True


def check_mcp(data, root, policy):
    tool = data.get("tool_name") or ""
    role = k.role_of(data)
    if policy.get("on_screen") == "slot" and starts_windowed_game(data) and not screen_free(root):
        k.deny(SLOT_REASON)
    if tool.startswith("mcp__godot-ai__"):
        if tool.endswith(("__script_create", "__script_patch")):
            rel = str((data.get("tool_input") or {}).get("path") or "")
            deny_acceptor_probe(rel.replace("res://", "").lstrip("/"), role)
        check_scene_first(data, policy)
        if role in MCP_READ_ONLY:
            check_godot_review(data, role)
        check_godot_text_write(data, root, policy)
    if tool.startswith("mcp__unity__"):
        check_unity(data, policy, role)
    if UNREAL_PREFIX.match(tool):
        check_unreal(data, policy, role)
    if policy.get("mcp_only") == "on" and FOR_CLI.match(tool):
        k.deny("The *_for_cli Blender tools run a background Blender process. Use the tools "
               "that act on the user's open Blender instead.")
    if tool == "mcp__godot-ai__client_manage" and role:
        k.deny("Agents do not reconfigure MCP clients. Report the need in the handoff.")
    if tool == "mcp__blender__execute_blender_code" and role in MCP_READ_ONLY:
        code = ((data.get("tool_input") or {}).get("code") or "").lstrip()
        if not code.startswith(REVIEW_SCRIPTS):
            k.deny(f"{role} is read-only: through execute_blender_code it may run only the Kiln "
                   "review scripts (set_view.py, silhouette_shot.py, mesh_qa.py, contact_check.py from the "
                   "blender-modeling skill), sent as-is with only their parameters changed.")
    resource = tool.split("__")[1] if tool.count("__") >= 2 else "editor"
    resource = {"godot-ai": "godot", "unreal-mcp": "unreal",
                "unreal-mcp-proxy": "unreal"}.get(resource, resource)
    editor_lock(data, root, policy, resource)


def check_agent(data, root, policy):
    """Manifest agent_model / agent_effort apply to every delegation (g2 rows 11, 153). Missing
    values are filled in; a different value needs the task file named in the prompt to ask for
    it (`model:` / `effort:` line, or `complexity: high` for a stronger model)."""
    want = {"model": policy.get("agent_model", "").strip(),
            "effort": policy.get("agent_effort", "").strip()}
    if want["model"] and not CLAUDE_MODEL.search(want["model"]):
        want["model"] = ""  # a Codex model name: codex_agents.py applies it, Claude Code cannot
    if not any(want.values()):
        return
    tool_input = dict(data.get("tool_input") or {})
    texts = [k.task_text(root, tid) for tid in
             sorted(set(re.findall(r"TASK-\d+", str(tool_input.get("prompt") or ""))))]
    changed = False
    for key, wanted in want.items():
        if not wanted:
            continue
        task_value = next((m.group(1) for t in texts
                           for m in [re.search(rf"^{key}:\s*([\w.:\[\]-]+)", t, re.M)] if m), None)
        if key == "model" and task_value and not CLAUDE_MODEL.search(task_value):
            task_value = None  # a Codex model line is for codex_agents.py
        given = tool_input.get(key)
        if given in (None, ""):
            tool_input[key] = task_value or wanted
            changed = True
            continue
        high = key == "model" and any(re.search(r"^complexity:\s*high", t, re.M) for t in texts)
        if given not in (wanted, task_value) and not high:
            k.deny(f"manifest.md sets agent_{key}={wanted} for every agent; this call asks for "
                   f"{key}={given}. Drop the {key} parameter (the hook fills in {wanted}), or put "
                   f"`{key}: {given}` in the task file the prompt names if the user asked for it.")
    if changed:
        k.emit({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "permissionDecision": "allow",
                                       "permissionDecisionReason": "[kiln] model/effort from "
                                       "manifest.md / the task file",
                                       "updatedInput": tool_input}})


# Claude Code's model values: aliases (with a context suffix such as [1m]), opusplan, inherit,
# and full ids including cloud ones (us.anthropic.claude-...). Anything else is for Codex.
CLAUDE_MODEL = re.compile(r"^(opus|sonnet|haiku|fable|opusplan|inherit)(\[[\w.]+\])?$|claude",
                          re.I)


def main(data):
    root = k.project_dir(data)
    policy = k.kiln_manifest(root)
    if policy is None:
        return
    k.agent_seen(root, data)
    tool = data.get("tool_name") or ""
    if tool in ("Write", "Edit", "NotebookEdit"):
        check_write(data, root, policy)
    elif tool == "apply_patch":
        check_patch(data, root, policy)
    elif tool in ("Agent", "Task"):
        check_agent(data, root, policy)
    elif tool in ("Bash", "PowerShell"):
        check_shell(data, root, policy)
    elif tool.startswith(("mcp__blender__", "mcp__godot-ai__", "mcp__unity__")) or \
            UNREAL_PREFIX.match(tool):
        check_mcp(data, root, policy)


if __name__ == "__main__":
    k.run_safely(main)
