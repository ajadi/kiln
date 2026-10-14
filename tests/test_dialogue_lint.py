"""Tests for plugins/kiln/skills/narrative/scripts/dialogue_lint.py (stdlib only)."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills", "narrative",
                      "scripts", "dialogue_lint.py")

CLEAN_YARN = """\
title: Start
tags: entry
---
Guard: Halt. Who goes there? #line:GATE_GUARD_0010
-> Player: A friend. #line:GATE_PLAYER_0020
    <<jump Friend>>
-> Player: None of your business. #line:GATE_PLAYER_0030
    Guard: Then turn back. #line:GATE_GUARD_0040
    <<stop>>
-> Player: Tell me about the gate. <<if $curious>> #line:GATE_PLAYER_0050
    <<detour GateLore>>
    <<jump Friend>>
===
title: Friend
---
Guard: Welcome, {$player_name}. #line:GATE_GUARD_0060
<<stop>>
===
title: GateLore
---
// detour target: returning at its end is intended
Guard: Built in the [b]third[/b] age. #line:GATE_GUARD_0070
===
"""

GROUP_YARN = """\
title: Start
---
<<jump Barkeep>>
===
title: Barkeep
when: once
---
Barkeep: First time here? #line:BAR_0010
<<stop>>
===
title: Barkeep
when: always
---
Barkeep: Back again. #line:BAR_0020
<<stop>>
===
"""

BAD_YARN = """\
title: Start
---
Guard: This line has no id.
Guard: This line is far too long for one subtitle card, it keeps going and going on. #line:BAD_0010
Guard: Same id twice. #line:BAD_0010
-> Pay. <<if $gold > 5>> #line:BAD_0020
    <<jump Paid>>
-> Threaten. <<if $strong>> #line:BAD_0030
    <<jump Nowhere>>
