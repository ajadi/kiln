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

import datetime
import glob
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kiln_hooklib as k  # noqa: E402

PROTECTED = [".claude/settings.json", ".claude/settings.local.json", ".claude/agents/**",
             ".mcp.json", "manifest.md",
             # the other runtimes' guard and configuration (bug hunt 2026-10-20)
             ".opencode/plugins/**", "opencode.json", ".github/copilot/settings.json",
             ".gemini/settings.json", ".codex/agents/**", ".codex/hooks.json"]
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
                "*.overrideController", "*.physicMaterial", "*.mixer", "*.inputactions",
                # editor-made assets the bug hunt (2026-10-20) found unprotected
                "*.anim", "*.shadergraph", "*.shadersubgraph", "*.vfx", "*.spriteatlas",
                "*.spriteatlasv2", "*.lighting", "*.terrainlayer", "*.playable", "*.signal",
                "*.rendertexture", "*.brush", "*.flare", "*.guiskin", "*.cubemap",
                "*.giparams", "*.physicsMaterial2D"]
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
# A read prefix followed by a change is not a read (bug hunt 2026-10-20: find_or_create_track).
UNREAL_CHANGE_WORD = re.compile(r"(^|_)(create|add|set|delete|remove|spawn|save|import|apply|make|"
                                r"build|edit|modify|move|rename|duplicate|replace|generate)(_|$)",
                                re.I)
UNREAL_GENERATORS = re.compile(r"^(create_(town|house|city|maze|building|castle|procedural\w*)|"
                               r"construct_|generate_(level|terrain|town|city|dungeon))", re.I)
# Fallback servers for UE 5.6/5.7 (ChiR24 Unreal_mcp) take one tool per area and the operation in
# `action`: these tools only read, and these actions only read, in any tool.
UNREAL_READ_ACTIONS = re.compile(
    r"^(get|find|list|describe|read|search|inspect|is|has|capture|screenshot|query|status|"
    r"profile|stat)(_\w+)?$", re.I)
UNREAL_READ_TOOLS_PLAIN = {"inspect"}
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
    if "patched_text" in tool_input:  # Codex / OpenCode apply_patch, hunks applied
        return tool_input["patched_text"]
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
        # a new task file: the producer creates tasks. A role's new file may not name the role
        # itself, or its paths would widen the role's own zone (bug hunt 2026-10-20).
        new = new_text_of(data, full) or ""
        if role in k.task_roles(new) or (data.get("tool_name") == "ShellWrite"
                                         and data.get("shell_mode") != "delete"):
            k.deny(f"{rel}: task files with a role line are the producer's. Put the follow-up "
                   "in your handoff (next: orchestrator) instead of creating a task for yourself.")
        return
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
    if KEY_VALUE.search(str(tool_input.get("content") or "") + str(tool_input.get("new_string") or "")):
        k.deny("That text holds an API key. Keys live in the user's environment (/kiln:settings), "
               "never in a file of the project.")
    if str(path or "").replace("\\", "/").lower().endswith(".codex/config.toml"):
        # field report 2026-10-19: an appended block without a final newline got Codex's next
        # table glued to it and Codex would not start
        k.deny("Codex's config.toml is changed only with Kiln's scripts/codex_config.py (--on / "
               "--off / --plugin <id> / --check / --repair): it keeps every other line, parses the "
               "result and keeps a backup. A hand edit can stop Codex from starting.")
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
        if engine == "unreal" and (k.path_matches(rel, UNREAL_ASSETS) or (
                re.search(r"(^|/)config/[^/]+\.ini$", rel.lower())
                and not re.search(r"(^|/)saved/", rel.lower()))):  # plugin and subfolder configs
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

    if engine == "godot" and rel.lower().endswith(".gd"):
        check_godot3(tool_input.get("content") or tool_input.get("new_string") or "", rel)
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

    if role and role not in k.KILN_ROLES and k.path_matches(rel, PROTECTED):
        k.deny(f"{rel} is framework configuration; only the main session changes it (on the "
               "user's word). Report the needed change instead.")
    if not role or role not in k.KILN_ROLES:
        # the main session (Codex too: its subagents' hooks always carry agent_id and
        # agent_type, "default" without a role - codex-rs hook_runtime.rs, 0.160-0.163), and
        # agents that are not Kiln roles (general-purpose, Codex default): the producer's rule,
        # so delegating to a built-in agent does not lift it (bug hunt 2026-10-20)
        state = STATE_FILES + notes_files(policy) + policy_list(policy, "state_paths")
        # shell output of the producer's own tools (reports, logs, recipes) is not policed here;
        # the engine-file rules above still apply to it
        if policy.get("orchestrator_writes", "state") == "state" and \
                data.get("tool_name") != "ShellWrite" and not k.path_matches(rel, state):
            k.deny(f"The main session coordinates; it does not write game content ({rel}). "
                   "Delegate to the Kiln role that owns this path (see the run skill), or set "
                   "orchestrator_writes=any in manifest.md if the user wants direct edits.")
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


def patch_files(patch):
    """[(path, kind, body lines)] for every file a Codex apply_patch touches, in order."""
    ops = []
    for line in patch.splitlines():
        m = PATCH_FILE.match(line)
        if m:
            ops.append((m.group(2), m.group(1), []))
        elif ops and not line.startswith("*** End"):
            ops[-1][2].append(line)
    return ops


def patch_operations(patch):
    """[(path, added_text)] for every file a Codex apply_patch touches, in order."""
    return [(path, "\n".join(l[1:] for l in lines if l.startswith("+")))
            for path, _, lines in patch_files(patch)]


def apply_hunks(old, lines):
    """The file after an Update File patch (context ' ', removed '-', added '+' lines in @@
    chunks), or None when a chunk does not match the file."""
    text, cursor = old.replace("\r\n", "\n"), 0
    chunks, cur = [], []
    for line in lines:
        if line.startswith("@@"):
            if cur:
                chunks.append(cur)
            cur = []
        elif line[:1] in (" ", "-", "+") or line == "":
            cur.append(line or " ")
    if cur:
        chunks.append(cur)
    for chunk in chunks:
        before = "\n".join(l[1:] for l in chunk if l[0] in " -")
        after = "\n".join(l[1:] for l in chunk if l[0] in " +")
        at = text.find(before, cursor) if before else len(text)
        if at < 0:
            return None
        if not before and text and not text.endswith("\n"):
            after = "\n" + after
        text = text[:at] + after + text[at + len(before):]
        cursor = at + len(after)
    return text


