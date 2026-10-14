---
name: localization
description: "Localizing game text - keys from the first UI string, key naming, extract/translate/import (Godot CSV and PO, Unity string tables, Unreal String Tables and Localization Dashboard), translator context, CLDR plurals and gender, placeholders, expansion budgets and layout, RTL, CJK and font fallbacks, numbers and dates, pseudolocalization as a gate, voice-over per language, loc_check.py gates. Load for any task that adds or changes player-facing text, fonts or languages."
user-invocable: false
---

# Localization

Every player-facing string is a key in a table from the first prototype menu, layouts are proven
with pseudolocalization before a translator sees them, and tables are accepted by `loc_check.py`.
Values marked (working) are starting points. Sizes, contrast, layout checks: `kiln:ui`; subtitle
timing: `kiln:accessibility`; line IDs, dialogue formats, VO scripts: `kiln:narrative`.

- `${extensionPath}${/}skills${/}localization/scripts/loc_check.py` — hard-coded strings in sources, table gaps (§12).
- `${extensionPath}${/}skills${/}localization/references/engines.md` — read when setting up or changing localization in
  Godot, Unity or Unreal (settings, MCP calls, fonts, pseudolocalization, sources).

## 1. Start with the first UI text

1. Day one: source locale (default `en`), table format, one table per domain (`ui`, `items`,
   `dialogue`) with only the source column. A new language is then a column, not a refactor.
2. Decide early (`memory/decisions.md`): languages, register (tu/vous, du/Sie), RTL or CJK in
   scope (fonts and layout change from the first screen), never-translated text (player names).
3. Pseudolocalization on in development runs from the first menu (§10).

## 2. Externalize strings, name keys

- No user-facing literal in scenes or code: nodes hold keys, code calls the engine's translation.
  Text that must not translate (names, numbers, debug) is marked so (Godot `auto_translate_mode`
  Disabled, Unreal `INVTEXT`) or its line carries `kiln:loc-ignore`.
- Key = `AREA_CONTEXT_ITEM[_VARIANT]`, upper case (`MENU_MAIN_PLAY`, `HUD_AMMO_COUNT`,
  `ITEM_MEDKIT_DESC`); dialogue uses narrative line IDs. Both match loc_check's `--key-pattern`.
- A key is a meaning in a place: "Close" on a door and on a dialog are two keys (or one key with
  context). A changed meaning gets a new key; keys are deleted only at a lock.
- No text baked into textures; unavoidable text art is a per-locale asset.

## 3. Extract → translate → import

1. **Extract**: CSV keys are added while building; Godot PO: Template Generation → POT, then
   `msgmerge --update --backup=none fr.po messages.pot`; Unity: CSV or XLIFF export; Unreal:
   Dashboard Gather Text → Export (PO).
2. **Freeze** a batch: source final, loc_check clean, pseudolocalized captures passed.
3. **Hand off** table, context notes, glossary, screenshots; the same format comes back.
4. **Import** through the engine MCP, run loc_check, capture every screen per new locale.
5. **Source changed later**: mark the translation for review (PO `fuzzy`, CSV cell cleared);
   loc_check fails on both until re-translated.

## 4. Context notes for translators

Per key: screen and widget (screenshot path), max chars, each placeholder with an example value,
the counted noun, speaker and addressee, glossary and do-not-translate terms. Carriers: Godot CSV
`_` columns (`_note`, `_max`; not imported), PO `#.` comments (`# TRANSLATORS:` in GDScript),
Unity Comment metadata, Unreal String Table metadata.

## 5. Plurals and gender (CLDR)

- Categories zero, one, two, few, many, other: en/de one, other; fr/es/it/pt one, many, other
  (many = millions); ru/pl/cs one, few, many, other; ar all six; ja/zh/ko other only. "one" is
  not "1": ru one = 1, 21, 31…, few = 2–4, 22–24…, many = 0, 5–20, 100….
- Godot CSV/PO count gettext forms, not CLDR categories (ru 3, fr 2, ar 6); loc_check reads
  nplurals from `?pluralrule` / `Plural-Forms`, else its built-in table.
- One key per counted message with all forms; never `n == 1` branches or "item(s)". Godot
  `tr_n()` (positive integers), Unity `{n:plural:…|…}`, Unreal `{N}|plural(one=…,other=…)`.
- Gender: rephrase neutrally first; else variants by context (Godot `?context`/`msgctxt`),
  Unity `{g:choose(Male|Female):…|…|…}`, Unreal `|gender(…)`. Never compose article + noun or
  adjective + item from separate keys.

## 6. Placeholders

- Named `{player}`, `{count}` so translators can reorder (GDScript `%` cannot): Godot
  `tr("KEY").format({"count": n})`, Unity Smart String `{count}`, Unreal `{Count}`.
- Same set in every translation: loc_check compares printf `%s %d` in order and braces as a
  multiset; plural forms may drop a placeholder, never add one.
- No concatenated fragments; input glyphs are placeholders (`{btn_jump}`); markup tags wrap whole
  phrases and survive translation (loc_check does not compare tags — the reviewer does).

