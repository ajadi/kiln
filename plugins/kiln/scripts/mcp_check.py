"""What a Kiln project needs from MCP, and whether it is really there.

  python mcp_check.py required [--manifest manifest.md] [--runtime claude|codex]
  python mcp_check.py verify --available .kiln/mcp-tools.txt --probe blender=ok \
      --probe godot-ai=ok [--manifest manifest.md] [--runtime claude|codex]

required  servers this project needs (from engine= and dimension= in the manifest), how to
          register each one, the tools Kiln uses from it (curated list + every tool named in a
          Kiln role's tools list) and one read-only probe call per server.
verify    compares the tool names the agent can actually see (one per line, written by the agent:
          `mcp__<server>__<tool>`; Unreal toolsets as `unreal:toolset:<Name>` from list_toolsets)
          and the probe results (`--probe <server>=ok` or `=<error text>`) with the requirements,
          writes .kiln/mcp-check.json (`"ready": true|false`) and exits 1 if anything is missing.

Tool names for blender and godot-ai were read from the installed servers (Blender Lab MCP
blender_mcp 1.0.2, Godot AI 4.3.0), unity names from MCP for Unity v10.3.0 sources, unreal toolset
names from the UE 5.8.0 toolset catalog (not yet seen on a live server).
"""

import argparse
import json
import os
import re
import sys
import time

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERVERS = {
    "blender": {
        "why": "modeling, pre-renders and review views in the user's open Blender",
        "claude": "claude mcp add --scope user blender -- <path to blender-mcp executable>",
        "codex": "codex mcp add blender -- <path to blender-mcp executable>",
        "tools": ["execute_blender_code", "get_blendfile_summary_path_info", "get_python_api_docs",
                  "search_api_docs", "get_screenshot_of_area_as_image"],
        "probe": {"tool": "get_blendfile_summary_path_info", "args": {}},
        "verified": True,
    },
    "godot-ai": {
        "why": "every scene, resource, script and play test in the Godot editor",
        "claude": "claude mcp add --scope user godot-ai -- godot-ai attach",
        "codex": "codex mcp add godot-ai -- godot-ai attach",
        "tools": ["session_manage", "session_activate", "editor_state", "editor_manage",
                  "editor_screenshot", "logs_read", "scene_open", "scene_save", "scene_manage",
                  "scene_get_hierarchy", "node_create", "node_manage", "node_find",
                  "node_get_properties", "node_set_property", "script_create", "script_patch",
                  "script_attach", "script_manage", "resource_manage", "material_manage",
                  "particle_manage", "signal_manage", "autoload_manage", "input_map_manage",
                  "ui_manage", "filesystem_manage", "batch_execute", "api_manage",
                  "project_run", "project_manage", "game_manage", "test_run", "test_manage"],
        "tools_2d": ["tilemap_manage", "tileset_manage"],
        "probe": {"tool": "editor_state", "args": {}},
        "verified": True,
    },
    "unity": {
        "why": "every scene, prefab, asset and play test in the Unity editor (MCP for Unity)",
        "claude": "claude mcp add --scope user --transport http unity http://localhost:8080/mcp",
        "codex": "codex mcp add unity --url http://localhost:8080/mcp",
        "tools": ["manage_scene", "find_gameobjects", "manage_gameobject", "manage_components",
                  "manage_prefabs", "manage_asset", "manage_material", "manage_editor",
                  "manage_camera", "create_script", "script_apply_edits", "validate_script",
                  "read_console", "run_tests", "get_test_job", "execute_code", "apply_text_edits",
                  "manage_tools", "manage_profiler"],
        "groups": "only the core group is on by default: enable testing (run_tests, get_test_job), "
                  "scripting_ext (execute_code) and profiling (manage_profiler) with manage_tools",
        "probe": {"tool": "manage_scene", "args": {"action": "get_active"}},
        "verified": True,
    },
    "unreal": {
        "why": "levels, assets and play tests in the Unreal editor (Epic Unreal MCP, UE 5.8)",
        "claude": "claude mcp add --scope user --transport http unreal http://127.0.0.1:8000/mcp",
        "codex": "codex mcp add unreal --url http://127.0.0.1:8000/mcp",
        "tools": ["list_toolsets", "describe_toolset", "call_tool"],
        "toolsets": ["SceneTools", "ActorTools", "ObjectTools", "AssetTools", "StaticMeshTools",
                     "SkeletalMeshTools", "EditorAppToolset", "LogsToolset",
                     "AutomationTestToolset"],
        "probe": {"tool": "list_toolsets", "args": {}},
        "verified": False,
    },
}
ENGINE_SERVER = {"godot": "godot-ai", "unity": "unity", "unreal": "unreal"}


