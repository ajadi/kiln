# Dialogue systems, licences and Kiln dialogue formats

Licences and versions as checked on 2026-10-06 (GitHub API and the projects' docs). Re-check the
licence file of the exact release you install; record it in `memory/decisions.md` and in the
game's credits list.

## Systems

| System | Licence | Engines / status | Line IDs, localization | Notes |
|---|---|---|---|---|
| Yarn Spinner core (compiler, language) | MIT | engine-agnostic | `#line:ID`, auto-tagging (random or descriptive), string tables | `.yarn` text; node groups with `when:`, `<<jump>>`, `<<detour>>`, saliency |
| Yarn Spinner for Unity | MIT | Unity, v3.x stable | built-in or Unity Localization line providers, voice-over line providers | paid store builds exist; GitHub/OpenUPM free |
| Yarn Spinner for Godot (GDScript) | **YSPL 1.0** | Godot 4.6+ standard build, early access 3.2 | Godot translation system, VO per line | see YSPL below |
| Yarn Spinner for Godot (C#) | MIT | Godot 4 .NET, work in progress, no official support | CSV export → Godot `.translation` | needs the .NET editor |
| Yarn Spinner for Unreal | **YSPL 1.0** | UE 5.4+, pre-release | localisation, VO | Blueprint-accessible |
| Ink (inkle) | MIT | engine-agnostic (C# runtime) | no built-in line IDs — Ink-Localiser (MIT) adds `#id:` tags, exports CSV/JSON/PO | `inklecate` warns on loose ends ("Apparent loose end") |
| ink-unity-integration | MIT | Unity | via Ink-Localiser or tags | official inkle package |
| godot-ink (paulloz) | MIT | Godot 4 .NET only; last release v1.1.2 (2024-02) | tags | needs the .NET editor and a `.csproj` |
| Inkpot (The Chinese Room) | MIT | UE 5.7 / 5.8 | tags | community plugin |
| Godot Dialogue Manager (nathanhoad) | MIT | v4 for Godot 4.6+ (v3.10 for 4.4–4.5), v4.1.0 (2026-09) | static IDs `[ID:KEY]` become the translation key (POT msgid / CSV key, v4); `##` comments become translator notes | `.dialogue` text, example balloon scene, C# wrapper |
| Dialogic 2 | MIT | Godot 4.5+, still alpha (2.0-alpha-20, 2026-07) | timeline-based | visual-novel tool; alpha risk is the user's call |
| Unreal Dialogue Wave + Dialogue Voice | engine | Unreal | per-context audio, spoken text, subtitle override, actor direction, localization dialogue scripts | engine-native VO assets |
| Unreal CommonConversation | engine plugin | Unreal, **experimental** | — | conversation graph of tasks and choices |

**Yarn Spinner Public Licence (YSPL) 1.0** (GDScript and Unreal integrations): free for games,
including commercial; **mandatory player-visible credit** (splash, credits, about page or store
page) next to other middleware credits; no competing dialogue tools built from it; redistribution
of unmodified source not allowed; **no AI training**, and when AI tools are used you must take
reasonable steps (training opt-out, telemetry off) so they do not send the plugin's source or docs
to a remote service for training — your own `.yarn` scripts and code calling the public API are
exempt. Kiln consequence: agents work from the public API docs and the user's scripts, do not read
or paste the plugin source, and the user confirms the account's training opt-out before adoption.

## Choosing

1. Barks, item/UI text and linear lines → Kiln line table (no plugin): CSV/JSON →
   Godot CSV translation, Unity Localization string table, Unreal String Table / DataTable.
2. Branching conversations → the engine row of the SKILL.md table. Prefer MIT when the choices are
   otherwise equal; a YSPL plugin is fine if the user accepts the credit and AI-tool duties.
3. Needs the engine's .NET/C# build (godot-ink, Yarn Godot C#)? Only if the project already uses
   C# — never switch the editor build for a dialogue plugin without the user.
4. Whatever runs the dialogue, the writer keeps the source text in `dialogue/` (or the engine's
   folder the plugin requires) and lints it, or lints its CSV/POT export.

Lint paths: Yarn → `dialogue_lint.py` directly. Kiln JSON/CSV → directly. Ink → `inklecate`
warnings for loose ends + Ink-Localiser CSV → lint the CSV (`--id-col`/`--text-col` if the
headers differ). Dialogue Manager → its editor errors for broken jumps (read through the engine
MCP log) + the generated CSV (`keys,en,…`) → lint the CSV.

## Yarn conventions the lint understands

- Entry nodes: a node titled `Start`, nodes with `tags: entry`, or `--entry NAME`.
- Every line and option carries `#line:<ID>`; other tags (`#tone:sarcastic`) are notes.
- End a node with `<<stop>>` or `<<jump X>>`; a node tagged `end` or used only as a `<<detour>>`
  target may simply run out.
- Dynamic jumps (`<<jump {$next}>>`) are reported and switch off the unreachable check.

## Kiln dialogue JSON (`kiln-dialogue/1`)

Engine-neutral graph for conversations and quest dialogue when no plugin is used:

```json
{
  "format": "kiln-dialogue/1",
  "entries": ["Q01_SMITH_START"],
  "nodes": [
    {"id": "Q01_SMITH_START",
     "lines": [{"id": "Q01_SMITH_0010", "speaker": "SMITH", "text": "Need a blade?",
                "notes": "gruff, busy hammering", "max_chars": 80}],
     "choices": [
       {"id": "Q01_PLAYER_0020", "text": "Show me.", "next": "Q01_SMITH_SHOP"},
       {"id": "Q01_PLAYER_0030", "text": "I need the cellar key.", "condition": "q01_stage == 2",
        "next": "Q01_SMITH_KEY"},
       {"id": "Q01_PLAYER_0040", "text": "Later.", "end": true}]},
    {"id": "Q01_SMITH_SHOP", "lines": [], "end": true, "action": "open_shop"},
    {"id": "Q01_SMITH_KEY",
     "lines": [{"id": "Q01_SMITH_0050", "speaker": "SMITH", "text": "Cellar's yours. Mind the rats."}],
     "end": true, "action": "give_item:cellar_key"}
  ]
}
```

A node continues with one of: `choices`, `next`, or `"end": true` — anything else is a dead end.
A choice continues with its own `next`, the node's `next`, or `"end": true`. `condition` and
`action` are strings the gameplay runner evaluates (names from `memory/registries.md`); the
writer never puts code in them. Each `id` is the localization key and VO file stem.

## Kiln line table (CSV)

`id,speaker,text,context,max_chars` (extra columns allowed: `concept`, `criteria`, `notes`,
`status`). Godot translation CSVs (`keys,en,de,…`) are read too: `keys` is the ID column and
`--lang` picks the text column. Per-row `max_chars` overrides `--max-chars` (UI labels, journal
lines).