## 7. Expansion budget and layout

Average expansion from English (IBM via W3C): ≤ 10 chars 200–300%, 11–20 180–200%, 21–30
160–180%, 31–50 140–160%, 51–70 151–170%, > 70 130%. CJK has fewer but wide characters
(loc_check counts them 2); Thai, Arabic, Devanagari need taller lines.

1. Text sits in containers that grow; no width fitted to English; buttons get a minimum width.
2. Sentences autowrap; one-word buttons budget 2× the source width or a second line (working).
3. Never shrink text below the ui skill minimum; ellipsis only for user content (names).
4. Max chars per key come from the real layout and go into the context notes (§4).

## 8. RTL, CJK, fonts

- RTL (ar, he, fa, ur): layout mirrors by locale and the engine shapes text (Godot Advanced text
  server, Unity UI Toolkit Advanced Text Generator — not uGUI/TextMeshPro, Unreal flow direction
  Culture); never reverse strings by hand; numbers and Latin names stay LTR inside.
- CJK, Thai, Khmer, Lao, Burmese break lines by dictionary (Godot export:
  `include_text_server_data`). Han glyphs differ per language: ja, zh-Hans, zh-Hant, ko each
  get their own font (Noto Sans CJK JP/SC/TC/KR) or language tagging.
- Bundled fallback chain per ui §6; system fallback is a safety net only. No tofu (□) in any
  locale capture.

## 9. Numbers, dates, units

Never concatenate numbers: grouping and decimals (1,234.5 en, 1 234,5 fr), native digits, date
order, 12/24 h, metric/imperial setting; currency strings from the store. Godot only converts
digits (`format_number`) — keep patterns as keys (`FMT_DATE` = `{d}.{m}.{y}`); Unity Smart
Strings use the locale's CultureInfo (`{0:N}`); Unreal `FText::AsNumber/AsDate`. Saves and
network use invariant culture.

## 10. Pseudolocalization as a gate

Accents, +30% length, brackets `[ ]`, fake BiDi when RTL ships: Godot
`internationalization/pseudolocalization/*`, Unity Pseudo-Locale, Unreal `culture=keys`
(engines.md). Pass per screen and HUD state at 1080p and the minimum window: every string shows
`[…]` (none = hard-coded), every closing `]` visible, accents uncut, `ui_check.py layout` clean.

## 11. Voice-over per language

VO script per line ID per locale (narrative `references/production.md`), files
`vo/<locale>/<ID>`; per line wild, time-constrained (±10% of the source take, working) or
lip-sync. Subtitles re-timed per locale, checked with `subtitle_check.py`. Voice language is its
own setting; a locale without VO plays source audio with localized subtitles.

## 12. Engines and checks

Tables, settings and text properties change in the open editor through the engine MCP; no
hand-edited `.tscn`/`.tres`/`project.godot`, Unity `.asset` or Unreal `.uasset`/`Config` files.

- **Godot 4.6/4.7**: CSV (`keys,en,…`, UTF-8 no BOM) or PO via `filesystem_manage`, registered
  in `internationalization/locale/translations`; Controls hold keys, auto-translate on.
- **Unity 6**: Localization 1.5 string tables, `LocalizedString` bindings, Smart Strings.
- **Unreal 5.8**: `FText` only (`LOCTEXT`, String Tables), Dashboard gather → PO → compile.

`python ${extensionPath}${/}skills${/}localization/scripts/loc_check.py --src <dirs|files|globs> --tables <csv|po|pot>
--locales <shipping>` → JSON `verdict`, exit 1 on fail. Options: `--source-locale en`,
`--max-expansion 1.4`, `--fail-on-expansion`, `--expansion-min-width 6` (skip short labels:
a compact source such as Russian made every short English string a "risk" — 11 false alarms
in g2), `--expansion-allow KEY,...|@file` (reviewed keys), `--key-pattern`, `--delimiter`,
`--max-items`. Per-row length limits for dialogue go in the Godot CSV comment column `_max`
(or `_max_<locale>`); the narrative skill's `dialogue_lint.py` reads it.
Scans .tscn/.tres, .gd, .cs, .uxml, .cpp/.h; skips `auto_translate_mode = 2` subtrees, `addons/`
and `kiln:loc-ignore` lines.

| Gate | Pass |
|---|---|
| Hard-coded strings | `hardcoded` 0, `unknown_keys` 0 |
| Translations | `missing`, `missing_plural_forms`, `fuzzy`, `duplicates`, `table_problems` 0; `missing_locales` [] |
| Placeholder parity | `placeholder_mismatch` 0 |
| Expansion | each `expansion_risk` row (> 1.4×) shortened, or its screen passed a capture in that locale or pseudolocalized at ≥ its ratio (path in the task file); else `--fail-on-expansion` |
| Pseudolocalized layout | §10 on every screen and HUD state |
| Each shipping locale | screens captured: no tofu, no clipping; runtime language switch updates all text and persists |
