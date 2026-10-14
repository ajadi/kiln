# Save system — engine notes, code and the fixture manifest

Read with the save-system skill. Code is a starting sketch: adapt names, keep the rules
(header + body, integer version, migration chain on raw data, temp + replace + `.bak`, recovery
order, no executable data).

## Godot 4.6/4.7

Save is one of the allowed autoloads (engine-godot § Scene composition). Record it in
`memory/decisions.md`; the save format and version in `memory/registries.md`.

```gdscript
# scripts/save/save_service.gd — autoload "Save"
extends Node

const CURRENT_VERSION: int = 3
const FIRST_VERSION: int = 1
const DIR: String = "user://saves"

var _seq: int = 0

func _init() -> void:
	# FileAccess WRITE goes to a temp file that replaces the target on close
	# (Windows ReplaceFileW, POSIX rename). Global: affects every FileAccess write.
	OS.set_use_file_access_save_and_swap(true)

func write_slot(slot: String, state: Dictionary) -> Error:
	DirAccess.make_dir_recursive_absolute(DIR)
	var path: String = "%s/%s.json" % [DIR, slot]
	var body: String = JSON.stringify(state, "\t")
	_seq += 1
	var header: Dictionary = {"save_version": CURRENT_VERSION, "save_seq": _seq,
		"game_version": ProjectSettings.get_setting("application/config/version", ""),
		"sha256": body.sha256_text()}
	if FileAccess.file_exists(path):
		DirAccess.copy_absolute(path, path + ".bak")  # previous good save
	var f: FileAccess = FileAccess.open(path, FileAccess.WRITE)
	if f == null:
		return FileAccess.get_open_error()
	f.store_string(JSON.stringify(header) + "\n" + body)
	f.close()  # the temp file replaces the target here
	return OK

func read_slot(slot: String) -> Dictionary:
	var path: String = "%s/%s.json" % [DIR, slot]
	for candidate: String in [path, path + ".bak"]:
		var data: Dictionary = _read(candidate)
		if not data.is_empty():
			return data
	return {}  # caller: offer the newest autosave, never start over silently

func _read(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var text: String = FileAccess.get_file_as_string(path)
	var nl: int = text.find("\n")
	if nl < 0:
		return {}
	var header: Variant = JSON.parse_string(text.substr(0, nl))
	var body: String = text.substr(nl + 1)
	if typeof(header) != TYPE_DICTIONARY or body.sha256_text() != str(header.get("sha256")):
		push_warning("save %s damaged" % path)
		return {}
	var version: int = int(header.get("save_version", 0))
	if version > CURRENT_VERSION or version < FIRST_VERSION:
		return {}  # newer build or unsupported: refuse, keep the file
	var data: Variant = JSON.parse_string(body)
	if typeof(data) != TYPE_DICTIONARY:
		return {}
	for v: int in range(version, CURRENT_VERSION):
		data = _migrate(v, data)
	_seq = maxi(_seq, int(header.get("save_seq", 0)))
	return data  # validate (ids exist, ranges, sizes) before building game state

func _migrate(from: int, d: Dictionary) -> Dictionary:
	match from:
		1:  # v1 -> v2: hp moved under player, fov added
			d["player"] = {"health": int(d.get("hp", 100))}
			d.erase("hp")
			d.get_or_add("settings", {})["fov"] = 90
		2:  # v2 -> v3
			d.erase("legacy_flags")
			d["inventory"] = []
	return d
```

- JSON numbers come back as `float`: convert ids, counts and enums with `int()`.
- `Vector3`, `Color`, `Transform3D`: store as arrays by hand, or `JSON.from_native(value)` /
  `JSON.to_native(value)` with the object flags left `false`.
- `DirAccess.rename_absolute` on Windows deletes an existing target and then moves (not atomic) —
  hence the `.bak` copy and the recovery order. Godot does not fsync on close: power loss can still
  truncate the newest file; the checksum + `.bak` handle it.
- `RandomNumberGenerator.state` can be saved and restored to continue a seeded sequence.
- Capturing a fixture from the running game (editor run, `editor_manage` game eval):
  `DirAccess.copy_absolute(ProjectSettings.globalize_path("user://saves/slot_1.json"),
  ProjectSettings.globalize_path("res://tests/saves/v3/midgame.json"))`.
- Tests: a GUT/gdUnit suite in `tests/` iterates `res://tests/saves/v*/` and loads each file
  through `Save._read`, asserting a non-empty, valid result; bad cases in `tests/saves/bad/`.

## Unity 6

