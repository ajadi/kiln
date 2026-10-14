# Localization per engine

Everything here happens in the open editor through the engine MCP. Confirm an API you have not
used before (`api_manage`, `unity_reflect`, `describe_toolset`). Items marked UNVERIFIED were not
confirmed in official documentation — check them in the running editor before relying on them.

## Godot 4.6/4.7 (Godot AI)

| What | How |
|---|---|
| Table sources | `res://locale/<domain>.csv` — header `keys,en,fr,…`, `_`-prefixed comment columns, `?context` and `?plural` columns and a `?pluralrule` row (4.6+), UTF-8 without BOM, cells with commas/newlines quoted, `""` for a quote. Or `res://locale/<locale>.po` + `messages.pot`. Written with `filesystem_manage` `write_text`, then `scan` so the editor reimports |
| Import | CSV → `<name>.<locale>.translation` next to the CSV, one per locale column (every other column name must start with `_`). Import options (Import dock): `compress` Auto (OptimizedTranslation, falls back for context/plurals), `delimiter`, `unescape_keys` false, `unescape_translations` true. PO/MO import directly; `fuzzy` entries are not read. No MCP op for import options is documented — ask the user |
| Register | `project_manage` `settings_set` `internationalization/locale/translations` = the `.translation` / `.po` paths — importing does not register them |
| Fallback / test | `internationalization/locale/fallback` = source locale. `internationalization/locale/test` also applies to exports — set it as `internationalization/locale/test.editor`; same for `…/use_pseudolocalization.editor` |
| Template | Project Settings → Localization → Template Generation (`internationalization/locale/translations_pot_files`): parses scenes and GDScript (`tr`, `tr_n`, `atr`, `atr_n`, `text`, `placeholder_text`, `tooltip_text`, `add_item`, `add_tab`, `set_tab_title`…); `# TRANSLATORS:` becomes a note, `# NO_TRANSLATE` skips; writes POT, or CSV in 4.6+. An editor button — ask the user unless the MCP exposes it |
| Remaps | `internationalization/locale/translation_remaps` — per-locale VO, fonts, textures |
| Text server | `internationalization/rendering/text_driver` empty = "ICU / HarfBuzz / Graphite" (needed for RTL and complex scripts); `internationalization/locale/include_text_server_data` on when shipping CJK, Thai, Khmer, Lao or Burmese (~4 MB) |
| Pseudolocalization | `internationalization/pseudolocalization/`: `use_pseudolocalization` (read at startup; at runtime `TranslationServer.pseudolocalization_enabled`, `reload_pseudolocalization()` after changes), `replace_with_accents` (default on), `expansion_ratio` 0.3 (default 0), `prefix` `[` / `suffix` `]` (defaults), `skip_placeholders` (default on), `fake_bidi` for the RTL pass, `override` (every char `*`) for a hard-coded sweep |
| RTL test | `internationalization/rendering/force_right_to_left_layout_direction` (testing only) |

Scenes and scripts:
- A Control's `text` holds the key; `auto_translate_mode` Inherit (the root is Always by
  `internationalization/rendering/root_node_auto_translate`), Disabled (2) on nodes that show
  player names, numbers or debug text — set with `node_set_property`.
- Formatted text: `label.text = tr("HUD_AMMO_COUNT").format({"ammo": ammo, "max": max_ammo})` on a
  Label whose auto-translate is Disabled, so the result is not looked up again (working). Refresh
  in `_notification(what)` on `NOTIFICATION_TRANSLATION_CHANGED` (`await ready` if not ready).
- Plurals with keys — `tr_n("ENEMY_LEFT", "ENEMY_LEFT_PL", n).format({"n": n})`:

```
keys,?plural,en,ru,_note
POINTS_LEFT,POINTS_LEFT_PL,{n} point left,Pozostał {n} punkt,points left in the round
,,{n} points left,Pozostały {n} punkty,
,,,Pozostało {n} punktów,
```

- Context: `tr("CLOSE", "door")` with a `?context` column (CSV) or `msgctxt` (PO).
- Language setting: `TranslationServer.set_locale(code)`, saved with the settings; first launch
  uses `OS.get_locale_language()` when it is shipped, else the fallback.
