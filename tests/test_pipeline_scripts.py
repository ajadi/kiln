"""Tests for the pipeline skill's scripts: pipeline.py, scope.py, licenses.py, refs_fetch.py,
ab.py. Stdlib + Pillow; each test runs in a throwaway project folder."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "pipeline",
                       "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS))
import pipeline  # noqa: E402


def project(engine="godot"):
    root = tempfile.mkdtemp(prefix="kiln-pipe-")
    with open(os.path.join(root, "manifest.md"), "w", encoding="utf-8") as fh:
        fh.write(f"framework=kiln\nengine={engine}\ndimension=3d\n")
    return root


def run(root, script, *args):
    p = subprocess.run([sys.executable, "-B", os.path.join(SCRIPTS, script), *args], cwd=root,
                       capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or root, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class Pipeline(unittest.TestCase):
    def test_every_template_gate_parses(self):
        text = open(pipeline.TEMPLATE, encoding="utf-8").read()
        for line in text.splitlines():
            if line.startswith("- [ ]"):
                m = pipeline.GATE.match(line)
                self.assertTrue(m and m.group(6), f"gate without a kind: {line}")
                if m.group(6).startswith("check:"):
                    self.assertNotIn(" — ", m.group(7), line)

    def test_init_per_engine(self):
        for engine, needle in (("godot", "scenes/lookdev/*.tscn"),
                               ("unity", "Assets/_Project/Scenes/LookDev*.unity"),
                               ("unreal", "Content/*/Maps/LookDev*.umap")):
            root = project(engine)
            code, out = run(root, "pipeline.py", "init")
            self.assertEqual(code, 0, out)
            text = open(os.path.join(root, "production", "PIPELINE.md"), encoding="utf-8").read()
            self.assertIn(needle, text)
            self.assertNotIn("{{", text)

    def test_status_auto_ticks_checks(self):
        root = project()
        run(root, "pipeline.py", "init")
        write(root, ".kiln/mcp-check.json", '{\n "ready": true\n}')
        code, out = run(root, "pipeline.py", "status")
        self.assertEqual(code, 0, out)
        text = open(os.path.join(root, "production", "PIPELINE.md"), encoding="utf-8").read()
        self.assertIn("- [x] MCP check ready", text)
        self.assertIn("- [x] Dimension chosen", text)

    def test_placeholder_ignores_inline_code(self):
        # live: the project CLAUDE.md template's own `kiln:<skill>` notation kept Phase 0 "NOW"
        root = project()
        write(root, "a.md", "Run `/kiln:<skill>`; stage with `git add <paths>`.\n")
        write(root, "b.md", "Name: <game name>\n")
        self.assertFalse(pipeline.has_placeholder(os.path.join(root, "a.md")))
        self.assertTrue(pipeline.has_placeholder(os.path.join(root, "b.md")))
        template = os.path.join(SCRIPTS, "..", "..", "..", "templates", "project", "CLAUDE.md")
        self.assertFalse(pipeline.has_placeholder(template))

    def test_a_user_decision_stays_the_users_on_autopilot(self):
        # g2 row 9: decisions the user really made (#32, #33) were recorded as proxy.
        root = project()
        run(root, "pipeline.py", "init")
        write(root, ".kiln/autopilot", "on\n")
        code, out = run(root, "pipeline.py", "decide", "agents run sonnet", "--options",
                        "sonnet / opus", "--by", "user", "--why", "user said so")
        self.assertEqual(code, 0, out)
        with open(os.path.join(root, "memory", "decisions.md"), encoding="utf-8") as fh:
            self.assertIn("| user | user said so |", fh.read())
        code, out = run(root, "pipeline.py", "decide", "palette B", "--options", "A / B",
                        "--by", "proxy", "--why", "recommended")
        with open(os.path.join(root, "memory", "decisions.md"), encoding="utf-8") as fh:
            self.assertIn("| proxy | recommended |", fh.read())

    def test_status_shows_running_agents(self):
        # g2 row 13: nothing told the producer whether an agent died or was still working.
        import time
        root = project()
        run(root, "pipeline.py", "init")
        now = time.time()
        write(root, ".kiln/agents.json", json.dumps({
            "a1": {"role": "modeler", "session": "s", "since": now - 1500, "last": now - 200,
                   "last_tool": "mcp__blender__execute_blender_code"}}))
        code, out = run(root, "pipeline.py", "status")
        self.assertIn("Running agents", out)
        self.assertIn("modeler", out)
        self.assertIn("25 min", out)
        self.assertIn("last call 3 min ago", out)
        self.assertIn("execute_blender_code", out)

    def test_gates_suggest_the_roles_a_task_needs(self):
        # g2 rows 43-46: anatomy-expert never called on 5 humans, physics-expert skipped after a
        # physics-engine switch, qa-audio / qa-performance named but never run.
        root = project()
        write(root, "tasks/TASK-020.md", "# TASK-020: merchants\n## spec\ntype: art\n"
              "role: modeler\nbatch: five human merchant NPCs on one base\npaths: art/npc/\n")
        write(root, "tasks/TASK-017.md", "# TASK-017: controller\n## spec\ntype: gameplay\n"
              "role: gameplay-dev\nbatch: switch to Jolt physics, step-up for the "
              "CharacterBody3D\n")
        write(root, "tasks/TASK-011.md", "# TASK-011: music\n## spec\ntype: music\n"
              "role: composer\npaths: assets/music/calm.ogg\n")
        code, out = run(root, "pipeline.py", "gates", "TASK-020", "--suggest")
        self.assertEqual(code, 0, out)
        for role in ("anatomy-expert", "art-director", "qa-readability", "verifier"):
            self.assertIn(f"| {role} |", out)
        self.assertNotIn("creature-expert", out)
        code, out = run(root, "pipeline.py", "gates", "TASK-017", "--suggest")
        for role in ("physics-expert", "qa-physics", "qa-feel", "playtester", "verifier"):
            self.assertIn(f"| {role} |", out)
        code, out = run(root, "pipeline.py", "gates", "TASK-011", "--suggest")
        self.assertIn("| qa-audio |", out)

    def test_asset_mode_gates_judge_the_asset_not_a_game(self):
        # S08: kind=assets (no game, no engine) - the asset is judged by its own acceptors and
        # experts; nothing that needs a running game (playtester, qa-performance, qa-feel).
        root = project("none")
        with open(os.path.join(root, "manifest.md"), "a", encoding="utf-8") as fh:
            fh.write("kind=assets\n")
        write(root, "tasks/TASK-001.md", "# TASK-001: knight from photos\n## spec\ntype: art\n"
              "role: modeler\ntouches: humanoid, movement\n")
        write(root, "tasks/TASK-002.md", "# TASK-002: calm track\n## spec\ntype: music\n"
              "role: composer\n")
        write(root, "tasks/TASK-003.md", "# TASK-003: walk sheet\n## spec\ntype: animation\n"
              "role: artist-2d\n")
        code, out = run(root, "pipeline.py", "gates", "TASK-001", "--suggest")
        self.assertEqual(code, 0, out)
        for role in ("art-director", "anatomy-expert", "verifier"):
            self.assertIn(f"| {role} |", out)
        for role in ("qa-feel", "playtester", "qa-performance", "qa-readability"):
            self.assertNotIn(f"| {role} |", out)
        code, out = run(root, "pipeline.py", "gates", "TASK-002", "--suggest")
        self.assertIn("| qa-audio |", out)
        code, out = run(root, "pipeline.py", "gates", "TASK-003", "--suggest")
        self.assertIn("| art-director |", out)
        self.assertNotIn("qa-locomotion", out)

    def test_parallel_decisions_get_distinct_numbers(self):
        # Review 2026-10-14: decide counted rows and wrote without the row lock.
        root = project()
        procs = [subprocess.Popen([sys.executable, "-B", os.path.join(SCRIPTS, "pipeline.py"),
                                   "decide", f"choice {i}"], cwd=root, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL) for i in range(8)]
        for p in procs:
            p.wait(timeout=60)
        with open(os.path.join(root, "memory", "decisions.md"), encoding="utf-8") as fh:
            rows = re.findall(r"^\|\s*(\d+)\s*\|", fh.read(), re.M)
        self.assertEqual(sorted(map(int, rows)), list(range(1, 9)))

    def test_manifest_with_spaces_around_equals(self):
        # Review 2026-10-14: the hooks read "engine = unity", migrate appended engine=godot.
        root = tempfile.mkdtemp(prefix="kiln-pipe-")
        write(root, "manifest.md", "framework = kiln\nengine = unity\nkind = assets\n")
        code, out = run(root, "pipeline.py", "migrate")
        with open(os.path.join(root, "manifest.md"), encoding="utf-8") as fh:
            manifest = fh.read()
        self.assertNotIn("engine=godot", manifest)
        self.assertNotIn("kind=game", manifest)
        code, out = run(root, "pipeline.py", "init")
        self.assertIn("kind=assets", out)   # kind read with spaces too

    def test_cinematic_tasks_get_their_gates(self):
        # S09: a cutscene is judged for its look, subtitles and frame rate in the game; a
        # standalone clip in asset mode by its look.
        root = project()
        write(root, "tasks/TASK-040.md", "# TASK-040: intro cutscene\n## spec\ntype: cinematic\n"
              "role: animator\n")
        code, out = run(root, "pipeline.py", "gates", "TASK-040", "--suggest")
        for role in ("art-director", "qa-readability", "qa-performance", "verifier"):
            self.assertIn(f"| {role} |", out)
        with open(os.path.join(root, "manifest.md"), "a", encoding="utf-8") as fh:
            fh.write("kind=assets\nengine=none\n")
        code, out = run(root, "pipeline.py", "gates", "TASK-040", "--suggest")
        self.assertIn("| art-director |", out)
        self.assertNotIn("qa-performance", out)

    def test_asset_mode_has_no_game_pipeline(self):
        # S08: kind=assets - no phases to init; status lists the asset tasks instead of failing.
        root = project("none")
        with open(os.path.join(root, "manifest.md"), "a", encoding="utf-8") as fh:
            fh.write("kind=assets\n")
        write(root, "backlog.md", "- [ ] TASK-001 knight from photos\n- [x] TASK-002 calm track\n")
        code, out = run(root, "pipeline.py", "init")
        self.assertEqual(code, 1, out)
        self.assertIn("kind=assets", out)
        self.assertFalse(os.path.exists(os.path.join(root, "production", "PIPELINE.md")))
        code, out = run(root, "pipeline.py", "status")
        self.assertEqual(code, 0, out)
        self.assertIn("asset mode", out)
        self.assertIn("TASK-001", out)

    def test_gates_check_fails_until_every_role_answered(self):
        root = project()
        body = ("# TASK-020: merchants\n## spec\ntype: art\nrole: modeler\n"
                "batch: five human merchants\n## gates\n| role | why | verdict |\n|---|---|---|\n"
                "| anatomy-expert | humanoid character | |\n"
                "| art-director | refs | |\n"
                "| qa-readability | art change | SKIP: decision #41 (user) no captures yet |\n"
                "| verifier | close | |\n"
                "## handoff: art-director\nstatus: APPROVED\n")
        write(root, "tasks/TASK-020.md", body)
        code, out = run(root, "pipeline.py", "gates", "TASK-020")
        self.assertEqual(code, 1, out)
        self.assertIn("anatomy-expert", out)
        self.assertIn("verifier", out)
        self.assertNotIn("missing: art-director", out)      # its handoff answers the row
        write(root, "tasks/TASK-020.md", body.replace(
            "| anatomy-expert | humanoid character | |", "| anatomy-expert | humanoid | PASS |")
              .replace("| verifier | close | |", "| verifier | close | PASSED |"))
        code, out = run(root, "pipeline.py", "gates", "TASK-020")
        self.assertEqual(code, 0, out)
        # a required role dropped from the table without a recorded skip is still missing
        write(root, "tasks/TASK-021.md", "# TASK-021\n## spec\ntype: art\nbatch: a crowd\n"
              "touches: humanoid\n"
              "## gates\n| role | why | verdict |\n|---|---|---|\n| verifier | close | PASSED |\n")
        code, out = run(root, "pipeline.py", "gates", "TASK-021")
        self.assertEqual(code, 1, out)
        self.assertIn("anatomy-expert", out)

    def test_touches_is_the_contract_and_guesses_do_not_gate(self):
        # 0.7.0 review: keyword triggers over the whole task text put anatomy-expert on g2's
        # facades, a rug and a dagger, and qa-audio on home-server tooling.
        root = project()
        facade = ("# TASK-030: Square buildings: 6 facades\n## spec\ntype: art\nrole: modeler\n"
                  "batch: tavern and bank facades\nacceptance:\n"
                  "  - a character walking past reads the signs; footstep sound on the steps\n")
        write(root, "tasks/TASK-030.md", facade)
        code, out = run(root, "pipeline.py", "gates", "TASK-030", "--suggest")
        self.assertNotIn("anatomy-expert", out)            # acceptance prose is not the spec
        self.assertNotIn("qa-audio", out)
        self.assertIn("touches: (none guessed)", out)
        write(root, "tasks/TASK-031.md", facade.replace("TASK-030", "TASK-031")
              + "touches: humanoid, audio\n")
        code, out = run(root, "pipeline.py", "gates", "TASK-031", "--suggest")
        self.assertIn("| anatomy-expert |", out)            # declared: required
        self.assertIn("| qa-audio |", out)
        self.assertIn("touches: humanoid, audio (declared)", out)
        # a guessed role is offered, but a task without touches is not held by it
        write(root, "tasks/TASK-032.md", "# TASK-032: Merchant NPC model\n## spec\ntype: art\n"
              "batch: one human merchant\n## gates\n| role | why | verdict |\n|---|---|---|\n"
              "| art-director | refs | APPROVED |\n| qa-readability | art | PASS |\n"
              "| verifier | close | PASSED |\n")
        code, out = run(root, "pipeline.py", "gates", "TASK-032", "--suggest")
        self.assertIn("touches: humanoid (guessed - confirm", out)
        code, out = run(root, "pipeline.py", "gates", "TASK-032")
        self.assertEqual(code, 0, out)
        self.assertIn("no touches: line", out)

    def test_perf_gate_informational_makes_qa_performance_advisory(self):
        # g2 rows 7/19: frame-time gates need a visible, focused window on an idle PC; on a shared
        # workstation the user dropped measurement sessions, and every lighting task stayed open.
        root = project()
        task = ("# TASK-030: lighting\n## spec\ntype: lighting\nbatch: plaza night\n"
                "## gates\n| role | why | verdict |\n|---|---|---|\n"
                "| qa-readability | route | PASS |\n| verifier | close | PASSED |\n")
        write(root, "tasks/TASK-030.md", task)
        code, out = run(root, "pipeline.py", "gates", "TASK-030")
        self.assertEqual(code, 1, out)
        self.assertIn("qa-performance", out)
        with open(os.path.join(root, "manifest.md"), "a", encoding="utf-8") as fh:
            fh.write("perf_gate=informational\n")
        code, out = run(root, "pipeline.py", "gates", "TASK-030")
        self.assertEqual(code, 0, out)
        code, out = run(root, "pipeline.py", "gates", "TASK-030", "--suggest")
        self.assertIn("| qa-performance | advisory (perf_gate=informational)", out)

    def test_migrate_brings_an_old_project_to_0_7(self):
        root = project()
        write(root, "tasks/TASK-020.md", "# TASK-020: Five merchant models\n## spec\ntype: art\n"
              "role: modeler\nbatch: five human merchants\npaths: art/npc/\n## checklist\n- [ ] x\n")
        write(root, "tasks/TASK-009.md", "# TASK-009: Greybox\n## spec\ntype: level\n"
              "role: level-designer\ntouches: none\n## gates\n| role | why | verdict |\n"
              "|---|---|---|\n| verifier | close | |\n")
        write(root, "tasks/archive/TASK-001.md", "# TASK-001: old\n## spec\ntype: art\n")
        write(root, "backlog.md", "- [ ] TASK-020 merchants\n- [ ] TASK-009 greybox\n"
              "- [x] TASK-001 old\n")
        code, out = run(root, "pipeline.py", "migrate")
        self.assertEqual(code, 0, out)
        with open(os.path.join(root, "tasks", "TASK-020.md"), encoding="utf-8") as fh:
            t20 = fh.read()
        self.assertIn("touches: humanoid\ntouches_source: guessed by migrate - confirm", t20)
        self.assertIn("| anatomy-expert |", t20)
        self.assertLess(t20.index("## gates"), t20.index("## checklist"))
        with open(os.path.join(root, "tasks", "TASK-009.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read().count("## gates"), 1)          # left as it was
        with open(os.path.join(root, "tasks", "archive", "TASK-001.md"), encoding="utf-8") as fh:
            self.assertNotIn("touches", fh.read())
        with open(os.path.join(root, "manifest.md"), encoding="utf-8") as fh:
            manifest = fh.read()
        for key in ("perf_gate=on", "on_screen=anytime", "agent_model=", "notes_files="):
            self.assertIn(key, manifest)
        with open(os.path.join(SCRIPTS, "..", "..", "..", ".claude-plugin", "plugin.json"),
                  encoding="utf-8") as fh:
            version = json.load(fh)["version"]
        self.assertIn(f"framework_version={version}", manifest)
        self.assertIn("TASK-020", out)
        code, again = run(root, "pipeline.py", "migrate")
        self.assertIn("nothing to migrate", again)

    def test_migrate_adds_the_problem_report_rule_to_the_project_rules(self):
        # S07: projects set up before 0.7.1 get the kiln-report.md rule in whichever file holds
        # the Kiln rules (CLAUDE.md, or AGENTS.md for Codex), once.
        for rules_file in ("CLAUDE.md", "AGENTS.md"):
            root = project()
            write(root, rules_file, "# Game\n\n## Rules that matter most\n\n- MCP only.\n\n"
                  "## Kiln settings\n\nIn manifest.md.\n")
            if rules_file == "AGENTS.md":
                write(root, "CLAUDE.md", "@AGENTS.md\n")
            code, out = run(root, "pipeline.py", "migrate")
            self.assertEqual(code, 0, out)
            with open(os.path.join(root, rules_file), encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("## Problem reports (kiln-report.md)", text)
            self.assertLess(text.index("## Problem reports"), text.index("## Kiln settings"))
            self.assertIn("pipeline.py\" row kiln-report.md", text)
            self.assertIn(f"{rules_file}: problem report rule added", out)
            if rules_file == "AGENTS.md":
                with open(os.path.join(root, "CLAUDE.md"), encoding="utf-8") as fh:
                    self.assertEqual(fh.read(), "@AGENTS.md\n")
            run(root, "pipeline.py", "migrate")
            with open(os.path.join(root, rules_file), encoding="utf-8") as fh:
                self.assertEqual(fh.read().count("## Problem reports"), 1)

    def test_row_appends_with_the_next_free_number(self):
        # g2 row 46: two agents wrote the same kiln_reports row number.
        root = project()
        write(root, "memory/kiln_reports.md", "| # | date | area |\n|---|---|---|\n"
              "| 1 | d | a |\n| 7 | d | b |\n")
        code, out = run(root, "pipeline.py", "row", "memory/kiln_reports.md", "2026-10-13 | guard")
        self.assertEqual(code, 0, out)
        code, out = run(root, "pipeline.py", "row", "memory/kiln_reports.md", "2026-10-13 | hooks")
        with open(os.path.join(root, "memory", "kiln_reports.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("| 8 | 2026-10-13 | guard |", text)
        self.assertIn("| 9 | 2026-10-13 | hooks |", text)
        self.assertIn("9", out)

    def test_row_creates_kiln_report_with_its_header(self):
        # S07: the first problem report creates kiln-report.md with the table header.
        root = project()
        code, out = run(root, "pipeline.py", "row", "kiln-report.md",
                        "2026-10-14 | playtester | guard | write denied | allow tests/ | open")
        self.assertEqual(code, 0, out)
        with open(os.path.join(root, "kiln-report.md"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        self.assertEqual(lines[0], "# Kiln problem reports")
        self.assertIn("| # | date | who | area | what happened | suggestion | status |", lines)
        self.assertEqual(lines[-1], "| 1 | 2026-10-14 | playtester | guard | write denied | allow tests/ | open |")

    def test_status_shows_editor_holders_and_queue(self):
        import time
        root = project()
        run(root, "pipeline.py", "init")
        now = time.time()
        write(root, ".kiln/locks.json", json.dumps({"godot": {
            "owner": "a1", "role": "level-designer", "session": "s", "ts": now,
            "since": now - 1200}}))
        write(root, ".kiln/queue.json", json.dumps({"godot": [
            {"owner": "a2", "role": "modeler", "session": "s", "since": now - 300, "ts": now}]}))
        code, out = run(root, "pipeline.py", "status")
        self.assertIn("Editors:", out)
        self.assertIn("godot: level-designer for 20 min", out)
        self.assertIn("waiting: modeler 5 min", out)

    def test_status_page(self):
        # F04: one page for a busy user: where things stand, who works, what was decided for them.
        import time
        root = project()
        run(root, "pipeline.py", "init")
        write(root, "backlog.md", "- [x] TASK-001 dagger\n- [~] TASK-020 merchants\n"
              "- [ ] TASK-021 crowd\n")
        write(root, "tasks/TASK-020.md", "# TASK-020: Five merchant models\n## spec\ntype: art\n"
              "touches: humanoid\n## gates\n| role | why | verdict |\n|---|---|---|\n"
              "| anatomy-expert | humanoid | |\n| verifier | close | |\n")
        run(root, "pipeline.py", "decide", "palette B for the rug", "--options", "A / B",
            "--by", "proxy", "--why", "closer to the bible")
        run(root, "pipeline.py", "decide", "Jolt physics", "--options", "Jolt / Godot",
            "--by", "user", "--why", "user said so")
        write(root, ".kiln/agents.json", json.dumps({"m1": {"role": "modeler", "session": "s",
                                                           "since": time.time() - 600}}))
        write(root, "production/autoplay/night1/REPORT.md",
              "# Autoplay report\n\nRuns: 12 · crashes mid-run: 1\n")
        code, out = run(root, "pipeline.py", "page")
        self.assertEqual(code, 0, out)
        with open(os.path.join(root, "production", "STATUS.html"), encoding="utf-8") as fh:
            page = fh.read()
        for text in ("Phase 0", "TASK-020", "anatomy-expert", "palette B for the rug",
                     "modeler", "Runs: 12", "1 / 3"):
            self.assertIn(text, page)
        self.assertNotIn("Jolt physics", page.split("Decided for you")[1].split("</section>")[0])
        self.assertIn("prefers-color-scheme", page)

    def test_backlog_template_example_is_not_a_task_id(self):
        # g2 row 12: replacing TASK-001 toggled the template's example line.
        template = os.path.join(SCRIPTS, "..", "..", "..", "templates", "project", "backlog.md")
        with open(template, encoding="utf-8") as fh:
            self.assertNotRegex(fh.read(), r"TASK-\d")


class Scope(unittest.TestCase):
    def test_counted_manual_blocked(self):
        root = project()
        os.makedirs(os.path.join(root, "scenes", "levels"))
        for n in ("a", "b"):
            write(root, f"scenes/levels/{n}.tscn", "x")
        write(root, "production/SCOPE.md",
              "- [ ] levels: 2 — count: glob:scenes/levels/*.tscn\n"
              "- [ ] final fight playable — manual\n"
              "- [ ] co-op — manual — BLOCKED: cut, decision #4\n")
        code, out = run(root, "scope.py", "check")
        self.assertEqual(code, 1, out)  # the manual promise is still open
        text = open(os.path.join(root, "production", "SCOPE.md"), encoding="utf-8").read()
        self.assertIn("- [x] levels", text)
        self.assertIn("- [ ] final fight", text)
        self.assertIn("- [x] co-op", text)
        write(root, "production/SCOPE.md", text.replace("- [ ] final fight", "- [x] final fight"))
        code, out = run(root, "scope.py", "check")
        self.assertEqual(code, 0, out)
        write(root, "production/SCOPE.md", "- [x] levels: 2 — count: glob:scenes/levels/*.tscn\n")
        code, out = run(root, "scope.py", "check")
        self.assertEqual(code, 1, out)  # two promises vanished from the contract
        self.assertIn("REMOVED OR RENAMED", out)


class Licences(unittest.TestCase):
    def test_registry_and_release_gate(self):
        root = project()
        write(root, "ref/manifest.csv", "ref_id,source_url,author,licence,local_path\n"
              "sheet,https://x,someone,unknown,ref/sheet.png\n")
        write(root, "art/generated/rock/provenance.json",
              json.dumps({"tool": "trellis2", "version": "1", "licence": "MIT"}))
        write(root, "assets/fonts/ui.ttf", "x")
        write(root, "assets/fonts/OFL.txt", "SIL Open Font License, Version 1.1")
        write(root, "addons/thing/plugin.cfg", "[plugin]")
        code, out = run(root, "licenses.py", "build")
        self.assertEqual(code, 1, out)  # the add-on has no licence file
        result = json.loads(out)
        self.assertEqual([r[0] for r in result["risky"]], ["addons/thing"])
        table = open(os.path.join(root, "production", "LICENSES.md"), encoding="utf-8").read()
        self.assertIn("| ref/sheet.png |", table)  # unknown but not shipped: no risk
        self.assertIn("OFL-1.1", table)
        gate = "nogrep:(?i)\\|\\s*(unknown|non-commercial|cc by-nc[^|]*)\\s*\\|[^|]*\\|\\s*yes\\s*\\|@production/LICENSES.md"
        cwd = os.getcwd()
        os.chdir(root)
        try:
            self.assertFalse(pipeline.run_check(gate))
            write(root, "addons/thing/LICENSE", "MIT License")
            run(root, "licenses.py", "build")
            self.assertTrue(pipeline.run_check(gate))
            # bug hunt 2026-10-20: CC BY output with nobody to credit passed
            credit = "nogrep:(?i)\\|\\s*cc[ -]by[^|]*\\|\\s*\\|\\s*yes\\s*\\|@production/LICENSES.md"
            write(root, "art/generated/crate/provenance.json",
                  json.dumps({"tool": "meshy", "licence": "CC BY 4.0, Meshy owns the output",
                              "attribution": ""}))
            code, out = run(root, "licenses.py", "build")
            self.assertEqual(code, 1, out)
            self.assertEqual([r[0] for r in json.loads(out)["risky"]], ["art/generated/crate"])
            self.assertFalse(pipeline.run_check(credit))
            write(root, "art/generated/crate/provenance.json",
                  json.dumps({"tool": "meshy", "licence": "CC BY 4.0, Meshy owns the output",
                              "attribution": "crate: generated with Meshy, CC BY 4.0"}))
            self.assertEqual(run(root, "licenses.py", "build")[0], 0)
            self.assertTrue(pipeline.run_check(credit))
        finally:
            os.chdir(cwd)


class Refs(unittest.TestCase):
    def test_palette_uses_liked_board_images(self):
        root = project()
        refs = os.path.join(root, "refs")
        os.makedirs(refs)
        Image.new("RGB", (32, 32), (255, 0, 0)).save(os.path.join(refs, "001_aaaa.jpg"))
        Image.new("RGB", (32, 32), (0, 0, 255)).save(os.path.join(refs, "002_bbbb.jpg"))
        write(root, "refs/sources.json", json.dumps({"items": [
            {"file": "001_aaaa.jpg", "url": "u1"}, {"file": "002_bbbb.jpg", "url": "u2"}]}))
        write(root, "fb.json", json.dumps({"latest": {"liked": ["img/0_002_bbbb.jpg"]}}))
        code, out = run(root, "refs_fetch.py", "palette", "refs", "--liked", "fb.json",
                        "--colors", "2")
        self.assertEqual(code, 0, out)
        self.assertIn("#0000f", out.lower().replace("#0000fe", "#0000ff"))
        self.assertNotIn("#ff0000", out.lower())


class AB(unittest.TestCase):
    def test_prepare_and_reveal(self):
        root = project()
        Image.new("RGB", (40, 30), (10, 10, 10)).save(os.path.join(root, "ours.png"))
        Image.new("RGB", (80, 60), (200, 200, 200)).save(os.path.join(root, "bar.png"))
        code, out = run(root, "ab.py", "prepare", "r1", "--ours", "ours.png", "--bar", "bar.png")
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(os.path.join(root, "r1", "A.png")))
        code, out = run(root, "ab.py", "reveal", "r1")
        self.assertNotEqual(code, 0, "reveal must refuse without a verdict")
        write(root, "r1/verdict.md", "WINNER: A\nGAP: edges too soft\n")
        code, out = run(root, "ab.py", "reveal", "r1")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
