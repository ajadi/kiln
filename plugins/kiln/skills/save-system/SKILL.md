---
name: save-system
description: Designing, building and verifying game saves — what to save versus derive, JSON with an integer save_version and a migration chain, atomic writes (temp file + replace, previous file kept as backup), slots and autosave cadence, checksums and recovery, platform paths, Steam Cloud, security (saves are untrusted data, never code), golden fixtures per save version and the release gate that earlier saves load, with Godot 4.6/4.7, Unity 6 and Unreal 5.8 notes. Use when adding or changing anything that is saved, before a release, or when a save bug is reported.
user-invocable: false
---

# Save system

A save file is a public API with a version: players keep it across every patch. Build N loads
every save any shipped build wrote, or says why not and leaves the file untouched. Engine code:
`${CLAUDE_SKILL_DIR}/references/engine-notes.md`. Checker: `${CLAUDE_SKILL_DIR}/scripts/save_check.py`.
Values marked (working) are starting points.

## 1. Save the minimum authoritative state, derive the rest

| Save | Derive on load, never save |
|---|---|
| ids of what is owned, unlocked, killed, opened | anything in the level scene or data tables |
| per-instance state that differs from the authored default (part HP, ammo, moved objects) | values computed from others (max HP from level + gear, totals) |
| progress flags, quest stage ids, counters, seed + state of seeded systems | caches, navmesh, UI state, velocities of sleeping debris |
| game clock (sky skill) and the weather state with its accumulators (weather skill) | sun/moon direction, light curves, particles — derived from the clock and the state |

- Reference content by stable string ids (`"weapon.smg_mk2"`), never scene paths, node names,
  array indices or engine object ids — those change when content moves.
- Store the world as deltas from the authored level (destroyed, opened, moved), so level edits
  after release still apply.
- Separate files, one owner each: `settings` (per machine, not cloud-synced), `profile.json`
  (meta progress), `slot_<n>.json` (a campaign or run).

## 2. Format and versioning

- JSON by default: readable, diffable, fixtures in git. Binary only when size or load time is
  measured to need it, and then with a debug JSON dump of the same data.
- File = header line + body. Header: `{"save_version": 3, "game_version": "0.4.1",
  "save_seq": 118, "sha256": "<hex of the body bytes>"}`, newline, then the JSON body.
- `save_version` is an integer bumped on every change of the body's shape or meaning;
  `game_version` is informational.
- Migrations: an ordered list of pure functions `v_N -> v_N+1` on the raw dictionary, before it is
  mapped into game objects. A shipped migration is never edited; fix forward. New fields get
  explicit defaults in the migration.
- Loader: header → newer than current: refuse ("made by a newer version"), never overwrite → older
  than the first supported: refuse with a message → apply the chain → validate (types, ranges,
  ids exist; clamp) → build state. The migrated data is written on the next normal save.
- Fields unknown after migration: logged and dropped in release; in tests they fail (a migration
  is missing).

## 3. Writing safely

1. Snapshot state on the game thread at a safe point; serialise; write on a worker thread when
   the main-thread cost exceeds ~2 ms (working). Measure the hitch.
2. Write `slot_1.json.tmp`, flush, close.
3. Replace `slot_1.json` with the temp file, keeping the old one as `slot_1.json.bak` — one OS
   replace call where the engine offers it.
4. One write per slot at a time: queue only the latest pending snapshot.
5. Where rename is unavailable (platform save APIs, Unreal slots): two slots A/B, write the
   older one, the header carries an increasing `save_seq`, load the newest valid one.

## 4. Slots and autosave (working values)

- Manual slots 3–10, a quicksave, a rotating autosave ring of 3; newest by `save_seq`.
- Autosave on: entering an area, checkpoints, after a boss or major reward, after spending
  currency, on quit, on app pause or suspend (mobile focus loss, Steam Deck sleep), and every
  5–10 min of play at the next safe moment.
- Never autosave in combat, airborne, in a cutscene or with death pending — a save that loads
  into certain death is a softlock.
- Show a save indicator; never block input. Roguelike/ironman: one slot, saved on every room
  transition and on quit, closed on death.

## 5. Corruption detection and recovery

- Detect: header parse, body length, checksum over the body bytes (sha256; crc32 where hashing
  costs), JSON parse, validation. A checksum detects damage, not cheating: anyone can recompute
  it; an HMAC with a key in the client only deters casual edits.
