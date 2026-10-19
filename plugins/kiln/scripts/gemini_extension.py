"""Build Kiln as a Google Gemini CLI extension. Stdlib only.

  python gemini_extension.py --out <folder>     # e.g. dist/gemini/kiln
  gemini extensions install <folder>            # or link it while developing

Layout read from gemini-cli v0.64.0 (packages/cli/src/config/extension-manager.ts and
docs/extensions/reference.md): gemini-extension.json at the root, skills/<name>/SKILL.md,
agents/*.md, commands/**/*.toml, hooks/hooks.json. The build copies the kiln plugin and changes
only what Gemini reads differently:
- agents/: each Kiln role as a Gemini subagent `kiln-<role>`. Gemini's frontmatter schema is
  strict (agents/agentLoader.ts), so only name, description, tools and max_turns are written;
  tools are the role's tools in Gemini names (read-only roles get no write tools). The body
  tells the role which Kiln skills to activate first and how Kiln's Claude Code wording maps.
- commands/kiln/<name>.toml: every user command as /kiln:<name>, activating its skill.
- hooks/hooks.json: the same Python hooks with --runtime gemini (BeforeTool for the guard and
  for invoke_agent, AfterTool for invoke_agent, SessionStart, SessionEnd, AfterAgent). Gemini
  runs hook commands in PowerShell on Windows and bash elsewhere; `python` must be on PATH.
- ${CLAUDE_PLUGIN_ROOT} / ${CLAUDE_SKILL_DIR} in skills and agents become ${extensionPath}
  forms, which Gemini expands in extension skills and agents.
Output: JSON report; exit 1 on a problem.
"""

import argparse
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import codex_agents as cx  # noqa: E402  (role frontmatter, zones, MCP notes)

k = cx.k
TOOL_NAMES = {"Read": ["read_file", "read_many_files"], "Grep": ["grep_search"],
              "Glob": ["glob"], "LS": ["list_directory"], "Write": ["write_file"],
              "Edit": ["replace"], "MultiEdit": ["replace"], "Bash": ["run_shell_command"],
              "PowerShell": ["run_shell_command"], "Skill": ["activate_skill"],
              "WebFetch": ["web_fetch"], "WebSearch": ["google_web_search"],
              "TodoWrite": ["write_todos"], "AskUserQuestion": ["ask_user"]}
ALWAYS = ["list_directory", "activate_skill"]
EVENTS = {
    "BeforeTool": [
        ("^(run_shell_command|write_file|replace|mcp_(blender|godot-ai|unity|unreal|unreal-mcp|"
         "unreal-mcp-proxy)_.*)$", "guard.py", 10000),
        ("^invoke_agent$", "session.py subagent", 10000)],
    "AfterTool": [("^invoke_agent$", "stop.py subagent", 10000)],
    "SessionStart": [("", "session.py start", 10000)],
    "SessionEnd": [("", "session.py end", 5000)],
    "AfterAgent": [("", "stop.py stop", 10000)],
}
CONTEXT = """# Kiln in Gemini CLI

Kiln's skills and roles were written for Claude Code. Read them with these equivalences:

- Write / Edit = write_file / replace; Bash or PowerShell = run_shell_command; the Skill tool =
  activate_skill; AskUserQuestion = ask_user.
- A Kiln role `kiln:<role>` is the subagent `kiln-<role>`: delegate with invoke_agent
  (agent_name `kiln-<role>`). Subagents cannot start subagents.
- Kiln commands are `/kiln:<name>` (setup, pipeline, run, model, track, ...).
- MCP tools named `mcp__<server>__<tool>` in Kiln texts are `mcp_<server>_<tool>` here.
- Kiln's hooks run here too: a denial names the rule; follow it instead of working around it.
"""


def gemini_tools(fm):
    tools = [t.strip() for t in fm.get("tools", "").split(",") if t.strip()]
    if not tools:
        return None  # the role inherits every tool
    out = list(ALWAYS)
    for t in tools:
        if t.startswith("mcp__"):
            parts = t.split("__")
            names = [f"mcp_{parts[1]}_*"] if len(parts) == 2 else [f"mcp_{parts[1]}_{parts[2]}"]
        else:
            names = TOOL_NAMES.get(t, [])
        out += [n for n in names if n not in out]
    return out


def gemini_vars(text, skill=None):
    text = text.replace("${CLAUDE_PLUGIN_ROOT}", "${extensionPath}")
    if skill:
        text = text.replace("${CLAUDE_SKILL_DIR}", "${extensionPath}${/}skills${/}" + skill)
    return text


def agent_file(path):
    fm, body = cx.frontmatter(path)
    role = fm["name"]
    lines = ["---", f"name: kiln-{role}", f"description: {json.dumps(fm['description'])}"]
    tools = gemini_tools(fm)
    if tools:
        lines.append("tools:")
        lines += [f"  - {json.dumps(t)}" for t in tools]
    if fm.get("maxTurns"):
        lines.append(f"max_turns: {int(fm['maxTurns'])}")
    lines.append(f"timeout_mins: {k.GEMINI_ROLE_TIMEOUT_MIN}")  # default 10 min stops long roles
    lines.append("---")
    skills = fm.get("skills[]", [])
    zone = cx.zone_paths(cx.guard.ZONES[role]) if role in cx.guard.ZONES else []
    notes = [f"You are the Kiln role `{role}`, running as the Gemini CLI subagent `kiln-{role}`."]
    if skills:
        notes.append("Before you start, activate these Kiln skills with activate_skill and follow "
                     "them: " + ", ".join(skills) + ". Activate other Kiln skills when the "
                     "protocol skill's situational table says so.")
    if zone:
        notes.append("You may write only: " + ", ".join(zone) + ". The Kiln guard denies "
                     "edits outside these paths.")
    if role in k.READ_ONLY_ROLES:
        notes.append("You are read-only for the game: run, observe, measure and probe; never "
                     "change scenes, assets, settings or game code.")
    notes += [n.replace("mcp__", "mcp_") for n in cx.mcp_notes(role, fm)]
    return "kiln-" + role, "\n".join(lines) + "\n\n" + "\n".join(notes) + "\n\n" + \
        gemini_vars(body).strip() + "\n"