def check_patch(data, root, policy):
    """Codex file edits: run the Write checks once per file in the patch. The added lines are
    scanned as the content; the whole new file (hunks applied) is what the task-file rules compare
    (bug hunt 2026-10-20: added lines alone looked like a rewrite of every spec line)."""
    tool_input = data.get("tool_input") or {}
    base = data.get("cwd") or root
    for path, kind, lines in patch_files(str(tool_input.get("command") or "")):
        full = path if os.path.isabs(path) else os.path.join(base, path)
        added = "\n".join(l[1:] for l in lines if l.startswith("+"))
        patched = added if kind == "Add File" else "" if kind == "Delete File" else None
        if kind == "Update File":
            try:
                with open(full, encoding="utf-8", errors="ignore") as fh:
                    patched = apply_hunks(fh.read(), lines)
            except OSError:
                patched = None
        check_write({**data, "tool_input": {"file_path": full, "content": added,
                                            "patched_text": patched}}, root, policy)


# AI generators by policy (manifest model_generators / audio_generators: off | local | api).
MODEL_LOCAL = re.compile(r"\b(trellis|pixal3d|hunyuan3d|triposg|triposr|instantmesh|step1x-3d|"
                         r"direct3d-s2|hi3dgen|stable-fast-3d|sf3d|spar3d|partcrafter|omnipart|"
                         r"comfyui|diffusers|stable[-_]?diffusion|sdxl|flux\.?[12]|qwen-image)")
# Hosts checked 2026-10-19 (generator connectors research): Rodin moved to api.hyper3d.com;
# fal, Replicate, Tencent and 3D AI Studio host the same models. Stability's /audio/ endpoints
# are music and sound, the rest of api.stability.ai is image/3D.
MODEL_API = re.compile(r"(api\.tripo3d\.ai|api\.meshy\.ai|hyper3d\.(ai|com)|"
                       r"api\.stability\.ai(?!/v\w+/audio)|api\.retrodiffusion|pixellab\.ai|"
                       r"fal\.run|api\.replicate\.com|tencentcloudapi\.com|api\.sloyd\.ai|"
                       r"api\.3daistudio\.com|cloud\.leonardo\.ai|api\.cloud\.scenario\.com|"
                       r"api\.app\.layer\.ai)")
AUDIO_LOCAL = re.compile(r"\b(audiocraft|musicgen|ace-?step|stable[-_]audio|riffusion|yue|"
                         r"diffrhythm)")
AUDIO_API = re.compile(r"(suno\.com|udio\.com|api\.elevenlabs\.io|stableaudio\.com|"
                       r"api\.stability\.ai/v\w+/audio)")
# Video models (animation reference clips; research 2026-10-19): their own policy, so a yes to
# image-to-3D does not cover them. The Gemini host also serves text models: only Veo counts.
VIDEO_LOCAL = re.compile(r"(\bwan2\.[12]\b|wan-?video|\bwan2[._-]?[12]?-|hunyuanvideo|framepack|"
                         r"\bltx-?2\b|ltx-video|cogvideo)")
VIDEO_API = re.compile(r"(api\.x\.ai/\S*video|bytepluses\.com|api\.minimax\.io|klingai|"
                       r"api\.dev\.runwayml\.com|generativelanguage\.googleapis\.com/\S*veo-)")


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


def script_at(words, name):
    """Index of the Kiln script `name` a simple command runs (python [options] name, py -3 -u
    name, or name itself), or None. Interpreter options such as -X utf8 come before it (bug hunt
    2026-10-20: only the first three words were searched)."""
    if os.path.basename(words[0]).lower() == name:
        return 0
    if not PYTHON_EXE.match(words[0]):
        return None
    rest = list(enumerate(words))[1:]
    i = 0
    while i < len(rest):
        at, arg = rest[i]
        if arg in ("-c", "-m", "-"):
            return None
        if arg in ("-X", "-W", "-Q"):
            i += 2
            continue
        if not arg.startswith("-"):
            return at if os.path.basename(arg).lower() == name else None
        i += 1
    return None


def runs_gpu_job(command):
    """True when the command starts the gpu-server skill's job runner."""
    return any(script_at(words, "gpu_job.py") is not None for words in shell_segments(command))


GENERATOR_RULES = (("model_generators", MODEL_LOCAL, MODEL_API, "image/3D"),
                   ("audio_generators", AUDIO_LOCAL, AUDIO_API, "music/sound"),
                   ("video_generators", VIDEO_LOCAL, VIDEO_API, "video"))


def check_generators(low, policy):
    for key, local, api, what in GENERATOR_RULES:
        if policy.get(key) == "remote" and not runs_gpu_job(low):
            text = executed_text(low)
            if local.search(text) or api.search(text):
                k.deny(f"{key}=remote: {what} generators run only on the rented GPU server "
                       "through the gpu-server skill's gpu_job.py (spend cap, provenance, stop "
                       "after the job), not on this machine and not through paid APIs.")
    low = executed_text(low)
    for key, local, api, what in GENERATOR_RULES:
        mode = policy.get(key, "off")
        if mode == "off" and (local.search(low) or api.search(low)):
            k.deny(f"{what} generators are off for this project ({key}=off in manifest.md). "
                   "Make the asset with the normal pipeline, or ask the user to change the policy.")
        if mode == "local" and api.search(low):
            k.deny(f"{key}=local allows only local open-weight models, not paid APIs.")


# api-generators: gen_api.py hides the service hosts from the rules above, so its commands map
# to the policy here. services/balance are free reads; spending is never done under autopilot.
GEN_SERVICES = {"meshy": "model_generators"}
KEY_VARS = re.compile(r"\b(MESHY_API_KEY|TRIPO_API_KEY|HYPER3D_API_KEY|STABILITY_API_KEY|FAL_KEY|"
                      r"REPLICATE_API_TOKEN|ELEVENLABS_API_KEY|PIXELLAB_API_KEY|"
                      r"RETRODIFFUSION_API_KEY|RUNWAY_API_KEY|KLING_API_KEY|GEMINI_API_KEY|"
                      r"OPENAI_API_KEY|TENCENTCLOUD_SECRET_(ID|KEY))\b")
KEY_VALUE = re.compile(r"\b(msy_|tsk_|r8_|rdpk-|layer_pat_)[A-Za-z0-9_-]{16,}|\bsk-[A-Za-z0-9_-]{20,}")


