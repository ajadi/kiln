"""Generate OpenAI Codex custom agents from Kiln's role definitions (agents/*.md).

  python codex_agents.py                       # -> ./.codex/agents/kiln-<role>.toml
  python codex_agents.py --out ~/.codex/agents # personal agents instead of project agents
  python codex_agents.py --model-map opus=gpt-6-astra,sonnet=gpt-6.1-sol,haiku=gpt-6-luna

Format (learn.chatgpt.com/docs/agent-configuration/subagents): one TOML file per agent with
the required `name`, `description`, `developer_instructions`, plus other config.toml keys —
`model`, `model_reasoning_effort`, `default_permissions` with a `[permissions.<name>]`
profile (learn.chatgpt.com/docs/permissions). Codex cannot preload skills or restrict built-in
tools per agent, so the instructions name the skills to read first and the role's MCP access.
With --with-permission-profiles each zoned role also gets its write zone as a permission
profile (Beta): Codex uses profiles only when they are enabled for the setup; otherwise it keeps
sandbox_mode (checked with codex 0.160.0 `debug prompt-input`).

Codex 0.160 (codex-rs/core/src/agent/role.rs at rust-v0.160.1) applies only
developer_instructions, model, model_reasoning_effort/summary, verbosity, personality,
service_tier, disabled features and disabled skills from an agent file; permission profiles are
parsed but not yet applied. Role rules are therefore enforced by the Kiln guard hook, which
receives agent_type in PreToolUse inside subagents (hooks schema at rust-v0.160.1).

manifest.md `agent_model` / `agent_effort` (read from the current folder) override every role's
model (through --model-map) and reasoning effort. Re-run after updating Kiln or the manifest:
generated files are overwritten.
"""

import argparse
import json
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
# Kiln's own role definitions. A built distribution whose agents/ holds another runtime's
# converted agents (the Gemini extension) keeps the originals in roles/ (review 2026-10-21,
# KILN-REV-06: generating from converted agents gave kiln-kiln-<role>).
ROLES = os.path.join(PLUGIN, "roles") if os.path.isdir(os.path.join(PLUGIN, "roles")) else \
    os.path.join(PLUGIN, "agents")
sys.path.insert(0, os.path.join(PLUGIN, "hooks"))
import guard  # noqa: E402  (role zones: single source of truth)
import kiln_hooklib as k  # noqa: E402

CLAUDE_ONLY = re.compile(r"^(opus|sonnet|haiku|fable|opusplan|inherit)(\[[\w.]+\])?$|claude",
                         re.I)
MODEL_MAP = {"opus": "gpt-6.1-sol", "sonnet": "gpt-6.1-sol", "haiku": "gpt-6-luna"}
SERVERS = ("blender", "godot-ai", "unity", "unreal")