def hooks_json():
    hooks = {}
    for event, entries in EVENTS.items():
        hooks[event] = []
        for matcher, script, timeout in entries:
            file, _, args = script.partition(" ")
            # node runs Kiln's Python launcher: Gemini CLI is a node program, and plain
            # `python` is missing on macOS / most Linux (py.cjs finds python, python3 or py -3)
            command = ('node "${extensionPath}${/}hooks${/}py.cjs" '
                       f'"${{extensionPath}}${{/}}hooks${{/}}{file}"'
                       + (f" {args}" if args else "") + " --runtime gemini")
            entry = {"hooks": [{"type": "command", "name": f"kiln-{file[:-3]}-{event}",
                                "command": command, "timeout": timeout}]}
            if matcher:
                entry["matcher"] = matcher
            hooks[event].append(entry)
    return {"description": "Kiln hooks for Gemini CLI (the Claude Code hooks, --runtime gemini). "
                           "No-ops outside projects whose manifest.md says framework=kiln.",
            "hooks": hooks}


def user_policy(skills):
    """Rules for ~/.gemini/policies/kiln.toml (user tier; extensions may not allow anything):
    Plan Mode may start Kiln's read-only roles (by default only codebase_investigator and
    cli_help), and Kiln's skills activate without asking (headless runs denied them)."""
    roles = "|".join(sorted(k.READ_ONLY_ROLES))
    names = "|".join(sorted(skills))
    rules = [("Kiln read-only roles in Plan Mode", "invoke_agent",
              r'"agent_name":\s*"kiln-(' + roles + r')"', ["plan"]),
             ("Kiln skills", "activate_skill", r'"name":\s*"(' + names + r')"', None)]
    text = "# Kiln for Gemini CLI: copy to ~/.gemini/policies/kiln.toml (setup does it).\n"
    for name, tool, pattern, modes in rules:
        text += (f'\n[[rule]]\nname = "{name}"\ntoolName = "{tool}"\n'
                 f"argsPattern = '{pattern}'\ndecision = \"allow\"\npriority = 100\n")
        if modes:
            text += f"modes = {json.dumps(modes)}\n"
    return text


def build(out):
    if os.path.exists(out):
        shutil.rmtree(out)
    shutil.copytree(PLUGIN, out, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", "agents", "hooks.json", "codex-hooks.json"))
    with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    manifest = {"name": "kiln", "version": meta["version"],
                "description": meta.get("description", ""), "contextFileName": "GEMINI.md"}
    write(os.path.join(out, "gemini-extension.json"), json.dumps(manifest, indent=2) + "\n")
    write(os.path.join(out, "GEMINI.md"), CONTEXT)
    write(os.path.join(out, "hooks", "hooks.json"), json.dumps(hooks_json(), indent=2) + "\n")
    agents = []
    for fn in sorted(os.listdir(os.path.join(PLUGIN, "agents"))):
        if fn.endswith(".md"):
            name, text = agent_file(os.path.join(PLUGIN, "agents", fn))
            write(os.path.join(out, "agents", name + ".md"), text)
            agents.append(name)
    skills, commands = [], []
    for name in sorted(os.listdir(os.path.join(out, "skills"))):
        folder = os.path.join(out, "skills", name)
        for base, _dirs, files in os.walk(folder):
            for f in files:
                if f.endswith(".md"):
                    p = os.path.join(base, f)
                    text = open(p, encoding="utf-8").read()
                    write(p, gemini_vars(text, name))
        skill = os.path.join(folder, "SKILL.md")
        if not os.path.isfile(skill):
            continue
        skills.append(name)
        text = open(skill, encoding="utf-8").read()
        if re.search(r"^user-invocable:\s*false", text, re.M):
            continue
        desc = re.search(r"^description:\s*(.+)$", text, re.M)
        desc = desc.group(1).strip().strip('"') if desc else name
        prompt = (f"Use the Kiln skill `{name}`: activate it with activate_skill (name \"{name}\") "
                  "and follow it.\nArguments (may be empty): {{args}}\n")
        write(os.path.join(out, "commands", "kiln", name + ".toml"),
              f"description = {json.dumps(desc[:300])}\nprompt = {json.dumps(prompt)}\n")
        commands.append(name)
    write(os.path.join(out, "user-policy", "kiln.toml"), user_policy(skills))
    return {"out": os.path.abspath(out), "version": meta["version"], "agents": len(agents),
            "skills": len(skills), "commands": len(commands)}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", default=os.path.join("dist", "gemini", "kiln"))
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(build(a.out), indent=1))


if __name__ == "__main__":
    main()