def check_gen_api(command, root, policy, data=None):
    for words in shell_segments(command):
        at = script_at(words, "gen_api.py")
        if at is None or len(words) <= at + 1:
            continue
        verb = words[at + 1].lower()
        arg = words[at + 2].lower() if len(words) > at + 2 else ""
        if verb in ("services", "balance", "jobs", "actions", "decline"):
            continue
        service = arg.split("-", 1)[0]
        key = GEN_SERVICES.get(service, "model_generators")
        if policy.get(key, "off") != "api":
            k.deny(f"{key} is {policy.get(key, 'off')} in manifest.md: paid generators run only with "
                   f"{key}=api, which the user sets (/kiln:settings).")
        if verb == "submit" and os.path.exists(os.path.join(root, ".kiln", "autopilot")):
            k.deny("Spending money is never decided under autopilot: `gen_api.py request <job> "
                   "--why ...` puts the estimate into production/SPEND_REQUESTS.md for the user's "
                   "yes; go on with work that needs no money.")
        if verb == "submit" and not user_spoke_after(data or {}, root, arg):
            k.deny("The user has not answered since this estimate. Show them its ask_the_user "
                   "text and submit only after their yes.")


def user_spoke_after(data, root, job):
    """True unless the transcript shows no user message newer than the job's estimate (Claude
    Code passes transcript_path; without it, or unreadable, the check fails open)."""
    path = data.get("transcript_path") or ""
    try:
        with open(os.path.join(root, ".kiln", "gen", "jobs", job + ".json"), encoding="utf-8") as fh:
            since = float(json.load(fh).get("estimated_at") or 0)
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except (OSError, ValueError, TypeError, AttributeError):
        return True
    for line in reversed(lines):
        try:
            row = json.loads(line)
            stamp = row.get("timestamp") or ""
            when = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except (ValueError, AttributeError, TypeError):
            continue
        if when <= since:
            return False
        content = (row.get("message") or {}).get("content") if row.get("type") == "user" else None
        if row.get("isMeta") or content is None:
            continue
        if isinstance(content, str) or any(isinstance(b, dict) and b.get("type") == "text"
                                           for b in content):
            return True
    return False


# Vendor MCP servers of paid generators (a server name like meshy, claude_ai_ElevenLabs): the
# same policy as gen_api.py; under autopilot only their read calls (balance, status, lists).
VENDOR_MCP = k.VENDOR_MCP
VENDOR_READ = re.compile(r"^(get|list|search|check|retrieve|read|download|fetch)|"
                         r"(balance|status|credits)", re.I)


def vendor_policy_key(tool):
    server = tool.split("__")[1].lower() if tool.count("__") >= 2 else ""
    # the vendor's own server name (meshy, fal-ai, elevenlabs-mcp, claude_ai_Meshy), not any
    # server that merely contains the word (a project's scenario-runner is not Scenario)
    return next((key for key, names in VENDOR_MCP.items()
                 if re.fullmatch(rf"(claude_ai_)?({names})([_-]?(mcp|ai|api|server|official))*",
                                 server)), None)


def check_vendor_mcp(data, root, policy):
    tool = data.get("tool_name") or ""
    key = vendor_policy_key(tool)
    if not key:
        return
    if policy.get(key, "off") != "api":
        k.deny(f"{tool} is a paid generator and {key} is {policy.get(key, 'off')} in manifest.md "
               f"(only {key}=api, which the user sets with /kiln:settings).")
    if os.path.exists(os.path.join(root, ".kiln", "autopilot")) and \
            not VENDOR_READ.search(tool.rsplit("__", 1)[-1]):
        k.deny("Spending money is never decided under autopilot: list the request in "
               "production/SPEND_REQUESTS.md (asset, service, cost, why) for the user's yes.")


def check_asset_libraries(command, policy):
    if policy.get("asset_libraries", "attribution") != "off":
        return
    for words in shell_segments(command):
        at = script_at(words, "assets_api.py")
        if at is not None and len(words) > at + 1 and words[at + 1].lower() in ("fetch", "import"):
            k.deny("asset_libraries=off in manifest.md: nothing is downloaded from free "
                   "libraries in this project (the user changes it with /kiln:settings).")


REMOVERS = {"remove-item", "ri", "rm", "del", "erase", "rd", "rmdir"}


def is_junction(path):
    if hasattr(os.path, "isjunction"):
        return os.path.isjunction(path)
    try:
        return bool(os.lstat(path).st_file_attributes & 0x400) and not os.path.islink(path)
    except (OSError, AttributeError):
        return False


def holds_junction(path, limit=20000):
    """The first junction at or under `path` (not followed), or None."""
    if is_junction(path):
        return path
    seen = 0
    for dirpath, dirnames, _ in os.walk(path):
        for d in list(dirnames):
            full = os.path.join(dirpath, d)
            if is_junction(full):
                return full
        seen += len(dirnames)
        if seen > limit:
            return None
    return None


def check_junction_remove(data, root):
    """Windows PowerShell 5.1 `Remove-Item -Recurse` walks into a junction and deletes the
    target's files (install audit 2026-10-19: the shared Godot AI addon, the Kiln clone)."""
    if os.name != "nt":
        return
    tool = data.get("tool_name") or ""
    command = (data.get("tool_input") or {}).get("command") or ""
    base = data.get("cwd") or root
    for words in shell_segments(command):
        prog = program(words).removesuffix(".exe").lower()
        if prog not in REMOVERS or (tool != "PowerShell" and prog != "remove-item"):
            continue
        if prog in ("rd", "rmdir") and tool != "PowerShell":
            continue
        flags = [w.lower() for w in words[1:] if w.startswith("-")]
        if not any(f in ("-r", "-recurse", "-rf", "-fr") or f.startswith("-rec") for f in flags):
            continue
        paths, skip = [], False
        for w in words[1:]:
            if skip:
                paths.append(w)
                skip = False
            elif w.lower() in ("-path", "-literalpath", "-lp"):
                skip = True
            elif not w.startswith("-"):
                paths.append(w)
        for p in paths:
            full = p if os.path.isabs(p) else os.path.join(base, p)
            for target in glob.glob(full) or [full]:
                found = holds_junction(target) if os.path.isdir(target) else None
                if found:
                    k.deny(f"{found} is a junction (a link to a folder shared outside this "
                           "project): Remove-Item -Recurse in Windows PowerShell follows it and "
                           "deletes the shared files. Remove the link itself first: "
                           f"cmd /c rmdir \"{found}\" (or [IO.Directory]::Delete(...)), then the "
                           "rest.")


