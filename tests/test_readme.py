"""README and setup numbers follow the plugin tree (g2 row 15: counts went stale by hand).

Counts come from the files themselves: agents/*.md, skills/*/SKILL.md (user-invocable: false =
knowledge skill, the rest are process commands) and the role groups in hooks/kiln_hooklib.py.
Every policy key in DEFAULT_POLICY must be documented in the README settings table.
"""

import glob
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
PLUGIN = os.path.join(ROOT, "plugins", "kiln")
sys.path.insert(0, os.path.join(PLUGIN, "hooks"))
import kiln_hooklib as k  # noqa: E402


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def counts():
    roles = len(glob.glob(os.path.join(PLUGIN, "agents", "*.md")))
    skills = glob.glob(os.path.join(PLUGIN, "skills", "*", "SKILL.md"))
    knowledge = sum(1 for p in skills if re.search(r"^user-invocable:\s*false", read(p), re.M))
    return {"roles": roles, "knowledge": knowledge, "commands": len(skills) - knowledge,
            "designers": len({"game-designer", "tech-designer"}),
            "builders": len(k.BUILD_ROLES), "qa": len(k.QA_ROLES),
            "reviewers": len(k.READ_ONLY_ROLES - k.QA_ROLES),
            "experts": len(k.EXPERT_ROLES - {"tech-designer"})}


class Readme(unittest.TestCase):
    def test_counts(self):
        c = counts()
        text = read(ROOT, "README.md")
        self.assertIn(f"| {c['roles']} roles", text)
        self.assertIn(f"| {c['knowledge']} knowledge skills", text)
        self.assertIn(f"| {c['commands']} process commands", text)
        self.assertIn(f"{c['designers']} designers, {c['builders']} builders, {c['qa']} "
                      f"acceptors, {c['reviewers']} reviewers, {c['experts']} experts", text)
        self.assertIn(f"generates {c['roles']} roles", text)
        self.assertEqual(c["roles"], c["designers"] + c["builders"] + c["qa"] + c["reviewers"]
                         + c["experts"], "a role file is missing from the hooklib role groups")
        self.assertEqual(len(re.findall(r"`/kiln:[a-z-]+`", text.split("process commands")[1]
                                        .split("\n")[0])), c["commands"])

    def test_setup_names_the_codex_role_count(self):
        self.assertIn(f"({counts()['roles']} files:", read(PLUGIN, "skills", "setup", "SKILL.md"))

    def test_versions_agree(self):
        # 0.7.0 review: the project template still wrote framework_version=0.5.0 under 0.6.0,
        # and "migrate after a Kiln update" compares exactly these numbers.
        import json
        versions = {}
        for plugin in ("kiln", "kiln-start"):
            for kind in (".claude-plugin", ".codex-plugin"):
                with open(os.path.join(ROOT, "plugins", plugin, kind, "plugin.json"),
                          encoding="utf-8") as fh:
                    versions[f"{plugin}/{kind}"] = json.load(fh)["version"]
        versions["README"] = re.search(r"Version (\d+\.\d+\.\d+)",
                                       read(ROOT, "README.md")).group(1)
        versions["template"] = re.search(r"^framework_version=(\S+)", read(
            PLUGIN, "templates", "project", "manifest.md"), re.M).group(1)
        changelog = re.findall(r"^## (\d+\.\d+\.\d+)", read(PLUGIN, "CHANGELOG.md"), re.M)
        versions["CHANGELOG (last entry)"] = changelog[-1]
        self.assertEqual(len(set(versions.values())), 1, versions)

    def test_every_policy_key_is_documented(self):
        text = read(ROOT, "README.md")
        missing = [key for key in k.DEFAULT_POLICY if f"`{key}`" not in text]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