```csharp
[Serializable] public class SaveData { public PlayerData player; public List<ItemStack> inventory; }

public static class SaveIO {
    public static void Write(string path, string headerJson, string body) {
        string tmp = path + ".tmp", bak = path + ".bak";
        using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None))
        using (var w = new StreamWriter(fs, new UTF8Encoding(false))) {
            w.Write(headerJson); w.Write('\n'); w.Write(body);
            w.Flush(); fs.Flush(true);                 // flush OS buffers to disk
        }
        if (File.Exists(path)) File.Replace(tmp, path, bak); else File.Move(tmp, path);
    }
    public static string Sha256(string body) {
        using var sha = SHA256.Create();
        return BitConverter.ToString(sha.ComputeHash(new UTF8Encoding(false).GetBytes(body)))
            .Replace("-", "").ToLowerInvariant();
    }
}
```

- Path: `Path.Combine(Application.persistentDataPath, "saves")`. Fix company and product names
  before release.
- `JsonUtility`: `[Serializable]` classes and structs, `List<T>` and arrays; no dictionaries,
  no top-level arrays or primitives; unknown JSON fields are ignored, missing ones keep the
  constructor defaults (so a forgotten migration fails silently — the fixture tests catch it).
- Migrations need a JSON tree: the Newtonsoft Json package (`com.unity.nuget.newtonsoft-json`),
  `JObject.Parse(body)` → migrate the `JObject` → `ToObject<SaveData>()`. Never a
  `TypeNameHandling` other than `None` (type names from the file decide what is instantiated). Never
  `BinaryFormatter`.
- Write numbers with `CultureInfo.InvariantCulture` (Newtonsoft's default `Culture` is invariant;
  JsonUtility's culture handling is UNVERIFIED).
- Where `File.Replace` is unavailable on a target platform, use A/B slots with `save_seq`.
- Tests: an EditMode test enumerates `tests/saves/v*/*.json` (outside `Assets/`, read by path),
  loads each through the real loader and asserts the validated result.

## Unreal 5.8

```cpp
UCLASS()
class UKilnSaveGame : public ULocalPlayerSaveGame
{
    GENERATED_BODY()
public:
    UPROPERTY(SaveGame) int32 SaveSeq = 0;
    UPROPERTY(SaveGame) FPlayerSave Player;
    UPROPERTY(SaveGame) TArray<FItemStack> Inventory;

    virtual int32 GetLatestDataVersion() const override { return 3; }
    virtual void HandlePostLoad() override;   // migrate from GetSavedDataVersion() up to latest
};
```

- `UGameplayStatics::AsyncSaveGameToSlot` serialises on the game thread, writes on a worker and
  calls back on the game thread; `SaveGameToSlot` (sync) is fine in menus or while paused. Some
  platforms cannot load and save at the same time (UNVERIFIED).
- Files land in `Saved/SaveGames/<slot>.sav` on desktop. Whether the default save system replaces
  the file atomically is UNVERIFIED — write A/B slots (`<name>_a`, `<name>_b`) with `SaveSeq` and
  load the newest that deserialises and validates.
- `USaveGame` data is tagged property serialization: added properties default, removed ones are
  skipped, renamed ones lose their value unless redirected (CoreRedirects `PropertyRedirects`)
  or migrated in `HandlePostLoad`. Practitioner rule: add, don't rename or reorder.
- Store asset references as ids mapped through a DataTable or Primary Asset Ids, not raw soft
  object paths read back from the file.
- `.sav` is binary: fixtures are `.sav` files per version under `tests/saves/v<N>/`, loaded by an
  Automation test; if the game also writes a JSON debug export, `save_check.py` checks that.

## Fixture manifest (`tests/saves/manifest.json`)

```json
{
  "current_version": 3,
  "first_version": 1,
  "version_field": "save_version",
  "fixtures": "v*/**/*.json",
  "migrations": [
    {"from": 1, "to": 2, "rename": {"hp": "player.health"}, "add": ["settings.fov"]},
    {"from": 2, "to": 3, "remove": ["legacy_flags"], "add": ["inventory"]}
  ],
  "schemas": {
    "1": {"fields": ["hp", "settings", "legacy_flags.*"], "required": ["hp"]},
    "2": {"fields": ["player.health", "settings", "legacy_flags.*"], "required": ["player.health"]},
    "3": {"fields": ["player.health", "settings.fov", "inventory[].id", "inventory[].count"],
          "required": ["player.health", "settings.fov", "inventory"]}
  },
  "checksum": {"field": "sha256", "algo": "sha256"}
}
```

Paths: `a.b` nested keys, `list[]` every element, `*` any key; a declared path allows everything
below it. The `rename`/`add`/`remove` lists mirror what the migration code does — when they are
declared on every step, `save_check.py` migrates each fixture's field set on paper and reports
fields the code forgot to move, drop or default. Update the manifest in the same change as the
migration code; the checker cannot see the code itself.