===
title: Paid
---
Guard: Go on. #line:BAD_0040
===
title: Orphan
---
Guard: Nobody comes here. #line:BAD_0050
<<stop>>
===
title: Paid
---
Guard: Duplicate node. #line:BAD_0060
<<stop>>
===
"""


def write(root, name, content):
    path = os.path.join(root, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    return path


def run(*args, cwd=None):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], capture_output=True, text=True,
                       encoding="utf-8", timeout=60, cwd=cwd)
    return p.returncode, json.loads(p.stdout)


def checks(report, severity="errors"):
    return sorted(f["check"] for f in report[severity])


class YarnLint(unittest.TestCase):
    def test_clean_script_passes(self):
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        path = write(root, "gate.yarn", CLEAN_YARN)
        code, rep = run(path)
        self.assertEqual(code, 0, rep)
        self.assertEqual(rep["verdict"], "PASS", rep)
        self.assertEqual(rep["stats"]["nodes"], 3)
        self.assertEqual(rep["stats"]["choices"], 3)
        self.assertEqual(rep["stats"]["lines"], 7)
        self.assertGreater(rep["stats"]["vo_minutes_est"], 0)

    def test_node_groups_are_not_duplicates(self):
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        code, rep = run(write(root, "bar.yarn", GROUP_YARN))
        self.assertEqual(rep["verdict"], "PASS", rep)

    def test_bad_script_reports_every_problem(self):
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        code, rep = run(write(root, "bad.yarn", BAD_YARN), "--max-chars", "60")
        self.assertEqual(code, 1)
        self.assertEqual(rep["verdict"], "FAIL")
        errs = checks(rep)
        for expected in ("missing_id", "too_long", "duplicate_id", "broken_link", "unreachable",
                         "duplicate_node"):
            self.assertIn(expected, errs, rep)
        warns = checks(rep, "warnings")
        self.assertIn("choices_all_conditional", warns)
        self.assertIn("implicit_end", warns)  # Paid ends without <<stop>>
        orphan = [f for f in rep["errors"] if f["check"] == "unreachable"]
        self.assertEqual([f["node"] for f in orphan], ["Orphan"])
        long_line = [f for f in rep["errors"] if f["check"] == "too_long"][0]
        self.assertEqual(long_line["line"], 4)

    def test_ids_can_be_relaxed_and_entries_given(self):
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        path = write(root, "intro.yarn", textwrap.dedent("""\
            title: Intro
            ---
            Narrator: It was raining.
            <<stop>>
            ===
            """))
        code, rep = run(path)
        self.assertIn("missing_id", checks(rep))
        self.assertIn("no_entry", checks(rep, "warnings"))
        code, rep = run(path, "--ids", "warn", "--entry", "Intro")
        self.assertEqual(rep["verdict"], "WARN")
        self.assertEqual(code, 0)
        code, rep = run(path, "--ids", "off", "--entry", "Intro")
        self.assertEqual(rep["verdict"], "PASS", rep)
        code, rep = run(path, "--ids", "warn", "--entry", "Intro", "--strict")
        self.assertEqual((code, rep["verdict"]), (1, "FAIL"))
        code, rep = run(path, "--ids", "off", "--entry", "Missing")
        self.assertIn("broken_link", checks(rep))

    def test_cross_file_jumps_and_globs(self):
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        write(root, "dlg/a.yarn", "title: Start\n---\nA: Hi. #line:X_1\n<<jump Other>>\n===\n")
        write(root, "dlg/sub/b.yarn", "title: Other\n---\nB: Bye. #line:X_2\n<<stop>>\n===\n")
        code, rep = run("dlg/**/*.yarn", cwd=root)
        self.assertEqual(rep["verdict"], "PASS", rep)
        self.assertEqual(rep["stats"]["files"], 2)
        code, rep = run("dlg", cwd=root)  # directory input
        self.assertEqual(rep["stats"]["files"], 2)

    def test_markup_tags_and_expressions_do_not_count(self):
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        line = "Guard: [wave]Hello[/wave] {$name}! #line:M_1 #tone:warm"
        path = write(root, "m.yarn", f"title: Start\n---\n{line}\n<<stop>>\n===\n")
        # visible: "Hello XXXXXXXX!" = 15 chars
        self.assertEqual(run(path, "--max-chars", "15")[1]["verdict"], "PASS")
        self.assertIn("too_long", checks(run(path, "--max-chars", "14")[1]))

    def test_option_limit(self):
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        path = write(root, "o.yarn", "title: Start\n---\nA: Pick. #line:O_1\n"
                                     "-> I would like to hear the whole long story, please. #line:O_2\n"
                                     "    <<stop>>\n-> No. #line:O_3\n    <<stop>>\n===\n")
        code, rep = run(path)
        long_opts = [f for f in rep["errors"] if f["check"] == "too_long"]
        self.assertEqual([f["id"] for f in long_opts], ["O_2"])
        self.assertEqual(run(path, "--max-option-chars", "60")[1]["verdict"], "PASS")

    def test_non_ascii_text(self):
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        path = write(root, "pl.yarn", "title: Start\n---\nStrażnik: Stój! Kto idzie? #line:PL_1\n"
                                      "<<stop>>\n===\n")
        code, rep = run(path, "--max-chars", "10")
        self.assertIn("Kto", [f for f in rep["errors"] if f["check"] == "too_long"][0]["message"])

    def test_dynamic_jump_skips_unreachable(self):
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        path = write(root, "d.yarn", "title: Start\n---\n<<jump {$next}>>\n===\n"
                     "title: Later\n---\nA: x #line:D_1\n<<stop>>\n===\n")
        code, rep = run(path)
        self.assertIn("dynamic_jump", checks(rep, "warnings"))
        self.assertNotIn("unreachable", checks(rep))


class TableLint(unittest.TestCase):
    def test_kiln_json_graph(self):
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        doc = {
            "format": "kiln-dialogue/1",
            "entries": ["Q1_START"],
            "nodes": [
                {"id": "Q1_START",
                 "lines": [{"id": "Q1_0010", "speaker": "SMITH", "text": "Need a blade?"}],
                 "choices": [
                     {"id": "Q1_0020", "text": "Yes.", "next": "Q1_BUY"},
                     {"id": "Q1_0030", "text": "Later.", "end": True},
                     {"id": "Q1_0040", "text": "Haggle.", "next": "Q1_GONE"}]},
                {"id": "Q1_BUY", "lines": [{"text": "Fine steel."}]},
                {"id": "Q1_COND", "lines": [{"id": "Q1_0010", "text": "Dup id."}],
                 "choices": [{"id": "Q1_0050", "text": "a", "condition": "$x", "end": True}]},
            ],
        }
        path = write(root, "smith.json", json.dumps(doc))
        write(root, "other.json", json.dumps({"not": "dialogue"}))
        code, rep = run(root)
        self.assertEqual(code, 1)
        errs = checks(rep)
        self.assertEqual(errs.count("broken_link"), 1)          # Q1_GONE
        self.assertIn("dead_end", errs)                         # Q1_BUY: no next/end
        self.assertIn("missing_id", errs)                       # Fine steel.
        self.assertIn("duplicate_id", errs)                     # Q1_0010
        self.assertIn("unreachable", errs)                      # Q1_COND
        self.assertIn("choices_all_conditional", checks(rep, "warnings"))
        self.assertEqual(len(rep["skipped_json"]), 1)
        self.assertTrue(path)

    def test_csv_line_table_godot_style(self):
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        path = write(root, "barks.csv", "keys,en,de,max_chars\n"
                                        "BARK_RELOAD_01,Reloading!,Lade nach!,\n"
                                        ",Cover me!,Gib mir Deckung!,\n"
                                        "BARK_RELOAD_01,Dup,Dup,\n"
                                        "UI_OK,Okay then fine,Okay,8\n")
        code, rep = run(path)
        errs = checks(rep)
        self.assertEqual(errs, ["duplicate_id", "missing_id", "too_long"], rep)
        too_long = [f for f in rep["errors"] if f["check"] == "too_long"][0]
        self.assertEqual(too_long["line"], 5)
        code, rep = run(path, "--lang", "de", "--max-chars", "12")
        self.assertIn("too_long", checks(rep))  # "Gib mir Deckung!" is 16 chars

    def test_godot_comment_max_column_per_locale(self):
        # g2 row 32: per-row limits sat in the Godot CSV comment column `_max` (replies <= 40,
        # lines longer), which the lint ignored.
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        path = write(root, "talk.csv", "keys,pl,en,_max,_max_en\n"
                                       "REPLY_01,Pokaż towar,Show me what you have here today,"
                                       "40,24\n"
                                       "LINE_01,Długa kwestia kupca,A merchant line,80,\n")
        code, rep = run(path, "--lang", "en", "--max-chars", "200")
        long = [f for f in rep["errors"] if f["check"] == "too_long"]
        self.assertEqual([f["id"] for f in long], ["REPLY_01"], rep)   # 32 > _max_en 24
        code, rep = run(path, "--lang", "pl", "--max-chars", "200")
        self.assertNotIn("too_long", checks(rep))                            # 10 <= _max 40

    def test_nothing_found(self):
        root = tempfile.mkdtemp(prefix="kiln-dlg-")
        code, rep = run(os.path.join(root, "*.yarn"))
        self.assertEqual(code, 2)
        self.assertEqual(rep["verdict"], "FAIL")
        self.assertEqual(len(rep["not_found"]), 1)


if __name__ == "__main__":
    unittest.main()