- Numbers: `TranslationServer.format_number(str, locale)` converts digits only; Controls convert
  SpinBox/ProgressBar digits by `localize_numeral_system`. Grouping and dates come from
  per-locale pattern keys.
- RTL: Control `layout_direction` (Inherited, Application locale, LTR, RTL, System locale) and
  `text_direction`; `structured_text_bidi_override` for paths, URLs, emails.
- Fonts (ui `references/godot.md` §2.6): fallbacks in Advanced Import Settings or a
  FontVariation resource (`resource_manage`); fallbacks that do not support the text's language
  and script are tried last, so set `language_support` overrides (`ja` on the JP font, `zh` on SC)
  or the Label `language` property. `allow_system_fallback` defaults to true; system fonts load
  only on Windows, macOS, Linux, Android and iOS. Pre-render configurations can pre-render glyphs
  from translations.

Verify: `project_run` → `editor_manage` `game_eval` `TranslationServer.set_locale("de")` →
`editor_screenshot` {source: "game"} → `game_manage` `get_ui_elements` → `ui_check.py layout`;
repeat per locale and with pseudolocalization on. `loc_check.py --src scenes scripts --tables
"locale/*.csv"` (or `"locale/*.po*"`).

## Unity 6 (MCP for Unity)

- Package `com.unity.localization` 1.5.x (1.5.13 released for 6000.0) via `manage_packages`;
  adding it is a `memory/decisions.md` row (open question if undecided).
- Localization Settings, one Locale per language, a String Table Collection per domain (`UI`,
  `Items`, `Dialogue`); entry Key = Kiln key; Smart flag on entries with placeholders, plurals or
  gender. Tables are `.asset` files — change them with the editor API through `execute_code`
  (`LocalizationEditorSettings.GetStringTableCollection("UI")`,
  `CreateStringTableCollection(name, dir)`, `AddLocale(locale, false)`) or the Localization
  Tables window; never edit their YAML.
- CSV round trip: `UnityEditor.Localization.Plugins.CSV.Csv.Export(writer, collection, columns)`
  and `Csv.ImportInto(reader, collection, columns, …)`. For translators and loc_check set the
  columns Godot-style: `KeyIdColumns` KeyFieldName `keys`, IncludeId off, SharedCommentFieldName
  `_note`; each `LocaleColumns` FieldName = locale code (`en`, `fr`), CommentFieldName
  `_<code>_note`. The default headers (`Key,Id,English(en)`) hide locales from loc_check.
- UI Toolkit (Unity 6+): text bound in UXML — `<ui:Label text="Play"><Bindings>
  <UnityEngine.Localization.LocalizedString property="text" table="UI" entry="MENU_MAIN_PLAY" />
  </Bindings></ui:Label>` (UI Builder: right-click a field → Add binding). loc_check flags
  `text`/`label`/`tooltip` attributes without such a binding. uGUI: `LocalizeStringEvent`
  component (`manage_components`).
- Smart Strings: `{count}`, `{0:plural:…|…}` with forms in the table locale's CLDR order,
  `{g:choose(Male|Female):…|…|…}`, `{0:N}` and dates by the locale's CultureInfo.
- Pseudo-Locale: Assets → Create → Localization → Pseudo-Locale (default methods Accenter,
  Expander, Encapsulator; Mirror for RTL); select it in the Game view locale menu or by
  `LocalizationSettings.SelectedLocale`; keep it out of release builds.
- RTL and complex scripts: UI Toolkit with the Advanced Text Generator (Project Settings → UI
  Toolkit → Enable Advanced Text Generator; dynamic font assets only); the `language-direction`
  UXML attribute (Inherited, LTR, RTL) sets text direction — mirror the layout with an RTL USS
  class (working). uGUI/TextMeshPro has no built-in RTL shaping (Unity forum).
- Fonts and audio per locale: Asset Table Collections (font assets, LocalizedAudioClip,
  sprites); fallback font assets per script.
- Verify: play → `execute_code` `LocalizationSettings.SelectedLocale =
  LocalizationSettings.AvailableLocales.GetLocale("de")` → `manage_ui` `render_ui` or
  `manage_camera` screenshot → `ui_check.py`. `loc_check.py --src Assets/_Project/UI
  Assets/_Project/Scripts --tables loc/export.csv`.

## Unreal 5.8 (Epic Unreal MCP)