- Recover in order: `slot.json` → a complete, valid `slot.json.tmp` (crash between write and
  replace) → `slot.json.bak` → newest valid autosave. Tell the player what was restored.
- Never start a new game over a slot that failed to load and never overwrite it; rename it
  `slot.json.corrupt-<timestamp>` and attach it to bug reports.

## 6. Paths and cloud

| Engine | Location |
|---|---|
| Godot | `user://` = `%APPDATA%\Godot\app_userdata\<project>` on Windows; set `application/config/use_custom_user_dir` (+ `custom_user_dir_name`) before the first release — renaming the project moves the folder otherwise |
| Unity | `Application.persistentDataPath` = `%USERPROFILE%\AppData\LocalLow\<company>\<product>`; changing company or product name orphans saves |
| Unreal | `SaveGameToSlot` → `Saved/SaveGames/<slot>.sav` |

Web builds store files in IndexedDB — test that a reload keeps them. Consoles: platform save APIs.

Steam Cloud: **Auto-Cloud** needs no code — Steamworks config of a root (e.g. WinAppDataLocalLow),
subdirectory (`{64BitSteamID}` for per-user folders), pattern, byte and file quotas; it syncs at
launch and exit; root overrides map other OS paths for cross-platform saves; dynamic Cloud sync
uploads on Steam Deck suspend. Use the **ISteamRemoteStorage API** when the game must choose
which files sync. Keep settings out of the cloud; few, small files.

## 7. Saves are untrusted data, never code

Saves get shared, downloaded and edited. Validate everything: ids exist, numbers finite and in
range, list sizes and string lengths capped.

- Godot: never `ResourceLoader.load()` a `.tres/.res` from `user://`, nor `ConfigFile` or
  `str_to_var` on shared files — they can instantiate objects with embedded scripts (godot#80562,
  open, confirmed). Use JSON mapped by hand; `get_var` with `allow_objects=false`,
  `bytes_to_var` (never the `_with_objects` variants).
- Unity: never `BinaryFormatter` (dangerous, obsolete since .NET 5); `JsonUtility`, or Newtonsoft
  with `TypeNameHandling.None`.
- Unreal: `USaveGame` stores `UPROPERTY` values; do not load class or asset paths read from a save
  without mapping them through an allow-list of ids.

## 8. Tests and the release gate

- **Golden fixtures**: `tests/saves/v<N>/<case>.json` — files written by a real build at version N
  (new game, mid-game with a full inventory, late game, edge cases), committed, never edited; a
  new folder with every version bump. Damaged, truncated and future-version cases go to
  `tests/saves/bad/` with the expected outcome (recover from `.bak` / refuse).
- **Manifest** `tests/saves/manifest.json`: `current_version`, `first_version`, `migrations` with
  field operations (`rename`/`add`/`remove`), per-version `schemas` (allowed and required paths),
  `checksum`. Run `python "${CLAUDE_SKILL_DIR}/scripts/save_check.py" tests/saves/manifest.json
  --out production/save_check.json`: chain complete from every supported version, a fixture per
  version, folder = version, no unknown or missing fields, checksums, each migration ends on the
  current schema on paper. Exit 1 on fail. It does not run game code.
- **Engine tests** (Godot `test_run`, Unity EditMode, Unreal Automation): every fixture loads
  through the real loader, migrates and validates with no errors or warnings; round trip at the
  current version (`save(load(x))` equals `x` after normalising); every bad case recovers or
  refuses as expected without modifying the file; an interrupted write never replaces the good
  file.
- **Release gate "earlier saves load"**: save_check verdict pass and the engine fixture tests
  green on the release build. A save-format change is a registry change: record it in
  `memory/registries.md` and send it to review.

## 9. Engine notes (details and code in references/engine-notes.md)

- **Godot 4.6/4.7**: Save autoload, `FileAccess` + `JSON` (numbers come back as float — `int()`
  ids and counters), `OS.set_use_file_access_save_and_swap(true)` for temp-and-replace writes.
- **Unity 6**: `[Serializable]` save classes + `JsonUtility` or Newtonsoft; `File.Replace(tmp,
  path, bak)`.
- **Unreal 5.8**: `USaveGame` / `ULocalPlayerSaveGame` (`GetLatestDataVersion`, `HandlePostLoad`
  for migrations), `AsyncSaveGameToSlot`, A/B slots.
