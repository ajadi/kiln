"""Tests for plugins/kiln/skills/localization/scripts/loc_check.py (stdlib only)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "plugins", "kiln", "skills",
                      "localization", "scripts", "loc_check.py")

TSCN = '''[gd_scene format=3 uid="uid://abc"]

[node name="Menu" type="Control"]

[node name="Title" type="Label" parent="." groups=["ui"]]
text = "MENU_TITLE"

[node name="Start" type="Button" parent="."]
text = "Start Game"
tooltip_text = "Begin a new
run"

[node name="Count" type="Label" parent="."]
text = "%d / %d"

[node name="PlayerName" type="Label" parent="."]
auto_translate_mode = 2
text = "Ada"

[node name="Box" type="VBoxContainer" parent="."]
auto_translate_mode = 2

[node name="Inner" type="Label" parent="Box"]
text = "Inherited no-translate"

[node name="Quality" type="OptionButton" parent="."]
popup/item_0/text = "Low"
popup/item_1/text = "OPT_HIGH"
'''

GD = '''extends Control
@onready var label: Label = $Label

func _ready() -> void:
	label.text = "Score: %d" % 10
	$Ammo.text = tr("HUD_AMMO")
	$Hint.text = "HUD_HINT"  # key-shaped
	# label.text = "commented out"
	label.text = "Debug only"  # kiln:loc-ignore
	$Opt.add_item("Fullscreen")
	$Opt.set_item_text(0, tr("OPT_WINDOWED"))
	print("not user facing")
	if label.text == "x":
		pass
'''

CS = '''using UnityEngine;
public class Hud : MonoBehaviour {
    void Start() {
        ammoText.text = $"Ammo {ammo}";
        title.text = "MENU_TITLE";
        tmp.SetText("Game Over");
        // label.text = "ignored";
    }
}
'''

UXML = '''<ui:UXML xmlns:ui="UnityEngine.UIElements">
    <ui:Label name="a" text="Options" />
    <ui:Button name="b" text="Back">
        <Bindings>
            <UnityEngine.Localization.LocalizedString property="text" table="UI" entry="BACK" />
        </Bindings>
    </ui:Button>
</ui:UXML>
'''

CPP = '''void UHud::Show() {
    Label->SetText(FText::FromString(TEXT("Mission Failed")));
    Other->SetText(LOCTEXT("Win", "Mission Complete"));
}
'''

CSV = (
    "keys,en,fr,de,ja,_comment\n"
    "MENU_TITLE,Main Menu,Menu principal,Hauptmenü,メインメニュー,shown on title\n"
    "HUD_AMMO,Ammo: %d,Munitions : %d,Munition: %s,弾薬: %d,\n"
    "HUD_HINT,Press {key} to jump,Appuyez sur {key} pour sauter,,{key}でジャンプ,\n"
    "OPT_HIGH,High,Élevé,Hoch,高,\n"
    "OPT_WINDOWED,Windowed,Fenêtré,Fenstermodus mit Rahmen und Titelleiste,ウィンドウ,\n"
    "MENU_TITLE,Main Menu,Menu,Menü,メニュー,duplicate\n"
)

PLURAL_CSV = (
    "en,?plural,fr,pl,ja\n"
    "?pluralrule,,nplurals=2; plural=(n >= 2);,,\n"
    "There is %d apple,There are %d apples,Il y a %d pomme,Jest %d jabłko,リンゴが%d個あります\n"
    ",,Il y a %d pommes,Są %d jabłka,\n"
)

PO_FR = r'''msgid ""
msgstr ""
"Language: fr\n"
"Plural-Forms: nplurals=2; plural=(n > 1);\n"

msgid "Start Game"
msgstr "Commencer la partie"

#, fuzzy
msgid "Options"
msgstr "Options"

msgctxt "Menu"
msgid "Quit"
msgstr ""

msgid "%d enemy left"
msgid_plural "%d enemies left"
msgstr[0] "%d ennemi restant"
msgstr[1] "{count} ennemis restants"

msgid "Back"
msgstr "Retour "
"au menu"
'''


def write(root, name, text, bom=False):
    path = os.path.join(root, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write((b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8"))
    return path


def run(root, *args):
    p = subprocess.run([sys.executable, "-B", SCRIPT, *args], cwd=root, capture_output=True,
                       text=True, encoding="utf-8", timeout=60)
    return p.returncode, json.loads(p.stdout)


class LocCheck(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kiln-loc-")

    def test_sources_without_tables(self):
        write(self.root, "scenes/ui/menu.tscn", TSCN)
        write(self.root, "scripts/hud.gd", GD)
        write(self.root, "addons/plugin/skip.gd", 'func f():\n\tl.text = "Plugin text"\n')
        code, rep = run(self.root, "--src", ".", "scripts/hud.gd")  # walk + dedupe, addons skipped
        self.assertEqual(code, 1)
        texts = sorted(h["text"] for h in rep["hardcoded"])
        self.assertEqual(texts, ["Begin a new\nrun", "Fullscreen", "Low", "Score: %d",
                                 "Start Game"])
        tooltip = next(h for h in rep["hardcoded"] if h["property"] == "tooltip_text")
        self.assertEqual((tooltip["node"], tooltip["line"]), ("Start", 10))
        self.assertEqual(rep["unknown_keys"], [])  # keys are not judged without tables

    def test_glob_and_other_languages(self):
        write(self.root, "Assets/UI/Hud.cs", CS)
        write(self.root, "Assets/UI/Menu.uxml", UXML)
        write(self.root, "Source/Game/Hud.cpp", CPP)
        code, rep = run(self.root, "--src", "Assets/**/*.cs", "Assets/**/*.uxml",
                        "Source/**/*.cpp")
        texts = sorted(h["text"] for h in rep["hardcoded"])
        self.assertEqual(texts, ["Ammo {ammo}", "Game Over", "Mission Failed", "Options"])
        self.assertEqual(code, 1)

    def test_tables_and_keys(self):
        write(self.root, "scenes/ui/menu.tscn", TSCN)
        write(self.root, "scripts/hud.gd", GD)
        write(self.root, "locale/game.csv", CSV)
        code, rep = run(self.root, "--src", "scenes", "scripts", "--tables", "locale/*.csv",
                        "--locales", "fr,de,ja,ko")
        self.assertEqual(code, 1)
        s = rep["summary"]
        self.assertEqual(s["missing_locales"], ["ko"])
        table = rep["tables"][0]
        self.assertEqual(table["missing"], {"de": ["HUD_HINT"]})
        self.assertEqual(len(table["duplicates"]), 1)
        mismatch = table["placeholder_mismatch"]
        self.assertEqual([(m["key"], m["locale"]) for m in mismatch], [("HUD_AMMO", "de")])
        risky = {(r["key"], r["locale"]) for r in table["expansion_risk"]}
        self.assertIn(("OPT_WINDOWED", "de"), risky)
        self.assertNotIn(("OPT_HIGH", "ja"), risky)
        # key-shaped literals present in the table are fine, the rest are unknown keys
        self.assertEqual([h["text"] for h in rep["unknown_keys"]], [])
        self.assertNotIn("Main Menu", [h["text"] for h in rep["hardcoded"]])

    def test_unknown_key_and_clean_pass(self):
        write(self.root, "scenes/a.tscn",
              '[gd_scene format=3]\n\n[node name="A" type="Label"]\ntext = "HUD_MISSING"\n')
        write(self.root, "locale/t.csv", "keys,en,fr\nHUD_OK,OK,OK\n")
        code, rep = run(self.root, "--src", "scenes", "--tables", "locale/t.csv")
        self.assertEqual(code, 1)
        self.assertEqual([h["text"] for h in rep["unknown_keys"]], ["HUD_MISSING"])
        write(self.root, "scenes/a.tscn",
              '[gd_scene format=3]\n\n[node name="A" type="Label"]\ntext = "HUD_OK"\n')
        code, rep = run(self.root, "--src", "scenes", "--tables", "locale/t.csv")
        self.assertEqual((code, rep["verdict"]), (0, "pass"))

    def test_plural_csv(self):
        write(self.root, "locale/plural.csv", PLURAL_CSV)
        code, rep = run(self.root, "--tables", "locale/plural.csv")
        table = rep["tables"][0]
        self.assertEqual(table["locales"], ["fr", "pl", "ja"])
        forms = table["missing_plural_forms"]
        self.assertEqual([(f["locale"], f["have"], f["want"]) for f in forms], [("pl", 2, 3)])
        self.assertEqual(table["placeholder_mismatch"], [])
        self.assertEqual(code, 1)

    def test_po(self):
        write(self.root, "locale/fr.po", PO_FR)
        write(self.root, "locale/messages.pot", 'msgid "Start Game"\nmsgstr ""\n')
        write(self.root, "scenes/m.tscn",
              '[gd_scene format=3]\n\n[node name="M" type="Button"]\ntext = "Start Game"\n')
        code, rep = run(self.root, "--src", "scenes", "--tables", "locale/*.po*")
        self.assertEqual(rep["hardcoded"], [])  # msgid used as key
        po = next(t for t in rep["tables"] if t.get("format") == "po")
        self.assertEqual(po["locales"], ["fr"])
        self.assertEqual(sorted(po["missing"]["fr"]), ["Options", "Quit"])  # fuzzy + empty
        self.assertEqual(po["fuzzy"], ["Options"])
        self.assertEqual(len(po["placeholder_mismatch"]), 1)
        self.assertEqual(po["placeholder_mismatch"][0]["extra"], ["count"])
        self.assertEqual(code, 1)

    def test_expansion_min_width_and_allow_list(self):
        # g2 row 32: a compact source language flagged every short EN string (11 false alarms).
        write(self.root, "locale/a.csv", "keys,pl,en\nBTN_OK,Ok,Okay\nBTN_BACK,Wstecz,Go back\n"
              "HINT_LONG,Naciśnij,Press and hold the button\n")
        code, rep = run(self.root, "--tables", "locale/a.csv", "--source-locale", "pl")
        self.assertEqual(rep["summary"]["expansion_risk"], 2)
        code, rep = run(self.root, "--tables", "locale/a.csv", "--source-locale", "pl",
                        "--expansion-min-width", "6", "--expansion-allow", "HINT_LONG")
        self.assertEqual(rep["summary"]["expansion_risk"], 0, rep["tables"])

    def test_bom_and_expansion_flag(self):
        write(self.root, "locale/a.csv", "keys,en,de\nBTN_OK,OK,Bestätigen\n", bom=True)
        code, rep = run(self.root, "--tables", "locale/a.csv")
        self.assertEqual(rep["summary"]["table_problems"], 1)
        self.assertEqual(code, 1)
        write(self.root, "locale/a.csv", "keys,en,de\nBTN_OK,OK,Bestätigen\n")
        code, rep = run(self.root, "--tables", "locale/a.csv")
        self.assertEqual((code, rep["summary"]["expansion_risk"]), (0, 1))
        code, rep = run(self.root, "--tables", "locale/a.csv", "--fail-on-expansion")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