- User-facing text is `FText`: `#define LOCTEXT_NAMESPACE "Hud"` … `LOCTEXT("AmmoCount",
  "{Ammo} / {Max}")` … `#undef LOCTEXT_NAMESPACE`; `NSLOCTEXT(ns, key, source)`; `FText::Format`
  with named arguments; `INVTEXT` / `FText::AsCultureInvariant` for text that must not translate;
  never `FText::FromString` with a literal (loc_check flags it). FText → FString loses the
  localization data.
- String Tables per domain (`ST_UI`), created and filled with `StringTableTools` (`create`,
  `set_entry`, `import_file` from a CSV with `Key,SourceString` and metadata such as `Comment`,
  `list_keys` — confirm with `describe_toolset`). Widgets point their Text at a table entry via
  `ObjectTools.set_properties` (value format UNVERIFIED — read back with `get_properties`); C++
  `LOCTABLE(table id, key)` / `FText::FromStringTable`.
- Localization Dashboard (Tools menu): target Game, native culture = source locale, cultures
  added; Gather Text → Export Text (PO) → translate → Import Text → Count Words → Compile Text.
  Its settings are `Config/Localization/*.ini`, which the guard keeps out of text edits, and no
  dashboard toolset is documented for the 5.8 MCP (UNVERIFIED) — ask the user to run the steps
  and say so in the handoff. loc_check reads the exported PO files (path per target, check
  `Content/Localization/Game/<culture>/Game.po` — UNVERIFIED).
- Plurals and gender: `{N}|plural(one=…,few=…,other=…)`, `{P}|ordinal(one=st,two=nd,few=rd,
  other=th)`, `{G}|gender(masculine,feminine,neuter)`, Korean `|hpp(…)`; backticks escape braces.
- Numbers and dates: `FText::AsNumber` (1,234.5 en, 1 234,5 fr), `AsPercent`, `AsCurrencyBase`,
  `AsDate`, `AsTime`, `AsDateTime`.
- Fonts: a composite font — default family plus Sub-Font Families with `Cultures` (`ja`,
  `zh-Hans`, …) and character ranges; or per-culture font assets by asset localization.
- RTL: panels' Flow Direction Preference = Culture (Inherit, Culture, LeftToRight, RightToLeft).
- Debug: `-culture=keys` typed in the console shows keys instead of text — any readable sentence is
  not localized; `Slate.LogPaintedText 1` logs painted text. No pseudo-locale is documented for
  5.8: test expansion with the longest real locale or a dev-only culture filled with a
  pseudo-transformed PO (UNVERIFIED that a spare culture can be added for this).
- Per-culture VO: Dialogue Waves gathered per culture; localized assets by asset localization.

## Sources

1. Godot 4.7 docs: Internationalizing games; Localization using spreadsheets; Localization using
   gettext; Pseudolocalization; Using fonts.
2. Godot 4.6 class reference: ProjectSettings (`internationalization/*`), Node
   (`auto_translate_mode`, `NOTIFICATION_TRANSLATION_CHANGED`), TranslationServer, Control, Label,
   ResourceImporterCSVTranslation, ResourceImporterDynamicFont; editor sources
   `localization_editor.cpp`, `template_generator.cpp`, `resource_importer_csv_translation.cpp`.
3. Unity Localization 1.5 manual and API: Smart Strings, Plural and Choose formatters,
   Pseudo-Localization, CSV extension (`Csv`, `KeyIdColumns`, `LocaleColumns`), UI Toolkit
   bindings, `LocalizationEditorSettings`; Unity 6 manual package page (1.5.13).
4. Unity 6 manual: Advanced Text Generator, language direction; Unity Discussions "Announcing full
   RTL language support" (UI Toolkit only).
5. Unreal Engine 5.8 docs: Text Localization, Localization Dashboard, String Tables, Debugging
   Localization Keys, Asset Localization, Font Asset and Editor; EFlowDirectionPreference API.
6. Unicode CLDR Language Plural Rules chart.
7. W3C Internationalization, "Text size in translation" (IBM expansion table).
8. Google/Adobe Noto CJK repository (language-specific JP/KR/SC/TC/HK fonts, `locl`).
9. Xbox Accessibility Guidelines 104 and BBC subtitle guidelines via `kiln:accessibility`.