def check_key_exposure(command):
    """No command shows an API key: the keys stay in the environment, out of every transcript."""
    for words in shell_segments(command):
        prog = program(words).removesuffix(".exe").lower()
        if prog in ("git", "gh"):
            continue
        text = " ".join(words)
        if (prog in ("printenv", "env", "set") and len(words) == 1) or \
                re.search(r"\b(get-childitem|gci|dir|ls)\s+env:", text, re.I) or KEY_VARS.search(text):
            k.deny("API keys stay in the environment and out of the conversation: no command may "
                   "print or pass a key variable. gen_api.py reads the key itself; `gen_api.py "
                   "services` says whether one is set.")


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
            # `python - <<EOF`, `cat <<EOF | python -`, `uv run python - <<EOF` (bug hunt
            # 2026-10-20: only a python at the head of the line counted)
            to_python = any(starts_python(part) for part in line.replace("\\", "/").split("|"))
    return "\n".join(out), python_bodies


def starts_python(text):
    """True when this simple command starts a Python interpreter (VAR=x and uv run / uvx /
    uv tool run in front of it allowed)."""
    words = text.strip().split()
    while words and re.match(r"^\w+=", words[0]):
        words.pop(0)
    if words[:3] == ["uv", "tool", "run"]:
        words = words[3:]
    elif words[:2] == ["uv", "run"] or words[:1] == ["uvx"]:
        words = [w for w in words[1 if words[0] == "uvx" else 2:] if not w.startswith("-")]
    return bool(words) and bool(PYTHON_EXE.match(words[0].strip("'\"")))


IMPORTS_BPY = re.compile(r"\bimport\s+(?:[\w.]+\s*(?:as\s+\w+\s*)?,\s*)*bpy\b|\bfrom\s+bpy\b|"
                         r"__import__\(\s*['\"]bpy")


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
    yield from _segments(strip_heredocs(command).replace("\\", "/"), 0)


SUBSTITUTION = re.compile(r"\$\(([^()]*)\)|`([^`]*)`")
SHELL_WRAPPERS = {"bash": ("-c",), "sh": ("-c",), "zsh": ("-c",), "dash": ("-c",),
                  "cmd": ("/c", "/k"), "powershell": ("-c", "-command"),
                  "pwsh": ("-c", "-command")}


def _segments(text, depth):
    for seg in split_unquoted(text):
        if depth < 4:  # $(godot-ai ...) runs too (bug hunt 2026-10-20)
            for m in SUBSTITUTION.finditer(seg):
                yield from _segments(m.group(1) or m.group(2) or "", depth + 1)
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
        if not words:
            continue
        # `bash -c '...'`, `cmd /c ...`, `powershell -Command ...`: the inner command is what runs
        flags = SHELL_WRAPPERS.get(os.path.basename(words[0]).lower().removesuffix(".exe"))
        at = next((i for i, w in enumerate(words[1:], 1) if w.lower() in (flags or ())), None)
        if at is not None and depth < 4:
            yield from _segments(" ".join(words[at + 1:]) if len(words) > at + 2
                                 else (words[at + 1] if len(words) > at + 1 else ""), depth + 1)
            continue
        yield words


def program(words):
    return os.path.basename(words[0]).lower()


def python_pipelines(command):
    """Pipelines (a | b | c) of the command that start a Python interpreter: text in them is its
    code or its stdin; text in other pipelines (a search, a commit message) is not."""
    out = []
    for pipe in re.split(r"&&|\|\||;|\n", command):
        if any(starts_python(part) for part in pipe.split("|")):
            out.append(pipe)
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
PS_WRITE = {"set-content", "add-content", "out-file", "sc", "ac"}
PS_COPY = {"copy-item", "move-item", "cp", "mv", "copy", "move", "cpi", "mi"}
CD_PROGS = {"cd", "chdir", "pushd", "set-location", "sl"}


def shell_write_targets(command, base=None):
    """[(path, mode)] a shell command writes: redirections, tee, cp/mv destinations, sed -i,
    PowerShell Set-Content / Add-Content / Out-File / New-Item -Value / Copy-Item / Move-Item /
    Rename-Item. mode is 'append' for >> and tee -a / Add-Content, else 'write'. Here-document
    bodies are not commands. With `base` (the shell's folder), `cd` moves it and relative paths
    come back absolute (bug hunt 2026-10-20: `cd scenes && echo x > ../project.godot`)."""
    out = []
    for seg in split_unquoted(strip_heredocs(command).replace("\\", "/")):
        cd = None
        start = len(out)
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
        prog = os.path.basename(words[0]).lower().removesuffix(".exe") if words else ""
        args = words[1:]
        if prog in CD_PROGS and base:
            named, positional = ps_args(args)
            dest = named.get("-path") or named.get("-literalpath") or \
                (positional[0] if positional else None)
            if dest and dest != "-":
                cd = dest if os.path.isabs(dest) else os.path.join(base, dest)
        elif prog == "tee":
            mode = "append" if any(a in ("-a", "--append") for a in args) else "write"
            out += [(a, mode) for a in args if not a.startswith("-")]
        elif prog == "sed" and any(a == "-i" or a.startswith("-i") or a == "--in-place"
                                   for a in args):
            files = [a for a in args if not a.startswith("-")][1:]
            out += [(f, "write") for f in files]
        elif prog in ("cp", "mv", "install", "ln") or (prog in PS_COPY and not any(
                a.lower().startswith("-dest") for a in args)):
            out += [(t, "write") for t in copy_targets(args, base)]
        elif prog in PS_WRITE or (prog in ("new-item", "ni") and any(
                ps_param(a) == "-value" for a in args)):
            named, positional = ps_args(args)
            target = next((named[p] for p in ("-path", "-literalpath", "-filepath")
                           if p in named), None) or (positional[0] if positional else None)
            if target:
                out.append((target, "append" if prog in ("add-content", "ac") else "write"))
        if prog in PS_COPY or prog in ("rename-item", "ren", "rni"):
            named, positional = ps_args(args)
            if prog in ("rename-item", "ren", "rni"):
                src = named.get("-path") or named.get("-literalpath") or \
                    (positional[0] if positional else None)
                new = named.get("-newname") or (positional[1] if len(positional) > 1 else None)
                if src and new:
                    out.append((posixpath.join(posixpath.dirname(src), new), "write"))
            elif "-destination" in named:
                srcs = [named[p] for p in ("-path", "-literalpath") if p in named] or positional
                out += [(t, "write") for t in into_folder(named["-destination"], srcs, base)]
        if base:
            out[start:] = [(p if os.path.isabs(p) or p.lower() in NULL_TARGETS
                            else os.path.join(base, p), m) for p, m in out[start:]]
        if cd is not None:
            base = cd
    return [(p, m) for p, m in out if p.lower() not in NULL_TARGETS]


