"""Tests for plugins/kiln/skills/save-system/scripts/save_check.py (stdlib only)."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "save-system",
                      "scripts", "save_check.py")

MANIFEST = {
    "current_version": 3,
    "first_version": 1,
    "migrations": [
        {"from": 1, "to": 2, "rename": {"hp": "player.health"}, "add": ["settings.fov"]},
        {"from": 2, "to": 3, "remove": ["legacy_flags"], "add": ["inventory"]},
    ],
    "schemas": {
        "1": {"fields": ["hp", "settings", "legacy_flags.*"], "required": ["hp"]},
        "2": {"fields": ["player.health", "settings", "legacy_flags.*"],
              "required": ["player.health"]},
        "3": {"fields": ["player.health", "settings.fov", "inventory[].id", "inventory[].count"],
              "required": ["player.health", "settings.fov", "inventory"]},
    },
}
V1 = {"save_version": 1, "hp": 80, "settings": {}, "legacy_flags": {"tutorial": True}}
V2 = {"save_version": 2, "player": {"health": 80}, "settings": {"fov": 90},
      "legacy_flags": {"tutorial": True}}
V3 = {"save_version": 3, "player": {"health": 80}, "settings": {"fov": 90},
      "inventory": [{"id": "medkit", "count": 2}]}


def project(manifest=None, fixtures=None):
    root = tempfile.mkdtemp(prefix="kiln-save-")
    with open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(MANIFEST if manifest is None else manifest, fh)
    fixtures = {"v1/start.json": V1, "v2/mid.json": V2, "v3/late.json": V3} \
        if fixtures is None else fixtures
    for rel, data in fixtures.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data if isinstance(data, bytes) else json.dumps(data, indent=2).encode())
    return root


def run(root, *extra):
    p = subprocess.run([sys.executable, "-B", SCRIPT, os.path.join(root, "manifest.json"), *extra],
                       capture_output=True, text=True, timeout=60, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


def joined(res):
    return " | ".join(res["problems"])


class SaveCheck(unittest.TestCase):
    def test_complete_chain_passes(self):
        code, res = run(project())
        self.assertEqual(code, 0, joined(res))
        self.assertEqual(res["verdict"], "pass")
        self.assertEqual(res["chains"]["1"], [1, 2, 3])
        sims = {f["version"]: f["simulated"] for f in res["fixtures"]}
        self.assertEqual(sims, {1: "ok", 2: "ok", 3: "current"})

    def test_gap_in_chain_fails(self):
        manifest = dict(MANIFEST, migrations=MANIFEST["migrations"][1:])
        code, res = run(project(manifest))
        self.assertEqual(code, 1)
        self.assertIn("v1 cannot reach v3", joined(res))

    def test_duplicate_and_backward_migrations_fail(self):
        migs = MANIFEST["migrations"] + [{"from": 1, "to": 3}, {"from": 3, "to": 2}]
        code, res = run(project(dict(MANIFEST, migrations=migs)))
        self.assertEqual(code, 1)
        text = joined(res)
        self.assertIn("second migration from v1", text)
        self.assertIn("backwards", text)

    def test_missing_version_fixture_fails(self):
        code, res = run(project(fixtures={"v1/a.json": V1, "v3/c.json": V3}))
        self.assertEqual(code, 1)
        self.assertIn("no golden fixture for v2", joined(res))

    def test_unknown_and_missing_required_fields(self):
        bad = dict(V3, cheat_mode=True)
        del bad["settings"]
        code, res = run(project(fixtures={"v1/a.json": V1, "v2/b.json": V2, "v3/c.json": bad}))
        self.assertEqual(code, 1)
        text = joined(res)
        self.assertIn("unknown fields for v3: cheat_mode", text)
        self.assertIn("missing required fields for v3: settings.fov", text)

    def test_migration_that_forgets_a_field_is_caught(self):
        migs = [dict(MANIFEST["migrations"][0]), {"from": 2, "to": 3, "add": ["inventory"]}]
        code, res = run(project(dict(MANIFEST, migrations=migs)))
        self.assertEqual(code, 1)
        self.assertIn("legacy_flags.tutorial (rename or remove them)", joined(res))

    def test_migration_that_forgets_a_default_is_caught(self):
        migs = [dict(MANIFEST["migrations"][0]), {"from": 2, "to": 3, "remove": ["legacy_flags"]}]
        code, res = run(project(dict(MANIFEST, migrations=migs)))
        self.assertEqual(code, 1)
        self.assertIn("lacks required v3 fields: inventory", joined(res))

    def test_undeclared_operations_skip_simulation(self):
        migs = [{"from": 1, "to": 2}, MANIFEST["migrations"][1]]
        code, res = run(project(dict(MANIFEST, migrations=migs)))
        self.assertEqual(code, 0, joined(res))
        v1 = [f for f in res["fixtures"] if f["version"] == 1][0]
        self.assertTrue(v1["simulated"].startswith("skipped"))

    def test_future_version_and_folder_mismatch(self):
        future = dict(V3, save_version=4)
        moved = dict(V2)
        code, res = run(project(fixtures={"v1/a.json": V1, "v2/b.json": V2, "v3/c.json": V3,
                                          "v3/moved.json": moved, "v4/f.json": future}))
        self.assertEqual(code, 1)
        text = joined(res)
        self.assertIn("in folder v3 but save_version = 2", text)
        self.assertIn("newer than current_version 3", text)

    def test_header_checksum(self):
        body = json.dumps(V3, indent=2).encode()
        good = (json.dumps({"save_version": 3, "sha256": hashlib.sha256(body).hexdigest()})
                .encode() + b"\n" + body)
        bad = good.replace(b'"health": 80', b'"health": 99')
        self.assertNotEqual(good, bad)
        manifest = dict(MANIFEST, checksum={"field": "sha256", "algo": "sha256"})
        root = project(manifest, {"v1/a.json": V1, "v2/b.json": V2, "v3/good.json": good,
                                  "v3/bad.json": bad})
        code, res = run(root)
        text = joined(res)
        self.assertIn("bad.json: sha256 mismatch", text)
        self.assertNotIn("good.json: sha256", text)
        self.assertIn("a.json: no header line with 'sha256'", text)

    def test_float_version_warns_and_unreadable_fails(self):
        code, res = run(project(fixtures={"v1/a.json": dict(V1, save_version=1.0),
                                          "v2/b.json": V2, "v3/c.json": V3,
                                          "v3/broken.json": b"{\"save_version\": 3,"}))
        self.assertEqual(code, 1)
        self.assertIn("broken.json: unreadable", joined(res))
        self.assertTrue(any("stored as a float" in w for w in res["warnings"]))

    def test_out_file_for_pipeline_gate(self):
        root = project()
        out = os.path.join(root, "report", "save_check.json")
        code, _ = run(root, "--out", out)
        self.assertEqual(code, 0)
        with open(out, encoding="utf-8") as fh:
            self.assertIn('"verdict": "pass"', fh.read())


if __name__ == "__main__":
    unittest.main()
