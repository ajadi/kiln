"""Static checks that Kiln's skills and roles are wired together (stdlib only).

- every skill directory has a SKILL.md whose frontmatter name matches the directory;
- every `skills:` entry in an agent's frontmatter names an existing skill;
- every `kiln:<name>` / `/kiln:<name>` reference in the plugin resolves to a skill or an agent;
- a skill that another skill or role tells the model to invoke (Skill tool, load) does not carry
  `disable-model-invocation: true`;
- every knowledge skill (user-invocable: false) is reachable: preloaded by a role, listed in the
  protocol's situational table, or named by another skill or role;
- every `${CLAUDE_SKILL_DIR}/...` path in a SKILL.md exists;
- every check script a skill ships is mentioned in its SKILL.md and has a test file.
"""

import os
import re
import unittest

PLUGIN = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln")
SKILLS_DIR = os.path.join(PLUGIN, "skills")
AGENTS_DIR = os.path.join(PLUGIN, "agents")
TESTS_DIR = os.path.dirname(__file__)


def frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    data, key = {}, None
    for line in fm.splitlines():
        if re.match(r"^\s+-\s+", line) and key:
            data.setdefault(key, []).append(line.strip()[1:].strip())
        elif ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            data[key] = value if value else []
    return data, body


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


SKILLS = {}
for name in sorted(os.listdir(SKILLS_DIR)):
    path = os.path.join(SKILLS_DIR, name, "SKILL.md")
    if os.path.isfile(path):
        SKILLS[name] = (path, *frontmatter(read(path)))

AGENTS = {}
for fname in sorted(os.listdir(AGENTS_DIR)):
    if fname.endswith(".md"):
        path = os.path.join(AGENTS_DIR, fname)
        AGENTS[fname[:-3]] = (path, *frontmatter(read(path)))


def plugin_texts():
    for root, _, files in os.walk(PLUGIN):
        if "__pycache__" in root:
            continue
        for f in files:
            if f.endswith((".md", ".py", ".json", ".gd", ".toml")):
                path = os.path.join(root, f)
                yield path, read(path)


REF = re.compile(r"(?<![\w-])/?kiln:([a-z0-9][a-z0-9-]*)")
# code markers that share the kiln: prefix (guard escapes, probe tags, managed-block fences) and the
# engine profile template `kiln:engine-<engine>`
MARKERS = {"runtime-node", "probe", "loc-ignore", "begin", "end", "engine-", "godot3-ok"}
INVOKE = re.compile(r"(?:Skill tool[^.\n]{0,80}?|load[^.\n]{0,40}?|Skill `?)\"?`?kiln:([a-z0-9-]+)")


class SkillLinks(unittest.TestCase):
    def test_every_skill_dir_has_a_matching_skill_md(self):
        for name in os.listdir(SKILLS_DIR):
            if name.startswith((".", "_")) or not os.path.isdir(os.path.join(SKILLS_DIR, name)):
                continue
            self.assertTrue(name in SKILLS, f"skills/{name} has no SKILL.md")
            self.assertEqual(SKILLS[name][1].get("name"), name, f"skills/{name}: frontmatter name")

    def test_agent_preloads_exist(self):
        for agent, (_, fm, _) in AGENTS.items():
            for skill in fm.get("skills") or []:
                skill = skill.split(":")[-1]
                self.assertIn(skill, SKILLS, f"agent {agent} preloads unknown skill '{skill}'")

    def test_kiln_references_resolve(self):
        known = set(SKILLS) | set(AGENTS) | MARKERS
        bad = []
        for path, text in plugin_texts():
            for m in REF.finditer(text):
                if m.group(1) not in known:
                    bad.append(f"{os.path.relpath(path, PLUGIN)}: kiln:{m.group(1)}")
        self.assertEqual(bad, [], "unresolved kiln:<name> references")

    def test_model_invoked_skills_allow_model_invocation(self):
        bad = []
        for path, text in plugin_texts():
            for m in INVOKE.finditer(text):
                name = m.group(1)
                if name in SKILLS and SKILLS[name][1].get("disable-model-invocation") == "true":
                    bad.append(f"{os.path.relpath(path, PLUGIN)} invokes kiln:{name}, which "
                               "disables model invocation")
        self.assertEqual(bad, [])

    def test_knowledge_skills_are_reachable(self):
        protocol = SKILLS["protocol"][2]
        mentioned = set()
        for path, text in plugin_texts():
            for name in SKILLS:
                if path == SKILLS[name][0]:
                    continue
                if re.search(rf"(kiln:{name}\b|`{name}`|\b{name} skill)", text):
                    mentioned.add(name)
        preloaded = {s.split(":")[-1] for _, fm, _ in AGENTS.values() for s in fm.get("skills") or []}
        unreachable = []
        for name, (_, fm, _) in SKILLS.items():
            if fm.get("user-invocable") != "false":
                continue  # in the slash menu
            if name in preloaded or f"`{name}`" in protocol or name in mentioned:
                continue
            unreachable.append(name)
        self.assertEqual(unreachable, [], "knowledge skills nobody preloads, lists or names")

    def test_new_physics_skills_are_in_the_protocol_table(self):
        protocol = SKILLS["protocol"][2]
        for name in ("rigid-body-physics", "elements-materials", "fields-forces", "fluids-granular",
                     "soft-bodies", "vehicles", "traversal", "flight", "riding", "doors", "weather",
                     "sky"):
            if name in SKILLS:
                self.assertIn(f"`{name}`", protocol, f"{name} missing from the protocol table")

    def test_skill_dir_paths_exist(self):
        bad = []
        for name, (path, _, body) in SKILLS.items():
            for rel in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+)", body):
                rel = rel.rstrip(".,)")
                if not os.path.exists(os.path.join(SKILLS_DIR, name, rel)):
                    bad.append(f"{name}: {rel}")
        self.assertEqual(bad, [])

    def test_check_scripts_are_documented_and_tested(self):
        for name in ("elements-materials", "fields-forces", "fluids-granular", "soft-bodies",
                     "vehicles", "traversal", "implications", "flight", "hands", "riding", "doors", "weather", "sky"):
            scripts = os.path.join(SKILLS_DIR, name, "scripts")
            if name not in SKILLS or not os.path.isdir(scripts):
                continue
            for f in os.listdir(scripts):
                if not f.endswith(".py"):
                    continue
                self.assertIn(f, SKILLS[name][2], f"{name}/SKILL.md does not mention {f}")
                self.assertTrue(os.path.isfile(os.path.join(TESTS_DIR, f"test_{f}")),
                                f"no tests/test_{f}")



class Descriptions(unittest.TestCase):
    def test_every_description_fits_the_agent_skills_limit(self):
        # Agent Skills spec: description at most 1024 characters (agent platform research
        # 2026-10-19 found six over it; some agents cut or reject them).
        import glob
        import re
        root = os.path.join(os.path.dirname(__file__), "..", "plugins")
        for path in glob.glob(os.path.join(root, "*", "skills", "*", "SKILL.md")):
            text = open(path, encoding="utf-8").read()
            desc = re.search(r"^description:\s*(.+)$", text, re.M).group(1).strip().strip('"')
            self.assertLessEqual(len(desc), 1024, path)

if __name__ == "__main__":
    unittest.main()