# PowerShell parameters that take a value: the value is not a path (bug hunt 2026-10-20: the
# guard took `utf8` of `Out-File -Encoding utf8 scenes/main.tscn` for the target).
PS_VALUE_PARAMS = ("-value", "-encoding", "-path", "-literalpath", "-filepath", "-width",
                   "-stream", "-filter", "-include", "-exclude", "-credential", "-itemtype",
                   "-name", "-inputobject", "-destination", "-newname", "-delimiter")


def ps_param(arg):
    """The full name of a PowerShell parameter (`-Enc` -> -encoding, `-Path:x` -> -path)."""
    low = arg.lower().split(":", 1)[0]
    if not low.startswith("-") or len(low) < 2:
        return None
    hits = [p for p in PS_VALUE_PARAMS if p.startswith(low)]
    return low if low in PS_VALUE_PARAMS else (hits[0] if len(hits) == 1 else low)


def ps_args(args):
    """({parameter: value}, positional arguments) of a PowerShell cmdlet call."""
    named, positional, i = {}, [], 0
    while i < len(args):
        a = args[i]
        p = ps_param(a)
        if p and p in PS_VALUE_PARAMS:
            if ":" in a:
                named[p] = a.split(":", 1)[1]
            elif i + 1 < len(args):
                named[p] = args[i + 1]
                i += 1
        elif not p:
            positional.append(a)
        i += 1
    return named, positional


def into_folder(dest, srcs, base):
    """A copy's written paths: dest itself, or dest/<name> per source when dest is a folder."""
    full = dest if os.path.isabs(dest) or not base else os.path.join(base, dest)
    if dest.endswith("/") or os.path.isdir(full):
        return [posixpath.join(dest, posixpath.basename(s.rstrip("/"))) for s in srcs] or [dest]
    return [dest]


def copy_targets(args, base):
    """Written paths of cp / mv / install / ln and PowerShell copy aliases with positional
    arguments: the last argument, or every source inside it when it is a folder; -t DIR."""
    target_dir, plain, skip = None, [], False
    for i, a in enumerate(args):
        if skip:
            skip = False
            continue
        if a in ("-t", "--target-directory"):
            target_dir = args[i + 1] if i + 1 < len(args) else None
            skip = True
        elif a.startswith("--target-directory="):
            target_dir = a.split("=", 1)[1]
        elif a in ("-S", "--suffix", "-m", "--mode", "-o", "--owner", "-g", "--group"):
            skip = True
        elif not a.startswith("-"):
            plain.append(a)
    if target_dir:
        return [posixpath.join(target_dir, posixpath.basename(s.rstrip("/"))) for s in plain]
    if len(plain) < 2:
        return []
    return into_folder(plain[-1], plain[:-1], base)


REMOVE_PROGS = {"rm", "del", "erase", "rd", "rmdir", "unlink", "remove-item", "ri", "shred"}
MOVE_PROGS = {"mv", "move", "move-item", "mi", "rename-item", "ren", "rni"}


def shell_removed_paths(command, base):
    """Absolute paths a shell command deletes, moves or renames away (the source of mv; git rm /
    git mv); `cd` moves the base."""
    found = []
    for words in shell_segments(command):
        out = []
        prog = program(words).removesuffix(".exe")
        args = words[1:]
        if prog in CD_PROGS:
            named, positional = ps_args(args)
            dest = named.get("-path") or named.get("-literalpath") or \
                (positional[0] if positional else None)
            if dest and dest != "-":
                base = dest if os.path.isabs(dest) else os.path.join(base, dest)
        elif prog == "git" and args[:1] in (["rm"], ["mv"]):
            plain = [a for a in args[1:] if not a.startswith("-")]
            out += plain if args[0] == "rm" else plain[:-1]
        elif prog in REMOVE_PROGS:
            named, positional = ps_args(args) if prog in ("remove-item", "ri") else ({}, [
                a for a in args if not a.startswith("-") and not re.fullmatch(r"/[a-zA-Z]", a)])
            out += [named[p] for p in ("-path", "-literalpath") if p in named] + positional
        elif prog in MOVE_PROGS:
            if prog in ("mv", "move") and not any(a.lower().startswith("-dest") for a in args):
                plain = [a for a in args if not a.startswith("-")]
                out += plain[:-1]
            else:
                named, positional = ps_args(args)
                srcs = [named[p] for p in ("-path", "-literalpath") if p in named]
                out += srcs or positional[:1]
        found += [p if os.path.isabs(p) else os.path.join(base, p) for p in out]
    return found


def check_shell_removals(data, root, policy):
    """Deleting, moving or renaming a file is a change to it: framework files (manifest.md - every
    Kiln hook stops without it -, agent and runtime settings) and engine files follow the Write
    rules (bug hunt 2026-10-20: `mv manifest.md manifest.bak` switched Kiln off)."""
    command = (data.get("tool_input") or {}).get("command") or ""
    for path in shell_removed_paths(command, data.get("cwd") or root):
        rel = k.rel_path(root, path)
        if rel is None:
            continue
        rel = rel.rstrip("/")
        if rel in ("", ".") or k.path_matches(rel, PROTECTED) or any(
                p.lower().startswith(rel.lower() + "/") for p in PROTECTED):
            k.deny(f"{rel or 'the project folder'}: deleting or moving framework files "
                   "(manifest.md, agent and runtime settings) turns Kiln's rules off. Ask the user.")
        check_write({**data, "tool_name": "ShellWrite", "shell_mode": "delete",
                     "tool_input": {"file_path": path, "content": ""}}, root, policy)


def check_shell_writes(data, root, policy):
    """A file written by a shell command passes the same checks as a Write of that file."""
    command = (data.get("tool_input") or {}).get("command") or ""
    for target, mode in shell_write_targets(command, data.get("cwd") or root):
        path = target if os.path.isabs(target) else os.path.join(root, target)
        if path.replace("\\", "/").lower().endswith(".codex/config.toml"):
            check_write({**data, "tool_input": {"file_path": path, "content": ""}}, root, policy)
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


def res_rel(path):
    """A res:// or project path, normalised ('..' resolved); '' when it leaves the project, so
    `tests/probes/../../scripts/x.gd` is scripts/x.gd, not a probe (bug hunt 2026-10-20)."""
    rel = re.sub(r"^(res://|\./|/)+", "", str(path or "").replace("\\", "/"))
    rel = posixpath.normpath(rel) if rel else ""
    return "" if rel == ".." or rel.startswith("../") else rel


def headless_probe(words, script):
    """Parse checks and test probes may run headless; scripts that build content may not."""
    rel = res_rel(script)
    return "--check-only" in words or rel.startswith(("tests/", ".kiln/"))


