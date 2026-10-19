"""Connect a project to Kiln for OpenCode. Stdlib only; run with the project root as --project.

  python opencode_setup.py --project .     # (re)write the project's .opencode/ Kiln parts

Writes, from this Kiln checkout (checked live with OpenCode 1.19.0):
- .opencode/plugins/kiln.js: Kiln's hooks around OpenCode's tool calls (opencode/kiln.js, with
  this Kiln folder written into it). OpenCode loads project plugins only in that project, so
  Kiln stays off elsewhere.
- .opencode/agents/kiln-<role>.md: every Kiln role as a subagent (`mode: subagent`); the body
  is the role's own, led by the skills it activates first.
- .opencode/skills/<name>: a directory junction (Windows) or symlink to each Kiln skill, so
  skills stay current with the checkout.
The project rules go to AGENTS.md (setup, as for Codex); OpenCode reads it, and CLAUDE.md.
MCP servers go into opencode.json "mcp" (setup prints the entries). Output: JSON report.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import codex_agents as cx  # noqa: E402  (role frontmatter)


def link(src, dst):
    """Link dst to Kiln's skill src. A real folder at dst is the user's own skill: it is kept and
    not linked (False). Only an old link is replaced; its target is never touched."""
    if os.path.lexists(dst):
        if os.path.isdir(dst) and not os.path.islink(dst) and not is_junction(dst):
            return False
        os.remove(dst) if os.path.islink(dst) else os.rmdir(dst)
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", dst, src], check=True, capture_output=True)
    else:
        os.symlink(src, dst, target_is_directory=True)
    return True


def is_junction(path):
    try:
        return bool(os.lstat(path).st_file_attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except (AttributeError, OSError):
        return False


def agent_file(path):
    fm, body = cx.frontmatter(path)
    role = fm["name"]
    skills = fm.get("skills[]", [])
    lines = ["---", f"description: {json.dumps(fm['description'])}", "mode: subagent", "---", "",
             f"You are the Kiln role `{role}`, running as the OpenCode subagent `kiln-{role}`."]
    if skills:
        lines.append("Before you start, load these Kiln skills with the skill tool and follow them: "
                     + ", ".join(skills) + ". Load other Kiln skills when the protocol skill's "
                     "situational table says so.")
    text = "\n".join(lines) + "\n\n" + body.replace("${CLAUDE_PLUGIN_ROOT}", PLUGIN.replace("\\", "/"))
    return f"kiln-{role}.md", text.strip() + "\n"


def setup(project):
    project = os.path.abspath(os.path.normpath(project))  # mklink /J reads "/" as a switch
    oc = os.path.join(project, ".opencode")
    for sub in ("plugins", "agents", "skills"):
        os.makedirs(os.path.join(oc, sub), exist_ok=True)
    with open(os.path.join(PLUGIN, "opencode", "kiln.js"), encoding="utf-8") as fh:
        plugin = fh.read().replace("__KILN_ROOT__", PLUGIN.replace("\\", "/"))
    with open(os.path.join(oc, "plugins", "kiln.js"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(plugin)
    agents = 0
    for fn in sorted(os.listdir(os.path.join(PLUGIN, "agents"))):
        if fn.endswith(".md"):
            name, text = agent_file(os.path.join(PLUGIN, "agents", fn))
            with open(os.path.join(oc, "agents", name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            agents += 1
    skills, kept = 0, []
    for name in sorted(os.listdir(os.path.join(PLUGIN, "skills"))):
        src = os.path.join(PLUGIN, "skills", name)
        if os.path.isfile(os.path.join(src, "SKILL.md")):
            if link(src, os.path.join(oc, "skills", name)):
                skills += 1
            else:
                kept.append(name)
    return {"project": os.path.abspath(project), "kiln": PLUGIN, "agents": agents,
            "skills": skills, "plugin": os.path.join(oc, "plugins", "kiln.js"), "kept": kept}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project", default=".")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(setup(a.project), indent=1))


if __name__ == "__main__":
    main()