def manifest(path):
    values = {}
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8", errors="ignore"):
            m = re.match(r"^([\w.-]+)=(.*)$", line.strip())
            if m:
                values[m.group(1)] = m.group(2).strip()
    return values


def role_tools():
    """{server: {tool: [roles]}} for every MCP tool named explicitly in a role's tools list."""
    used = {}
    agents = os.path.join(PLUGIN, "agents")
    for fn in sorted(os.listdir(agents)):
        text = open(os.path.join(agents, fn), encoding="utf-8").read()
        m = re.search(r"^tools:(.*)$", text, re.M)
        for item in (m.group(1).split(",") if m else []):
            parts = item.strip().split("__")
            if len(parts) == 3 and parts[0] == "mcp" and not parts[2].endswith("_for_cli"):
                used.setdefault(parts[1], {}).setdefault(parts[2], []).append(fn[:-3])
    return used


def requirements(policy, runtime):
    engine = policy.get("engine", "godot")
    dimension = policy.get("dimension", "3d")
    by_role = role_tools()
    out = []
    for sid in ("blender", ENGINE_SERVER.get(engine, "godot-ai")):
        spec = SERVERS[sid]
        tools = list(spec["tools"])
        if dimension == "2d":
            tools += spec.get("tools_2d", [])
        for tool in by_role.get(sid, {}):
            if tool not in tools:
                tools.append(tool)
        out.append({
            "server": sid,
            "required": not (sid == "blender" and dimension == "2d"),
            "why": spec["why"] + ("" if sid != "blender" or dimension != "2d"
                                  else " (2D: only for pre-rendered sprites)"),
            "register": spec["codex" if runtime == "codex" else "claude"],
            "tools": tools,
            "toolsets": spec.get("toolsets", []),
            "groups": spec.get("groups", ""),
            "probe": spec["probe"],
            "names_verified": spec["verified"],
        })
    return out


def parse_available(path):
    tools, toolsets = {}, {}
    for line in open(path, encoding="utf-8", errors="ignore"):
        name = line.strip()
        m = re.match(r"^mcp__([\w-]+?)__(\w+)$", name)
        if m:  # Epic's own config names the Unreal server unreal-mcp / unreal-mcp-proxy
            server = "unreal" if m.group(1).startswith("unreal") else m.group(1)
            tools.setdefault(server, set()).add(m.group(2))
        m = re.match(r"^([\w-]+):toolset:(\S+)$", name)
        if m:  # UE 5.8 names are qualified: editor_toolset.toolsets.scene.SceneTools
            toolsets.setdefault(m.group(1), set()).add(m.group(2).rsplit(".", 1)[-1])
    return tools, toolsets


def verify(reqs, available_path, probes):
    tools, toolsets = parse_available(available_path)
    report, ready = [], True
    for req in reqs:
        sid = req["server"]
        seen = tools.get(sid, set())
        missing = [t for t in req["tools"] if t not in seen]
        missing_sets = [t for t in req["toolsets"] if t not in toolsets.get(sid, set())]
        probe = probes.get(sid, "not run")
        ok = bool(seen) and not missing and not missing_sets and probe == "ok"
        problems = []
        if not seen:
            problems.append(f"no {sid} tools visible: server not registered, not connected, or "
                            f"the session started before it was added — register: {req['register']}")
        else:
            if missing:
                problems.append(f"missing tools: {', '.join(missing)}")
            if missing_sets:
                problems.append(f"missing toolsets: {', '.join(missing_sets)}")
        if probe != "ok":
            problems.append(f"probe {req['probe']['tool']}: {probe}")
        if req["required"] and not ok:
            ready = False
        report.append({"server": sid, "required": req["required"], "ok": ok,
                       "tools_seen": len(seen), "problems": problems})
    return {"ready": ready, "checked_at": time.strftime("%Y-%m-%d %H:%M"), "servers": report}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("required", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--manifest", default="manifest.md")
        p.add_argument("--runtime", default="claude", choices=["claude", "codex"])
        if name == "verify":
            p.add_argument("--available", required=True)
            p.add_argument("--probe", action="append", default=[],
                           help="<server>=ok or <server>=<error text>")
            p.add_argument("--out", default=os.path.join(".kiln", "mcp-check.json"))
    args = ap.parse_args(argv)
    reqs = requirements(manifest(args.manifest), args.runtime)
    sys.stdout.reconfigure(encoding="utf-8")
    if args.cmd == "required":
        print(json.dumps(reqs, indent=1, ensure_ascii=False))
        return
    probes = dict(p.split("=", 1) for p in args.probe if "=" in p)
    result = verify(reqs, args.available, probes)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, ensure_ascii=False)
    print(json.dumps(result, indent=1, ensure_ascii=False))
    sys.exit(0 if result["ready"] else 1)


if __name__ == "__main__":
    main()