def kills_by_name(words):
    prog = program(words).removesuffix(".exe")
    args = [a.lower() for a in words[1:]]
    if prog == "taskkill":
        return "/im" in args or "-im" in args
    if prog in ("pkill", "killall"):
        return True
    if prog in ("stop-process", "spps", "kill"):
        # by name: -Name / -ProcessName, or a positional that is not a PID (`Stop-Process 1234`
        # and PowerShell's `kill 1234` stop one process - bug hunt 2026-10-20)
        named = {ps_param(a) for a in args if a.startswith("-")}
        positional = [a for i, a in enumerate(args) if not a.startswith("-")
                      and not (i and args[i - 1].startswith("-") and
                               args[i - 1] not in ("-force", "-passthru"))]
        if prog == "kill":
            return "-name" in named or "-processname" in named
        by_pid = ("-id" in named or "-processid" in named or
                  any(re.fullmatch(r"[\d,\s]+", p) for p in positional))
        # piped (`Get-Process python | Stop-Process`) or by name: every process of that name
        return not by_pid or "-name" in named or "-processname" in named
    return False


def join_continuations(command):
    """One logical line per command: bash `\\` and PowerShell backtick line continuations are
    joined before any check reads the command (bug hunt 2026-10-20: `git push \\<newline>
    --force` and `cp x \\<newline> scenes/main.tscn` passed every shell rule). Here-document
    bodies are data and stay as they are, so their end marker is still found."""
    out, end, cur = [], None, None
    for line in command.replace("\r\n", "\n").split("\n"):
        if end is not None:
            out.append(line)
            if line.strip() == end:
                end = None
            continue
        cur = line if cur is None else cur + " " + line.lstrip()
        stripped = cur.rstrip(" \t")
        if stripped.endswith(("\\", "`")) and not stripped.endswith("\\\\"):
            cur = stripped[:-1]
            continue
        out.append(cur)
        m = HEREDOC.search(cur)
        if m:
            end = m.group(2)
        cur = None
    if cur is not None:
        out.append(cur)
    return "\n".join(out)


def check_shell(data, root, policy):
    command = join_continuations((data.get("tool_input") or {}).get("command") or "")
    if not command.strip():
        return
    data = {**data, "tool_input": {**(data.get("tool_input") or {}), "command": command}}
    low = command.lower()
    role = k.role_of(data)

    check_shell_writes(data, root, policy)
    check_shell_removals(data, root, policy)
    windowed = any(windowed_godot_run(w) for w in shell_segments(command))
    if windowed and policy.get("on_screen") == "slot" and not screen_free(root):
        k.deny(SLOT_REASON)
    check_generators(low, policy)
    check_gen_api(command, root, policy, data)
    check_asset_libraries(command, policy)
    check_key_exposure(command)
    check_junction_remove(data, root)
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
        if invoked and (any(IMPORTS_BPY.search(pipe) for pipe in python_pipelines(outside)) or any(
                IMPORTS_BPY.match(line.strip()) for body in python_bodies
                for line in body.splitlines())):
            k.deny("bpy code must run inside the user's Blender through the Blender Lab MCP "
                   "(execute_blender_code), not from the shell.")
        for path in scripts:
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    if any(IMPORTS_BPY.match(line.strip()) for line in fh.read().splitlines()):
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
        # an agent CLI registering the server (`claude|codex|gemini|copilot|opencode mcp add ...
        # http://localhost:8080/mcp`, setup §6) names the port without connecting to it
        connecting = " ".join(" ".join(w) for w in calls if not (
            re.sub(r"\.(exe|cmd)$", "", program(w)) in ("claude", "codex", "gemini", "copilot",
                                                         "opencode") and "mcp" in w[1:3]))
        if re.search(r"(127(\.\d{1,3}){0,3}|localhost|\[::1\]|0\.0\.0\.0):(9876|9500|8000|8080)\b",
                     connecting.lower()):
            k.deny("Direct connections to the editors' MCP ports (Blender, Godot, Unity, Unreal) "
                   "are not allowed; use the MCP tools.")
        # Unity: only the release build method (release skill: KilnRelease.KilnBuild.Build, or the
        # methods listed in manifest unity_build_methods) runs headless; a class or method that
        # merely contains "build" (LevelBuilder.GenerateTown) does not (bug hunt 2026-10-20)
        allowed = {m.lower() for m in policy_list(policy, "unity_build_methods",
                                                  "KilnRelease.KilnBuild.Build")}
        for m in re.finditer(r"-executemethod\s+([\w.]+)", low):
            if re.search(r"-batchmode\b", low) and m.group(1) not in allowed:
                k.deny(f"Headless Unity method {m.group(1)} is not a release build method. Editor "
                       "work goes through MCP for Unity in the open editor; builds use the "
                       "release skill's build method (manifest unity_build_methods lists others).")
        # Unreal: no Python, no commandlet other than the cook / test ones, no ExecCmds that run
        # Python, outside the open editor
        if re.search(r"(-executepythonscript|-run=pythonscript)", low) or \
                re.search(r"-execcmds\s*=\s*['\"]?[^'\"]*\bpy\s", low) or \
                any(c not in ("cook", "derivedDataCache".lower(), "compileallblueprints")
                    for c in re.findall(r"-run=(\w+)", low)):
            k.deny("Headless Unreal editor scripts and commandlets are not allowed for editor "
                   "work; use the Unreal MCP in the open editor (builds: RunUAT BuildCookRun).")
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

    # git hygiene (user's commit policy): stage specific files, no force push, no secrets.
    # Parsed per simple command, options by meaning (bug hunt 2026-10-20: -vA, :/, -uf, +HEAD,
    # commit -n, `git -C . add -A` passed the old patterns; a commit message quoting
    # --no-verify was denied).
    staged, cwd = [], data.get("cwd") or root
    for words in shell_segments(command):
        if program(words).removesuffix(".exe") in CD_PROGS and len(words) > 1:
            dest = words[1] if not words[1].lower().startswith("-") else \
                (words[2] if len(words) > 2 else "")
            if dest and dest != "-":
                cwd = dest if os.path.isabs(dest) else os.path.join(cwd, dest)
            continue
        check_git(words, root, staged, cwd)


GIT_GLOBAL_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
                    "--config-env", "--super-prefix"}
GIT_ALL_PATHS = {".", "./", ":/", ":/.", "*", ":(top)", ":(glob)**", "-A", "--all"}


def git_subcommand(words):
    """(subcommand, its arguments) of a git command line, global options skipped, or (None, [])."""
    sub, args, _ = git_context(words, ".")
    return sub, args