def frontmatter(path):
    text = open(path, encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    data, key = {}, None
    for line in m.group(1).splitlines():
        if re.match(r"^[\w-]+:", line):
            key, _, value = line.partition(":")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = json.loads(value)
            data[key] = value
        elif line.strip().startswith("- ") and key:
            data.setdefault(key + "[]", []).append(line.strip()[2:])
    return data, m.group(2).strip()


def toml_str(value):
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def toml_multiline(text):
    if "'''" not in text and not re.search(r"[\x00-\x08\x0b-\x1f\x7f]", text):
        return "'''\n" + text.rstrip("\n") + "\n'''"
    return toml_str(text)


def zone_paths(patterns):
    """guard.ZONES patterns -> permission-profile subpaths under :workspace_roots."""
    out = []
    for p in patterns:
        p = p[:-3] if p.endswith("/**") else p
        if "*" not in p and p not in out:
            out.append(p)
    return out


def installed_root(codex_home):
    cache = os.path.join(codex_home, "plugins", "cache", "kiln", "kiln")
    if os.path.isdir(cache):
        # by number: a string sort puts 0.9.0 after 0.10.0
        versions = sorted(os.listdir(cache), key=lambda v: [int(x) if x.isdigit() else -1
                                                            for x in re.split(r"[.+-]", v)])
        if versions:
            return os.path.join(cache, versions[-1])
    return PLUGIN


def instructions(role, fm, body, plugin_root, zone):
    skills = fm.get("skills[]", [])
    mcp = mcp_notes(role, fm)
    lines = [
        f"You are the Kiln role `{role}` in OpenAI Codex. Kiln texts were written for Claude Code;",
        "read them with these equivalences:",
        "- Write/Edit = apply_patch; Bash/PowerShell = shell commands; the Skill tool = open the",
        "  skill's SKILL.md; AskUserQuestion = put the question in your final message (a subagent",
        "  cannot wait for answers); WebSearch/WebFetch = web search when it is enabled.",
        "- `kiln:<role>` = the custom agent `kiln-<role>`; skills are listed as `kiln:<skill>`.",
        "- In Kiln skill files `${CLAUDE_SKILL_DIR}` = the folder containing that SKILL.md and",
        f"  `${{CLAUDE_PLUGIN_ROOT}}` = {plugin_root}",
    ]
    if skills:
        lines.append("Before you start, read these skills in full and follow them: "
                     + ", ".join(f"kiln:{s}" for s in skills) + ". Load other kiln skills when "
                     "the protocol's situational table says so.")
    if zone:
        lines.append("You may write only: " + ", ".join(zone) + ". The Kiln guard denies file "
                     "edits outside these paths; keep shell commands inside them too.")
    if role in k.READ_ONLY_ROLES:
        lines.append("You are read-only for the game: run, observe, measure and probe; never "
                     "change scenes, assets, settings or game code. Write probes only under "
                     "tests/probes/ and evidence under production/captures/.")
    lines += mcp
    return "\n".join(lines) + "\n\n" + body + "\n"


def mcp_notes(role, fm):
    """MCP access of the role, as instructions. Agent files cannot carry partial
    [mcp_servers.<id>] tables (a server table needs its command or url), and Codex 0.160 does not
    apply mcp_servers from agent files; the Kiln guard enforces read-only roles by agent_type."""
    tools = [t.strip() for t in fm.get("tools", "").split(",") if t.strip()]
    denied = [t.strip() for t in fm.get("disallowedTools", "").split(",") if t.strip()]
    unused, lines = [], []
    for sid in SERVERS:
        listed = [t.split("__", 2)[2] for t in tools if t.startswith(f"mcp__{sid}__")]
        off = [t.split("__", 2)[2] for t in denied if t.startswith(f"mcp__{sid}__")
               and not t.endswith("_for_cli")]
        if f"mcp__{sid}" not in tools and not listed:
            unused.append(sid)
        elif listed and f"mcp__{sid}" not in tools:
            lines.append(f"From the {sid} MCP server use only: {', '.join(listed)}.")
        if off and sid not in unused:
            lines.append(f"Never call these {sid} tools: {', '.join(off)}.")
    if unused:
        lines.insert(0, f"Do not use these MCP servers: {', '.join(unused)}.")
    if role in k.READ_ONLY_ROLES:
        lines.append("Engine and Blender MCP calls that change the project are denied for your "
                     "role by the Kiln guard; Blender code is limited to the Kiln review scripts.")
    return lines


def permission_profile(role, zone):
    name = f"kiln-{role}"
    rows = [f'default_permissions = "{name}"', "", f"[permissions.{name}]",
            f"description = {toml_str(f'Kiln {role}: read the project, write only its zone.')}",
            'extends = ":read-only"', "", f"[permissions.{name}.filesystem]",
            '":tmpdir" = "write"', "", f'[permissions.{name}.filesystem.":workspace_roots"]']
    rows += [f'{toml_str(p)} = "write"' for p in zone]
    return "\n".join(rows)


def build(path, model_map, plugin_root, version, profiles=False, override=None):
    fm, body = frontmatter(path)
    for key, value in (override or {}).items():   # manifest agent_model / agent_effort
        if value:
            fm[key] = value
    role = fm["name"]
    zone = zone_paths(guard.ZONES[role]) if role in guard.ZONES else []
    parts = [f"# Generated by Kiln scripts/codex_agents.py from agents/{role}.md (kiln {version}).",
             "# Re-run the script after updating Kiln; edits here are overwritten.",
             f"name = {toml_str('kiln-' + role)}",
             f"description = {toml_str(fm['description'])}"]
    model = fm.get("model")
    if model in model_map:
        parts.append(f"model = {toml_str(model_map[model])}")
    elif model and not CLAUDE_ONLY.search(model):  # a Codex model name stays as given
        parts.append(f"model = {toml_str(model)}")
    # a Claude-only name Codex does not know (fable, inherit, claude-...) is left out: Codex then
    # uses its default model
    if fm.get("effort"):
        parts.append(f"model_reasoning_effort = {toml_str(fm['effort'])}")
    parts.append("developer_instructions = "
                 + toml_multiline(instructions(role, fm, body, plugin_root, zone)))
    text = "\n".join(parts)
    if zone and profiles:
        text += "\n\n" + permission_profile(role, zone)
    text += "\n"
    tomllib.loads(text)  # refuse to write anything Codex could not parse
    return "kiln-" + role, text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(".codex", "agents"))
    codex_home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    ap.add_argument("--user-config", default=os.path.join(codex_home, "config.toml"))
    ap.add_argument("--model-map", default="", help="e.g. opus=gpt-6-astra,haiku=gpt-6-luna")
    ap.add_argument("--with-permission-profiles", action="store_true",
                    help="also write each zoned role's write zone as a permission profile "
                         "(Beta; inactive unless permission profiles are enabled for the setup)")
    args = ap.parse_args(argv)

    model_map = dict(MODEL_MAP)
    for pair in filter(None, args.model_map.split(",")):
        key, _, value = pair.partition("=")
        model_map[key.strip()] = value.strip()
    config = {}
    if os.path.isfile(args.user_config):
        with open(args.user_config, "rb") as fh:
            config = tomllib.load(fh)
    servers = set(config.get("mcp_servers", {}))
    warnings = []
    if args.with_permission_profiles and "sandbox_mode" in config:
        warnings.append("user config sets sandbox_mode: Codex then ignores permission profiles")
    for sid in ("blender", "godot-ai"):
        if sid not in servers:
            warnings.append(f"MCP server '{sid}' is not configured in {args.user_config}")
    version = json.load(open(os.path.join(PLUGIN, ".codex-plugin", "plugin.json"), encoding="utf-8"))["version"]
    # the project's manifest (run from the project root): agent_model / agent_effort apply to
    # every role, as the guard does for Claude Code's Agent tool
    policy = k.kiln_manifest(os.getcwd()) or {}
    override = {"model": policy.get("agent_model", ""), "effort": policy.get("agent_effort", "")}
    plugin_root = installed_root(codex_home)

    os.makedirs(args.out, exist_ok=True)
    written = []
    for fn in sorted(os.listdir(ROLES)):
        if not fn.endswith(".md"):
            continue
        name, text = build(os.path.join(ROLES, fn), model_map, plugin_root, version,
                           args.with_permission_profiles, override)
        with open(os.path.join(args.out, name + ".toml"), "w", encoding="utf-8",
                  newline="\n") as fh:
            fh.write(text)
        written.append(name)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"out": os.path.abspath(args.out), "agents": len(written),
                      "plugin_root": plugin_root, "mcp_servers": sorted(servers),
                      "warnings": warnings}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