def git_context(words, cwd):
    """(subcommand, its arguments, (folder, global options)) of a git command line: the folder
    after every -C (each relative to the one before) and the --git-dir / --work-tree it names,
    so the secrets check reads the index the command acts on (review 2026-10-21, KILN-REV-04:
    `git -C nested commit` was checked against the Kiln root's index)."""
    if program(words).removesuffix(".exe") != "git":
        return None, [], (cwd, [])
    i, where, extra = 1, cwd, []
    while i < len(words) and words[i].startswith("-"):
        w = words[i]
        name, _, inline = w.partition("=")
        value = inline if inline else (words[i + 1] if i + 1 < len(words) else "")
        if w == "-C":
            where = value if os.path.isabs(value) else os.path.join(where, value)
        elif name in ("--git-dir", "--work-tree"):
            path = value if os.path.isabs(value) else os.path.join(where, value)
            extra.append(f"{name}={path}")
        i += 2 if w in GIT_GLOBAL_VALUE else 1
    sub = (words[i].lower(), words[i + 1:]) if i < len(words) else (None, [])
    return sub[0], sub[1], (where, extra)


def short_flags(args, value_letters):
    """Letters of the short-option clusters (-vA, -uf), stopping at a value-taking letter."""
    letters, skip = set(), False
    for a in args:
        if skip:
            skip = False
            continue
        if a == "--":
            break
        if a.startswith("-") and not a.startswith("--") and len(a) > 1:
            for j, ch in enumerate(a[1:]):
                letters.add(ch)
                if ch in value_letters:
                    skip = j == len(a) - 2
                    break
    return letters


def check_git(words, root, staged, cwd=None):
    sub, args, (where, extra) = git_context(words, cwd or root)
    if sub is None:
        return
    repo = os.path.normcase(os.path.abspath(where)) + "|" + "|".join(extra)

    def names(*git_args):
        return git_names(where, *extra, *git_args)
    long_opts = {a.split("=", 1)[0] for a in args if a.startswith("--")}
    if sub == "add":
        plain = [a for a in args if not a.startswith("-") or a == "-"]
        literal = args[args.index("--") + 1:] if "--" in args else []
        if "A" in short_flags(args, "") or "--all" in long_opts or \
                any(p.rstrip("/") in ("", ".", ":", ":/.") or p in GIT_ALL_PATHS
                    for p in plain + literal):
            k.deny("Stage specific files (git add <paths>), not everything — framework state and "
                   "generated files must not slip into commits.")
        for name in plain + literal:
            if is_secret_file(name):
                k.deny(f"{name} is a secrets file: never stage it. Make sure it is git-ignored.")
            if os.path.isdir(os.path.join(where, name)):
                for found in names("ls-files", "--others", "--modified", "--exclude-standard",
                                   "--", name):
                    if is_secret_file(found):
                        k.deny(f"git add {name} would stage {found}, a secrets file. Stage the "
                               "files you mean by name and git-ignore it.")
                    staged.append((repo, found))
            else:
                staged.append((repo, name))
    if sub == "push":
        refs = [a for a in args if not a.startswith("-")]
        if "f" in short_flags(args, "o") or "--force" in long_opts or \
                any(r.startswith("+") for r in refs):
            k.deny("Force push is not allowed. Use --force-with-lease only if the user asked.")
    if sub in ("commit", "push", "merge", "rebase", "am", "cherry-pick", "revert", "pull"):
        if "--no-verify" in long_opts or (sub == "commit" and "n" in short_flags(args, "mFCctS")):
            k.deny("Do not skip git hooks (--no-verify / commit -n).")
    if sub == "commit":
        paths, everything = commit_paths(["git", "commit"] + args)
        found = names("diff", "--cached", "--name-only") + paths + \
            [n for r, n in staged if r == repo]
        if everything:  # -a commits every modified tracked file
            found += names("diff", "--name-only")
        for name in found:
            if is_secret_file(name):
                k.deny(f"{name} would be committed; secrets files must not be committed. "
                       "Unstage it (git restore --staged), leave it out of the commit and "
                       "make sure it is git-ignored.")


SECRET_NAME = re.compile(r"\.env(\..+)?|.+\.(key|pem|p12|pfx)|credentials\.json|"
                         r"client_secret.*\.json", re.I)


def is_secret_file(name):
    """The user's commit policy: .env files, keys and certificates, credentials, secrets/."""
    path = name.replace("\\", "/").rstrip("/")
    base = path.rsplit("/", 1)[-1]
    if base == ".env.example":
        return False
    return bool(SECRET_NAME.fullmatch(base)) or "secrets" in path.lower().split("/")


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
        ttl = k.number(policy, "editor_lock_other_session_ttl", 120)
    else:
        ttl = k.number(policy, "editor_lock_ttl", 600)
    # The main session hands the editor to the role it delegates to: its own doctor probes must
    # not lock its agents out (live: the producer's probe blocked the animator for the TTL).
    handed_over = held and held.get("owner") == "main" and me != "main" and \
        held.get("session", session) == session
    # The queue (g2 row 6): a refused caller waits in line instead of retrying blind; a holder
    # past its lease hands over when someone waits; a free editor goes to the head of the line.
    qpath = os.path.join(os.path.dirname(path), "queue.json")
    queues = k.load_json(qpath, {})
    line = [w for w in queues.get(resource, []) if now - w.get("ts", 0) < QUEUE_STALE_S]
    lease = k.number(policy, "editor_lease_s", 900)

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
    rel = res_rel(path)
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
        rel = res_rel(tool_input.get("path"))
        if rel and k.path_matches(rel, GODOT_REVIEW_WRITES):
            return
    allowed = GODOT_REVIEW_OPS.get(tool)
    if allowed is None or op not in allowed:
        k.deny(f"{role} is read-only: {tool} {op} can change the project. Run, observe and "
               "probe the game; describe the change in your handoff for the owning role.")
    if tool == "filesystem_manage" and op == "write_text":
        rel = res_rel(params.get("path") or tool_input.get("path"))
        if not rel or not k.path_matches(rel, GODOT_REVIEW_WRITES):
            k.deny(f"{role} may write files through the Godot MCP only under "
                   f"{', '.join(GODOT_REVIEW_WRITES)} (probes, captures, reports).")


_GODOT_LINT = None


def check_godot3(code, path):
    """Godot 3 API in GDScript (engine-godot godot_lint.py's table): models trained on public code
    write Godot 3 forms that fail in 4.x; the error names the Godot 4 form."""
    global _GODOT_LINT
    if not code:
        return
    if _GODOT_LINT is None:
        scripts = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "skills", "engine-godot", "scripts")
        sys.path.insert(0, scripts)
        try:
            import godot_lint
            _GODOT_LINT = godot_lint
        except ImportError:
            _GODOT_LINT = False
        finally:
            sys.path.remove(scripts)
    if not _GODOT_LINT:
        return
    hits = [h for h in _GODOT_LINT.lint_gdscript(code) if h["severity"] == "error"]
    if hits:
        k.deny(f"{path or 'This script'} uses Godot 3 API: " + "; ".join(
            f"line {h['line']} `{h['found']}` -> {h['godot4']}" for h in hits[:8]) +
            ". Write the Godot 4 form (engine-godot godot4-pitfalls.md; confirm with api_manage). "
            "A deliberate use (a comment quoting Godot 3) can carry '# kiln:godot3-ok'.")


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


# Editor calls that change the project, in C# a read-only role sends through execute_code (bug
# hunt 2026-10-20: the kiln:probe marker alone let a probe save the scene).
UNITY_CODE_WRITES = re.compile(
    r"\b(EditorSceneManager\s*\.\s*(Save|Mark|NewScene|OpenScene|CloseScene)|"
    r"AssetDatabase\s*\.\s*(Create|Delete|Move|Copy|Import|Save|Rename|Refresh|StartAssetEditing|"
    r"ForceReserialize)|PrefabUtility\s*\.\s*(Save|Apply|Revert|Unpack|Replace|Instantiate)|"
    r"DestroyImmediate|EditorUtility\s*\.\s*SetDirty|Undo\s*\.\s*Record|"
    r"(File|Directory)\s*\.\s*(Write|Create|Delete|Move|Copy|Append|Replace)|PlayerSettings\s*\.|"
    r"BuildPipeline\s*\.|AssetImporter|\bnew\s+GameObject\b|CreatePrimitive|AddComponent\s*<)")
# Tool groups (MCP for Unity v10.3.0 manage_tools): visibility is per session, so a fresh
# session's read-only role must be able to turn on the groups its probes need.
UNITY_READ_GROUPS = {"testing", "scripting_ext", "profiling", "docs"}


def unity_is_read(short, tool_input):
    """Read-only use of an MCP for Unity tool (names and actions from its v10.3.0 sources)."""
    action = str(tool_input.get("action") or "")
    if short == "execute_code":
        code = str(tool_input.get("code") or "")
        return action in ("", "execute") and "kiln:probe" in code and \
            not UNITY_CODE_WRITES.search(re.sub(r"//[^\n]*", "", code))
    if short == "manage_tools":
        return action in ("list_groups", "sync") or (
            action == "activate" and str(tool_input.get("group") or "") in UNITY_READ_GROUPS)
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
                   "execute, code marked '// kiln:probe') that read state - no saving, asset, "
                   "prefab, settings, file or object-creating calls.")
        k.deny(f"{role} is read-only: {tool} {action} changes the project. Describe the "
               "change in your handoff for the owning role.")
    if policy.get("scene_first", "on") != "on":
        return
    if tool == "execute_code":  # scenes are not built in bulk through code (engine-unity)
        hits = csharp_constructions(str(tool_input.get("code") or ""))
        if hits:
            k.deny(scene_first_reason(hits, "//"))
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
        action = str(args.get("action") or "")
        if re.search(r"console", name + " " + action, re.I):
            return bool(UNREAL_SAFE_CONSOLE.match(str(args.get("command") or args.get("cmd") or "")))
        if action:  # a fallback server: the operation is the action (bug hunt 2026-10-20)
            if UNREAL_CHANGE_WORD.search(action):
                return False
            return name in UNREAL_READ_TOOLS_PLAIN or bool(UNREAL_READ_ACTIONS.match(action)) or \
                bool(re.fullmatch(r"(start|stop)_?pie|(run|stop)_?tests|kiln_probe\w*|"
                                  r"inject_input\w*|highres_shot", action, re.I))
        return bool(UNREAL_READ_TOOLS.match(name)) and not UNREAL_CHANGE_WORD.search(name)
    return False


def check_unreal(data, policy, role):
    name, args = unreal_call(data)
    if role in MCP_READ_ONLY and not is_engine_read(data):
        k.deny(f"{role} is read-only: Unreal tool {name or data.get('tool_name')} may change the "
               "project. Read-only roles use get/find/list/capture/log/PIE/test tools, the Kiln "
               "probe toolset and stat/csvprofile/trace console commands. Describe the change in "
               "your handoff for the owning role.")
    action = str(args.get("action") or "")
    if policy.get("scene_first", "on") == "on" and (UNREAL_GENERATORS.match(name) or
                                                     UNREAL_GENERATORS.match(action)):
        k.deny(f"{action or name} generates level content procedurally. Build levels by placing actors, "
               "level instances and packed level actors in the open editor so the user can edit "
               "them by hand.")


GAME_START = re.compile(r"__(project_run|startpie)$|__manage_editor$", re.I)


def starts_windowed_game(data):
    """Godot project_run, Unity Play mode (manage_editor play, the Edit/Play menu item), Unreal
    PIE - Epic's server wraps it in call_tool, fallback servers put it in `action` (bug hunt
    2026-10-20: neither was seen)."""
    tool = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}
    if tool.endswith("__execute_menu_item"):
        return re.sub(r"\s", "", str(tool_input.get("menu_path") or tool_input.get("menuPath")
                                     or tool_input.get("path") or "")).lower() == "edit/play"
    if UNREAL_PREFIX.match(tool):
        name, args = unreal_call(data)
        return bool(re.fullmatch(r"(start_?pie|play_in_editor|play)", name, re.I) or
                    re.fullmatch(r"(start_?pie|play_in_editor|play)", str(args.get("action") or ""),
                                 re.I))
    if not GAME_START.search(tool):
        return False
    if tool.endswith("__manage_editor"):  # MCP for Unity: action play enters Play mode
        return str(tool_input.get("action") or "").lower() == "play"
    return True


def check_mcp(data, root, policy):
    tool = data.get("tool_name") or ""
    role = k.role_of(data)
    if policy.get("on_screen") == "slot" and starts_windowed_game(data) and not screen_free(root):
        k.deny(SLOT_REASON)
    if tool.startswith("mcp__godot-ai__"):
        if tool.endswith(("__script_create", "__script_patch")):
            rel = str((data.get("tool_input") or {}).get("path") or "")
            deny_acceptor_probe(res_rel(rel), role)
            ti = data.get("tool_input") or {}
            check_godot3(str(ti.get("content") or ti.get("new_text") or ""), rel)
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
    elif tool.startswith("mcp__"):
        check_vendor_mcp(data, root, policy)


if __name__ == "__main__":
    k.run_safely(main)
